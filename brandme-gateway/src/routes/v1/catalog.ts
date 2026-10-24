/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1/catalog — UNMOUNTED router (lane: opus-commerce-agents).
 * Results carry provider, freshness, simulation and affiliate disclosure; a catalog price is
 * an observation, never a purchasable quote. Provider text arrives wrapped as untrusted data.
 */

import { Router } from 'express';
import { z } from 'zod';
import { type CommerceDomainClient, forward, rejectIdentityFields, requireAgentScope, validate } from './commerce';

const Search = z
  .object({
    q: z.string().min(1).max(200),
    provider: z.string().max(80).optional(),
    cursor: z.string().max(512).optional(),
    limit: z.coerce.number().int().min(1).max(100).default(24),
  })
  .strict();

export function createCatalogRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.use(rejectIdentityFields);
  router.get('/search', requireAgentScope('commerce:research'), validate(Search, 'query'),
    forward(client, 'catalog.search', (_req, res) => res.locals.input));
  // productId is `{provider_id}:{source_product_id}`.
  router.get('/products/:id', requireAgentScope('commerce:research'),
    forward(client, 'catalog.product', (req) => ({ product_id: req.params.id })));
  return router;
}
