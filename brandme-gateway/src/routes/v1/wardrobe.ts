/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1 wardrobe items, closet layout/placements, per-piece visibility and
 * another member's visible closet (lane: opus-consumer-domains), mounted from
 * index.ts behind principalMiddleware.
 *
 * Shape/scope/If-Match/Idempotency-Key checks here; every invariant (finite
 * normalized quaternions, asset-bounded positions, slot uniqueness, ownership)
 * is enforced again by the Python wardrobe domain.
 */

import { Router, type Request } from 'express';
import { problems } from '../../middleware/problem';
import { requirePrincipal } from '../../middleware/session';
import {
  forwardTo,
  idempotencyKey,
  ifMatch,
  objectBody,
  pickQuery,
  requireScope,
  uuidParam,
  type DomainClient,
} from './persona';
import type { Principal } from '../../types';

const PLACEMENT_KEYS = new Set([
  'room_template_id',
  'semantic_group',
  'slot_id',
  'position_meters',
  'rotation_quaternion',
  'uniform_scale',
  'asset_revision',
  'wardrobe_item_id',
  'version',
]);

function finiteVector(v: unknown, n: number, name: string): void {
  if (v === undefined || v === null) return;
  if (!Array.isArray(v) || v.length !== n || !v.every((x) => typeof x === 'number' && Number.isFinite(x))) {
    throw problems.invalid(`${name} must be ${n} finite numbers.`);
  }
}

/** Cheap early rejection; the domain repeats every check with room/asset bounds. */
export function placementShape(b: Record<string, unknown>): void {
  const unknown = Object.keys(b).filter((k) => !PLACEMENT_KEYS.has(k));
  if (unknown.length) throw problems.invalid(`Unsupported placement fields: ${unknown.join(', ')}.`);
  finiteVector(b.position_meters, 3, 'position_meters');
  finiteVector(b.rotation_quaternion, 4, 'rotation_quaternion');
  if (b.uniform_scale !== undefined && b.uniform_scale !== null && !(typeof b.uniform_scale === 'number' && Number.isFinite(b.uniform_scale) && b.uniform_scale > 0)) {
    throw problems.invalid('uniform_scale must be a finite positive number.');
  }
}

export function wardrobeRouter(client: DomainClient): Router {
  const r = Router();
  r.use(['/wardrobe', '/closet', '/members'], requirePrincipal);

  r.get(
    '/wardrobe/items',
    requireScope('wardrobe:read'),
    forwardTo(client, (req) => ({ method: 'GET', path: '/wardrobe/items', query: pickQuery(req, ['collection', 'category', 'q', 'cursor', 'limit']) })),
  );
  r.post(
    '/wardrobe/items',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => {
      const body = objectBody(req, 20);
      if (body.placement && typeof body.placement === 'object') placementShape(body.placement as Record<string, unknown>);
      return { method: 'POST', path: '/wardrobe/items', body, idempotencyKey: idempotencyKey(req) };
    }),
  );
  r.get(
    '/wardrobe/items/:itemId',
    requireScope('wardrobe:read'),
    forwardTo(client, (req) => ({ method: 'GET', path: `/wardrobe/items/${uuidParam(req, 'itemId')}` })),
  );
  r.patch(
    '/wardrobe/items/:itemId',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => ({ method: 'PATCH', path: `/wardrobe/items/${uuidParam(req, 'itemId')}`, ifMatch: ifMatch(req), body: objectBody(req, 12) })),
  );
  for (const action of ['archive', 'unarchive'] as const) {
    r.post(
      `/wardrobe/items/:itemId/${action}`,
      requireScope('wardrobe:write'),
      forwardTo(client, (req) => ({ method: 'POST', path: `/wardrobe/items/${uuidParam(req, 'itemId')}/${action}`, ifMatch: ifMatch(req) })),
    );
  }
  r.post(
    '/wardrobe/items/:itemId/duplicates/:otherId',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => ({
      method: 'POST',
      path: `/wardrobe/items/${uuidParam(req, 'itemId')}/duplicates/${uuidParam(req, 'otherId')}`,
      body: objectBody(req, 1),
    })),
  );
  r.post(
    '/wardrobe/items/:itemId/worn',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => ({ method: 'POST', path: `/wardrobe/items/${uuidParam(req, 'itemId')}/worn`, idempotencyKey: idempotencyKey(req) })),
  );

  r.get('/closet/layout', requireScope('wardrobe:read'), forwardTo(client, () => ({ method: 'GET', path: '/closet/layout' })));
  r.put(
    '/closet/layout/theme',
    requireScope('wardrobe:write'),
    forwardTo(client, (req: Request) => {
      const preview = req.query.preview === 'true';
      const query: Record<string, string> = preview ? { preview: 'true' } : {};
      return {
        method: 'PUT',
        path: '/closet/layout/theme',
        body: objectBody(req, 1),
        query,
        ...(preview ? {} : { ifMatch: ifMatch(req) }),
      };
    }),
  );
  r.put(
    '/closet/placements/:itemId',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => {
      const body = objectBody(req, 9);
      placementShape(body);
      return { method: 'PUT', path: `/closet/placements/${uuidParam(req, 'itemId')}`, ifMatch: ifMatch(req), body };
    }),
  );
  r.post(
    '/closet/placements/batch',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => {
      const body = objectBody(req, 1);
      const list = body.placements;
      if (!Array.isArray(list) || list.length < 1 || list.length > 50) throw problems.invalid('placements must list 1-50 moves.');
      for (const p of list) {
        if (!p || typeof p !== 'object' || Array.isArray(p)) throw problems.invalid('Each placement must be an object.');
        placementShape(p as Record<string, unknown>);
      }
      return { method: 'POST', path: '/closet/placements/batch', body, idempotencyKey: idempotencyKey(req) };
    }),
  );
  // Who sees a piece, and how much: the member's own choice (Ultra plan 02, item 6).
  r.put(
    '/wardrobe/items/:itemId/visibility',
    requireScope('wardrobe:write'),
    forwardTo(client, (req, res) => {
      if ((res.locals.principal as Principal).delegationId) throw problems.forbidden('Only the member decides who sees their closet.');
      const b = objectBody(req, 3);
      const extra = Object.keys(b).filter((k) => !['visibility', 'detail', 'showcase_note'].includes(k));
      if (extra.length) throw problems.invalid(`Unknown fields: ${extra.join(', ')}.`);
      if (!['private', 'friends', 'members'].includes(b.visibility as string)) throw problems.invalid('visibility must be private, friends or members.');
      if (b.detail !== undefined && !['piece', 'story', 'full'].includes(b.detail as string)) throw problems.invalid('detail must be piece, story or full.');
      if (b.showcase_note !== undefined && (typeof b.showcase_note !== 'string' || b.showcase_note.trim().length < 1 || b.showcase_note.length > 280)) {
        throw problems.invalid('showcase_note must be 1-280 characters.');
      }
      return { method: 'PUT', path: `/wardrobe/items/${uuidParam(req, 'itemId')}/visibility`, body: b };
    }),
  );
  r.get('/members/:memberId/closet', requireScope('wardrobe:read'),
    forwardTo(client, (req) => ({ method: 'GET', path: `/members/${uuidParam(req, 'memberId')}/closet` })));
  return r;
}
