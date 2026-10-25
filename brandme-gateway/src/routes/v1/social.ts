/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1 relationships, blocks, mutes, shares and notifications — UNMOUNTED router
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
 *
 * `moderationOpsRouter` (console only) lists and resolves member reports;
 * it needs `moderation:admin`, no delegation, and aal2 outside development.
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
import { requireOperator } from './rewards';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const TOKEN_RE = /^[A-Za-z0-9_-]{16,128}$/;
const SHARE_SUBJECTS = ['outfit_version', 'wardrobe_item', 'closet_capsule', 'persona_snapshot', 'badge'];
const AUDIENCES = ['selected_members', 'unlisted', 'public'];
const REPORT_TARGETS: Record<string, string[]> = {
  decision_response: ['decision_id', 'respondent_id'],
  decision_comment: ['decision_id', 'comment_id'],
  room_post: ['room_id', 'post_id'],
  share: ['share_id'],
  outfit_proposal: ['outfit_id', 'proposal_id'],
  member: ['member_id'],
};
const REPORT_REASONS = ['harassment', 'spam', 'hate', 'sexual_content', 'self_harm', 'privacy', 'other'];

/** A report names content the caller saw; target ids are references, never the caller's identity. */
export function reportShape(b: Record<string, unknown>): void {
  const extra = Object.keys(b).filter((k) => !['target_type', 'target', 'reason', 'note'].includes(k));
  if (extra.length) throw problems.invalid(`Unknown fields: ${extra.join(', ')}.`);
  const fields = typeof b.target_type === 'string' ? REPORT_TARGETS[b.target_type] : undefined;
  if (!fields) throw problems.invalid('Unknown target_type.');
  const t = b.target as Record<string, unknown> | undefined;
  if (!t || typeof t !== 'object' || Array.isArray(t) || Object.keys(t).sort().join() !== [...fields].sort().join()) {
    throw problems.invalid(`target must contain exactly: ${fields.join(', ')}.`);
  }
  if (!fields.every((f) => typeof t[f] === 'string' && UUID_RE.test(t[f] as string))) throw problems.invalid('target ids must be ids.');
  if (typeof b.reason !== 'string' || !REPORT_REASONS.includes(b.reason)) throw problems.invalid('Unknown reason.');
  if (b.note !== undefined && (typeof b.note !== 'string' || b.note.length > 500)) throw problems.invalid('note must be at most 500 characters.');
}

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

  r.use(['/relationships', '/blocks', '/mutes', '/shares', '/notifications', '/reports'], requirePrincipal);

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
  // Mute is private to the caller: the muted member is never told (ch.01 §6.4).
  r.get('/mutes', requireScope('social:read'), forwardTo(client, () => ({ method: 'GET', path: '/mutes' })));
  r.post('/mutes', requireScope('social:write'), forwardTo(client, (req) => ({ method: 'POST', path: '/mutes', body: target(req) })));
  r.delete('/mutes/:memberId', requireScope('social:write'), forwardTo(client, (req) => ({ method: 'DELETE', path: `/mutes/${uuidParam(req, 'memberId')}` })));

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

  r.get('/reports', requireScope('social:read'), forwardTo(client, () => ({ method: 'GET', path: '/reports' })));
  r.post(
    '/reports',
    requireScope('social:write'),
    forwardTo(client, (req) => {
      const b = objectBody(req, 4);
      reportShape(b);
      return { method: 'POST', path: '/reports', body: b };
    }),
  );
  return r;
}

export function moderationOpsRouter(client: DomainClient): Router {
  const r = Router();
  r.use('/ops/moderation', requirePrincipal, requireOperator);
  r.get(
    '/ops/moderation/reports',
    forwardTo(client, (req) => ({ method: 'GET', path: '/ops/moderation/reports', query: pickQuery(req, ['state', 'limit']) })),
  );
  r.post(
    '/ops/moderation/reports/:reportId/resolve',
    forwardTo(client, (req) => {
      const b = objectBody(req, 2);
      if (!['dismiss', 'remove_content', 'escalate'].includes(String(b.decision))) throw problems.invalid('Unknown decision.');
      if (typeof b.note !== 'string' || b.note.trim().length < 1 || b.note.length > 1000) throw problems.invalid('note must be 1-1000 characters.');
      return { method: 'POST', path: `/ops/moderation/reports/${uuidParam(req, 'reportId')}/resolve`, body: { decision: b.decision, note: b.note } };
    }),
  );
  return r;
}
