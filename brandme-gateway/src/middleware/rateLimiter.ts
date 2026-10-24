/**
 * Brand.Me Gateway - Rate Limiting Middleware
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Token buckets (capacity = max requests, full refill over the window), two
 * tiers (ch.03 §6 and §9):
 *
 *   1. ipRateLimiter — pre-auth security limit keyed by client address, on
 *      every route except the kubelet probes /health and /healthz. It applies
 *      to all methods: it is the security limit, so exhausting it blocks reads
 *      and exports too. The client address is req.ip, so it depends on the
 *      TRUST_PROXY setting (config/index.ts; GKE Ingress: 2). IPv6 clients
 *      are keyed by their /64.
 *   2. principalRateLimiter — per-member budget, mounted after principal
 *      resolution (routes/v1/index.ts, and /scan). Keyed by member when a
 *      principal is known, by client address otherwise. Read-only requests
 *      and data-export requests are exempt, so read-only recovery and export
 *      stay usable while a member's (non-security) budget is exhausted.
 *
 * Throttled requests get a 429 application/problem+json (spec Problem) with
 * Retry-After and request_id. Logs carry the limiter scope, key kind and a
 * templated path, never the key itself (member ID or IP address).
 *
 * Storage is in memory, per process, bounded to RATE_LIMIT_MAX_KEYS buckets
 * per limiter with least-recently-used eviction. Evicting a bucket forgets
 * that client's usage, so the bound trades exactness for memory under key
 * floods. With N gateway replicas a client gets up to N times the budget
 * and a restart resets all buckets: multi-replica deployments need a shared
 * store (for example Memorystore/Redis with an atomic token-bucket script)
 * before these limits can be relied on for cost or abuse control.
 */

import { isIPv6 } from 'node:net';
import type { NextFunction, Request, Response } from 'express';
import type { GatewayConfig } from '../config';
import { logger } from '../config/logger';
import type { Principal } from '../types';
import { requestPath, templatePath } from './logPath';
import { problems, resolveRequestId, sendProblem } from './problem';

interface Bucket {
  tokens: number;
  updated: number;
}

export interface TakeResult {
  allowed: boolean;
  remaining: number;
  /** Milliseconds until one request is allowed again (0 when allowed). */
  retryAfterMs: number;
  /** Milliseconds until the bucket is full again. */
  resetMs: number;
}

export class TokenBucketStore {
  private readonly buckets = new Map<string, Bucket>();
  private readonly ratePerMs: number;
  private evicted = 0;

  constructor(
    private readonly capacity: number,
    windowMs: number,
    private readonly maxKeys: number,
    private readonly now: () => number = Date.now,
  ) {
    if (!(capacity >= 1) || !(windowMs >= 1) || !(maxKeys >= 1)) throw new RangeError('rate limit capacity, window and key bound must be >= 1');
    this.ratePerMs = capacity / windowMs;
  }

  take(key: string): TakeResult {
    const t = this.now();
    let bucket = this.buckets.get(key);
    if (bucket) {
      // Re-insert so Map order stays least-recently-used first.
      this.buckets.delete(key);
      bucket.tokens = Math.min(this.capacity, bucket.tokens + Math.max(0, t - bucket.updated) * this.ratePerMs);
      bucket.updated = t;
    } else {
      bucket = { tokens: this.capacity, updated: t };
      while (this.buckets.size >= this.maxKeys) {
        const oldest = this.buckets.keys().next().value as string;
        this.buckets.delete(oldest);
        this.evicted++;
      }
    }
    this.buckets.set(key, bucket);
    const allowed = bucket.tokens >= 1;
    if (allowed) bucket.tokens -= 1;
    return {
      allowed,
      remaining: Math.floor(bucket.tokens),
      retryAfterMs: allowed ? 0 : Math.ceil((1 - bucket.tokens) / this.ratePerMs),
      resetMs: Math.ceil((this.capacity - bucket.tokens) / this.ratePerMs),
    };
  }

  has(key: string): boolean {
    return this.buckets.has(key);
  }

  get size(): number {
    return this.buckets.size;
  }

  get evictions(): number {
    return this.evicted;
  }
}

export type KeyKind = 'member' | 'ip';

/** Rate-limit key for a client address: IPv4 (incl. IPv4-mapped IPv6) as is, IPv6 by /64. */
export function clientAddressKey(address: string | undefined): string {
  if (!address) return 'ip:unknown';
  const mapped = /^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$/i.exec(address);
  if (mapped) return `ip:${mapped[1]}`;
  if (!isIPv6(address.split('%')[0])) return `ip:${address}`;
  const [head, tail] = address.split('%')[0].toLowerCase().split('::');
  const width = (groups: string[]) => groups.reduce((n, g) => n + (g.includes('.') ? 2 : 1), 0);
  const left = head ? head.split(':') : [];
  const right = tail ? tail.split(':') : [];
  const groups = tail === undefined ? left : [...left, ...Array<string>(8 - width(left) - width(right)).fill('0'), ...right];
  return `ip6:${groups.slice(0, 4).map((g) => parseInt(g, 16).toString(16)).join(':')}::/64`;
}

export function rateLimitKey(req: Request, res: Response, keyBy: 'ip' | 'principal'): { key: string; kind: KeyKind } {
  const principal = res.locals.principal as Principal | undefined;
  if (keyBy === 'principal' && principal?.memberId) return { key: `member:${principal.memberId}`, kind: 'member' };
  return { key: clientAddressKey(req.ip ?? req.socket.remoteAddress), kind: 'ip' };
}

const fullPath = requestPath;

/** Kubelet liveness/readiness probes are never throttled. */
export function isHealthProbe(req: Request): boolean {
  return /^\/healthz?\/?$/.test(fullPath(req));
}

const READ_ONLY = new Set(['GET', 'HEAD', 'OPTIONS']);
const EXPORT_PATH = /^\/api\/v1\/me\/exports(?:\/|$)/i;
const SESSION_PATH = /^\/api\/v1\/session\/?$/i;

/**
 * Essential access kept open under budget exhaustion (ch.03 §9): read-only
 * requests, the member's data export (POST /api/v1/me/exports and the export
 * job/download routes) and sign-out (DELETE /api/v1/session), so a member is
 * never stuck in a session. Deletion and other mutations are budgeted.
 */
export function isEssentialAccess(req: Request): boolean {
  return READ_ONLY.has(req.method) || EXPORT_PATH.test(fullPath(req))
    || (req.method === 'DELETE' && SESSION_PATH.test(fullPath(req)));
}

export interface RateLimiterOptions {
  /** Label for logs and stats, e.g. 'ip', 'principal', 'scan'. */
  scope: string;
  maxRequests: number;
  windowMs: number;
  maxKeys: number;
  keyBy: 'ip' | 'principal';
  /** Requests for which this limiter neither counts nor blocks. */
  exempt?: (req: Request) => boolean;
  now?: () => number;
}

export interface RateLimiter {
  (req: Request, res: Response, next: NextFunction): void;
  readonly store: TokenBucketStore;
  stats(): { scope: string; keys: number; maxKeys: number; evictions: number };
}

export function createRateLimiter(opts: RateLimiterOptions): RateLimiter {
  const store = new TokenBucketStore(opts.maxRequests, opts.windowMs, opts.maxKeys, opts.now);
  const middleware = (req: Request, res: Response, next: NextFunction): void => {
    if (opts.exempt?.(req)) return next();
    const { key, kind } = rateLimitKey(req, res, opts.keyBy);
    const result = store.take(key);
    // Two limiters can apply (address, then member). Report the tighter one so a
    // client pacing itself by these headers is never surprised by the other.
    const shown = res.locals.rateLimitShown as { remaining: number } | undefined;
    if (!shown || result.remaining < shown.remaining) {
      res.locals.rateLimitShown = { remaining: result.remaining };
      res.setHeader('X-RateLimit-Limit', String(opts.maxRequests));
      res.setHeader('X-RateLimit-Remaining', String(result.remaining));
      res.setHeader('X-RateLimit-Reset', String(Math.ceil(result.resetMs / 1000)));
    }
    if (result.allowed) return next();
    const retryAfter = Math.max(1, Math.ceil(result.retryAfterMs / 1000));
    logger.warn({
      requestId: resolveRequestId(req, res),
      scope: opts.scope,
      keyKind: kind,
      method: req.method,
      path: templatePath(req.originalUrl),
    }, 'Rate limit exceeded');
    sendProblem(res, req, problems.rateLimited(retryAfter));
  };
  return Object.assign(middleware, {
    store,
    stats: () => ({ scope: opts.scope, keys: store.size, maxKeys: opts.maxKeys, evictions: store.evictions }),
  });
}

type LimitConfig = Pick<GatewayConfig, 'rateLimitWindow' | 'rateLimitMaxRequests' | 'rateLimitIpMaxRequests' | 'rateLimitMaxKeys'>;

/** Pre-auth security limiter keyed by client address (app level, before /api/v1 and /scan). */
export function ipRateLimiter(cfg: LimitConfig, now?: () => number): RateLimiter {
  return createRateLimiter({
    scope: 'ip',
    maxRequests: cfg.rateLimitIpMaxRequests,
    windowMs: cfg.rateLimitWindow,
    maxKeys: cfg.rateLimitMaxKeys,
    keyBy: 'ip',
    exempt: isHealthProbe,
    now,
  });
}

/** Per-member budget, mounted after principal resolution. One bucket set per scope. */
export function principalRateLimiter(cfg: LimitConfig, scope = 'principal', now?: () => number): RateLimiter {
  return createRateLimiter({
    scope,
    maxRequests: cfg.rateLimitMaxRequests,
    windowMs: cfg.rateLimitWindow,
    maxKeys: cfg.rateLimitMaxKeys,
    keyBy: 'principal',
    exempt: isEssentialAccess,
    now,
  });
}
