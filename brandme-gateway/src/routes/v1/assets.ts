/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /v1/assets/:id — claim-level passport, transfer intents, reprint quotes.
 * Mounted under /api/v1 behind the gateway principal boundary.
 */

import { handle } from '../../middleware/problem';

import { Router } from 'express';
import type { Router as IRouter } from 'express';
import { z } from 'zod';
import {
  capabilityUnavailable, chainCapability, commandHeaders, commandsOf, idempotencyKeyOr400, relay, subjectOr401, type V1Deps,
} from './chain';
import { readQuery } from './read-query';

const assetId = z.string().uuid();
const lowerUuid = z.string().regex(/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/);
/** Re-auth window for moving ownership, as for My Data export and deletion. */
export const TRANSFER_REAUTH_SECONDS = 600;

/**
 * A bearer secret the sender's app generates and gives the recipient privately;
 * 43+ base64url characters carry at least 256 bits. The command service stores
 * only its SHA-256 digest. Never an email address or handle.
 */
export const recipientInvite = z.string().regex(/^[A-Za-z0-9_-]{43,128}$/);

const transferSchema = z.object({
  rights_scope: z.array(z.enum(['display', 'transfer', 'personal_manufacture', 'repair_parts', 'commercial_reproduction'])).min(1),
  recipient_invite: recipientInvite,
  expires_in_seconds: z.number().int().min(300).max(7 * 24 * 3600),
  include_documents: z.array(lowerUuid).max(20).default([]),
}).strict();

const reprintQuoteSchema = z.object({
  quantity: z.number().int().min(1).max(100),
  manufacturer_id: z.string().regex(/^[0-9a-f]{64}$/),
  territory: z.string().regex(/^[A-Z]{2}$/),
  modifications: z.record(z.string(), z.string()).default({}),
}).strict();

export function createAssetsRouter(deps: V1Deps): IRouter {
  const router: IRouter = Router();

  // Claim-level passport. Visibility is resolved server-side by the rights service from the viewer's relation.
  router.get('/:id/passport', handle(async (req, res) => {
    const id = assetId.safeParse(req.params.id);
    if (!id.success) { res.status(400).json({ error: 'invalid_asset_id' }); return; }
    const query = readQuery(req.query, z.string().uuid());
    const subject = deps.subjectOf(req);
    const r = await deps.upstream.rights.get(`/assets/${id.data}/passport${query}`, subject ? { 'x-subject-ref': subject } : {});
    relay(res, r);
  }));

  router.post('/:id/transfers', deps.requireScope('rights:transfer'), deps.requireRecentAuth(TRANSFER_REAUTH_SECONDS),
    handle(async (req, res) => {
      const subject = subjectOr401(deps, req, res);
      if (!subject) return;
      const id = assetId.safeParse(req.params.id);
      const body = transferSchema.safeParse(req.body);
      if (!id.success || !body.success) { res.status(400).json({ error: 'invalid_request', details: body.success ? undefined : body.error.issues }); return; }
      const idem = idempotencyKeyOr400(req, res);
      if (!idem) return;
      const cap = await chainCapability(deps);
      if (capabilityUnavailable(res, cap)) return;
      // The command service scopes the intent to its configured network and contract. The
      // proving arguments appear on GET /transfers/:id once the recipient has bound a commitment.
      relay(res, await commandsOf(deps).post(`/rights/assets/${id.data}/transfers`, body.data,
        commandHeaders(deps, req, subject, { 'idempotency-key': idem })));
    }));

  router.post('/:id/reprint-quotes', deps.requireScope('rights:reprint'), handle(async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const id = assetId.safeParse(req.params.id);
    const body = reprintQuoteSchema.safeParse(req.body);
    if (!id.success || !body.success) { res.status(400).json({ error: 'invalid_request', details: body.success ? undefined : body.error.issues }); return; }
    const cap = await chainCapability(deps);
    if (capabilityUnavailable(res, cap)) return;
    // The command service checks license, controller entitlement, quota, manufacturer capability and territory,
    // and returns either a quote or the missing conditions. Browsing never consumes quota.
    relay(res, await commandsOf(deps).post(`/rights/assets/${id.data}/reprint-quotes`, body.data, commandHeaders(deps, req, subject)));
  }));

  return router;
}
