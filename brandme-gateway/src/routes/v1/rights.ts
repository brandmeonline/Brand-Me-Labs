/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /v1/rights — the member's entitlements and reprint jobs.
 * UNMOUNTED (mounted by opus-foundation).
 */

import { Router } from 'express';
import type { Router as IRouter } from 'express';
import { z } from 'zod';
import { chainCapability, relay, subjectOr401, type V1Deps } from './chain';

export function createRightsRouter(deps: V1Deps): IRouter {
  const router: IRouter = Router();

  router.get('/entitlements', deps.requireScope('rights:read'), async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const [cap, r] = await Promise.all([chainCapability(deps), deps.upstream.rights.get('/entitlements', { 'x-subject-ref': subject })]);
    if (r.status !== 200) { relay(res, r); return; }
    // Every response carries the network badge so a test-network entitlement is never shown as Mainnet ownership.
    res.status(200).json({ network: cap.network, badge: cap.badge, capability: cap.status, ...(r.body as object) });
  });

  router.get('/reprint-jobs/:jobId', deps.requireScope('rights:reprint'), async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    if (!z.string().uuid().safeParse(req.params.jobId).success) { res.status(400).json({ error: 'invalid_job_id' }); return; }
    relay(res, await deps.upstream.rights.get(`/reprint-jobs/${req.params.jobId}`, { 'x-subject-ref': subject }));
  });

  return router;
}
