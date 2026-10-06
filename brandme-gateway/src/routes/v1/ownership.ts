/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /v1/ownership — proof challenges and client-reported submissions.
 * UNMOUNTED (mounted by opus-foundation).
 *
 * The member's wallet proves and submits; the gateway only issues a fresh
 * single-use challenge bound to an audience, and accepts a reported tx id for
 * reconciliation. A reported tx id is a hint to look up — never evidence.
 */

import { Router } from 'express';
import type { Router as IRouter } from 'express';
import { randomBytes } from 'node:crypto';
import { z } from 'zod';
import { capabilityUnavailable, chainCapability, relay, subjectOr401, type V1Deps } from './chain';

const hex32 = z.string().regex(/^[0-9a-f]{64}$/i);

const challengeSchema = z.object({
  entitlement_id: hex32,
  audience: z.string().min(1).max(128),   // who will verify (e.g. resale partner id)
}).strict();

const reportSchema = z.object({
  operation_id: z.string().uuid(),
  tx_id: z.string().min(8).max(256),
  network: z.enum(['undeployed', 'preview', 'preprod']),
}).strict();

export function createOwnershipRouter(deps: V1Deps): IRouter {
  const router: IRouter = Router();

  router.post('/challenges', deps.requireScope('rights:read'), async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const body = challengeSchema.safeParse(req.body);
    if (!body.success) { res.status(400).json({ error: 'invalid_request', details: body.error.issues }); return; }
    const cap = await chainCapability(deps);
    if (capabilityUnavailable(res, cap)) return;
    const challenge = randomBytes(32).toString('hex');
    const r = await deps.upstream.rights.post('/challenges', { ...body.data, challenge, ttl_seconds: 300 }, { 'x-subject-ref': subject });
    if (r.status !== 201) { relay(res, r); return; }
    res.status(201).json({ ...(r.body as object), challenge, network: cap.network, badge: cap.badge, circuit: 'proveControl' });
  });

  router.post('/submissions', deps.requireScope('rights:transfer'), async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const body = reportSchema.safeParse(req.body);
    if (!body.success) { res.status(400).json({ error: 'invalid_request', details: body.error.issues }); return; }
    const cap = await chainCapability(deps);
    if (cap.network !== body.data.network) {
      res.status(409).json({ error: 'wrong_network', expected: cap.network, got: body.data.network });
      return;
    }
    relay(res, await deps.upstream.rights.post('/operations/reconcile', body.data, { 'x-subject-ref': subject }));
  });

  return router;
}
