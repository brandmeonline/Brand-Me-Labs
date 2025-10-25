/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Brand.Me Chain Service
 * ======================
 * Blockchain integration for Cardano and Midnight chains
 * - TX Builder for both chains
 * - Cross-chain verification
 * - Secure wallet management
 */

import express from 'express';
import helmet from 'helmet';
import cors from 'cors';
import { config } from './config';
import { logger } from './config/logger';
import { errorHandler } from './middleware/errorHandler';
import { requestLogger} from './middleware/requestLogger';
import txRouter from './routes/tx';
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

// Routes
app.use('/health', healthRouter);
app.use('/tx', txRouter);

// Error handling
app.use(errorHandler);

// Start server
async function start() {
  try {
    const port = config.port;
    app.listen(port, () => {
      logger.info(`Brand.Me Chain Service listening on port ${port}`);
      logger.info(`Environment: ${config.environment}`);
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
