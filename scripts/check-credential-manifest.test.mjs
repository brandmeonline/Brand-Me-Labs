// Tests for scripts/check-credential-manifest.mjs against synthetic git repositories.
//   node --test scripts/check-credential-manifest.test.mjs
//
// Env-read snippets are assembled from fragments (PE below) so that this file does not itself
// contain the read patterns the checker scans the real tree for.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { after, describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';

import { checkRepo, findEnvReads, parseManifestYaml, validateManifest } from './check-credential-manifest.mjs';

const SCRIPT = join(dirname(fileURLToPath(import.meta.url)), 'check-credential-manifest.mjs');
const PE = ['process', 'env'].join('.');
const ENV = 'env';
const DOLLAR = '$';
const MANIFEST = 'docs/build/security/credential-manifest.yaml';
const made = [];
after(() => made.forEach((d) => rmSync(d, { recursive: true, force: true })));

function entry(name, extra = {}) {
  const e = {
    kind: 'internal-bearer-token', secret: 'true', lane_owner: 'fnd', consumers: '[]', modes: '[sandbox]',
    secret_manager_id: 'none', github_location: '[]', validation: 'none', distinct_from: '[]',
    rotation_class: 'internal-bearer', cadence_days: '90', status: 'active', created_by_this_lane: 'false', ...extra,
  };
  const lines = [`  - name: ${name}`];
  for (const [k, v] of Object.entries(e)) {
    if (Array.isArray(v)) lines.push(`    ${k}:`, ...v.map((x) => `      - ${x}`));
    else lines.push(`    ${k}: ${v}`);
  }
  return lines.join('\n');
}
const manifest = (...entries) => `schema: brandme-credential-manifest/1\nentries:\n${entries.join('\n')}\n`;

function repo(files) {
  const dir = mkdtempSync(join(tmpdir(), 'cred-manifest-'));
  made.push(dir);
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(dirname(join(dir, path)), { recursive: true });
    writeFileSync(join(dir, path), text);
  }
  for (const argv of [['init', '-q'], ['add', '-A']]) {
    const r = spawnSync('git', argv, { cwd: dir, encoding: 'utf8' });
    assert.equal(r.status, 0, r.stderr);
  }
  return dir;
}
const cli = (dir, ...argv) => spawnSync(process.execPath, [SCRIPT, '--root', dir, ...argv], { encoding: 'utf8' });

describe('YAML subset parser', () => {
  test('parses the supported constructs exactly', () => {
    const doc = parseManifestYaml([
      '# header',
      'schema: brandme-credential-manifest/1',
      "quoted: 'it''s: fine # not a comment'",
      'double: "a \\"b\\" \\\\ c"',
      'count: 90',
      'nothing: null',
      'flag: false   # trailing comment',
      'entries:',
      '  - name: A_TOKEN',
      "    modes: [sandbox, 'production']",
      '    consumers:',
      '      - src/a.ts:12',
      '      - .mcp.json:9',
      '    empty: []',
      '  - plain item',
    ].join('\n'));
    assert.deepEqual(doc, {
      schema: 'brandme-credential-manifest/1',
      quoted: "it's: fine # not a comment",
      double: 'a "b" \\ c',
      count: 90,
      nothing: null,
      flag: false,
      entries: [
        { name: 'A_TOKEN', modes: ['sandbox', 'production'], consumers: ['src/a.ts:12', '.mcp.json:9'], empty: [] },
        'plain item',
      ],
    });
  });

  const rejects = {
    tab: 'a:\tb',
    anchor: 'a: &x b',
    alias: 'a: *x',
    tag: 'a: !!str b',
    'block scalar': 'a: |\n  text',
    'flow mapping': 'a: {b: c}',
    'duplicate key': 'a: b\na: c',
    'yes/no': 'a: yes',
    'number-like': 'a: 1.5',
    date: "a: 2026-10-23",
    'leading zero': 'a: 0755',
    'document marker': '---\na: b',
    'bad indentation': 'a:\n  - b\n   - c',
    'unterminated quote': "a: 'b",
    'colon in plain value': 'a: b: c',
    'unquoted colon in flow item': 'a: [x:1]',
    'empty value': 'a:',
  };
  for (const [what, text] of Object.entries(rejects)) {
    test(`rejects ${what}`, () => assert.throws(() => parseManifestYaml(text), /manifest line \d+/));
  }
});

describe('manifest validation', () => {
  const v = (text) => validateManifest(parseManifestYaml(text)).errors;
  test('accepts a complete entry', () => assert.deepEqual(v(manifest(entry('A_TOKEN'))), []));
  const cases = {
    'unknown lane': [entry('A_TOKEN', { lane_owner: 'xyz' }), /lane_owner/],
    'unknown status': [entry('A_TOKEN', { status: 'maybe' }), /status/],
    'unknown mode': [entry('A_TOKEN', { modes: '[staging]' }), /unknown mode 'staging'/],
    'missing field': [entry('A_TOKEN').replace(/\n {4}kind: [^\n]+/, ''), /missing field 'kind'/],
    'unknown field': [entry('A_TOKEN', { color: 'blue' }), /unknown field 'color'/],
    'Secret Manager lane mismatch': [entry('A_TOKEN', { secret_manager_id: 'brandme-<mode>-rts-a-token' }), /differs from lane_owner/],
    'Secret Manager id shape': [entry('A_TOKEN', { secret_manager_id: 'a-token' }), /secret_manager_id must be/],
    'non-secret with Secret Manager id': [entry('A_URL', { secret: 'false', secret_manager_id: 'brandme-<mode>-fnd-a-url' }), /non-secret/],
    'GitHub Environment secret renamed': [entry('A_TOKEN', { github_location: "['env:sandbox/OTHER_TOKEN']" }), /must equal the runtime name/],
    'secret stored as a GitHub variable': [entry('A_TOKEN', { github_location: "['repo-var:A_TOKEN']" }), /must not be stored as GitHub variables/],
    'new repo-level secret naming': [entry('NEW_TOKEN', { status: 'planned', github_location: "['repo-secret:NEW_TOKEN']" }), /BM_<MODE>_<LANE>_<PURPOSE>/],
    'NEXT_PUBLIC secret': [entry('NEXT_PUBLIC_API_KEY'), /NEXT_PUBLIC_/],
    'planned name without a type suffix': [entry('NEW_THING', { status: 'planned' }), /must end in _TOKEN/],
    'unanchored regex': [entry('A_TOKEN', { validation: "'[a-z]+'" }), /anchored/],
    'bad regex': [entry('A_TOKEN', { validation: "'^([a-z$'" }), /does not compile/],
    'bad cadence': [entry('A_TOKEN', { cadence_days: '0' }), /cadence_days/],
  };
  for (const [what, [text, re]] of Object.entries(cases)) {
    test(`rejects ${what}`, () => assert.match(v(manifest(text)).join('\n'), re));
  }
  test('distinct_from must be symmetric and known', () => {
    const errs = v(manifest(entry('A_TOKEN', { distinct_from: '[B_TOKEN, C_TOKEN]' }), entry('B_TOKEN'))).join('\n');
    assert.match(errs, /not symmetric: B_TOKEN does not list A_TOKEN/);
    assert.match(errs, /unknown entry 'C_TOKEN'/);
  });
  test('rejects duplicate entries', () => assert.match(v(manifest(entry('A_TOKEN'), entry('A_TOKEN'))).join('\n'), /duplicate entry/));
});

describe('env read detection', () => {
  test('finds reads in each language and skips comments', () => {
    const ts = [
      `const a = ${PE}.ALPHA_TOKEN;`,
      `const b = ${PE}['BRAVO_SECRET'];`,
      `const c = blank(${ENV}.CHARLIE_PASSWORD);`,
      `// ${PE}.COMMENTED_TOKEN`,
      `const d = ${PE}.PLAIN_URL;`,
    ].join('\n');
    assert.deepEqual(findEnvReads('src/a.ts', ts).map((r) => `${r.line}:${r.name}`), ['1:ALPHA_TOKEN', '2:BRAVO_SECRET', '3:CHARLIE_PASSWORD']);
    const py = ['import os', 'a = os.environ["DELTA_KEY"]', 'b = os.getenv("ECHO_DSN", "")', 'c = env.get("FOXTROT_SEEDS")', '# os.getenv("NOPE_TOKEN")'].join('\n');
    assert.deepEqual(findEnvReads('svc/a.py', py).map((r) => r.name), ['DELTA_KEY', 'ECHO_DSN', 'FOXTROT_SEEDS']);
    const sh = ['echo "' + DOLLAR + '{GOLF_PASSWORD:-x}"', 'curl -u "' + DOLLAR + 'HOTEL_TOKEN"', 'local_secret="' + DOLLAR + 'lowercase_secret"', '# ' + DOLLAR + 'COMMENT_TOKEN'].join('\n');
    assert.deepEqual(findEnvReads('scripts/a.sh', sh).map((r) => r.name), ['GOLF_PASSWORD', 'HOTEL_TOKEN']);
    const wf = 'jobs:\n  a:\n    steps:\n      - run: echo hi\n        env:\n          X: ' + DOLLAR + '{{ secrets.INDIA_KEY }}\n';
    assert.deepEqual(findEnvReads('.github/workflows/ci.yml', wf).map((r) => r.name), ['INDIA_KEY']);
    assert.deepEqual(findEnvReads('README.md', `${PE}.ALPHA_TOKEN`), []);
  });
});

describe('repository check', () => {
  const reads = {
    'src/config.ts': `export const t = ${PE}.ALPHA_TOKEN;\n`,
    'svc/config.py': 'import os\nKEY = os.environ.get("DELTA_KEY")\n',
    'scripts/run.sh': '#!/bin/sh\ncurl -H "Authorization: Bearer ' + DOLLAR + '{GOLF_TOKEN}" http://x\n',
    '.github/workflows/ci.yml': 'jobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ' + DOLLAR + '{{ secrets.INDIA_KEY }}\n',
    '.env.example': '# names only\nALPHA_TOKEN=\n# DELTA_KEY=<from secret manager>\nPORT=3001\n',
  };
  const fullManifest = manifest(
    entry('ALPHA_TOKEN', { consumers: ['src/config.ts:1'], templates: ['.env.example:2'] }),
    entry('DELTA_KEY', { consumers: ['svc/config.py:2'] }),
    entry('GOLF_TOKEN', { consumers: ['scripts/run.sh:2'] }),
    entry('INDIA_KEY', { consumers: ['.github/workflows/ci.yml:5'], modes: '[ci]' }),
  );

  test('passes when every secret-shaped read is manifested', () => {
    const dir = repo({ ...reads, [MANIFEST]: fullManifest });
    const r = checkRepo({ root: dir });
    assert.deepEqual(r.errors, []);
    assert.deepEqual(r.warnings, []);
    assert.equal(cli(dir).status, 0);
    assert.equal(cli(dir, '--strict').status, 0);
  });

  test('fails on unmanifested reads in every scanned language', () => {
    const dir = repo({ ...reads, [MANIFEST]: manifest(entry('ALPHA_TOKEN', { consumers: ['src/config.ts:1'] })) });
    const errs = checkRepo({ root: dir }).errors.join('\n');
    assert.match(errs, /DELTA_KEY has no row .*svc\/config\.py:2/);
    assert.match(errs, /GOLF_TOKEN has no row .*scripts\/run\.sh:2/);
    assert.match(errs, /INDIA_KEY has no row .*\.github\/workflows\/ci\.yml:5/);
    const out = cli(dir);
    assert.equal(out.status, 1);
    assert.match(out.stdout, /✖ credential manifest/);
  });

  test('fails on a NEXT_PUBLIC_ secret even when manifested', () => {
    const dir = repo({ 'app/page.tsx': `const k = ${PE}.NEXT_PUBLIC_MAPS_API_KEY;\n`, [MANIFEST]: manifest(entry('A_TOKEN')) });
    assert.match(checkRepo({ root: dir }).errors.join('\n'), /app\/page\.tsx:1: NEXT_PUBLIC_MAPS_API_KEY .*browsers/);
    const dir2 = repo({ 'app/.env.example': 'NEXT_PUBLIC_SESSION_SECRET=\n', [MANIFEST]: manifest(entry('A_TOKEN')) });
    assert.match(checkRepo({ root: dir2 }).errors.join('\n'), /NEXT_PUBLIC_SESSION_SECRET/);
  });

  test('fails on tracked env files that are not *.example', () => {
    const dir = repo({
      '.env.production': 'X=1\n', 'svc/app.env': 'X=1\n', '.envrc': 'export X=1\n', 'dist/.env': 'X=1\n',
      '.env.example': 'X=\n', 'svc/.env.example': 'X=\n', [MANIFEST]: manifest(entry('A_TOKEN')),
    });
    const errs = checkRepo({ root: dir }).errors.join('\n');
    for (const f of ['.env.production', 'svc/app.env', '.envrc', 'dist/.env']) assert.match(errs, new RegExp(`${f.replace('.', '\\.')}: tracked env file`));
    assert.doesNotMatch(errs, /\.env\.example: tracked/);
  });

  test('template declarations need manifest rows; values and URL credentials warn', () => {
    const dir = repo({
      '.env.example': 'ALPHA_TOKEN=change-me\n# ZULU_PASSWORD=\nDATABASE_URL=postgresql://app:placeholder@db:5432/x\n',
      [MANIFEST]: manifest(entry('ALPHA_TOKEN', { templates: ['.env.example:1'] })),
    });
    const r = checkRepo({ root: dir });
    assert.match(r.errors.join('\n'), /\.env\.example:2: template declares secret-shaped ZULU_PASSWORD/);
    assert.match(r.warnings.join('\n'), /\.env\.example:1: template assigns a value to secret ALPHA_TOKEN/);
    assert.match(r.warnings.join('\n'), /DATABASE_URL embeds credentials/);
  });

  test('stale consumers and line drift warn; --strict fails on them', () => {
    const dir = repo({
      'src/config.ts': `// moved\nexport const t = ${PE}.ALPHA_TOKEN;\n`,
      [MANIFEST]: manifest(
        entry('ALPHA_TOKEN', { consumers: ['src/config.ts:1'] }),
        entry('OLD_TOKEN', { consumers: ['src/config.ts:2', 'src/gone.ts:3'], status: 'legacy-unread', rotation_class: 'retire', cadence_days: 'null' }),
        entry('UNUSED_TOKEN', { consumers: ['src/gone.ts:1'] }),
      ),
    });
    const r = checkRepo({ root: dir });
    assert.deepEqual(r.errors, []);
    const w = r.warnings.join('\n');
    assert.match(w, /ALPHA_TOKEN: consumer src\/config\.ts:1 moved/);
    assert.match(w, /OLD_TOKEN: consumer src\/config\.ts:2 no longer references OLD_TOKEN/);
    assert.match(w, /OLD_TOKEN: consumer src\/gone\.ts:3 no longer exists/);
    assert.match(w, /UNUSED_TOKEN: status active but no consumer/);
    assert.equal(cli(dir).status, 0);
    assert.equal(cli(dir, '--strict').status, 1);
  });

  test('skips generated and vendored paths but not legacy code', () => {
    const read = `x = ${PE}.HIDDEN_TOKEN;\n`;
    const dir = repo({
      'dist/app.js': read, 'packages/x/generated/api.ts': read, 'vendor/lib.js': read, 'a/b.min.js': read,
      'legacy-service/main.js': read, [MANIFEST]: manifest(entry('A_TOKEN')),
    });
    const errs = checkRepo({ root: dir }).errors;
    assert.equal(errs.length, 1);
    assert.match(errs[0], /HIDDEN_TOKEN has no row .*legacy-service\/main\.js:1\)$/);
  });

  test('reports malformed manifests and untracked manifests', () => {
    const dir = repo({ [MANIFEST]: 'schema: brandme-credential-manifest/1\nentries:\n\t- name: X\n' });
    assert.match(checkRepo({ root: dir }).errors[0], /tabs are not allowed/);
    const json = JSON.parse(cli(dir, '--json').stdout);
    assert.equal(json.ok, false);
    const dir2 = repo({ 'x.txt': 'x' });
    writeFileSync(join(dir2, 'm.yaml'), manifest(entry('A_TOKEN')));
    assert.match(checkRepo({ root: dir2, manifestPath: 'm.yaml' }).warnings.join('\n'), /m\.yaml: manifest is not tracked/);
  });
});
