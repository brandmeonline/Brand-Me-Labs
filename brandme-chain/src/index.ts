/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Brand.Me Chain Service
 * ======================
 * Midnight rights network adapter (primary). Optional Cardano anchoring is a
 * separate adapter and never gates the Midnight path.
 */

import express from 'express';
import helmet from 'helmet';
import cors from 'cors';
import { config } from './config/index.js';
import { logger } from './config/logger.js';
import { errorHandler } from './middleware/errorHandler.js';
import { requestLogger } from './middleware/requestLogger.js';
import healthRouter from './routes/health.js';
import midnightRouter from './routes/midnight.js';
import { midnightCapability } from './midnight/capability.js';

const app = express();
app.use(helmet());
app.use(cors({ origin: config.corsOrigins, credentials: true }));
app.use(express.json({ limit: '256kb' }));
app.use(requestLogger);

app.use('/health', healthRouter);
app.use('/midnight', midnightRouter);

// Retired: these returned simulated hashes and a hardcoded "consistent" result.
app.all(['/tx/anchor-scan', '/tx/verify-root'], (_req, res) => {
  res.status(410).json({
    error: 'Gone',
    message: 'Simulated dual-chain anchoring was removed. Rights operations use the Midnight adapter; see GET /midnight/capability.',
  });
});

app.use(errorHandler);

const cap = midnightCapability(config);
logger.info({ network: cap.network, status: cap.status, reasons: cap.reasons }, 'Midnight capability');
app.listen(config.port, () => logger.info(`Brand.Me Chain Service listening on port ${config.port}`));

const shutdown = () => { logger.info('shutting down'); process.exit(0); };
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
