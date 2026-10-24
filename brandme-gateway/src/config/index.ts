/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Configuration. BRANDME_MODE (demo | development | sandbox | production) is
 * required; the mode guard in middleware/mode.ts refuses unsafe combinations.
 * Secrets never have defaults here.
 */

import { isIP } from 'node:net';
import dotenv from 'dotenv';
import { z } from 'zod';

dotenv.config();

const list = (fallback: string) =>
  z
    .string()
    .default(fallback)
    .transform((val) => val.split(',').map((s) => s.trim()).filter(Boolean));

/** Express `trust proxy` value: off, a hop count, or explicit proxy addresses/subnets. */
export type TrustProxy = false | number | string[];

const TRUST_PROXY_NAMES = new Set(['loopback', 'linklocal', 'uniquelocal']);

function isProxyAddress(entry: string): boolean {
  if (TRUST_PROXY_NAMES.has(entry)) return true;
  const [addr, prefix, ...rest] = entry.split('/');
  if (rest.length || !isIP(addr)) return false;
  if (prefix === undefined) return true;
  const max = isIP(addr) === 4 ? 32 : 128;
  return /^\d{1,3}$/.test(prefix) && Number(prefix) <= max;
}

/**
 * TRUST_PROXY (default off). Only set it when the gateway sits behind a proxy
 * you control; otherwise a client can choose its own rate-limit key through
 * X-Forwarded-For. `true` (trust every hop) is refused for that reason.
 *   - unset / false / 0: use the socket address (direct exposure, local dev).
 *   - N: trust N hops. GKE Ingress (external Application Load Balancer)
 *     appends "<client-ip>, <load-balancer-ip>" to X-Forwarded-For and
 *     connects from a Google front end, so the GKE value is TRUST_PROXY=2.
 *     That comes from Google's documented header format, not from a live
 *     cluster: confirm req.ip against a known client before relying on it.
 *   - comma list of IPs/CIDRs or loopback|linklocal|uniquelocal.
 */
const trustProxySchema = z
  .string()
  .optional()
  .transform((raw, ctx): TrustProxy => {
    const v = raw?.trim().toLowerCase();
    if (!v || v === 'false' || v === '0') return false;
    if (v === 'true') {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'TRUST_PROXY=true trusts any client-supplied X-Forwarded-For; set a hop count or proxy subnets' });
      return z.NEVER;
    }
    if (/^\d+$/.test(v)) {
      const hops = Number(v);
      if (hops > 10) ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'TRUST_PROXY hop count must be between 0 and 10' });
      return hops;
    }
    const entries = v.split(',').map((s) => s.trim()).filter(Boolean);
    const bad = entries.filter((e) => !isProxyAddress(e));
    if (bad.length || !entries.length) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: `TRUST_PROXY entries must be IPs, CIDRs or ${[...TRUST_PROXY_NAMES].join('|')}` });
      return z.NEVER;
    }
    return entries;
  });

const configSchema = z.object({
  mode: z.enum(['demo', 'development', 'sandbox', 'production']),
  port: z.coerce.number().int().min(1).max(65535).default(3001),

  // Identity: 'oidc' verifies issuer/audience/algorithm via JWKS; 'dev' is a
  // labelled simulation available only in demo/development.
  identityProvider: z.enum(['oidc', 'dev']).default('dev'),
  oidcIssuer: z.string().url().optional(),
  oidcAudience: z.string().min(1).optional(),
  oidcJwksUri: z.string().url().optional(),
  oidcAlgorithms: list('RS256,ES256'),
  sessionTtlHours: z.coerce.number().int().min(1).max(24 * 30).default(24 * 7),

  // Downstream services and persistence
  brainUrl: z.string().url().default('http://localhost:8000'),
  chainUrl: z.string().url().default('http://localhost:3003'),
  rightsServiceUrl: z.string().url().optional(),
  privacyServiceUrl: z.string().url().optional(),
  privacyExportServiceUrl: z.string().url().optional(),
  rightsServiceToken: z.string().min(32).optional(),
  privacyServiceToken: z.string().min(32).optional(),
  privacyExportServiceToken: z.string().min(32).optional(),
  chainServiceToken: z.string().min(32).optional(),
  spannerProjectId: z.string().default('test-project'),
  spannerInstanceId: z.string().default('brandme-instance'),
  spannerDatabaseId: z.string().default('brandme-db'),

  // Legacy NATS publisher for /scan; optional so the gateway boots without it.
  natsUrl: z.string().url().optional(),
  natsMaxReconnectAttempts: z.coerce.number().default(10),

  defaultRegion: z.string().default('us-east1'),
  corsOrigins: list('http://localhost:3000,http://localhost:3002'),
  // Origins allowed to make cookie-authenticated state changes (CSRF origin check).
  publicOrigins: list('http://localhost:3000,http://localhost:3002'),

  // Rate limits (middleware/rateLimiter.ts). Token buckets that refill fully
  // over RATE_LIMIT_WINDOW_MS.
  //   RATE_LIMIT_MAX_REQUESTS: per-member budget for non-essential requests
  //     (mutations other than data export); read-only and export requests are
  //     exempt from it (ch.03 §9). Signed-out callers are budgeted by address.
  //     /api/v1 and the legacy /scan keep separate buckets.
  //   RATE_LIMIT_IP_MAX_REQUESTS: pre-auth security limit per client address
  //     on every route except /health and /healthz (default = 100/min sustained).
  //   RATE_LIMIT_MAX_KEYS: tracked keys per limiter before LRU eviction.
  rateLimitWindow: z.coerce.number().int().positive().default(15 * 60 * 1000),
  rateLimitMaxRequests: z.coerce.number().int().positive().default(100),
  rateLimitIpMaxRequests: z.coerce.number().int().positive().default(1500),
  rateLimitMaxKeys: z.coerce.number().int().positive().default(10_000),
  trustProxy: trustProxySchema,
  logLevel: z.enum(['trace', 'debug', 'info', 'warn', 'error', 'fatal']).default('info'),
});

export type GatewayConfig = z.infer<typeof configSchema> & {
  environment: 'development' | 'staging' | 'production';
  /** CHAIN_SERVICE_URL was set explicitly (chainUrl otherwise carries a local default). */
  chainUrlExplicit: boolean;
};

const blank = (v: string | undefined) => (v === undefined || v.trim() === '' ? undefined : v);

export function loadConfig(env: NodeJS.ProcessEnv = process.env): GatewayConfig {
  const parsed = configSchema.parse({
    mode: blank(env.BRANDME_MODE),
    port: blank(env.PORT),
    identityProvider: blank(env.IDENTITY_PROVIDER),
    oidcIssuer: blank(env.OIDC_ISSUER),
    oidcAudience: blank(env.OIDC_AUDIENCE),
    oidcJwksUri: blank(env.OIDC_JWKS_URI),
    oidcAlgorithms: blank(env.OIDC_ALGORITHMS),
    sessionTtlHours: blank(env.SESSION_TTL_HOURS),
    brainUrl: blank(env.BRAIN_SERVICE_URL),
    chainUrl: blank(env.CHAIN_SERVICE_URL),
    rightsServiceUrl: blank(env.RIGHTS_SERVICE_URL),
    privacyServiceUrl: blank(env.PRIVACY_SERVICE_URL),
    privacyExportServiceUrl: blank(env.PRIVACY_EXPORT_SERVICE_URL),
    rightsServiceToken: blank(env.RIGHTS_SERVICE_TOKEN),
    privacyServiceToken: blank(env.PRIVACY_SERVICE_TOKEN),
    privacyExportServiceToken: blank(env.PRIVACY_EXPORT_SERVICE_TOKEN),
    chainServiceToken: blank(env.CHAIN_SERVICE_TOKEN),
    spannerProjectId: blank(env.SPANNER_PROJECT_ID),
    spannerInstanceId: blank(env.SPANNER_INSTANCE_ID),
    spannerDatabaseId: blank(env.SPANNER_DATABASE_ID),
    natsUrl: blank(env.NATS_URL),
    natsMaxReconnectAttempts: blank(env.NATS_MAX_RECONNECT_ATTEMPTS),
    defaultRegion: blank(env.DEFAULT_REGION),
    corsOrigins: blank(env.CORS_ORIGINS),
    publicOrigins: blank(env.PUBLIC_ORIGINS),
    rateLimitWindow: blank(env.RATE_LIMIT_WINDOW_MS),
    rateLimitMaxRequests: blank(env.RATE_LIMIT_MAX_REQUESTS),
    rateLimitIpMaxRequests: blank(env.RATE_LIMIT_IP_MAX_REQUESTS),
    rateLimitMaxKeys: blank(env.RATE_LIMIT_MAX_KEYS),
    trustProxy: blank(env.TRUST_PROXY),
    logLevel: blank(env.LOG_LEVEL),
  });
  // Legacy field used by the logger and older routes.
  const environment = parsed.mode === 'production' ? 'production' : parsed.mode === 'sandbox' ? 'staging' : 'development';
  return { ...parsed, environment, chainUrlExplicit: blank(env.CHAIN_SERVICE_URL) !== undefined };
}

export const config: GatewayConfig = loadConfig();
