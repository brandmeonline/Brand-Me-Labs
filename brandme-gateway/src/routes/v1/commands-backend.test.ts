/** Signed OIDC → mounted gateway → real Python rights command process → Spanner. */
import { execFileSync, spawn, type ChildProcess } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { createConnection, createServer } from 'node:net';
import { resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import request from 'supertest';
import { SignJWT, createLocalJWKSet, exportJWK, generateKeyPair, type KeyLike } from 'jose';
import { createApp } from '../../index';
import { loadConfig } from '../../config';
import type { IdentityStore } from '../../middleware/identity/store';
import { sha256 } from '../../middleware/identity/store';

const root = resolve(__dirname, '../../../..');
const python = process.env.BRANDME_PYTHON ?? 'python3';
const emulator = process.env.SPANNER_EMULATOR_HOST ?? 'localhost:9010';
const up = await new Promise<boolean>((done) => {
  const [host, port] = emulator.split(':');
  const s = createConnection({ host, port: Number(port) }, () => { s.end(); done(true); });
  s.on('error', () => done(false)); s.setTimeout(1000, () => { s.destroy(); done(false); });
});

describe.skipIf(!up)('gateway and running rights command service', () => {
  let backend: ChildProcess | undefined;
  let app: ReturnType<typeof createApp>;
  let privateKey: KeyLike;
  let logs = '';
  let upstreamCalls = 0;
  const member = '11111111-1111-4111-8111-111111111111';
  const other = '22222222-2222-4222-8222-222222222222';
  const asset = '33333333-3333-4333-8333-333333333333';
  const commandToken = 'test-rights-command-32-characters';
  const invite = 'A'.repeat(43);
  const issuer = 'https://rights-command-identity.example';
  const signed = (sub = 'owner', scope = 'rights:read rights:transfer rights:reprint', recent = true) =>
    new SignJWT({ sub, scope, ...(recent ? { auth_time: Math.floor(Date.now() / 1000) } : {}) })
      .setProtectedHeader({ alg: 'RS256', kid: 'commands' }).setIssuer(issuer).setAudience('gateway')
      .setIssuedAt().setExpirationTime('5m').sign(privateKey);

  beforeAll(async () => {
    const port = await new Promise<number>((done) => {
      const s = createServer().listen(0, '127.0.0.1', () => {
        const port = (s.address() as { port: number }).port; s.close(() => done(port));
      });
    });
    const env = { ...process.env, BRANDME_MODE: 'development', ENVIRONMENT: 'development', PYTHONPATH: root,
      SPANNER_EMULATOR_HOST: emulator, SPANNER_PROJECT_ID: 'test-project', SPANNER_INSTANCE_ID: 'gateway-command-tests',
      SPANNER_DATABASE_ID: `cmd-${randomUUID().slice(0, 8)}`, RIGHTS_COMMAND_NETWORK: 'preprod',
      RIGHTS_COMMAND_CONTRACT_ADDRESS: 'ab'.repeat(32), RIGHTS_COMMAND_SERVICE_TOKEN: commandToken, PORT: String(port) };
    execFileSync(python, [resolve(root, 'tests/fixtures/seed_rights_commands.py')], { cwd: root, env, stdio: 'pipe', timeout: 120_000 });
    backend = spawn(python, ['-m', 'brandme_core.rights_commands'], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
    backend.stdout?.on('data', (b) => { logs += b; }); backend.stderr?.on('data', (b) => { logs += b; });
    const base = `http://127.0.0.1:${port}`;
    let ready = false;
    const deadline = Date.now() + 20_000;
    while (Date.now() < deadline) {
      try { ready = (await fetch(`${base}/health`, { signal: AbortSignal.timeout(1000) })).ok; } catch { /* startup */ }
      if (ready || backend.exitCode !== null) break;
      await new Promise((done) => setTimeout(done, 100));
    }
    expect(ready, 'Python command service readiness').toBe(true);
    const pair = await generateKeyPair('RS256'); privateKey = pair.privateKey;
    const jwks = createLocalJWKSet({ keys: [{ ...(await exportJWK(pair.publicKey)), kid: 'commands', alg: 'RS256' }] });
    // JWT verification is real; only the external subject-to-member lookup and the
    // cookie session row are fixed here (IdentityStore has its own Spanner tests).
    const identities = {
      resolveMember: async (_issuer: string, subject: string) => ({ memberId: subject === 'owner' ? member : other }),
      loadSession: async () => ({ member_id: member, identity_provider: 'oidc', assurance_level: 'aal1', client_id: null,
        csrf_hash: sha256('csrf-test'), created_at: new Date(), expires_at: new Date(Date.now() + 60000) }),
    } as unknown as IdentityStore;
    const cfg = loadConfig({ ...env, IDENTITY_PROVIDER: 'oidc', OIDC_ISSUER: issuer, OIDC_AUDIENCE: 'gateway',
      RIGHTS_COMMAND_SERVICE_URL: base, RIGHTS_COMMAND_SERVICE_TOKEN: commandToken, CHAIN_SERVICE_URL: 'http://chain.test' });
    // The chain capability is the only fake: a local test network that accepts commands.
    const fetchImpl: typeof fetch = (input, init) => {
      if (String(input).startsWith('http://chain.test/')) return Promise.resolve(Response.json({ status: 'available', network: 'preprod', reasons: [] }));
      upstreamCalls += 1;
      return fetch(input, init);
    };
    app = createApp(cfg, identities, { jwks, fetchImpl });
  });

  afterAll(async () => {
    if (backend && backend.exitCode === null) {
      await new Promise<void>((done) => { backend!.once('exit', () => done()); backend!.kill('SIGTERM'); });
    }
    expect(logs).not.toContain(commandToken); expect(logs).not.toContain(member); expect(logs).not.toContain(invite);
  });

  it('creates one idempotent transfer intent for the verified owner, behind scope and recent authentication', async () => {
    const path = `/api/v1/assets/${asset}/transfers`;
    const body = { rights_scope: ['transfer'], recipient_invite: invite, expires_in_seconds: 3600 };
    const key = `transfer-${randomUUID()}`;
    const stale = await request(app).post(path).auth(await signed('owner', 'rights:transfer', false), { type: 'bearer' })
      .set('Idempotency-Key', key).send(body);
    expect(stale.status).toBe(401); expect(stale.body.code).toBe('reauth_required');
    const unscoped = await request(app).post(path).auth(await signed('owner', 'rights:read'), { type: 'bearer' })
      .set('Idempotency-Key', key).send(body);
    expect(unscoped.status).toBe(403);
    const created = await request(app).post(path).auth(await signed(), { type: 'bearer' }).set('Idempotency-Key', key).send(body);
    expect(created.status).toBe(201);
    expect(created.body).toMatchObject({ state: 'AwaitingRecipient', role: 'sender', expected_epoch: '2', network: 'preprod',
      entitlement_id: 'cd'.repeat(32), proving: null });
    expect(JSON.stringify(created.body)).not.toContain(invite);
    const replay = await request(app).post(path).auth(await signed(), { type: 'bearer' }).set('Idempotency-Key', key).send(body);
    expect(replay.status).toBe(201); expect(replay.body.intent_id).toBe(created.body.intent_id);
    const second = await request(app).post(path).auth(await signed(), { type: 'bearer' })
      .set('Idempotency-Key', `transfer-${randomUUID()}`).send(body);
    expect(second.status).toBe(409); expect(second.body.code).toBe('transfer_in_progress');
    expect(second.headers['content-type']).toMatch(/application\/problem\+json/);
    const stranger = await request(app).post(path).auth(await signed('other'), { type: 'bearer' })
      .set('Idempotency-Key', `transfer-${randomUUID()}`).send(body);
    expect(stranger.status).toBe(404);
  });

  it('authorizes ownership challenges and evaluates reprint quotes without consuming anything', async () => {
    const challenge = await request(app).post('/api/v1/ownership/challenges').auth(await signed('owner', 'rights:read'), { type: 'bearer' })
      .send({ entitlement_id: 'cd'.repeat(32), audience: 'resale-partner' });
    expect(challenge.status).toBe(201);
    expect(challenge.body).toMatchObject({ circuit: 'proveControl', expected_epoch: '2', network: 'preprod' });
    expect(challenge.body.audience_digest).toMatch(/^[0-9a-f]{64}$/);
    const denied = await request(app).post('/api/v1/ownership/challenges').auth(await signed('other', 'rights:read'), { type: 'bearer' })
      .send({ entitlement_id: 'cd'.repeat(32), audience: 'resale-partner' });
    expect(denied.status).toBe(404);
    const quote = await request(app).post(`/api/v1/assets/${asset}/reprint-quotes`).auth(await signed('owner', 'rights:reprint'), { type: 'bearer' })
      .send({ quantity: 1, manufacturer_id: 'ab'.repeat(32), territory: 'US' });
    expect(quote.status).toBe(200);
    expect(quote.body).toMatchObject({ eligible: false, missing: ['license_missing'], price: null, price_status: 'unavailable' });
  });

  it('keeps the cookie CSRF boundary in front of the command service', async () => {
    const before = upstreamCalls;
    const r = await request(app).post(`/api/v1/assets/${asset}/transfers`).set('Cookie', 'bm_session=test-session')
      .set('Idempotency-Key', `transfer-${randomUUID()}`).send({ rights_scope: ['transfer'], recipient_invite: invite, expires_in_seconds: 3600 });
    expect(r.status).toBe(403); expect(r.body.code).toBe('csrf_failed'); expect(upstreamCalls).toBe(before);
  });
});
