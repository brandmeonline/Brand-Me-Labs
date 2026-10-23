/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1/providers (operator console) and /api/v1/capabilities (sanitized) —
 * UNMOUNTED routers (lane: opus-commerce-agents).
 *
 * Console routes require `provider:admin`. Secret fields are write-only: requests may carry a
 * Secret Manager resource name, never a secret value, and responses only ever show a masked
 * reference and rotation time. "Connect" is never a local boolean: activation goes through the
 * domain's setup checklist and verification evidence.
 */

import { Router } from 'express';
import { z } from 'zod';
import { CommerceDomainClient, forward, rejectIdentityFields, requireScope, validate } from './commerce';

const SetupUpdate = z
  .object({
    access_level: z.enum(['unconfigured', 'link_only', 'approved_publisher', 'contracted_commerce']).optional(),
    program_application_opened: z.boolean().optional(),
    approval_evidence_ref: z.string().max(256).optional(),
    account_ref: z.string().max(256).optional(),
    credential_secret_ref: z
      .string()
      .regex(/^projects\/[^/]+\/secrets\/[^/]+\/versions\/[^/]+$/, 'must be a Secret Manager resource name')
      .optional(),
    catalog_ref: z.string().max(256).optional(),
    endpoint_descriptor_ref: z.string().max(256).optional(),
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
  })
  .strict();

const VerificationRun = z
  .object({ capability: z.string().min(1).max(40), mode: z.enum(['read_only_test', 'staging_ingestion']) })
  .strict();

export function createProvidersRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.use(rejectIdentityFields, requireScope('provider:admin'));
  router.get('/', forward(client, 'provider.list', () => ({})));
  router.get('/:id', forward(client, 'provider.get', (r) => ({ provider_id: r.params.id })));
  router.get('/:id/setup', forward(client, 'provider.setup.get', (r) => ({ provider_id: r.params.id })));
  router.patch('/:id/setup', validate(SetupUpdate),
    forward(client, 'provider.setup.update', (r) => ({ provider_id: r.params.id, ...r.body })));
  router.get('/:id/health', forward(client, 'provider.health', (r) => ({ provider_id: r.params.id })));
  router.post('/:id/verification-runs', validate(VerificationRun),
    forward(client, 'provider.verify', (r) => ({ provider_id: r.params.id, ...r.body })));
  return router;
}

/** GET /capabilities — effective, sanitized capabilities for the current principal and environment. */
export function createCapabilitiesRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.get('/', forward(client, 'capabilities.effective', () => ({})));
  return router;
}
