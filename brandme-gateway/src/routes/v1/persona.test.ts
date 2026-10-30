/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Unmounted persona router: mounted here in a throwaway app with a fake
 * DomainClient and a test-only principal. Checks the gateway-side contract:
 * auth/scope, If-Match (428), Idempotency-Key, identity-field rejection,
 * opaque-ID path params and faithful relay of domain status/ETag/problem bodies.
 */

import express, { type NextFunction, type Request, type Response } from 'express';
import request from 'supertest';
import { beforeEach, describe, expect, it } from 'vitest';
import { problemHandler, requestContext } from '../../middleware/problem';
import type { Principal } from '../../types';
import { personaRouter, type DomainClient, type DomainRequest, type DomainResponse } from './persona';

const MEMBER = '2ad9041e-561e-527b-aa0d-5a7fda5f710b';
const EVIDENCE = '0b6f1a3e-7f1d-4c55-9a0e-2f6b8c1d9e10';

function principal(scopes: string[]): Principal {
  return {
    memberId: MEMBER,
    subject: 'dev|alex',
    sessionId: 's1',
    clientId: null,
    scopes,
    assuranceLevel: 'simulated',
    environment: 'development',
    delegationId: null,
    identityProvider: 'dev',
    expiresAt: new Date(Date.now() + 3_600_000),
    via: 'session',
  };
}

class FakeClient implements DomainClient {
  calls: DomainRequest[] = [];
  next: DomainResponse = { status: 200, body: { ok: true }, headers: { etag: '"7"' } };
  async request(req: DomainRequest): Promise<DomainResponse> {
    this.calls.push(req);
    return this.next;
  }
}

function app(client: DomainClient, scopes: string[] | null) {
  const a = express();
  a.use(requestContext('development'));
  a.use(express.json({ limit: '256kb' }));
  a.use((_req: Request, res: Response, next: NextFunction) => {
    if (scopes) res.locals.principal = principal(scopes); // TEST-ONLY stand-in for principalMiddleware
    next();
  });
  a.use(personaRouter(client));
  a.use(problemHandler);
  return a;
}

const ALL = ['profile:read', 'profile:write'];
const KEY = 'key-0123456789abcdef';

describe('persona router (unmounted)', () => {
  let client: FakeClient;
  beforeEach(() => {
    client = new FakeClient();
  });

  it('requires a principal and the right scope', async () => {
    const anon = await request(app(client, null)).get('/me/persona');
    expect(anon.status).toBe(401);
    expect(anon.headers['content-type']).toMatch(/application\/problem\+json/);
    const ro = await request(app(client, ['profile:read'])).patch('/me/persona').set('If-Match', '"0"').send({ changes: [], client_revision: 'x' });
    expect(ro.status).toBe(403);
    expect(client.calls).toHaveLength(0);
  });

  it('forwards GET with the verified principal and relays ETag', async () => {
    const res = await request(app(client, ALL)).get('/me/persona');
    expect(res.status).toBe(200);
    expect(res.headers.etag).toBe('"7"');
    expect(client.calls[0]).toMatchObject({ method: 'GET', path: '/me/persona' });
    expect(client.calls[0].principal.memberId).toBe(MEMBER);
    expect(client.calls[0].requestId).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('PATCH needs If-Match (428) and never takes identity from the body', async () => {
    const a = app(client, ALL);
    const missing = await request(a).patch('/me/persona').send({ changes: [], client_revision: 'x' });
    expect(missing.status).toBe(428);
    expect(missing.body.code).toBe('if_match_required');
    const spoof = await request(a).patch('/me/persona').set('If-Match', '"3"').send({ changes: [], client_revision: 'x', member_id: 'someone-else' });
    expect(spoof.status).toBe(422);
    const tooMany = await request(a).patch('/me/persona').set('If-Match', '"3"').send({ changes: new Array(13).fill({}), client_revision: 'x' });
    expect(tooMany.status).toBe(422);
    expect(client.calls).toHaveLength(0);
    const ok = await request(a).patch('/me/persona').set('If-Match', '"3"').send({ changes: [], client_revision: 'x' });
    expect(ok.status).toBe(200);
    expect(client.calls[0]).toMatchObject({ method: 'PATCH', ifMatch: '"3"', body: { changes: [], client_revision: 'x' } });
  });

  it('idempotent operations require a 16-128 char Idempotency-Key', async () => {
    const a = app(client, ALL);
    const none = await request(a).post(`/me/persona/evidence/${EVIDENCE}/suppress`);
    expect(none.status).toBe(400);
    expect(none.body.code).toBe('idempotency_key_invalid');
    const ok = await request(a).post(`/me/persona/evidence/${EVIDENCE}/suppress`).set('Idempotency-Key', KEY);
    expect(ok.status).toBe(200);
    expect(client.calls[0]).toMatchObject({ path: `/me/persona/evidence/${EVIDENCE}/suppress`, idempotencyKey: KEY });
    const snap = await request(a).post('/me/persona/snapshots').set('Idempotency-Key', KEY).send({ name: 'Mine' });
    expect(snap.status).toBe(200);
    const reset = await request(a).post('/me/persona/reset').set('If-Match', '"2"').set('Idempotency-Key', KEY).send({ scope: 'inference' });
    expect(reset.status).toBe(422); // confirm must be true
  });

  it('non-UUID ids are not found and never forwarded', async () => {
    const res = await request(app(client, ALL)).post('/me/persona/evidence/../../admin/suppress').set('Idempotency-Key', KEY);
    expect(res.status).toBe(404);
    const res2 = await request(app(client, ALL)).post('/recommendations/not-a-uuid/feedback').set('Idempotency-Key', KEY).send({});
    expect(res2.status).toBe(404);
    expect(client.calls).toHaveLength(0);
  });

  it('relays domain problem+json bodies unchanged', async () => {
    client.next = {
      status: 409,
      body: { type: 'https://brand.me/problems/revision_conflict', title: 'Conflict', status: 409, code: 'revision_conflict', detail: 'x', instance: '/me/persona', request_id: EVIDENCE, retryable: false, current_version: '4', mergeable: true, conflicting_axes: [] },
    };
    const res = await request(app(client, ALL)).patch('/me/persona').set('If-Match', '"3"').send({ changes: [], client_revision: 'x' });
    expect(res.status).toBe(409);
    expect(res.headers['content-type']).toMatch(/application\/problem\+json/);
    expect(res.body.mergeable).toBe(true);
    expect(res.body.current_version).toBe('4');
  });

  it('only allowlisted query parameters reach the domain', async () => {
    await request(app(client, ALL)).get('/recommendations?occasion=work&limit=4&member_id=x&debug=1');
    expect(client.calls[0].query).toEqual({ occasion: 'work', limit: '4' });
  });
});
