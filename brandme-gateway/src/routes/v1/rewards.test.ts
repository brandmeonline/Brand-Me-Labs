/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Unmounted rewards routers in a throwaway app (fake DomainClient, test-only
 * principal). Gateway-side contract only; the ledger is tested against Spanner in Python.
 */

import express, { type NextFunction, type Request, type Response } from 'express';
import request from 'supertest';
import { beforeEach, describe, expect, it } from 'vitest';
import { problemHandler, requestContext } from '../../middleware/problem';
import type { Principal } from '../../types';
import type { DomainClient, DomainRequest, DomainResponse } from './persona';
import { rewardsOpsRouter, rewardsRouter } from './rewards';

const ID = '0b6f1a3e-7f1d-4c55-9a0e-2f6b8c1d9e10';
const KEY = 'key-0123456789abcdef';

class FakeClient implements DomainClient {
  calls: DomainRequest[] = [];
  async request(req: DomainRequest): Promise<DomainResponse> {
    this.calls.push(req);
    return { status: 200, body: { ok: true } };
  }
}

function principal(scopes: string[], over: Partial<Principal> = {}): Principal {
  return {
    memberId: '2ad9041e-561e-527b-aa0d-5a7fda5f710b', subject: 'dev|alex', sessionId: 's', clientId: null, scopes,
    assuranceLevel: 'simulated', environment: 'development', delegationId: null, identityProvider: 'dev',
    expiresAt: new Date(Date.now() + 60_000), via: 'session', ...over,
  };
}

function app(client: DomainClient, p: Principal | null) {
  const a = express();
  a.use(requestContext('development'));
  a.use(express.json());
  a.use((_req: Request, res: Response, next: NextFunction) => {
    if (p) res.locals.principal = p; // TEST-ONLY
    next();
  });
  a.use(rewardsRouter(client));
  a.use(rewardsOpsRouter(client));
  a.use(problemHandler);
  return a;
}

const MEMBER = ['rewards:read', 'rewards:write'];

describe('rewards routers (unmounted)', () => {
  let client: FakeClient;
  beforeEach(() => {
    client = new FakeClient();
  });

  it('reads need rewards:read; there is no award or balance-edit route', async () => {
    expect((await request(app(client, null)).get('/rewards')).status).toBe(401);
    expect((await request(app(client, principal(['profile:read']))).get('/rewards')).status).toBe(403);
    const a = app(client, principal(MEMBER));
    expect((await request(a).get('/rewards')).status).toBe(200);
    for (const [method, path] of [['post', '/rewards'], ['patch', '/rewards'], ['post', '/rewards/entries'], ['put', '/rewards/balance']] as const) {
      expect((await request(a)[method](path).send({ points: 1000 })).status).toBe(404);
    }
    expect(client.calls).toHaveLength(1);
  });

  it('reservation: rewards:write, Idempotency-Key, and no amount in the body', async () => {
    expect((await request(app(client, principal(['rewards:read']))).post(`/benefits/${ID}/reservations`).set('Idempotency-Key', KEY)).status).toBe(403);
    const a = app(client, principal(MEMBER));
    expect((await request(a).post(`/benefits/${ID}/reservations`)).status).toBe(400);
    expect((await request(a).post(`/benefits/${ID}/reservations`).set('Idempotency-Key', KEY).send({ cost_points: 1 })).status).toBe(422);
    expect((await request(a).post('/benefits/nope/reservations').set('Idempotency-Key', KEY)).status).toBe(404);
    const ok = await request(a).post(`/benefits/${ID}/reservations`).set('Idempotency-Key', KEY);
    expect(ok.status).toBe(200);
    expect(client.calls[0]).toMatchObject({ method: 'POST', path: `/benefits/${ID}/reservations`, idempotencyKey: KEY });
    expect(client.calls[0].body).toBeUndefined();
  });

  it('disputes are member-only with a bounded shape', async () => {
    const agent = app(client, principal(MEMBER, { delegationId: 'd-1' }));
    expect((await request(agent).post('/rewards/disputes').send({ category: 'other', message: 'x' })).status).toBe(403);
    const a = app(client, principal(MEMBER));
    expect((await request(a).post('/rewards/disputes').send({ category: 'bribe', message: 'x' })).status).toBe(422);
    expect((await request(a).post('/rewards/disputes').send({ category: 'other', message: 'x', points: 50 })).status).toBe(422);
    expect((await request(a).post('/rewards/disputes').send({ category: 'missing_reward', message: 'Repair missing', entry_id: ID })).status).toBe(200);
  });

  it('ops routes need moderation:admin, no delegation, and aal2 outside development', async () => {
    expect((await request(app(client, principal(MEMBER))).get('/ops/rewards/disputes')).status).toBe(403);
    expect((await request(app(client, principal(['moderation:admin'], { delegationId: 'd' }))).get('/ops/rewards/disputes')).status).toBe(403);
    expect((await request(app(client, principal(['moderation:admin'], { environment: 'production', assuranceLevel: 'aal1' })))
      .get('/ops/rewards/disputes')).status).toBe(403);
    expect((await request(app(client, principal(['moderation:admin'], { environment: 'production', assuranceLevel: 'aal2' })))
      .get('/ops/rewards/disputes?state=open&x=1')).status).toBe(200);
    expect(client.calls[0].query).toEqual({ state: 'open' });
  });

  it('ops bodies are validated before forwarding', async () => {
    const a = app(client, principal(['moderation:admin']));
    const resolve = (b: object) => request(a).post(`/ops/rewards/disputes/${ID}/resolve`).send(b);
    expect((await resolve({ outcome: 'correction', signed_points: 0, note: 'n', evidence_ref: 'e' })).status).toBe(422);
    expect((await resolve({ outcome: 'correction', signed_points: 1.5, note: 'n', evidence_ref: 'e' })).status).toBe(422);
    expect((await resolve({ outcome: 'no_change', note: 'n' })).status).toBe(422);
    expect((await resolve({ outcome: 'correction', signed_points: -20, note: 'Reversal confirmed', evidence_ref: 'case-9' })).status).toBe(200);
    expect((await request(a).post(`/ops/rewards/members/${ID}/entries/${ID}/reverse`).send({ reason: 'r' })).status).toBe(422);
    expect((await request(a).post('/ops/benefits').send({ kind: 'partner', title: 't', description: 'd', cost_points: 1, inventory_total: 1 })).status).toBe(422);
    expect((await request(a).post('/ops/rewards/contributions').send({ member_ref: ID, kind: 'catalog_correction', contribution_ref: ID, evidence_ref: 'photo' }))
      .status).toBe(200);
  });
});
