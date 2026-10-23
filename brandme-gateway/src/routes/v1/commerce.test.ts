/**
 * Router boundary tests for the unmounted commerce routers (lane: opus-commerce-agents).
 * A fake domain client records forwarded operations; no domain logic runs here. The
 * principal is set on res.locals exactly as foundation's principalMiddleware does.
 */

import express, { type NextFunction, type Request, type Response } from 'express';
import type { AddressInfo } from 'net';
import { exportJWK, generateKeyPair, jwtVerify } from 'jose';
import { afterEach, describe, expect, it } from 'vitest';
import { problemHandler, requestContext } from '../../middleware/problem';
import type { Principal } from '../../types';
import { createAssistantRouter } from './assistant';
import { createCatalogRouter } from './catalog';
import {
  type CommerceDomainClient, type DomainResult, DOMAIN_AUDIENCE, createCommerceOpsRouter, createCommerceRouter,
  createCommerceWebhookRouter,
  createHttpCommerceDomainClient, principalClaim, WEBHOOK_HEADER,
} from './commerce';
import { createDelegationsRouter } from './delegations';
import { createProvidersRouter } from './providers';

const MEMBER: Principal = {
  memberId: '2ad9041e-561e-527b-aa0d-5a7fda5f710b', subject: '2ad9041e-561e-527b-aa0d-5a7fda5f710b',
  sessionId: 'a1b2c3d4e5f60718', clientId: null, scopes: ['profile:read', 'profile:write', 'privacy:manage'],
  assuranceLevel: 'simulated', environment: 'development', delegationId: null, identityProvider: 'dev',
  expiresAt: new Date('2026-10-24T00:00:00Z'), via: 'session',
};
const AGENT: Principal = {
  ...MEMBER, subject: 'sub-agent', sessionId: null, clientId: 'client-fictional-shopping-agent',
  scopes: ['commerce:research', 'commerce:cart'], assuranceLevel: 'aal1', identityProvider: 'oidc', via: 'bearer',
};
const KEY = 'idem-key-0000000001';
const q = '6f1c2a0e-6c38-4d43-9a4e-6e0b9a1d2c11';

function fakeClient(reply: DomainResult = { status: 200, body: { ok: true } }) {
  const calls: Array<{ op: string; principal: Principal; body: unknown; idem?: string; ifMatch?: string; rid?: string }> = [];
  const client: CommerceDomainClient = {
    async call(op, principal, body, options) {
      calls.push({ op, principal, body, idem: options?.idempotencyKey, ifMatch: options?.ifMatch, rid: options?.requestId });
      return reply;
    },
    async webhook() {
      return { status: 200, body: { received: true } };
    },
  };
  return { client, calls };
}

let server: ReturnType<express.Express['listen']> | undefined;
afterEach(() => server?.close());

async function app(principal: Principal | null, mount: (a: express.Express, c: CommerceDomainClient) => void,
                   reply?: DomainResult, json = true) {
  const { client, calls } = fakeClient(reply);
  const a = express();
  a.use(requestContext('development'));
  if (json) a.use(express.json());
  a.use((_req: Request, res: Response, next: NextFunction) => {
    if (principal) res.locals.principal = principal;
    next();
  });
  mount(a, client);
  a.use(problemHandler);
  server = a.listen(0);
  const port = (server.address() as AddressInfo).port;
  const call = (method: string, path: string, body?: unknown, headers: Record<string, string> = {}) =>
    fetch(`http://127.0.0.1:${port}${path}`, {
      method, headers: { 'content-type': 'application/json', ...headers }, body: body ? JSON.stringify(body) : undefined,
    });
  return { call, calls };
}

const commerce = (a: express.Express, c: CommerceDomainClient) => a.use('/commerce', createCommerceRouter(c));
const purchase = { quote_id: q, approval_id: q, delegation_id: null };

describe('commerce router', () => {
  it('rejects identity fields and the approved flag (BM-COM-002/006)', async () => {
    const { call, calls } = await app(MEMBER, commerce);
    for (const extra of [{ user_id: 'x' }, { approved: true }, { member_id: 'x' }]) {
      const r = await call('POST', '/commerce/purchases', { ...purchase, ...extra }, { 'Idempotency-Key': KEY });
      expect(r.status).toBe(400);
      expect(r.headers.get('content-type')).toContain('application/problem+json');
      expect((await r.json()).code).toBe('identity_argument_rejected');
    }
    expect(calls).toHaveLength(0);
  });

  it('requires a 16-128 character Idempotency-Key', async () => {
    const m = await app(MEMBER, commerce);
    expect((await m.call('POST', '/commerce/purchases', purchase)).status).toBe(400);
    expect((await m.call('POST', '/commerce/purchases', purchase, { 'Idempotency-Key': 'short-key' })).status).toBe(400);
    expect(m.calls).toHaveLength(0);
  });

  it('gates agents on commerce scopes; the member session acts with its own authority', async () => {
    const a = await app(AGENT, commerce);
    const r = await a.call('POST', '/commerce/purchases', { ...purchase, delegation_id: q }, { 'Idempotency-Key': KEY });
    expect(r.status).toBe(403);
    expect(r.headers.get('www-authenticate')).toContain('insufficient_scope');
    expect(a.calls).toHaveLength(0);
    server?.close();
    const m = await app(MEMBER, commerce); // profile scopes only, like every foundation session
    const ok = await m.call('POST', '/commerce/purchases', purchase, { 'Idempotency-Key': KEY });
    expect(ok.status).toBe(200);
    expect(m.calls[0]).toMatchObject({ op: 'purchase.execute', principal: MEMBER, idem: KEY, body: purchase });
    expect(ok.headers.get('cache-control')).toBe('private, no-store');
  });

  it('returns need purchase authority from agents', async () => {
    const a = await app(AGENT, commerce); // research + cart only
    const r = await a.call('POST', `/commerce/orders/${q}/returns`, { source_variant_ref: 'demo-overshirt-m', quantity: 1 },
      { 'Idempotency-Key': KEY });
    expect(r.status).toBe(403);
    expect(a.calls).toHaveLength(0);
  });

  it('only the first-party session can open challenges and create approvals', async () => {
    const body = { operation_id: q, challenge_id: q, nonce: 'n'.repeat(32), displayed_quote_hash: 'sha256:' + '0'.repeat(64) };
    const a = await app(AGENT, commerce);
    const r = await a.call('POST', '/commerce/approvals', body);
    expect(r.status).toBe(403);
    expect((await r.json()).code).toBe('not_trusted_surface');
    expect((await a.call('POST', `/commerce/operations/${q}/approval-challenge`)).status).toBe(403);
    server?.close();
    const delegatedSession = await app({ ...MEMBER, delegationId: q }, commerce);
    expect((await delegatedSession.call('POST', '/commerce/approvals', body)).status).toBe(403);
    server?.close();
    const m = await app(MEMBER, commerce, { status: 201, body: { id: q } });
    expect((await m.call('POST', '/commerce/approvals', body)).status).toBe(201);
    expect(m.calls[0].op).toBe('approval.create');
  });

  it('maps domain problems onto foundation problem+json, keeping code and extras', async () => {
    const m = await app(MEMBER, commerce, {
      status: 409, body: { type: 'x', status: 409, code: 'revision_conflict', title: 'revision conflict', detail: 'cart changed', current_version: '3' },
    });
    const r = await m.call('PATCH', `/commerce/carts/${q}`, { lines: [{ variant_id: q, source_variant_ref: 'demo-overshirt-m', quantity: 1 }] },
      { 'If-Match': '"2"' });
    expect(r.status).toBe(409);
    const p = await r.json();
    expect(p).toMatchObject({ code: 'revision_conflict', detail: 'cart changed', current_version: '3', status: 409 });
    expect(p.request_id).toBeTruthy();
    expect(m.calls[0].ifMatch).toBe('"2"');
  });

  it('a refused gateway assertion surfaces as 503, never as the caller being unauthenticated', async () => {
    const m = await app(MEMBER, commerce, { status: 401, body: { code: 'invalid_token' } });
    const r = await m.call('POST', `/commerce/carts/${q}/quote`);
    expect(r.status).toBe(503);
    expect((await r.json()).code).toBe('dependency_unavailable');
  });

  it('cart edits need If-Match; ETag passes through', async () => {
    const m = await app(MEMBER, commerce, { status: 200, body: { id: q, revision: '2' }, headers: { etag: '"2"' } });
    const lines = [{ variant_id: q, source_variant_ref: 'demo-overshirt-m', quantity: 1 }];
    expect((await m.call('PATCH', `/commerce/carts/${q}`, { lines })).status).toBe(428);
    const ok = await m.call('PATCH', `/commerce/carts/${q}`, { lines }, { 'If-Match': '"1"' });
    expect(ok.status).toBe(200);
    expect(ok.headers.get('etag')).toBe('"2"');
  });

  it('unauthenticated requests get 401', async () => {
    const m = await app(null, commerce);
    expect((await m.call('POST', `/commerce/carts/${q}/quote`)).status).toBe(401);
  });
});

describe('delegations, providers, catalog, assistant', () => {
  it('agents cannot list or create grants; autonomous purchase cannot be requested', async () => {
    const mount = (a: express.Express, c: CommerceDomainClient) => a.use('/delegations', createDelegationsRouter(c));
    const a = await app(AGENT, mount);
    expect((await a.call('GET', '/delegations')).status).toBe(403);
    expect((await a.call('POST', '/delegations', {}, { 'Idempotency-Key': KEY })).status).toBe(403);
    server?.close();
    const m = await app(MEMBER, mount);
    const r = await m.call('POST', '/delegations', {
      client_id: 'agent', mode: 'buy_within_rules', allowed_providers: ['demo_atelier'], expires_at: '2026-10-12T12:00:00Z',
      limits: { currency: 'USD', max_per_order: { amount_minor: '20000', currency: 'USD' },
        max_cumulative: { amount_minor: '30000', currency: 'USD' }, window_seconds: 86400,
        allowed_merchants: ['fictional-demo-merchant'], require_final_human_approval: false },
    }, { 'Idempotency-Key': KEY });
    expect(r.status).toBe(422);
    expect(m.calls).toHaveLength(0);
  });

  it('provider console requires provider:admin for everyone and refuses raw secrets', async () => {
    const mount = (a: express.Express, c: CommerceDomainClient) => a.use('/providers', createProvidersRouter(c));
    const m = await app({ ...MEMBER, scopes: [...MEMBER.scopes] }, mount);
    expect((await m.call('GET', '/providers')).status).toBe(403); // a member session is not an operator
    server?.close();
    const op = await app({ ...AGENT, clientId: 'ops-console', scopes: ['provider:admin'] }, mount);
    const bad = await op.call('PATCH', '/providers/nordstrom_impact/setup', { credential_secret_ref: 'sk_live_raw_value' });
    expect(bad.status).toBe(422);
    const ok = await op.call('PATCH', '/providers/nordstrom_impact/setup',
      { credential_secret_ref: 'projects/p/secrets/impact/versions/1' });
    expect(ok.status).toBe(200);
    expect(op.calls[0]).toMatchObject({ op: 'provider.setup.update', body: { provider_id: 'nordstrom_impact' } });
  });

  it('operations queue needs the commerce:operator role, even for a member session', async () => {
    const mount = (a: express.Express, c: CommerceDomainClient) => a.use('/ops', createCommerceOpsRouter(c));
    const m = await app(MEMBER, mount);
    expect((await m.call('GET', '/ops/queue')).status).toBe(403);
    server?.close();
    const op = await app({ ...AGENT, clientId: 'ops-console', scopes: ['commerce:operator'] }, mount);
    expect((await op.call('GET', '/ops/queue')).status).toBe(200);
    expect(op.calls[0].op).toBe('commerce.ops.queue');
  });

  it('catalog search validates the query and forwards it', async () => {
    const mount = (a: express.Express, c: CommerceDomainClient) => a.use('/catalog', createCatalogRouter(c));
    const m = await app(AGENT, mount);
    expect((await m.call('GET', '/catalog/search')).status).toBe(422);
    expect((await m.call('GET', '/catalog/search?q=linen&limit=5')).status).toBe(200);
    expect(m.calls[0]).toMatchObject({ op: 'catalog.search', body: { q: 'linen', limit: 5 } });
  });

  it('assistant events stream as SSE without model reasoning', async () => {
    const mount = (a: express.Express, c: CommerceDomainClient) => a.use('/assistant', createAssistantRouter(c));
    const m = await app(MEMBER, mount, { status: 200, body: { events: [{ seq: 1, type: 'goal', data: { goal: 'linen' } }] } });
    const r = await m.call('GET', `/assistant/tasks/${q}/events`);
    expect(r.headers.get('content-type')).toContain('text/event-stream');
    expect(await r.text()).toBe('id: 1\nevent: goal\ndata: {"goal":"linen"}\n\n');
  });

  it('webhook relay needs the raw body', async () => {
    const mount = (a: express.Express, c: CommerceDomainClient) =>
      a.use('/webhooks', express.raw({ type: '*/*' }), createCommerceWebhookRouter(c));
    const parsed = await app(null, mount); // a JSON parser ran first: the signed bytes are gone
    expect((await parsed.call('POST', '/webhooks/demo_atelier', { any: 'json' })).status).toBe(422);
    server?.close();
    const raw = await app(null, mount, undefined, false);
    expect((await raw.call('POST', '/webhooks/demo_atelier', { any: 'json' })).status).toBe(202);
  });
});

describe('webhook relay headers', () => {
  it('relays signature and timestamp headers only, never cookies or authorization', () => {
    for (const h of ['content-type', 'stripe-signature', 'x-demo-signature', 'x-demo-timestamp', 'webhook-id',
      'webhook-signature', 'x-impact-event-id']) expect(WEBHOOK_HEADER.test(h)).toBe(true);
    for (const h of ['cookie', 'authorization', 'x-forwarded-for', 'x-real-ip', 'x-csrf-token', 'host',
      'x-api-key', 'x-signature-bypass']) expect(WEBHOOK_HEADER.test(h)).toBe(false);
  });
});

describe('request correlation', () => {
  it('forwards the gateway request id so domain events and audit records correlate on it', async () => {
    const rid = '0b7c3f2e-9d41-4e6a-8f15-2c9a4d7e1b33';
    const { call, calls } = await app(MEMBER, commerce);
    const res = await call('GET', `/commerce/operations/${q}`, undefined, { 'X-Request-Id': rid });
    expect(res.status).toBe(200);
    expect(calls[0].rid).toBe(rid);
    const { privateKey } = await generateKeyPair('ES256');
    let sent: Record<string, string> = {};
    const fetchImpl = (async (_url: string, init: RequestInit) => {
      sent = init.headers as Record<string, string>;
      return new Response('{}', { status: 200 });
    }) as unknown as typeof fetch;
    const client = createHttpCommerceDomainClient({ baseUrl: 'http://c', issuer: 'gw', kid: 'k', privateKey, fetchImpl });
    await client.call('operation.get', MEMBER, { operation_id: q }, { requestId: rid });
    expect(sent['x-request-id']).toBe(rid);
  });
});

describe('HTTP domain client', () => {
  it('signs a short-lived ES256 assertion for the commerce domain audience', async () => {
    const { privateKey, publicKey } = await generateKeyPair('ES256');
    const seen: Array<{ url: string; init: RequestInit }> = [];
    const fetchImpl = (async (url: string, init: RequestInit) => {
      seen.push({ url, init });
      return new Response(JSON.stringify({ id: q, revision: '1' }), { status: 201, headers: { etag: '"1"' } });
    }) as unknown as typeof fetch;
    const client = createHttpCommerceDomainClient({ baseUrl: 'http://commerce.internal/', issuer: 'gw', kid: 'gw-1', privateKey, fetchImpl });
    const res = await client.call('cart.create', MEMBER, { provider_id: 'demo_atelier' }, { idempotencyKey: KEY });
    expect(res).toMatchObject({ status: 201, headers: { etag: '"1"' } });
    expect(seen[0].url).toBe('http://commerce.internal/internal/commerce/v1/cart.create');
    const headers = seen[0].init.headers as Record<string, string>;
    expect(headers['idempotency-key']).toBe(KEY);
    const token = headers.authorization.slice('Bearer '.length);
    const { payload, protectedHeader } = await jwtVerify(token, publicKey, { issuer: 'gw', audience: DOMAIN_AUDIENCE });
    expect(protectedHeader).toMatchObject({ alg: 'ES256', kid: 'gw-1' });
    expect((payload.exp ?? 0) - (payload.iat ?? 0)).toBeLessThanOrEqual(60);
    expect(payload.jti).toBeTruthy();
    expect(payload.principal).toEqual(principalClaim(MEMBER));
    expect(JSON.stringify(await exportJWK(publicKey))).not.toContain('"d"');
  });

  it('a bearer principal never carries a session; webhooks carry no principal', async () => {
    expect(principalClaim({ ...AGENT, sessionId: 'leaked' }).session_id).toBeNull();
    const { privateKey, publicKey } = await generateKeyPair('ES256');
    let captured: { body: string; auth: string } | undefined;
    const fetchImpl = (async (_url: string, init: RequestInit) => {
      captured = { body: String(init.body), auth: (init.headers as Record<string, string>).authorization };
      return new Response('{"received":true}', { status: 200 });
    }) as unknown as typeof fetch;
    const client = createHttpCommerceDomainClient({ baseUrl: 'http://c', issuer: 'gw', kid: 'k', privateKey, fetchImpl });
    await client.webhook('demo_atelier', { 'x-signature': 's' }, Buffer.from('raw-bytes'));
    const { payload } = await jwtVerify(captured!.auth.slice(7), publicKey, { audience: DOMAIN_AUDIENCE });
    expect(payload.principal).toBeNull();
    expect(JSON.parse(captured!.body)).toEqual({ headers: { 'x-signature': 's' }, body_b64: Buffer.from('raw-bytes').toString('base64') });
    expect((await client.webhook('../escape', {}, Buffer.from(''))).status).toBe(404);
  });

  it('a transport failure is a retryable 503, not a guess about the outcome', async () => {
    const { privateKey } = await generateKeyPair('ES256');
    const fetchImpl = (async () => { throw new Error('socket hang up'); }) as unknown as typeof fetch;
    const client = createHttpCommerceDomainClient({ baseUrl: 'http://c', issuer: 'gw', kid: 'k', privateKey, fetchImpl });
    await expect(client.call('purchase.execute', MEMBER, purchase, { idempotencyKey: KEY })).rejects.toMatchObject({
      status: 503, code: 'dependency_unavailable', retryable: true,
    });
  });
});
