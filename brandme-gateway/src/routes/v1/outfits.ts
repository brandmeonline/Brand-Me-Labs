/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1 outfits, friend proposals and packing lists — UNMOUNTED router
 * (lane: opus-consumer-domains). Mount at integration after principalMiddleware:
 *
 *   router.use(outfitsRouter(domainClient));
 *
 * A friend's proposal is addressed by outfit id only; the domain resolves the
 * owner and applies the social policy (same 404 for "missing" and "not yours").
 */

import { Router } from 'express';
import { problems } from '../../middleware/problem';
import { requirePrincipal } from '../../middleware/session';
import { forwardTo, idempotencyKey, ifMatch, objectBody, pickQuery, requireScope, uuidParam, type DomainClient } from './persona';

export function outfitsRouter(client: DomainClient): Router {
  const r = Router();
  r.use(['/outfits', '/packing-lists'], requirePrincipal);

  r.get('/outfits', requireScope('outfits:read'), forwardTo(client, (req) => ({ method: 'GET', path: '/outfits', query: pickQuery(req, ['cursor', 'limit']) })));
  r.post(
    '/outfits',
    requireScope('outfits:write'),
    forwardTo(client, (req) => ({ method: 'POST', path: '/outfits', body: objectBody(req, 7), idempotencyKey: idempotencyKey(req) })),
  );
  r.get(
    '/outfits/:outfitId',
    requireScope('outfits:read'),
    forwardTo(client, (req) => ({ method: 'GET', path: `/outfits/${uuidParam(req, 'outfitId')}` })),
  );
  r.post(
    '/outfits/:outfitId/versions',
    requireScope('outfits:write'),
    forwardTo(client, (req) => ({ method: 'POST', path: `/outfits/${uuidParam(req, 'outfitId')}/versions`, ifMatch: ifMatch(req), body: objectBody(req, 5) })),
  );
  r.get(
    '/outfits/:outfitId/proposals',
    requireScope('outfits:read'),
    forwardTo(client, (req) => ({ method: 'GET', path: `/outfits/${uuidParam(req, 'outfitId')}/proposals` })),
  );
  r.post(
    '/outfits/:outfitId/proposals',
    requireScope('outfits:write'),
    forwardTo(client, (req) => ({
      method: 'POST',
      path: `/outfits/${uuidParam(req, 'outfitId')}/proposals`,
      body: objectBody(req, 4),
      idempotencyKey: idempotencyKey(req),
    })),
  );
  r.post(
    '/outfits/:outfitId/proposals/:proposalId/:decision',
    requireScope('outfits:write'),
    forwardTo(client, (req) => {
      const decision = req.params.decision;
      if (decision !== 'accept' && decision !== 'decline') throw problems.notFound();
      return {
        method: 'POST',
        path: `/outfits/${uuidParam(req, 'outfitId')}/proposals/${uuidParam(req, 'proposalId')}/${decision}`,
        ...(decision === 'accept' ? { ifMatch: ifMatch(req) } : {}),
      };
    }),
  );

  r.post(
    '/packing-lists',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => ({ method: 'POST', path: '/packing-lists', body: objectBody(req, 4), idempotencyKey: idempotencyKey(req) })),
  );
  r.get(
    '/packing-lists/:listId',
    requireScope('wardrobe:read'),
    forwardTo(client, (req) => ({ method: 'GET', path: `/packing-lists/${uuidParam(req, 'listId')}` })),
  );
  r.patch(
    '/packing-lists/:listId/entries/:entryId',
    requireScope('wardrobe:write'),
    forwardTo(client, (req) => ({
      method: 'PATCH',
      path: `/packing-lists/${uuidParam(req, 'listId')}/entries/${uuidParam(req, 'entryId')}`,
      ifMatch: ifMatch(req),
      body: objectBody(req, 1),
    })),
  );
  return r;
}
