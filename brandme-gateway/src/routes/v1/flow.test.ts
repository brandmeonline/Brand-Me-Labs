/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Flow and houses router in a throwaway app (fake DomainClient, test-only
 * principal). Gateway-side contract only; Flow itself is tested against Spanner in Python.
 */

import express, { type NextFunction, type Request, type Response } from 'express';
import request from 'supertest';
import { beforeEach, describe, expect, it } from 'vitest';
import { problemHandler, requestContext } from '../../middleware/problem';
import type { Principal } from '../../types';
import type { DomainClient, DomainRequest, DomainResponse } from './persona';
import { flowRouter } from './flow';
import { rewardsRouter } from './rewards';

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
  a.use(flowRouter(client));
  a.use(rewardsRouter(client));
  a.use(problemHandler);
  return a;
}

describe('flow and houses router', () => {
  let client: FakeClient;
  beforeEach(() => {
    client = new FakeClient();
  });

  it('Flow needs a principal and social:read, and forwards only cursor and limit', async () => {
    expect((await request(app(client, null)).get('/flow')).status).toBe(401);
    expect((await request(app(client, principal(['rewards:read']))).get('/flow')).status).toBe(403);
    const a = request(app(client, principal(['social:read'])));
    expect((await a.get('/flow?limit=12&cursor=abc&rank=hot&member_id=x')).status).toBe(200);
    expect(client.calls[0]).toMatchObject({ method: 'GET', path: '/flow', query: { limit: '12', cursor: 'abc' } });
    expect(client.calls[0]!.query).not.toHaveProperty('rank');
    expect((await a.get('/houses')).status).toBe(200);
    expect(client.calls[1]).toMatchObject({ method: 'GET', path: '/houses' });
  });

  it('following and sharing standing are the member’s own choice, with a strict body', async () => {
    const a = request(app(client, principal(['social:read', 'social:write'])));
    expect((await a.put('/houses/atelier-north/follow').send({ share_standing: true })).status).toBe(200);
    expect(client.calls[0]).toMatchObject({ method: 'PUT', path: '/houses/atelier-north/follow', body: { share_standing: true } });
    expect((await a.put('/houses/atelier-north/follow').send({})).status).toBe(200);
    expect(client.calls[1]!.body).toEqual({});
    for (const body of [{ share_standing: 'yes' }, { share_standing: true, tier: 'top_1' }, { member_id: 'x' }]) {
      expect((await a.put('/houses/atelier-north/follow').send(body)).status).toBe(422);
    }
    for (const ref of ['Atelier-North', '-north', 'north-', 'a'.repeat(121), 'a_b']) {
      expect((await a.put(`/houses/${ref}/follow`).send({})).status).toBe(404);
    }
    expect((await a.delete('/houses/atelier-north/follow')).status).toBe(200);
    expect(client.calls.at(-1)).toMatchObject({ method: 'DELETE', path: '/houses/atelier-north/follow' });
    const agent = request(app(client, principal(['social:read', 'social:write'], { delegationId: '7d1b0f6e-1d2c-4c3b-9a8e-0f1e2d3c4b5a' })));
    const before = client.calls.length;
    expect((await agent.put('/houses/atelier-north/follow').send({ share_standing: true })).status).toBe(403);
    expect((await agent.delete('/houses/atelier-north/follow')).status).toBe(403);
    expect(client.calls.length).toBe(before);
    expect((await request(app(client, principal(['social:read']))).put('/houses/atelier-north/follow').send({})).status).toBe(403);
  });

  it('a member reads their own standings with rewards:read', async () => {
    expect((await request(app(client, principal(['social:read']))).get('/rewards/standings')).status).toBe(403);
    expect((await request(app(client, principal(['rewards:read']))).get('/rewards/standings')).status).toBe(200);
    expect(client.calls[0]).toMatchObject({ method: 'GET', path: '/rewards/standings' });
  });
});
