/**
 * Problem contract: every body the gateway's problem helpers emit validates
 * against the spec Problem (docs/design/brandme/contracts/domain.schema.json,
 * additionalProperties:false). Metadata travels in headers, never as
 * extension members; stacks and error messages never leave.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import express from 'express';
import request from 'supertest';
import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import { describe, expect, it } from 'vitest';
import { errorHandler } from './errorHandler';
import { ApiProblem, problemHandler, problems, requestContext } from './problem';

const REPO = resolve(__dirname, '../../..');
const spec = JSON.parse(readFileSync(resolve(REPO, 'docs/design/brandme/contracts/domain.schema.json'), 'utf8'));
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
const isSpecProblem = ajv.compile(spec.$defs.Problem);
const PROBLEM_MEMBERS = ['code', 'detail', 'instance', 'request_id', 'retryable', 'status', 'title', 'type'];

const thrown: Record<string, () => unknown> = {
  unauthenticated: problems.unauthenticated,
  forbidden: () => problems.forbidden(),
  csrf: problems.csrf,
  notFound: problems.notFound,
  conflict: () => problems.conflict('Changed since you loaded it.', 7),
  preconditionRequired: problems.preconditionRequired,
  invalid: () => problems.invalid(''),
  invalidLong: () => problems.invalid('x'.repeat(5000)),
  rateLimited: () => problems.rateLimited(12),
  notImplemented: () => problems.notImplemented('Not here.'),
  unavailable: () => problems.unavailable('Down.'),
  upstream: () => new ApiProblem(418, 'upstream_request_rejected', 'Request rejected', 'The service could not complete this request.'),
  // Lane routes still pass body extras as the 6th argument (pre-2026-10-24 signature).
  legacyExtra: () => new ApiProblem(403, 'insufficient_scope', 'Insufficient scope', 'x', false, { required_scopes: ['wardrobe:write'] }),
  unhandled: () => new Error('password=hunter2 at db.example.internal'),
};

function app(handler: typeof problemHandler | typeof errorHandler) {
  const a = express();
  a.use(requestContext('development'));
  a.use(express.json({ limit: '64b' }));
  a.post('/body', (_req, res) => { res.json({ ok: true }); });
  a.get('/p/:name', (req, _res, next) => next(thrown[req.params.name]()));
  a.use(handler);
  return a;
}

describe('problem+json bodies', () => {
  for (const [label, handler] of [['v1 problemHandler', problemHandler], ['app errorHandler', errorHandler]] as const) {
    it(`${label}: every helper yields a spec Problem with exactly its members`, async () => {
      for (const name of Object.keys(thrown)) {
        const r = await request(app(handler)).get(`/p/${name}?q=1`);
        expect(r.headers['content-type'], name).toMatch(/^application\/problem\+json/);
        expect(isSpecProblem(r.body), `${name}: ${JSON.stringify(isSpecProblem.errors)}`).toBe(true);
        expect(Object.keys(r.body).sort(), name).toEqual(PROBLEM_MEMBERS);
        expect(r.body.status).toBe(r.status);
        expect(r.body.request_id).toBe(r.headers['x-request-id']);
        expect(r.body.instance).toBe(`/p/${name}`);
      }
    });

    it(`${label}: unreadable and oversized bodies are 4xx Problems, not 500s`, async () => {
      const bad = await request(app(handler)).post('/body').set('Content-Type', 'application/json').send('{"a":');
      expect(bad.status).toBe(422);
      expect(isSpecProblem(bad.body)).toBe(true);
      const big = await request(app(handler)).post('/body').send({ a: 'x'.repeat(200) });
      expect(big.status).toBe(413);
      expect(big.body.code).toBe('payload_too_large');
      expect(isSpecProblem(big.body)).toBe(true);
    });
  }

  it('metadata goes in headers: ETag on 409, Retry-After on 429', async () => {
    const conflict = await request(app(problemHandler)).get('/p/conflict');
    expect(conflict.status).toBe(409);
    expect(conflict.headers.etag).toBe('"7"');
    expect(Object.keys(conflict.body).sort()).toEqual(PROBLEM_MEMBERS);
    for (const value of Object.values(conflict.body)) expect([7, '7', '"7"']).not.toContain(value);
    const limited = await request(app(problemHandler)).get('/p/rateLimited');
    expect(limited.headers['retry-after']).toBe('12');
    expect(limited.body).toMatchObject({ code: 'rate_limited', retryable: true });
  });

  it('accepts legacy body extras for compatibility but never sends them', async () => {
    const r = await request(app(problemHandler)).get('/p/legacyExtra');
    expect(r.status).toBe(403);
    expect(Object.keys(r.body).sort()).toEqual(PROBLEM_MEMBERS);
    expect(r.text).not.toMatch(/required_scopes|wardrobe:write/);
  });

  it('clamps detail to the spec bound and never sends an empty detail', async () => {
    const long = await request(app(problemHandler)).get('/p/invalidLong');
    expect(long.body.detail.length).toBeLessThanOrEqual(1000);
    const empty = await request(app(problemHandler)).get('/p/invalid');
    expect(empty.body.detail).toBe('Invalid request');
  });

  it('unhandled errors leak neither message nor stack', async () => {
    const r = await request(app(errorHandler)).get('/p/unhandled');
    expect(r.status).toBe(500);
    expect(r.text).not.toMatch(/hunter2|db\.example|\bat\s/);
    expect(r.body).toMatchObject({ code: 'internal_error', retryable: true });
  });

  it('refuses a status or code the spec Problem cannot carry', () => {
    expect(() => new ApiProblem(302, 'moved', 'Moved', 'x')).toThrow(TypeError);
    expect(() => new ApiProblem(600, 'x', 'X', 'x')).toThrow(TypeError);
    expect(() => new ApiProblem(400, 'Bad Code', 'X', 'x')).toThrow(TypeError);
    expect(() => new ApiProblem(400, 'a'.repeat(81), 'X', 'x')).toThrow(TypeError);
  });
});
