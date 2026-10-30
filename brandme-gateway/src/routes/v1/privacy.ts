/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /v1/me/data, /v1/me/exports, /v1/me/deletion — My Data (W10).
 * Mounted under /api/v1/me behind the gateway principal boundary.
 *
 * Export and deletion require `privacy:manage` and a re-authentication within
 * the last 10 minutes. Data export stays available during non-security
 * budget exhaustion (ch.03): mount these before generic rate limiters.
 */

import { ApiProblem, handle, problems } from '../../middleware/problem';

import { Router } from 'express';
import type { Router as IRouter } from 'express';
import { z } from 'zod';
import { relay, subjectOr401, type V1Deps } from './chain';

const REAUTH_SECONDS = 600;

const categoriesSchema = z.array(z.string().regex(/^[a-z_]+\.[a-z_]+$/)).min(1).max(100)
  .refine((values) => new Set(values).size === values.length, { message: 'categories must be distinct' });
const exportSchema = z.object({ categories: categoriesSchema }).strict();
const exportCapability = z.object({ status: z.literal('available'), environment: z.string(),
  network: z.enum(['undeployed', 'preview', 'preprod']), contract_address: z.string().regex(/^[0-9a-f]{64}$/),
  categories: categoriesSchema, full_account: z.literal(false), selected_categories_only: z.literal(true) }).strict();
const deletionSchema = z.object({
  scope: z.enum(['account', 'category']),
  categories: categoriesSchema.optional(),
  confirm: z.literal(true),
}).strict().refine((b) => b.scope === 'account' || (b.categories && b.categories.length > 0), {
  message: 'category deletion needs at least one category',
}).refine((b) => b.scope !== 'account' || b.categories === undefined, {
  message: 'account deletion cannot include category filters',
});

export function createPrivacyRouter(deps: V1Deps): IRouter {
  const router: IRouter = Router();

  router.get('/data', deps.requireScope('privacy:manage'), handle(async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const inventory = await deps.upstream.privacy.get('/inventory', { 'x-subject-ref': subject });
    if (inventory.status === 200 && inventory.body && typeof inventory.body === 'object' && deps.upstream.exports) {
      const body = inventory.body as { environment?: string; categories?: { key: string }[]; capabilities?: { export: string; deletion: string } };
      try {
        const r = await deps.upstream.exports.get('/capability', { 'x-subject-ref': subject });
        const cap = exportCapability.parse(r.body);
        if (r.status === 200 && cap.environment === body.environment && body.capabilities
          && cap.categories.length === body.categories?.length && cap.categories.every((c) => body.categories?.some((d) => d.key === c))) {
          inventory.body = { ...body, capabilities: { ...body.capabilities, export: 'selected_categories' } };
        }
      } catch { /* Keep the read service's explicit unavailable capability. */ }
    }
    relay(res, inventory);
  }));

  router.get('/exports/capability', deps.requireScope('privacy:manage'), handle(async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    if (Object.keys(req.query).length) throw new ApiProblem(400, 'invalid_query', 'Invalid query', 'This route accepts no query parameters.');
    if (!deps.upstream.exports) throw problems.unavailable('Exports are not configured.');
    const r = await deps.upstream.exports.get('/capability', { 'x-subject-ref': subject });
    const parsed = exportCapability.safeParse(r.body);
    if (r.status !== 200 || !parsed.success) throw problems.unavailable('Export capability could not be verified.');
    relay(res, { status: 200, body: parsed.data });
  }));

  router.post('/exports', deps.requireScope('privacy:manage'), deps.requireRecentAuth(REAUTH_SECONDS), handle(async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const body = exportSchema.safeParse(req.body ?? {});
    if (!body.success || Object.keys(req.query).length) throw new ApiProblem(400, 'invalid_request', 'Select export categories', 'Choose explicit supported categories.');
    const key = req.header('idempotency-key');
    const keyCount = req.rawHeaders.filter((_h, i) => i % 2 === 0 && req.rawHeaders[i]?.toLowerCase() === 'idempotency-key').length;
    if (keyCount !== 1 || !key || !/^[A-Za-z0-9_-]{16,128}$/.test(key)) throw new ApiProblem(400, 'idempotency_key_required', 'Idempotency key required', 'Send one valid Idempotency-Key header.');
    if (!deps.upstream.exports) throw problems.unavailable('Exports are not configured.');
    const authTime = deps.authTimeOf(req);
    relay(res, await deps.upstream.exports.post('/exports', { ...body.data, reauth_at: authTime?.toISOString() },
      { 'x-subject-ref': subject, 'idempotency-key': key }));
  }));

  router.get('/exports/:jobId', deps.requireScope('privacy:manage'), handle(async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const id = z.string().uuid().safeParse(req.params.jobId);
    if (!id.success || Object.keys(req.query).length) throw new ApiProblem(400, 'invalid_request', 'Invalid export request', 'Supply a valid job ID and no query parameters.');
    if (!deps.upstream.exports) throw problems.unavailable('Exports are not configured.');
    relay(res, await deps.upstream.exports.get(`/exports/${id.data.toLowerCase()}`, { 'x-subject-ref': subject }));
  }));

  router.get('/exports/:jobId/download', deps.requireScope('privacy:manage'), deps.requireRecentAuth(REAUTH_SECONDS), handle(async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const id = z.string().uuid().safeParse(req.params.jobId);
    if (!id.success || Object.keys(req.query).length) throw new ApiProblem(400, 'invalid_request', 'Invalid export request', 'Supply a valid job ID and no query parameters.');
    if (!deps.upstream.exports) throw problems.unavailable('Exports are not configured.');
    const r = await deps.upstream.exports.download(`/exports/${id.data.toLowerCase()}/download`,
      { 'x-subject-ref': subject, 'x-reauth-at': deps.authTimeOf(req)!.toISOString() });
    res.set({ 'Cache-Control': 'private, no-store', 'X-Export-SHA256': r.sha256, 'X-Content-Type-Options': 'nosniff',
      'Content-Disposition': `attachment; filename="brandme-rights-${id.data.toLowerCase()}.json"` }).type('application/json').send(r.bytes);
  }));

  router.post('/deletion', deps.requireScope('privacy:manage'), deps.requireRecentAuth(REAUTH_SECONDS), handle(async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const body = deletionSchema.safeParse(req.body);
    if (!body.success) { res.status(400).json({ error: 'invalid_request', details: body.error.issues }); return; }
    const authTime = deps.authTimeOf(req);
    relay(res, await deps.upstream.privacy.post('/deletion', {
      categories: body.data.scope === 'account' ? null : body.data.categories,
      reauth_at: authTime?.toISOString(),
    }, { 'x-subject-ref': subject }));
  }));

  router.get('/deletion/:jobId', deps.requireScope('privacy:manage'), handle(async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    if (!z.string().uuid().safeParse(req.params.jobId).success) { res.status(400).json({ error: 'invalid_job_id' }); return; }
    relay(res, await deps.upstream.privacy.get(`/deletion/${req.params.jobId}`, { 'x-subject-ref': subject }));
  }));

  return router;
}
