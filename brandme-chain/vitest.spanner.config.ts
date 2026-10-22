import { defineConfig } from 'vitest/config';

if (!process.env.SPANNER_EMULATOR_HOST) throw new Error('test:spanner requires a real Spanner emulator');
export default defineConfig({ test: { globals: true, environment: 'node', include: ['tests/spanner/**/*.test.ts'],
  hookTimeout: 120_000, testTimeout: 60_000, fileParallelism: false } });
