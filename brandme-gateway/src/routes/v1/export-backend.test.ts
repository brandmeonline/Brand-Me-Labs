/** Signed OIDC → gateway → actual export API/worker → Spanner + local GCS API contract fixture. */
import { execFileSync, spawn, type ChildProcess } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
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
const freePort = () => new Promise<number>((done) => {
  const s = createServer().listen(0, '127.0.0.1', () => {
    const port = (s.address() as { port: number }).port; s.close(() => done(port));
  });
});

describe.skipIf(!up)('selected rights export through running backends', () => {
  let app: ReturnType<typeof createApp>;
  let privateKey: KeyLike;
  let store: IdentityStore;
  let env: NodeJS.ProcessEnv;
  const children: ChildProcess[] = [];
  let logs = '';
  const member = '11111111-1111-4111-8111-111111111111';
  const other = '22222222-2222-4222-8222-222222222222';
  const token = 'export-service-test-token-32-characters';
  const issuer = 'https://export-test-identity.example';
  const signed = (sub = 'owner', age = 0, scope = 'privacy:manage') => new SignJWT({ sub, scope, auth_time: Math.floor(Date.now() / 1000) - age })
    .setProtectedHeader({ alg: 'RS256', kid: 'export-api' }).setIssuer(issuer).setAudience('gateway')
    .setIssuedAt().setExpirationTime('5m').sign(privateKey);

  const launch = (args: string[], vars: NodeJS.ProcessEnv) => {
    const child = spawn(python, args, { cwd: root, env: vars, stdio: ['ignore', 'pipe', 'pipe'] });
    children.push(child);
    child.stdout?.on('data', (b) => { logs += b; }); child.stderr?.on('data', (b) => { logs += b; });
    return child;
  };
  const ready = async (base: string, process: ChildProcess) => {
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline && process.exitCode === null) {
      try { if ((await fetch(`${base}/health`, { signal: AbortSignal.timeout(1000) })).ok) return; } catch { /* startup */ }
      await new Promise((done) => setTimeout(done, 100));
    }
    throw new Error('private service not ready');
  };

  beforeAll(async () => {
    env = { ...process.env, BRANDME_MODE: 'development', ENVIRONMENT: 'development', PYTHONPATH: root,
      SPANNER_EMULATOR_HOST: emulator, SPANNER_PROJECT_ID: 'test-project', SPANNER_INSTANCE_ID: 'gateway-export-tests',
      SPANNER_DATABASE_ID: `export-${randomUUID().slice(0, 8)}`, READ_API_NETWORK: 'preprod', READ_API_CONTRACT_ADDRESS: 'ab'.repeat(32),
      RIGHTS_SERVICE_TOKEN: 'rights-service-test-token-32-characters', PRIVACY_SERVICE_TOKEN: 'privacy-service-test-token-32-characters',
      EXPORT_NETWORK: 'preprod', EXPORT_CONTRACT_ADDRESS: 'ab'.repeat(32), EXPORT_BUCKET: 'brandme-development-exports-tests',
      PRIVACY_EXPORT_SERVICE_TOKEN: token };
    execFileSync(python, [resolve(root, 'tests/fixtures/seed_read_api.py')], { cwd: root, env, stdio: 'pipe', timeout: 120000 });
    store = new IdentityStore({ projectId: env.SPANNER_PROJECT_ID!, instanceId: env.SPANNER_INSTANCE_ID!, databaseId: env.SPANNER_DATABASE_ID!, mode: 'development' });
    const storage = launch([resolve(root, 'tests/fixtures/export_storage.py')], env);
    env.EXPORT_STORAGE_EMULATOR_HOST = await new Promise<string>((done, reject) => {
      let output = '';
      const timeout = setTimeout(() => reject(new Error('storage contract fixture not ready')), 10000);
      storage.stdout!.on('data', (b) => {
        output += b;
        if (output.includes('\n')) { clearTimeout(timeout); done((JSON.parse(output.split('\n')[0]!) as { host: string }).host); }
      });
    });
    const exportPort = await freePort(); const readPort = await freePort();
    const exportBase = `http://127.0.0.1:${exportPort}`; const readBase = `http://127.0.0.1:${readPort}`;
    const backend = launch(['-m', 'brandme_core.privacy_exports'], { ...env, PORT: String(exportPort) });
    const readBackend = launch(['-m', 'brandme_core.read_api'], { ...env, PORT: String(readPort) });
    await Promise.all([ready(exportBase, backend), ready(readBase, readBackend)]);
    const pair = await generateKeyPair('RS256'); privateKey = pair.privateKey;
    const jwks = createLocalJWKSet({ keys: [{ ...(await exportJWK(pair.publicKey)), kid: 'export-api', alg: 'RS256' }] });
    const identities = { resolveMember: async (_issuer: string, sub: string) => ({ memberId: sub === 'owner' ? member : other }) } as IdentityStore;
    const cfg = loadConfig({ ...env, IDENTITY_PROVIDER: 'oidc', OIDC_ISSUER: issuer, OIDC_AUDIENCE: 'gateway',
      PRIVACY_SERVICE_URL: `${readBase}/privacy`, PRIVACY_EXPORT_SERVICE_URL: exportBase });
    app = createApp(cfg, identities, { jwks });
  }, 120000);

  afterAll(async () => {
    for (const child of children.reverse()) {
      if (child.exitCode === null) await new Promise<void>((done) => { child.once('exit', () => done()); child.kill('SIGTERM'); });
    }
    if (store) { await store.database.delete(); await store.close(); }
    expect(logs).not.toContain(token); expect(logs).not.toContain(member);
  });

  it('keeps explicit selection, scope, idempotency and recent-auth boundaries', async () => {
    const body = { categories: ['rights.control_links'] };
    expect((await request(app).post('/api/v1/me/exports').send(body)).status).toBe(401);
    expect((await request(app).post('/api/v1/me/exports').auth(await signed('owner', 0, 'rights:read'), { type: 'bearer' }).send(body)).status).toBe(403);
    expect((await request(app).post('/api/v1/me/exports').auth(await signed('owner', 601), { type: 'bearer' }).send(body)).status).toBe(401);
    const bearer = await signed();
    expect((await request(app).post('/api/v1/me/exports').auth(bearer, { type: 'bearer' }).send(body)).status).toBe(400);
    expect((await request(app).post('/api/v1/me/exports').auth(bearer, { type: 'bearer' }).set('Idempotency-Key', randomUUID()).send({})).status).toBe(400);
    const cap = await request(app).get('/api/v1/me/exports/capability').auth(bearer, { type: 'bearer' });
    expect(cap.status).toBe(200); expect(cap.body).toMatchObject({ full_account: false, selected_categories_only: true, network: 'preprod' });
    const data = await request(app).get('/api/v1/me/data').auth(bearer, { type: 'bearer' });
    expect(data.body.capabilities).toEqual({ export: 'selected_categories', deletion: 'unavailable' });
  });

  it('persists a member-owned job and downloads exact worker-produced bytes after reauth', async () => {
    const bearer = await signed(); const key = randomUUID();
    const submit = (categories = ['rights.control_links']) => request(app).post('/api/v1/me/exports').auth(bearer, { type: 'bearer' })
      .set('Idempotency-Key', key).set('x-subject-ref', other).set('x-reauth-at', '1900-01-01T00:00:00Z').send({ categories });
    const r = await submit();
    expect(r.status).toBe(202); expect(r.body.state).toBe('requested');
    const id = r.body.job_id as string;
    expect((await submit()).body.job_id).toBe(id);
    expect((await submit(['rights.operations'])).status).toBe(409);
    const download = `/api/v1/me/exports/${id}/download`;
    expect((await request(app).get(download).auth(bearer, { type: 'bearer' })).status).toBe(409);
    execFileSync(python, ['-m', 'brandme_core.privacy_exports', '--worker', '--once'], { cwd: root, env, stdio: 'pipe', timeout: 30000 });
    const status = await request(app).get(`/api/v1/me/exports/${id}`).auth(bearer, { type: 'bearer' });
    expect(status.status).toBe(200); expect(status.body.state).toBe('ready');
    const downloaded = await request(app).get(download).auth(bearer, { type: 'bearer' }).set('x-subject-ref', other).set('Origin', 'http://localhost:3000');
    expect(downloaded.status).toBe(200);
    expect(createHash('sha256').update(downloaded.text).digest('hex')).toBe(status.body.package_sha256);
    expect(downloaded.headers['x-export-sha256']).toBe(status.body.package_sha256);
    expect(downloaded.headers['access-control-expose-headers']).toContain('X-Export-SHA256');
    expect(downloaded.headers['content-disposition']).toBe(`attachment; filename="brandme-rights-${id}.json"`);
    expect(downloaded.body).toMatchObject({ subject_ref: member, coverage: { full_account: false },
      sections: [{ category: 'rights.control_links', records: [{ entitlement_id: 'cd'.repeat(32) }] }] });
    expect((await request(app).get(download).auth(await signed('other'), { type: 'bearer' }).set('x-subject-ref', member)).status).toBe(404);
    expect((await request(app).get(download).auth(await signed('owner', 601), { type: 'bearer' })
      .set('x-reauth-at', new Date().toISOString())).status).toBe(401);
    expect((await request(app).get(`${download}?subject=${member}`).auth(bearer, { type: 'bearer' })).status).toBe(400);
  }, 30000);
});
