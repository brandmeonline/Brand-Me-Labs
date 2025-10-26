/**
 * Brand.Me Gateway - Rate Limiting Middleware
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 * 
 * Implements token bucket rate limiting for API protection
 */

import { Request, Response, NextFunction } from 'express';
import { logger } from '../config/logger';

interface ClientInfo {
  tokens: number;
  lastRefill: number;
}

interface RateLimiterConfig {
  maxRequests: number;
  windowMs: number;
}

class TokenBucketRateLimiter {
  private clients: Map<string, ClientInfo> = new Map();
  private maxRequests: number;
  private windowMs: number;
  private refillRate: number; // tokens per second

  constructor(config: RateLimiterConfig) {
    this.maxRequests = config.maxRequests;
    this.windowMs = config.windowMs;
    this.refillRate = config.maxRequests / (config.windowMs / 1000);
  }

  private getClientKey(req: Request): string {
    // Use user ID if authenticated, otherwise use IP
    const userId = (req as any).user?.userId;
    return userId || req.ip || req.socket.remoteAddress || 'unknown';
  }

  private refillTokens(clientKey: string): number {
    const client = this.clients.get(clientKey);
    if (!client) {
      return this.maxRequests;
    }

    const now = Date.now();
    const elapsed = (now - client.lastRefill) / 1000; // seconds
    const tokensToAdd = elapsed * this.refillRate;
    const newTokens = Math.min(this.maxRequests, client.tokens + tokensToAdd);

    client.tokens = newTokens;
    client.lastRefill = now;

    return newTokens;
  }

  check(clientKey: string): { allowed: boolean; remaining: number; reset: number } {
    const tokens = this.refillTokens(clientKey);
    const allowed = tokens >= 1;

    if (allowed) {
      const client = this.clients.get(clientKey);
      if (client) {
        client.tokens = Math.max(0, client.tokens - 1);
      } else {
        this.clients.set(clientKey, {
          tokens: this.maxRequests - 1,
          lastRefill: Date.now(),
        });
      }
    } else {
      // Initialize or update client
      this.clients.set(clientKey, {
        tokens: tokens,
        lastRefill: Date.now(),
      });
    }

    const remaining = Math.max(0, Math.floor(tokens - (allowed ? 1 : 0)));
    const reset = Math.ceil((1 / this.refillRate) * 1000);

    return { allowed, remaining, reset };
  }

  clear(): void {
    this.clients.clear();
  }

  getClientCount(): number {
    return this.clients.size;
  }
}

// Global rate limiter instance
const rateLimiter = new TokenBucketRateLimiter({
  maxRequests: 100, // Maximum requests per window
  windowMs: 60000, // 1 minute window
});

/**
 * Rate limiting middleware
 */
export function rateLimiterMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const clientKey = rateLimiter.getClientKey(req);
  const { allowed, remaining, reset } = rateLimiter.check(clientKey);

  // Add rate limit headers
  res.setHeader('X-RateLimit-Limit', rateLimiter['maxRequests']);
  res.setHeader('X-RateLimit-Remaining', remaining);
  res.setHeader('X-RateLimit-Reset', reset);

  if (!allowed) {
    logger.warn('Rate limit exceeded', {
      clientKey,
      path: req.path,
      method: req.method,
    });

    res.status(429).json({
      error: 'Too Many Requests',
      message: 'Rate limit exceeded. Please try again later.',
      retryAfter: reset / 1000, // seconds
    });
    return;
  }

  next();
}

/**
 * Strict rate limiter for sensitive endpoints
 */
export function strictRateLimiterMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const strictLimiter = new TokenBucketRateLimiter({
    maxRequests: 10, // Lower limit
    windowMs: 60000,
  });

  const clientKey = strictLimiter.getClientKey(req);
  const { allowed, remaining, reset } = strictLimiter.check(clientKey);

  res.setHeader('X-RateLimit-Limit', strictLimiter['maxRequests']);
  res.setHeader('X-RateLimit-Remaining', remaining);
  res.setHeader('X-RateLimit-Reset', reset);

  if (!allowed) {
    logger.warn('Strict rate limit exceeded', {
      clientKey,
      path: req.path,
      method: req.method,
    });

    res.status(429).json({
      error: 'Too Many Requests',
      message: 'Rate limit exceeded for this endpoint.',
      retryAfter: reset / 1000,
    });
    return;
  }

  next();
}

/**
 * Get rate limit statistics (for monitoring)
 */
export function getRateLimitStats() {
  return {
    activeClients: rateLimiter.getClientCount(),
  };
}

