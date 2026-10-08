/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /v1/assets/:id — claim-level passport, transfer intents, reprint quotes.
 * UNMOUNTED (mounted by opus-foundation).
 */

import { Router } from 'express';
import type { Router as IRouter } from 'express';
import { z } from 'zod';
import { capabilityUnavailable, chainCapability, relay, subjectOr401, type V1Deps } from './chain';

const assetId = z.string().uuid();

const transferSchema = z.object({
  rights_scope: z.array(z.enum(['display', 'transfer', 'personal_manufacture', 'repair_parts', 'commercial_reproduction'])).min(1),
  recipient_invite: z.string().min(8).max(128),     // private invite token; never an email/handle in the clear
  expires_in_seconds: z.number().int().min(300).max(7 * 24 * 3600),
  include_documents: z.array(z.string().uuid()).max(20).default([]),
}).strict();

const reprintQuoteSchema = z.object({
  quantity: z.number().int().min(1).max(100),
  manufacturer_id: z.string().regex(/^[0-9a-f]{64}$/i),
  territory: z.string().length(2),
  modifications: z.record(z.string(), z.string()).default({}),
}).strict();

export function createAssetsRouter(deps: V1Deps): IRouter {
  const router: IRouter = Router();

  // Claim-level passport. Visibility is resolved server-side by the rights service from the viewer's relation.
  router.get('/:id/passport', async (req, res) => {
    const id = assetId.safeParse(req.params.id);
    if (!id.success) { res.status(400).json({ error: 'invalid_asset_id' }); return; }
    const subject = deps.subjectOf(req);
    const r = await deps.upstream.rights.get(`/assets/${id.data}/passport`, subject ? { 'x-subject-ref': subject } : {});
    relay(res, r);
  });

  router.post('/:id/transfers', deps.requireScope('rights:transfer'), async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const id = assetId.safeParse(req.params.id);
    const body = transferSchema.safeParse(req.body);
    if (!id.success || !body.success) { res.status(400).json({ error: 'invalid_request', details: body.success ? undefined : body.error.issues }); return; }
    const cap = await chainCapability(deps);
    if (capabilityUnavailable(res, cap)) return;
    const idem = req.header('idempotency-key');
    if (!idem || idem.length < 8) { res.status(400).json({ error: 'idempotency_key_required' }); return; }
    const r = await deps.upstream.rights.post(`/assets/${id.data}/transfers`, { ...body.data, network: cap.network },
      { 'x-subject-ref': subject, 'idempotency-key': idem });
    // Proving requirements come back from the rights service: circuit, expected epoch, network badge, prover modes.
    relay(res, r);
  });

  router.post('/:id/reprint-quotes', deps.requireScope('rights:reprint'), async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const id = assetId.safeParse(req.params.id);
    const body = reprintQuoteSchema.safeParse(req.body);
    if (!id.success || !body.success) { res.status(400).json({ error: 'invalid_request', details: body.success ? undefined : body.error.issues }); return; }
    const cap = await chainCapability(deps);
    if (capabilityUnavailable(res, cap)) return;
    // The rights service checks license, controller entitlement, quota, manufacturer capability, territory and
    // files, and returns either a quote or the missing conditions. Browsing never consumes quota.
    relay(res, await deps.upstream.rights.post(`/assets/${id.data}/reprint-quotes`, body.data, { 'x-subject-ref': subject }));
  });

  return router;
}
