/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Brand.Me Gateway
 * ================
 * Edge API gateway for Brand.Me platform
 * - OAuth authentication
 * - Rate limiting
 * - NATS event publishing
 * - Request routing
 */

import express from 'express';
import helmet from 'helmet';
import cors from 'cors';
import { config } from './config';
import { logger } from './config/logger';
import { connectNATS } from './services/nats';
import { errorHandler } from './middleware/errorHandler';
import { requestLogger } from './middleware/requestLogger';
import { authMiddleware } from './middleware/auth';
import { rateLimiterMiddleware, strictRateLimiterMiddleware } from './middleware/rateLimiter';
import scanRouter from './routes/scan';
import healthRouter from './routes/health';

const app = express();

// Security middleware
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      scriptSrc: ["'self'"],
      imgSrc: ["'self'", "data:", "https:"],
    },
  },
}));

// CORS configuration - secure and configurable
const allowedOrigins = config.corsOrigins.split(',').filter(Boolean);
app.use(cors({
  origin: (origin, callback) => {
    // Allow requests with no origin (mobile apps, curl, etc.)
    if (!origin) {
      return callback(null, true);
    }
    
    // Check if origin is allowed
    if (allowedOrigins.includes(origin) || allowedOrigins.includes('*')) {
      callback(null, true);
    } else {
      logger.warn('CORS blocked origin', { origin, allowed: allowedOrigins });
      callback(new Error('Not allowed by CORS'));
    }
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-Request-Id', 'X-Region'],
  exposedHeaders: ['X-Request-Id', 'X-RateLimit-Limit', 'X-RateLimit-Remaining'],
  maxAge: 86400, // 24 hours
}));

// Body parsing
app.use(express.json({ limit: '1mb' })); // Limit JSON payload
app.use(express.urlencoded({ extended: true, limit: '1mb' }));

// Request logging
app.use(requestLogger);

// Global rate limiting
app.use(rateLimiterMiddleware);

// Health check (no auth, no rate limit)
app.use('/healthz', healthRouter);
app.use('/health', healthRouter);

// Authenticated routes with rate limiting
app.use('/scan', strictRateLimiterMiddleware, authMiddleware, scanRouter);

// Error handling
app.use(errorHandler);

// Start server
async function start() {
  try {
    // Connect to NATS
    await connectNATS();
    logger.info('Connected to NATS');

    // Start HTTP server
    const port = config.port;
    app.listen(port, () => {
      logger.info(`Brand.Me Gateway listening on port ${port}`);
      logger.info(`Environment: ${config.environment}`);
      logger.info(`Default region: ${config.defaultRegion}`);
    });
  } catch (error) {
    logger.error('Failed to start server:', error);
    process.exit(1);
  }
}

// Graceful shutdown
process.on('SIGTERM', async () => {
  logger.info('SIGTERM received, shutting down gracefully');
  process.exit(0);
});

process.on('SIGINT', async () => {
  logger.info('SIGINT received, shutting down gracefully');
  process.exit(0);
});

start();
