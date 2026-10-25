#!/usr/bin/env node
// Workspace + toolchain governance guard. Policy and error-code table:
// docs/build/workspace-governance.md. Node built-ins only; it never writes to the checkout.
//
//   node scripts/check-workspace.mjs               offline checks over git-tracked files
//   node scripts/check-workspace.mjs --with-pnpm   also run pnpm's own frozen --lockfile-only check
//                                                  (specifier/override staleness; writes nothing) and
//                                                  compare pnpm's project list with the guard's
//   node scripts/check-workspace.mjs --json        machine-readable result on stdout
//   node scripts/check-workspace.mjs --root <dir>  check another checkout (default: this repo)
//
// Exit 0: no errors (warnings allowed). Exit 1: governance errors. Exit 2: bad usage.
// Under GitHub Actions the findings are also printed as ::error / ::warning annotations.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { dirname, join, posix, relative, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// Directories whose package.json is intentionally NOT a pnpm workspace member: dir -> reason.
// The map lives here, not in a .json file, because .gitignore ignores *.json. An entry needs
// foundation approval and a row under "STANDALONE exceptions" in docs/build/workspace-governance.md.
// A STANDALONE directory may commit its own pnpm-lock.yaml (written by the root-pinned pnpm with
// --ignore-workspace); it may not set a packageManager that differs from the root.
export const STANDALONE = Object.freeze({});

export const LOCKFILE_VERSION = '9.0';
// pnpm's section precedence when a name is declared twice (verified with pnpm 10.34.6):
// dependencies beats devDependencies, optionalDependencies beats both. Later entries win here.
const DEP_SECTIONS = ['devDependencies', 'dependencies', 'optionalDependencies'];
const LOCK_NAMES = new Set(['pnpm-lock.yaml', 'package-lock.json', 'npm-shrinkwrap.json', 'yarn.lock', 'bun.lock', 'bun.lockb']);
const DOC = 'docs/build/workspace-governance.md';

// One fix hint per code; the per-finding message says what is wrong and where.
export const CODES = {
  E_GIT: 'Run the guard inside a git checkout (it checks git-tracked files), or pass --root <checkout>.',
  E_WS_CONFIG: 'pnpm-workspace.yaml must be tracked and have a block-list `packages:` of simple globs (* ** ? {a,b} [...] and !negations).',
  E_MANIFEST_JSON: 'Fix the package.json so it parses as a JSON object.',
  E_UNREGISTERED: 'Add the directory to pnpm-workspace.yaml `packages:` (shared code goes under packages/<name>), run `pnpm install --lockfile-only` from the repo root, and commit the manifest and pnpm-lock.yaml together. If it must stay outside the workspace, it needs a foundation-approved STANDALONE entry with a reason in scripts/check-workspace.mjs.',
  E_ALLOWLIST_CONFLICT: 'A directory is either a workspace member or STANDALONE, never both: drop the STANDALONE entry, or exclude the directory with a `!<dir>` glob.',
  E_ALLOWLIST_STALE: 'Fix or remove the STANDALONE entry: it must name a directory (no ./, no trailing /) that has a tracked package.json, with a non-empty reason.',
  E_LOCK_MISSING: 'Commit the root pnpm-lock.yaml: run `pnpm install --lockfile-only` from the repo root with the pinned pnpm.',
  E_LOCK_VERSION: `This repo's lockfile is v${LOCKFILE_VERSION} (pnpm 10). Do not commit a lockfile from another pnpm major: take the base branch's pnpm-lock.yaml, run \`corepack enable\`, then \`pnpm install --lockfile-only\`.`,
  E_LOCK_PARSE: 'pnpm-lock.yaml has no parseable `importers:` block; regenerate it with `pnpm install --lockfile-only` instead of editing it by hand.',
  E_IMPORTER_MISSING: 'Run `pnpm install --lockfile-only` from the repo root and commit pnpm-lock.yaml in the same commit as the manifest.',
  E_IMPORTER_ORPHAN: 'Run `pnpm install --lockfile-only` from the repo root (it drops the orphan importer) and commit pnpm-lock.yaml. `pnpm install --frozen-lockfile` does not detect this.',
  E_IMPORTER_STALE: 'Run `pnpm install --lockfile-only` from the repo root and commit pnpm-lock.yaml in the same commit as the manifest. Never hand-merge pnpm-lock.yaml.',
  E_PM_FORMAT: 'Set root package.json "packageManager" to an exact "pnpm@x.y.z" (optionally +sha); docs/build/compatibility-lock.md records the pin.',
  E_PM_ENGINES: 'Make root engines.pnpm equal the packageManager version exactly, or remove it.',
  E_PM_NESTED: 'Remove "packageManager" from nested manifests: the root packageManager is the only pnpm pin.',
  E_ACTION_PNPM_VERSION: 'Delete the `version:` input. pnpm/action-setup@v4 reads packageManager; with both set it refuses to start ("Multiple versions of pnpm specified", run 39961921035), and an equal copy drifts later.',
  E_PNPM_PIN: 'Use `corepack enable` (or `corepack install`), which reads packageManager, or pin exactly the packageManager version.',
  E_NODE_LITERAL: 'Give actions/setup-node `node-version-file: .nvmrc` and no `node-version:` input.',
  E_NODE_FILES: '.nvmrc (exact x.y.z), .node-version, .tool-versions, Dockerfile ARG NODE_VERSION defaults and node:<tag> images must all name the same Node version.',
  E_NESTED_LOCKFILE: 'Delete it. Only the root pnpm-lock.yaml (and a STANDALONE directory\'s own pnpm-lock.yaml) may be committed; install only from the repo root, never `pnpm --dir <pkg> install`.',
  E_PNPM_FIELD: 'Move pnpm settings (overrides, packageExtensions, onlyBuiltDependencies, ...) into pnpm-workspace.yaml; workspace membership is pnpm-workspace.yaml `packages:`.',
  E_PNPM_RUNTIME: 'Run `corepack enable` so `pnpm` resolves to the packageManager version; in CI use pnpm/action-setup@v4 with no `version:`.',
  E_PNPM_FROZEN: 'The lockfile is stale against the manifests or workspace settings (specifiers, overrides, packageExtensions). Run `pnpm install --lockfile-only` from the repo root and commit pnpm-lock.yaml with the manifest.',
  E_PNPM_PROJECTS: 'pnpm and the guard disagree about workspace membership. Commit or delete the listed package.json files, or simplify the glob; if the tree is clean this is a guard bug.',
  W_ENGINES_PNPM: 'Remove engines.pnpm from nested manifests; the root packageManager pins pnpm.',
  W_NOT_PRIVATE: 'Set "private": true; nothing in this repo is published to a registry.',
  W_UNTRACKED: 'git add the package.json (with pnpm-lock.yaml in the same commit) or delete it.',
  W_STANDALONE_NO_LOCK: 'Commit the STANDALONE directory\'s own pnpm-lock.yaml: `pnpm --dir <dir> install --lockfile-only --ignore-workspace`.',
};

// ---- small helpers ---------------------------------------------------------------

const indentOf = (line) => line.length - line.trimStart().length;
const skippable = (line) => !line.trim() || line.trimStart().startsWith('#');
const lineAt = (text, index) => text.slice(0, index).split('\n').length;
const lineOf = (text, re) => {
  const m = re.exec(text);
  return m ? lineAt(text, m.index) : undefined;
};
const dirOf = (file) => (posix.dirname(file) === '.' ? '.' : posix.dirname(file));
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const isDynamic = (v) => /[$%{}]/.test(v);
const stripComment = (v) => v.replace(/\s+#.*$/, '').trim();
function unquote(v) {
  const s = v.trim();
  if (s.length >= 2 && s[0] === "'" && s.endsWith("'")) return s.slice(1, -1).replace(/''/g, "'");
  if (s.length >= 2 && s[0] === '"' && s.endsWith('"')) {
    try { return JSON.parse(s); } catch { return s.slice(1, -1); }
  }
  return s;
}

// ---- pnpm-workspace.yaml `packages:` --------------------------------------------------

// Returns the raw glob list; throws Error(message) when the block cannot be read safely.
export function parseWorkspacePackages(text) {
  const lines = text.replace(/\r/g, '').split('\n');
  const at = lines.findIndex((l) => /^packages\s*:/.test(l));
  if (at < 0) throw new Error('pnpm-workspace.yaml has no top-level `packages:` key');
  const inline = stripComment(lines[at].replace(/^packages\s*:/, ''));
  if (inline) throw new Error(`\`packages:\` must be a block list (found inline value ${inline})`);
  const globs = [];
  for (let i = at + 1; i < lines.length; i++) {
    const line = lines[i];
    if (skippable(line)) continue;
    const item = /^\s*-\s+(.*)$/.exec(line) ?? /^\s*-$/.exec(line);
    if (!item) {
      if (indentOf(line) === 0) break;
      throw new Error(`unexpected line ${i + 1} inside \`packages:\`: ${line.trim()}`);
    }
    const raw = (item[1] ?? '').trim();
    let value;
    if (raw.startsWith("'") || raw.startsWith('"')) {
      const q = raw[0];
      const m = q === "'" ? /^'((?:[^']|'')*)'\s*(#.*)?$/.exec(raw) : /^"((?:[^"\\]|\\.)*)"\s*(#.*)?$/.exec(raw);
      if (!m) throw new Error(`unparseable quoted glob on line ${i + 1}: ${raw}`);
      value = unquote(`${q}${m[1]}${q}`);
    } else {
      value = stripComment(raw);
    }
    if (!value) throw new Error(`empty glob on line ${i + 1}`);
    globs.push(value);
  }
  if (!globs.length) throw new Error('`packages:` is empty');
  return globs;
}

function expandBraces(pattern) {
  const open = pattern.indexOf('{');
  if (open < 0) {
    if (pattern.includes('}')) throw new Error(`unbalanced } in glob ${pattern}`);
    return [pattern];
  }
  let depth = 0;
  let start = open + 1;
  const parts = [];
  for (let i = open; i < pattern.length; i++) {
    const ch = pattern[i];
    if (ch === '{') depth++;
    else if (ch === ',' && depth === 1) { parts.push(pattern.slice(start, i)); start = i + 1; }
    else if (ch === '}' && --depth === 0) {
      parts.push(pattern.slice(start, i));
      if (parts.length < 2) throw new Error(`unsupported brace form in glob ${pattern} (use {a,b})`);
      const head = pattern.slice(0, open);
      const tail = pattern.slice(i + 1);
      return parts.flatMap((p) => expandBraces(head + p + tail));
    }
  }
  throw new Error(`unbalanced { in glob ${pattern}`);
}

function segmentRe(seg) {
  // Wildcards never match a leading dot (pnpm's glob default, verified with pnpm 10.34.6).
  let out = seg.startsWith('.') ? '' : '(?!\\.)';
  for (let i = 0; i < seg.length; i++) {
    const ch = seg[i];
    if (ch === '*') out += '[^/]*';
    else if (ch === '?') out += '[^/]';
    else if (ch === '[') {
      const close = seg.indexOf(']', i + 2);
      if (close < 0) throw new Error(`unterminated [ in glob segment ${seg}`);
      let cls = seg.slice(i + 1, close);
      if (cls.startsWith('!')) cls = '^' + cls.slice(1);
      out += `[${cls.replace(/\\/g, '\\\\')}]`;
      i = close;
    } else out += escapeRe(ch);
  }
  return out;
}

// pnpm appends /package.json to every glob and hands the list to its glob library, so a
// directory is a member when <dir>/package.json matches some positive glob and no !glob.
// node_modules and bower_components are never projects.
function globToRe(glob) {
  if (/[()|\\]|[+@!]\(/.test(glob)) throw new Error(`unsupported glob syntax in ${glob} (extglobs, groups and escapes are not allowed)`);
  const body = glob.replace(/^\.\//, '').replace(/\/+$/, '');
  return expandBraces(body === '.' || body === '' ? 'package.json' : `${body}/package.json`).map((p) => {
    const segs = p.split('/').filter(Boolean);
    let re = '^';
    segs.forEach((seg, i) => {
      if (seg === '**') re += '(?:(?!\\.)[^/]+/)*';
      else re += segmentRe(seg) + (i < segs.length - 1 ? '/' : '');
    });
    return new RegExp(re + '$');
  });
}

export function workspaceMatcher(globs) {
  const pos = [];
  const neg = [];
  for (const g of globs) (g.startsWith('!') ? neg : pos).push(...globToRe(g.startsWith('!') ? g.slice(1) : g));
  return (dir) => {
    if (dir === '.') return true;
    if (dir.split('/').some((s) => s === 'node_modules' || s === 'bower_components')) return false;
    const file = `${dir}/package.json`;
    return pos.some((r) => r.test(file)) && !neg.some((r) => r.test(file));
  };
}

// ---- pnpm-lock.yaml ---------------------------------------------------------------

// Reads lockfileVersion and, for a v9 lockfile only, importer -> { dependency name -> section }.
// Relies on pnpm's fixed two-space layout; anything unexpected throws (fail closed).
export function parseLockfile(text) {
  const t = text.replace(/\r/g, '');
  const raw = (/^lockfileVersion:\s*(.*?)\s*$/m.exec(t) ?? [])[1];
  const version = raw === undefined ? undefined : unquote(raw);
  if (version !== LOCKFILE_VERSION) return { version, importers: null };
  const lines = t.split('\n');
  const at = lines.findIndex((l) => /^importers:\s*$/.test(l));
  if (at < 0) return { version, importers: null };
  const importers = new Map();
  let cur = null;
  let section = null;
  for (let i = at + 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    if (/^\S/.test(line)) break;
    let m;
    if ((m = /^ {2}(\S.*?):(\s*\{\})?\s*$/.exec(line))) {
      cur = { deps: new Map(), line: i + 1 };
      importers.set(unquote(m[1]), cur);
      section = null;
    } else if (!cur) {
      throw new Error(`unexpected line before the first importer on pnpm-lock.yaml:${i + 1}: ${line.trim()}`);
    } else if ((m = /^ {4}(\S.*?):(\s*\{\})?\s*$/.exec(line))) {
      section = DEP_SECTIONS.includes(m[1]) ? m[1] : null;
    } else if (/^ {4}\S/.test(line)) {
      section = null;
    } else if (section && (m = /^ {6}(\S.*?):\s*$/.exec(line))) {
      cur.deps.set(unquote(m[1]), section);
    } else if (section && /^ {6}\S/.test(line)) {
      throw new Error(`unexpected importer entry on pnpm-lock.yaml:${i + 1}: ${line.trim()}`);
    }
  }
  return { version, importers };
}

// ---- workflow steps -----------------------------------------------------------------

// Line-based reader for GitHub Actions steps: finds `uses: <action>` steps and their `with:` inputs.
export function actionSteps(text, actionRe) {
  const lines = text.replace(/\r/g, '').split('\n');
  const steps = [];
  for (let i = 0; i < lines.length; i++) {
    const m = /^(\s*)(-\s+)?uses:\s*['"]?([^'"\s#]+)/.exec(lines[i]);
    if (!m || !actionRe.test(m[3])) continue;
    const keyIndent = m[1].length + (m[2]?.length ?? 0);
    let start = i;
    let dashIndent = m[1].length;
    if (!m[2]) {
      for (start = i - 1; start >= 0; start--) if (!skippable(lines[start]) && indentOf(lines[start]) < keyIndent) break;
      const dm = start >= 0 ? /^(\s*)-\s+/.exec(lines[start]) : null;
      if (!dm || dm[0].length !== keyIndent) { start = i; dashIndent = keyIndent - 2; } else dashIndent = dm[1].length;
    }
    let end = i + 1;
    while (end < lines.length && (skippable(lines[end]) || indentOf(lines[end]) > dashIndent)) end++;
    const inputs = [];
    for (let j = start; j < end; j++) {
      const w = /^(\s*)(-\s+)?with:\s*(.*)$/.exec(lines[j]);
      if (!w || w[1].length + (w[2]?.length ?? 0) !== keyIndent) continue;
      const inline = stripComment(w[3]);
      if (inline.startsWith('{')) {
        for (const part of inline.slice(1, inline.lastIndexOf('}')).split(',')) {
          const kv = /^\s*['"]?([\w-]+)['"]?\s*:\s*(.*?)\s*$/.exec(part);
          if (kv) inputs.push({ key: kv[1], value: unquote(kv[2]), line: j + 1 });
        }
        continue;
      }
      let child = null;
      for (let k = j + 1; k < end; k++) {
        if (skippable(lines[k])) continue;
        const ind = indentOf(lines[k]);
        if (ind <= keyIndent) break;
        child ??= ind;
        if (ind !== child) continue;
        const kv = /^\s*['"]?([\w-]+)['"]?\s*:\s*(.*?)\s*$/.exec(lines[k]);
        if (kv) inputs.push({ key: kv[1], value: unquote(stripComment(kv[2])), line: k + 1 });
      }
    }
    steps.push({ uses: m[3], line: i + 1, inputs });
  }
  return steps;
}

// ---- pin scanners ---------------------------------------------------------------------

// Yields { version|null, index } for every pnpm install/activation command in a shell-ish text.
// Commented-out lines and echo/printf messages do not execute, so they are not pins.
function* pnpmPins(text) {
  const executes = (index) => {
    const line = text.slice(text.lastIndexOf('\n', index - 1) + 1, index);
    return !/^\s*(#|echo\b|printf\b)/.test(line);
  };
  const found = [];
  for (const m of text.matchAll(/\bcorepack[ \t]+(?:prepare|use|install)[ \t]+(?:(?:-g|--global|--activate)[ \t]+)*pnpm(?:@([^\s'"`;&|)\\,\]]+))?/g)) found.push({ version: m[1] ?? null, index: m.index });
  for (const m of text.matchAll(/\b(?:npx|pnpm[ \t]+dlx)[ \t]+(?:(?:--yes|-y)[ \t]+)*pnpm@([^\s'"`;&|)\\,\]]+)/g)) found.push({ version: m[1], index: m.index });
  for (const m of text.matchAll(/\bnpm[ \t]+(?:i|install|add)[ \t]+([^\n;&|]*)/g)) {
    const args = m[1].replace(/['"`,\]]/g, ' ');
    if (!/(^|\s)(-g|--global)(\s|$)/.test(args)) continue;
    const p = /(?:^|\s)pnpm(?:@(\S+))?(?=\s|$)/.exec(args);
    if (p) found.push({ version: p[1] ?? null, index: m.index });
  }
  yield* found.filter((p) => executes(p.index));
}

const isDockerfile = (f) => /(^|\/)(Dockerfile|Containerfile)[^/]*$|\.Dockerfile$/i.test(f);
const isScanned = (f) =>
  !f.startsWith('docs/') && !f.split('/').includes('node_modules') && !f.endsWith('pnpm-lock.yaml') &&
  (isDockerfile(f) || /\.(sh|bash|ya?ml|mk)$/.test(f) || /(^|\/)(Makefile|makefile|GNUmakefile|\.tool-versions)$/.test(f));

// ---- the guard ------------------------------------------------------------------------

export async function checkWorkspace({ root, standalone = STANDALONE, withPnpm = false } = {}) {
  const t0 = performance.now();
  const errors = [];
  const warnings = [];
  const find = (list) => (code, file, line, message) => list.push({ code, file: file ?? null, line: line ?? null, message });
  const err = find(errors);
  const warn = find(warnings);
  const result = (extra = {}) => ({ ok: errors.length === 0, root, errors, warnings, ...extra, ms: Math.round(performance.now() - t0) });

  const git = (args) => spawnSync('git', args, { cwd: root, encoding: 'utf8', maxBuffer: 1 << 28 });
  const ls = git(['ls-files', '-z', '--cached']);
  if (ls.status !== 0) {
    err('E_GIT', null, null, `git ls-files failed in ${root}: ${(ls.stderr || ls.error?.message || '').trim()}`);
    return result();
  }
  const tracked = ls.stdout.split('\0').filter((f) => f && existsSync(join(root, f)));
  const trackedSet = new Set(tracked);
  const untracked = git(['ls-files', '-z', '--others', '--exclude-standard', '--', ':(glob)**/package.json']).stdout.split('\0').filter(Boolean);
  const cache = new Map();
  const read = (f) => {
    if (!cache.has(f)) cache.set(f, existsSync(join(root, f)) ? readFileSync(join(root, f), 'utf8') : null);
    return cache.get(f);
  };
  const manifestText = new Map();
  const manifest = (f) => {
    if (!manifestText.has(f)) {
      let parsed = null;
      try {
        parsed = JSON.parse(read(f));
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('not a JSON object');
      } catch (e) {
        err('E_MANIFEST_JSON', f, 1, `${f} does not parse: ${e.message}`);
        parsed = null;
      }
      manifestText.set(f, parsed);
    }
    return manifestText.get(f);
  };
  const isManifest = (f) => posix.basename(f) === 'package.json' && !f.split('/').some((s) => s === 'node_modules' || s === 'bower_components');

  // -- STANDALONE map hygiene
  const standaloneDirs = [];
  for (const [dir, reason] of Object.entries(standalone)) {
    if (!dir || dir === '.' || dir.startsWith('./') || dir.endsWith('/') || dir.startsWith('/') || dir.split('/').includes('..')) err('E_ALLOWLIST_STALE', 'scripts/check-workspace.mjs', null, `STANDALONE entry "${dir}" is not a normalized repo-relative directory`);
    else if (typeof reason !== 'string' || !reason.trim()) err('E_ALLOWLIST_STALE', 'scripts/check-workspace.mjs', null, `STANDALONE entry ${dir} has no reason`);
    else if (!trackedSet.has(`${dir}/package.json`)) err('E_ALLOWLIST_STALE', 'scripts/check-workspace.mjs', null, `STANDALONE entry ${dir} has no tracked ${dir}/package.json`);
    else standaloneDirs.push(dir);
  }

  // -- workspace membership
  let member = null;
  const wsText = trackedSet.has('pnpm-workspace.yaml') ? read('pnpm-workspace.yaml') : null;
  if (wsText === null) err('E_WS_CONFIG', 'pnpm-workspace.yaml', null, 'pnpm-workspace.yaml is not tracked; without it pnpm installs only the root package');
  else {
    try {
      member = workspaceMatcher(parseWorkspacePackages(wsText));
    } catch (e) {
      err('E_WS_CONFIG', 'pnpm-workspace.yaml', lineOf(wsText, /^packages\s*:/m), e.message);
    }
  }
  const manifests = tracked.filter(isManifest);
  if (!trackedSet.has('package.json')) err('E_MANIFEST_JSON', 'package.json', null, 'root package.json is not tracked');
  const registered = [];
  if (member) {
    for (const f of manifests) {
      const dir = dirOf(f);
      const isMember = member(dir);
      if (isMember && standalone[dir] !== undefined) err('E_ALLOWLIST_CONFLICT', f, null, `${dir} is listed as STANDALONE but pnpm-workspace.yaml also matches it`);
      if (isMember) registered.push(dir);
      else if (standalone[dir] === undefined) err('E_UNREGISTERED', f, null, `${f} is tracked but no pnpm-workspace.yaml \`packages:\` glob matches ${dir}, so \`pnpm install\` never installs its dependencies (CI then fails later, e.g. "tsc: not found")`);
    }
    for (const f of untracked.filter(isManifest)) {
      const dir = dirOf(f);
      if (member(dir)) registered.push(dir);
      warn('W_UNTRACKED', f, null, `${f} is not tracked by git${member(dir) ? '' : ' and no workspace glob matches it'}`);
    }
  }
  const registeredSet = new Set(registered);

  // -- lockfiles
  const lockText = trackedSet.has('pnpm-lock.yaml') ? read('pnpm-lock.yaml') : null;
  let lock = null;
  if (lockText === null) err('E_LOCK_MISSING', 'pnpm-lock.yaml', null, 'the root pnpm-lock.yaml is not tracked');
  else {
    try {
      lock = parseLockfile(lockText);
    } catch (e) {
      err('E_LOCK_PARSE', 'pnpm-lock.yaml', null, e.message);
    }
    if (lock && lock.version !== LOCKFILE_VERSION) {
      err('E_LOCK_VERSION', 'pnpm-lock.yaml', 1, `pnpm-lock.yaml lockfileVersion is ${lock.version === undefined ? 'missing' : `'${lock.version}'`}, expected '${LOCKFILE_VERSION}'; importer checks were not run`);
      lock = null;
    } else if (lock && !lock.importers) {
      err('E_LOCK_PARSE', 'pnpm-lock.yaml', null, 'pnpm-lock.yaml has no `importers:` block');
      lock = null;
    }
  }
  for (const f of tracked) {
    if (!LOCK_NAMES.has(posix.basename(f)) || f === 'pnpm-lock.yaml') continue;
    const dir = dirOf(f);
    if (standaloneDirs.includes(dir) && posix.basename(f) === 'pnpm-lock.yaml') {
      const raw = (/^lockfileVersion:\s*(.*?)\s*$/m.exec(read(f) ?? '') ?? [])[1];
      const v = raw === undefined ? undefined : unquote(raw);
      if (v !== LOCKFILE_VERSION) err('E_LOCK_VERSION', f, 1, `${f} lockfileVersion is ${v === undefined ? 'missing' : `'${v}'`}, expected '${LOCKFILE_VERSION}'`);
      continue;
    }
    err('E_NESTED_LOCKFILE', f, null, `${f} is committed; only the root pnpm-lock.yaml${standaloneDirs.length ? ' and STANDALONE pnpm-lock.yaml files are' : ' is'} allowed`);
  }
  for (const dir of standaloneDirs) {
    const pkg = manifest(`${dir}/package.json`);
    const hasDeps = pkg && DEP_SECTIONS.some((s) => Object.keys(pkg[s] ?? {}).length);
    if (hasDeps && !trackedSet.has(`${dir}/pnpm-lock.yaml`)) warn('W_STANDALONE_NO_LOCK', `${dir}/package.json`, null, `STANDALONE ${dir} declares dependencies but commits no ${dir}/pnpm-lock.yaml`);
  }

  // -- importers vs registered packages (names + sections only; specifiers are pnpm's job)
  if (lock && member) {
    for (const dir of registered) {
      const imp = lock.importers.get(dir);
      if (!imp) {
        err('E_IMPORTER_MISSING', 'pnpm-lock.yaml', null, `registered package ${dir} has no importer in pnpm-lock.yaml`);
        continue;
      }
      const pkg = manifest(dir === '.' ? 'package.json' : `${dir}/package.json`);
      if (!pkg) continue;
      const want = new Map();
      for (const s of DEP_SECTIONS) for (const n of Object.keys(pkg[s] ?? {})) want.set(n, s);
      const peers = new Set(Object.keys(pkg.peerDependencies ?? {})); // autoInstallPeers records these in any section
      const missing = [...want.keys()].filter((n) => !imp.deps.has(n));
      const extra = [...imp.deps.keys()].filter((n) => !want.has(n) && !peers.has(n));
      const moved = [...want.keys()].filter((n) => imp.deps.has(n) && imp.deps.get(n) !== want.get(n)).map((n) => `${n} (${imp.deps.get(n)} -> ${want.get(n)})`);
      if (missing.length || extra.length || moved.length) {
        const parts = [missing.length && `missing [${missing.join(', ')}]`, extra.length && `not in manifest [${extra.join(', ')}]`, moved.length && `section changed [${moved.join(', ')}]`].filter(Boolean);
        err('E_IMPORTER_STALE', 'pnpm-lock.yaml', imp.line, `importer ${dir} does not match ${dir === '.' ? '' : `${dir}/`}package.json: ${parts.join('; ')}`);
      }
    }
    for (const [key, imp] of lock.importers) if (!registeredSet.has(key)) err('E_IMPORTER_ORPHAN', 'pnpm-lock.yaml', imp.line, `importer ${key} has no registered package${trackedSet.has(`${key}/package.json`) ? ` (${key}/package.json exists but is not a workspace member)` : ''}`);
  }

  // -- pnpm pin: root packageManager is the only source
  const rootPkg = trackedSet.has('package.json') ? manifest('package.json') : null;
  const rootText = read('package.json') ?? '';
  let want = null;
  if (rootPkg) {
    const pm = /^pnpm@(\d+\.\d+\.\d+)(\+sha\d+\.[0-9a-f]+)?$/.exec(rootPkg.packageManager ?? '');
    if (!pm) err('E_PM_FORMAT', 'package.json', lineOf(rootText, /"packageManager"/), `root packageManager is ${rootPkg.packageManager === undefined ? 'missing' : JSON.stringify(rootPkg.packageManager)}; it must be an exact pnpm@x.y.z`);
    else want = pm[1];
    if (want && rootPkg.engines?.pnpm !== undefined && rootPkg.engines.pnpm !== want) err('E_PM_ENGINES', 'package.json', lineOf(rootText, /"pnpm"\s*:/), `root engines.pnpm is ${JSON.stringify(rootPkg.engines.pnpm)}, packageManager pins ${want}`);
    for (const key of ['pnpm', 'resolutions', 'workspaces']) {
      if (rootPkg[key] === undefined) continue;
      const why = { pnpm: 'pnpm settings belong in pnpm-workspace.yaml', resolutions: 'pnpm applies root resolutions as overrides, splitting overrides across two files', workspaces: 'pnpm ignores it; membership is pnpm-workspace.yaml `packages:`' }[key];
      err('E_PNPM_FIELD', 'package.json', lineOf(rootText, new RegExp(`^\\s*"${key}"\\s*:`, 'm')), `root package.json has a "${key}" field: ${why}`);
    }
    if (rootPkg.private !== true) warn('W_NOT_PRIVATE', 'package.json', null, 'root package.json is not "private": true');
  }
  for (const f of manifests.filter((m) => m !== 'package.json')) {
    const pkg = manifest(f);
    if (!pkg) continue;
    const text = read(f);
    if (pkg.packageManager !== undefined && (!want || String(pkg.packageManager).split('+')[0] !== `pnpm@${want}`)) err('E_PM_NESTED', f, lineOf(text, /"packageManager"/), `${f} declares packageManager ${JSON.stringify(pkg.packageManager)}; the root pins pnpm@${want ?? '?'}`);
    if (pkg.engines?.pnpm !== undefined) warn('W_ENGINES_PNPM', f, lineOf(text, /"pnpm"\s*:/), `${f} declares engines.pnpm ${JSON.stringify(pkg.engines.pnpm)}`);
    if (pkg.private !== true && registeredSet.has(dirOf(f))) warn('W_NOT_PRIVATE', f, null, `${f} (${pkg.name ?? 'unnamed'}) is not "private": true`);
  }

  // -- workflows: pnpm/action-setup must not set `version:`; setup-node must read .nvmrc
  for (const f of tracked.filter((x) => /^\.github\/.+\.ya?ml$/.test(x))) {
    const text = read(f);
    for (const step of actionSteps(text, /^pnpm\/action-setup@/)) {
      for (const input of step.inputs.filter((x) => x.key === 'version')) err('E_ACTION_PNPM_VERSION', f, input.line, `pnpm/action-setup step (line ${step.line}) sets version: ${input.value}; packageManager pnpm@${want ?? '?'} must be the only pin`);
    }
    for (const step of actionSteps(text, /^actions\/setup-node@/)) {
      const literal = step.inputs.find((x) => x.key === 'node-version');
      const file = step.inputs.find((x) => x.key === 'node-version-file');
      if (literal) err('E_NODE_LITERAL', f, literal.line, `actions/setup-node sets node-version: ${literal.value}`);
      else if (!file) err('E_NODE_LITERAL', f, step.line, 'actions/setup-node has no node-version-file, so the runner\'s default Node is used');
      else if (!['.nvmrc', '.node-version'].includes(file.value)) err('E_NODE_LITERAL', f, file.line, `actions/setup-node reads node-version-file: ${file.value}`);
    }
  }

  // -- Node version files
  const nvmText = trackedSet.has('.nvmrc') ? read('.nvmrc') : null;
  const node = nvmText === null ? null : nvmText.trim().replace(/^v/, '');
  if (node === null) err('E_NODE_FILES', '.nvmrc', null, '.nvmrc is not tracked (CI and scripts/brandme.mjs read the Node pin from it)');
  else if (!/^\d+\.\d+\.\d+$/.test(node)) err('E_NODE_FILES', '.nvmrc', 1, `.nvmrc is ${JSON.stringify(nvmText.trim())}; it must be an exact x.y.z`);
  const nodeOk = node !== null && /^\d+\.\d+\.\d+$/.test(node);
  if (nodeOk && trackedSet.has('.node-version')) {
    const nv = read('.node-version').trim().replace(/^v/, '');
    if (nv !== node) err('E_NODE_FILES', '.node-version', 1, `.node-version is ${nv}, .nvmrc is ${node}`);
  }

  // -- pnpm/Node pins in Dockerfiles, compose/k8s YAML, shell, Makefiles, .tool-versions, package.json scripts
  const checkPin = (f, text, index, version) => {
    if (!want || (version !== null && isDynamic(version))) return;
    if (version === null) err('E_PNPM_PIN', f, lineAt(text, index), 'installs or activates pnpm without a version (resolves to whatever is latest)');
    else if (version.split('+')[0] !== want) err('E_PNPM_PIN', f, lineAt(text, index), `pins pnpm@${version}; packageManager is pnpm@${want}`);
  };
  const checkNode = (f, text, index, version, what) => {
    if (!nodeOk || (version !== undefined && isDynamic(version))) return;
    const lead = (/^v?(\d+(?:\.\d+){0,2})/.exec(version ?? '') ?? [])[1];
    if (lead !== node) err('E_NODE_FILES', f, lineAt(text, index), `${what}${version ?? ' (untagged, i.e. latest)'} does not match .nvmrc ${node}`);
  };
  for (const f of tracked.filter(isScanned)) {
    const text = read(f);
    if (text === null) continue;
    if (posix.basename(f) === '.tool-versions') {
      for (const m of text.matchAll(/^\s*(nodejs|node|pnpm)\s+(\S+)/gm)) {
        if (m[1] === 'pnpm') checkPin(f, text, m.index, m[2]);
        else checkNode(f, text, m.index, m[2], `.tool-versions ${m[1]}`);
      }
      continue;
    }
    for (const p of pnpmPins(text)) checkPin(f, text, p.index, p.version);
    if (isDockerfile(f)) {
      for (const m of text.matchAll(/^[ \t]*ARG[ \t]+NODE_VERSION[ \t]*=[ \t]*['"]?([^\s'"]+)/gim)) checkNode(f, text, m.index, m[1], 'ARG NODE_VERSION default ');
      // An untagged `FROM node` is latest; a digest-only reference cannot be compared, so it is skipped.
      for (const m of text.matchAll(/^[ \t]*FROM[ \t]+(?:--\S+[ \t]+)*(?:docker\.io\/)?(?:library\/)?node(?::([^\s@]+))?(@\S+)?(?=\s|$)/gim)) if (m[1] !== undefined || !m[2]) checkNode(f, text, m.index, m[1], 'base image node:');
    } else if (/\.ya?ml$/.test(f)) {
      for (const m of text.matchAll(/\bimage:[ \t]*['"]?(?:docker\.io\/)?(?:library\/)?node(?::([^\s'"@]+))?(@[^\s'"]+)?(?=['"\s]|$)/g)) if (m[1] !== undefined || !m[2]) checkNode(f, text, m.index, m[1], 'image node:');
    }
  }
  for (const f of manifests) {
    const pkg = manifest(f);
    if (!pkg || typeof pkg.scripts !== 'object' || !pkg.scripts) continue;
    const text = read(f);
    for (const [name, cmd] of Object.entries(pkg.scripts)) {
      if (typeof cmd !== 'string') continue;
      const at = text.indexOf(JSON.stringify(name));
      for (const p of pnpmPins(cmd)) checkPin(f, text, at < 0 ? 0 : at, p.version);
    }
  }

  // -- pnpm's own view (opt-in: spawns pnpm, ~0.6 s, writes nothing)
  const pnpmReport = [];
  if (withPnpm && want && member && lock) await pnpmChecks({ root, want, registered: registeredSet, standaloneDirs, trackedSet, err, report: pnpmReport });
  else if (withPnpm) pnpmReport.push('pnpm checks not run: they need readable workspace globs, a v9 lockfile and an exact packageManager (see the errors below)');

  return result({ registered: [...registeredSet].sort(), importers: lock ? [...lock.importers.keys()] : [], manifests: manifests.length, pnpm: want, node, pnpmReport });
}

function run(cmd, args, opts) {
  return new Promise((resolveRun) => {
    const t0 = performance.now();
    let out = '';
    let settled = false;
    let timer = null;
    const done = (code, extra = '') => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolveRun({ code, out: out + extra, ms: Math.round(performance.now() - t0) });
    };
    let child;
    try {
      child = spawn(cmd, args, { ...opts, stdio: ['ignore', 'pipe', 'pipe'] });
    } catch (e) {
      done(null, e.message);
      return;
    }
    timer = setTimeout(() => { child.kill('SIGKILL'); done(null, `\n${cmd} timed out`); }, opts.timeoutMs ?? 180_000);
    child.stdout.on('data', (d) => (out += d));
    child.stderr.on('data', (d) => (out += d));
    child.on('error', (e) => done(null, e.message));
    child.on('close', (code) => done(code));
  });
}

async function pnpmChecks({ root, want, registered, standaloneDirs, trackedSet, err, report }) {
  const env = { ...process.env, COREPACK_ENABLE_DOWNLOAD_PROMPT: '0' };
  const tail = (s) => s.trim().split('\n').slice(-12).join('\n');
  const v = await run('pnpm', ['--version'], { cwd: root, env });
  const got = v.code === 0 ? v.out.trim().split('\n').pop().trim() : null;
  if (got !== want) {
    err('E_PNPM_RUNTIME', 'package.json', null, got ? `active pnpm is ${got}, packageManager pins ${want}; the pnpm checks were not run` : `pnpm is not runnable here (${tail(v.out) || `exit ${v.code}`}); the pnpm checks were not run`);
    return;
  }
  const [frozen, list] = await Promise.all([
    run('pnpm', ['install', '--frozen-lockfile', '--lockfile-only', '--ignore-scripts'], { cwd: root, env }),
    run('pnpm', ['ls', '-r', '--depth', '-1', '--json'], { cwd: root, env }),
  ]);
  if (frozen.code === 0) report.push(`pnpm ${want} install --frozen-lockfile --lockfile-only: ok (${frozen.ms} ms)`);
  else err('E_PNPM_FROZEN', 'pnpm-lock.yaml', null, `pnpm install --frozen-lockfile --lockfile-only failed:\n${tail(frozen.out)}`);
  let projects = null;
  try {
    const real = realpathSync(root);
    projects = JSON.parse(list.out.slice(list.out.indexOf('['))).map((p) => relative(real, realpathSync(p.path)).split(sep).join('/') || '.');
  } catch (e) {
    err('E_PNPM_PROJECTS', 'pnpm-workspace.yaml', null, `could not read pnpm's project list (exit ${list.code}): ${e.message}`);
  }
  if (projects) {
    const pnpmSet = new Set(projects);
    const onlyPnpm = projects.filter((d) => !registered.has(d));
    const onlyGuard = [...registered].filter((d) => !pnpmSet.has(d));
    if (onlyPnpm.length || onlyGuard.length) err('E_PNPM_PROJECTS', 'pnpm-workspace.yaml', null, `pnpm sees [${onlyPnpm.join(', ')}] that the guard does not, and the guard sees [${onlyGuard.join(', ')}] that pnpm does not`);
    else report.push(`pnpm project list matches the guard (${projects.length} projects, ${list.ms} ms)`);
  }
  for (const dir of standaloneDirs.filter((d) => trackedSet.has(`${d}/pnpm-lock.yaml`))) {
    const r = await run('pnpm', ['--dir', dir, 'install', '--frozen-lockfile', '--lockfile-only', '--ignore-scripts', '--ignore-workspace'], { cwd: root, env });
    if (r.code === 0) report.push(`STANDALONE ${dir}: frozen --lockfile-only ok (${r.ms} ms)`);
    else err('E_PNPM_FROZEN', `${dir}/pnpm-lock.yaml`, null, `pnpm --dir ${dir} install --frozen-lockfile --lockfile-only --ignore-workspace failed:\n${tail(r.out)}`);
  }
}

// ---- CLI ------------------------------------------------------------------------------

const annotationEscape = (s, prop = false) => {
  let out = String(s).replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A');
  if (prop) out = out.replace(/:/g, '%3A').replace(/,/g, '%2C');
  return out;
};

function printText(r) {
  const where = (f) => (f.file ? `${f.file}${f.line ? `:${f.line}` : ''}` : '');
  console.log(`workspace guard: ${r.manifests ?? 0} manifests, ${r.registered?.length ?? 0} registered, ${r.importers?.length ?? 0} importers, pnpm ${r.pnpm ?? '?'}, node ${r.node ?? '?'} (${r.ms} ms)`);
  for (const line of r.pnpmReport ?? []) console.log(`  ${line}`);
  const groups = (list) => [...new Set(list.map((f) => f.code))].map((code) => [code, list.filter((f) => f.code === code)]);
  for (const [code, list] of groups(r.errors)) {
    for (const f of list) console.log(`✖ ${code} ${where(f)}\n    ${f.message.replace(/\n/g, '\n    ')}`);
    console.log(`    fix: ${CODES[code]}`);
  }
  for (const [code, list] of groups(r.warnings)) {
    for (const f of list) console.log(`! ${code} ${where(f)}: ${f.message}`);
    console.log(`    fix: ${CODES[code]}`);
  }
  if (process.env.GITHUB_ACTIONS === 'true') {
    for (const [kind, list] of [['error', r.errors], ['warning', r.warnings]]) {
      for (const f of list) {
        const props = [f.file && `file=${annotationEscape(f.file, true)}`, f.line && `line=${f.line}`, `title=${annotationEscape(f.code, true)}`].filter(Boolean).join(',');
        console.log(`::${kind} ${props}::${annotationEscape(`${f.message} | fix: ${CODES[f.code]}`)}`);
      }
    }
  }
  console.log(r.ok ? `workspace guard: clean${r.warnings.length ? ` (${r.warnings.length} warning${r.warnings.length === 1 ? '' : 's'})` : ''}` : `workspace guard: FAILED with ${r.errors.length} error${r.errors.length === 1 ? '' : 's'}; see ${DOC}`);
}

async function main(argv) {
  const usage = 'usage: node scripts/check-workspace.mjs [--with-pnpm] [--json] [--root <dir>]';
  const opts = { root: resolve(dirname(fileURLToPath(import.meta.url)), '..'), withPnpm: false, json: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--with-pnpm') opts.withPnpm = true;
    else if (a === '--json') opts.json = true;
    else if (a === '--root' && argv[i + 1]) opts.root = resolve(argv[++i]);
    else if (a === '--help' || a === '-h') { console.log(usage); return 0; }
    else { console.error(`unknown argument ${a}\n${usage}`); return 2; }
  }
  const r = await checkWorkspace({ root: opts.root, withPnpm: opts.withPnpm });
  if (opts.json) console.log(JSON.stringify({ ...r, fixes: Object.fromEntries([...r.errors, ...r.warnings].map((f) => [f.code, CODES[f.code]])) }, null, 2));
  else printText(r);
  return r.ok ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  main(process.argv.slice(2)).then((code) => { process.exitCode = code; });
}
