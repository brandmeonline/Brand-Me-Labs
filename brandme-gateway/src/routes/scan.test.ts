/**
 * Legacy /scan (BM-BASE-005): 503 problem+json without NATS (never a 500),
 * 501 problem+json for the unpersisted status route, spec Problem errors.
 * The real-app 503/501 path with a signed-in member runs in
 * routes/v1/me.test.ts against the Spanner emulator.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import express from 'express';
import request from 'supertest';
import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import { describe, expect, it } from 'vitest';
import { loadConfig } from '../config';
import { createApp } from '../index';
import { authMiddleware } from '../middleware/auth';
import { errorHandler } from '../middleware/errorHandler';
import type { IdentityStore } from '../middleware/identity/store';
import { requestContext } from '../middleware/problem';
import { createScanRouter, type ScanRouterDeps } from './scan';

const REPO = resolve(__dirname, '../../..');
const spec = JSON.parse(readFileSync(resolve(REPO, 'docs/design/brandme/contracts/domain.schema.json'), 'utf8'));
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
const isSpecProblem = ajv.compile(spec.$defs.Problem);

function scanApp(deps: Partial<ScanRouterDeps>, signedIn = true) {
  const app = express();
  app.use(requestContext('development'));
  app.use(express.json());
  app.use((_req, res, next) => {
    if (signedIn) res.locals.principal = { memberId: 'member-1' };
    next();
  });
  app.use('/scan', authMiddleware, createScanRouter({ natsConfigured: false, defaultRegion: 'us-east1', ...deps }));
  app.use(errorHandler);
  return app;
}

const expectProblem = (r: request.Response, status: number, code: string) => {
  expect(r.status).toBe(status);
  expect(r.headers['content-type']).toMatch(/^application\/problem\+json/);
  expect(isSpecProblem(r.body), JSON.stringify(isSpecProblem.errors)).toBe(true);
  expect(r.body.code).toBe(code);
  expect(r.text).not.toMatch(/stack|Error:|JetStream/);
};

describe('legacy /scan', () => {
  it('POST without NATS configured is a non-retryable 503 problem, not a 500', async () => {
    const r = await request(scanApp({ natsConfigured: false })).post('/scan').send({ garment_tag: 'TAG-1' });
    expectProblem(r, 503, 'dependency_unavailable');
    expect(r.body.retryable).toBe(false);
  });

  it('POST with NATS configured but unreachable is a retryable 503 problem', async () => {
    const publish = async () => { throw new Error('JetStream not initialized'); };
    const r = await request(scanApp({ natsConfigured: true, publish })).post('/scan').send({ garment_tag: 'TAG-1' });
    expectProblem(r, 503, 'dependency_unavailable');
    expect(r.body.retryable).toBe(true);
  });

  it('POST publishes scan.requested for the signed-in member and answers 202', async () => {
    const sent: { subject: string; data: Record<string, unknown> }[] = [];
    const publish = async (subject: string, data: Record<string, unknown>) => { sent.push({ subject, data }); };
    const r = await request(scanApp({ natsConfigured: true, publish })).post('/scan').set('X-Region', 'eu-west1').send({ garment_tag: 'TAG-1', user_id: 'spoofed' });
    expect(r.status).toBe(202);
    expect(sent).toHaveLength(1);
    expect(sent[0].subject).toBe('scan.requested');
    expect(sent[0].data).toMatchObject({ scan_id: r.body.scan_id, scanner_user_id: 'member-1', garment_tag: 'TAG-1', region_code: 'eu-west1', request_id: r.headers['x-request-id'] });
  });

  it('POST with an invalid body is a 422 problem', async () => {
    expectProblem(await request(scanApp({})).post('/scan').send({}), 422, 'invalid_request');
  });

  it('GET /scan/:id honestly answers 501 instead of a placeholder status', async () => {
    const r = await request(scanApp({ natsConfigured: true })).get('/scan/abc');
    expectProblem(r, 501, 'not_implemented');
    expect(r.text).not.toContain('processing');
  });

  it('signed-out requests get a 401 problem', async () => {
    expectProblem(await request(scanApp({}, false)).post('/scan').send({ garment_tag: 'x' }), 401, 'unauthenticated');
  });

  it('through createApp: auth and malformed bodies answer spec Problems', async () => {
    const gw = createApp(loadConfig({ BRANDME_MODE: 'development' }), {} as IdentityStore);
    expectProblem(await request(gw).post('/scan').send({ garment_tag: 'x' }), 401, 'unauthenticated');
    expectProblem(await request(gw).get('/scan/abc'), 401, 'unauthenticated');
    expectProblem(await request(gw).post('/scan').set('Content-Type', 'application/json').send('{"garment_tag":'), 422, 'invalid_request');
  });
});
