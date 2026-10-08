/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Network tests: real node + indexer + proof server. Local network
 * (MIDNIGHT_NETWORK=undeployed, started by scripts/local-network.sh) or
 * Preprod (MIDNIGHT_NETWORK=preprod, funded seeds required). Never Mainnet.
 */
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['tests/network/**/*.test.ts'],
    testTimeout: 60 * 60_000,
    hookTimeout: 30 * 60_000,
    fileParallelism: false,
    pool: 'forks',
    sequence: { concurrent: false },
  },
  server: { fs: { allow: ['..'] } },
});
