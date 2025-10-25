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
import scanRouter from './routes/scan';
import healthRouter from './routes/health';

const app = express();

// Security middleware
app.use(helmet());
app.use(cors({
  origin: config.corsOrigins,
  credentials: true,
}));

// Body parsing
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Request logging
app.use(requestLogger);

// Health check (no auth required)
app.use('/healthz', healthRouter);
app.use('/health', healthRouter);

// Authenticated routes
app.use('/scan', authMiddleware, scanRouter);

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
