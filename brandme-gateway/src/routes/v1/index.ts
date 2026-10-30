/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1 mount file. Every response carries
 * X-Request-Id and X-Brandme-Environment; errors are application/problem+json.
 */

import express, { Router, type Request, type Response } from 'express';
import type { JWTVerifyGetKey } from 'jose';
import type { GatewayConfig } from '../../config';
import { DEV_IDENTITY_ISSUER, DEV_IDENTITY_LABEL, isStrict } from '../../middleware/mode';
import { handle, problemHandler, problems, requestContext } from '../../middleware/problem';
import { principalMiddleware, requirePrincipal, sessionCookie } from '../../middleware/session';
import { principalRateLimiter } from '../../middleware/rateLimiter';
import { IdentityStore } from '../../middleware/identity/store';
import { validator } from '../../middleware/validation';
import type { Principal } from '../../types';
import { meRouter } from './me';
import { rightsDependencies } from '../../services/rights';
import { createChainRouter, type V1Deps } from './chain';
import { createRightsRouter } from './rights';
import { createOwnershipRouter } from './ownership';
import { createAssetsRouter } from './assets';
import { createPrivacyRouter } from './privacy';
import { consumerDomainClient } from '../../services/domains';
import { personaRouter, type DomainClient } from './persona';
import { wardrobeRouter } from './wardrobe';
import { outfitsRouter } from './outfits';
import { socialRouter } from './social';
import { decisionsRouter } from './decisions';
import { flowRouter } from './flow';
import { roomsRouter } from './rooms';
import { rewardsRouter } from './rewards';
import { mediaRouter } from './media';
import { tryOnRouter } from './tryon';

const validateDevSession = validator('DevSessionCreate');

export interface ApiV1Deps {
  cfg: GatewayConfig;
  store: IdentityStore;
  jwks?: JWTVerifyGetKey;
  fetchImpl?: typeof fetch;
  rights?: V1Deps;
  /** Consumer-domain transport; defaults to the signed-assertion client from cfg. */
  domains?: DomainClient;
}

async function timed(name: string, fn: () => Promise<void>) {
  const t0 = Date.now();
  try {
    await fn();
    return { name, status: 'ok' as const, duration_ms: Date.now() - t0 };
  } catch {
    return { name, status: 'unreachable' as const, duration_ms: Date.now() - t0 };
  }
}

export function apiV1(deps: ApiV1Deps): Router {
  const { cfg, store } = deps;
  const doFetch = deps.fetchImpl ?? fetch;
  const router = Router();

  router.use(requestContext(cfg.mode));
  router.use(express.json({ limit: '256kb' }));
  router.use(principalMiddleware({ cfg, store, jwks: deps.jwks }));
  router.use(principalRateLimiter(cfg));

  // W00 smoke: gateway → brain → Spanner, and gateway → Spanner directly.
  router.get(
    '/system/health',
    handle(async (_req, res) => {
      const checks = await Promise.all([
        timed('gateway.spanner', () => store.ping()),
        timed('brain.health', async () => {
          const r = await doFetch(`${cfg.brainUrl}/health`, { signal: AbortSignal.timeout(3000) });
          if (!r.ok) throw new Error(String(r.status));
          const body = (await r.json()) as { database?: string; status?: string };
          if (body.status !== 'ok' || body.database !== 'spanner') throw new Error('brain degraded');
        }),
      ]);
      const ok = checks.every((c) => c.status === 'ok');
      res.status(ok ? 200 : 503).json({ status: ok ? 'ok' : 'degraded', environment: cfg.mode, checks });
    }),
  );

  // demo/development only: fictional test identity. Refused (404) in strict modes.
  router.post(
    '/session/dev',
    handle(async (req: Request, res: Response) => {
      if (isStrict(cfg.mode) || cfg.identityProvider !== 'dev') throw problems.notFound();
      if (!validateDevSession(req.body)) throw problems.invalid('test_identity must match ^[a-z0-9_-]{1,40}$');
      const origin = req.header('origin');
      if (origin && !cfg.publicOrigins.includes(origin)) throw problems.csrf();
      const { test_identity } = req.body as { test_identity: string };
      const { memberId } = await store.resolveMember(DEV_IDENTITY_ISSUER, test_identity, 'dev', res.locals.requestId);
      const session = await store.createSession(memberId, 'dev', 'simulated', null, cfg.sessionTtlHours);
      res.setHeader('Set-Cookie', sessionCookie(cfg, session.secret, session.expiresAt));
      res.setHeader('X-Brandme-Simulation', DEV_IDENTITY_LABEL);
      res.status(201).json({
        member_id: memberId,
        csrf_token: session.csrf,
        expires_at: session.expiresAt.toISOString(),
        assurance_level: 'simulated',
      });
    }),
  );

  // Session info; rotates and returns the CSRF token (only readable by the
  // same-origin app, never stored in the cookie).
  router.get(
    '/session',
    requirePrincipal,
    handle(async (_req, res) => {
      const p: Principal = res.locals.principal;
      if (p.via !== 'session') throw problems.notFound();
      const csrf = await store.rotateCsrf(res.locals.sessionSecret);
      res.json({ member_id: p.memberId, csrf_token: csrf, expires_at: p.expiresAt.toISOString(), assurance_level: p.assuranceLevel });
    }),
  );

  router.delete(
    '/session',
    requirePrincipal,
    handle(async (_req, res) => {
      const p: Principal = res.locals.principal;
      if (p.via === 'session') await store.revokeSession(res.locals.sessionSecret, p.memberId, 'sign_out', res.locals.requestId);
      res.setHeader('Set-Cookie', sessionCookie(cfg, '', null));
      res.status(204).end();
    }),
  );

  const rights = deps.rights ?? rightsDependencies(cfg, doFetch);
  router.use('/chain', createChainRouter(rights));
  router.use('/rights', createRightsRouter(rights));
  router.use('/ownership', createOwnershipRouter(rights));
  router.use('/assets', createAssetsRouter(rights));
  router.use('/me', createPrivacyRouter(rights));
  router.use('/me', meRouter(cfg, store));

  // Consumer domains (persona, wardrobe, outfits, social, decisions, Flow and
  // houses, rooms, rewards, media, try-on): behind principalMiddleware,
  // forwarded with a signed principal assertion (services/domains.ts).
  // Unconfigured → 503 per route.
  const domains = deps.domains ?? consumerDomainClient(cfg, doFetch);
  const consumer = [personaRouter, wardrobeRouter, outfitsRouter, socialRouter, decisionsRouter, flowRouter, roomsRouter, rewardsRouter,
    mediaRouter, tryOnRouter];
  for (const mount of consumer) {
    router.use(mount(domains));
  }

  router.use((req: Request, res: Response) => problemHandler(problems.notFound(), req, res, () => undefined));
  router.use(problemHandler);
  return router;
}
