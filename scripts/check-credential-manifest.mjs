#!/usr/bin/env node
// Credential manifest guard (docs/build/security/credential-manifest.yaml).
//
//   node scripts/check-credential-manifest.mjs [--root DIR] [--manifest PATH] [--strict] [--json] [--dump-manifest]
//
// Scans git-tracked source (*.ts *.tsx *.js *.mjs *.cjs *.py *.sh, docker-compose*.yml and
// .github/workflows/*.yml) for environment reads whose names look secret-shaped and FAILS when
//   - a secret-shaped name is read but has no manifest row,
//   - a NEXT_PUBLIC_ name is secret-shaped (browser bundles are public),
//   - a tracked env file is not a *.example template,
//   - an env template declares a secret-shaped name that has no manifest row,
//   - the manifest itself is malformed (see validateManifest).
// It WARNS (exit 0 unless --strict) on manifest consumers that no longer reference their name,
// template values for secret names, and credentials embedded in template URLs.
//
// Node built-ins only. The manifest uses a deliberately small YAML subset that this file
// parses itself (parseManifestYaml); anything outside the subset is a hard error, never a guess.
// The subset is documented in docs/build/security/secrets-conventions.md.
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const SECRET_SHAPED = /(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|PRIVATE|SEED|SEEDS|MNEMONIC|DSN)/;
export const DEFAULT_MANIFEST = 'docs/build/security/credential-manifest.yaml';

export const LANES = ['fnd', 'com', 'dom', 'rts', 'ui', 'ar'];
// BRANDME_MODE words, plus two pseudo-modes for values that never reach a deployed service:
// `ci` (GitHub Actions only) and `local` (a developer workstation only).
export const MODES = ['demo', 'development', 'sandbox', 'production', 'ci', 'local'];
export const STATUSES = ['active', 'planned', 'legacy-unread', 'refused'];
export const ROTATION_CLASSES = [
  'internal-bearer', 'provider-token', 'test-wallet-seeds', 'signing-key', 'gcp-keyless',
  'gcp-sa-key-legacy', 'reference', 'not-secret', 'retire',
];
const REQUIRED_FIELDS = ['name', 'kind', 'secret', 'lane_owner', 'consumers', 'modes', 'secret_manager_id',
  'github_location', 'validation', 'distinct_from', 'rotation_class', 'cadence_days', 'status',
  'created_by_this_lane'];
const OPTIONAL_FIELDS = ['templates', 'notes'];
const NEW_NAME_TYPES = /_(TOKEN|KEY|KID|SEEDS|SECRET_REF|URL)$/;
const SM_ID = /^brandme-(<mode>|development|sandbox|production)-(fnd|com|dom|rts|ui|ar)-[a-z0-9]+(-[a-z0-9]+)*$/;
const GH_LOCATION = /^(env:(sandbox|production)\/([A-Z][A-Z0-9_]*)|env-var:(sandbox|production)\/([A-Z][A-Z0-9_]*)|repo-secret:([A-Z][A-Z0-9_]*)|repo-var:([A-Z][A-Z0-9_]*))$/;
const REPO_SECRET_NEW = /^BM_(SANDBOX|PRODUCTION)_(FND|COM|DOM|RTS|UI|AR)_[A-Z0-9_]+$/;

// Paths that are generated or vendored, not authored. Legacy code is NOT excluded: its names are
// listed in the manifest with status legacy-unread instead, so nothing escapes the inventory.
export const EXCLUDED_PATHS = [
  /(^|\/)node_modules\//,
  /(^|\/)(vendor|vendored|third_party)\//,
  /(^|\/)(dist|build|out|coverage|\.next)\//,
  /(^|\/)generated\//, // packages/*/generated: pnpm contracts:generate output
  /^brandme-chain\/contracts\/managed\//, // Compact compiler output
  /\.min\.js$/,
  /\.d\.ts$/,
];

// ---- YAML subset ------------------------------------------------------------------------------

class ManifestSyntaxError extends Error {
  constructor(line, message) {
    super(`manifest line ${line}: ${message}`);
    this.line = line;
  }
}

// Strip a trailing comment that starts with whitespace + '#' outside quotes.
function stripComment(text, lineNo) {
  let quote = null;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quote) {
      if (ch === quote) {
        if (quote === "'" && text[i + 1] === "'") { i++; continue; }
        quote = null;
      } else if (quote === '"' && ch === '\\') i++;
    } else if (ch === "'" || ch === '"') {
      quote = ch;
    } else if (ch === '#' && (i === 0 || /\s/.test(text[i - 1]))) {
      return text.slice(0, i).trimEnd();
    }
  }
  if (quote) throw new ManifestSyntaxError(lineNo, 'unterminated quoted string');
  return text.trimEnd();
}

const PLAIN_FORBIDDEN_START = /^[[\]{}&*!|>%@`,?]/;

function parseScalar(raw, lineNo) {
  const s = raw.trim();
  if (s === '') throw new ManifestSyntaxError(lineNo, 'empty value (write null, [] or a quoted empty string)');
  if (s.startsWith("'")) {
    if (!s.endsWith("'") || s.length < 2) throw new ManifestSyntaxError(lineNo, 'bad single-quoted string');
    const body = s.slice(1, -1);
    if (body.replace(/''/g, '').includes("'")) throw new ManifestSyntaxError(lineNo, 'stray quote in single-quoted string');
    return body.replace(/''/g, "'");
  }
  if (s.startsWith('"')) {
    if (!s.endsWith('"') || s.length < 2) throw new ManifestSyntaxError(lineNo, 'bad double-quoted string');
    const body = s.slice(1, -1);
    let out = '';
    for (let i = 0; i < body.length; i++) {
      const ch = body[i];
      if (ch === '"') throw new ManifestSyntaxError(lineNo, 'unescaped quote in double-quoted string');
      if (ch !== '\\') { out += ch; continue; }
      const next = body[++i];
      if (next === '"' || next === '\\') out += next;
      else if (next === 'n') out += '\n';
      else throw new ManifestSyntaxError(lineNo, `unsupported escape \\${next ?? ''} (use single quotes for regexes)`);
    }
    return out;
  }
  if (PLAIN_FORBIDDEN_START.test(s)) throw new ManifestSyntaxError(lineNo, `unsupported YAML syntax '${s[0]}' (quote the value)`);
  if (/:\s/.test(s) || s.endsWith(':')) throw new ManifestSyntaxError(lineNo, 'plain value contains ": " (quote it)');
  if (s === 'true') return true;
  if (s === 'false') return false;
  if (s === 'null' || s === '~') return null;
  if (/^-?(0|[1-9]\d*)$/.test(s)) return Number(s);
  // Values another YAML parser would type differently must be quoted, so every reader agrees.
  if (/^(yes|no|on|off|y|n|true|false|null)$/i.test(s)) throw new ManifestSyntaxError(lineNo, `ambiguous boolean-like value '${s}' (quote it)`);
  if (/^[-+.]?\d/.test(s) || /^[-+]?\.(inf|nan)$/i.test(s)) throw new ManifestSyntaxError(lineNo, `number-like value '${s}' (quote it or use a plain integer)`);
  return s;
}

function parseFlowSeq(raw, lineNo) {
  const s = raw.trim();
  if (!s.endsWith(']')) throw new ManifestSyntaxError(lineNo, 'flow sequences must open and close on one line');
  const inner = s.slice(1, -1).trim();
  if (inner === '') return [];
  const items = [];
  let cur = '';
  let quote = null;
  for (let i = 0; i < inner.length; i++) {
    const ch = inner[i];
    if (quote) {
      cur += ch;
      if (ch === quote) {
        if (quote === "'" && inner[i + 1] === "'") { cur += inner[++i]; continue; }
        quote = null;
      } else if (quote === '"' && ch === '\\') cur += inner[++i];
    } else if (ch === "'" || ch === '"') {
      quote = ch;
      cur += ch;
    } else if (ch === ',') {
      items.push(cur);
      cur = '';
    } else if (ch === '[' || ch === ']' || ch === '{' || ch === '}') {
      throw new ManifestSyntaxError(lineNo, 'nested flow collections are not supported');
    } else cur += ch;
  }
  items.push(cur);
  return items.map((it) => {
    const v = parseScalar(it, lineNo);
    if (typeof v === 'string' && /:/.test(it) && !/^\s*['"]/.test(it)) {
      throw new ManifestSyntaxError(lineNo, 'values containing ":" inside [...] must be quoted');
    }
    return v;
  });
}

function parseValue(raw, lineNo) {
  const s = raw.trim();
  return s.startsWith('[') ? parseFlowSeq(s, lineNo) : parseScalar(s, lineNo);
}

const KEY_LINE = /^([a-z_][a-z0-9_]*):(?:\s+(.*))?$/;

/**
 * Parse the manifest's YAML subset:
 *   top level: `key: scalar` lines, or `key:` followed by an indented block sequence;
 *   block sequence items: scalars (`- value`) or mappings (`- key: value` + more `key: value` lines);
 *   mapping values: scalar, one-line flow sequence `[a, 'b']`, or `key:` + block sequence of scalars;
 *   scalars: plain, 'single' ('' escapes) or "double" (\" \\ \n escapes); true/false/null/integers.
 * Rejected with a line number: tabs, anchors/aliases/tags, block scalars (| >), flow mappings,
 * document markers, duplicate keys, inconsistent indentation, ambiguous yes/no and number-like
 * plain values.
 */
export function parseManifestYaml(text) {
  const lines = [];
  text.split('\n').forEach((rawLine, idx) => {
    const lineNo = idx + 1;
    if (/\t/.test(rawLine)) throw new ManifestSyntaxError(lineNo, 'tabs are not allowed');
    if (/^\s*#/.test(rawLine) || rawLine.trim() === '') return;
    if (/^(---|\.\.\.)(\s|$)/.test(rawLine)) throw new ManifestSyntaxError(lineNo, 'document markers are not supported');
    const content = stripComment(rawLine, lineNo);
    if (content.trim() === '') return;
    const indent = content.length - content.trimStart().length;
    lines.push({ lineNo, indent, text: content.trim() });
  });

  let pos = 0;
  const peek = () => lines[pos];

  function parseMapping(indent, first) {
    const obj = {};
    const add = (key, value, lineNo) => {
      if (Object.prototype.hasOwnProperty.call(obj, key)) throw new ManifestSyntaxError(lineNo, `duplicate key '${key}'`);
      obj[key] = value;
    };
    const handle = (text, lineNo) => {
      const m = KEY_LINE.exec(text);
      if (!m) throw new ManifestSyntaxError(lineNo, `expected 'key: value', got '${text}'`);
      const [, key, rest] = m;
      if (rest === undefined || rest === '') {
        const next = peek();
        if (!next || next.indent <= indent) throw new ManifestSyntaxError(lineNo, `'${key}:' needs a value or an indented block`);
        add(key, parseSequence(next.indent), lineNo);
      } else {
        add(key, parseValue(rest, lineNo), lineNo);
      }
    };
    if (first) handle(first.text, first.lineNo);
    while (pos < lines.length) {
      const line = peek();
      if (line.indent < indent) break;
      if (line.indent > indent) throw new ManifestSyntaxError(line.lineNo, 'unexpected indentation');
      if (line.text.startsWith('- ') || line.text === '-') break;
      pos++;
      handle(line.text, line.lineNo);
    }
    return obj;
  }

  function parseSequence(indent) {
    const out = [];
    while (pos < lines.length) {
      const line = peek();
      if (line.indent < indent) break;
      if (line.indent > indent) throw new ManifestSyntaxError(line.lineNo, 'unexpected indentation');
      if (!(line.text.startsWith('- ') || line.text === '-')) {
        throw new ManifestSyntaxError(line.lineNo, 'expected a sequence item "- ..."');
      }
      pos++;
      const rest = line.text === '-' ? '' : line.text.slice(2).trim();
      if (rest === '') throw new ManifestSyntaxError(line.lineNo, 'empty sequence item');
      if (KEY_LINE.test(rest) && !/^['"]/.test(rest)) {
        // Mapping item: following keys sit two columns right of the dash.
        out.push(parseMapping(indent + 2, { text: rest, lineNo: line.lineNo }));
      } else {
        out.push(parseValue(rest, line.lineNo));
      }
    }
    return out;
  }

  if (lines.length === 0) throw new ManifestSyntaxError(1, 'manifest is empty');
  if (lines[0].indent !== 0) throw new ManifestSyntaxError(lines[0].lineNo, 'top level must not be indented');
  const doc = parseMapping(0);
  if (pos < lines.length) throw new ManifestSyntaxError(lines[pos].lineNo, 'unexpected content');
  return doc;
}

// ---- manifest validation ----------------------------------------------------------------------

const asList = (v) => (Array.isArray(v) ? v : []);

export function validateManifest(doc) {
  const errors = [];
  const err = (name, msg) => errors.push(`manifest${name ? ` ${name}` : ''}: ${msg}`);
  if (!doc || typeof doc !== 'object') return { errors: ['manifest: not a mapping'], entries: new Map() };
  if (doc.schema !== 'brandme-credential-manifest/1') err('', "schema must be 'brandme-credential-manifest/1'");
  if (!Array.isArray(doc.entries)) return { errors: [...errors, 'manifest: entries must be a sequence'], entries: new Map() };
  const entries = new Map();
  for (const [i, e] of doc.entries.entries()) {
    if (!e || typeof e !== 'object' || Array.isArray(e)) { err(`#${i + 1}`, 'entry must be a mapping'); continue; }
    const name = typeof e.name === 'string' ? e.name : `#${i + 1}`;
    for (const f of REQUIRED_FIELDS) if (!(f in e)) err(name, `missing field '${f}'`);
    for (const f of Object.keys(e)) if (!REQUIRED_FIELDS.includes(f) && !OPTIONAL_FIELDS.includes(f)) err(name, `unknown field '${f}'`);
    if (!/^[A-Z][A-Z0-9_]*$/.test(String(e.name ?? ''))) err(name, 'name must be an UPPER_SNAKE env name');
    if (entries.has(e.name)) err(name, 'duplicate entry');
    if (typeof e.secret !== 'boolean') err(name, 'secret must be true or false');
    if (typeof e.created_by_this_lane !== 'boolean') err(name, 'created_by_this_lane must be true or false');
    if (typeof e.kind !== 'string' || !/^[a-z0-9]+(-[a-z0-9]+)*$/.test(e.kind)) err(name, 'kind must be a kebab-case word');
    if (!LANES.includes(e.lane_owner)) err(name, `lane_owner must be one of ${LANES.join(', ')}`);
    if (!STATUSES.includes(e.status)) err(name, `status must be one of ${STATUSES.join(', ')}`);
    if (!ROTATION_CLASSES.includes(e.rotation_class)) err(name, `rotation_class must be one of ${ROTATION_CLASSES.join(', ')}`);
    if (!(e.cadence_days === null || (Number.isInteger(e.cadence_days) && e.cadence_days > 0))) err(name, 'cadence_days must be a positive integer or null');
    for (const f of ['consumers', 'modes', 'github_location', 'distinct_from', ...(('templates' in e) ? ['templates'] : [])]) {
      if (!Array.isArray(e[f])) err(name, `${f} must be a sequence ([] when empty)`);
    }
    for (const m of asList(e.modes)) if (!MODES.includes(m)) err(name, `unknown mode '${m}'`);
    for (const c of [...asList(e.consumers), ...asList(e.templates)]) {
      if (typeof c !== 'string' || !/^[^\s:]+(:\d+(-\d+)?)?$/.test(c)) err(name, `consumer/template '${c}' must be path or path:line`);
    }
    if (typeof e.notes !== 'undefined' && typeof e.notes !== 'string') err(name, 'notes must be a string');
    const sm = e.secret_manager_id;
    if (sm !== 'none') {
      const m = typeof sm === 'string' ? SM_ID.exec(sm) : null;
      if (!m) err(name, "secret_manager_id must be 'none' or brandme-<mode>-<lane>-<purpose-kebab>");
      else if (m[2] !== e.lane_owner) err(name, `secret_manager_id lane '${m[2]}' differs from lane_owner '${e.lane_owner}'`);
      if (e.secret === false) err(name, 'non-secret entries must not have a Secret Manager id');
    }
    for (const loc of asList(e.github_location)) {
      const m = typeof loc === 'string' ? GH_LOCATION.exec(loc) : null;
      if (!m) { err(name, `github_location '${loc}' must be env:<environment>/NAME, env-var:<environment>/NAME, repo-secret:NAME or repo-var:NAME`); continue; }
      const envSecret = m[3];
      const repoSecret = m[6];
      if (envSecret && envSecret !== e.name) err(name, `GitHub Environment secret '${envSecret}' must equal the runtime name`);
      if (repoSecret && e.status === 'planned' && !REPO_SECRET_NEW.test(repoSecret)) err(name, `new repo-level secret '${repoSecret}' must be BM_<MODE>_<LANE>_<PURPOSE>`);
      if ((m[4] || m[7]) && e.secret === true) err(name, 'secrets must not be stored as GitHub variables');
    }
    if (e.validation !== 'none') {
      if (typeof e.validation !== 'string') err(name, "validation must be 'none' or a quoted regex");
      else {
        try { new RegExp(e.validation); } catch { err(name, 'validation regex does not compile'); }
        if (!e.validation.startsWith('^') || !e.validation.endsWith('$')) err(name, 'validation regex must be anchored with ^...$');
      }
    }
    if (typeof e.name === 'string' && e.name.startsWith('NEXT_PUBLIC_') && (e.secret === true || SECRET_SHAPED.test(e.name.slice(12)))) {
      err(name, 'NEXT_PUBLIC_ values are compiled into browser bundles and can never be secrets');
    }
    if (e.status === 'planned' && typeof e.name === 'string' && e.secret === true && !NEW_NAME_TYPES.test(e.name)) {
      err(name, 'new secret names must end in _TOKEN, _KEY, _KID, _SEEDS, _SECRET_REF or _URL');
    }
    if (e.created_by_this_lane === true && e.status === 'legacy-unread') err(name, 'legacy entries cannot be created by a lane');
    if (typeof e.name === 'string') entries.set(e.name, e);
  }
  for (const [name, e] of entries) {
    for (const other of asList(e.distinct_from)) {
      if (other === name) err(name, 'distinct_from lists itself');
      else if (!entries.has(other)) err(name, `distinct_from names unknown entry '${other}'`);
      else if (!asList(entries.get(other).distinct_from).includes(name)) err(name, `distinct_from is not symmetric: ${other} does not list ${name}`);
    }
  }
  return { errors, entries };
}

// ---- repository scan ------------------------------------------------------------------------

const ID = '([A-Za-z_][A-Za-z0-9_]*)';
const UP = '([A-Z][A-Z0-9_]*)';
const Q = `(['"\`])`;
// [regex, nameGroup, mixedCaseAllowed]. Mixed-case names are tested upper-cased only for
// unambiguous env APIs; `env.X` / `$X` style reads only count UPPER_SNAKE names.
const JS_PATTERNS = [
  [new RegExp(`process\\.env\\.${ID}`, 'g'), 1, true],
  [new RegExp(`process\\.env\\[\\s*${Q}${ID}\\1\\s*\\]`, 'g'), 2, true],
  [new RegExp(`import\\.meta\\.env\\.${ID}`, 'g'), 1, true],
  [new RegExp(`\\benv\\.${UP}\\b`, 'g'), 1, false],
  [new RegExp(`\\benv\\[\\s*${Q}${UP}\\1\\s*\\]`, 'g'), 2, false],
  [new RegExp(`\\bstubEnv\\(\\s*${Q}${ID}\\1`, 'g'), 2, true],
];
const PY_PATTERNS = [
  [new RegExp(`\\benviron\\[\\s*${Q}${ID}\\1\\s*\\]`, 'g'), 2, true],
  [new RegExp(`\\benviron\\.(?:get|pop|setdefault)\\(\\s*${Q}${ID}\\1`, 'g'), 2, true],
  [new RegExp(`\\bgetenv\\(\\s*${Q}${ID}\\1`, 'g'), 2, true],
  [new RegExp(`\\benv\\.get\\(\\s*${Q}${UP}\\1`, 'g'), 2, false],
  [new RegExp(`\\benv\\[\\s*${Q}${UP}\\1\\s*\\]`, 'g'), 2, false],
  [new RegExp(`\\b(?:setenv|delenv)\\(\\s*${Q}${ID}\\1`, 'g'), 2, true],
];
const SH_PATTERNS = [
  [new RegExp(`\\$\\{${UP}`, 'g'), 1, false],
  [new RegExp(`\\$${UP}`, 'g'), 1, false],
];
const WORKFLOW_PATTERNS = [
  [new RegExp(`\\bsecrets\\.${ID}`, 'g'), 1, true],
  [new RegExp(`\\bsecrets\\[\\s*${Q}${ID}\\1\\s*\\]`, 'g'), 2, true],
  [new RegExp(`\\$\\{\\{[^}]*\\benv\\.${UP}`, 'g'), 1, false],
  ...SH_PATTERNS,
];

function patternsFor(path) {
  if (/^\.github\/workflows\/[^/]+\.ya?ml$/.test(path)) return { patterns: WORKFLOW_PATTERNS, comment: /^\s*#/ };
  if (/(^|\/)docker-compose[^/]*\.ya?ml$/.test(path)) return { patterns: SH_PATTERNS.slice(0, 1), comment: /^\s*#/ };
  if (/\.(ts|tsx|js|mjs|cjs)$/.test(path)) return { patterns: JS_PATTERNS, comment: /^\s*(\/\/|\/?\*)/ };
  if (/\.py$/.test(path)) return { patterns: PY_PATTERNS, comment: /^\s*#/ };
  if (/\.sh$/.test(path)) return { patterns: SH_PATTERNS, comment: /^\s*#/ };
  return null;
}

export const isSecretShaped = (name, mixedCaseAllowed = true) => {
  if (/^[A-Z0-9_]+$/.test(name)) return SECRET_SHAPED.test(name);
  return mixedCaseAllowed && SECRET_SHAPED.test(name.toUpperCase());
};
const nextPublicSecret = (name) => name.toUpperCase().startsWith('NEXT_PUBLIC_') && SECRET_SHAPED.test(name.toUpperCase().slice(12));

export function findEnvReads(path, text) {
  const spec = patternsFor(path);
  if (!spec) return [];
  const reads = new Map();
  text.split('\n').forEach((line, i) => {
    if (spec.comment.test(line)) return;
    for (const [re, group, mixed] of spec.patterns) {
      for (const m of line.matchAll(re)) {
        const name = m[group];
        // One read per path:line:name (process.env.X also matches the env.X pattern).
        if (isSecretShaped(name, mixed) || nextPublicSecret(name)) reads.set(`${i + 1}:${name}`, { path, line: i + 1, name });
      }
    }
  });
  return [...reads.values()];
}

export const isEnvFile = (path) => {
  const b = basename(path);
  return /^\.env(\.|$)/.test(b) || /\.env$/.test(b) || b === '.envrc';
};
export const isEnvTemplate = (path) => isEnvFile(path) && path.endsWith('.example');

export function parseEnvTemplate(path, text) {
  const decls = [];
  text.split('\n').forEach((line, i) => {
    const m = /^\s*(#\s*)?(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)$/.exec(line);
    if (!m) return;
    const commented = Boolean(m[1]);
    let value = m[3].trim();
    if (!/^['"]/.test(value)) value = value.replace(/\s+#.*$/, '').trim();
    decls.push({ path, line: i + 1, name: m[2], value, commented });
  });
  return decls;
}

const isPlaceholder = (v) => v === '' || v === '""' || v === "''" || /^<[^<>]*>$/.test(v);

function gitTracked(root) {
  const r = spawnSync('git', ['ls-files', '-z'], { cwd: root, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  if (r.status !== 0) throw new Error(`git ls-files failed in ${root}: ${r.stderr.trim()}`);
  return r.stdout.split('\0').filter(Boolean);
}

function refMatches(root, ref, name, tracked) {
  const m = /^([^:]+)(?::(\d+)(?:-(\d+))?)?$/.exec(ref);
  const [, file, a, b] = m ?? [null, ref];
  if (!tracked.has(file) || !existsSync(join(root, file))) return 'missing';
  const lines = readFileSync(join(root, file), 'utf8').split('\n');
  if (!lines.some((l) => l.includes(name))) return 'absent';
  if (a) {
    const from = Number(a);
    const to = Number(b ?? a);
    if (!lines.slice(from - 1, to).some((l) => l.includes(name))) return 'drift';
  }
  return 'ok';
}

export function checkRepo({ root, manifestPath = DEFAULT_MANIFEST } = {}) {
  const errors = [];
  const warnings = [];
  const absManifest = resolve(root, manifestPath);
  if (!existsSync(absManifest)) return { errors: [`manifest not found: ${manifestPath}`], warnings, reads: [] };
  let doc;
  try {
    doc = parseManifestYaml(readFileSync(absManifest, 'utf8'));
  } catch (e) {
    return { errors: [e.message], warnings, reads: [] };
  }
  const { errors: mErrors, entries } = validateManifest(doc);
  errors.push(...mErrors);

  const trackedList = gitTracked(root);
  const tracked = new Set(trackedList);
  const relManifest = absManifest.startsWith(resolve(root) + '/') ? absManifest.slice(resolve(root).length + 1) : null;
  if (relManifest && !tracked.has(relManifest)) warnings.push(`${relManifest}: manifest is not tracked by git (docs/build/ is gitignored by build/; add it with git add -f)`);

  const reads = [];
  for (const path of trackedList) {
    const abs = join(root, path);
    // Env files are checked everywhere, including generated and vendored paths.
    if (isEnvFile(path) && !isEnvTemplate(path)) {
      errors.push(`${path}: tracked env file; only *.example templates (names and placeholders) may be committed`);
      continue;
    }
    if (EXCLUDED_PATHS.some((re) => re.test(path))) continue;
    if (isEnvTemplate(path)) {
      if (!existsSync(abs)) continue;
      for (const d of parseEnvTemplate(path, readFileSync(abs, 'utf8'))) {
        if (nextPublicSecret(d.name)) errors.push(`${path}:${d.line}: ${d.name} is secret-shaped but NEXT_PUBLIC_ values ship to browsers`);
        else if (SECRET_SHAPED.test(d.name) && !entries.has(d.name)) errors.push(`${path}:${d.line}: template declares secret-shaped ${d.name}, which has no manifest row`);
        const entry = entries.get(d.name);
        if (!d.commented && (entry?.secret === true || (!entry && SECRET_SHAPED.test(d.name))) && !isPlaceholder(d.value)) {
          warnings.push(`${path}:${d.line}: template assigns a value to secret ${d.name}; templates carry names only (leave it empty or <placeholder>)`);
        }
        if (!d.commented && /^[a-z][a-z0-9+.-]*:\/\/[^/\s:@]*:[^/\s@]+@/i.test(d.value)) {
          warnings.push(`${path}:${d.line}: ${d.name} embeds credentials in a URL`);
        }
      }
      continue;
    }
    if (!patternsFor(path) || !existsSync(abs)) continue;
    reads.push(...findEnvReads(path, readFileSync(abs, 'utf8')));
  }

  const missing = new Map();
  for (const r of reads) {
    if (nextPublicSecret(r.name)) errors.push(`${r.path}:${r.line}: ${r.name} is secret-shaped but NEXT_PUBLIC_ values ship to browsers`);
    else if (!entries.has(r.name)) missing.set(r.name, [...(missing.get(r.name) ?? []), `${r.path}:${r.line}`]);
  }
  for (const [name, at] of missing) {
    const shown = at.slice(0, 5).join(', ') + (at.length > 5 ? `, +${at.length - 5} more` : '');
    errors.push(`secret-shaped env read ${name} has no row in ${manifestPath} (read at ${shown})`);
  }

  for (const [name, e] of entries) {
    let live = 0;
    for (const ref of asList(e.consumers)) {
      const s = refMatches(root, ref, name, tracked);
      if (s === 'missing') warnings.push(`manifest ${name}: consumer ${ref} no longer exists (stale)`);
      else if (s === 'absent') warnings.push(`manifest ${name}: consumer ${ref} no longer references ${name} (stale)`);
      else if (s === 'drift') { live++; warnings.push(`manifest ${name}: consumer ${ref} moved (name found elsewhere in the file; update the line)`); }
      else live++;
    }
    for (const ref of asList(e.templates)) {
      const s = refMatches(root, ref, name, tracked);
      if (s === 'missing' || s === 'absent') warnings.push(`manifest ${name}: template ${ref} no longer declares ${name} (stale)`);
      else if (s === 'drift') warnings.push(`manifest ${name}: template ${ref} moved (update the line)`);
    }
    if (e.status === 'active' && live === 0) warnings.push(`manifest ${name}: status active but no consumer still references it`);
  }
  return { errors, warnings, reads, entries: entries.size };
}

// ---- CLI --------------------------------------------------------------------------------------

function main(argv) {
  const arg = (name) => {
    const i = argv.indexOf(`--${name}`);
    return i >= 0 ? argv[i + 1] : undefined;
  };
  const root = resolve(arg('root') ?? join(dirname(fileURLToPath(import.meta.url)), '..'));
  const manifestPath = arg('manifest') ?? DEFAULT_MANIFEST;
  if (argv.includes('--dump-manifest')) {
    process.stdout.write(JSON.stringify(parseManifestYaml(readFileSync(resolve(root, manifestPath), 'utf8')), null, 2) + '\n');
    return 0;
  }
  const result = checkRepo({ root, manifestPath });
  const strict = argv.includes('--strict');
  const ok = result.errors.length === 0 && (!strict || result.warnings.length === 0);
  if (argv.includes('--json')) {
    process.stdout.write(JSON.stringify({ ok, errors: result.errors, warnings: result.warnings, secret_shaped_reads: result.reads.length, entries: result.entries ?? 0 }, null, 2) + '\n');
    return ok ? 0 : 1;
  }
  for (const e of result.errors) console.error(`✖ ${e}`);
  for (const w of result.warnings) console.error(`! ${w}`);
  const summary = `${result.entries ?? 0} manifest entries, ${result.reads.length} secret-shaped env reads, ${result.errors.length} errors, ${result.warnings.length} warnings`;
  console.log(ok ? `✓ credential manifest: ${summary}` : `✖ credential manifest: ${summary}${strict && result.errors.length === 0 ? ' (--strict: warnings fail)' : ''}`);
  return ok ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    process.exit(main(process.argv.slice(2)));
  } catch (e) {
    console.error(`✖ ${e.message}`);
    process.exit(1);
  }
}
