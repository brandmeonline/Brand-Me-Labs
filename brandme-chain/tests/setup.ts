/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Test Setup
 * ==========
 * Global test setup and utilities
 */

import { beforeAll, afterAll } from 'vitest';
import * as dotenv from 'dotenv';

// Load test environment variables
dotenv.config({ path: '.env.test' });

beforeAll(() => {
  // Set fallback mode for tests by default
  process.env.CARDANO_FALLBACK_MODE = process.env.CARDANO_FALLBACK_MODE || 'true';
  process.env.MIDNIGHT_FALLBACK_MODE = process.env.MIDNIGHT_FALLBACK_MODE || 'true';
});

afterAll(() => {
  // Cleanup
});
