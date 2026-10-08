/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1/catalog — UNMOUNTED router (lane: opus-commerce-agents).
 * Results carry provider, freshness, simulation and affiliate disclosure; a catalog price is
 * an observation, never a purchasable quote.
 */

import { Router } from 'express';
import { z } from 'zod';
import { CommerceDomainClient, PrincipalRequest, forward, problem, rejectIdentityFields, requireScope } from './commerce';

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
  router.get('/search', requireScope('commerce:research'), (req: PrincipalRequest, res, next) => {
    const parsed = Search.safeParse(req.query);
    if (!parsed.success) {
      problem(res, 400, 'invalid_request', parsed.error.issues[0]?.message ?? 'invalid query', req.requestId);
      return;
    }
    (req as PrincipalRequest & { search?: unknown }).search = parsed.data;
    next();
  }, forward(client, 'catalog.search', (r) => (r as PrincipalRequest & { search?: unknown }).search));
  router.get('/products/:id', requireScope('commerce:research'),
    forward(client, 'catalog.product', (r) => ({ product_id: r.params.id })));
  return router;
}
