/** Authenticated boundary for the v1 rights and My Data routers. */
import type { Request } from 'express';
import { createHash } from 'node:crypto';
import type { GatewayConfig } from '../config';
import type { Principal } from '../types';
import { ApiProblem, problems } from '../middleware/problem';
import type { ExportClient, UpstreamClient, V1Deps } from '../routes/v1/chain';

const principal = (req: Request): Principal | undefined => req.res?.locals.principal;

/**
 * Refusals the rights command service reports with a fixed public code
 * (brandme_core/domains/rights/commands.py). Only these codes are relayed, with
 * gateway-owned text; any other error body is still discarded.
 */
const COMMAND_REFUSALS: Readonly<Record<string, string>> = {
  invalid_request: 'The request is not valid.',
  idempotency_key_required: 'An Idempotency-Key header is required.',
  idempotency_key_reused: 'This Idempotency-Key was already used for a different request.',
  operation_in_progress: 'The same request is still being processed.',
  not_transferable: 'This right cannot be transferred.',
  ambiguous_entitlement: 'More than one active right is linked to this item.',
  transfer_in_progress: 'Another transfer of this right is still open.',
  recipient_is_sender: 'You cannot accept your own transfer.',
  invalid_transition: 'This transfer can no longer be accepted.',
  transfer_expired: 'This transfer has expired.',
  stale_intent: 'The right changed after this transfer was offered.',
  processing_frozen: 'Processing is paused by a pending deletion or restriction.',
};

async function refusalCode(response: Response, known: Readonly<Record<string, string>>): Promise<string | undefined> {
  try {
    const text = (await response.text()).slice(0, 4096);
    const code = (JSON.parse(text) as { error?: unknown }).error;
    return typeof code === 'string' && Object.hasOwn(known, code) ? code : undefined;
  } catch {
    return undefined;
  }
}

function client(base: string | undefined, token: string | undefined, doFetch: typeof fetch, authenticated: boolean, timeoutMs = 5000,
  refusals?: Readonly<Record<string, string>>): UpstreamClient {
  const send = async (method: string, path: string, body?: unknown, headers: Record<string, string> = {}) => {
    if (!base || (authenticated && !token)) throw problems.unavailable('This service is not configured.');
    try {
      // Only router-constructed headers cross this boundary. Never forward the caller's bearer token or subject header.
      const response = await doFetch(`${base.replace(/\/$/, '')}${path}`, {
        method, redirect: 'error', signal: AbortSignal.timeout(timeoutMs),
        headers: { ...headers, 'content-type': 'application/json', ...(authenticated ? { authorization: `Bearer ${token}` } : {}) },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      // Provider failures can contain internal URLs or credentials; do not relay them to members.
      if (response.status >= 500 || response.status < 200 || response.status >= 300 && response.status < 400) {
        await response.body?.cancel();
        throw new Error('upstream failure');
      }
      if (response.status >= 400) {
        const code = refusals ? await refusalCode(response, refusals) : undefined;
        if (!refusals) await response.body?.cancel();
        // Status is useful; arbitrary provider error bodies are not safe to
        // expose. Keep the gateway's public Problem contract on every route.
        if (response.status === 404) throw problems.notFound();
        if (code) throw new ApiProblem(response.status, code, 'Request rejected', refusals![code]!);
        if (response.status === 401 || response.status === 403) throw problems.unavailable('The service could not authorize this request.');
        throw new ApiProblem(response.status, 'upstream_request_rejected', 'Request rejected', 'The service could not complete this request.');
      }
      if (response.status === 204) return { status: 200, body: null };
      const reader = response.body?.getReader();
      if (!reader) throw new Error('missing response');
      const chunks: Uint8Array[] = [];
      let size = 0;
      try {
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > 1024 * 1024) throw new Error('oversized response');
          chunks.push(value);
        }
      } finally { await reader.cancel(); }
      return { status: response.status, body: JSON.parse(Buffer.concat(chunks).toString('utf8')) as unknown };
    } catch (error) {
      if (error instanceof ApiProblem) throw error;
      throw problems.unavailable('The service is temporarily unavailable.');
    }
  };
  return { get: (path, headers) => send('GET', path, undefined, headers), post: (path, body, headers) => send('POST', path, body, headers) };
}

export function rightsDependencies(cfg: GatewayConfig, doFetch: typeof fetch = fetch): V1Deps {
  return {
    subjectOf: (req) => principal(req)?.memberId,
    authTimeOf: (req) => principal(req)?.authenticatedAt,
    scopesOf: (req) => principal(req)?.scopes ?? [],
    requireScope: (scope) => (req, _res, next) => {
      const p = principal(req);
      next(!p ? problems.unauthenticated() : !p.scopes.includes(scope) ? problems.forbidden() : undefined);
    },
    requireRecentAuth: (maxAgeSeconds) => (req, _res, next) => {
      const age = Date.now() - (principal(req)?.authenticatedAt?.getTime() ?? NaN);
      next(Number.isFinite(age) && age >= -5000 && age <= maxAgeSeconds * 1000 ? undefined :
        new ApiProblem(401, 'reauth_required', 'Sign in again', 'Recent authentication is required for this action.'));
    },
    upstream: {
      operations: client(`${cfg.chainUrl.replace(/\/$/, '')}/midnight`, cfg.chainServiceToken, doFetch, true, 15000),
      chain: client(cfg.chainUrl, undefined, doFetch, false),
      rights: client(cfg.rightsServiceUrl, cfg.rightsServiceToken, doFetch, true),
      commands: client(cfg.rightsCommandServiceUrl, cfg.rightsCommandServiceToken, doFetch, true, 10000, COMMAND_REFUSALS),
      privacy: client(cfg.privacyServiceUrl, cfg.privacyServiceToken, doFetch, true),
      exports: exportClient(cfg.privacyExportServiceUrl, cfg.privacyExportServiceToken, doFetch),
    },
  };
}

function exportClient(base: string | undefined, token: string | undefined, doFetch: typeof fetch): ExportClient {
  return {
    ...client(base, token, doFetch, true, 15000),
    async download(path, headers) {
      if (!base || !token) throw problems.unavailable('Exports are not configured.');
      try {
        const response = await doFetch(`${base.replace(/\/$/, '')}${path}`, { redirect: 'error', signal: AbortSignal.timeout(15000),
          headers: { ...headers, authorization: `Bearer ${token}` } });
        if (response.status !== 200) {
          await response.body?.cancel();
          if (response.status === 404) throw problems.notFound();
          if ([409, 410, 429].includes(response.status)) throw new ApiProblem(response.status, 'export_unavailable', 'Export unavailable', 'This export cannot be downloaded.');
          throw new Error('unavailable');
        }
        const digest = response.headers.get('x-export-sha256') ?? '';
        const reader = response.body?.getReader();
        if (!reader) throw new Error('missing response');
        const chunks: Uint8Array[] = [];
        let size = 0;
        try {
          if (!/^[0-9a-f]{64}$/.test(digest) || !response.headers.get('content-type')?.startsWith('application/json')) throw new Error('invalid response');
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            size += value.byteLength;
            if (size > 2 * 1024 * 1024) throw new Error('oversized response');
            chunks.push(value);
          }
        } finally { await reader.cancel(); }
        const bytes = Buffer.concat(chunks);
        if (!size || createHash('sha256').update(bytes).digest('hex') !== digest) throw new Error('integrity failure');
        return { bytes, sha256: digest };
      } catch (error) {
        if (error instanceof ApiProblem) throw error;
        throw problems.unavailable('The export could not be verified.');
      }
    },
  };
}
