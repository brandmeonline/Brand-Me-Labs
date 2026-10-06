import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    env: {
      BRANDME_MODE: 'development',
      LOG_LEVEL: 'warn',
      SPANNER_EMULATOR_HOST: process.env.SPANNER_EMULATOR_HOST ?? 'localhost:9010',
    },
    testTimeout: 60_000,
    hookTimeout: 180_000,
  },
});
