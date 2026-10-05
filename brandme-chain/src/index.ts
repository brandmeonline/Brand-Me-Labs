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
import { config } from './config/index.js';
import { logger } from './config/logger.js';
import { errorHandler } from './middleware/errorHandler.js';
import { requestLogger} from './middleware/requestLogger.js';
import txRouter from './routes/tx.js';
import healthRouter from './routes/health.js';
import { initCardanoWallet } from './services/cardano-wallet.js';
import { initCardanoTxBuilder } from './services/cardano-tx-builder.js';
import { initMidnightClient } from './services/midnight-client.js';

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
    logger.info('Initializing Brand.Me Chain Service...');

    // Initialize Cardano wallet and TX builder
    if (config.cardanoMnemonicPath || config.cardanoWalletPath) {
      logger.info('Initializing Cardano wallet...');
      initCardanoWallet({
        network: config.cardanoNetwork,
        mnemonicPath: config.cardanoMnemonicPath,
        privateKeyPath: config.cardanoWalletPath,
      });

      if (config.blockfrostApiKey) {
        logger.info('Initializing Cardano TX Builder with Blockfrost...');
        initCardanoTxBuilder(config.blockfrostApiKey, config.cardanoNetwork);
      } else {
        logger.warn('Blockfrost API key not provided - Cardano transactions will use fallback mode');
      }
    } else {
      logger.warn('Cardano wallet not configured - using fallback mode');
    }

    // Initialize Midnight client
    logger.info('Initializing Midnight client...');
    initMidnightClient({
      network: config.midnightNetwork,
      walletPath: config.midnightWalletPath,
      rpcUrl: config.midnightRpcUrl,
    });

    // Start HTTP server
    const port = config.port;
    app.listen(port, () => {
      logger.info(`Brand.Me Chain Service listening on port ${port}`);
      logger.info(`Environment: ${config.environment}`);
      logger.info(`Cardano Network: ${config.cardanoNetwork}`);
      logger.info(`Midnight Network: ${config.midnightNetwork}`);
      logger.info(`Cardano Fallback Mode: ${config.cardanoFallbackMode}`);
      logger.info(`Midnight Fallback Mode: ${config.midnightFallbackMode}`);
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
