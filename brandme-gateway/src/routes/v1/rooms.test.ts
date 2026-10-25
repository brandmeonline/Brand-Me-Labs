/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Rooms router in a throwaway app (fake DomainClient, test-only principal).
 */

import express, { type NextFunction, type Request, type Response } from 'express';
import request from 'supertest';
import { beforeEach, describe, expect, it } from 'vitest';
import { problemHandler, requestContext } from '../../middleware/problem';
import type { Principal } from '../../types';
import type { DomainClient, DomainRequest, DomainResponse } from './persona';
import { roomsRouter } from './rooms';

const ROOM = '0b6f1a3e-7f1d-4c55-9a0e-2f6b8c1d9e10';
const POST = '6d0b9a8e-2f4c-4b1a-9e3d-7c5a1b2e3f40';
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
  a.use(roomsRouter(client));
  a.use(problemHandler);
  return a;
}

const ALL = ['social:read', 'social:write'];

describe('rooms router', () => {
  let client: FakeClient;
  beforeEach(() => {
    client = new FakeClient();
  });

  it('opening a room: a title, at most 11 people by id, an Idempotency-Key; the member only', async () => {
    expect((await request(app(client, null)).get('/rooms')).status).toBe(401);
    const a = request(app(client, principal(ALL)));
    const open = (b: object) => a.post('/rooms').set('Idempotency-Key', KEY).send(b);
    for (const b of [{}, { title: '' }, { title: 'x'.repeat(81) }, { title: 'R', member_ids: ['x'] }, { title: 'R', member_ids: Array(12).fill(POST) },
      { title: 'R', public: true }]) {
      expect((await open(b)).status).toBe(422);
    }
    expect((await a.post('/rooms').send({ title: 'Bridesmaids' })).status).toBe(400);
    expect((await open({ title: 'Bridesmaids', purpose: 'Pick by Friday', member_ids: [POST] })).status).toBe(200);
    expect(client.calls[0]).toMatchObject({ method: 'POST', path: '/rooms', idempotencyKey: KEY });
    const agent = request(app(client, principal(ALL, { delegationId: 'd-1' })));
    expect((await agent.post('/rooms').set('Idempotency-Key', KEY).send({ title: 'R' })).status).toBe(403);
    expect((await agent.put(`/rooms/${ROOM}/posts/${POST}/reaction`).send({ reaction: 'yes' })).status).toBe(403);
    expect(client.calls).toHaveLength(1);
  });

  it('posts and reactions have strict shapes; ids are validated', async () => {
    const a = request(app(client, principal(ALL)));
    const post = (b: object) => a.post(`/rooms/${ROOM}/posts`).set('Idempotency-Key', KEY).send(b);
    for (const b of [{ kind: 'poll' }, { kind: 'piece', subject_type: 'outfit', subject_id: POST }, { kind: 'piece', subject_type: 'wardrobe_item' },
      { kind: 'note', body: 'x'.repeat(1001) }, { kind: 'note', body: 'hi', author_id: POST }]) {
      expect((await post(b)).status).toBe(422);
    }
    expect((await post({ kind: 'piece', subject_type: 'catalog_product', subject_id: POST, body: 'This one?' })).status).toBe(200);
    expect((await a.put(`/rooms/${ROOM}/posts/${POST}/reaction`).send({ reaction: 'love' })).status).toBe(422);
    expect((await a.put(`/rooms/${ROOM}/posts/${POST}/reaction`).send({ reaction: 'maybe' })).status).toBe(200);
    expect(client.calls.at(-1)).toMatchObject({ method: 'PUT', path: `/rooms/${ROOM}/posts/${POST}/reaction`, body: { reaction: 'maybe' } });
    expect((await a.get('/rooms/not-an-id')).status).toBe(404);
    expect((await a.post(`/rooms/${ROOM}/members`).send({ member_id: 'x' })).status).toBe(422);
    for (const [m, p] of [['post', `/rooms/${ROOM}/archive`], ['delete', `/rooms/${ROOM}/members/${POST}`], ['delete', `/rooms/${ROOM}/posts/${POST}`]] as const) {
      expect((await a[m](p)).status).toBe(200);
    }
  });
});
