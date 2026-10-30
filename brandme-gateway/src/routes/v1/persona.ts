/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1 persona, recommendations, guest migration and the persona card
 * (lane: opus-consumer-domains), mounted from index.ts behind
 * principalMiddleware.
 *
 * The gateway is the identity boundary: `res.locals.principal` comes from the
 * foundation session/bearer middleware, never from the body or query. This
 * router does cheap shape, scope, If-Match and Idempotency-Key checks, then
 * forwards to the Python persona domain through an injected `DomainClient`.
 * The domain enforces every invariant again. How the client proves the
 * principal to Python (signed assertion vs relay) is chosen by the foundation
 * lane (proposal PD-07 in docs/build/status/opus-consumer-domains.md).
 *
 * This file also exports the shared helpers used by this lane's other
 * routers (wardrobe, outfits, social, decisions, rewards, media, tryon).
 */

import { Router, type NextFunction, type Request, type Response } from 'express';
import { ApiProblem, handle, problems } from '../../middleware/problem';
import { requirePrincipal } from '../../middleware/session';
import type { Principal } from '../../types';

export interface DomainRequest {
  method: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  /** Path on the domain service, mirroring the public path (e.g. `/me/persona`). */
  path: string;
  /** Null only on routes that explicitly allow anonymous callers (share-link resolve). */
  principal: Principal | null;
  requestId: string;
  body?: unknown;
  query?: Record<string, string>;
  ifMatch?: string;
  idempotencyKey?: string;
}

export interface DomainResponse {
  status: number;
  body: unknown;
  headers?: Record<string, string>;
}

/** Transport to the Python domain services (injected at mount time). */
export interface DomainClient {
  request(req: DomainRequest): Promise<DomainResponse>;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const IF_MATCH_RE = /^(?:W\/)?"?(\d{1,18})"?$/;
/** Identity/authority never comes from a request body (ch.03 §3). */
const IDENTITY_FIELDS = ['user_id', 'member_id', 'owner_id', 'principal', 'scopes', 'actor_ref', 'delegation_id'];

export function requireScope(scope: string) {
  return (_req: Request, res: Response, next: NextFunction): void => {
    const p: Principal | undefined = res.locals.principal;
    if (!p) return next(problems.unauthenticated());
    if (!p.scopes.includes(scope)) return next(problems.forbidden(`Scope ${scope} is required.`));
    next();
  };
}

export function ifMatch(req: Request): string {
  const header = req.header('if-match');
  if (!header || !IF_MATCH_RE.test(header.trim())) throw problems.preconditionRequired();
  return header.trim();
}

export function idempotencyKey(req: Request): string {
  const key = req.header('idempotency-key');
  if (!key || key.length < 16 || key.length > 128) {
    throw new ApiProblem(400, 'idempotency_key_invalid', 'Idempotency-Key required', 'Send an Idempotency-Key of 16-128 characters.');
  }
  return key;
}

/** Path parameter that must be an opaque UUID; anything else is simply not found. */
export function uuidParam(req: Request, name: string): string {
  const v = req.params[name];
  if (!v || !UUID_RE.test(v)) throw problems.notFound();
  return v.toLowerCase();
}

export function objectBody(req: Request, maxKeys = 32): Record<string, unknown> {
  const b = req.body;
  if (b === undefined || b === null) return {};
  if (typeof b !== 'object' || Array.isArray(b)) throw problems.invalid('Request body must be a JSON object.');
  const keys = Object.keys(b);
  if (keys.length > maxKeys) throw problems.invalid('Request body has too many fields.');
  const identity = keys.filter((k) => IDENTITY_FIELDS.includes(k));
  if (identity.length) throw problems.invalid(`Identity cannot be set by the request: ${identity.join(', ')}.`);
  return b as Record<string, unknown>;
}

export function pickQuery(req: Request, allowed: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of allowed) {
    const v = req.query[k];
    if (typeof v === 'string' && v.length > 0 && v.length <= 512) out[k] = v;
  }
  return out;
}

/** Relay the domain response: status, body, ETag; problem bodies keep their media type. */
export function relay(res: Response, r: DomainResponse): void {
  const etag = r.headers?.etag ?? r.headers?.ETag;
  if (etag) res.setHeader('ETag', etag);
  if (r.status === 204) {
    res.status(204).end();
    return;
  }
  if (r.status >= 400) {
    res.status(r.status).type('application/problem+json').send(JSON.stringify(r.body));
    return;
  }
  res.status(r.status).json(r.body);
}

export function forwardTo(client: DomainClient, build: (req: Request, res: Response) => Omit<DomainRequest, 'principal' | 'requestId'>) {
  return handle(async (req: Request, res: Response) => {
    const spec = build(req, res);
    const r = await client.request({ ...spec, principal: res.locals.principal as Principal, requestId: res.locals.requestId });
    relay(res, r);
  });
}

/** Like forwardTo, for the few routes where a signed-in principal is optional. */
export function forwardOptionalPrincipal(
  client: DomainClient,
  build: (req: Request, res: Response) => Omit<DomainRequest, 'principal' | 'requestId'>,
) {
  return handle(async (req: Request, res: Response) => {
    const spec = build(req, res);
    const principal = (res.locals.principal as Principal | undefined) ?? null;
    const r = await client.request({ ...spec, principal, requestId: res.locals.requestId });
    relay(res, r);
  });
}

function personaPatchShape(b: Record<string, unknown>): void {
  const changes = b.changes;
  if (!Array.isArray(changes) || changes.length > 12) throw problems.invalid('changes must be an array of at most 12 axis changes.');
  if (typeof b.client_revision !== 'string' || b.client_revision.length < 1 || b.client_revision.length > 64) {
    throw problems.invalid('client_revision is required (1-64 characters).');
  }
}

export function personaRouter(client: DomainClient): Router {
  const r = Router();
  r.use(['/me/persona', '/me/guest-migration', '/recommendations'], requirePrincipal);

  r.get('/me/persona', requireScope('profile:read'), forwardTo(client, () => ({ method: 'GET', path: '/me/persona' })));

  r.patch(
    '/me/persona',
    requireScope('profile:write'),
    forwardTo(client, (req) => {
      const tag = ifMatch(req);
      const body = objectBody(req);
      personaPatchShape(body);
      return { method: 'PATCH', path: '/me/persona', body, ifMatch: tag };
    }),
  );

  r.post(
    '/me/persona/preview',
    requireScope('profile:read'),
    forwardTo(client, (req) => {
      const body = objectBody(req);
      personaPatchShape({ changes: body.changes ?? [], client_revision: body.client_revision });
      return { method: 'POST', path: '/me/persona/preview', body, query: pickQuery(req, ['occasion']) };
    }),
  );

  r.get(
    '/me/persona/evidence',
    requireScope('profile:read'),
    forwardTo(client, (req) => ({ method: 'GET', path: '/me/persona/evidence', query: pickQuery(req, ['cursor', 'limit']) })),
  );

  r.post(
    '/me/persona/evidence/:evidenceId/suppress',
    requireScope('profile:write'),
    forwardTo(client, (req) => ({
      method: 'POST',
      path: `/me/persona/evidence/${uuidParam(req, 'evidenceId')}/suppress`,
      idempotencyKey: idempotencyKey(req),
    })),
  );

  r.post(
    '/me/persona/reset',
    requireScope('profile:write'),
    forwardTo(client, (req) => {
      const tag = ifMatch(req);
      const body = objectBody(req, 2);
      if (body.confirm !== true) throw problems.invalid('Reset requires "confirm": true.');
      return { method: 'POST', path: '/me/persona/reset', body, ifMatch: tag, idempotencyKey: idempotencyKey(req) };
    }),
  );

  r.post(
    '/me/persona/snapshots',
    requireScope('profile:write'),
    forwardTo(client, (req) => ({
      method: 'POST',
      path: '/me/persona/snapshots',
      body: objectBody(req, 1),
      idempotencyKey: idempotencyKey(req),
    })),
  );

  r.get(
    '/me/persona/snapshots/:snapshotId/diff',
    requireScope('profile:read'),
    forwardTo(client, (req) => ({ method: 'GET', path: `/me/persona/snapshots/${uuidParam(req, 'snapshotId')}/diff` })),
  );

  r.post(
    '/me/persona/snapshots/:snapshotId/restore',
    requireScope('profile:write'),
    forwardTo(client, (req) => ({
      method: 'POST',
      path: `/me/persona/snapshots/${uuidParam(req, 'snapshotId')}/restore`,
      ifMatch: ifMatch(req),
    })),
  );

  r.post(
    '/me/persona/contexts',
    requireScope('profile:write'),
    forwardTo(client, (req) => ({ method: 'POST', path: '/me/persona/contexts', ifMatch: ifMatch(req), body: objectBody(req, 4) })),
  );

  r.patch(
    '/me/persona/contexts/:overrideId',
    requireScope('profile:write'),
    forwardTo(client, (req) => ({
      method: 'PATCH',
      path: `/me/persona/contexts/${uuidParam(req, 'overrideId')}`,
      ifMatch: ifMatch(req),
      body: objectBody(req, 1),
    })),
  );

  r.post(
    '/me/persona/adaptations/:axis/accept',
    requireScope('profile:write'),
    forwardTo(client, (req) => {
      const axis = req.params.axis;
      if (!/^[a-z_]{3,20}$/.test(axis)) throw problems.notFound();
      return { method: 'POST', path: `/me/persona/adaptations/${axis}/accept`, ifMatch: ifMatch(req) };
    }),
  );

  r.get(
    '/recommendations',
    requireScope('profile:read'),
    forwardTo(client, (req) => ({ method: 'GET', path: '/recommendations', query: pickQuery(req, ['occasion', 'limit', 'cursor']) })),
  );

  r.post(
    '/recommendations/:recommendationId/feedback',
    requireScope('profile:write'),
    forwardTo(client, (req) => ({
      method: 'POST',
      path: `/recommendations/${uuidParam(req, 'recommendationId')}/feedback`,
      body: objectBody(req, 2),
      idempotencyKey: idempotencyKey(req),
    })),
  );

  r.post(
    '/me/guest-migration',
    requireScope('profile:write'),
    forwardTo(client, (req) => ({
      method: 'POST',
      path: '/me/guest-migration',
      body: objectBody(req, 4),
      idempotencyKey: idempotencyKey(req),
    })),
  );

  // The living persona card (Ultra plan 02, item 6): settings are the member's own; viewing respects them.
  r.get('/me/persona/card', requireScope('profile:read'), forwardTo(client, () => ({ method: 'GET', path: '/me/persona/card' })));
  r.put(
    '/me/persona/card',
    requireScope('profile:write'),
    forwardTo(client, (req, res) => {
      if ((res.locals.principal as Principal).delegationId) throw problems.forbidden('Only the member decides who sees their card.');
      const b = objectBody(req, 3);
      const extra = Object.keys(b).filter((k) => !['audience', 'show_standings', 'highlight_item_ids'].includes(k));
      if (extra.length) throw problems.invalid(`Unknown fields: ${extra.join(', ')}.`);
      if (b.audience !== undefined && !['private', 'friends', 'members'].includes(b.audience as string)) throw problems.invalid('Unknown audience.');
      if (b.show_standings !== undefined && typeof b.show_standings !== 'boolean') throw problems.invalid('show_standings must be true or false.');
      const ids = b.highlight_item_ids;
      if (ids !== undefined && (!Array.isArray(ids) || ids.length > 6 || !ids.every((i) => typeof i === 'string' && UUID_RE.test(i)))) {
        throw problems.invalid('Pick at most 6 highlights by id.');
      }
      return { method: 'PUT', path: '/me/persona/card', body: b };
    }),
  );
  r.get('/members/:memberId/card', requirePrincipal, requireScope('social:read'),
    forwardTo(client, (req) => ({ method: 'GET', path: `/members/${uuidParam(req, 'memberId')}/card` })));

  return r;
}
