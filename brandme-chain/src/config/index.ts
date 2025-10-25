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
  port: z.coerce.number().default(3001),
  environment: z.enum(['development', 'staging', 'production']).default('development'),

  // CORS
  corsOrigins: z.string().transform(val => val.split(',')).default('http://localhost:3000'),

  // Logging
  logLevel: z.enum(['trace', 'debug', 'info', 'warn', 'error', 'fatal']).default('info'),

  // Blockchain (secrets loaded from K8s in production)
  cardanoWalletPath: z.string().optional(),
  midnightWalletPath: z.string().optional(),
});

const envConfig = {
  port: process.env.PORT,
  environment: process.env.ENVIRONMENT,
  corsOrigins: process.env.CORS_ORIGINS,
  logLevel: process.env.LOG_LEVEL,
  cardanoWalletPath: process.env.CARDANO_WALLET_PATH,
  midnightWalletPath: process.env.MIDNIGHT_WALLET_PATH,
};

export const config = configSchema.parse(envConfig);
