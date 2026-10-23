/**
 * Router boundary tests for the unmounted commerce routers (lane: opus-commerce-agents).
 * A fake domain client records forwarded operations; no domain logic runs here.
 */

import express, { NextFunction, Response } from 'express';
import { AddressInfo } from 'net';
import { afterEach, describe, expect, it } from 'vitest';
import { createCommerceRouter, CommerceDomainClient, Principal, PrincipalRequest } from './commerce';
import { createDelegationsRouter } from './delegations';
import { createProvidersRouter } from './providers';

const MEMBER: Principal = {
  memberId: '2ad9041e-561e-527b-aa0d-5a7fda5f710b', subject: 's', issuer: 'https://idp.example.invalid',
  clientId: 'brandme-web', scopes: ['commerce:research', 'commerce:cart', 'commerce:purchase'],
  assuranceLevel: 'aal2', environment: 'development', sessionId: 'sess', delegationId: null, firstPartySession: true,
};
const AGENT: Principal = {
  ...MEMBER, clientId: 'agent', scopes: ['commerce:research', 'commerce:cart'], assuranceLevel: 'aal1',
  sessionId: null, delegationId: '11111111-1111-4111-8111-111111111111', firstPartySession: false,
};

function fakeClient() {
  const calls: Array<{ op: string; principal: Principal | null; body: unknown; idem?: string }> = [];
  const client: CommerceDomainClient = {
    async call(op, principal, body, options) {
      calls.push({ op, principal, body, idem: options?.idempotencyKey });
      return { status: 200, body: { ok: true } };
    },
  };
  return { client, calls };
}

let server: ReturnType<express.Express['listen']> | undefined;
afterEach(() => server?.close());

async function app(principal: Principal | null, mount: (a: express.Express, c: CommerceDomainClient) => void) {
  const { client, calls } = fakeClient();
  const a = express();
  a.use(express.json());
  a.use((req: PrincipalRequest, _res: Response, next: NextFunction) => {
    if (principal) req.principal = principal;
    next();
  });
  mount(a, client);
  server = a.listen(0);
  const port = (server.address() as AddressInfo).port;
  const call = (method: string, path: string, body?: unknown, headers: Record<string, string> = {}) =>
    fetch(`http://127.0.0.1:${port}${path}`, {
      method, headers: { 'content-type': 'application/json', ...headers }, body: body ? JSON.stringify(body) : undefined,
    });
  return { call, calls };
}

const commerce = (a: express.Express, c: CommerceDomainClient) => a.use('/commerce', createCommerceRouter(c));
const q = '6f1c2a0e-6c38-4d43-9a4e-6e0b9a1d2c11';

describe('commerce router', () => {
  it('rejects identity fields and the approved flag (BM-COM-002/006)', async () => {
    const { call, calls } = await app(MEMBER, commerce);
    for (const extra of [{ user_id: 'x' }, { approved: true }]) {
      const r = await call('POST', '/commerce/purchases', { quote_id: q, approval_id: q, delegation_id: null, ...extra },
        { 'Idempotency-Key': 'key-12345678' });
      expect(r.status).toBe(400);
      expect(r.headers.get('content-type')).toContain('application/problem+json');
    }
    expect(calls).toHaveLength(0);
  });

  it('requires an Idempotency-Key and the purchase scope', async () => {
    const m = await app(MEMBER, commerce);
    expect((await m.call('POST', '/commerce/purchases', { quote_id: q, approval_id: q, delegation_id: null })).status).toBe(400);
    server?.close();
    const a = await app(AGENT, commerce);
    const r = await a.call('POST', '/commerce/purchases', { quote_id: q, approval_id: q, delegation_id: AGENT.delegationId },
      { 'Idempotency-Key': 'key-12345678' });
    expect(r.status).toBe(403);
    expect(r.headers.get('www-authenticate')).toContain('insufficient_scope');
    expect(a.calls).toHaveLength(0);
  });

  it('only the first-party trusted surface can create approvals', async () => {
    const a = await app(AGENT, commerce);
    const body = { operation_id: q, challenge_id: q, nonce: 'n'.repeat(32), displayed_quote_hash: 'sha256:' + '0'.repeat(64) };
    expect((await a.call('POST', '/commerce/approvals', body)).status).toBe(403);
    server?.close();
    const m = await app(MEMBER, commerce);
    expect((await m.call('POST', '/commerce/approvals', body)).status).toBe(200);
    expect(m.calls[0].op).toBe('approval.create');
  });

  it('forwards the authenticated principal, never a body identity', async () => {
    const m = await app(MEMBER, commerce);
    const r = await m.call('POST', '/commerce/purchases', { quote_id: q, approval_id: q, delegation_id: null },
      { 'Idempotency-Key': 'key-12345678' });
    expect(r.status).toBe(200);
    expect(m.calls[0]).toMatchObject({ op: 'purchase.execute', principal: MEMBER, idem: 'key-12345678' });
    expect(r.headers.get('cache-control')).toBe('private, no-store');
  });

  it('rejects a delegation id that differs from the principal', async () => {
    const m = await app(MEMBER, commerce);
    const r = await m.call('POST', '/commerce/purchases', { quote_id: q, approval_id: q, delegation_id: q },
      { 'Idempotency-Key': 'key-12345678' });
    expect(r.status).toBe(403);
  });

  it('unauthenticated requests get 401', async () => {
    const m = await app(null, commerce);
    expect((await m.call('POST', '/commerce/carts/' + q + '/quote')).status).toBe(401);
  });
});

describe('delegations and providers', () => {
  it('agents cannot create grants; autonomous purchase cannot be requested', async () => {
    const mount = (a: express.Express, c: CommerceDomainClient) => a.use('/delegations', createDelegationsRouter(c));
    const a = await app(AGENT, mount);
    expect((await a.call('POST', '/delegations', {})).status).toBe(403);
    server?.close();
    const m = await app(MEMBER, mount);
    const r = await m.call('POST', '/delegations', {
      client_id: 'agent', mode: 'buy_within_rules', allowed_providers: ['demo_atelier'], expires_at: '2026-10-12T12:00:00Z',
      limits: { currency: 'USD', max_per_order: { amount_minor: '20000', currency: 'USD' },
        max_cumulative: { amount_minor: '30000', currency: 'USD' }, window_seconds: 86400,
        allowed_merchants: ['fictional-demo-merchant'], require_final_human_approval: false },
    });
    expect(r.status).toBe(400);
  });

  it('provider console requires provider:admin and refuses raw secrets', async () => {
    const mount = (a: express.Express, c: CommerceDomainClient) => a.use('/providers', createProvidersRouter(c));
    const m = await app(MEMBER, mount);
    expect((await m.call('GET', '/providers')).status).toBe(403);
    server?.close();
    const op = await app({ ...MEMBER, scopes: ['provider:admin'] }, mount);
    const bad = await op.call('PATCH', '/providers/nordstrom_impact/setup', { credential_secret_ref: 'sk_live_raw_value' });
    expect(bad.status).toBe(400);
    const ok = await op.call('PATCH', '/providers/nordstrom_impact/setup',
      { credential_secret_ref: 'projects/p/secrets/impact/versions/1' });
    expect(ok.status).toBe(200);
  });
});
