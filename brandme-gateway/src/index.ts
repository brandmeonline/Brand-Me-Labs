/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Brand.Me Gateway — public domain API and identity boundary.
 * - /api/v1: versioned API (routes/v1), sessions/OIDC principal, problem+json
 * - /scan: legacy route, kept through the same principal resolution
 * - mode guard: sandbox/production refuse to boot with simulated identity
 */

import express from 'express';
import helmet from 'helmet';
import cors from 'cors';
import { config as defaultConfig, type GatewayConfig } from './config';
import { logger } from './config/logger';
import { connectNATS } from './services/nats';
import { errorHandler } from './middleware/errorHandler';
import { requestLogger } from './middleware/requestLogger';
import { authMiddleware } from './middleware/auth';
import { assertGatewayMode } from './middleware/mode';
import { principalMiddleware } from './middleware/session';
import { IdentityStore } from './middleware/identity/store';
import { rateLimiterMiddleware, strictRateLimiterMiddleware } from './middleware/rateLimiter';
import { apiV1, type ApiV1Deps } from './routes/v1';
import scanRouter from './routes/scan';
import healthRouter from './routes/health';

export function createApp(cfg: GatewayConfig, store: IdentityStore, extra: Partial<ApiV1Deps> = {}): express.Express {
  const app = express();
  app.disable('x-powered-by');
  app.use(
    helmet({
      contentSecurityPolicy: {
        directives: { defaultSrc: ["'self'"], styleSrc: ["'self'", "'unsafe-inline'"], scriptSrc: ["'self'"], imgSrc: ["'self'", 'data:', 'https:'] },
      },
    }),
  );
  app.use(
    cors({
      origin: (origin, callback) => {
        if (!origin || cfg.corsOrigins.includes(origin)) return callback(null, true);
        // No CORS headers for unknown origins; the browser blocks the read and
        // state changes are still refused by the CSRF/origin check.
        callback(null, false);
      },
      credentials: true,
      methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],
      allowedHeaders: ['Content-Type', 'Authorization', 'X-Request-Id', 'X-Region', 'X-CSRF-Token', 'If-Match', 'Idempotency-Key'],
      exposedHeaders: ['X-Request-Id', 'X-Brandme-Environment', 'X-Brandme-Simulation', 'ETag', 'X-RateLimit-Limit', 'X-RateLimit-Remaining'],
      maxAge: 86400,
    }),
  );
  app.use(requestLogger);
  app.use(rateLimiterMiddleware);

  app.use('/healthz', healthRouter);
  app.use('/health', healthRouter);
  app.use('/api/v1', apiV1({ cfg, store, ...extra }));

  app.use(
    '/scan',
    express.json({ limit: '1mb' }),
    strictRateLimiterMiddleware,
    principalMiddleware({ cfg, store, jwks: extra.jwks }),
    authMiddleware,
    scanRouter,
  );

  app.use(errorHandler);
  return app;
}

async function start(cfg: GatewayConfig): Promise<void> {
  assertGatewayMode(cfg);
  const store = new IdentityStore({
    projectId: cfg.spannerProjectId,
    instanceId: cfg.spannerInstanceId,
    databaseId: cfg.spannerDatabaseId,
    mode: cfg.mode,
  });
  if (cfg.natsUrl) {
    await connectNATS();
    logger.info('Connected to NATS (legacy /scan publisher)');
  } else {
    logger.warn('NATS_URL not set: legacy /scan publishing is unavailable');
  }
  const app = createApp(cfg, store);
  app.listen(cfg.port, () => {
    logger.info({ port: cfg.port, mode: cfg.mode, identityProvider: cfg.identityProvider }, 'Brand.Me Gateway listening');
  });
}

if (require.main === module) {
  start(defaultConfig).catch((error) => {
    logger.error({ err: error instanceof Error ? error.message : String(error) }, 'Gateway refused to start');
    process.exit(1);
  });
  process.on('SIGTERM', () => process.exit(0));
  process.on('SIGINT', () => process.exit(0));
}
