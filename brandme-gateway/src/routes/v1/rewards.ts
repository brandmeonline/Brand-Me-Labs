/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1 rewards, benefits, disputes and house standings (lane:
 * opus-consumer-domains). `rewardsRouter` is mounted from index.ts behind
 * principalMiddleware; `rewardsOpsRouter` stays unmounted until the console
 * has operator auth.
 *
 * There is deliberately no member route that awards, edits or transfers
 * points (ch.01 §5, BM-LOY-005): bodies on member routes never carry amounts.
 * `rewards:write` (proposed, PD-12) lets a member reserve a benefit or open a
 * dispute; it can never award. Operator routes need `moderation:admin` and,
 * outside development, an aal2 session; the domain checks both again and
 * refuses self-review.
 */

import { Router, type NextFunction, type Request, type Response } from 'express';
import { problems } from '../../middleware/problem';
import { requirePrincipal } from '../../middleware/session';
import type { Principal } from '../../types';
import { forwardTo, idempotencyKey, objectBody, pickQuery, requireScope, uuidParam, type DomainClient } from './persona';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const DISPUTE_CATEGORIES = ['missing_reward', 'wrong_amount', 'reversal', 'reservation', 'other'];

function onlyKeys(b: Record<string, unknown>, allowed: string[]): void {
  const extra = Object.keys(b).filter((k) => !allowed.includes(k));
  if (extra.length) throw problems.invalid(`Unknown fields: ${extra.join(', ')}.`);
}

function text(v: unknown, name: string, max: number): string {
  if (typeof v !== 'string' || v.trim().length < 1 || v.length > max) throw problems.invalid(`${name} must be 1-${max} characters.`);
  return v;
}

export function rewardsRouter(client: DomainClient): Router {
  const r = Router();
  r.use(['/rewards', '/benefits'], requirePrincipal);

  r.get('/rewards', requireScope('rewards:read'), forwardTo(client, () => ({ method: 'GET', path: '/rewards' })));
  r.get('/rewards/standings', requireScope('rewards:read'), forwardTo(client, () => ({ method: 'GET', path: '/rewards/standings' })));
  r.get(
    '/rewards/entries',
    requireScope('rewards:read'),
    forwardTo(client, (req) => ({ method: 'GET', path: '/rewards/entries', query: pickQuery(req, ['cursor', 'limit']) })),
  );
  r.get('/rewards/reservations', requireScope('rewards:read'), forwardTo(client, () => ({ method: 'GET', path: '/rewards/reservations' })));
  r.get('/rewards/disputes', requireScope('rewards:read'), forwardTo(client, () => ({ method: 'GET', path: '/rewards/disputes' })));
  r.post(
    '/rewards/disputes',
    requireScope('rewards:write'),
    forwardTo(client, (req, res) => {
      if ((res.locals.principal as Principal).delegationId) throw problems.forbidden('Disputes are opened by the member.');
      const b = objectBody(req, 3);
      onlyKeys(b, ['entry_id', 'category', 'message']);
      if (b.entry_id !== undefined && (typeof b.entry_id !== 'string' || !UUID_RE.test(b.entry_id))) throw problems.invalid('entry_id must be an id.');
      if (typeof b.category !== 'string' || !DISPUTE_CATEGORIES.includes(b.category)) throw problems.invalid('Unknown category.');
      text(b.message, 'message', 1000);
      return { method: 'POST', path: '/rewards/disputes', body: b };
    }),
  );
  r.get('/benefits', requireScope('rewards:read'), forwardTo(client, () => ({ method: 'GET', path: '/benefits' })));
  r.post(
    '/benefits/:benefitId/reservations',
    requireScope('rewards:write'),
    forwardTo(client, (req) => {
      const b = objectBody(req, 0); // the cost comes from the server-side benefit, never the request
      onlyKeys(b, []);
      return { method: 'POST', path: `/benefits/${uuidParam(req, 'benefitId')}/reservations`, idempotencyKey: idempotencyKey(req) };
    }),
  );
  return r;
}

/** moderation:admin plus aal2 outside development; agents are never operators. */
export function requireOperator(_req: Request, res: Response, next: NextFunction): void {
  const p: Principal | undefined = res.locals.principal;
  if (!p) return next(problems.unauthenticated());
  if (p.delegationId) return next(problems.forbidden('Operator session required.'));
  if (!p.scopes.includes('moderation:admin')) return next(problems.forbidden('Scope moderation:admin is required.'));
  if (p.environment !== 'development' && p.assuranceLevel !== 'aal2') return next(problems.forbidden('Operator actions need an aal2 session.'));
  next();
}

export function rewardsOpsRouter(client: DomainClient): Router {
  const r = Router();
  r.use('/ops', requirePrincipal, requireOperator);

  r.get(
    '/ops/rewards/disputes',
    forwardTo(client, (req) => ({ method: 'GET', path: '/ops/rewards/disputes', query: pickQuery(req, ['state', 'limit']) })),
  );
  r.post(
    '/ops/rewards/disputes/:disputeId/resolve',
    forwardTo(client, (req) => {
      const b = objectBody(req, 4);
      onlyKeys(b, ['outcome', 'signed_points', 'note', 'evidence_ref']);
      if (b.outcome !== 'correction' && b.outcome !== 'no_change') throw problems.invalid('outcome must be correction or no_change.');
      if (b.outcome === 'correction' && (!Number.isInteger(b.signed_points) || b.signed_points === 0 || Math.abs(b.signed_points as number) > 10_000)) {
        throw problems.invalid('signed_points must be a non-zero integer within ±10000.');
      }
      text(b.note, 'note', 1000);
      text(b.evidence_ref, 'evidence_ref', 120);
      return { method: 'POST', path: `/ops/rewards/disputes/${uuidParam(req, 'disputeId')}/resolve`, body: b };
    }),
  );
  r.get(
    '/ops/rewards/members/:memberRef/ledger',
    forwardTo(client, (req) => ({ method: 'GET', path: `/ops/rewards/members/${uuidParam(req, 'memberRef')}/ledger` })),
  );
  r.post(
    '/ops/rewards/members/:memberRef/entries/:entryId/reverse',
    forwardTo(client, (req) => {
      const b = objectBody(req, 2);
      onlyKeys(b, ['reason', 'evidence_ref']);
      text(b.reason, 'reason', 500);
      text(b.evidence_ref, 'evidence_ref', 120);
      return { method: 'POST', path: `/ops/rewards/members/${uuidParam(req, 'memberRef')}/entries/${uuidParam(req, 'entryId')}/reverse`, body: b };
    }),
  );
  r.post(
    '/ops/rewards/contributions',
    forwardTo(client, (req) => {
      const b = objectBody(req, 4);
      onlyKeys(b, ['member_ref', 'kind', 'contribution_ref', 'evidence_ref']);
      for (const k of ['member_ref', 'contribution_ref']) {
        if (typeof b[k] !== 'string' || !UUID_RE.test(b[k] as string)) throw problems.invalid(`${k} must be an id.`);
      }
      if (b.kind !== 'catalog_correction' && b.kind !== 'product_history') throw problems.invalid('Unknown contribution kind.');
      text(b.evidence_ref, 'evidence_ref', 120);
      return { method: 'POST', path: '/ops/rewards/contributions', body: b };
    }),
  );
  r.post(
    '/ops/benefits',
    forwardTo(client, (req) => {
      const b = objectBody(req, 11);
      onlyKeys(b, ['kind', 'title', 'description', 'cost_points', 'inventory_total', 'funded', 'sponsor', 'available_until', 'reservation_ttl_seconds',
        'house_ref', 'min_standing']);
      if (b.kind === 'partner' && (b.funded !== true || typeof b.sponsor !== 'string')) throw problems.invalid('Partner benefits must be funded and name a sponsor.');
      if ((b.house_ref === undefined) !== (b.min_standing === undefined) || (b.house_ref !== undefined && b.kind !== 'partner')) {
        throw problems.invalid('A house reward is a partner benefit with both house_ref and min_standing.');
      }
      return { method: 'POST', path: '/ops/benefits', body: b };
    }),
  );
  return r;
}
