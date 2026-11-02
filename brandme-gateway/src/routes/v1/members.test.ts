/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Closet visibility and the persona card through the wardrobe and persona
 * routers (fake DomainClient, test-only principal). The domain enforces every
 * rule again on the Spanner emulator in Python.
 */

import express, { type NextFunction, type Request, type Response } from 'express';
import request from 'supertest';
import { beforeEach, describe, expect, it } from 'vitest';
import { problemHandler, requestContext } from '../../middleware/problem';
import type { Principal } from '../../types';
import type { DomainClient, DomainRequest, DomainResponse } from './persona';
import { personaRouter } from './persona';
import { wardrobeRouter } from './wardrobe';

const ITEM = '0b6f1a3e-7f1d-4c55-9a0e-2f6b8c1d9e10';
const OTHER = '6d0b9a8e-2f4c-4b1a-9e3d-7c5a1b2e3f40';

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
  a.use(wardrobeRouter(client));
  a.use(personaRouter(client));
  a.use(problemHandler);
  return a;
}

const ALL = ['wardrobe:read', 'wardrobe:write', 'profile:read', 'profile:write', 'social:read'];

describe('closet visibility and the persona card', () => {
  let client: FakeClient;
  beforeEach(() => {
    client = new FakeClient();
  });

  it('visibility: an offered audience and detail, a short note, and only the member decides', async () => {
    const a = request(app(client, principal(ALL)));
    const put = (b: object, id = ITEM) => a.put(`/wardrobe/items/${id}/visibility`).send(b);
    for (const b of [{}, { visibility: 'everyone' }, { visibility: 'friends', detail: 'all' }, { visibility: 'friends', price: 'show' },
      { visibility: 'members', showcase_note: '' }, { visibility: 'members', showcase_note: 'x'.repeat(281) }]) {
      expect((await put(b)).status).toBe(422);
    }
    expect((await put({ visibility: 'friends' }, 'not-an-id')).status).toBe(404);
    expect((await put({ visibility: 'friends', detail: 'full', showcase_note: 'Worn every summer' })).status).toBe(200);
    expect(client.calls[0]).toMatchObject({ method: 'PUT', path: `/wardrobe/items/${ITEM}/visibility`,
      body: { visibility: 'friends', detail: 'full', showcase_note: 'Worn every summer' } });
    const agent = request(app(client, principal(ALL, { delegationId: 'd-1' })));
    expect((await agent.put(`/wardrobe/items/${ITEM}/visibility`).send({ visibility: 'members' })).status).toBe(403);
    expect((await request(app(client, principal(['wardrobe:read']))).put(`/wardrobe/items/${ITEM}/visibility`).send({ visibility: 'private' }))
      .status).toBe(403);
    expect(client.calls).toHaveLength(1);
  });

  it('viewing another member: closet needs wardrobe:read, the card social:read; ids are validated', async () => {
    expect((await request(app(client, null)).get(`/members/${OTHER}/closet`)).status).toBe(401);
    expect((await request(app(client, principal(['profile:read']))).get(`/members/${OTHER}/closet`)).status).toBe(403);
    const a = request(app(client, principal(ALL)));
    expect((await a.get(`/members/${OTHER}/closet`)).status).toBe(200);
    expect((await a.get(`/members/${OTHER}/card`)).status).toBe(200);
    expect((await a.get('/members/nope/card')).status).toBe(404);
    expect(client.calls.map((c) => c.path)).toEqual([`/members/${OTHER}/closet`, `/members/${OTHER}/card`]);
  });

  it('card settings: audience, standings switch and at most six highlights; the member only', async () => {
    const a = request(app(client, principal(ALL)));
    for (const b of [{ audience: 'everyone' }, { show_standings: 'yes' }, { highlight_item_ids: Array(7).fill(ITEM) }, { highlight_item_ids: ['x'] },
      { tagline: 'hi' }]) {
      expect((await a.put('/me/persona/card').send(b)).status).toBe(422);
    }
    expect((await a.put('/me/persona/card').send({ audience: 'members', show_standings: true, highlight_item_ids: [ITEM] })).status).toBe(200);
    expect(client.calls.at(-1)).toMatchObject({ method: 'PUT', path: '/me/persona/card', body: { audience: 'members', show_standings: true } });
    expect((await a.get('/me/persona/card')).status).toBe(200);
    const agent = request(app(client, principal(ALL, { delegationId: 'd-1' })));
    expect((await agent.put('/me/persona/card').send({ audience: 'members' })).status).toBe(403);
  });
});
