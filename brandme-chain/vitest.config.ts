/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Unit + local contract tests. No network access. Network tests (local
 * devnet / Preprod) use vitest.network.config.ts.
 */

import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['tests/**/*.test.ts', '../tests/contracts/**/*.test.ts'],
    exclude: ['node_modules', 'dist', 'tests/network/**'],
    testTimeout: 60_000,
    hookTimeout: 60_000,
    coverage: { provider: 'v8', reporter: ['text', 'json'], include: ['src/**'] },
  },
  server: { fs: { allow: ['..'] } },
});
