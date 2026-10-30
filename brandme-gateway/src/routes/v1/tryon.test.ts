/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Unmounted media + try-on routers in a throwaway app (fake DomainClient,
 * test-only principal). Gateway-side contract only; consent/retention/deletion
 * are tested against Spanner in Python.
 */

import express, { type NextFunction, type Request, type Response } from 'express';
import request from 'supertest';
import { beforeEach, describe, expect, it } from 'vitest';
import { problemHandler, requestContext } from '../../middleware/problem';
import type { Principal } from '../../types';
import { mediaRouter } from './media';
import type { DomainClient, DomainRequest, DomainResponse } from './persona';
import { tryOnJobShape, tryOnRouter } from './tryon';

const ID = '0b6f1a3e-7f1d-4c55-9a0e-2f6b8c1d9e10';
const KEY = 'key-0123456789abcdef';
const CONSENT = { accepted: true, provider_id: 'p', terms_version: 't' };

class FakeClient implements DomainClient {
  calls: DomainRequest[] = [];
  next: DomainResponse = { status: 200, body: { ok: true } };
  async request(req: DomainRequest): Promise<DomainResponse> {
    this.calls.push(req);
    return this.next;
  }
}

function principal(scopes: string[]): Principal {
  return {
    memberId: '2ad9041e-561e-527b-aa0d-5a7fda5f710b', subject: 'dev|alex', sessionId: 's', clientId: null, scopes,
    assuranceLevel: 'simulated', environment: 'development', delegationId: null, identityProvider: 'dev',
    expiresAt: new Date(Date.now() + 60_000), via: 'session',
  };
}

function app(client: DomainClient, scopes: string[] | null) {
  const a = express();
  a.use(requestContext('development'));
  a.use(express.json());
  a.use((_req: Request, res: Response, next: NextFunction) => {
    if (scopes) res.locals.principal = principal(scopes); // TEST-ONLY
    next();
  });
  a.use(mediaRouter(client));
  a.use(tryOnRouter(client));
  a.use(problemHandler);
  return a;
}

const ALL = ['wardrobe:read', 'wardrobe:write'];
const job = { mode: 'photo_preview', input_media_id: ID, item_id: ID, consent: CONSENT };

describe('media/try-on routers (unmounted)', () => {
  let client: FakeClient;
  beforeEach(() => {
    client = new FakeClient();
  });

  it('try-on job: consent required, unavailable modes never forwarded', async () => {
    expect(() => tryOnJobShape(job)).not.toThrow();
    const a = app(client, ALL);
    const post = (b: object) => request(a).post('/try-on/jobs').set('Idempotency-Key', KEY).send(b);
    expect((await post({ ...job, consent: undefined })).body.code).toBe('consent_required');
    expect((await post({ ...job, consent: { ...CONSENT, accepted: 'true' } })).status).toBe(422);
    expect((await post({ ...job, mode: 'calibrated_fit' })).body.code).toBe('capability_unavailable');
    expect((await post({ ...job, mode: 'live_overlay' })).body.code).toBe('on_device_only');
    expect((await post({ ...job, product_id: ID })).status).toBe(422);
    expect((await post({ ...job, frames: ['...'] })).status).toBe(422);
    expect(client.calls).toHaveLength(0);
    expect((await request(a).post('/try-on/jobs').send(job)).status).toBe(400);
    expect((await post(job)).status).toBe(200);
    expect(client.calls[0]).toMatchObject({ method: 'POST', path: '/try-on/jobs', idempotencyKey: KEY });
  });

  it('uploads are bounded and need write scope', async () => {
    expect((await request(app(client, null)).post('/media/uploads')).status).toBe(401);
    expect((await request(app(client, ['wardrobe:read'])).post('/media/uploads').set('Idempotency-Key', KEY)
      .send({ kind: 'tryon_input', content_type: 'image/png', bytes: 10 })).status).toBe(403);
    const a = app(client, ALL);
    const post = (b: object) => request(a).post('/media/uploads').set('Idempotency-Key', KEY).send(b);
    expect((await post({ kind: 'tryon_input', content_type: 'image/gif', bytes: 10 })).status).toBe(422);
    expect((await post({ kind: 'tryon_input', content_type: 'image/png', bytes: 11 * 1024 * 1024 })).status).toBe(422);
    expect((await post({ kind: 'avatar', content_type: 'image/png', bytes: 10 })).status).toBe(422);
    expect((await post({ kind: 'tryon_input', content_type: 'image/png', bytes: 10 })).status).toBe(200);
    expect((await request(a).post(`/media/uploads/${ID}/complete`)).status).toBe(200);
    expect((await request(a).get('/media/jobs/not-an-id')).status).toBe(404);
  });

  it('result bytes are relayed privately; problems keep their media type', async () => {
    const a = app(client, ALL);
    client.next = { status: 200, body: Buffer.from([0x89, 0x50, 0x4e, 0x47]), headers: { 'content-type': 'image/png' } };
    const ok = await request(a).get(`/try-on/jobs/${ID}/result`);
    expect(ok.status).toBe(200);
    expect(ok.headers['content-type']).toMatch(/^image\/png/);
    expect(ok.headers['cache-control']).toBe('private, no-store');
    client.next = { status: 404, body: { code: 'not_found' } };
    const missing = await request(a).get(`/try-on/jobs/${ID}/result`);
    expect(missing.status).toBe(404);
    expect(missing.headers['content-type']).toMatch(/problem\+json/);
    client.next = { status: 200, body: Buffer.from('<svg/>'), headers: { 'content-type': 'image/svg+xml' } };
    expect((await request(a).get(`/try-on/jobs/${ID}/result`)).headers['content-type']).not.toMatch(/svg/);
  });

  it('delete and consent routes forward with ids validated', async () => {
    const a = app(client, ALL);
    expect((await request(a).delete(`/try-on/jobs/${ID}`)).status).toBe(200);
    expect((await request(a).delete('/try-on/consents/x')).status).toBe(404);
    expect((await request(a).delete(`/try-on/consents/${ID}`)).status).toBe(200);
    expect(client.calls.map((c) => c.method)).toEqual(['DELETE', 'DELETE']);
  });
});
