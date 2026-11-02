import { beforeAll, describe, expect, it, vi } from 'vitest';
import { exportPKCS8, generateKeyPair, jwtVerify, type KeyLike } from 'jose';
import { loadConfig } from '../config';
import type { Principal } from '../types';
import { DOMAIN_AUDIENCE, DOMAIN_ISSUER, consumerDomainClient } from './domains';

const principal: Principal = {
  memberId: '11111111-1111-4111-8111-111111111111', subject: 'dev|e2e', sessionId: 'abc123', clientId: null,
  scopes: ['wardrobe:read', 'wardrobe:write'], assuranceLevel: 'simulated', environment: 'development', delegationId: null,
  identityProvider: 'dev', expiresAt: new Date(Date.now() + 60_000), via: 'session',
};
let publicKey: KeyLike;
let pem = '';

beforeAll(async () => {
  const pair = await generateKeyPair('ES256', { extractable: true });
  publicKey = pair.publicKey;
  pem = await exportPKCS8(pair.privateKey);
});

function client(fetchImpl: typeof fetch, configured = true) {
  const cfg = loadConfig({ BRANDME_MODE: 'development', ...(configured ? {
    CONSUMER_DOMAIN_SERVICE_URL: 'http://domains.internal/', CONSUMER_DOMAIN_ASSERTION_KEY: pem, CONSUMER_DOMAIN_ASSERTION_KID: 'k-1' } : {}) });
  return consumerDomainClient(cfg, fetchImpl);
}

describe('consumer-domain client', () => {
  it('sends a short-lived, audience-bound assertion and only router-built fields', async () => {
    const fetchImpl = vi.fn(async () => Response.json({ ok: true }, { status: 201, headers: { etag: '"3"' } }));
    const out = await client(fetchImpl as unknown as typeof fetch).request({
      method: 'POST', path: '/wardrobe/items', principal, requestId: 'req-1', body: { title: 'Coat' },
      query: { limit: '5' }, ifMatch: '"2"', idempotencyKey: 'k'.repeat(20),
    });
    expect(out).toEqual({ status: 201, body: { ok: true }, headers: { etag: '"3"', 'content-type': 'application/json' } });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('http://domains.internal/wardrobe/items?limit=5');
    expect(init.redirect).toBe('error');
    const headers = init.headers as Record<string, string>;
    expect(Object.keys(headers).sort()).toEqual(['accept', 'authorization', 'content-type', 'idempotency-key', 'if-match', 'x-request-id']);
    const token = headers.authorization.replace(/^Bearer /, '');
    const { payload, protectedHeader } = await jwtVerify(token, publicKey, { issuer: DOMAIN_ISSUER, audience: DOMAIN_AUDIENCE });
    expect(protectedHeader).toEqual({ alg: 'ES256', kid: 'k-1' });
    expect(payload.exp! - payload.iat!).toBe(30);
    expect(payload.jti).toMatch(/^[0-9a-f-]{36}$/);
    expect(payload.principal).toEqual({ member_id: principal.memberId, subject: 'dev|e2e', session_id: 'abc123', client_id: null,
      scopes: ['wardrobe:read', 'wardrobe:write'], assurance_level: 'simulated', environment: 'development', delegation_id: null });
    expect(JSON.parse(init.body as string)).toEqual({ title: 'Coat' });
  });

  it('mints a fresh assertion per request and none for anonymous share-link calls', async () => {
    const fetchImpl = vi.fn(async () => Response.json({}));
    const c = client(fetchImpl as unknown as typeof fetch);
    await c.request({ method: 'GET', path: '/a', principal, requestId: 'r' });
    await c.request({ method: 'GET', path: '/a', principal, requestId: 'r' });
    await c.request({ method: 'GET', path: '/shares/x', principal: null, requestId: 'r' });
    const auth = (fetchImpl.mock.calls as unknown as [string, RequestInit][]).map(([, i]) => (i.headers as Record<string, string>).authorization);
    expect(auth[0]).not.toBe(auth[1]);
    expect(auth[2]).toBeUndefined();
  });

  it('passes result images through as bytes and refuses non-JSON bodies', async () => {
    const png = Buffer.from([0x89, 0x50, 0x4e, 0x47]);
    const image = client((async () => new Response(png, { headers: { 'content-type': 'image/png' } })) as typeof fetch);
    const out = await image.request({ method: 'GET', path: '/try-on/jobs/x/result', principal, requestId: 'r' });
    expect(Buffer.isBuffer(out.body) && out.body.equals(png)).toBe(true);
    const html = client((async () => new Response('<h1>Internal error at /srv</h1>', { status: 500 })) as typeof fetch);
    await expect(html.request({ method: 'GET', path: '/a', principal, requestId: 'r' })).rejects.toMatchObject({ status: 503 });
  });

  it('is unavailable when unconfigured or unreachable', async () => {
    const never = vi.fn();
    await expect(client(never as unknown as typeof fetch, false).request({ method: 'GET', path: '/a', principal, requestId: 'r' }))
      .rejects.toMatchObject({ status: 503 });
    expect(never).not.toHaveBeenCalled();
    const down = client((async () => { throw new TypeError('connect ECONNREFUSED'); }) as typeof fetch);
    await expect(down.request({ method: 'GET', path: '/a', principal, requestId: 'r' })).rejects.toMatchObject({ status: 503 });
  });
});
