/**
 * /api/v1 identity boundary against the Spanner emulator (W02 exit evidence):
 * persistence across restart and a second session, CSRF, If-Match conflicts,
 * unauthenticated access, OIDC token validation, strict-mode refusal of the
 * dev identity simulation.
 */
import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { existsSync } from 'node:fs';
import { createConnection } from 'node:net';
import { resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import request from 'supertest';
import { SignJWT, createLocalJWKSet, exportJWK, generateKeyPair } from 'jose';
import { loadConfig } from '../../config';
import { createApp } from '../../index';
import { IdentityStore } from '../../middleware/identity/store';

const REPO = resolve(__dirname, '../../../..');
const emulator = process.env.SPANNER_EMULATOR_HOST ?? 'localhost:9010';

async function reachable(hostPort: string): Promise<boolean> {
  const [host, port] = hostPort.split(':');
  return new Promise((res) => {
    const s = createConnection({ host, port: Number(port) }, () => { s.end(); res(true); });
    s.on('error', () => res(false));
    s.setTimeout(1000, () => { s.destroy(); res(false); });
  });
}

const up = await reachable(emulator);
const databaseId = `gw-${randomUUID().slice(0, 8)}`;
const python = process.env.BRANDME_PYTHON ?? (existsSync(resolve(REPO, '.venv/bin/python')) ? resolve(REPO, '.venv/bin/python') : 'python3');
const ORIGIN = 'http://localhost:3000';

const baseEnv = { BRANDME_MODE: 'development', SPANNER_DATABASE_ID: databaseId, BRAIN_SERVICE_URL: 'http://127.0.0.1:9' };

describe.skipIf(!up)('api/v1 identity + me (emulator)', () => {
  const stores: IdentityStore[] = [];
  const mkApp = (env: Record<string, string> = {}, extra = {}) => {
    const cfg = loadConfig({ ...baseEnv, ...env });
    const store = new IdentityStore({ projectId: cfg.spannerProjectId, instanceId: cfg.spannerInstanceId, databaseId, mode: cfg.mode });
    stores.push(store);
    return createApp(cfg, store, extra);
  };

  beforeAll(() => {
    execFileSync(python, [resolve(REPO, 'brandme-data/spanner/migrations/runner.py'), 'up', '--create-database', '--wait', '30'], {
      env: { ...process.env, SPANNER_EMULATOR_HOST: emulator, SPANNER_DATABASE_ID: databaseId },
      stdio: 'pipe',
    });
  });
  afterAll(async () => {
    const db = stores[0]?.database;
    if (db) await db.delete().catch(() => undefined);
    await Promise.all(stores.map((s) => s.close()));
  });

  async function signIn(app: ReturnType<typeof mkApp>, identity: string) {
    const r = await request(app).post('/api/v1/session/dev').set('Origin', ORIGIN).send({ test_identity: identity });
    expect(r.status).toBe(201);
    expect(r.headers['x-brandme-simulation']).toMatch(/Simulated/);
    const cookie = r.headers['set-cookie'][0].split(';')[0];
    return { cookie, csrf: r.body.csrf_token as string, memberId: r.body.member_id as string };
  }

  it('requires authentication and returns problem+json with request id and environment', async () => {
    const r = await request(mkApp()).get('/api/v1/me');
    expect(r.status).toBe(401);
    expect(r.headers['content-type']).toMatch(/application\/problem\+json/);
    expect(r.headers['x-request-id']).toMatch(/^[0-9a-f-]{36}$/);
    expect(r.headers['x-brandme-environment']).toBe('development');
    expect(r.body).toMatchObject({ status: 401, code: 'unauthenticated', retryable: false });
  });

  it('a saved profile survives gateway restart and is visible to a second browser session', async () => {
    const identity = `ada-${randomUUID().slice(0, 6)}`;
    const app1 = mkApp();
    const s1 = await signIn(app1, identity);
    const me = await request(app1).get('/api/v1/me').set('Cookie', s1.cookie);
    expect(me.status).toBe(200);
    expect(me.body.member.version).toBe('1');
    expect(me.body.session.assurance_level).toBe('simulated');
    expect(me.body.capabilities.find((c: { name: string }) => c.name === 'auth.identity').simulation_label).toMatch(/Simulated/);

    const patched = await request(app1)
      .patch('/api/v1/me')
      .set({ Cookie: s1.cookie, 'X-CSRF-Token': s1.csrf, 'If-Match': '"1"', Origin: ORIGIN })
      .send({ display_name: 'Ada', settings: { room_theme: 'garden_studio', motion_mode: 'reduced' } });
    expect(patched.status).toBe(200);
    expect(patched.headers.etag).toBe('"2"');

    // "Restart": a brand-new app + store instance; a different browser signs in as the same identity.
    const app2 = mkApp();
    const s2 = await signIn(app2, identity);
    expect(s2.memberId).toBe(s1.memberId);
    expect(s2.cookie).not.toBe(s1.cookie);
    const again = await request(app2).get('/api/v1/me').set('Cookie', s2.cookie);
    expect(again.body.member.display_name).toBe('Ada');
    expect(again.body.settings.room_theme).toBe('garden_studio');
    expect(again.body.settings.motion_mode).toBe('reduced');
    // The original session cookie still works on the restarted gateway.
    expect((await request(app2).get('/api/v1/me').set('Cookie', s1.cookie)).status).toBe(200);
  });

  it('stale If-Match gets 409 with the current revision; missing If-Match gets 428', async () => {
    const app = mkApp();
    const s = await signIn(app, `bo-${randomUUID().slice(0, 6)}`);
    const h = { Cookie: s.cookie, 'X-CSRF-Token': s.csrf };
    expect((await request(app).patch('/api/v1/me').set(h).send({ display_name: 'x' })).status).toBe(428);
    expect((await request(app).patch('/api/v1/me').set({ ...h, 'If-Match': '"1"' }).send({ display_name: 'first' })).status).toBe(200);
    const stale = await request(app).patch('/api/v1/me').set({ ...h, 'If-Match': '"1"' }).send({ display_name: 'second' });
    expect(stale.status).toBe(409);
    expect(stale.body).toMatchObject({ code: 'revision_conflict', current_version: '2' });
    const me = await request(app).get('/api/v1/me').set('Cookie', s.cookie);
    expect(me.body.member.display_name).toBe('first');
  });

  it('rejects non-allowlisted fields and invalid values', async () => {
    const app = mkApp();
    const s = await signIn(app, `cy-${randomUUID().slice(0, 6)}`);
    const h = { Cookie: s.cookie, 'X-CSRF-Token': s.csrf, 'If-Match': '"1"' };
    for (const body of [{ account_state: 'deleted' }, { member_id: randomUUID() }, { handle: 'NO SPACES' }, { settings: { room_theme: 'castle' } }, {}]) {
      const r = await request(app).patch('/api/v1/me').set(h).send(body);
      expect(r.status, JSON.stringify(body)).toBe(422);
    }
  });

  it('state changes need the CSRF token and an allowed Origin', async () => {
    const app = mkApp();
    const s = await signIn(app, `dee-${randomUUID().slice(0, 6)}`);
    const noToken = await request(app).patch('/api/v1/me').set({ Cookie: s.cookie, 'If-Match': '"1"' }).send({ display_name: 'x' });
    expect(noToken.status).toBe(403);
    expect(noToken.body.code).toBe('csrf_failed');
    const badToken = await request(app).patch('/api/v1/me').set({ Cookie: s.cookie, 'X-CSRF-Token': 'nope', 'If-Match': '"1"' }).send({ display_name: 'x' });
    expect(badToken.status).toBe(403);
    const evil = await request(app).patch('/api/v1/me').set({ Cookie: s.cookie, 'X-CSRF-Token': s.csrf, 'If-Match': '"1"', Origin: 'https://evil.example' }).send({ display_name: 'x' });
    expect(evil.status).toBe(403);
  });

  it('signing out revokes the session server-side', async () => {
    const app = mkApp();
    const s = await signIn(app, `eve-${randomUUID().slice(0, 6)}`);
    const out = await request(app).delete('/api/v1/session').set({ Cookie: s.cookie, 'X-CSRF-Token': s.csrf });
    expect(out.status).toBe(204);
    expect((await request(app).get('/api/v1/me').set('Cookie', s.cookie)).status).toBe(401);
  });

  it('two members cannot read or write each other: /me is always the caller', async () => {
    const app = mkApp();
    const a = await signIn(app, `fay-${randomUUID().slice(0, 6)}`);
    const b = await signIn(app, `gus-${randomUUID().slice(0, 6)}`);
    await request(app).patch('/api/v1/me').set({ Cookie: a.cookie, 'X-CSRF-Token': a.csrf, 'If-Match': '"1"' }).send({ display_name: 'A' });
    const asB = await request(app).get('/api/v1/me').set('Cookie', b.cookie);
    expect(asB.body.member.id).toBe(b.memberId);
    expect(asB.body.member.display_name).toBeNull();
    // B's CSRF token cannot drive A's session.
    const cross = await request(app).patch('/api/v1/me').set({ Cookie: a.cookie, 'X-CSRF-Token': b.csrf, 'If-Match': '"2"' }).send({ display_name: 'hijack' });
    expect(cross.status).toBe(403);
  });

  it('a session minted in development is not accepted by a production-mode gateway', async () => {
    const dev = mkApp();
    const s = await signIn(dev, `hal-${randomUUID().slice(0, 6)}`);
    const prod = mkApp({ BRANDME_MODE: 'production', IDENTITY_PROVIDER: 'oidc', OIDC_ISSUER: 'https://idp.example.invalid', OIDC_AUDIENCE: 'brandme-api' });
    expect((await request(prod).get('/api/v1/me').set('Cookie', s.cookie)).status).toBe(401);
    expect((await request(prod).post('/api/v1/session/dev').send({ test_identity: 'x' })).status).toBe(404);
  });

  describe('OIDC bearer tokens', async () => {
    const issuer = 'https://idp.example.invalid';
    const audience = 'brandme-api';
    const { publicKey, privateKey } = await generateKeyPair('RS256');
    const jwks = createLocalJWKSet({ keys: [{ ...(await exportJWK(publicKey)), kid: 'k1', alg: 'RS256' }] });
    const sign = (claims: Record<string, unknown>, opts: { iss?: string; aud?: string; exp?: string } = {}) =>
      new SignJWT(claims)
        .setProtectedHeader({ alg: 'RS256', kid: 'k1' })
        .setIssuer(opts.iss ?? issuer)
        .setAudience(opts.aud ?? audience)
        .setIssuedAt()
        .setExpirationTime(opts.exp ?? '5m')
        .sign(privateKey);
    const oidcApp = () => mkApp({ IDENTITY_PROVIDER: 'oidc', OIDC_ISSUER: issuer, OIDC_AUDIENCE: audience }, { jwks });

    it('maps a verified (iss, sub) to one internal member', async () => {
      const app = oidcApp();
      const sub = `oidc-${randomUUID()}`;
      const t = await sign({ sub, scope: 'profile:read' });
      const r1 = await request(app).get('/api/v1/me').set('Authorization', `Bearer ${t}`);
      const r2 = await request(app).get('/api/v1/me').set('Authorization', `Bearer ${await sign({ sub })}`);
      expect(r1.status).toBe(200);
      expect(r1.body.member.id).toBe(r2.body.member.id);
      expect(r1.body.session.assurance_level).toBe('aal1');
    });

    it('rejects wrong audience, wrong issuer, expired and symmetric (HS256) tokens', async () => {
      const app = oidcApp();
      const bad = [
        await sign({ sub: 'x' }, { aud: 'other-api' }),
        await sign({ sub: 'x' }, { iss: 'https://evil.example' }),
        await sign({ sub: 'x' }, { exp: '-1m' }),
        await new SignJWT({ sub: 'x' }).setProtectedHeader({ alg: 'HS256' }).setIssuer(issuer).setAudience(audience).setExpirationTime('5m').sign(new TextEncoder().encode('s'.repeat(40))),
      ];
      for (const t of bad) expect((await request(app).get('/api/v1/me').set('Authorization', `Bearer ${t}`)).status).toBe(401);
    });
  });
});
