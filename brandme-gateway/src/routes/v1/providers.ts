/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1/providers (operator console) and /api/v1/capabilities (sanitized) —
 * UNMOUNTED routers (lane: opus-commerce-agents).
 *
 * Console routes require the `provider:admin` role for every caller; a member session never
 * implies it. Secret fields are write-only: requests may carry a Secret Manager resource name,
 * never a secret value (values that look like keys, PEM blocks or long random text are refused
 * here and again by the domain), and responses only show whether a credential is configured,
 * a fingerprint and the rotation time. "Connect" is never a local boolean: saving setup never
 * changes a capability; a capability is enabled only by `{ "activate": <capability> }`, which the
 * domain refuses (409) without every prerequisite and a fresh passing connection test.
 *
 * - `PATCH /:id/setup` — partial save (`SetupUpdate`), or `{ activate }` on its own. An optional
 *   `If-Match: "<version>"` guards against lost updates.
 * - `POST /:id/verification-runs` — run one connection test for one exact capability.
 * - `GET /:id/verification-runs` — recent runs (time, environment, capability, sanitized evidence).
 * - `PUT /:id/tier` — the connection's partner tier (`tier_id: null` clears it); `If-Match` required. Placeholder
 *   tiers carry no price; assigning a tier never enables a capability (3D/AR still needs activation and a
 *   passing test), and a downgrade resets the capabilities the new tier excludes.
 */

import { Router } from 'express';
import { z } from 'zod';
import { type CommerceDomainClient, forward, rejectIdentityFields, requireIfMatch, requireRole, validate } from './commerce';

/** Chapter 05 capability names (the domain's closed `CAPABILITIES` tuple; tests/test_providers.py checks drift). */
export const CAPABILITY_NAMES = [
  'catalog.search', 'catalog.detail', 'catalog.feed', 'catalog.images', 'catalog.3d',
  'inventory.read', 'price.quote', 'cart.create', 'cart.update', 'checkout.handoff',
  'checkout.submit', 'orders.read', 'orders.webhook', 'returns.request', 'refunds.read',
  'affiliate.attribution', 'receipts.import', 'tryon.photo', 'tryon.live',
  'rights.issue', 'rights.transfer', 'rights.reprint', 'manufacture.quote', 'manufacture.submit',
] as const;
const capability = z.enum(CAPABILITY_NAMES);

// Mirrors `looks_like_secret` in brandme_core/domains/providers/setup.py; the domain re-checks every value.
const SECRET_TOKEN =
  /^(sk_|rk_|pk_|whsec_|sk-|ghp_|gho_|ghs_|github_pat_|glpat-|xox[abps]-|ya29\.|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|eyJ[A-Za-z0-9_-]{8,})/;

function entropy(token: string): number {
  const counts = new Map<string, number>();
  const chars = [...token];
  for (const c of chars) counts.set(c, (counts.get(c) ?? 0) + 1);
  let h = 0;
  for (const n of counts.values()) h -= (n / chars.length) * Math.log2(n / chars.length);
  return h;
}

export function looksLikeSecret(value: string): boolean {
  if (value.toUpperCase().includes('PRIVATE KEY') || value.includes('-----BEGIN')) return true;
  for (const token of value.split(/[\s/:@,;=?&]+/)) {
    if (!token) continue;
    if (SECRET_TOKEN.test(token) || (token.length >= 32 && /^[0-9a-fA-F]+$/.test(token))) return true;
    if (token.length >= 24) {
      const mixed = /[A-Z]/.test(token) && /[a-z]/.test(token) && /[0-9]/.test(token);
      const h = entropy(token);
      if ((mixed && h >= 4.3) || (token.length >= 32 && h >= 4.5)) return true;
    }
  }
  return false;
}

const NOT_A_SECRET = 'looks like a secret value; enter a reference and keep secrets in Secret Manager';

const reference = z
  .string()
  .trim()
  .min(1)
  .max(256)
  .refine((v) => !looksLikeSecret(v), NOT_A_SECRET)
  .refine((v) => /^[A-Za-z0-9][A-Za-z0-9 ._:/@#+-]*$/.test(v), 'must be a plain reference');

const secretResourceName = z
  .string()
  .max(512)
  .regex(/^projects\/[a-z0-9][a-z0-9.:-]{0,99}\/secrets\/[A-Za-z0-9_-]{1,255}\/versions\/([0-9]{1,10}|latest)$/,
    'must be a Secret Manager resource name')
  .refine((v) => !looksLikeSecret(v), NOT_A_SECRET);

export const SetupUpdate = z
  .object({
    access_level: z.enum(['unconfigured', 'link_only', 'approved_publisher', 'contracted_commerce']).optional(),
    program_application_opened: z.boolean().optional(),
    approval_evidence_ref: reference.optional(),
    account_ref: reference.optional(),
    credential_secret_ref: secretResourceName.optional(),
    catalog_ref: reference.optional(),
    endpoint_descriptor_ref: reference.optional(),
    data_use: z
      .object({
        display_images: z.boolean(),
        cache_images: z.boolean(),
        transform_images: z.boolean(),
        retain_prices: z.boolean(),
        affiliate_tracking: z.boolean(),
        derive_3d_or_ai: z.boolean(),
      })
      .strict()
      .optional(),
    /** Enable one capability. Sent alone, so a refused activation never discards a partial save. */
    activate: capability.optional(),
  })
  .strict()
  .refine((o) => Object.keys(o).length > 0, 'send at least one setup field')
  .refine((o) => o.activate === undefined || Object.keys(o).length === 1, 'send activate on its own');

export const TierAssignment = z
  .object({ tier_id: z.string().regex(/^[a-z][a-z0-9_]{1,39}$/).nullable() })
  .strict();

export const VerificationRun = z
  .object({ capability, mode: z.enum(['read_only_test', 'staging_ingestion']) })
  .strict();

export const VerificationRunsQuery = z
  .object({ capability: capability.optional(), limit: z.coerce.number().int().min(1).max(100).optional() })
  .strict();

export function createProvidersRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.use(rejectIdentityFields, requireRole('provider:admin'));
  router.get('/', forward(client, 'provider.list', () => ({})));
  router.get('/:id', forward(client, 'provider.get', (req) => ({ provider_id: req.params.id })));
  router.get('/:id/setup', forward(client, 'provider.setup.get', (req) => ({ provider_id: req.params.id })));
  router.patch('/:id/setup', validate(SetupUpdate),
    forward(client, 'provider.setup.update', (req, res) => ({ provider_id: req.params.id, ...(res.locals.input as object) })));
  router.get('/:id/health', forward(client, 'provider.health', (req) => ({ provider_id: req.params.id })));
  router.put('/:id/tier', requireIfMatch, validate(TierAssignment),
    forward(client, 'provider.tier.assign', (req, res) => ({ provider_id: req.params.id, ...(res.locals.input as object) })));
  router.post('/:id/verification-runs', validate(VerificationRun),
    forward(client, 'provider.verify', (req, res) => ({ provider_id: req.params.id, ...(res.locals.input as object) })));
  router.get('/:id/verification-runs', validate(VerificationRunsQuery, 'query'),
    forward(client, 'provider.runs', (req, res) => ({ provider_id: req.params.id, ...(res.locals.input as object) })));
  return router;
}

/** GET /capabilities — sanitized capability summary for any signed-in principal. */
export function createCapabilitiesRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.get('/', forward(client, 'capabilities.effective', () => ({})));
  return router;
}
