import { beforeAll, describe, expect, it, vi } from 'vitest';
import request from 'supertest';
import { SignJWT, createLocalJWKSet, exportJWK, generateKeyPair, type KeyLike } from 'jose';
import { createApp } from '../../index';
import { loadConfig } from '../../config';
import { IdentityStore, sha256 } from '../../middleware/identity/store';

const memberId = '11111111-1111-4111-8111-111111111111';
const jobId = '22222222-2222-4222-8222-222222222222';
const issuer = 'https://identity.example';
const token = 'test-service-credential-32-characters';
let privateKey: KeyLike;
let jwks: ReturnType<typeof createLocalJWKSet>;
beforeAll(async () => {
  const pair = await generateKeyPair('RS256'); privateKey = pair.privateKey;
  jwks = createLocalJWKSet({ keys: [{ ...(await exportJWK(pair.publicKey)), kid: 'integration', alg: 'RS256' }] });
});
const signed = (claims: Record<string, unknown>) => new SignJWT({ sub: 'external-subject', ...claims })
  .setProtectedHeader({ alg: 'RS256', kid: 'integration' }).setIssuer(issuer).setAudience('gateway')
  .setIssuedAt().setExpirationTime('5m').sign(privateKey);

function setup(options: { configured?: boolean; upstream?: (url: string) => Response | Promise<Response> } = {}) {
  const store = {
    resolveMember: vi.fn(async () => ({ memberId })),
    loadSession: vi.fn(async () => ({ member_id: memberId, identity_provider: 'oidc', assurance_level: 'aal1',
      client_id: null, csrf_hash: sha256('csrf-test'), created_at: new Date(), expires_at: new Date(Date.now() + 60000) })),
  } as unknown as IdentityStore;
  const fetchImpl = vi.fn(async (url: string | URL | Request) => options.upstream ? options.upstream(String(url)) :
    Response.json(String(url).includes('/midnight/capability')
      ? { status: 'available', network: 'preprod', reasons: [], badge: 'forged Mainnet badge' } : { items: [], job_id: jobId, network: 'preprod' }));
  const cfg = loadConfig({ BRANDME_MODE: 'development', IDENTITY_PROVIDER: 'oidc', OIDC_ISSUER: issuer, OIDC_AUDIENCE: 'gateway',
    CHAIN_SERVICE_URL: 'http://chain.internal', ...(options.configured === false ? {} : {
      RIGHTS_SERVICE_URL: 'http://rights.internal', PRIVACY_SERVICE_URL: 'http://privacy.internal', RIGHTS_SERVICE_TOKEN: token,
      PRIVACY_SERVICE_TOKEN: 'privacy-' + token, CHAIN_SERVICE_TOKEN: 'chain-' + token,
    }) });
  return { app: createApp(cfg, store, { jwks, fetchImpl: fetchImpl as typeof fetch }), fetchImpl };
}

describe('mounted rights and My Data authentication boundary', () => {
  it('mounts all five routers and requires a verified principal for private reads', async () => {
    const { app, fetchImpl } = setup();
    for (const path of ['/rights/entitlements', `/chain/operations/${jobId}`, `/rights/reprint-jobs/${jobId}`, '/me/data']) {
      expect((await request(app).get(`/api/v1${path}`).set('x-subject-ref', memberId)).status).toBe(401);
    }
    expect(fetchImpl).not.toHaveBeenCalled();
    expect((await request(app).get('/api/v1/chain/capability')).body.badge).toBe('Preprod test network');
    expect((await request(app).post('/api/v1/ownership/challenges').send({})).status).toBe(401);
    expect((await request(app).post(`/api/v1/assets/${jobId}/transfers`).send({})).status).toBe(401);
  });

  it('uses verified internal member identity and service credentials, ignoring caller subject headers', async () => {
    const { app, fetchImpl } = setup();
    const bearer = await signed({ scope: 'rights:read' });
    const response = await request(app).get('/api/v1/rights/entitlements').set({ Authorization: `Bearer ${bearer}`, 'x-subject-ref': 'victim' });
    expect(response.status).toBe(200);
    expect(response.body).toMatchObject({ network: 'preprod', badge: 'Preprod test network' });
    const call = (fetchImpl.mock.calls as unknown as [string, RequestInit][]).find(([url]) => url.includes('rights.internal'))!;
    expect(call[1].headers).toMatchObject({ 'x-subject-ref': memberId, authorization: `Bearer ${token}` });
    expect(JSON.stringify(call)).not.toContain(bearer);
    expect(call[1].redirect).toBe('error');
  });

  it('uses the dedicated chain service credential for private operation status and reconciliation', async () => {
    const { app, fetchImpl } = setup();
    const bearer = await signed({ scope: 'rights:read rights:transfer' });
    expect((await request(app).get(`/api/v1/chain/operations/${jobId}`).auth(bearer, { type: 'bearer' })).status).toBe(200);
    expect((await request(app).post('/api/v1/ownership/submissions').auth(bearer, { type: 'bearer' })
      .send({ operation_id: jobId, tx_id: 'bound-transaction-id', network: 'preprod' })).status).toBe(200);
    const calls = (fetchImpl.mock.calls as unknown as [string, RequestInit][]).filter(([url]) => url.includes('/midnight/operations'));
    expect(calls).toHaveLength(2);
    for (const [url, init] of calls) {
      expect(url).toContain('http://chain.internal/midnight/operations');
      expect(init.headers).toMatchObject({ authorization: `Bearer chain-${token}`, 'x-subject-ref': memberId });
    }
  });

  it('rejects authenticated clients without the required scope', async () => {
    const { app, fetchImpl } = setup();
    const r = await request(app).get('/api/v1/rights/entitlements').auth(await signed({ scope: 'profile:read' }), { type: 'bearer' });
    expect(r.status).toBe(403); expect(fetchImpl).not.toHaveBeenCalled();
  });

  it.each([undefined, Math.floor(Date.now() / 1000) - 601, Math.floor(Date.now() / 1000) + 60])('requires recent auth_time, not token issuance time (%s)', async (auth_time) => {
    const { app, fetchImpl } = setup();
    const r = await request(app).post('/api/v1/me/exports').auth(await signed({ scope: 'privacy:manage', auth_time }), { type: 'bearer' }).send({});
    expect(r.status).toBe(401); expect(r.body.code).toBe('reauth_required'); expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('forwards trusted recent authentication to My Data', async () => {
    const { app, fetchImpl } = setup(); const auth_time = Math.floor(Date.now() / 1000);
    const r = await request(app).post('/api/v1/me/exports').auth(await signed({ scope: 'privacy:manage', auth_time }), { type: 'bearer' }).send({});
    expect(r.status).toBe(200);
    const init = (fetchImpl.mock.calls as unknown as [string, RequestInit][])[0]![1];
    expect(JSON.parse(init.body as string).reauth_at).toBe(new Date(auth_time * 1000).toISOString());
    expect(init.headers).toMatchObject({ authorization: `Bearer privacy-${token}`, 'x-subject-ref': memberId });
  });

  it('never relabels entitlements from another network', async () => {
    const { app } = setup({ upstream: (url) => Response.json(url.includes('/capability')
      ? { status: 'available', network: 'preprod', reasons: [] } : { network: 'mainnet', items: [{ entitlement_id: 'private-record' }] }) });
    const r = await request(app).get('/api/v1/rights/entitlements').auth(await signed({ scope: 'rights:read' }), { type: 'bearer' });
    expect(r.status).toBe(503); expect(JSON.stringify(r.body)).not.toContain('private-record');
  });

  it('forwards only bounded pagination, with no caller-selected visibility', async () => {
    const { app, fetchImpl } = setup();
    const bearer = await signed({ scope: 'rights:read' });
    const cursor = 'ab'.repeat(32);
    const r = await request(app).get(`/api/v1/rights/entitlements?cursor=${cursor}&limit=1`).auth(bearer, { type: 'bearer' });
    expect(r.status).toBe(200); expect(r.headers['cache-control']).toBe('no-store');
    expect(fetchImpl.mock.calls.some(([url]) => String(url).endsWith(`/entitlements?cursor=${cursor}&limit=1`))).toBe(true);
    expect((await request(app).get(`/api/v1/assets/${jobId}/passport?cursor=${jobId}&limit=2`)).status).toBe(200);
    const before = fetchImpl.mock.calls.length;
    for (const suffix of ['limit=101', 'limit=1&limit=2', 'cursor=invalid', 'viewer=owner', 'x-subject-ref=victim']) {
      expect((await request(app).get(`/api/v1/assets/${jobId}/passport?${suffix}`)).status).toBe(400);
    }
    expect(fetchImpl.mock.calls.length).toBe(before);
  });

  it('does not fall back to the rights credential when privacy authentication is unconfigured', async () => {
    const cfg = loadConfig({ BRANDME_MODE: 'development', RIGHTS_SERVICE_TOKEN: token, PRIVACY_SERVICE_URL: 'http://privacy.internal' });
    const { rightsDependencies } = await import('../../services/rights');
    const fetchImpl = vi.fn();
    await expect(rightsDependencies(cfg, fetchImpl).upstream.privacy.get('/inventory')).rejects.toMatchObject({ status: 503 });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('applies the existing cookie CSRF boundary to newly mounted routes', async () => {
    const { app, fetchImpl } = setup();
    const r = await request(app).post('/api/v1/me/deletion').set('Cookie', 'bm_session=test-session').send({ scope: 'account', confirm: true });
    expect(r.status).toBe(403); expect(r.body.code).toBe('csrf_failed'); expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('reports unconfigured domain services as unavailable', async () => {
    const { app } = setup({ configured: false });
    const r = await request(app).get('/api/v1/me/data').auth(await signed({ scope: 'privacy:manage' }), { type: 'bearer' });
    expect(r.status).toBe(503); expect(r.body.code).toBe('dependency_unavailable');
  });

  it('handles async upstream failure without exposing internal credentials', async () => {
    const { app } = setup({ upstream: () => { throw new Error(`provider failed with ${token}`); } });
    const r = await request(app).get('/api/v1/me/data').auth(await signed({ scope: 'privacy:manage' }), { type: 'bearer' });
    expect(r.status).toBe(503); expect(JSON.stringify(r.body)).not.toContain(token);
  });

  it('redacts client-error provider bodies and returns the public Problem contract', async () => {
    const { app } = setup({ upstream: () => Response.json({ error: `private ${token}` }, { status: 404 }) });
    const r = await request(app).get(`/api/v1/me/deletion/${jobId}`).auth(await signed({ scope: 'privacy:manage' }), { type: 'bearer' });
    expect(r.status).toBe(404); expect(r.body.code).toBe('not_found');
    expect(r.headers['content-type']).toMatch(/application\/problem\+json/); expect(JSON.stringify(r.body)).not.toContain(token);
  });

  it.each([{ status: 'yes', network: 'preprod', reasons: [] }, { status: 'available', network: 'other', reasons: [] }])('fails closed on malformed chain capability', async (cap) => {
    const { app } = setup({ upstream: () => Response.json(cap) });
    expect((await request(app).get('/api/v1/chain/capability')).body.status).toBe('unavailable');
  });

  it('does not allow a Mainnet capability to enable write routes', async () => {
    const { app } = setup({ upstream: () => Response.json({ status: 'available', network: 'mainnet', reasons: [] }) });
    expect((await request(app).get('/api/v1/chain/capability')).body.status).toBe('read_only');
  });
});
