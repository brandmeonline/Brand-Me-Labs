/**
 * Request logging (ch.03 §9): only gateway-validated request IDs and templated
 * paths reach the logs; member IDs, handles and query strings do not.
 */
import express, { Router } from 'express';
import request from 'supertest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadConfig } from '../config';
import { logger } from '../config/logger';
import { createApp } from '../index';
import type { IdentityStore } from './identity/store';
import { templatePath } from './logPath';
import { requestLogger } from './requestLogger';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MEMBER = '6f1c2a3e-1111-4222-8333-944455556666';

let logged: Record<string, unknown>[] = [];
beforeEach(() => {
  logged = [];
  vi.spyOn(logger, 'info').mockImplementation(((obj: Record<string, unknown>) => { logged.push(obj); }) as never);
});
afterEach(() => vi.restoreAllMocks());

function app() {
  const a = express();
  a.use(requestLogger);
  const v1 = Router();
  v1.post('/members/:id/block', (_req, res) => { res.status(204).end(); });
  a.use('/api/v1', v1);
  a.all('*', (req, res) => { res.json({ requestId: res.locals.requestId, region: req.headers['x-region'] }); });
  return a;
}

describe('request logger', () => {
  it('logs an inbound X-Request-Id only when it is a UUID', async () => {
    const id = 'a3bb189e-8bf9-4888-9912-ace4e6543002';
    const ok = await request(app()).get('/x').set('X-Request-Id', id);
    expect(ok.headers['x-request-id']).toBe(id);
    expect(logged.map((l) => l.requestId)).toEqual([id, id]);

    for (const hostile of ['member-123', `${id}x`, 'x'.repeat(300), "<script>alert('member-123')</script>"]) {
      logged = [];
      const r = await request(app()).get('/x').set('X-Request-Id', hostile);
      const generated = r.headers['x-request-id'];
      expect(generated).toMatch(UUID);
      expect(generated).not.toBe(hostile);
      expect(r.body.requestId).toBe(generated);
      expect(logged.map((l) => l.requestId)).toEqual([generated, generated]);
      expect(JSON.stringify(logged)).not.toContain('member-123');
    }
  });

  it('templates identifier segments and drops the query string', async () => {
    const cases: [string, string][] = [
      [`/api/v1/members/${MEMBER}/block?token=abc`, '/api/v1/members/:id/block'],
      ['/api/v1/members/ada-lovelace/block', '/api/v1/members/:id/block'],
      [`/api/v1/me/exports/${MEMBER}/download`, '/api/v1/me/exports/:id/download'],
      [`/api/v1/assets/${MEMBER}/transfers`, '/api/v1/assets/:id/transfers'],
      ['/scan/zq-scan-77', '/scan/:id'],
      ['/healthz', '/healthz'],
    ];
    for (const [url, expected] of cases) {
      logged = [];
      await request(app()).post(url);
      expect(logged.map((l) => l.path), url).toEqual([expected, expected]);
      expect(JSON.stringify(logged)).not.toMatch(new RegExp(`${MEMBER}|ada-lovelace|zq-scan|token`));
    }
  });

  it('the completion log keeps the full templated path when a sub-router answered', async () => {
    await request(app()).post(`/api/v1/members/${MEMBER}/block`).expect(204);
    const done = logged.find((l) => l.statusCode === 204);
    expect(done?.path).toBe('/api/v1/members/:id/block');
  });

  it('normalizes the region header instead of logging free text', async () => {
    expect((await request(app()).get('/x').set('X-Region', 'eu-west1')).body.region).toBe('eu-west1');
    logged = [];
    const r = await request(app()).get('/x').set('X-Region', "us-east1'; DROP TABLE x");
    expect(r.body.region).toBe('us-east1');
    expect(JSON.stringify(logged)).not.toContain('DROP');
    expect(logged.every((l) => !('userAgent' in l))).toBe(true);
  });

  it('the gateway logs, returns and problem-reports one request id', async () => {
    const gw = createApp(loadConfig({ BRANDME_MODE: 'development', BRAIN_SERVICE_URL: 'http://127.0.0.1:9' }), {} as IdentityStore);
    const r = await request(gw).get(`/api/v1/members/${MEMBER}`).set('X-Request-Id', 'not-a-uuid');
    expect(r.status).toBe(404);
    expect(r.headers['x-request-id']).toMatch(UUID);
    expect(r.body.request_id).toBe(r.headers['x-request-id']);
    expect(logged.map((l) => l.requestId)).toEqual([r.body.request_id, r.body.request_id]);
    expect(logged.map((l) => l.path)).toEqual(['/api/v1/members/:id', '/api/v1/members/:id']);
  });
});

describe('templatePath', () => {
  it('keeps only known static words', () => {
    expect(templatePath('/')).toBe('/');
    expect(templatePath('/API/V1/Me')).toBe('/api/v1/me');
    expect(templatePath('/api/v1/me/consents/c-1')).toBe('/api/v1/me/consents/:id');
    expect(templatePath('/api/v1/commerce/orders/o-9/returns')).toBe('/api/v1/commerce/orders/:id/returns');
    expect(templatePath('/api/v1/someone@example.com')).toBe('/api/v1/:id');
    expect(templatePath(undefined)).toBe('/');
  });

  it('bounds the segment count and length', () => {
    const deep = `/${Array.from({ length: 40 }, () => 'me').join('/')}`;
    const out = templatePath(deep);
    expect(out.split('/').length).toBeLessThanOrEqual(14);
    expect(out.endsWith('…')).toBe(true);
    expect(templatePath(`/${'a'.repeat(5000)}`)).toBe('/:id');
  });
});
