/**
 * Rate limiting behaviour (ch.03 §6/§9): problem+json 429 with Retry-After and
 * request_id, probe exemption, essential read/export access, bounded store,
 * member vs address keying, trust-proxy handling, limits from config.
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
import type { IdentityStore } from './identity/store';
import { requestContext } from './problem';
import { TokenBucketStore, clientAddressKey, createRateLimiter, ipRateLimiter, principalRateLimiter, type RateLimiter } from './rateLimiter';

const REPO = resolve(__dirname, '../../..');
const spec = JSON.parse(readFileSync(resolve(REPO, 'docs/design/brandme/contracts/domain.schema.json'), 'utf8'));
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
const isSpecProblem = ajv.compile(spec.$defs.Problem);
const PROBLEM_MEMBERS = ['code', 'detail', 'instance', 'request_id', 'retryable', 'status', 'title', 'type'];

const frozen = (t = 1_000_000) => {
  const clock = { now: t };
  return { clock, now: () => clock.now };
};

/** Minimal app: X-Test-Member stands in for a resolved principal. */
function limitedApp(limiter: RateLimiter, trustProxy: false | number = false) {
  const app = express();
  app.set('trust proxy', trustProxy);
  app.use(requestContext('development'));
  app.use((req, res, next) => {
    const member = req.header('x-test-member');
    if (member) res.locals.principal = { memberId: member };
    next();
  });
  app.use(limiter);
  app.all('*', (_req, res) => { res.json({ ok: true }); });
  return app;
}

const limits = { rateLimitWindow: 60_000, rateLimitMaxRequests: 1, rateLimitIpMaxRequests: 1, rateLimitMaxKeys: 100 };

describe('TokenBucketStore', () => {
  it('allows the capacity, then refuses until the next token has refilled', () => {
    const { clock, now } = frozen();
    const store = new TokenBucketStore(3, 3000, 10, now);
    expect([store.take('k'), store.take('k'), store.take('k')].map((r) => [r.allowed, r.remaining])).toEqual([[true, 2], [true, 1], [true, 0]]);
    const refused = store.take('k');
    expect(refused).toMatchObject({ allowed: false, remaining: 0, retryAfterMs: 1000, resetMs: 3000 });
    clock.now += 999;
    expect(store.take('k').allowed).toBe(false);
    clock.now += 1;
    expect(store.take('k').allowed).toBe(true);
  });

  it('refills over the window but never above capacity', () => {
    const { clock, now } = frozen();
    const store = new TokenBucketStore(2, 1000, 10, now);
    store.take('k');
    store.take('k');
    clock.now += 10_000;
    expect(store.take('k').remaining).toBe(1);
  });

  it('bounds tracked keys and evicts the least recently used bucket first', () => {
    const { now } = frozen();
    const store = new TokenBucketStore(1, 60_000, 3, now);
    store.take('a');
    store.take('b');
    store.take('c');
    store.take('a'); // touch a: b is now least recently used
    store.take('d');
    expect(store.size).toBe(3);
    expect(store.has('b')).toBe(false);
    expect(store.has('a') && store.has('c') && store.has('d')).toBe(true);
    expect(store.evictions).toBe(1);
    for (let i = 0; i < 5000; i++) store.take(`flood-${i}`);
    expect(store.size).toBe(3);
    expect(store.evictions).toBe(5001);
  });

  it('refuses a zero capacity, window or key bound', () => {
    expect(() => new TokenBucketStore(0, 1000, 10)).toThrow(RangeError);
    expect(() => new TokenBucketStore(1, 0, 10)).toThrow(RangeError);
    expect(() => new TokenBucketStore(1, 1000, 0)).toThrow(RangeError);
  });
});

describe('clientAddressKey', () => {
  it('keys IPv4 (and IPv4-mapped IPv6) by address and IPv6 by /64', () => {
    expect(clientAddressKey('203.0.113.7')).toBe('ip:203.0.113.7');
    expect(clientAddressKey('::ffff:203.0.113.7')).toBe('ip:203.0.113.7');
    expect(clientAddressKey('2001:db8::1:0:0:1')).toBe('ip6:2001:db8:0:0::/64');
    expect(clientAddressKey('2001:0db8:0000:0000:ffff::')).toBe(clientAddressKey('2001:db8::1:0:0:1'));
    expect(clientAddressKey('2001:db8:0:1::1')).not.toBe(clientAddressKey('2001:db8::1'));
    expect(clientAddressKey('::1')).toBe('ip6:0:0:0:0::/64');
    expect(clientAddressKey(undefined)).toBe('ip:unknown');
  });
});

describe('throttled responses', () => {
  it('429 is a spec Problem with Retry-After and the request id', async () => {
    const { now } = frozen();
    const app = limitedApp(createRateLimiter({ scope: 't', maxRequests: 2, windowMs: 60_000, maxKeys: 10, keyBy: 'ip', now }));
    expect((await request(app).get('/x')).status).toBe(200);
    const second = await request(app).get('/x');
    expect(second.headers['x-ratelimit-limit']).toBe('2');
    expect(second.headers['x-ratelimit-remaining']).toBe('0');
    const id = 'a3bb189e-8bf9-4888-9912-ace4e6543002';
    const r = await request(app).get('/x?member=secret').set('X-Request-Id', id);
    expect(r.status).toBe(429);
    expect(r.headers['content-type']).toMatch(/^application\/problem\+json/);
    expect(r.headers['retry-after']).toBe('30'); // 2 per 60 s: one token every 30 s
    expect(isSpecProblem(r.body), JSON.stringify(isSpecProblem.errors)).toBe(true);
    expect(Object.keys(r.body).sort()).toEqual(PROBLEM_MEMBERS);
    expect(r.body).toMatchObject({ status: 429, code: 'rate_limited', retryable: true, request_id: id, instance: '/x' });
    expect(r.headers['x-request-id']).toBe(id);
  });

  it('keys by member when a principal is known and by address otherwise', async () => {
    const app = limitedApp(createRateLimiter({ scope: 't', maxRequests: 1, windowMs: 60_000, maxKeys: 10, keyBy: 'principal' }));
    expect((await request(app).post('/x').set('X-Test-Member', 'm-a')).status).toBe(200);
    expect((await request(app).post('/x').set('X-Test-Member', 'm-a')).status).toBe(429);
    // Same address, different member: own budget.
    expect((await request(app).post('/x').set('X-Test-Member', 'm-b')).status).toBe(200);
    // Anonymous callers share the address bucket, separate from members.
    expect((await request(app).post('/x')).status).toBe(200);
    expect((await request(app).post('/x')).status).toBe(429);
    expect((await request(app).post('/x').set('X-Test-Member', 'm-c')).status).toBe(200);
  });

  it('an address limiter ignores members: one address, one bucket', async () => {
    const app = limitedApp(ipRateLimiter(limits));
    expect((await request(app).get('/x').set('X-Test-Member', 'm-a')).status).toBe(200);
    expect((await request(app).get('/x').set('X-Test-Member', 'm-b')).status).toBe(429);
  });

  it('honours X-Forwarded-For only for the configured proxy hops', async () => {
    // GKE Ingress shape: "<client>, <load-balancer-ip>", connection from the front end.
    const viaLb = (client: string, spoofed?: string) => [spoofed, client, '34.120.0.1'].filter(Boolean).join(', ');
    const behindLb = limitedApp(ipRateLimiter(limits), 2);
    expect((await request(behindLb).get('/x').set('X-Forwarded-For', viaLb('203.0.113.7'))).status).toBe(200);
    // A client-chosen leftmost entry does not buy a new bucket.
    expect((await request(behindLb).get('/x').set('X-Forwarded-For', viaLb('203.0.113.7', '198.51.100.99'))).status).toBe(429);
    expect((await request(behindLb).get('/x').set('X-Forwarded-For', viaLb('203.0.113.8'))).status).toBe(200);

    // Default (off): the header is ignored and the socket address is the key.
    const direct = limitedApp(ipRateLimiter(limits));
    expect((await request(direct).get('/x').set('X-Forwarded-For', '203.0.113.7')).status).toBe(200);
    expect((await request(direct).get('/x').set('X-Forwarded-For', '203.0.113.8')).status).toBe(429);
  });

  it('keeps read-only and data-export access open once the member budget is spent', async () => {
    const app = limitedApp(principalRateLimiter(limits));
    const as = (r: request.Test) => r.set('X-Test-Member', 'm-a');
    expect((await as(request(app).post('/api/v1/wardrobe/items'))).status).toBe(200);
    expect((await as(request(app).post('/api/v1/wardrobe/items'))).status).toBe(429);
    for (let i = 0; i < 3; i++) expect((await as(request(app).get('/api/v1/wardrobe/items'))).status).toBe(200);
    expect((await as(request(app).post('/api/v1/me/exports'))).status).toBe(200);
    expect((await as(request(app).get('/api/v1/me/exports/0b9c7a52-6a4e-4f8e-9f53-3d8f1f0f2a11/download'))).status).toBe(200);
    expect((await as(request(app).head('/api/v1/me/data'))).status).toBe(200);
    // Deletion and other mutations stay budgeted.
    expect((await as(request(app).post('/api/v1/me/deletion'))).status).toBe(429);
    expect((await as(request(app).patch('/api/v1/me'))).status).toBe(429);
  });
});

describe('gateway wiring (createApp)', () => {
  const store = {} as IdentityStore; // never touched: no route below reaches persistence
  const app = (env: Record<string, string>) => createApp(loadConfig({ BRANDME_MODE: 'development', BRAIN_SERVICE_URL: 'http://127.0.0.1:9', ...env }), store);

  it('limits come from config; probes are never throttled; 429s carry request id and environment', async () => {
    const a = app({ RATE_LIMIT_IP_MAX_REQUESTS: '3', RATE_LIMIT_MAX_REQUESTS: '1' });
    // Member budget (address-keyed while signed out): one mutation.
    expect((await request(a).patch('/api/v1/me')).status).toBe(401);
    const budget = await request(a).patch('/api/v1/me');
    expect(budget.status).toBe(429);
    expect(isSpecProblem(budget.body)).toBe(true);
    expect(budget.headers['x-brandme-environment']).toBe('development');
    expect(budget.body.request_id).toBe(budget.headers['x-request-id']);
    // Pre-auth address limit: three requests in total, reads included.
    expect((await request(a).get('/api/v1/me')).status).toBe(401);
    const security = await request(a).get('/api/v1/me');
    expect(security.status).toBe(429);
    expect(Number(security.headers['retry-after'])).toBeGreaterThanOrEqual(1);
    expect((await request(a).post('/scan').send({ garment_tag: 't' })).status).toBe(429);
    // Kubelet probes keep answering.
    for (let i = 0; i < 5; i++) {
      expect((await request(a).get('/healthz')).status).toBe(200);
      expect((await request(a).get('/health')).status).toBe(200);
    }
  });

  it('TRUST_PROXY=2 keys GKE-forwarded clients by their own address', async () => {
    const a = app({ TRUST_PROXY: '2', RATE_LIMIT_IP_MAX_REQUESTS: '1' });
    expect((await request(a).get('/api/v1/me').set('X-Forwarded-For', '203.0.113.7, 34.120.0.1')).status).toBe(401);
    expect((await request(a).get('/api/v1/me').set('X-Forwarded-For', '203.0.113.7, 34.120.0.1')).status).toBe(429);
    expect((await request(a).get('/api/v1/me').set('X-Forwarded-For', '203.0.113.8, 34.120.0.1')).status).toBe(401);
  });
});

describe('rate-limit config', () => {
  const load = (env: Record<string, string>) => loadConfig({ BRANDME_MODE: 'development', ...env });

  it('defaults: trust proxy off, bounded store, spec defaults', () => {
    const cfg = load({});
    expect(cfg).toMatchObject({ trustProxy: false, rateLimitWindow: 900_000, rateLimitMaxRequests: 100, rateLimitIpMaxRequests: 1500, rateLimitMaxKeys: 10_000 });
  });

  it('accepts a hop count or proxy addresses, and refuses trust-everything', () => {
    expect(load({ TRUST_PROXY: '2' }).trustProxy).toBe(2);
    expect(load({ TRUST_PROXY: 'false' }).trustProxy).toBe(false);
    expect(load({ TRUST_PROXY: 'loopback, 10.0.0.0/8, 2001:db8::/32' }).trustProxy).toEqual(['loopback', '10.0.0.0/8', '2001:db8::/32']);
    for (const bad of ['true', 'TRUE', 'proxy.example', '10.0.0.0/33', '11']) expect(() => load({ TRUST_PROXY: bad }), bad).toThrow();
  });

  it('refuses non-positive limits', () => {
    for (const name of ['RATE_LIMIT_WINDOW_MS', 'RATE_LIMIT_MAX_REQUESTS', 'RATE_LIMIT_IP_MAX_REQUESTS', 'RATE_LIMIT_MAX_KEYS']) {
      expect(() => load({ [name]: '0' }), name).toThrow();
    }
  });
});
