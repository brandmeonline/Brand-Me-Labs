import { describe, it, expect } from 'vitest';
import { getRateLimitStats } from './rateLimiter';

describe('rateLimiter', () => {
  it('exposes stats shape', () => {
    const stats = getRateLimitStats();
    expect(stats).toHaveProperty('activeClients');
    expect(typeof stats.activeClients).toBe('number');
  });
});
