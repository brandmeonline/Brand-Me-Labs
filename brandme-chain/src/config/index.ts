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

  // Cardano Configuration
  cardanoNetwork: z.enum(['mainnet', 'testnet', 'preprod', 'preview']).default('preprod'),
  cardanoWalletPath: z.string().optional(),
  cardanoMnemonicPath: z.string().optional(),
  blockfrostApiKey: z.string().optional(),
  cardanoFallbackMode: z.string().transform(v => v === 'true').default('true'),

  // Midnight Configuration
  midnightNetwork: z.enum(['mainnet', 'testnet', 'devnet']).default('testnet'),
  midnightWalletPath: z.string().optional(),
  midnightRpcUrl: z.string().optional(),
  midnightFallbackMode: z.string().transform(v => v === 'true').default('true'),
});

const envConfig = {
  port: process.env.PORT,
  environment: process.env.ENVIRONMENT,
  corsOrigins: process.env.CORS_ORIGINS,
  logLevel: process.env.LOG_LEVEL,

  // Cardano
  cardanoNetwork: process.env.CARDANO_NETWORK,
  cardanoWalletPath: process.env.CARDANO_WALLET_PATH,
  cardanoMnemonicPath: process.env.CARDANO_MNEMONIC_PATH,
  blockfrostApiKey: process.env.BLOCKFROST_API_KEY,
  cardanoFallbackMode: process.env.CARDANO_FALLBACK_MODE,

  // Midnight
  midnightNetwork: process.env.MIDNIGHT_NETWORK,
  midnightWalletPath: process.env.MIDNIGHT_WALLET_PATH,
  midnightRpcUrl: process.env.MIDNIGHT_RPC_URL,
  midnightFallbackMode: process.env.MIDNIGHT_FALLBACK_MODE,
};

export const config = configSchema.parse(envConfig);
