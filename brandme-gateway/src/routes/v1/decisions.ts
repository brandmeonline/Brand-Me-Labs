/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1 five-minute decisions — UNMOUNTED router (lane: opus-consumer-domains).
 * Mount at integration after principalMiddleware:
 *
 *   router.use(decisionsRouter(domainClient));
 *
 * The deadline is server-owned: `duration_seconds` must be exactly 300 and no
 * client time is forwarded. Whether a response is on time is decided in the
 * domain transaction against Spanner time (BM-SOC-005). An agent principal
 * without `social:send` gets a draft that only the member can send.
 */

import { Router, type Request } from 'express';
import { problems } from '../../middleware/problem';
import { requirePrincipal } from '../../middleware/session';
import { forwardTo, idempotencyKey, objectBody, pickQuery, requireScope, uuidParam, type DomainClient } from './persona';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SUBJECTS = ['wardrobe_item', 'catalog_product', 'outfit_version'];
const CHOICES = ['yes', 'pass', 'alternative'];
const OUTCOMES = ['bought', 'saved', 'passed', 'still_deciding'];

function onlyKeys(b: Record<string, unknown>, allowed: string[]): void {
  const extra = Object.keys(b).filter((k) => !allowed.includes(k));
  if (extra.length) throw problems.invalid(`Unknown fields: ${extra.join(', ')}.`);
}

/** Cheap shape check of contracts #DecisionCreate; the domain re-checks everything. */
export function decisionShape(b: Record<string, unknown>): void {
  onlyKeys(b, ['subject_type', 'subject_id', 'prompt', 'recipient_ids', 'duration_seconds', 'discussion_mode']);
  if (typeof b.subject_type !== 'string' || !SUBJECTS.includes(b.subject_type)) throw problems.invalid('Unknown subject_type.');
  if (typeof b.subject_id !== 'string' || !UUID_RE.test(b.subject_id)) throw problems.invalid('subject_id must be an id.');
  if (typeof b.prompt !== 'string' || b.prompt.trim().length < 1 || b.prompt.length > 280) throw problems.invalid('prompt must be 1-280 characters.');
  if (b.duration_seconds !== 300) throw problems.invalid('Decisions last exactly 300 seconds.');
  if (b.discussion_mode !== 'blind_until_response' && b.discussion_mode !== 'open') throw problems.invalid('Unknown discussion_mode.');
  const recips = b.recipient_ids;
  if (!Array.isArray(recips) || recips.length < 1 || recips.length > 12 || !recips.every((r) => typeof r === 'string' && UUID_RE.test(r))) {
    throw problems.invalid('Choose 1-12 recipients.');
  }
  if (new Set(recips.map((r: string) => r.toLowerCase())).size !== recips.length) throw problems.invalid('Each recipient can be invited once.');
}

function responseShape(req: Request): Record<string, unknown> {
  const b = objectBody(req, 3);
  onlyKeys(b, ['choice', 'alternative_ref', 'note']);
  if (typeof b.choice !== 'string' || !CHOICES.includes(b.choice)) throw problems.invalid('choice must be yes, pass or alternative.');
  if (b.choice === 'alternative' && (typeof b.alternative_ref !== 'string' || !UUID_RE.test(b.alternative_ref))) {
    throw problems.invalid('Try this instead needs an item reference.');
  }
  if (b.note !== undefined && (typeof b.note !== 'string' || b.note.length > 500)) throw problems.invalid('note must be at most 500 characters.');
  return b;
}

export function decisionsRouter(client: DomainClient): Router {
  const r = Router();
  r.use('/decisions', requirePrincipal);

  r.get(
    '/decisions',
    requireScope('social:read'),
    forwardTo(client, (req) => {
      const q = pickQuery(req, ['role']);
      if (q.role && q.role !== 'invited' && q.role !== 'mine') throw problems.invalid('role must be invited or mine.');
      return { method: 'GET', path: '/decisions', query: q };
    }),
  );
  r.post(
    '/decisions',
    requireScope('social:write'),
    forwardTo(client, (req) => {
      const body = objectBody(req, 6);
      decisionShape(body);
      return { method: 'POST', path: '/decisions', body, idempotencyKey: idempotencyKey(req) };
    }),
  );
  r.get('/decisions/:decisionId', requireScope('social:read'), forwardTo(client, (req) => ({ method: 'GET', path: `/decisions/${uuidParam(req, 'decisionId')}` })));
  r.post(
    '/decisions/:decisionId/responses',
    requireScope('social:write'),
    forwardTo(client, (req) => ({ method: 'POST', path: `/decisions/${uuidParam(req, 'decisionId')}/responses`, body: responseShape(req) })),
  );
  for (const action of ['open', 'close', 'cancel'] as const) {
    r.post(
      `/decisions/:decisionId/${action}`,
      requireScope('social:write'),
      forwardTo(client, (req) => ({ method: 'POST', path: `/decisions/${uuidParam(req, 'decisionId')}/${action}` })),
    );
  }
  r.put(
    '/decisions/:decisionId/outcome',
    requireScope('social:write'),
    forwardTo(client, (req) => {
      const b = objectBody(req, 1);
      if (typeof b.outcome !== 'string' || !OUTCOMES.includes(b.outcome)) throw problems.invalid('Unknown outcome.');
      return { method: 'PUT', path: `/decisions/${uuidParam(req, 'decisionId')}/outcome`, body: { outcome: b.outcome } };
    }),
  );
  return r;
}
