/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1 relationships, blocks, shares and notifications — UNMOUNTED router
 * (lane: opus-consumer-domains). Mount at integration after principalMiddleware:
 *
 *   router.use(socialRouter(domainClient));
 *
 * Friendship is established only by the recipient's own session accepting.
 * The target of a request/block is `target_member_id`; the caller is always
 * the verified principal. `POST /shares/resolve` is the one route that accepts
 * anonymous callers (public/unlisted share links); the token travels in the
 * body so it does not land in URL access logs. It should sit behind the
 * foundation rate limiter at mount time.
 */

import { Router, type NextFunction, type Request, type Response } from 'express';
import { problems } from '../../middleware/problem';
import { requirePrincipal } from '../../middleware/session';
import type { Principal } from '../../types';
import {
  forwardOptionalPrincipal,
  forwardTo,
  idempotencyKey,
  objectBody,
  pickQuery,
  requireScope,
  uuidParam,
  type DomainClient,
} from './persona';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const TOKEN_RE = /^[A-Za-z0-9_-]{16,128}$/;
const SHARE_SUBJECTS = ['outfit_version', 'wardrobe_item', 'closet_capsule', 'persona_snapshot', 'badge'];
const AUDIENCES = ['selected_members', 'unlisted', 'public'];

function target(req: Request): { target_member_id: string } {
  const b = objectBody(req, 1);
  const id = b.target_member_id;
  if (typeof id !== 'string' || !UUID_RE.test(id)) throw problems.invalid('target_member_id must be a member id.');
  return { target_member_id: id.toLowerCase() };
}

/** Cheap shape check of contracts #ShareCreate; the domain re-checks and applies the field allowlist. */
export function shareShape(b: Record<string, unknown>): void {
  const extra = Object.keys(b).filter((k) => !['subject_type', 'subject_id', 'audience', 'allowed_fields', 'recipient_ids', 'expires_at'].includes(k));
  if (extra.length) throw problems.invalid(`Unknown fields: ${extra.join(', ')}.`);
  if (typeof b.subject_type !== 'string' || !SHARE_SUBJECTS.includes(b.subject_type)) throw problems.invalid('Unknown subject_type.');
  if (typeof b.subject_id !== 'string' || !UUID_RE.test(b.subject_id)) throw problems.invalid('subject_id must be an id.');
  if (typeof b.audience !== 'string' || !AUDIENCES.includes(b.audience)) throw problems.invalid('Unknown audience.');
  const fields = b.allowed_fields;
  if (!Array.isArray(fields) || fields.length < 1 || fields.length > 30 || !fields.every((f) => typeof f === 'string' && f.length >= 1 && f.length <= 64)) {
    throw problems.invalid('allowed_fields must list 1-30 field names.');
  }
  const recips = b.recipient_ids;
  if (!Array.isArray(recips) || recips.length > 100 || !recips.every((r) => typeof r === 'string' && UUID_RE.test(r))) {
    throw problems.invalid('recipient_ids must list at most 100 member ids.');
  }
  if (b.audience === 'selected_members' && recips.length === 0) throw problems.invalid('Choose at least one member.');
  if (typeof b.expires_at !== 'string' || Number.isNaN(Date.parse(b.expires_at))) throw problems.invalid('expires_at must be a date-time.');
}

/** Optional principal: if one is present it still needs social:read. */
function optionalReadScope(_req: Request, res: Response, next: NextFunction): void {
  const p: Principal | undefined = res.locals.principal;
  if (p && !p.scopes.includes('social:read')) return next(problems.forbidden('Scope social:read is required.'));
  next();
}

export function socialRouter(client: DomainClient): Router {
  const r = Router();

  // Anonymous-capable: registered before the principal gate below.
  r.post(
    '/shares/resolve',
    optionalReadScope,
    forwardOptionalPrincipal(client, (req) => {
      const b = objectBody(req, 1);
      if (typeof b.token !== 'string' || !TOKEN_RE.test(b.token)) throw problems.notFound();
      return { method: 'POST', path: '/shares/resolve', body: { token: b.token } };
    }),
  );

  r.use(['/relationships', '/blocks', '/shares', '/notifications'], requirePrincipal);

  r.get('/relationships', requireScope('social:read'), forwardTo(client, () => ({ method: 'GET', path: '/relationships' })));
  r.post('/relationships', requireScope('social:write'), forwardTo(client, (req) => ({ method: 'POST', path: '/relationships', body: target(req) })));
  r.post(
    '/relationships/:relationshipId/accept',
    requireScope('social:write'),
    forwardTo(client, (req) => ({ method: 'POST', path: `/relationships/${uuidParam(req, 'relationshipId')}/accept` })),
  );
  r.delete(
    '/relationships/:memberId',
    requireScope('social:write'),
    forwardTo(client, (req) => ({ method: 'DELETE', path: `/relationships/${uuidParam(req, 'memberId')}` })),
  );
  r.post('/blocks', requireScope('social:write'), forwardTo(client, (req) => ({ method: 'POST', path: '/blocks', body: target(req) })));
  r.delete('/blocks/:memberId', requireScope('social:write'), forwardTo(client, (req) => ({ method: 'DELETE', path: `/blocks/${uuidParam(req, 'memberId')}` })));

  r.get('/shares', requireScope('social:read'), forwardTo(client, () => ({ method: 'GET', path: '/shares' })));
  r.post(
    '/shares',
    requireScope('social:write'),
    forwardTo(client, (req) => {
      const body = objectBody(req, 6);
      shareShape(body);
      return { method: 'POST', path: '/shares', body, idempotencyKey: idempotencyKey(req) };
    }),
  );
  r.get('/shares/:shareId', requireScope('social:read'), forwardTo(client, (req) => ({ method: 'GET', path: `/shares/${uuidParam(req, 'shareId')}` })));
  r.delete('/shares/:shareId', requireScope('social:write'), forwardTo(client, (req) => ({ method: 'DELETE', path: `/shares/${uuidParam(req, 'shareId')}` })));

  r.get(
    '/notifications',
    requireScope('social:read'),
    forwardTo(client, (req) => ({ method: 'GET', path: '/notifications', query: pickQuery(req, ['cursor', 'limit']) })),
  );
  r.post(
    '/notifications/read',
    requireScope('social:write'),
    forwardTo(client, (req) => {
      const b = objectBody(req, 1);
      const ids = b.ids;
      if (!Array.isArray(ids) || ids.length < 1 || ids.length > 100 || !ids.every((i) => typeof i === 'string' && UUID_RE.test(i))) {
        throw problems.invalid('ids must list 1-100 notification ids.');
      }
      return { method: 'POST', path: '/notifications/read', body: { ids } };
    }),
  );
  return r;
}
