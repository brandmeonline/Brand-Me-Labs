/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1 Home = Flow and followed houses (lane: opus-consumer-domains;
 * Ultra plan 02, item 3), mounted from index.ts behind principalMiddleware.
 *
 * Flow position is freshness; size and depth come from excitement, and each
 * item says why. Following a house, and whether that house may see the
 * member's standing tier, is the member's own choice: an agent cannot make it.
 */

import { Router, type Request } from 'express';
import { problems } from '../../middleware/problem';
import { requirePrincipal } from '../../middleware/session';
import type { Principal } from '../../types';
import { forwardTo, objectBody, pickQuery, requireScope, type DomainClient } from './persona';

const HOUSE_REF_RE = /^[a-z0-9](?:[a-z0-9-]{0,118}[a-z0-9])?$/;

function houseRef(req: Request): string {
  const v = req.params.houseRef;
  if (!v || !HOUSE_REF_RE.test(v)) throw problems.notFound();
  return v;
}

function memberOnly(p: Principal): void {
  if (p.delegationId) throw problems.forbidden('Only the member can follow a house or share their standing.');
}

export function flowRouter(client: DomainClient): Router {
  const r = Router();
  r.use(['/flow', '/houses'], requirePrincipal);

  r.get('/flow', requireScope('social:read'), forwardTo(client, (req) => ({ method: 'GET', path: '/flow', query: pickQuery(req, ['cursor', 'limit']) })));
  r.get('/houses', requireScope('social:read'), forwardTo(client, () => ({ method: 'GET', path: '/houses' })));
  r.put(
    '/houses/:houseRef/follow',
    requireScope('social:write'),
    forwardTo(client, (req, res) => {
      memberOnly(res.locals.principal as Principal);
      const b = objectBody(req, 1);
      const extra = Object.keys(b).filter((k) => k !== 'share_standing');
      if (extra.length) throw problems.invalid(`Unknown fields: ${extra.join(', ')}.`);
      if (b.share_standing !== undefined && typeof b.share_standing !== 'boolean') throw problems.invalid('share_standing must be true or false.');
      return { method: 'PUT', path: `/houses/${houseRef(req)}/follow`, body: b.share_standing === undefined ? {} : { share_standing: b.share_standing } };
    }),
  );
  r.delete(
    '/houses/:houseRef/follow',
    requireScope('social:write'),
    forwardTo(client, (req, res) => {
      memberOnly(res.locals.principal as Principal);
      return { method: 'DELETE', path: `/houses/${houseRef(req)}/follow` };
    }),
  );
  return r;
}
