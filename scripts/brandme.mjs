#!/usr/bin/env node
// Brand.Me developer commands (spec ch.06 §3). Every step reports exactly what
// ran; nothing that did not execute is reported as passed.
//
//   node scripts/brandme.mjs setup --mode demo     validate runtimes, venv, deps, emulator, migrations (idempotent)
//   node scripts/brandme.mjs dev --mode demo|development
//   node scripts/brandme.mjs smoke                 gateway → brain → Spanner + outbox round trip
//   node scripts/brandme.mjs check                 drift, types, unit + emulator tests, spec validator
//   node scripts/brandme.mjs migrate               apply Spanner migrations
//   node scripts/brandme.mjs evidence              acceptance status summary from recorded results
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, copyFileSync } from 'node:fs';
import { createConnection } from 'node:net';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const cmd = args[0];
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : def;
};

const PORTS = { consumer: 3000, gateway: 3001, console: 3002, brain: 8000, policy: 8001, spanner: 9010 };
const EMULATOR_IMAGE = 'gcr.io/cloud-spanner-emulator/emulator:1.5.28';
const VENV_PY = join(ROOT, '.venv/bin/python');
let PY = process.env.BRANDME_PYTHON ?? (existsSync(VENV_PY) ? VENV_PY : 'python3');

const c = { ok: (s) => `\x1b[32m${s}\x1b[0m`, bad: (s) => `\x1b[31m${s}\x1b[0m`, warn: (s) => `\x1b[33m${s}\x1b[0m`, dim: (s) => `\x1b[2m${s}\x1b[0m` };
const fail = (msg) => {
  console.error(c.bad(`✖ ${msg}`));
  process.exit(1);
};

function loadEnvFile() {
  const file = join(ROOT, '.env.local');
  if (!existsSync(file)) return {};
  const out = {};
  for (const line of readFileSync(file, 'utf8').split('\n')) {
    const m = /^([A-Z0-9_]+)=(.*)$/.exec(line.trim());
    if (m) out[m[1]] = m[2];
  }
  return out;
}

function baseEnv(mode) {
  return {
    ...process.env,
    ...loadEnvFile(),
    BRANDME_MODE: mode,
    SPANNER_EMULATOR_HOST: process.env.SPANNER_EMULATOR_HOST ?? `localhost:${PORTS.spanner}`,
    SPANNER_PROJECT_ID: process.env.SPANNER_PROJECT_ID ?? 'test-project',
    SPANNER_INSTANCE_ID: process.env.SPANNER_INSTANCE_ID ?? 'brandme-instance',
    SPANNER_DATABASE_ID: process.env.SPANNER_DATABASE_ID ?? 'brandme-db',
    PYTHONPATH: ROOT,
    BRAIN_SERVICE_URL: `http://localhost:${PORTS.brain}`,
    PORT: String(PORTS.gateway),
    CORS_ORIGINS: `http://localhost:${PORTS.consumer},http://localhost:${PORTS.console}`,
    PUBLIC_ORIGINS: `http://localhost:${PORTS.consumer},http://localhost:${PORTS.console}`,
  };
}

const run = (bin, argv, opts = {}) => spawnSync(bin, argv, { cwd: ROOT, stdio: 'inherit', ...opts });
const capture = (bin, argv, opts = {}) => spawnSync(bin, argv, { cwd: ROOT, encoding: 'utf8', ...opts });

function portOpen(port, host = '127.0.0.1') {
  return new Promise((res) => {
    const s = createConnection({ host, port }, () => { s.end(); res(true); });
    s.on('error', () => res(false));
    s.setTimeout(800, () => { s.destroy(); res(false); });
  });
}

async function waitFor(name, check, seconds) {
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    if (await check()) return;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`${name} not ready after ${seconds}s`);
}

// ---- runtime validation ---------------------------------------------------

function checkRuntimes() {
  const problems = [];
  const wantNode = readFileSync(join(ROOT, '.nvmrc'), 'utf8').trim();
  if (process.versions.node !== wantNode) problems.push(`Node ${wantNode} required (found ${process.versions.node}); see .nvmrc`);
  const pkg = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
  const wantPnpm = pkg.packageManager.split('@')[1];
  const pnpm = capture('pnpm', ['--version']);
  if (pnpm.status !== 0 || pnpm.stdout.trim() !== wantPnpm) problems.push(`pnpm ${wantPnpm} required (found ${pnpm.stdout?.trim() || 'none'}); run: corepack enable`);
  const py = capture(PY, ['--version']);
  if (py.status !== 0 || !py.stdout.startsWith('Python 3.11')) problems.push(`Python 3.11 required at ${PY} (found ${py.stdout?.trim() || py.stderr?.trim() || 'none'})`);
  return problems;
}

async function ensureEmulator() {
  if (await portOpen(PORTS.spanner)) return 'already running';
  const docker = capture('docker', ['info']);
  if (docker.status !== 0) {
    throw new Error(`Spanner emulator not reachable on :${PORTS.spanner} and docker is unavailable. Start one with: gcloud emulators spanner start, or docker run -p 9010:9010 -p 9020:9020 ${EMULATOR_IMAGE}`);
  }
  const existing = capture('docker', ['ps', '-a', '--filter', 'name=^brandme-spanner$', '--format', '{{.Names}}']).stdout.trim();
  const r = existing
    ? capture('docker', ['start', 'brandme-spanner'])
    : capture('docker', ['run', '-d', '--name', 'brandme-spanner', '-p', '9010:9010', '-p', '9020:9020', EMULATOR_IMAGE]);
  if (r.status !== 0) throw new Error(`docker could not start the emulator: ${r.stderr}`);
  await waitFor('Spanner emulator', () => portOpen(PORTS.spanner), 60);
  return 'started (docker brandme-spanner)';
}

function migrate(env) {
  const r = run(PY, ['brandme-data/spanner/migrations/runner.py', 'up', '--create-database', '--wait', '60'], { env });
  if (r.status !== 0) throw new Error('migrations failed (see output above)');
}

// ---- commands ---------------------------------------------------------------

async function setup(mode) {
  console.log(`Brand.Me setup (${mode})`);
  if (!process.env.BRANDME_PYTHON && !existsSync(VENV_PY)) {
    // Project venv from the hashed lock (idempotent: skipped when present).
    const uv = capture('uv', ['--version']);
    const made = uv.status === 0
      ? run('uv', ['venv', '-p', '3.11', '.venv']).status === 0 && run('uv', ['pip', 'sync', '--python', '.venv/bin/python', 'scripts/python/requirements.lock']).status === 0
      : run('python3.11', ['-m', 'venv', '.venv']).status === 0 && run(VENV_PY, ['-m', 'pip', 'install', '--require-hashes', '-r', 'scripts/python/requirements.lock']).status === 0;
    if (!made) fail('could not create .venv from scripts/python/requirements.lock (needs uv or python3.11)');
    PY = VENV_PY;
    console.log(c.ok('✓ .venv from scripts/python/requirements.lock'));
  }
  const remaining = checkRuntimes();
  if (remaining.length) fail(`missing prerequisites:\n  - ${remaining.join('\n  - ')}`);
  console.log(c.ok('✓ runtimes'));
  if (run('pnpm', ['install', '--frozen-lockfile']).status !== 0) fail('pnpm install --frozen-lockfile failed');
  console.log(c.ok('✓ node dependencies (frozen lockfile)'));
  const envLocal = join(ROOT, '.env.local');
  if (!existsSync(envLocal)) {
    copyFileSync(join(ROOT, '.env.example'), envLocal);
    writeFileSync(envLocal, readFileSync(envLocal, 'utf8').replace(/^BRANDME_MODE=.*$/m, `BRANDME_MODE=${mode}`));
    console.log(c.ok('✓ wrote .env.local (no secrets; safe local defaults)'));
  }
  console.log(c.ok(`✓ Spanner emulator ${await ensureEmulator()}`));
  migrate(baseEnv(mode));
  console.log(c.ok('✓ migrations applied'));
  console.log(c.warn('! Demo fixtures, licensed assets and deterministic providers are delivered by later work packages (W03–W06).'));
  console.log(`Next: pnpm dev:${mode === 'demo' ? 'demo' : ''}`.replace(/:$/, ''));
}

function startServices(mode, { withFrontend }) {
  const env = baseEnv(mode);
  const children = [];
  const start = (name, bin, argv, opts) => {
    const child = spawn(bin, argv, { cwd: ROOT, env, stdio: ['ignore', 'pipe', 'pipe'], ...opts });
    const tag = c.dim(`[${name}]`);
    child.stdout.on('data', (d) => process.stdout.write(d.toString().replace(/^/gm, `${tag} `)));
    child.stderr.on('data', (d) => process.stderr.write(d.toString().replace(/^/gm, `${tag} `)));
    child.on('exit', (code) => code && console.error(c.bad(`${name} exited with ${code}`)));
    children.push(child);
    return child;
  };
  const pre = capture(PY, ['-m', 'brandme_core.config', 'preflight', '--service', 'brain'], { env });
  process.stdout.write(pre.stdout);
  if (pre.status !== 0) fail(pre.stderr.trim());
  start('brain', PY, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(PORTS.brain)], { cwd: join(ROOT, 'brandme-core/brain') });
  start('gateway', 'pnpm', ['--filter', '@brandme/gateway', 'exec', 'tsx', 'src/index.ts']);
  if (withFrontend) start('consumer', 'pnpm', ['--filter', 'brandme-frontend', 'exec', 'next', 'dev', '-p', String(PORTS.consumer)]);
  const stop = () => children.forEach((ch) => ch.exitCode === null && ch.kill('SIGTERM'));
  process.on('SIGINT', () => { stop(); process.exit(0); });
  process.on('SIGTERM', () => { stop(); process.exit(0); });
  return { env, stop };
}

async function dev(mode) {
  if (mode !== 'demo' && mode !== 'development') {
    fail(`dev runs demo or development locally; ${mode} needs its deployed configuration`);
  }
  const problems = checkRuntimes();
  if (problems.length) fail(`missing prerequisites (run pnpm setup:demo):\n  - ${problems.join('\n  - ')}`);
  for (const [name, port] of Object.entries(PORTS)) {
    if (name !== 'spanner' && name !== 'console' && name !== 'policy' && (await portOpen(port))) fail(`port ${port} (${name}) is already in use`);
  }
  await ensureEmulator();
  migrate(baseEnv(mode));
  startServices(mode, { withFrontend: true });
  await waitFor('gateway', () => portOpen(PORTS.gateway), 60).catch((e) => fail(e.message));
  console.log(`\n${c.ok('Brand.Me is running')} (BRANDME_MODE=${mode})
  consumer  http://localhost:${PORTS.consumer}
  gateway   http://localhost:${PORTS.gateway}/api/v1/system/health
  brain     http://localhost:${PORTS.brain}/health
  Sign-in is the labelled dev identity simulation: POST /api/v1/session/dev {"test_identity":"you"}
  Ctrl-C to stop.\n`);
}

async function smoke() {
  const mode = 'development';
  const report = { started_at: new Date().toISOString(), mode, steps: [] };
  const step = (name, ok, detail = '') => {
    report.steps.push({ name, result: ok ? 'passed' : 'failed', detail });
    console.log(`${ok ? c.ok('✓') : c.bad('✖')} ${name}${detail ? c.dim(` — ${detail}`) : ''}`);
    return ok;
  };
  let svc;
  try {
    for (const p of [PORTS.brain, PORTS.gateway]) if (await portOpen(p)) throw new Error(`port ${p} busy; stop running services first`);
    step('spanner emulator', true, await ensureEmulator());
    migrate(baseEnv(mode));
    step('migrations to V001', true);
    svc = startServices(mode, { withFrontend: false });
    await waitFor('brain', () => portOpen(PORTS.brain), 60);
    await waitFor('gateway', () => portOpen(PORTS.gateway), 60);
    const gw = `http://localhost:${PORTS.gateway}/api/v1`;
    const health = await fetch(`${gw}/system/health`);
    const hb = await health.json();
    step('gateway → brain → Spanner health', health.status === 200 && hb.status === 'ok', JSON.stringify(hb.checks));
    const origin = `http://localhost:${PORTS.consumer}`;
    const identity = `smoke-${Date.now()}`;
    const s = await fetch(`${gw}/session/dev`, { method: 'POST', headers: { 'content-type': 'application/json', origin }, body: JSON.stringify({ test_identity: identity }) });
    const sb = await s.json();
    const cookie = (s.headers.get('set-cookie') ?? '').split(';')[0];
    step('dev session (labelled simulation)', s.status === 201 && /Simulated/.test(s.headers.get('x-brandme-simulation') ?? ''), `member ${sb.member_id}`);
    const patch = await fetch(`${gw}/me`, { method: 'PATCH', headers: { 'content-type': 'application/json', cookie, origin, 'x-csrf-token': sb.csrf_token, 'if-match': '"1"' }, body: JSON.stringify({ display_name: 'Smoke Test' }) });
    step('PATCH /me with If-Match + CSRF', patch.status === 200, `etag ${patch.headers.get('etag')}`);
    svc.stop();
    await waitFor('gateway stopped', async () => !(await portOpen(PORTS.gateway)), 20);
    svc = startServices(mode, { withFrontend: false });
    await waitFor('gateway restart', () => portOpen(PORTS.gateway), 60);
    const me = await (await fetch(`${gw}/me`, { headers: { cookie } })).json();
    step('profile survives gateway + brain restart', me.member?.display_name === 'Smoke Test' && me.member?.version === '2');
    const disp = capture(PY, ['-c', `
import brandme_core.domains, os
from google.cloud import spanner
from brandme_core.events import OutboxDispatcher
db = spanner.Client(project=os.environ['SPANNER_PROJECT_ID']).instance(os.environ['SPANNER_INSTANCE_ID']).database(os.environ['SPANNER_DATABASE_ID'])
seen = []
def deliver(ev):
    ev.validate()
    if ev.aggregate_id == '${sb.member_id}': seen.append(ev.event_type)
OutboxDispatcher(db, deliver).run_once()
print(','.join(sorted(seen)))
`], { env: baseEnv(mode) });
    step('outbox events validated + dispatched (Python)', disp.status === 0 && disp.stdout.includes('member.created') && disp.stdout.includes('member.updated'), disp.stdout.trim() || disp.stderr.trim().split('\n').pop());
  } catch (e) {
    step('smoke aborted', false, e.message);
  } finally {
    svc?.stop();
  }
  report.finished_at = new Date().toISOString();
  report.result = report.steps.every((s) => s.result === 'passed') ? 'passed' : 'failed';
  const out = join(ROOT, 'docs/build/evidence/w00/smoke-latest.json');
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, JSON.stringify(report, null, 2) + '\n');
  console.log(`\nsmoke ${report.result === 'passed' ? c.ok('PASSED') : c.bad('FAILED')} → ${out.replace(ROOT + '/', '')}`);
  process.exit(report.result === 'passed' ? 0 : 1);
}

async function check() {
  const results = [];
  const emulator = await portOpen(PORTS.spanner);
  const env = { ...baseEnv('development') };
  const steps = [
    ['spec package validator', PY, ['docs/design/brandme/contracts/validate_spec.py']],
    ['contract + token drift', 'pnpm', ['contracts:check']],
    ['packages type-check', 'pnpm', ['--filter', './packages/*', 'type-check']],
    ['packages tests', 'pnpm', ['--filter', './packages/*', 'test']],
    ['gateway type-check', 'pnpm', ['--filter', '@brandme/gateway', 'type-check']],
    ['gateway tests' + (emulator ? '' : ' (emulator suites skipped)'), 'pnpm', ['--filter', '@brandme/gateway', 'exec', 'vitest', 'run']],
    ['python foundation tests' + (emulator ? '' : ' (emulator suites skipped)'), PY, ['-m', 'pytest', 'tests/foundation', '-q', '-p', 'no:cacheprovider', '--timeout=120']],
    ['docs/build links', process.execPath, [fileURLToPath(import.meta.url), 'links']],
  ];
  for (const [name, bin, argv] of steps) {
    const t0 = Date.now();
    const r = capture(bin, argv, { env });
    const ok = r.status === 0;
    results.push({ name, result: ok ? 'passed' : 'failed', seconds: (Date.now() - t0) / 1000 });
    console.log(`${ok ? c.ok('✓') : c.bad('✖')} ${name} ${c.dim(`${((Date.now() - t0) / 1000).toFixed(1)}s`)}`);
    if (!ok) console.log((r.stdout + r.stderr).split('\n').slice(-25).join('\n'));
  }
  if (!emulator) console.log(c.warn(`! Spanner emulator not reachable on :${PORTS.spanner}; emulator suites were skipped (not_run), not passed.`));
  process.exit(results.every((r) => r.result === 'passed') ? 0 : 1);
}

function links() {
  const files = capture('git', ['ls-files', 'docs/build', 'packages/*/README.md', 'brandme-data/spanner/migrations']).stdout.split('\n').filter((f) => f.endsWith('.md'));
  let bad = 0;
  for (const f of files) {
    const text = readFileSync(join(ROOT, f), 'utf8');
    for (const m of text.matchAll(/\]\((?!https?:|#|mailto:)([^)\s]+)\)/g)) {
      const target = resolve(dirname(join(ROOT, f)), m[1].split('#')[0]);
      if (!existsSync(target)) { console.error(`${f}: broken link ${m[1]}`); bad++; }
    }
  }
  process.exit(bad ? 1 : 0);
}

function evidence() {
  const catalog = JSON.parse(readFileSync(join(ROOT, 'docs/design/brandme/contracts/acceptance-catalog.json'), 'utf8'));
  const resultsFile = join(ROOT, 'docs/build/evidence/results.json');
  const recorded = existsSync(resultsFile) ? JSON.parse(readFileSync(resultsFile, 'utf8')).results ?? {} : {};
  const allowed = new Set(catalog.allowed_result_statuses);
  const counts = {};
  const rows = catalog.requirements.map((r) => {
    const rec = recorded[r.id];
    const status = rec && allowed.has(rec.status) ? rec.status : 'not_run';
    if (status !== 'not_run' && status !== 'not_applicable' && !rec.evidence) throw new Error(`${r.id}: ${status} without evidence`);
    if (status === 'not_applicable' && !rec.reason) throw new Error(`${r.id}: not_applicable without reason`);
    counts[status] = (counts[status] ?? 0) + 1;
    return { id: r.id, stage: r.stage, status, evidence: rec?.evidence ?? null };
  });
  console.log(`acceptance catalog: ${rows.length} requirements`);
  for (const [k, v] of Object.entries(counts)) console.log(`  ${k}: ${v}`);
  for (const r of rows.filter((x) => x.status !== 'not_run')) console.log(`  ${r.id} [${r.stage}] ${r.status} — ${r.evidence ?? ''}`);
}

function notYet(name, stage) {
  console.error(c.warn(`${name} is not implemented yet: it belongs to ${stage}. Nothing was run; this is not a pass.`));
  process.exit(2);
}

const commands = {
  setup: () => setup(opt('mode', 'demo')),
  dev: () => dev(opt('mode', 'development')),
  smoke,
  check,
  links,
  migrate: () => migrate(baseEnv(opt('mode', 'development'))),
  evidence,
  'not-yet': () => notYet(args[1], args[2]),
};
if (!commands[cmd]) fail(`unknown command ${cmd}; one of ${Object.keys(commands).join(', ')}`);
Promise.resolve(commands[cmd]()).catch((e) => fail(e.message));
