import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createBrandmeClient, BrandmeApiError } from '../src/index.ts';
import { unwrap } from '../src/client.ts';

const require = createRequire(import.meta.url);
const Ajv2020 = require('ajv/dist/2020').default;
const addFormats = require('ajv-formats');

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), 'utf8'));
const openapi = read('../generated/openapi.json');
const domain = read('../generated/domain.schema.json');
const examples = read('../../../docs/design/brandme/contracts/contract-examples.json');

test('generated domain schema is byte-identical to the spec input', () => {
  assert.deepEqual(domain, read('../../../docs/design/brandme/contracts/domain.schema.json'));
});

test('every $ref in the OpenAPI document resolves', () => {
  const refs: string[] = [];
  const walk = (n: unknown) => {
    if (Array.isArray(n)) n.forEach(walk);
    else if (n && typeof n === 'object') for (const [k, v] of Object.entries(n)) k === '$ref' ? refs.push(v as string) : walk(v);
  };
  walk(openapi);
  assert.ok(refs.length > 50);
  for (const r of refs) {
    assert.match(r, /^#\/components\/schemas\//);
    assert.ok(openapi.components.schemas[r.split('/').pop()!], r);
  }
});

test('operations are unique, owned and error-typed', () => {
  const ids = new Set<string>();
  for (const [path, item] of Object.entries<any>(openapi.paths)) {
    for (const [method, op] of Object.entries<any>(item)) {
      assert.ok(!ids.has(op.operationId), op.operationId);
      ids.add(op.operationId);
      assert.ok(op['x-brandme-owner'], `${method} ${path} owner`);
      assert.equal(op.responses['429'].content['application/problem+json'].schema.$ref, '#/components/schemas/Problem');
      if (['post', 'put', 'patch', 'delete'].includes(method) && op.security?.length !== 0) {
        assert.ok(op.responses['401'], `${method} ${path} must require auth`);
      }
    }
  }
  assert.ok(ids.size >= 70, `chapter 03 inventory covered (${ids.size})`);
});

test('spec examples: valid accepted, invalid rejected (ajv 2020-12)', () => {
  const ajv = new Ajv2020({ strict: false, allErrors: true });
  addFormats(ajv);
  ajv.addSchema(domain, 'domain');
  for (const ex of examples.valid) {
    const v = ajv.getSchema(`domain#/$defs/${ex.definition}`)!;
    assert.ok(v(ex.value), `${ex.definition}: ${JSON.stringify(v.errors)}`);
  }
  for (const ex of examples.invalid) {
    const v = ajv.getSchema(`domain#/$defs/${ex.definition}`)!;
    assert.equal(v(ex.value), false, `${ex.definition} should be invalid: ${ex.reason ?? ''}`);
  }
});

test('typed client calls the gateway path and adds CSRF on unsafe methods', async () => {
  const seen: Request[] = [];
  const fetchStub = async (input: Request) => {
    seen.push(input);
    if (input.method === 'PATCH') {
      return new Response(JSON.stringify({ type: 'about:blank', title: 'Conflict', status: 409, code: 'revision_conflict', detail: 'x', instance: '/me', request_id: '00000000-0000-4000-8000-000000000000', retryable: false }), { status: 409, headers: { 'content-type': 'application/problem+json' } });
    }
    return new Response(JSON.stringify({ status: 'ok', environment: 'demo', checks: [] }), { headers: { 'content-type': 'application/json' } });
  };
  const client = createBrandmeClient({ baseUrl: 'http://gw.test/api/v1', fetch: fetchStub as typeof fetch, csrfToken: () => 'csrf-abc' });
  const health = unwrap(await client.GET('/system/health'));
  assert.equal(health.status, 'ok');
  assert.equal(seen[0].url, 'http://gw.test/api/v1/system/health');
  assert.equal(seen[0].headers.get('x-csrf-token'), null);
  const res = await client.PATCH('/me', { params: { header: { 'If-Match': '"3"' } }, body: { display_name: 'Ada' } });
  assert.equal(seen[1].headers.get('x-csrf-token'), 'csrf-abc');
  assert.equal(seen[1].headers.get('if-match'), '"3"');
  assert.throws(() => unwrap(res), (e: unknown) => e instanceof BrandmeApiError && e.problem?.code === 'revision_conflict');
});
