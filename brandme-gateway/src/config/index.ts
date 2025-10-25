/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Configuration
 */

import dotenv from 'dotenv';
import { z } from 'zod';

dotenv.config();

const configSchema = z.object({
  // Server
  port: z.coerce.number().default(3000),
  environment: z.enum(['development', 'staging', 'production']).default('development'),

  // OAuth
  oauthClientId: z.string(),
  oauthClientSecret: z.string(),
  oauthIssuer: z.string().url().default('https://accounts.google.com'),
  jwtSecret: z.string().min(32),

  // NATS
  natsUrl: z.string().url().default('nats://localhost:4222'),
  natsMaxReconnectAttempts: z.coerce.number().default(10),

  // Region
  defaultRegion: z.string().default('us-east1'),

  // CORS
  corsOrigins: z.string().transform(val => val.split(',')).default('http://localhost:3002'),

  // Rate Limiting
  rateLimitWindow: z.coerce.number().default(15 * 60 * 1000), // 15 minutes
  rateLimitMaxRequests: z.coerce.number().default(100),

  // Logging
  logLevel: z.enum(['trace', 'debug', 'info', 'warn', 'error', 'fatal']).default('info'),
});

const envConfig = {
  port: process.env.PORT,
  environment: process.env.ENVIRONMENT,
  oauthClientId: process.env.OAUTH_CLIENT_ID,
  oauthClientSecret: process.env.OAUTH_CLIENT_SECRET,
  oauthIssuer: process.env.OAUTH_ISSUER,
  jwtSecret: process.env.JWT_SECRET,
  natsUrl: process.env.NATS_URL,
  natsMaxReconnectAttempts: process.env.NATS_MAX_RECONNECT_ATTEMPTS,
  defaultRegion: process.env.DEFAULT_REGION,
  corsOrigins: process.env.CORS_ORIGINS,
  rateLimitWindow: process.env.RATE_LIMIT_WINDOW_MS,
  rateLimitMaxRequests: process.env.RATE_LIMIT_MAX_REQUESTS,
  logLevel: process.env.LOG_LEVEL,
};

export const config = configSchema.parse(envConfig);
