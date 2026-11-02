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

  it('runs Now, Flow and loyalty standing end to end for two dev members', async () => {
    const seed = (...args: string[]) => JSON.parse(execFileSync(python, [resolve(root, 'tests/fixtures/persona/consumer_dev.py'), ...args],
      { cwd: root, env, timeout: 120_000 }).toString().trim().split('\n').pop()!);
    const signIn = async (identity: string) => {
      const agent = request.agent(app);
      const s = await agent.post('/api/v1/session/dev').send({ test_identity: identity });
      expect(s.status).toBe(201);
      const csrf = { 'x-csrf-token': s.body.csrf_token as string };
      return { agent, id: s.body.member_id as string, csrf, key: () => ({ ...csrf, 'idempotency-key': `e2e-${randomUUID()}` }) };
    };
    const asker = await signIn('e2e-now-asker');
    const friend = await signIn('e2e-now-friend');
    const rel = await asker.agent.post('/api/v1/relationships').set(asker.csrf).send({ target_member_id: friend.id });
    expect(rel.status).toBe(201);
    expect((await friend.agent.post(`/api/v1/relationships/${rel.body.relationship_id}/accept`).set(friend.csrf)).status).toBe(200);

    const brand = `Dev House ${randomUUID().slice(0, 8)}`;
    const pieces = seed('pieces', brand, '3') as { variant_id: string; house_ref: string }[];
    const ref = pieces[0]!.house_ref;
    expect((await asker.agent.get('/api/v1/flow')).body.items).toEqual([]); // no houses yet
    const follow = await asker.agent.put(`/api/v1/houses/${ref}/follow`).set(asker.csrf).send({ share_standing: true });
    expect(follow.body).toMatchObject({ house_ref: ref, name: brand, followed: true, share_standing: true });
    expect((await asker.agent.put('/api/v1/houses/Not_A_Ref/follow').set(asker.csrf).send({})).status).toBe(404);

    // Now: the asker picks a short window and says why; the friend sees it cut into their Flow.
    const target = pieces[1]!.variant_id;
    const ask = await asker.agent.post('/api/v1/decisions').set(asker.key()).send({ subject_type: 'catalog_product', subject_id: target,
      prompt: 'This one?', why: 'Gallery opening on Friday', duration_seconds: 180, recipient_ids: [friend.id], discussion_mode: 'open' });
    expect(ask.status).toBe(201);
    expect(ask.body).toMatchObject({ duration_seconds: 180, why: 'Gallery opening on Friday', state: 'open' });
    const bogus = await asker.agent.post('/api/v1/decisions').set(asker.key()).send({ subject_type: 'catalog_product', subject_id: randomUUID(),
      prompt: 'This one?', recipient_ids: [friend.id], discussion_mode: 'open' });
    expect(bogus.status).toBe(422); // not a catalog piece
    const theirs = await friend.agent.get('/api/v1/flow');
    expect(theirs.body.items[0]).toMatchObject({ kind: 'decision_request', position: 1,
      decision: { decision_id: ask.body.decision_id, why: 'Gallery opening on Friday', answered: false } });
    const did = ask.body.decision_id as string;
    expect((await friend.agent.post(`/api/v1/decisions/${did}/responses`).set(friend.csrf).send({ choice: 'yes' })).status).toBe(200);
    expect((await friend.agent.post(`/api/v1/decisions/${did}/comments`).set(friend.key()).send({ body: 'With the grey trousers' })).status).toBe(201);
    const thread = await asker.agent.get(`/api/v1/decisions/${did}/comments`);
    expect(thread.body.items.map((c: { body: string }) => c.body)).toEqual(['With the grey trousers']);

    // Flow: the house's newest pieces, newest first, sized with a reason.
    const home = await asker.agent.get('/api/v1/flow');
    expect(home.status).toBe(200);
    expect(home.body.items.map((i: { piece: { product_id: string } }) => i.piece.product_id)).toEqual(pieces.map((p) => p.variant_id).reverse());
    expect(home.body.items[0]).toMatchObject({ kind: 'house_piece', position: 1, size: 'compact', piece: { house_ref: ref, via: 'followed' } });
    expect(JSON.stringify(home.body)).not.toMatch(/count/);

    // The asker buys what the friend said yes to; the friend earns influence credit once it is delivered.
    expect((await asker.agent.post(`/api/v1/decisions/${did}/close`).set(asker.csrf)).status).toBe(200);
    expect(seed('delivered', asker.id, target, '1')).toEqual({ items_created: 1, events_delivered: 1 });
    const earned = await friend.agent.get('/api/v1/rewards/entries');
    expect(earned.body.items.filter((e: { rule_id: string }) => e.rule_id === 'decision_influence'))
      .toEqual([expect.objectContaining({ points: 25, state: 'posted' })]);

    // Loyalty: the jobs process recomputes standings; the member sees only a tier (one buyer is below the ranking cohort).
    const ran = JSON.parse(execFileSync(python, ['-m', 'brandme_core.domains.persona.jobs', '--once'], { cwd: root, env, timeout: 120_000 })
      .toString().trim().split('\n').pop()!);
    expect(ran.standings.standings).toBeGreaterThanOrEqual(1);
    const standing = await asker.agent.get('/api/v1/rewards/standings');
    expect(standing.body.items).toEqual([expect.objectContaining({ house_ref: ref, house_name: brand, tier: 'member', shared_with_house: true })]);
    expect((await friend.agent.get('/api/v1/rewards/standings')).body.items).toEqual([]);
    expect((await asker.agent.delete(`/api/v1/houses/${ref}/follow`).set(asker.csrf)).body).toEqual({ house_ref: ref, followed: false });
  }, 180_000);

  it('runs closet visibility, the persona card, surveys and in-app credit end to end', async () => {
    const seed = (...args: string[]) => JSON.parse(execFileSync(python, [resolve(root, 'tests/fixtures/persona/consumer_dev.py'), ...args],
      { cwd: root, env, timeout: 120_000 }).toString().trim().split('\n').pop()!);
    const signIn = async (identity: string) => {
      const agent = request.agent(app);
      const s = await agent.post('/api/v1/session/dev').send({ test_identity: identity });
      const csrf = { 'x-csrf-token': s.body.csrf_token as string };
      return { agent, id: s.body.member_id as string, csrf, key: () => ({ ...csrf, 'idempotency-key': `e2e-${randomUUID()}` }) };
    };
    const me = await signIn('e2e-card-owner');
    const friend = await signIn('e2e-card-friend');
    const stranger = await signIn('e2e-card-stranger');
    const rel = await me.agent.post('/api/v1/relationships').set(me.csrf).send({ target_member_id: friend.id });
    await friend.agent.post(`/api/v1/relationships/${rel.body.relationship_id}/accept`).set(friend.csrf);

    // Closet visibility: private by default; friends see the story, strangers nothing.
    const piece = (await me.agent.post('/api/v1/wardrobe/items').set(me.key()).send({ source: 'manual', title: 'Signature coat', category: 'outerwear' }))
      .body.items[0].id as string;
    expect((await friend.agent.get(`/api/v1/members/${me.id}/closet`)).body.items).toEqual([]);
    const shown = await me.agent.put(`/api/v1/wardrobe/items/${piece}/visibility`).set(me.csrf)
      .send({ visibility: 'friends', detail: 'story', showcase_note: 'Every winter since 2019' });
    expect(shown.status).toBe(200);
    expect((await friend.agent.get(`/api/v1/members/${me.id}/closet`)).body.items)
      .toEqual([expect.objectContaining({ item_id: piece, showcase_note: 'Every winter since 2019', detail: 'story' })]);
    expect((await stranger.agent.get(`/api/v1/members/${me.id}/closet`)).body.items).toEqual([]);

    // The persona card: composed from the profile, highlights respect each piece's visibility.
    expect((await me.agent.patch('/api/v1/me/persona').set({ ...me.csrf, 'if-match': '"0"' })
      .send({ changes: [{ axis: 'expression', value: 85, locked: false }], client_revision: 'e2e' })).status).toBe(200);
    const card = await me.agent.put('/api/v1/me/persona/card').set(me.csrf).send({ highlight_item_ids: [piece] });
    expect(card.status).toBe(200);
    expect(card.body.card.taste).toEqual([expect.objectContaining({ label: 'Expressive' })]);
    expect((await friend.agent.get(`/api/v1/members/${me.id}/card`)).body.card.highlights).toEqual([expect.objectContaining({ item_id: piece })]);
    expect((await stranger.agent.get(`/api/v1/members/${me.id}/card`)).status).toBe(404); // friends-only by default

    // Surveys feed points; points become in-app credit only.
    const { survey_id: surveyId } = seed('survey');
    const open = await me.agent.get('/api/v1/surveys');
    expect(open.body.items.map((s: { survey_id: string }) => s.survey_id)).toContain(surveyId);
    const answered = await me.agent.post(`/api/v1/surveys/${surveyId}/responses`).set(me.key()).send({ answers: { fit: 'Relaxed', comfort: 4 } });
    expect(answered.status).toBe(201);
    expect(answered.body.reward).toEqual({ status: 'posted', points: 10 });
    expect(seed('points', me.id, '3').available).toBe(610);
    const credit = await me.agent.post('/api/v1/rewards/credits').set(me.key()).send({ points: 500 });
    expect(credit.status).toBe(201);
    expect(credit.body).toMatchObject({ amount: { minor: 500, currency: 'USD' }, state: 'available', account: { available: 110, reserved: 500 } });
    expect((await me.agent.post('/api/v1/rewards/credits').set(me.key()).send({ points: 500, payout_account: 'acct_1' })).status).toBe(422);
    expect((await me.agent.get('/api/v1/rewards/credits')).body.items).toHaveLength(1);
  }, 180_000);

  it('the service refuses calls that do not carry a valid gateway assertion', async () => {
    const base = loadConfig({ BRANDME_MODE: 'development', CONSUMER_DOMAIN_SERVICE_URL: `http://127.0.0.1:${env.PORT}` }).consumerDomainUrl;
    expect((await fetch(`${base}/try-on/capabilities`)).status).toBe(401);
    expect((await fetch(`${base}/try-on/capabilities`, { headers: { authorization: 'Bearer not-an-assertion' } })).status).toBe(401);
  });
});
