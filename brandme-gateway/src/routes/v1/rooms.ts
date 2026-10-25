/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1 small-group rooms (lane: opus-consumer-domains; Ultra plan 02,
 * item 7), mounted from index.ts behind principalMiddleware. Rooms are the
 * member's own: an agent cannot open, post, react or manage them. The domain
 * checks friendship, size, blocking and archive state again.
 */

import { Router } from 'express';
import { problems } from '../../middleware/problem';
import { requirePrincipal } from '../../middleware/session';
import type { Principal } from '../../types';
import { forwardTo, idempotencyKey, objectBody, requireScope, uuidParam, type DomainClient } from './persona';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function onlyKeys(b: Record<string, unknown>, allowed: string[]): void {
  const extra = Object.keys(b).filter((k) => !allowed.includes(k));
  if (extra.length) throw problems.invalid(`Unknown fields: ${extra.join(', ')}.`);
}

function text(v: unknown, name: string, max: number): void {
  if (typeof v !== 'string' || v.trim().length < 1 || v.length > max) throw problems.invalid(`${name} must be 1-${max} characters.`);
}

function memberOnly(p: Principal): void {
  if (p.delegationId) throw problems.forbidden('Rooms are the member’s own.');
}

export function roomsRouter(client: DomainClient): Router {
  const r = Router();
  r.use('/rooms', requirePrincipal);

  r.get('/rooms', requireScope('social:read'), forwardTo(client, () => ({ method: 'GET', path: '/rooms' })));
  r.post(
    '/rooms',
    requireScope('social:write'),
    forwardTo(client, (req, res) => {
      memberOnly(res.locals.principal as Principal);
      const b = objectBody(req, 3);
      onlyKeys(b, ['title', 'purpose', 'member_ids']);
      text(b.title, 'title', 80);
      if (b.purpose !== undefined) text(b.purpose, 'purpose', 200);
      const ids = b.member_ids ?? [];
      if (!Array.isArray(ids) || ids.length > 11 || !ids.every((i) => typeof i === 'string' && UUID_RE.test(i))) {
        throw problems.invalid('Add at most 11 people by id.');
      }
      return { method: 'POST', path: '/rooms', body: b, idempotencyKey: idempotencyKey(req) };
    }),
  );
  r.get('/rooms/:roomId', requireScope('social:read'), forwardTo(client, (req) => ({ method: 'GET', path: `/rooms/${uuidParam(req, 'roomId')}` })));
  r.post('/rooms/:roomId/archive', requireScope('social:write'), forwardTo(client, (req, res) => {
    memberOnly(res.locals.principal as Principal);
    return { method: 'POST', path: `/rooms/${uuidParam(req, 'roomId')}/archive` };
  }));
  r.post('/rooms/:roomId/members', requireScope('social:write'), forwardTo(client, (req, res) => {
    memberOnly(res.locals.principal as Principal);
    const b = objectBody(req, 1);
    onlyKeys(b, ['member_id']);
    if (typeof b.member_id !== 'string' || !UUID_RE.test(b.member_id)) throw problems.invalid('member_id must be an id.');
    return { method: 'POST', path: `/rooms/${uuidParam(req, 'roomId')}/members`, body: { member_id: b.member_id } };
  }));
  r.delete('/rooms/:roomId/members/:memberId', requireScope('social:write'), forwardTo(client, (req, res) => {
    memberOnly(res.locals.principal as Principal);
    return { method: 'DELETE', path: `/rooms/${uuidParam(req, 'roomId')}/members/${uuidParam(req, 'memberId')}` };
  }));
  r.post('/rooms/:roomId/posts', requireScope('social:write'), forwardTo(client, (req, res) => {
    memberOnly(res.locals.principal as Principal);
    const b = objectBody(req, 4);
    onlyKeys(b, ['kind', 'body', 'subject_type', 'subject_id']);
    if (b.kind !== 'note' && b.kind !== 'piece') throw problems.invalid('kind must be note or piece.');
    if (b.body !== undefined) text(b.body, 'body', 1000);
    if (b.kind === 'piece' && (!['wardrobe_item', 'catalog_product'].includes(b.subject_type as string)
      || typeof b.subject_id !== 'string' || !UUID_RE.test(b.subject_id))) {
      throw problems.invalid('A piece names a wardrobe_item or catalog_product by id.');
    }
    return { method: 'POST', path: `/rooms/${uuidParam(req, 'roomId')}/posts`, body: b, idempotencyKey: idempotencyKey(req) };
  }));
  r.put('/rooms/:roomId/posts/:postId/reaction', requireScope('social:write'), forwardTo(client, (req, res) => {
    memberOnly(res.locals.principal as Principal);
    const b = objectBody(req, 1);
    onlyKeys(b, ['reaction']);
    if (!['yes', 'maybe', 'no'].includes(b.reaction as string)) throw problems.invalid('reaction must be yes, maybe or no.');
    return { method: 'PUT', path: `/rooms/${uuidParam(req, 'roomId')}/posts/${uuidParam(req, 'postId')}/reaction`, body: { reaction: b.reaction } };
  }));
  r.delete('/rooms/:roomId/posts/:postId', requireScope('social:write'), forwardTo(client, (req, res) => {
    memberOnly(res.locals.principal as Principal);
    return { method: 'DELETE', path: `/rooms/${uuidParam(req, 'roomId')}/posts/${uuidParam(req, 'postId')}` };
  }));
  return r;
}
