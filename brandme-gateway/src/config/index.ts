/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Configuration. BRANDME_MODE (demo | development | sandbox | production) is
 * required; the mode guard in middleware/mode.ts refuses unsafe combinations.
 * Secrets never have defaults here.
 */

import dotenv from 'dotenv';
import { z } from 'zod';

dotenv.config();

const list = (fallback: string) =>
  z
    .string()
    .default(fallback)
    .transform((val) => val.split(',').map((s) => s.trim()).filter(Boolean));

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

  rateLimitWindow: z.coerce.number().default(15 * 60 * 1000),
  rateLimitMaxRequests: z.coerce.number().default(100),
  logLevel: z.enum(['trace', 'debug', 'info', 'warn', 'error', 'fatal']).default('info'),
});

export type GatewayConfig = z.infer<typeof configSchema> & { environment: 'development' | 'staging' | 'production' };

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
    logLevel: blank(env.LOG_LEVEL),
  });
  // Legacy field used by the logger and older routes.
  const environment = parsed.mode === 'production' ? 'production' : parsed.mode === 'sandbox' ? 'staging' : 'development';
  return { ...parsed, environment };
}

export const config: GatewayConfig = loadConfig();
