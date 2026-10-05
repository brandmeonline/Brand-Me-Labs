#!/usr/bin/env node
// Generates the OpenAPI 3.1 document, TypeScript types and Python models from
// docs/design/brandme/contracts/domain.schema.json (read-only spec input) plus
// packages/contracts/src/foundation-schemas.json (lane extensions).
//
//   node scripts/generate.mjs           write generated/ + python/
//   node scripts/generate.mjs --check   regenerate into memory; exit 1 on drift
import { readFileSync, writeFileSync, mkdirSync, existsSync, mkdtempSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import openapiTS, { astToString } from 'openapi-typescript';
import { ENDPOINTS } from './endpoints.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const pkg = resolve(here, '..');
const repo = resolve(pkg, '../..');
const SPEC = join(repo, 'docs/design/brandme/contracts/domain.schema.json');
const EXT = join(pkg, 'src/foundation-schemas.json');
const check = process.argv.includes('--check');

const spec = JSON.parse(readFileSync(SPEC, 'utf8'));
const ext = JSON.parse(readFileSync(EXT, 'utf8'));
delete ext.$comment;

const rewriteRefs = (node) => {
  if (Array.isArray(node)) return node.map(rewriteRefs);
  if (node && typeof node === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(node)) {
      out[k] = k === '$ref' && typeof v === 'string' ? v.replace('#/$defs/', '#/components/schemas/') : rewriteRefs(v);
    }
    return out;
  }
  return node;
};

const schemas = {};
for (const [name, def] of Object.entries(spec.$defs)) schemas[name] = rewriteRefs(def);
for (const [name, def] of Object.entries(ext)) {
  if (schemas[name]) throw new Error(`extension ${name} would shadow a spec definition`);
  schemas[name] = def;
}

const ref = (name) => {
  if (!schemas[name]) throw new Error(`unknown schema ${name}`);
  return { $ref: `#/components/schemas/${name}` };
};
const problem = (description) => ({ description, content: { 'application/problem+json': { schema: ref('Problem') } } });

function operation(e) {
  const op = {
    operationId: e.id,
    tags: [e.tag],
    summary: e.summary,
    'x-brandme-owner': e.owner,
    'x-brandme-status': e.status ?? 'reserved',
    parameters: [],
    responses: {},
  };
  for (const m of e.path.matchAll(/\{(\w+)\}/g)) {
    op.parameters.push({ name: m[1], in: 'path', required: true, schema: m[1] === 'handle' ? { type: 'string' } : ref('Identifier') });
  }
  if (e.ifMatch) op.parameters.push({ name: 'If-Match', in: 'header', required: true, schema: { type: 'string' }, description: 'Quoted aggregate revision' });
  if (e.idempotent) op.parameters.push({ name: 'Idempotency-Key', in: 'header', required: true, schema: { type: 'string', minLength: 16, maxLength: 128 } });
  if (e.paginated) {
    op.parameters.push({ name: 'cursor', in: 'query', required: false, schema: { type: 'string', maxLength: 512 } });
    op.parameters.push({ name: 'limit', in: 'query', required: false, schema: { type: 'integer', minimum: 1, maximum: 100, default: 24 } });
  }
  if (!op.parameters.length) delete op.parameters;
  if (e.body) op.requestBody = { required: true, content: { 'application/json': { schema: ref(e.body) } } };
  const ok = e.created ? '201' : e.accepted ? '202' : e.noContent ? '204' : '200';
  op.responses[ok] = e.noContent
    ? { description: 'Done' }
    : { description: e.responseDescription ?? 'Success', content: { 'application/json': { schema: e.response ? (e.list ? { type: 'object', additionalProperties: false, properties: { items: { type: 'array', items: ref(e.response) }, next_cursor: { type: ['string', 'null'] } }, required: ['items', 'next_cursor'] } : ref(e.response)) : { type: 'object', description: 'Shape defined by the owning lane before implementation' } } } };
  if (e.public !== true) op.responses['401'] = problem('Not authenticated');
  op.responses['403'] = problem('Forbidden by object policy or mode');
  if (e.path.includes('{')) op.responses['404'] = problem('Not found or not visible to caller');
  if (e.ifMatch) {
    op.responses['409'] = problem('Revision conflict');
    op.responses['428'] = problem('If-Match required');
  }
  if (e.idempotent) op.responses['409'] ??= problem('Idempotency key reused with a different request');
  if (e.body) op.responses['422'] = problem('Invalid domain transition or field');
  op.responses['429'] = problem('Throttled');
  op.responses['503'] = problem('Provider or dependency unavailable; safe retry or handoff');
  if (e.public === true) op.security = [];
  return op;
}

const paths = {};
for (const e of ENDPOINTS) {
  paths[e.path] ??= {};
  if (paths[e.path][e.method]) throw new Error(`duplicate ${e.method} ${e.path}`);
  paths[e.path][e.method] = operation(e);
}

const openapi = {
  openapi: '3.1.0',
  jsonSchemaDialect: 'https://json-schema.org/draft/2020-12/schema',
  info: {
    title: 'Brand.Me public API',
    version: '0.1.0',
    description:
      'Generated from docs/design/brandme/contracts/domain.schema.json (spec $id ' + spec.$id + ') and chapter 03 endpoint inventory. ' +
      'Wire fields are snake_case. Operations marked x-brandme-status: reserved are contracts only; their owning lane implements them. ' +
      'Every JSON response carries X-Request-Id and X-Brandme-Environment headers.',
  },
  servers: [{ url: '/api/v1' }],
  security: [{ session: [] }, { bearer: [] }],
  paths,
  components: {
    schemas,
    securitySchemes: {
      session: { type: 'apiKey', in: 'cookie', name: 'bm_session', description: 'HTTP-only SameSite=Lax session; state changes also require X-CSRF-Token' },
      bearer: { type: 'http', scheme: 'bearer', bearerFormat: 'JWT', description: 'Audience-bound OIDC access token (agents/MCP)' },
    },
  },
};

const stable = (v) => JSON.stringify(v, null, 2) + '\n';
const outputs = new Map();
outputs.set('generated/openapi.json', stable(openapi));
outputs.set('generated/domain.schema.json', stable(spec));

const header = '// GENERATED by packages/contracts/scripts/generate.mjs — do not edit.\n';
const ast = await openapiTS(openapi, { alphabetize: true, exportType: true });
outputs.set('generated/api.ts', header + astToString(ast));

const schemaNames = Object.keys(schemas).sort();
outputs.set(
  'generated/schemas.ts',
  header +
    "import type { components } from './api.ts';\n\n" +
    schemaNames.map((n) => `export type ${n} = components['schemas']['${n}'];`).join('\n') +
    '\n\nexport const SCHEMA_NAMES = ' + JSON.stringify(schemaNames) + ' as const;\n' +
    'export const OPERATION_IDS = ' + JSON.stringify(ENDPOINTS.map((e) => e.id).sort()) + ' as const;\n',
);

// Python: pydantic v2 models for the spec definitions via datamodel-code-generator.
const python = process.env.BRANDME_PYTHON ?? (existsSync(join(repo, '.venv/bin/python')) ? join(repo, '.venv/bin/python') : 'python3');
const tmp = mkdtempSync(join(tmpdir(), 'bm-contracts-'));
try {
  const input = join(tmp, 'schema.json');
  const target = join(tmp, 'models.py');
  writeFileSync(input, JSON.stringify({ ...spec, title: 'BrandmeDomain' }));
  execFileSync(python, ['-m', 'datamodel_code_generator',
    '--input', input, '--input-file-type', 'jsonschema',
    '--output', target, '--output-model-type', 'pydantic_v2.BaseModel',
    '--target-python-version', '3.11', '--use-standard-collections', '--use-union-operator',
    '--field-constraints', '--use-schema-description', '--disable-timestamp',
    '--snake-case-field', '--collapse-root-models',
  ], { stdio: ['ignore', 'pipe', 'inherit'], cwd: tmp });
  outputs.set('python/brandme_contracts/models.py', '# GENERATED by packages/contracts/scripts/generate.mjs — do not edit.\n' + readFileSync(target, 'utf8'));
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
outputs.set('python/brandme_contracts/__init__.py', '"""Generated Brand.Me contract models (pydantic v2). See packages/contracts."""\nfrom . import models  # noqa: F401\n\nSPEC_ID = ' + JSON.stringify(spec.$id) + '\n');

let drift = 0;
for (const [rel, content] of outputs) {
  const file = join(pkg, rel);
  const current = existsSync(file) ? readFileSync(file, 'utf8') : null;
  if (check) {
    if (current !== content) {
      drift++;
      console.error(`drift: ${rel} is out of date (run pnpm contracts:generate)`);
    }
  } else if (current !== content) {
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, content);
    console.log(`wrote ${rel}`);
  }
}
if (check) {
  if (drift) process.exit(1);
  console.log(`contracts: no drift (${outputs.size} files, ${ENDPOINTS.length} operations, ${schemaNames.length} schemas)`);
}
