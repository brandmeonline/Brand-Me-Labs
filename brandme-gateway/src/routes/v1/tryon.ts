/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1 photo try-on jobs and consents — UNMOUNTED router
 * (lane: opus-consumer-domains; W08 server side). Mount at integration after
 * principalMiddleware:
 *
 *   router.use(tryOnRouter(domainClient));
 *
 * A job request must carry explicit consent for the provider's current terms;
 * the domain re-checks consent immediately before any provider upload.
 * `calibrated_fit` is refused (no validated pipeline) and `live_overlay` is
 * on-device only, so neither is ever forwarded. Results are relayed through
 * this authorized route with private, no-store caching; no bucket URL leaves
 * the server.
 */

import { Router, type Request, type Response } from 'express';
import { ApiProblem, handle, problems } from '../../middleware/problem';
import { requirePrincipal } from '../../middleware/session';
import type { Principal } from '../../types';
import { forwardTo, idempotencyKey, objectBody, relay, requireScope, uuidParam, type DomainClient } from './persona';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** Cheap shape check; the domain enforces consent, ownership, quota and retention. */
export function tryOnJobShape(b: Record<string, unknown>): void {
  const extra = Object.keys(b).filter((k) => !['mode', 'input_media_id', 'item_id', 'product_id', 'consent'].includes(k));
  if (extra.length) throw problems.invalid(`Unknown fields: ${extra.join(', ')}.`);
  if (b.mode === 'calibrated_fit') {
    throw new ApiProblem(422, 'capability_unavailable', 'Calibrated fit is not available', 'No validated measurement pipeline exists.');
  }
  if (b.mode === 'live_overlay') throw new ApiProblem(422, 'on_device_only', 'Live overlay runs on your device', 'Camera frames are never uploaded.');
  if (b.mode !== 'photo_preview') throw problems.invalid('Unknown mode.');
  if (typeof b.input_media_id !== 'string' || !UUID_RE.test(b.input_media_id)) throw problems.invalid('input_media_id must be an id.');
  const ids = ['item_id', 'product_id'].filter((k) => b[k] !== undefined && b[k] !== null);
  if (ids.length !== 1 || !UUID_RE.test(String(b[ids[0]]))) throw problems.invalid('Choose exactly one of item_id or product_id.');
  const c = b.consent as Record<string, unknown> | undefined;
  if (!c || typeof c !== 'object' || c.accepted !== true || typeof c.provider_id !== 'string' || typeof c.terms_version !== 'string') {
    throw new ApiProblem(422, 'consent_required', 'Consent required', 'Review the provider terms and explicitly agree before sending a photo.');
  }
}

export function tryOnRouter(client: DomainClient): Router {
  const r = Router();
  r.use('/try-on', requirePrincipal);

  r.get('/try-on/capabilities', requireScope('wardrobe:read'), forwardTo(client, () => ({ method: 'GET', path: '/try-on/capabilities' })));
  r.post(
    '/try-on/jobs',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => {
      const body = objectBody(req, 5);
      tryOnJobShape(body);
      return { method: 'POST', path: '/try-on/jobs', body, idempotencyKey: idempotencyKey(req) };
    }),
  );
  r.get('/try-on/jobs/:jobId', requireScope('wardrobe:read'), forwardTo(client, (req) => ({ method: 'GET', path: `/try-on/jobs/${uuidParam(req, 'jobId')}` })));
  r.get(
    '/try-on/jobs/:jobId/result',
    requireScope('wardrobe:read'),
    handle(async (req: Request, res: Response) => {
      const out = await client.request({
        method: 'GET', path: `/try-on/jobs/${uuidParam(req, 'jobId')}/result`,
        principal: res.locals.principal as Principal, requestId: res.locals.requestId,
      });
      const ctype = out.headers?.['content-type'] ?? '';
      if (out.status !== 200 || !Buffer.isBuffer(out.body) || !/^image\/(png|jpeg|webp)$/.test(ctype)) return relay(res, out);
      res.setHeader('Cache-Control', 'private, no-store');
      res.status(200).type(ctype).send(out.body);
    }),
  );
  r.post(
    '/try-on/jobs/:jobId/save',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => ({ method: 'POST', path: `/try-on/jobs/${uuidParam(req, 'jobId')}/save` })),
  );
  r.delete(
    '/try-on/jobs/:jobId',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => ({ method: 'DELETE', path: `/try-on/jobs/${uuidParam(req, 'jobId')}` })),
  );
  r.get('/try-on/consents', requireScope('wardrobe:read'), forwardTo(client, () => ({ method: 'GET', path: '/try-on/consents' })));
  r.delete(
    '/try-on/consents/:consentId',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => ({ method: 'DELETE', path: `/try-on/consents/${uuidParam(req, 'consentId')}` })),
  );
  return r;
}
