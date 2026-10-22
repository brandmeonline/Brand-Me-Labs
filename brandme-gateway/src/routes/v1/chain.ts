/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /v1/chain — Midnight capability and operation status. Mounted behind the gateway principal boundary.
 *
 * Shared contract for all v1 rights/privacy routers in this directory: they
 * are factories taking injected dependencies, so they carry no coupling to
 * the gateway's middleware/config internals.
 */

import { handle } from '../../middleware/problem';

import { z } from 'zod';
import { Router, type Request, type RequestHandler, type Response } from 'express';
import type { Router as IRouter } from 'express';

export interface UpstreamResponse { status: number; body: unknown }
export interface UpstreamClient {
  get(path: string, headers?: Record<string, string>): Promise<UpstreamResponse>;
  post(path: string, body: unknown, headers?: Record<string, string>): Promise<UpstreamResponse>;
}

export interface V1Deps {
  /** Rejects with 403 unless the token carries the scope (ch.03 scopes). */
  requireScope(scope: 'rights:read' | 'rights:transfer' | 'rights:reprint' | 'privacy:manage'): RequestHandler;
  /** Rejects with 401 + `reauth_required` unless the member authenticated within maxAgeSeconds. */
  requireRecentAuth(maxAgeSeconds: number): RequestHandler;
  /** Opaque subject reference of the authenticated member. */
  subjectOf(req: Request): string | undefined;
  /** Returns the auth_time of the current session (for re-auth evidence passed upstream). */
  authTimeOf(req: Request): Date | undefined;
  upstream: {
    chain: UpstreamClient;     // brandme-chain service
    rights: UpstreamClient;    // rights domain service (brandme_core.domains.rights)
    privacy: UpstreamClient;   // My Data service (brandme_core.domains.privacy)
  };
}

export interface MidnightCapabilityView {
  status: 'available' | 'read_only' | 'unavailable';
  reasons: string[];
  badge: string | null;
  network: string;
}

/** Fetch capability; anything unexpected is reported as unavailable, never as available. */
export async function chainCapability(deps: V1Deps): Promise<MidnightCapabilityView> {
  try {
    const r = await deps.upstream.chain.get('/midnight/capability');
    const parsed = z.object({
      status: z.enum(['available', 'read_only', 'unavailable']),
      network: z.enum(['undeployed', 'preview', 'preprod', 'mainnet']),
      reasons: z.array(z.string().max(256)).max(16),
    }).safeParse(r.body);
    if (r.status !== 200 || !parsed.success) throw new Error('invalid capability');
    const b = parsed.data;
    const badges = { undeployed: 'Local test network', preview: 'Preview test network', preprod: 'Preprod test network', mainnet: 'Mainnet' };
    return { ...b, status: b.network === 'mainnet' && b.status === 'available' ? 'read_only' : b.status, badge: badges[b.network] };
  } catch {
    return { status: 'unavailable', reasons: ['Chain capability could not be verified.'], badge: null, network: 'unknown' };
  }
}

export function capabilityUnavailable(res: Response, cap: MidnightCapabilityView, need: 'available' | 'read_only' = 'available'): boolean {
  const ok = need === 'read_only' ? cap.status !== 'unavailable' : cap.status === 'available';
  if (ok) return false;
  res.status(503).json({ error: 'capability_unavailable', capability: 'midnight_rights', status: cap.status, reasons: cap.reasons, badge: cap.badge });
  return true;
}

export function subjectOr401(deps: V1Deps, req: Request, res: Response): string | undefined {
  const s = deps.subjectOf(req);
  if (!s) res.status(401).json({ error: 'unauthenticated' });
  return s;
}

export function relay(res: Response, r: UpstreamResponse): void {
  res.status(r.status).json(r.body);
}

export function createChainRouter(deps: V1Deps): IRouter {
  const router: IRouter = Router();

  router.get('/capability', handle(async (_req, res) => {
    res.status(200).json(await chainCapability(deps));
  }));

  router.get('/operations/:operationId', deps.requireScope('rights:read'), handle(async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    if (!/^[0-9a-f-]{36}$/i.test(req.params.operationId!)) { res.status(400).json({ error: 'invalid_operation_id' }); return; }
    relay(res, await deps.upstream.rights.get(`/operations/${req.params.operationId}`, { 'x-subject-ref': subject }));
  }));

  return router;
}
