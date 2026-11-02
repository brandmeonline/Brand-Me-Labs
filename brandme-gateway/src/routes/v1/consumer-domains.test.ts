/**
 * Dev gateway → consumer-domain service → Spanner + GCS emulator, end to end
 * (Ultra plan 02, item 1). A fictional dev session drives the whole try-on media
 * flow through the mounted routers. The service checks the gateway's signed
 * principal assertion; the jobs process dispatches to the labelled simulated
 * provider (BRANDME_TRYON_PROVIDER=simulated, demo/development only).
 */
import { execFileSync, spawn, type ChildProcess } from 'node:child_process';
import { existsSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { createConnection, createServer } from 'node:net';
import { resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import request from 'supertest';
import { exportJWK, exportPKCS8, generateKeyPair } from 'jose';
import { createApp } from '../../index';
import { loadConfig } from '../../config';
import { IdentityStore } from '../../middleware/identity/store';
import { DOMAIN_ISSUER } from '../../services/domains';

const root = resolve(__dirname, '../../../..');
const python = process.env.BRANDME_PYTHON ?? 'python3';
const emulator = process.env.SPANNER_EMULATOR_HOST ?? 'localhost:9010';
const up = await new Promise<boolean>((done) => {
  const [host, port] = emulator.split(':');
  const s = createConnection({ host, port: Number(port) }, () => { s.end(); done(true); });
  s.on('error', () => done(false)); s.setTimeout(1000, () => { s.destroy(); done(false); });
});
const PNG = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(200)]);

const freePort = () => new Promise<number>((done) => {
  const s = createServer().listen(0, '127.0.0.1', () => { const p = (s.address() as { port: number }).port; s.close(() => done(p)); });
});

async function waitFor(url: string, proc: ChildProcess, what: string): Promise<void> {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try { if ((await fetch(url, { signal: AbortSignal.timeout(1000) })).ok) return; } catch { /* starting */ }
    if (proc.exitCode !== null) break;
    await new Promise((d) => setTimeout(d, 100));
  }
  throw new Error(`${what} did not become ready`);
}

function gcsBinary(): string {
  const fromEnv = process.env.GCS_EMULATOR_BIN;
  if (fromEnv && existsSync(fromEnv)) return fromEnv;
  // Pinned release, checked against its published SHA256 (scripts/python/fetch_gcs_emulator.py).
  return execFileSync(python, [resolve(root, 'scripts/python/fetch_gcs_emulator.py'), resolve(root, '.cache/gcs-emulator')],
    { cwd: root, timeout: 120_000 }).toString().trim();
}

describe.skipIf(!up)('mounted consumer domains on the dev gateway', () => {
  const procs: ChildProcess[] = [];
  let logs = '';
  let app: ReturnType<typeof createApp>;
  let store: IdentityStore;
  let env: NodeJS.ProcessEnv;
  let privatePem = '';
  let bucketApi = '';

  beforeAll(async () => {
    const [domainPort, gcsPort] = [await freePort(), await freePort()];
    bucketApi = `http://127.0.0.1:${gcsPort}`;
    const gcs = spawn(gcsBinary(), ['-scheme', 'http', '-host', '127.0.0.1', '-port', String(gcsPort), '-backend', 'memory',
      '-external-url', bucketApi, '-public-host', `127.0.0.1:${gcsPort}`, '-log-level', 'error'], { stdio: 'ignore' });
    procs.push(gcs);
    await waitFor(`${bucketApi}/storage/v1/b`, gcs, 'GCS emulator');
    const bucket = `bm-e2e-${randomUUID().slice(0, 8)}`;
    expect((await fetch(`${bucketApi}/storage/v1/b?project=brandme-dev`, { method: 'POST', body: JSON.stringify({ name: bucket }),
      headers: { 'content-type': 'application/json' } })).ok).toBe(true);

    const pair = await generateKeyPair('ES256', { extractable: true });
    privatePem = await exportPKCS8(pair.privateKey);
    const jwks = JSON.stringify({ keys: [{ ...(await exportJWK(pair.publicKey)), kid: 'e2e-1' }] });
    env = { ...process.env, BRANDME_MODE: 'development', ENVIRONMENT: 'development', PYTHONPATH: root, SPANNER_EMULATOR_HOST: emulator,
      SPANNER_PROJECT_ID: 'test-project', SPANNER_INSTANCE_ID: 'gateway-consumer-tests', SPANNER_DATABASE_ID: `cd-${randomUUID().slice(0, 8)}`,
      CONSUMER_DOMAIN_ASSERTION_ISSUER: DOMAIN_ISSUER, CONSUMER_DOMAIN_ASSERTION_JWKS: jwks, BRANDME_MEDIA_BUCKET: bucket,
      STORAGE_EMULATOR_HOST: bucketApi, BRANDME_TRYON_PROVIDER: 'simulated', PORT: String(domainPort) };
    execFileSync(python, [resolve(root, 'brandme-data/spanner/migrations/runner.py'), 'up', '--create-database', '--wait', '60'],
      { cwd: root, env, stdio: 'pipe', timeout: 180_000 });
    const domain = spawn(python, ['-m', 'brandme_core.domains.persona.app'], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
    domain.stdout?.on('data', (b) => { logs += b; }); domain.stderr?.on('data', (b) => { logs += b; });
    procs.push(domain);
    await waitFor(`http://127.0.0.1:${domainPort}/health`, domain, 'consumer-domain service');

    store = new IdentityStore({ projectId: env.SPANNER_PROJECT_ID!, instanceId: env.SPANNER_INSTANCE_ID!,
      databaseId: env.SPANNER_DATABASE_ID!, mode: 'development' });
    const cfg = loadConfig({ BRANDME_MODE: 'development', IDENTITY_PROVIDER: 'dev', SPANNER_PROJECT_ID: env.SPANNER_PROJECT_ID,
      SPANNER_INSTANCE_ID: env.SPANNER_INSTANCE_ID, SPANNER_DATABASE_ID: env.SPANNER_DATABASE_ID,
      CONSUMER_DOMAIN_SERVICE_URL: `http://127.0.0.1:${domainPort}`, CONSUMER_DOMAIN_ASSERTION_KEY: privatePem,
      CONSUMER_DOMAIN_ASSERTION_KID: 'e2e-1' });
    app = createApp(cfg, store);
  }, 240_000);

  afterAll(async () => {
    for (const p of procs.reverse()) {
      if (p.exitCode === null) await new Promise<void>((done) => { p.once('exit', () => done()); p.kill('SIGTERM'); });
    }
    if (store) { await store.database.delete(); await store.close(); }
    expect(logs).not.toContain('PRIVATE KEY');
  });

  it('runs the try-on media flow end to end behind a dev session', async () => {
    const agent = request.agent(app);
    expect((await agent.get('/api/v1/try-on/capabilities')).status).toBe(401); // foundation auth first
    const session = await agent.post('/api/v1/session/dev').send({ test_identity: 'e2e-tryon' });
    expect(session.status).toBe(201);
    const csrf = { 'x-csrf-token': session.body.csrf_token as string };
    const key = () => ({ ...csrf, 'idempotency-key': `e2e-${randomUUID()}` });

    const caps = await agent.get('/api/v1/try-on/capabilities');
    expect(caps.status).toBe(200);
    expect(caps.body.photo_preview).toMatchObject({ available: true, simulated: true });
    const item = await agent.post('/api/v1/wardrobe/items').set(key()).send({ source: 'manual', title: 'Linen shirt', category: 'top' });
    expect(item.status).toBe(201);
    const itemId = item.body.items[0].id as string;

    const upload = await agent.post('/api/v1/media/uploads').set(key()).send({ kind: 'tryon_input', content_type: 'image/png', bytes: PNG.length });
    expect(upload.status).toBe(201);
    expect(upload.body.upload.url).toMatch(new RegExp(`^${bucketApi}/`)); // a signed bucket URL, never the gateway
    const put = await fetch(upload.body.upload.url, { method: 'PUT', body: PNG, headers: upload.body.upload.headers });
    expect(put.status).toBe(200);
    const done = await agent.post(`/api/v1/media/uploads/${upload.body.media_id}/complete`).set(csrf);
    expect(done.body.state).toBe('verified');

    const consent = { accepted: true, provider_id: caps.body.photo_preview.provider_id, terms_version: caps.body.photo_preview.terms_version };
    const job = await agent.post('/api/v1/try-on/jobs').set(key())
      .send({ mode: 'photo_preview', input_media_id: upload.body.media_id, item_id: itemId, consent });
    expect(job.status).toBe(202);
    const jobs = execFileSync(python, ['-m', 'brandme_core.domains.persona.jobs', '--once'], { cwd: root, env, timeout: 120_000 }).toString();
    expect(JSON.parse(jobs.trim().split('\n').pop()!).media.dispatched).toBeTruthy();

    const state = await agent.get(`/api/v1/try-on/jobs/${job.body.job_id}`);
    expect(state.body).toMatchObject({ state: 'succeeded', fidelity_label: 'generated_visual_preview_simulated', result_available: true });
    const result = await agent.get(`/api/v1/try-on/jobs/${job.body.job_id}/result`).buffer(true);
    expect(result.status).toBe(200);
    expect(result.headers['content-type']).toBe('image/png');
    expect(result.headers['cache-control']).toBe('private, no-store');
    expect((await agent.post(`/api/v1/try-on/jobs/${job.body.job_id}/save`).set(csrf)).body.saved).toBe(true);
    expect((await agent.delete(`/api/v1/try-on/jobs/${job.body.job_id}`).set(csrf)).status).toBe(204);
    expect((await agent.get(`/api/v1/try-on/jobs/${job.body.job_id}/result`)).status).toBe(404);
  });

  it('the service refuses calls that do not carry a valid gateway assertion', async () => {
    const base = loadConfig({ BRANDME_MODE: 'development', CONSUMER_DOMAIN_SERVICE_URL: `http://127.0.0.1:${env.PORT}` }).consumerDomainUrl;
    expect((await fetch(`${base}/try-on/capabilities`)).status).toBe(401);
    expect((await fetch(`${base}/try-on/capabilities`, { headers: { authorization: 'Bearer not-an-assertion' } })).status).toBe(401);
  });
});
