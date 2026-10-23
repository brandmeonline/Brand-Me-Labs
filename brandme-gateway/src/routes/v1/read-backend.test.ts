/** Signed OIDC → mounted gateway → real Python HTTP process → Spanner. */
import { execFileSync, spawn, type ChildProcess } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { createConnection, createServer } from 'node:net';
import { resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import request from 'supertest';
import { SignJWT, createLocalJWKSet, exportJWK, generateKeyPair, type KeyLike } from 'jose';
import { createApp } from '../../index';
import { loadConfig } from '../../config';
import { IdentityStore } from '../../middleware/identity/store';

const root = resolve(__dirname, '../../../..');
const python = process.env.BRANDME_PYTHON ?? 'python3';
const emulator = process.env.SPANNER_EMULATOR_HOST ?? 'localhost:9010';
const up = await new Promise<boolean>((done) => {
  const [host, port] = emulator.split(':');
  const s = createConnection({ host, port: Number(port) }, () => { s.end(); done(true); });
  s.on('error', () => done(false)); s.setTimeout(1000, () => { s.destroy(); done(false); });
});

describe.skipIf(!up)('gateway and running rights read backend', () => {
  let backend: ChildProcess | undefined;
  let app: ReturnType<typeof createApp>;
  let privateKey: KeyLike;
  let store: IdentityStore;
  let logs = '';
  const member = '11111111-1111-4111-8111-111111111111';
  const other = '22222222-2222-4222-8222-222222222222';
  const rightsToken = 'test-rights-service-32-characters';
  const privacyToken = 'test-privacy-service-32-characters';
  const issuer = 'https://read-api-identity.example';
  const signed = (sub = 'owner', scope = 'rights:read privacy:manage', recent = false) => new SignJWT({ sub, scope,
    ...(recent ? { auth_time: Math.floor(Date.now() / 1000) } : {}) })
    .setProtectedHeader({ alg: 'RS256', kid: 'read-api' }).setIssuer(issuer).setAudience('gateway')
    .setIssuedAt().setExpirationTime('5m').sign(privateKey);

  beforeAll(async () => {
    const port = await new Promise<number>((done) => {
      const s = createServer().listen(0, '127.0.0.1', () => {
        const port = (s.address() as { port: number }).port; s.close(() => done(port));
      });
    });
    const env = { ...process.env, BRANDME_MODE: 'development', ENVIRONMENT: 'development', PYTHONPATH: root,
      SPANNER_EMULATOR_HOST: emulator, SPANNER_PROJECT_ID: 'test-project', SPANNER_INSTANCE_ID: 'gateway-read-tests',
      SPANNER_DATABASE_ID: `read-${randomUUID().slice(0, 8)}`, READ_API_NETWORK: 'preprod', READ_API_CONTRACT_ADDRESS: 'ab'.repeat(32),
      RIGHTS_SERVICE_TOKEN: rightsToken, PRIVACY_SERVICE_TOKEN: privacyToken, PORT: String(port) };
    execFileSync(python, [resolve(root, 'tests/fixtures/seed_read_api.py')], { cwd: root, env, stdio: 'pipe', timeout: 120_000 });
    store = new IdentityStore({ projectId: env.SPANNER_PROJECT_ID, instanceId: env.SPANNER_INSTANCE_ID,
      databaseId: env.SPANNER_DATABASE_ID, mode: 'development' });
    backend = spawn(python, ['-m', 'brandme_core.read_api'], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
    backend.stdout?.on('data', (b) => { logs += b; }); backend.stderr?.on('data', (b) => { logs += b; });
    const base = `http://127.0.0.1:${port}`;
    let ready = false;
    const deadline = Date.now() + 20_000;
    while (Date.now() < deadline) {
      try { ready = (await fetch(`${base}/health`, { signal: AbortSignal.timeout(1000) })).ok; } catch { /* startup */ }
      if (ready || backend.exitCode !== null) break;
      await new Promise((done) => setTimeout(done, 100));
    }
    expect(ready, 'Python service readiness').toBe(true);
    const pair = await generateKeyPair('RS256'); privateKey = pair.privateKey;
    const jwks = createLocalJWKSet({ keys: [{ ...(await exportJWK(pair.publicKey)), kid: 'read-api', alg: 'RS256' }] });
    // JWT verification is real; only the external subject-to-member lookup is
    // fixed here. IdentityStore's own real-Spanner tests cover that mapping.
    const identities = { resolveMember: async (_issuer: string, subject: string) => ({ memberId: subject === 'owner' ? member : other }) } as IdentityStore;
    const cfg = loadConfig({ ...env, IDENTITY_PROVIDER: 'oidc', OIDC_ISSUER: issuer, OIDC_AUDIENCE: 'gateway',
      RIGHTS_SERVICE_URL: `${base}/rights`, PRIVACY_SERVICE_URL: `${base}/privacy`, CHAIN_SERVICE_URL: 'http://chain.test' });
    const fetchImpl: typeof fetch = (input, init) => String(input).startsWith('http://chain.test/')
      ? Promise.resolve(Response.json({ status: 'unavailable', network: 'preprod', reasons: ['test has no funded wallet'] }))
      : fetch(input, init);
    app = createApp(cfg, identities, { jwks, fetchImpl });
  });

  afterAll(async () => {
    if (backend && backend.exitCode === null) {
      await new Promise<void>((done) => { backend!.once('exit', () => done()); backend!.kill('SIGTERM'); });
    }
    if (store) { await store.database.delete(); await store.close(); }
    expect(logs).not.toContain(rightsToken); expect(logs).not.toContain(privacyToken); expect(logs).not.toContain(member);
  });

  it('returns only the verified member’s persisted entitlements with honest capability labels', async () => {
    const owner = await request(app).get('/api/v1/rights/entitlements?limit=1').auth(await signed(), { type: 'bearer' })
      .set('x-subject-ref', other);
    expect(owner.status).toBe(200);
    expect(owner.body).toMatchObject({ network: 'preprod', badge: 'Preprod test network', capability: 'unavailable',
      items: [{ entitlement_id: 'cd'.repeat(32), epoch: '1' }], next_cursor: null });
    const stranger = await request(app).get('/api/v1/rights/entitlements').auth(await signed('other'), { type: 'bearer' })
      .set('x-subject-ref', member);
    expect(stranger.status).toBe(200); expect(stranger.body.items).toEqual([]);
    expect((await request(app).get('/api/v1/rights/entitlements').auth('invalid', { type: 'bearer' })).status).toBe(401);
    const missing = await request(app).get('/api/v1/rights/reprint-jobs/44444444-4444-4444-8444-444444444444')
      .auth(await signed('owner', 'rights:reprint'), { type: 'bearer' });
    expect(missing.status).toBe(404); expect(missing.body.code).toBe('not_found');
    expect(missing.headers['content-type']).toMatch(/application\/problem\+json/);
  });

  it('reads partial My Data coverage and refuses unimplemented export/deletion commands', async () => {
    const bearer = await signed('owner', 'privacy:manage', true);
    const r = await request(app).get('/api/v1/me/data').auth(bearer, { type: 'bearer' });
    expect(r.status).toBe(200); expect(r.body.coverage).toEqual({ domains: ['rights'], full_account: false });
    for (const path of ['/api/v1/me/exports', '/api/v1/me/deletion']) {
      const r = await request(app).post(path).auth(bearer, { type: 'bearer' })
        .send(path.endsWith('/deletion') ? { scope: 'account', confirm: true } : {});
      expect(r.status).toBe(503); expect(r.body.code).toBe('dependency_unavailable');
    }
  });
});
