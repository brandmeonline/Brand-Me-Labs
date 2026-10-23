/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1/providers (operator console) and /api/v1/capabilities (sanitized) —
 * UNMOUNTED routers (lane: opus-commerce-agents).
 *
 * Console routes require the `provider:admin` role for every caller; a member session never
 * implies it. Secret fields are write-only: requests may carry a Secret Manager resource name,
 * never a secret value, and responses only show whether a credential is configured. "Connect"
 * is never a local boolean: activation goes through the setup checklist and verification
 * evidence. The domain answers 501 for setup changes and verification runs until that
 * operator workflow is built.
 */

import { Router } from 'express';
import { z } from 'zod';
import { type CommerceDomainClient, forward, rejectIdentityFields, requireRole, validate } from './commerce';

export const SetupUpdate = z
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
  router.use(rejectIdentityFields, requireRole('provider:admin'));
  router.get('/', forward(client, 'provider.list', () => ({})));
  router.get('/:id', forward(client, 'provider.get', (req) => ({ provider_id: req.params.id })));
  router.get('/:id/setup', forward(client, 'provider.setup.get', (req) => ({ provider_id: req.params.id })));
  router.patch('/:id/setup', validate(SetupUpdate),
    forward(client, 'provider.setup.update', (req, res) => ({ provider_id: req.params.id, ...(res.locals.input as object) })));
  router.get('/:id/health', forward(client, 'provider.health', (req) => ({ provider_id: req.params.id })));
  router.post('/:id/verification-runs', validate(VerificationRun),
    forward(client, 'provider.verify', (req, res) => ({ provider_id: req.params.id, ...(res.locals.input as object) })));
  return router;
}

/** GET /capabilities — sanitized capability summary for any signed-in principal. */
export function createCapabilitiesRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.get('/', forward(client, 'capabilities.effective', () => ({})));
  return router;
}
