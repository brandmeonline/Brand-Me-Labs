/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /v1/rights — the member's entitlements and reprint jobs.
 * Mounted under /api/v1 behind the gateway principal boundary.
 */

import { handle } from '../../middleware/problem';

import { Router } from 'express';
import type { Router as IRouter } from 'express';
import { z } from 'zod';
import { chainCapability, relay, subjectOr401, type V1Deps } from './chain';
import { problems } from '../../middleware/problem';
import { readQuery } from './read-query';

export function createRightsRouter(deps: V1Deps): IRouter {
  const router: IRouter = Router();

  router.get('/entitlements', deps.requireScope('rights:read'), handle(async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const query = readQuery(req.query, z.string().regex(/^[0-9a-f]{64}$/));
    const [cap, r] = await Promise.all([chainCapability(deps), deps.upstream.rights.get(`/entitlements${query}`, { 'x-subject-ref': subject })]);
    if (r.status !== 200) { relay(res, r); return; }
    const body = z.object({ network: z.enum(['undeployed', 'preview', 'preprod', 'mainnet']) }).passthrough().safeParse(r.body);
    if (!body.success || body.data.network !== cap.network) throw problems.unavailable('The rights network could not be verified.');
    // Attach a badge only after verifying the response's actual network.
    res.set('Cache-Control', 'no-store').status(200).json({ ...body.data, badge: cap.badge, capability: cap.status });
  }));

  router.get('/reprint-jobs/:jobId', deps.requireScope('rights:reprint'), handle(async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    if (!z.string().uuid().safeParse(req.params.jobId).success) { res.status(400).json({ error: 'invalid_job_id' }); return; }
    relay(res, await deps.upstream.rights.get(`/reprint-jobs/${req.params.jobId}`, { 'x-subject-ref': subject }));
  }));

  return router;
}
