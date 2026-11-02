/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /v1/chain — Midnight capability and operation status. Mounted behind the gateway principal boundary.
 *
 * Shared contract for all v1 rights/privacy routers in this directory: they
 * are factories taking injected dependencies, so they carry no coupling to
 * the gateway's middleware/config internals.
 */

import { handle, problems } from '../../middleware/problem';

import { z } from 'zod';
import { Router, type Request, type RequestHandler, type Response } from 'express';
import type { Router as IRouter } from 'express';

export interface UpstreamResponse { status: number; body: unknown }
export interface UpstreamClient {
  get(path: string, headers?: Record<string, string>): Promise<UpstreamResponse>;
  post(path: string, body: unknown, headers?: Record<string, string>): Promise<UpstreamResponse>;
}

export interface ExportClient extends UpstreamClient {
  download(path: string, headers: Record<string, string>): Promise<{ bytes: Buffer; sha256: string }>;
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
  /** The verified principal's scopes; only the rights scopes are forwarded upstream. */
  scopesOf?(req: Request): readonly string[];
  upstream: {
    operations?: UpstreamClient; // authenticated chain operation journal
    chain: UpstreamClient;     // brandme-chain service
    rights: UpstreamClient;    // read-only rights service (brandme_core.read_api)
    commands?: UpstreamClient; // rights command service (brandme_core.rights_commands)
    privacy: UpstreamClient;   // My Data service (brandme_core.domains.privacy)
    exports?: ExportClient;   // independently deployed, selected-category export API
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
  res.set('Cache-Control', 'no-store').status(r.status).json(r.body);
}

/** The scopes the command service accepts (brandme_core/rights_commands/app.py SCOPES). */
const COMMAND_SCOPES = new Set(['rights:read', 'rights:transfer', 'rights:reprint', 'privacy:manage']);
/** Same key format the command service accepts. */
const IDEMPOTENCY_KEY = /^[A-Za-z0-9._~:-]{16,128}$/;

/** The resolved principal for the command service, which re-checks scope and recent authentication. */
export function commandHeaders(deps: V1Deps, req: Request, subject: string, extra: Record<string, string> = {}): Record<string, string> {
  const scopes = (deps.scopesOf?.(req) ?? []).filter((s) => COMMAND_SCOPES.has(s));
  const authTime = deps.authTimeOf(req);
  return { 'x-subject-ref': subject, 'x-principal-scopes': scopes.join(' '),
    ...(authTime ? { 'x-auth-time': authTime.toISOString() } : {}), ...extra };
}

export function commandsOf(deps: V1Deps): UpstreamClient {
  if (!deps.upstream.commands) throw problems.unavailable('Rights commands are not configured.');
  return deps.upstream.commands;
}

export function idempotencyKeyOr400(req: Request, res: Response): string | undefined {
  const key = req.header('idempotency-key');
  if (!key || !IDEMPOTENCY_KEY.test(key)) { res.status(400).json({ error: 'idempotency_key_required' }); return undefined; }
  return key;
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
    relay(res, await (deps.upstream.operations ?? deps.upstream.rights).get(`/operations/${req.params.operationId}`, { 'x-subject-ref': subject }));
  }));

  return router;
}
