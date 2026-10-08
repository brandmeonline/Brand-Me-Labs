/**
 * Unmounted v1 rights/privacy routers, exercised in an isolated test app with
 * injected auth and upstream fakes.
 */
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import express from 'express';
import type { AddressInfo } from 'node:net';
import type { Server } from 'node:http';
import { createChainRouter, type V1Deps, type UpstreamClient } from './chain';
import { createOwnershipRouter } from './ownership';
import { createAssetsRouter } from './assets';
import { createRightsRouter } from './rights';
import { createPrivacyRouter } from './privacy';

let capability: unknown = { status: 'available', reasons: [], badge: 'Preprod test network', network: 'preprod' };
const calls: { path: string; body?: unknown; headers?: Record<string, string> }[] = [];

const fake = (name: string): UpstreamClient => ({
  async get(path, headers) {
    calls.push({ path: `${name}:${path}`, headers });
    if (name === 'chain' && path === '/midnight/capability') return { status: 200, body: capability };
    return { status: 200, body: { ok: true } };
  },
  async post(path, body, headers) {
    calls.push({ path: `${name}:${path}`, body, headers });
    return { status: path === '/challenges' ? 201 : 202, body: { accepted: true } };
  },
});

const deps: V1Deps = {
  requireScope: (scope) => (req, res, next) => {
    const scopes = String(req.header('x-test-scopes') ?? '').split(',');
    if (!scopes.includes(scope)) { res.status(403).json({ error: 'insufficient_scope', scope }); return; }
    next();
  },
  requireRecentAuth: (max) => (req, res, next) => {
    const t = Number(req.header('x-test-auth-age') ?? 99999);
    if (t > max) { res.status(401).json({ error: 'reauth_required' }); return; }
    next();
  },
  subjectOf: (req) => req.header('x-test-subject') ?? undefined,
  authTimeOf: () => new Date(),
  upstream: { chain: fake('chain'), rights: fake('rights'), privacy: fake('privacy') },
};

let server: Server;
let base = '';
beforeAll(async () => {
  const app = express();
  app.use(express.json());
  app.use('/v1/chain', createChainRouter(deps));
  app.use('/v1/ownership', createOwnershipRouter(deps));
  app.use('/v1/assets', createAssetsRouter(deps));
  app.use('/v1/rights', createRightsRouter(deps));
  app.use('/v1/me', createPrivacyRouter(deps));
  server = app.listen(0);
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
afterAll(() => server.close());

const req = (method: string, path: string, body?: unknown, headers: Record<string, string> = {}) =>
  fetch(base + path, { method, headers: { 'content-type': 'application/json', ...headers }, body: body ? JSON.stringify(body) : undefined });
const member = (scopes: string, extra: Record<string, string> = {}) => ({ 'x-test-subject': 'member-1', 'x-test-scopes': scopes, ...extra });
const ASSET = '6f1c2a3e-1111-4222-8333-944455556666';

describe('v1 rights/privacy routers (unmounted)', () => {
  it('transfer is refused with 503 + reasons when Midnight capability is not available (no pretend success)', async () => {
    capability = { status: 'unavailable', reasons: ['no rights contract deployed/configured for this network'], badge: 'Preprod test network', network: 'preprod' };
    const r = await req('POST', `/v1/assets/${ASSET}/transfers`, { rights_scope: ['transfer'], recipient_invite: 'invite-abc123', expires_in_seconds: 3600 },
      member('rights:transfer', { 'idempotency-key': 'idem-123456' }));
    expect(r.status).toBe(503);
    const b = await r.json();
    expect(b.reasons[0]).toMatch(/no rights contract/);
    capability = { status: 'available', reasons: [], badge: 'Preprod test network', network: 'preprod' };
  });

  it('chain service unreachable → capability unavailable', async () => {
    const saved = deps.upstream.chain.get;
    deps.upstream.chain.get = async () => { throw new Error('ECONNREFUSED'); };
    const r = await req('GET', '/v1/chain/capability');
    expect((await r.json()).status).toBe('unavailable');
    deps.upstream.chain.get = saved;
  });

  it('enforces scopes and idempotency keys', async () => {
    const body = { rights_scope: ['transfer'], recipient_invite: 'invite-abc123', expires_in_seconds: 3600 };
    expect((await req('POST', `/v1/assets/${ASSET}/transfers`, body, member('rights:read'))).status).toBe(403);
    expect((await req('POST', `/v1/assets/${ASSET}/transfers`, body, member('rights:transfer'))).status).toBe(400);
    const ok = await req('POST', `/v1/assets/${ASSET}/transfers`, body, member('rights:transfer', { 'idempotency-key': 'idem-123456' }));
    expect(ok.status).toBe(202);
    expect(calls.at(-1)!.body).toMatchObject({ network: 'preprod' });
    expect(calls.at(-1)!.headers).toMatchObject({ 'x-subject-ref': 'member-1', 'idempotency-key': 'idem-123456' });
  });

  it('rejects unknown fields and malformed ids', async () => {
    expect((await req('POST', `/v1/assets/${ASSET}/transfers`, { rights_scope: ['transfer'], recipient_invite: 'invite-abc123', expires_in_seconds: 3600, email: 'x@y.z' },
      member('rights:transfer', { 'idempotency-key': 'idem-123456' }))).status).toBe(400);
    expect((await req('GET', '/v1/assets/not-a-uuid/passport')).status).toBe(400);
    expect((await req('POST', '/v1/ownership/challenges', { entitlement_id: 'zz', audience: 'resale' }, member('rights:read'))).status).toBe(400);
  });

  it('issues a fresh 32-byte challenge per request, bound to audience and network', async () => {
    const a = await (await req('POST', '/v1/ownership/challenges', { entitlement_id: 'ab'.repeat(32), audience: 'resale-partner' }, member('rights:read'))).json();
    const b = await (await req('POST', '/v1/ownership/challenges', { entitlement_id: 'ab'.repeat(32), audience: 'resale-partner' }, member('rights:read'))).json();
    expect(a.challenge).toMatch(/^[0-9a-f]{64}$/);
    expect(a.challenge).not.toBe(b.challenge);
    expect(a).toMatchObject({ network: 'preprod', badge: 'Preprod test network', circuit: 'proveControl' });
  });

  it('a submission reported for another network is refused (no cross-network evidence)', async () => {
    const r = await req('POST', '/v1/ownership/submissions', { operation_id: '6f1c2a3e-1111-4222-8333-944455556666', tx_id: 'tx-0001234', network: 'preview' }, member('rights:transfer'));
    expect(r.status).toBe(409);
  });

  it('entitlements always carry the network badge', async () => {
    const r = await (await req('GET', '/v1/rights/entitlements', undefined, member('rights:read'))).json();
    expect(r).toMatchObject({ network: 'preprod', badge: 'Preprod test network' });
  });

  it('My Data export/deletion require privacy:manage and recent re-auth', async () => {
    expect((await req('POST', '/v1/me/exports', {}, member('rights:read'))).status).toBe(403);
    expect((await req('POST', '/v1/me/exports', {}, member('privacy:manage', { 'x-test-auth-age': '3600' }))).status).toBe(401);
    expect((await req('POST', '/v1/me/exports', {}, member('privacy:manage', { 'x-test-auth-age': '30' }))).status).toBe(202);
    expect((await req('POST', '/v1/me/deletion', { scope: 'account' }, member('privacy:manage', { 'x-test-auth-age': '30' }))).status).toBe(400); // confirm required
    expect((await req('POST', '/v1/me/deletion', { scope: 'category', confirm: true }, member('privacy:manage', { 'x-test-auth-age': '30' }))).status).toBe(400);
    const ok = await req('POST', '/v1/me/deletion', { scope: 'account', confirm: true }, member('privacy:manage', { 'x-test-auth-age': '30' }));
    expect(ok.status).toBe(202);
    expect(calls.at(-1)!.body).toMatchObject({ categories: null });
  });
});
