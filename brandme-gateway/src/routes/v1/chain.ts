/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /v1/chain — Midnight capability and operation status. UNMOUNTED: the
 * opus-foundation lane mounts these routers in the gateway entrypoint.
 *
 * Shared contract for all v1 rights/privacy routers in this directory: they
 * are factories taking injected dependencies, so they carry no coupling to
 * the gateway's middleware/config internals.
 */

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
    const b = r.body as Partial<MidnightCapabilityView> | undefined;
    if (r.status !== 200 || !b || !b.status) return { status: 'unavailable', reasons: [`chain service responded ${r.status}`], badge: null, network: 'unknown' };
    return { status: b.status, reasons: b.reasons ?? [], badge: b.badge ?? null, network: b.network ?? 'unknown' };
  } catch (e) {
    return { status: 'unavailable', reasons: [`chain service unreachable: ${(e as Error).message}`], badge: null, network: 'unknown' };
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

  router.get('/capability', async (_req, res) => {
    res.status(200).json(await chainCapability(deps));
  });

  router.get('/operations/:operationId', deps.requireScope('rights:read'), async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    if (!/^[0-9a-f-]{36}$/i.test(req.params.operationId!)) { res.status(400).json({ error: 'invalid_operation_id' }); return; }
    relay(res, await deps.upstream.rights.get(`/operations/${req.params.operationId}`, { 'x-subject-ref': subject }));
  });

  return router;
}
