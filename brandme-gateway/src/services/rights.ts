/** Authenticated boundary for the v1 rights and My Data routers. */
import type { Request } from 'express';
import { createHash } from 'node:crypto';
import type { GatewayConfig } from '../config';
import type { Principal } from '../types';
import { ApiProblem, problems } from '../middleware/problem';
import type { ExportClient, UpstreamClient, V1Deps } from '../routes/v1/chain';

const principal = (req: Request): Principal | undefined => req.res?.locals.principal;

function client(base: string | undefined, token: string | undefined, doFetch: typeof fetch, authenticated: boolean, timeoutMs = 5000): UpstreamClient {
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
        await response.body?.cancel();
        // Status is useful; arbitrary provider error bodies are not safe to
        // expose. Keep the gateway's public Problem contract on every route.
        if (response.status === 404) throw problems.notFound();
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
