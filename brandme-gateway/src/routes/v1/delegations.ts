/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1/delegations — UNMOUNTED router (lane: opus-commerce-agents).
 * Grants are created, listed and revoked only from the member's first-party session; one
 * active grant per (member, client). Defaults: research mode, no substitution, all-in totals,
 * final human approval required (autonomous purchase is refused by the domain until a
 * provider + AP2 open-mandate path is verified).
 *
 * The member's autonomy boundary (buy-within-rules grants only) says where the agent may place, on its
 * own, the exact quote the member approved: per-merchant or per-wishlist rules with a level
 * (prepare | buy_after_approval) and an optional all-in cap, applied line by line; everything else
 * defaults to prepare, so the member completes it. It is changed only here, from the member's
 * session, with If-Match on the grant version. The domain validates it against the grant and refuses
 * any level that would skip the member's approval.
 */

import { Router } from 'express';
import { z } from 'zod';
import {
  type CommerceDomainClient, forward, rejectIdentityFields, requireIdempotencyKey, requireIfMatch,
  requireTrustedSurface, validate,
} from './commerce';

const money = z.object({ amount_minor: z.string().regex(/^(0|[1-9][0-9]{0,17})$/), currency: z.string().regex(/^[A-Z]{3}$/) }).strict();

const level = z.enum(['prepare', 'buy_after_approval']);
const providerId = z.string().regex(/^[a-z0-9_]{1,80}$/);
const exactRef = z.string().regex(/^[A-Za-z0-9._:/-]{1,256}$/);

export const AutonomyBoundary = z
  .object({
    default_level: level.default('prepare'),
    default_max_total: money.nullable().default(null),
    rules: z
      .array(
        z.discriminatedUnion('scope', [
          z.object({ scope: z.literal('merchant'), provider_id: providerId, merchant_id: exactRef, level,
            max_total: money.nullable().default(null) }).strict(),
          z.object({ scope: z.literal('wishlist'), provider_id: providerId,
            variant_refs: z.array(exactRef).min(1).max(200), level, max_total: money.nullable().default(null) }).strict(),
        ]),
      )
      .max(20)
      .default([]),
  })
  .strict();

export const BoundaryUpdate = z.object({ autonomy_boundary: AutonomyBoundary.nullable() }).strict();

export const DelegationCreate = z
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
    autonomy_boundary: AutonomyBoundary.optional(),
  })
  .strict();

export function createDelegationsRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.use(rejectIdentityFields, requireTrustedSurface);
  router.get('/', forward(client, 'delegation.list', () => ({})));
  router.post('/', requireIdempotencyKey, validate(DelegationCreate),
    forward(client, 'delegation.create', (_req, res) => res.locals.input));
  router.delete('/:id', forward(client, 'delegation.revoke', (req) => ({ delegation_id: req.params.id })));
  router.put('/:id/autonomy-boundary', requireIfMatch, validate(BoundaryUpdate),
    forward(client, 'delegation.boundary.update', (req, res) => ({
      delegation_id: req.params.id, ...(res.locals.input as object) })));
  return router;
}
