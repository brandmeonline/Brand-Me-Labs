/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Vitest Configuration
 * ====================
 * Test configuration for Brand.Me Chain Service
 */

import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/*.{test,spec}.ts', 'tests/**/*.{test,spec}.ts'],
    exclude: ['node_modules', 'dist'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules',
        'dist',
        '**/*.config.ts',
        '**/*.d.ts',
        'tests/**',
      ],
    },
    testTimeout: 30000, // 30s for blockchain operations
    hookTimeout: 30000,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
