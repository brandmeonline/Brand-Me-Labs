// Tests for scripts/check-workspace.mjs (node:test, Node built-ins only).
//   node --test scripts/check-workspace.test.mjs
// Every rule runs against a synthetic git repo in a temp dir. The --with-pnpm cases need the
// pinned pnpm on PATH (corepack enable, or pnpm/action-setup in CI) and skip without it.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { actionSteps, checkWorkspace, CODES, parseLockfile, parseWorkspacePackages, STANDALONE, workspaceMatcher } from './check-workspace.mjs';

const GUARD = fileURLToPath(new URL('./check-workspace.mjs', import.meta.url));
const REPO = fileURLToPath(new URL('..', import.meta.url));
const PNPM = JSON.parse(readFileSync(join(REPO, 'package.json'), 'utf8')).packageManager.replace(/^pnpm@/, '').split('+')[0];
const NODE = readFileSync(join(REPO, '.nvmrc'), 'utf8').trim();
const OTHER = '8.15.0'; // a pnpm version that is not the pin
const json = (o) => JSON.stringify(o, null, 2) + '\n';

// Minimal v9 lockfile text: importers = { dir: { section: { name: specifier } } }.
function lockText(importers, version = "'9.0'") {
  let out = `lockfileVersion: ${version}\n\nsettings:\n  autoInstallPeers: true\n  excludeLinksFromLockfile: false\n\nimporters:\n`;
  for (const [dir, sections] of Object.entries(importers)) {
    const names = Object.keys(sections);
    out += `\n  ${dir}:${names.length ? '' : ' {}'}\n`;
    for (const s of names) {
      out += `    ${s}:\n`;
      for (const [n, spec] of Object.entries(sections[s])) {
        const key = /^[@']/.test(n) ? `'${n}'` : n;
        const version = spec.startsWith('workspace:') ? `link:../${n.split('/').pop()}` : spec;
        out += `      ${key}:\n        specifier: ${spec}\n        version: ${version}\n`;
      }
    }
  }
  return out + '\npackages: {}\n';
}

const WORKFLOW = `name: CI
on: [pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version-file: .nvmrc
      # comment between steps
      - name: Setup pnpm
        uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - uses: azure/setup-helm@v4
        with:
          version: '3.13.0'
`;

function baseFiles() {
  return {
    'package.json': json({ name: 'fixture', private: true, scripts: { check: 'node scripts/check.mjs' }, engines: { node: '>=20.0.0 <25', pnpm: PNPM }, packageManager: `pnpm@${PNPM}` }),
    'pnpm-workspace.yaml': "# fixture\npackages:\n  - 'packages/*'\n\nonlyBuiltDependencies:\n  - esbuild\n",
    'packages/a/package.json': json({ name: '@brandme/a', private: true, dependencies: { '@brandme/b': 'workspace:*' } }),
    'packages/b/package.json': json({ name: '@brandme/b', private: true, devDependencies: { typescript: '5.9.3' } }),
    'pnpm-lock.yaml': lockText({ '.': {}, 'packages/a': { dependencies: { '@brandme/b': 'workspace:*' } }, 'packages/b': { devDependencies: { typescript: '5.9.3' } } }),
    '.nvmrc': `${NODE}\n`,
    '.node-version': `${NODE}\n`,
    '.github/workflows/ci.yml': WORKFLOW,
    'svc/Dockerfile': `ARG NODE_VERSION=${NODE}\nFROM node:\${NODE_VERSION}-bookworm-slim AS build\nRUN corepack enable && corepack prepare pnpm@${PNPM} --activate\n`,
    'docker-compose.yml': `services:\n  web:\n    image: node:${NODE}-bookworm-slim\n    command: ["sh", "-c", "corepack enable && pnpm install --frozen-lockfile"]\n`,
  };
}

function write(dir, files) {
  for (const [path, content] of Object.entries(files)) {
    if (content === null) {
      rmSync(join(dir, path), { force: true });
      continue;
    }
    mkdirSync(dirname(join(dir, path)), { recursive: true });
    writeFileSync(join(dir, path), content);
  }
}

const tmpRoot = mkdtempSync(join(tmpdir(), 'check-workspace-'));
process.on('exit', () => rmSync(tmpRoot, { recursive: true, force: true }));
let n = 0;

// A temp git repo: `files` overrides baseFiles() (null deletes), all of it staged; `untracked` is written after.
function repo(files = {}, { untracked = {}, base = true } = {}) {
  const dir = join(tmpRoot, `r${n++}`);
  mkdirSync(dir);
  write(dir, { ...(base ? baseFiles() : {}), ...files });
  const g = spawnSync('git', ['-c', 'init.defaultBranch=main', 'init', '-q'], { cwd: dir });
  assert.equal(g.status, 0, String(g.stderr));
  assert.equal(spawnSync('git', ['add', '-A'], { cwd: dir }).status, 0);
  write(dir, untracked);
  return dir;
}

const check = (dir, opts = {}) => checkWorkspace({ root: dir, standalone: {}, ...opts });
const codes = (list) => [...new Set(list.map((f) => f.code))].sort();
async function expectOnly(dir, code, opts) {
  const r = await check(dir, opts);
  assert.deepEqual(codes(r.errors), [code], JSON.stringify(r.errors, null, 2));
  return r;
}
const cli = (args, env = {}) => spawnSync(process.execPath, [GUARD, ...args], { encoding: 'utf8', env: { ...process.env, GITHUB_ACTIONS: '', ...env } });

function pnpmUsable(dir) {
  const r = spawnSync('pnpm', ['--version'], { cwd: dir, encoding: 'utf8', env: { ...process.env, COREPACK_ENABLE_DOWNLOAD_PROMPT: '0' } });
  return r.status === 0 && r.stdout.trim() === PNPM;
}

// ---- baseline ------------------------------------------------------------------------

test('the synthetic baseline is clean', async () => {
  const r = await check(repo());
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.warnings, []);
  assert.deepEqual(r.registered, ['.', 'packages/a', 'packages/b']);
});

test('the current tree is clean (offline checks)', () => {
  const r = cli(['--json', '--root', REPO]);
  const out = JSON.parse(r.stdout);
  assert.deepEqual(out.errors, [], r.stdout);
  assert.equal(r.status, 0);
  assert.equal(out.pnpm, PNPM);
  assert.ok(out.registered.includes('brandme-frontend'), 'brandme-frontend must be a workspace member');
});

test('the shipped STANDALONE map has a reason for every entry', () => {
  for (const [dir, reason] of Object.entries(STANDALONE)) assert.ok(dir && typeof reason === 'string' && reason.trim(), dir);
});

test('every code has a fix hint', async () => {
  const src = readFileSync(GUARD, 'utf8');
  for (const m of src.matchAll(/\b(?:err|warn)\('([EW]_[A-Z_]+)'/g)) assert.ok(CODES[m[1]], `${m[1]} has no CODES entry`);
});

// ---- membership ----------------------------------------------------------------------

test('E_UNREGISTERED: a tracked package.json that no workspace glob matches', async () => {
  const r = await expectOnly(repo({ 'brandme-frontend/package.json': json({ name: 'brandme-frontend', private: true, devDependencies: { typescript: '5.9.3' } }) }), 'E_UNREGISTERED');
  assert.equal(r.errors[0].file, 'brandme-frontend/package.json');
});

test('STANDALONE: an allowlisted directory may keep its own manifest and pnpm-lock.yaml', async () => {
  const files = { 'scripts/assets/package.json': json({ name: '@brandme/assets', private: true, devDependencies: { three: '0.182.0' } }), 'scripts/assets/pnpm-lock.yaml': lockText({ '.': { devDependencies: { three: '0.182.0' } } }) };
  const r = await check(repo(files), { standalone: { 'scripts/assets': 'isolated asset tools' } });
  assert.deepEqual(r.errors, []);
  const noLock = await check(repo({ ...files, 'scripts/assets/pnpm-lock.yaml': null }), { standalone: { 'scripts/assets': 'isolated asset tools' } });
  assert.deepEqual(codes(noLock.warnings), ['W_STANDALONE_NO_LOCK']);
  const oldLock = await check(repo({ ...files, 'scripts/assets/pnpm-lock.yaml': lockText({ '.': {} }, "'6.0'") }), { standalone: { 'scripts/assets': 'isolated asset tools' } });
  assert.deepEqual(codes(oldLock.errors), ['E_LOCK_VERSION']);
});

test('E_ALLOWLIST_CONFLICT: a STANDALONE directory that a glob also matches', async () => {
  await expectOnly(repo(), 'E_ALLOWLIST_CONFLICT', { standalone: { 'packages/b': 'should not be both' } });
});

test('E_ALLOWLIST_STALE: entries without a tracked manifest, a reason or a normalized path', async () => {
  const dir = repo({ 'tools/x/package.json': json({ name: '@brandme/x', private: true }) });
  for (const standalone of [{ 'tools/gone': 'deleted' }, { 'tools/x': '  ' }, { './tools/x': 'dot slash' }, { 'tools/x/': 'trailing slash' }]) {
    const r = await check(dir, { standalone });
    assert.ok(codes(r.errors).includes('E_ALLOWLIST_STALE'), JSON.stringify(standalone));
  }
});

test('workspace globs follow pnpm semantics (verified against pnpm 10.34.6)', () => {
  const globs = parseWorkspacePackages(
    "packages:\n  - 'tests/*'\n  - \"packages/*\"   # quoted\n  - '!packages/skip'\n  - apps/**\n  - 'tools/*/'\n  - 'libs/{a,b}'\n  - 'q/?x'\n  - ./dot/*\n",
  );
  const member = workspaceMatcher(globs);
  const yes = ['.', 'tests/x', 'packages/ok', 'apps', 'apps/a', 'apps/a/b', 'apps/test/z', 'tools/t1', 'libs/a', 'q/ax', 'dot/d'];
  const no = ['packages/.hidden', 'packages/skip', 'apps/.cfg/x', 'apps/bower_components/k', 'packages/ok/node_modules/dep', 'libs/c', 'q/abx', 'tools', 'other'];
  for (const d of yes) assert.ok(member(d), `${d} should be a member`);
  for (const d of no) assert.ok(!member(d), `${d} should not be a member`);
  // A negation excludes only <dir>/package.json, not the subtree, unless it ends in /**.
  const neg = workspaceMatcher(['packages/**', '!packages/skip', '!packages/neg/**']);
  assert.deepEqual(['packages/ok', 'packages/skip', 'packages/skip/sub', 'packages/neg', 'packages/neg/x'].filter(neg), ['packages/ok', 'packages/skip/sub']);
});

test('parseWorkspacePackages fails closed on shapes it cannot read', () => {
  assert.throws(() => parseWorkspacePackages('onlyBuiltDependencies:\n  - esbuild\n'), /no top-level `packages:`/);
  assert.throws(() => parseWorkspacePackages("packages: ['a', 'b']\n"), /block list/);
  assert.throws(() => parseWorkspacePackages('packages:\n'), /empty/);
  assert.throws(() => parseWorkspacePackages('packages:\n  - a\n  b: c\n'), /unexpected line/);
  assert.deepEqual(parseWorkspacePackages("packages:\n- a\n- 'b#c' # note\nother: 1\n"), ['a', 'b#c']);
  assert.throws(() => workspaceMatcher(['apps/+(a|b)']), /unsupported glob/);
  assert.throws(() => workspaceMatcher(['apps/{1..3}']), /brace/);
});

test('E_WS_CONFIG: missing pnpm-workspace.yaml or an unsupported glob', async () => {
  await expectOnly(repo({ 'pnpm-workspace.yaml': null }), 'E_WS_CONFIG');
  await expectOnly(repo({ 'pnpm-workspace.yaml': 'packages:\n  - packages/@(a|b)\n' }), 'E_WS_CONFIG');
});

test('E_MANIFEST_JSON: a package.json that does not parse', async () => {
  const r = await check(repo({ 'packages/b/package.json': '{ "name": "@brandme/b", }\n' }));
  assert.ok(codes(r.errors).includes('E_MANIFEST_JSON'));
});

// ---- lockfile -------------------------------------------------------------------------

test('E_IMPORTER_MISSING: a registered package (even a zero-dependency one) with no importer', async () => {
  await expectOnly(repo({ 'packages/c/package.json': json({ name: '@brandme/c', private: true, devDependencies: { typescript: '5.9.3' } }) }), 'E_IMPORTER_MISSING');
  await expectOnly(repo({ 'packages/empty/package.json': json({ name: '@brandme/empty', private: true }) }), 'E_IMPORTER_MISSING');
});

test('E_IMPORTER_ORPHAN: an importer whose package is gone or unregistered', async () => {
  await expectOnly(repo({ 'packages/b/package.json': null, 'packages/a/package.json': json({ name: '@brandme/a', private: true }) , 'pnpm-lock.yaml': lockText({ '.': {}, 'packages/a': {}, 'packages/b': { devDependencies: { typescript: '5.9.3' } } }) }), 'E_IMPORTER_ORPHAN');
  const r = await check(repo({ 'pnpm-workspace.yaml': "packages:\n  - 'packages/*'\n  - '!packages/b'\n" }));
  assert.deepEqual(codes(r.errors), ['E_IMPORTER_ORPHAN', 'E_UNREGISTERED']);
});

test('E_IMPORTER_STALE: missing, extra and section-moved dependency names', async () => {
  const add = await expectOnly(repo({ 'packages/b/package.json': json({ name: '@brandme/b', private: true, devDependencies: { typescript: '5.9.3', 'left-pad': '1.3.0' } }) }), 'E_IMPORTER_STALE');
  assert.match(add.errors[0].message, /missing \[left-pad\]/);
  const drop = await expectOnly(repo({ 'packages/b/package.json': json({ name: '@brandme/b', private: true }) }), 'E_IMPORTER_STALE');
  assert.match(drop.errors[0].message, /not in manifest \[typescript\]/);
  const moved = await expectOnly(repo({ 'packages/b/package.json': json({ name: '@brandme/b', private: true, dependencies: { typescript: '5.9.3' } }) }), 'E_IMPORTER_STALE');
  assert.match(moved.errors[0].message, /section changed \[typescript \(devDependencies -> dependencies\)\]/);
});

test('importer comparison ignores specifiers and follows pnpm precedence and autoInstallPeers', async () => {
  // Overrides rewrite specifiers (postcss ^8.4.32 is recorded as 8.5.23), so only names/sections count.
  const spec = await check(repo({ 'packages/b/package.json': json({ name: '@brandme/b', private: true, devDependencies: { typescript: '^5.9.0' } }) }));
  assert.deepEqual(spec.errors, []);
  // dependencies beats devDependencies; optionalDependencies beats both; peers may appear anywhere.
  const files = {
    'packages/a/package.json': json({ name: '@brandme/a', private: true, dependencies: { '@brandme/b': 'workspace:*', x: '1.0.0' }, devDependencies: { '@brandme/b': 'workspace:*' }, optionalDependencies: { x: '1.0.0' }, peerDependencies: { react: '^18' } }),
    'pnpm-lock.yaml': lockText({ '.': {}, 'packages/a': { dependencies: { '@brandme/b': 'workspace:*', react: '18.3.1' }, optionalDependencies: { x: '1.0.0' } }, 'packages/b': { devDependencies: { typescript: '5.9.3' } } }),
  };
  assert.deepEqual((await check(repo(files))).errors, []);
});

test('E_LOCK_VERSION / E_LOCK_MISSING / E_LOCK_PARSE fail closed', async () => {
  await expectOnly(repo({ 'pnpm-lock.yaml': lockText({ '.': {} }, "'6.0'") }), 'E_LOCK_VERSION');
  await expectOnly(repo({ 'pnpm-lock.yaml': "lockfileVersion: '10.0'\n\nimporters:\n\n  .: {}\n" }), 'E_LOCK_VERSION');
  await expectOnly(repo({ 'pnpm-lock.yaml': null }), 'E_LOCK_MISSING');
  await expectOnly(repo({ 'pnpm-lock.yaml': "lockfileVersion: '9.0'\n\npackages: {}\n" }), 'E_LOCK_PARSE');
  await expectOnly(repo({ 'pnpm-lock.yaml': "lockfileVersion: '9.0'\n\nimporters:\n\n  .:\n    dependencies:\n      left-pad: 1.3.0\n" }), 'E_LOCK_PARSE');
  await expectOnly(repo({ 'pnpm-lock.yaml': "lockfileVersion: '9.0'\n\nimporters:\n    dependencies:\n      left-pad:\n" }), 'E_LOCK_PARSE');
  assert.equal(parseLockfile("lockfileVersion: '9.0'\nimporters:\n\n  .: {}\n").importers.get('.').deps.size, 0);
});

test('E_NESTED_LOCKFILE: lockfiles outside the root and STANDALONE directories', async () => {
  await expectOnly(repo({ 'packages/a/pnpm-lock.yaml': lockText({ '.': {} }) }), 'E_NESTED_LOCKFILE');
  await expectOnly(repo({ 'package-lock.json': '{}\n' }), 'E_NESTED_LOCKFILE');
  await expectOnly(repo({ 'packages/b/yarn.lock': '# yarn\n' }), 'E_NESTED_LOCKFILE');
});

// ---- pnpm pin ----------------------------------------------------------------------------

test('E_PM_FORMAT: root packageManager must be an exact pnpm@x.y.z', async () => {
  for (const pm of [`pnpm@${PNPM.split('.')[0]}`, 'npm@10.9.0', `pnpm@^${PNPM}`, undefined]) {
    const pkg = { name: 'fixture', private: true, packageManager: pm };
    await expectOnly(repo({ 'package.json': json(pkg) }), 'E_PM_FORMAT');
  }
  const sha = await check(repo({ 'package.json': json({ name: 'fixture', private: true, packageManager: `pnpm@${PNPM}+sha512.${'ab'.repeat(32)}` }) }));
  assert.deepEqual(sha.errors, []);
});

test('E_PM_ENGINES: root engines.pnpm must equal packageManager', async () => {
  await expectOnly(repo({ 'package.json': json({ name: 'fixture', private: true, engines: { pnpm: '>=8.0.0' }, packageManager: `pnpm@${PNPM}` }) }), 'E_PM_ENGINES');
});

test('E_PM_NESTED: a nested packageManager that differs from the root', async () => {
  const r = await expectOnly(repo({ 'packages/b/package.json': json({ name: '@brandme/b', private: true, devDependencies: { typescript: '5.9.3' }, packageManager: 'pnpm@11.25.0' }) }), 'E_PM_NESTED');
  assert.equal(r.errors[0].line, 7);
  const same = await check(repo({ 'packages/b/package.json': json({ name: '@brandme/b', private: true, devDependencies: { typescript: '5.9.3' }, packageManager: `pnpm@${PNPM}` }) }));
  assert.deepEqual(same.errors, []);
});

test('E_PNPM_FIELD: pnpm settings or membership in the root package.json', async () => {
  for (const extra of [{ pnpm: { packageExtensions: { '@react-three/fiber@9.4.0': { peerDependencies: { '@types/react': '^19.0.0' } } } } }, { resolutions: { postcss: '8.5.23' } }, { workspaces: ['packages/*'] }]) {
    await expectOnly(repo({ 'package.json': json({ name: 'fixture', private: true, packageManager: `pnpm@${PNPM}`, ...extra }) }), 'E_PNPM_FIELD');
  }
});

test('E_ACTION_PNPM_VERSION: any version input on pnpm/action-setup, in any step layout', async () => {
  const layouts = [
    '      - name: Setup pnpm\n        uses: pnpm/action-setup@v4\n        with:\n          version: 8\n',
    `      - uses: pnpm/action-setup@v4\n        with:\n          run_install: false\n          version: ${PNPM}\n`,
    '      - name: Setup pnpm\n        with:\n          version: 10   # before uses\n        uses: pnpm/action-setup@v4\n',
    "      - uses: 'pnpm/action-setup@v4'\n        with: { version: 9 }\n",
    '      - uses: pnpm/action-setup@a7487c7e89a18df4991f7f222e4898a00d66ddda # v4.1.0\n        with:\n          # pinned\n          version: "8"\n',
  ];
  for (const steps of layouts) {
    const wf = `name: X\non: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n${steps}      - run: pnpm -v\n`;
    const r = await expectOnly(repo({ '.github/workflows/x.yml': wf }), 'E_ACTION_PNPM_VERSION');
    assert.ok(r.errors[0].line > 8, steps);
  }
  // `version:` on a later step or another action is not the pnpm step's input.
  const later = 'name: X\non: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: pnpm/action-setup@v4\n      - uses: azure/setup-helm@v4\n        with:\n          version: 3.13.0\n';
  assert.deepEqual((await check(repo({ '.github/workflows/x.yml': later }))).errors, []);
  const composite = 'name: setup\nruns:\n  using: composite\n  steps:\n    - uses: pnpm/action-setup@v4\n      with:\n        version: 8\n';
  await expectOnly(repo({ '.github/actions/setup/action.yml': composite }), 'E_ACTION_PNPM_VERSION');
});

test('actionSteps reads with: inputs only from the matching step', () => {
  const steps = actionSteps(WORKFLOW, /^actions\/setup-node@/);
  assert.equal(steps.length, 1);
  assert.deepEqual(steps[0].inputs.map((i) => [i.key, i.value]), [['node-version-file', '.nvmrc']]);
  assert.deepEqual(actionSteps(WORKFLOW, /^pnpm\/action-setup@/)[0].inputs, []);
});

test('E_PNPM_PIN: pnpm installs/activations that differ from packageManager', async () => {
  const cases = {
    'svc/Dockerfile': `FROM node:${NODE}-bookworm-slim\nRUN npm install -g pnpm@${OTHER}\n`,
    'other/Dockerfile': `FROM node:${NODE}-bookworm-slim\nRUN corepack enable && corepack prepare pnpm@${OTHER.split('.')[0]} --activate\n`,
    'scripts/setup.sh': `#!/bin/sh\nnpx --yes pnpm@${OTHER} install\n`,
    'Makefile': 'install:\n\tnpm i --global pnpm && pnpm install\n',
    'docker-compose.yml': `services:\n  web:\n    image: node:${NODE}-bookworm-slim\n    command: ["sh", "-c", "corepack use pnpm@latest && pnpm dev"]\n`,
    '.tool-versions': `nodejs ${NODE}\npnpm ${OTHER}\n`,
    'package.json': json({ name: 'fixture', private: true, scripts: { bootstrap: `corepack prepare pnpm@${OTHER} --activate` }, packageManager: `pnpm@${PNPM}` }),
  };
  for (const [path, content] of Object.entries(cases)) {
    const r = await expectOnly(repo({ [path]: content }), 'E_PNPM_PIN');
    assert.equal(r.errors[0].file, path);
  }
  const ok = {
    'svc/Dockerfile': `FROM node:${NODE}-bookworm-slim\nRUN corepack enable && corepack prepare pnpm@${PNPM} --activate\n# RUN npm i -g pnpm@${OTHER}\n`,
    'scripts/setup.sh': `#!/bin/sh\necho "Install with: npm install -g pnpm"\nnpm install -g "pnpm@\${PNPM_VERSION}"\ncorepack install\n`,
    'docs/old.md': `npm i -g pnpm@${OTHER}\n`,
  };
  assert.deepEqual((await check(repo(ok))).errors, []);
});

// ---- Node pin --------------------------------------------------------------------------

test('E_NODE_LITERAL: setup-node must use node-version-file', async () => {
  const step = (w) => `name: X\non: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    strategy:\n      matrix:\n        node-version: [20]\n    steps:\n      - uses: actions/setup-node@v4\n${w}`;
  for (const w of ["        with:\n          node-version: '20'\n", '        with:\n          node-version: ${{ matrix.node-version }}\n', '', '        with:\n          node-version-file: package.json\n', '        with:\n          cache: pnpm\n']) {
    await expectOnly(repo({ '.github/workflows/x.yml': step(w) }), 'E_NODE_LITERAL');
  }
  assert.deepEqual((await check(repo({ '.github/workflows/x.yml': step('        with:\n          node-version-file: .node-version\n') }))).errors, []);
});

test('E_NODE_FILES: .nvmrc, .node-version, Dockerfile ARG/FROM and node images agree', async () => {
  const cases = [
    { '.node-version': '24.0.0\n' },
    { '.nvmrc': 'lts/*\n', '.node-version': null },
    { '.nvmrc': null },
    { 'svc/Dockerfile': `ARG NODE_VERSION=20.11.0\nFROM node:\${NODE_VERSION}-alpine\n` },
    { 'svc/Dockerfile': 'FROM node:18-alpine AS build\n' },
    { 'svc/Dockerfile': 'FROM --platform=linux/amd64 docker.io/library/node:lts\n' },
    { 'svc/Dockerfile': 'FROM node AS build\n' },
    { 'docker-compose.yml': 'services:\n  web:\n    image: "node:20-bookworm-slim"\n' },
    { 'docker-compose.yml': 'services:\n  web:\n    image: node\n' },
    { '.tool-versions': 'nodejs 22.0.0\n' },
  ];
  for (const files of cases) await expectOnly(repo(files), 'E_NODE_FILES');
  const ok = { 'svc/Dockerfile': `FROM node@sha256:${'0'.repeat(64)}\nFROM node-red:3\nFROM nodered/node-red\n`, 'docker-compose.yml': `services:\n  a:\n    image: 'node:${NODE}'\n  b:\n    image: nodered/node-red\n` };
  assert.deepEqual((await check(repo(ok))).errors, []);
});

// ---- warnings --------------------------------------------------------------------------

test('warnings: nested engines.pnpm, non-private packages, untracked manifests', async () => {
  const dir = repo(
    { 'packages/b/package.json': json({ name: '@brandme/b', devDependencies: { typescript: '5.9.3' }, engines: { pnpm: '>=8.0.0' } }) },
    { untracked: { 'packages/c/package.json': json({ name: '@brandme/c', private: true }), 'scratch/package.json': json({ name: 'scratch', private: true }) } },
  );
  const r = await check(dir);
  assert.deepEqual(codes(r.warnings), ['W_ENGINES_PNPM', 'W_NOT_PRIVATE', 'W_UNTRACKED']);
  // The untracked packages/c is matched by packages/*, so pnpm sees it and so does the guard.
  assert.deepEqual(codes(r.errors), ['E_IMPORTER_MISSING']);
  assert.ok(r.registered.includes('packages/c') && !r.registered.includes('scratch'));
});

// ---- CLI -------------------------------------------------------------------------------

test('CLI: exit codes, --json and GitHub annotations', () => {
  const clean = cli(['--root', repo()]);
  assert.equal(clean.status, 0, clean.stdout);
  assert.match(clean.stdout, /workspace guard: clean/);
  const bad = repo({ 'brandme-frontend/package.json': json({ name: 'x,y', private: true }) });
  const text = cli(['--root', bad]);
  assert.equal(text.status, 1);
  assert.match(text.stdout, /✖ E_UNREGISTERED brandme-frontend\/package\.json/);
  assert.match(text.stdout, /fix: Add the directory to pnpm-workspace.yaml/);
  const js = cli(['--json', '--root', bad]);
  assert.equal(js.status, 1);
  const out = JSON.parse(js.stdout);
  assert.equal(out.ok, false);
  assert.equal(out.errors[0].code, 'E_UNREGISTERED');
  assert.equal(out.fixes.E_UNREGISTERED, CODES.E_UNREGISTERED);
  const gh = cli(['--root', bad], { GITHUB_ACTIONS: 'true' });
  assert.match(gh.stdout, /^::error file=brandme-frontend\/package\.json,title=E_UNREGISTERED::/m);
  assert.equal(cli(['--nope']).status, 2);
  assert.equal(cli(['--help']).status, 0);
});

test('E_GIT: the guard refuses to run outside a git checkout', async () => {
  const dir = join(tmpRoot, `nogit${n++}`);
  mkdirSync(dir);
  write(dir, baseFiles());
  const ceiling = process.env.GIT_CEILING_DIRECTORIES;
  process.env.GIT_CEILING_DIRECTORIES = tmpRoot; // never discover a repo above the temp dir
  try {
    const r = await check(dir);
    assert.deepEqual(codes(r.errors), ['E_GIT']);
  } finally {
    if (ceiling === undefined) delete process.env.GIT_CEILING_DIRECTORIES;
    else process.env.GIT_CEILING_DIRECTORIES = ceiling;
  }
});

// ---- --with-pnpm -----------------------------------------------------------------------

// Workspace-only dependencies, so pnpm can write a real lockfile without the registry.
function pnpmRepo(t) {
  const dir = repo({
    'packages/a/package.json': json({ name: '@brandme/a', private: true, dependencies: { '@brandme/b': 'workspace:*' } }),
    'packages/b/package.json': json({ name: '@brandme/b', private: true }),
    'pnpm-lock.yaml': null,
  });
  if (!pnpmUsable(dir)) {
    t.skip(`pnpm ${PNPM} is not on PATH (corepack enable)`);
    return null;
  }
  const gen = spawnSync('pnpm', ['install', '--lockfile-only', '--ignore-scripts'], { cwd: dir, encoding: 'utf8' });
  assert.equal(gen.status, 0, gen.stdout + gen.stderr);
  assert.equal(spawnSync('git', ['add', '-A'], { cwd: dir }).status, 0);
  return dir;
}
const snapshot = (dir) => {
  const out = {};
  const walk = (d) => {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      if (e.name === '.git') continue;
      const p = join(d, e.name);
      if (e.isDirectory()) walk(p);
      else out[p.slice(dir.length + 1)] = readFileSync(p, 'utf8');
    }
  };
  walk(dir);
  return out;
};

test('--with-pnpm: clean workspace passes and nothing is written', async (t) => {
  const dir = pnpmRepo(t);
  if (!dir) return;
  const before = snapshot(dir);
  const r = await check(dir, { withPnpm: true });
  assert.deepEqual(r.errors, []);
  assert.equal(r.pnpmReport.length, 2, r.pnpmReport.join('\n'));
  assert.deepEqual(snapshot(dir), before);
  assert.ok(!existsSync(join(dir, 'node_modules')));
});

test('--with-pnpm: specifier-only staleness is caught by pnpm, not the offline checks', async (t) => {
  const dir = pnpmRepo(t);
  if (!dir) return;
  write(dir, { 'packages/a/package.json': json({ name: '@brandme/a', private: true, dependencies: { '@brandme/b': 'workspace:^' } }) });
  assert.deepEqual((await check(dir)).errors, []);
  const r = await check(dir, { withPnpm: true });
  assert.deepEqual(codes(r.errors), ['E_PNPM_FROZEN']);
  assert.match(r.errors[0].message, /workspace:\^/);
});

test('--with-pnpm: pnpm\'s project list matches the guard on pnpm-specific globs', async (t) => {
  const dir = repo({ 'pnpm-workspace.yaml': "packages:\n  - 'packages/*'\n  - '!packages/skip'\n  - apps/**\n  - 'libs/{a,b}'\n", 'pnpm-lock.yaml': null, 'packages/a/package.json': json({ name: '@brandme/a', private: true }), 'packages/b/package.json': json({ name: '@brandme/b', private: true }) });
  for (const [d, name] of [['packages/.hidden', 'h'], ['packages/skip', 's'], ['apps', 'apps'], ['apps/x/y', 'xy'], ['apps/.cfg/z', 'z'], ['libs/a', 'la'], ['libs/c', 'lc']]) write(dir, { [`${d}/package.json`]: json({ name: `@brandme/${name}`, private: true }) });
  if (!pnpmUsable(dir)) return t.skip(`pnpm ${PNPM} is not on PATH`);
  assert.equal(spawnSync('pnpm', ['install', '--lockfile-only', '--ignore-scripts'], { cwd: dir }).status, 0);
  assert.equal(spawnSync('git', ['add', '-A'], { cwd: dir }).status, 0);
  const r = await check(dir, { withPnpm: true, standalone: { 'packages/.hidden': 'dot dirs are never members', 'packages/skip': 'negated', 'apps/.cfg/z': 'dot path', 'libs/c': 'not in braces' } });
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.registered, ['.', 'apps', 'apps/x/y', 'libs/a', 'packages/a', 'packages/b']);
});

test('--with-pnpm: E_PNPM_RUNTIME when pnpm is not runnable', async () => {
  const bin = join(tmpRoot, `bin${n++}`);
  mkdirSync(bin);
  symlinkSync(process.execPath, join(bin, 'node'));
  const git = spawnSync('sh', ['-c', 'command -v git'], { encoding: 'utf8' }).stdout.trim();
  symlinkSync(git, join(bin, 'git'));
  const r = cli(['--json', '--with-pnpm', '--root', repo()], { PATH: bin });
  assert.equal(r.status, 1, r.stdout + r.stderr);
  assert.deepEqual(codes(JSON.parse(r.stdout).errors), ['E_PNPM_RUNTIME']);
});
