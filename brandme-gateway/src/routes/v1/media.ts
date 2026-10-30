/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1 media uploads — UNMOUNTED router (lane: opus-consumer-domains).
 * Mount at integration after principalMiddleware:
 *
 *   router.use(mediaRouter(domainClient));
 *
 * The response carries a short-lived, constrained upload target minted by the
 * domain's object store adapter; the gateway never proxies or inspects image
 * bytes, and never returns a bucket path or public URL.
 */

import { Router } from 'express';
import { problems } from '../../middleware/problem';
import { requirePrincipal } from '../../middleware/session';
import { forwardTo, idempotencyKey, objectBody, requireScope, uuidParam, type DomainClient } from './persona';

const TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_BYTES = 10 * 1024 * 1024;

export function mediaRouter(client: DomainClient): Router {
  const r = Router();
  r.use('/media', requirePrincipal);

  r.post(
    '/media/uploads',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => {
      const b = objectBody(req, 3);
      const extra = Object.keys(b).filter((k) => !['kind', 'content_type', 'bytes'].includes(k));
      if (extra.length) throw problems.invalid(`Unknown fields: ${extra.join(', ')}.`);
      if (b.kind !== 'tryon_input') throw problems.invalid('kind must be tryon_input.');
      if (typeof b.content_type !== 'string' || !TYPES.includes(b.content_type)) throw problems.invalid('Unsupported content_type.');
      if (!Number.isInteger(b.bytes) || (b.bytes as number) < 1 || (b.bytes as number) > MAX_BYTES) throw problems.invalid('bytes must be 1-10485760.');
      return { method: 'POST', path: '/media/uploads', body: b, idempotencyKey: idempotencyKey(req) };
    }),
  );
  r.post(
    '/media/uploads/:mediaId/complete',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => ({ method: 'POST', path: `/media/uploads/${uuidParam(req, 'mediaId')}/complete` })),
  );
  r.get('/media/jobs/:mediaId', requireScope('wardrobe:read'), forwardTo(client, (req) => ({ method: 'GET', path: `/media/jobs/${uuidParam(req, 'mediaId')}` })));
  return r;
}
