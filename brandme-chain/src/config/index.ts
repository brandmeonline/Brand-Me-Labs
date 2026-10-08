/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Configuration. There is no "fallback mode": a missing or misconfigured
 * Midnight capability is reported as unavailable, never simulated.
 */

import dotenv from 'dotenv';
import { z } from 'zod';

dotenv.config();

const configSchema = z.object({
  port: z.coerce.number().default(3001),
  environment: z.enum(['demo', 'development', 'sandbox', 'production']).default('development'),
  corsOrigins: z.string().transform((val) => val.split(',')).default('http://localhost:3000'),
  logLevel: z.enum(['trace', 'debug', 'info', 'warn', 'error', 'fatal']).default('info'),

  // Midnight (primary rights network)
  midnightNetwork: z.enum(['undeployed', 'preview', 'preprod', 'mainnet']).default('preprod'),
  midnightContractAddress: z.string().regex(/^[0-9a-f]{64,}$/i).optional(),
  midnightBlockfrostProjectId: z.string().optional(),
  midnightLocalNodePort: z.coerce.number().optional(),
  midnightLocalIndexerPort: z.coerce.number().optional(),
});

const removedFlags = ['MIDNIGHT_FALLBACK_MODE', 'CARDANO_FALLBACK_MODE'];
for (const f of removedFlags) {
  if (process.env[f] === 'true') {
    throw new Error(`${f}=true is no longer supported: simulated chain results are not permitted in the trust path`);
  }
}

export const config = configSchema.parse({
  port: process.env.PORT,
  environment: process.env.ENVIRONMENT,
  corsOrigins: process.env.CORS_ORIGINS,
  logLevel: process.env.LOG_LEVEL,
  midnightNetwork: process.env.MIDNIGHT_NETWORK,
  midnightContractAddress: process.env.MIDNIGHT_CONTRACT_ADDRESS,
  midnightBlockfrostProjectId: process.env.MIDNIGHT_BLOCKFROST_PROJECT_ID,
  midnightLocalNodePort: process.env.MIDNIGHT_LOCAL_NODE_PORT,
  midnightLocalIndexerPort: process.env.MIDNIGHT_LOCAL_INDEXER_PORT,
});

export type ChainConfig = typeof config;
