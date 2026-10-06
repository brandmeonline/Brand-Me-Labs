/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /v1/me/data, /v1/me/exports, /v1/me/deletion — My Data (W10).
 * UNMOUNTED (mounted by opus-foundation under /v1/me).
 *
 * Export and deletion require `privacy:manage` and a re-authentication within
 * the last 10 minutes. Data export stays available during non-security
 * budget exhaustion (ch.03): mount these before generic rate limiters.
 */

import { Router } from 'express';
import type { Router as IRouter } from 'express';
import { z } from 'zod';
import { relay, subjectOr401, type V1Deps } from './chain';

const REAUTH_SECONDS = 600;

const exportSchema = z.object({ categories: z.array(z.string().regex(/^[a-z_]+\.[a-z_]+$/)).max(100).optional() }).strict();
const deletionSchema = z.object({
  scope: z.enum(['account', 'category']),
  categories: z.array(z.string().regex(/^[a-z_]+\.[a-z_]+$/)).max(100).optional(),
  confirm: z.literal(true),
}).strict().refine((b) => b.scope === 'account' || (b.categories && b.categories.length > 0), {
  message: 'category deletion needs at least one category',
});

export function createPrivacyRouter(deps: V1Deps): IRouter {
  const router: IRouter = Router();

  router.get('/data', deps.requireScope('privacy:manage'), async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    relay(res, await deps.upstream.privacy.get('/inventory', { 'x-subject-ref': subject }));
  });

  router.post('/exports', deps.requireScope('privacy:manage'), deps.requireRecentAuth(REAUTH_SECONDS), async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const body = exportSchema.safeParse(req.body ?? {});
    if (!body.success) { res.status(400).json({ error: 'invalid_request', details: body.error.issues }); return; }
    const authTime = deps.authTimeOf(req);
    relay(res, await deps.upstream.privacy.post('/exports', { ...body.data, reauth_at: authTime?.toISOString() }, { 'x-subject-ref': subject }));
  });

  router.post('/deletion', deps.requireScope('privacy:manage'), deps.requireRecentAuth(REAUTH_SECONDS), async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const body = deletionSchema.safeParse(req.body);
    if (!body.success) { res.status(400).json({ error: 'invalid_request', details: body.error.issues }); return; }
    const authTime = deps.authTimeOf(req);
    relay(res, await deps.upstream.privacy.post('/deletion', {
      categories: body.data.scope === 'account' ? null : body.data.categories,
      reauth_at: authTime?.toISOString(),
    }, { 'x-subject-ref': subject }));
  });

  router.get('/deletion/:jobId', deps.requireScope('privacy:manage'), async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    if (!z.string().uuid().safeParse(req.params.jobId).success) { res.status(400).json({ error: 'invalid_job_id' }); return; }
    relay(res, await deps.upstream.privacy.get(`/deletion/${req.params.jobId}`, { 'x-subject-ref': subject }));
  });

  return router;
}
