/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Unmounted wardrobe + outfits routers in a throwaway app (fake DomainClient,
 * test-only principal). Gateway-side contract only; domain rules are tested in Python.
 */

import express, { type NextFunction, type Request, type Response } from 'express';
import request from 'supertest';
import { beforeEach, describe, expect, it } from 'vitest';
import { problemHandler, requestContext } from '../../middleware/problem';
import type { Principal } from '../../types';
import { outfitsRouter } from './outfits';
import type { DomainClient, DomainRequest, DomainResponse } from './persona';
import { placementShape, wardrobeRouter } from './wardrobe';

const ITEM = '0b6f1a3e-7f1d-4c55-9a0e-2f6b8c1d9e10';
const KEY = 'key-0123456789abcdef';

class FakeClient implements DomainClient {
  calls: DomainRequest[] = [];
  async request(req: DomainRequest): Promise<DomainResponse> {
    this.calls.push(req);
    return { status: 200, body: { ok: true }, headers: { etag: '"1"' } };
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
  a.use(wardrobeRouter(client));
  a.use(outfitsRouter(client));
  a.use(problemHandler);
  return a;
}

const ALL = ['wardrobe:read', 'wardrobe:write', 'outfits:read', 'outfits:write'];
const placement = {
  room_template_id: 'walnut_atelier', semantic_group: 'rail.left', slot_id: '0',
  position_meters: [-2.11, 1.75, -0.65], rotation_quaternion: [0, 0, 0, 1], uniform_scale: 1, asset_revision: 'original-v1',
};

describe('wardrobe/outfits routers (unmounted)', () => {
  let client: FakeClient;
  beforeEach(() => {
    client = new FakeClient();
  });

  it('placementShape rejects non-finite and malformed transforms', () => {
    expect(() => placementShape({ ...placement, position_meters: [1, 2] })).toThrow();
    expect(() => placementShape({ ...placement, rotation_quaternion: [0, 0, 0, Number.NaN] })).toThrow();
    expect(() => placementShape({ ...placement, position_meters: [Number.POSITIVE_INFINITY, 1, 1] })).toThrow();
    expect(() => placementShape({ ...placement, uniform_scale: 0 })).toThrow();
    expect(() => placementShape({ ...placement, owner_id: 'x' })).toThrow();
    expect(() => placementShape(placement)).not.toThrow();
  });

  it('PUT placement needs If-Match and a valid shape before forwarding', async () => {
    const a = app(client, ALL);
    expect((await request(a).put(`/closet/placements/${ITEM}`).send(placement)).status).toBe(428);
    expect((await request(a).put(`/closet/placements/${ITEM}`).set('If-Match', '"0"').send({ ...placement, rotation_quaternion: [0, 0, 1] })).status).toBe(422);
    expect(client.calls).toHaveLength(0);
    const ok = await request(a).put(`/closet/placements/${ITEM}`).set('If-Match', '"0"').send(placement);
    expect(ok.status).toBe(200);
    expect(client.calls[0]).toMatchObject({ method: 'PUT', path: `/closet/placements/${ITEM}`, ifMatch: '"0"' });
  });

  it('batch is bounded to 50 and needs an Idempotency-Key', async () => {
    const a = app(client, ALL);
    const many = Array.from({ length: 51 }, () => ({ ...placement, wardrobe_item_id: ITEM, version: '0' }));
    expect((await request(a).post('/closet/placements/batch').set('Idempotency-Key', KEY).send({ placements: many })).status).toBe(422);
    expect((await request(a).post('/closet/placements/batch').send({ placements: many.slice(0, 2) })).status).toBe(400);
    expect((await request(a).post('/closet/placements/batch').set('Idempotency-Key', KEY).send({ placements: many.slice(0, 2) })).status).toBe(200);
  });

  it('intake requires write scope and an Idempotency-Key; identity fields are refused', async () => {
    expect((await request(app(client, ['wardrobe:read'])).post('/wardrobe/items').set('Idempotency-Key', KEY).send({ source: 'manual' })).status).toBe(403);
    const a = app(client, ALL);
    expect((await request(a).post('/wardrobe/items').send({ source: 'manual' })).status).toBe(400);
    expect((await request(a).post('/wardrobe/items').set('Idempotency-Key', KEY).send({ source: 'manual', member_id: 'x' })).status).toBe(422);
    expect((await request(a).post('/wardrobe/items').set('Idempotency-Key', KEY).send({ source: 'manual', title: 't', category: 'top' })).status).toBe(200);
  });

  it('theme preview needs no If-Match; a real change does', async () => {
    const a = app(client, ALL);
    expect((await request(a).put('/closet/layout/theme?preview=true').send({ room_template_id: 'garden_studio' })).status).toBe(200);
    expect(client.calls[0].query).toEqual({ preview: 'true' });
    expect((await request(a).put('/closet/layout/theme').send({ room_template_id: 'garden_studio' })).status).toBe(428);
  });

  it('proposal decisions are accept/decline only and accept needs If-Match', async () => {
    const a = app(client, ALL);
    expect((await request(a).post(`/outfits/${ITEM}/proposals/${ITEM}/approve`)).status).toBe(404);
    expect((await request(a).post(`/outfits/${ITEM}/proposals/${ITEM}/accept`)).status).toBe(428);
    expect((await request(a).post(`/outfits/${ITEM}/proposals/${ITEM}/decline`)).status).toBe(200);
    expect((await request(a).post('/outfits/not-a-uuid/proposals').set('Idempotency-Key', KEY).send({})).status).toBe(404);
  });
});
