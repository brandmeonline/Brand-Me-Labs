/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1/delegations — UNMOUNTED router (lane: opus-commerce-agents).
 * Grants are created and revoked only from the member's first-party session. Defaults: research
 * mode, no substitution, all-in totals, final human approval required (autonomous purchase is
 * refused by the domain until a provider + AP2 open-mandate path is verified).
 */

import { Router } from 'express';
import { z } from 'zod';
import { CommerceDomainClient, forward, rejectIdentityFields, requireTrustedSurface, validate } from './commerce';

const money = z.object({ amount_minor: z.string().regex(/^(0|[1-9][0-9]{0,17})$/), currency: z.string().regex(/^[A-Z]{3}$/) }).strict();

const DelegationCreate = z
  .object({
    client_id: z.string().min(1).max(256),
    mode: z.enum(['research', 'prepare', 'buy_within_rules']).default('research'),
    allowed_providers: z.array(z.string().max(80)).min(1).max(20),
    expires_at: z.string().datetime(),
    limits: z
      .object({
        currency: z.string().regex(/^[A-Z]{3}$/),
        max_per_order: money,
        max_cumulative: money,
        window_seconds: z.number().int().min(3600).max(90 * 86400),
        allowed_merchants: z.array(z.string().max(256)).min(1).max(20),
        allowed_categories: z.array(z.string().max(80)).max(50).default([]),
        delivery_ref: z.string().max(256).optional(),
        payment_instrument_ref: z.string().max(256).optional(),
        require_returnable: z.boolean().default(true),
        refund_credit_back: z.boolean().default(false),
        require_final_human_approval: z.literal(true).default(true),
        allow_substitution: z.literal(false).default(false),
      })
      .strict()
      .optional(),
  })
  .strict();

export function createDelegationsRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.use(rejectIdentityFields, requireTrustedSurface);
  router.get('/', forward(client, 'delegation.list', () => ({})));
  router.post('/', validate(DelegationCreate), forward(client, 'delegation.create', (r) => r.body));
  router.delete('/:id', forward(client, 'delegation.revoke', (r) => ({ delegation_id: r.params.id })));
  return router;
}
