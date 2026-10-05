/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Principal resolution for /api/v1.
 *
 * Browser: `bm_session` cookie (HTTP-only, SameSite=Lax, Secure outside local
 * modes) → server-side Sessions row. Unsafe methods additionally need an
 * X-CSRF-Token matching the session's CSRF hash and, when sent, an allowed
 * Origin.
 *
 * Agents/API clients: `Authorization: Bearer <JWT>` verified against the OIDC
 * issuer's JWKS with an explicit algorithm allowlist, issuer and audience.
 * The verified (iss, sub) maps to an internal member; a `user_id` in a body or
 * tool argument is never identity.
 */

import { randomUUID, timingSafeEqual } from 'node:crypto';
import type { NextFunction, Request, Response } from 'express';
import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey } from 'jose';
import type { GatewayConfig } from '../config';
import type { Principal } from '../types';
import { problems } from './problem';
import { IdentityStore, sha256 } from './identity/store';

export const SESSION_COOKIE = 'bm_session';
const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export function parseCookies(header: string | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of (header ?? '').split(';')) {
    const i = part.indexOf('=');
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

export function sessionCookie(cfg: GatewayConfig, value: string, expires: Date | null): string {
  const secure = cfg.mode === 'demo' || cfg.mode === 'development' ? '' : '; Secure';
  const exp = expires ? `; Expires=${expires.toUTCString()}` : '; Max-Age=0';
  return `${SESSION_COOKIE}=${encodeURIComponent(value)}; Path=/; HttpOnly; SameSite=Lax${secure}${exp}`;
}

const safeEqualHex = (a: string, b: string) => a.length === b.length && timingSafeEqual(Buffer.from(a), Buffer.from(b));

export interface PrincipalResolverDeps {
  cfg: GatewayConfig;
  store: IdentityStore;
  /** Injected in tests; defaults to the issuer's remote JWKS. */
  jwks?: JWTVerifyGetKey;
}

export function principalMiddleware({ cfg, store, jwks }: PrincipalResolverDeps) {
  let keySet: JWTVerifyGetKey | undefined = jwks;
  const getKeys = (): JWTVerifyGetKey => {
    if (keySet) return keySet;
    if (!cfg.oidcIssuer) throw problems.unauthenticated();
    const uri = cfg.oidcJwksUri ?? `${cfg.oidcIssuer.replace(/\/$/, '')}/.well-known/jwks.json`;
    keySet = createRemoteJWKSet(new URL(uri), { cooldownDuration: 30_000, cacheMaxAge: 600_000 });
    return keySet;
  };

  return async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      const auth = req.header('authorization');
      if (auth?.startsWith('Bearer ')) {
        if (cfg.identityProvider !== 'oidc' || !cfg.oidcIssuer || !cfg.oidcAudience) throw problems.unauthenticated();
        let payload;
        try {
          ({ payload } = await jwtVerify(auth.slice(7), getKeys(), {
            issuer: cfg.oidcIssuer,
            audience: cfg.oidcAudience,
            algorithms: cfg.oidcAlgorithms,
            clockTolerance: 30,
          }));
        } catch {
          throw problems.unauthenticated();
        }
        if (!payload.sub) throw problems.unauthenticated();
        const { memberId } = await store.resolveMember(cfg.oidcIssuer, payload.sub, 'oidc', res.locals.requestId);
        const scopes = typeof payload.scope === 'string' ? payload.scope.split(' ').filter(Boolean) : [];
        res.locals.principal = {
          memberId,
          subject: payload.sub,
          sessionId: null,
          clientId: typeof payload.azp === 'string' ? payload.azp : typeof payload.client_id === 'string' ? payload.client_id : null,
          scopes,
          assuranceLevel: 'aal1',
          environment: cfg.mode,
          delegationId: null,
          identityProvider: 'oidc',
          expiresAt: new Date((payload.exp ?? 0) * 1000),
          via: 'bearer',
        } satisfies Principal;
        return next();
      }

      const secret = parseCookies(req.header('cookie'))[SESSION_COOKIE];
      if (secret) {
        const session = await store.loadSession(secret);
        if (session) {
          if (UNSAFE.has(req.method)) {
            const origin = req.header('origin');
            if (origin && !cfg.publicOrigins.includes(origin)) throw problems.csrf();
            const csrf = req.header('x-csrf-token');
            if (!csrf || !safeEqualHex(sha256(csrf), session.csrf_hash)) throw problems.csrf();
          }
          res.locals.sessionSecret = secret;
          res.locals.principal = {
            memberId: session.member_id,
            subject: session.member_id,
            sessionId: sha256(secret).slice(0, 16),
            clientId: session.client_id,
            scopes: ['profile:read', 'profile:write', 'privacy:manage'],
            assuranceLevel: session.assurance_level,
            environment: cfg.mode,
            delegationId: null,
            identityProvider: session.identity_provider,
            expiresAt: session.expires_at,
            via: 'session',
          } satisfies Principal;
        }
      }
      next();
    } catch (err) {
      next(err);
    }
  };
}

export function requirePrincipal(_req: Request, res: Response, next: NextFunction): void {
  if (!res.locals.principal) return next(problems.unauthenticated());
  next();
}

export const newCorrelationId = () => randomUUID();
