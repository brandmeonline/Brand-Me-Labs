/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Unmounted social + decisions routers in a throwaway app (fake DomainClient,
 * test-only principal). Gateway-side contract only; deadlines, audiences,
 * blocks and share disclosure are tested against Spanner in Python.
 */

import express, { type NextFunction, type Request, type Response } from 'express';
import request from 'supertest';
import { beforeEach, describe, expect, it } from 'vitest';
import { problemHandler, requestContext } from '../../middleware/problem';
import type { Principal } from '../../types';
import { decisionShape, decisionsRouter } from './decisions';
import type { DomainClient, DomainRequest, DomainResponse } from './persona';
import { moderationOpsRouter, reportShape, shareShape, socialRouter } from './social';

const ID = '0b6f1a3e-7f1d-4c55-9a0e-2f6b8c1d9e10';
const OTHER = '6d1c2b3a-4e5f-4a7b-8c9d-0e1f2a3b4c5d';
const KEY = 'key-0123456789abcdef';
const TOKEN = 'AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcde';

class FakeClient implements DomainClient {
  calls: DomainRequest[] = [];
  async request(req: DomainRequest): Promise<DomainResponse> {
    this.calls.push(req);
    return { status: 200, body: { ok: true } };
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
  a.use(socialRouter(client));
  a.use(decisionsRouter(client));
  a.use(moderationOpsRouter(client));
  a.use(problemHandler);
  return a;
}

const ALL = ['social:read', 'social:write'];
const decision = {
  subject_type: 'wardrobe_item', subject_id: ID, prompt: 'Wear this tonight?', recipient_ids: [OTHER],
  duration_seconds: 300, discussion_mode: 'blind_until_response',
};
const share = { subject_type: 'outfit_version', subject_id: ID, audience: 'unlisted', allowed_fields: ['title'], recipient_ids: [], expires_at: '2026-11-01T00:00:00Z' };

describe('social/decisions routers (unmounted)', () => {
  let client: FakeClient;
  beforeEach(() => {
    client = new FakeClient();
  });

  it('requires a principal and the right scope', async () => {
    expect((await request(app(client, null)).get('/relationships')).status).toBe(401);
    expect((await request(app(client, null)).get('/decisions')).status).toBe(401);
    expect((await request(app(client, ['social:read'])).post('/blocks').send({ target_member_id: OTHER })).status).toBe(403);
    expect(client.calls).toHaveLength(0);
  });

  it('targets come from target_member_id; identity fields are refused', async () => {
    const a = app(client, ALL);
    expect((await request(a).post('/relationships').send({ member_id: OTHER })).status).toBe(422);
    expect((await request(a).post('/relationships').send({ target_member_id: 'nope' })).status).toBe(422);
    const ok = await request(a).post('/relationships').send({ target_member_id: OTHER.toUpperCase() });
    expect(ok.status).toBe(200);
    expect(client.calls[0]).toMatchObject({ method: 'POST', path: '/relationships', body: { target_member_id: OTHER } });
    expect(client.calls[0].principal?.memberId).toBe('2ad9041e-561e-527b-aa0d-5a7fda5f710b');
    expect((await request(a).post('/relationships/not-a-uuid/accept')).status).toBe(404);
  });

  it('decision create: exactly 300 s, 1-12 unique recipients, Idempotency-Key', async () => {
    expect(() => decisionShape(decision)).not.toThrow();
    for (const bad of [
      { ...decision, duration_seconds: 299 },
      { ...decision, duration_seconds: '300' },
      { ...decision, recipient_ids: [] },
      { ...decision, recipient_ids: [OTHER, OTHER.toUpperCase()] },
      { ...decision, recipient_ids: Array.from({ length: 13 }, () => OTHER) },
      { ...decision, discussion_mode: 'public' },
      { ...decision, prompt: '' },
    ]) {
      expect(() => decisionShape(bad)).toThrow();
    }
    const a = app(client, ALL);
    expect((await request(a).post('/decisions').send(decision)).status).toBe(400);
    expect((await request(a).post('/decisions').set('Idempotency-Key', KEY).send({ ...decision, closes_at: '2099-01-01T00:00:00Z' })).status).toBe(422);
    const ok = await request(a).post('/decisions').set('Idempotency-Key', KEY).send(decision);
    expect(ok.status).toBe(200);
    expect(client.calls).toHaveLength(1);
    expect(client.calls[0]).toMatchObject({ method: 'POST', path: '/decisions', idempotencyKey: KEY });
  });

  it('responses: valid choices only, alternative needs a reference; no client time is forwarded', async () => {
    const a = app(client, ALL);
    expect((await request(a).post(`/decisions/${ID}/responses`).send({ choice: 'maybe' })).status).toBe(422);
    expect((await request(a).post(`/decisions/${ID}/responses`).send({ choice: 'alternative' })).status).toBe(422);
    expect((await request(a).post(`/decisions/${ID}/responses`).send({ choice: 'yes', submitted_at: '2026-01-01T00:00:00Z' })).status).toBe(422);
    const ok = await request(a).post(`/decisions/${ID}/responses`).send({ choice: 'alternative', alternative_ref: OTHER, note: 'Try mine' });
    expect(ok.status).toBe(200);
    expect(client.calls[0].body).toEqual({ choice: 'alternative', alternative_ref: OTHER, note: 'Try mine' });
    for (const action of ['open', 'close', 'cancel']) {
      expect((await request(a).post(`/decisions/${ID}/${action}`)).status).toBe(200);
    }
    expect((await request(a).put(`/decisions/${ID}/outcome`).send({ outcome: 'won' })).status).toBe(422);
    expect((await request(a).get('/decisions?role=everyone')).status).toBe(422);
  });

  it('share create shape and Idempotency-Key', async () => {
    expect(() => shareShape(share)).not.toThrow();
    expect(() => shareShape({ ...share, audience: 'selected_members' })).toThrow();
    expect(() => shareShape({ ...share, allowed_fields: [] })).toThrow();
    expect(() => shareShape({ ...share, subject_type: 'closet' })).toThrow();
    const a = app(client, ALL);
    expect((await request(a).post('/shares').send(share)).status).toBe(400);
    expect((await request(a).post('/shares').set('Idempotency-Key', KEY).send({ ...share, owner_id: ID })).status).toBe(422);
    expect((await request(a).post('/shares').set('Idempotency-Key', KEY).send(share)).status).toBe(200);
    expect((await request(a).delete(`/shares/${ID}`)).status).toBe(200);
    expect(client.calls.map((c) => c.method)).toEqual(['POST', 'DELETE']);
  });

  it('share-link resolve works anonymously, token in body, malformed tokens are 404', async () => {
    const anon = app(client, null);
    expect((await request(anon).post('/shares/resolve').send({ token: 'short' })).status).toBe(404);
    expect((await request(anon).post('/shares/resolve').send({ token: TOKEN, extra: 1 })).status).toBe(422);
    const ok = await request(anon).post('/shares/resolve').send({ token: TOKEN });
    expect(ok.status).toBe(200);
    expect(client.calls[0]).toMatchObject({ method: 'POST', path: '/shares/resolve', body: { token: TOKEN }, principal: null });
    // A signed-in viewer is forwarded (blocks and selected audiences apply), but needs social:read.
    expect((await request(app(client, ['profile:read'])).post('/shares/resolve').send({ token: TOKEN })).status).toBe(403);
    await request(app(client, ALL)).post('/shares/resolve').send({ token: TOKEN });
    expect(client.calls[1].principal?.memberId).toBe('2ad9041e-561e-527b-aa0d-5a7fda5f710b');
    // Every other share route still needs a principal.
    expect((await request(anon).get(`/shares/${ID}`)).status).toBe(401);
  });

  it('notifications: bounded id list', async () => {
    const a = app(client, ALL);
    expect((await request(a).post('/notifications/read').send({ ids: [] })).status).toBe(422);
    expect((await request(a).post('/notifications/read').send({ ids: ['x'] })).status).toBe(422);
    expect((await request(a).post('/notifications/read').send({ ids: [ID] })).status).toBe(200);
    expect((await request(a).get('/notifications?limit=5&evil=1')).status).toBe(200);
    expect(client.calls[1].query).toEqual({ limit: '5' });
  });

  it('reports: typed targets, no identity fields; moderation is operator-only', async () => {
    const report = { target_type: 'decision_response', target: { decision_id: ID, respondent_id: OTHER }, reason: 'harassment' };
    expect(() => reportShape(report)).not.toThrow();
    expect(() => reportShape({ ...report, target: { decision_id: ID } })).toThrow();
    expect(() => reportShape({ ...report, target: { ...report.target, extra: ID } })).toThrow();
    expect(() => reportShape({ ...report, reason: 'dislike' })).toThrow();
    const a = app(client, ALL);
    expect((await request(a).post('/reports').send({ ...report, reporter_id: ID })).status).toBe(422);
    expect((await request(a).post('/reports').send(report)).status).toBe(200);
    expect((await request(a).get('/ops/moderation/reports')).status).toBe(403);
    const ops = app(client, ['moderation:admin']);
    expect((await request(ops).get('/ops/moderation/reports?state=open&extra=1')).status).toBe(200);
    expect(client.calls[1].query).toEqual({ state: 'open' });
    expect((await request(ops).post(`/ops/moderation/reports/${ID}/resolve`).send({ decision: 'ban', note: 'x' })).status).toBe(422);
    expect((await request(ops).post(`/ops/moderation/reports/${ID}/resolve`).send({ decision: 'dismiss', note: 'Not a violation' })).status).toBe(200);
  });
});
