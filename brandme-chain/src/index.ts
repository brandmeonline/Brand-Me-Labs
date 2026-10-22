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
import { createOperationsRouter } from './routes/operations.js';
import { operationDatabase, SpannerOperationStore } from './midnight/spanner-store.js';
import { IndexerTransactionLookup, OperationReconciler } from './midnight/reconciler.js';
import { FinalizedEntitlementProjector, IndexerFinalizedLedgerReader } from './midnight/projection.js';
import { SpannerReconciliationQueue } from './midnight/reconciliation-queue.js';
import { ReconciliationWorker } from './midnight/reconciliation-worker.js';
import { NodeRpcFinalityOracle } from './midnight/adapter.js';
import { resolveEndpoints } from './midnight/capability.js';
import { midnightCapability } from './midnight/capability.js';

const app = express();
app.use(helmet());
app.use(cors({ origin: config.corsOrigins, credentials: true }));
app.use(express.json({ limit: '256kb' }));
app.use(requestLogger);

app.use('/health', healthRouter);
app.use('/midnight', midnightRouter);
const database = config.spannerProjectId && config.spannerInstanceId && config.spannerDatabaseId
  ? operationDatabase(config.spannerProjectId, config.spannerInstanceId, config.spannerDatabaseId) : undefined;
const store = database ? new SpannerOperationStore(database, config.environment) : undefined;
const endpoints = resolveEndpoints(config);
const finality = endpoints ? new NodeRpcFinalityOracle(endpoints.nodeRpc) : undefined;
const reconciler = store && endpoints && config.midnightContractAddress ? new OperationReconciler({
  store, endpoints, contractAddress: config.midnightContractAddress,
  lookup: new IndexerTransactionLookup(endpoints), finality: finality!,
}) : undefined;
const worker = config.chainReconciliationEnabled !== false && store && reconciler && finality && endpoints &&
  config.midnightContractAddress && config.midnightNetwork !== 'mainnet' ? new ReconciliationWorker({
    network: config.midnightNetwork, contractAddress: config.midnightContractAddress, store, reconciler,
    queue: new SpannerReconciliationQueue(store),
    projector: new FinalizedEntitlementProjector({ network: config.midnightNetwork, contractAddress: config.midnightContractAddress,
      finality, reader: new IndexerFinalizedLedgerReader(endpoints) }),
    report: (counts) => { if (counts.processed || counts.errors) logger.info(counts, 'chain reconciliation batch'); },
  }) : undefined;
app.use('/midnight', createOperationsRouter({ token: config.chainServiceToken, store, reconciler,
  network: config.midnightNetwork, contractAddress: config.midnightContractAddress }));

// Retired: these returned simulated hashes and a hardcoded "consistent" result.
app.all(['/tx/anchor-scan', '/tx/verify-root'], (_req, res) => {
  res.status(410).json({
    error: 'Gone',
    message: 'Simulated dual-chain anchoring was removed. Rights operations use the Midnight adapter; see GET /midnight/capability.',
  });
});

app.use(errorHandler);

try { await store?.initialize(); }
catch { logger.fatal('operation database unavailable or V012 migration missing'); await database?.close(); process.exit(1); }

const cap = midnightCapability(config);
if (worker && !cap.artifacts.verified) {
  logger.fatal('reconciliation requires verified compiled contract artifacts');
  await database?.close();
  process.exit(1);
}
logger.info({ network: cap.network, status: cap.status, reasons: cap.reasons }, 'Midnight capability');
const server = app.listen(config.port, () => logger.info(`Brand.Me Chain Service listening on port ${config.port}`));
worker?.start();
logger.info({ enabled: Boolean(worker) }, 'read-only reconciliation worker');

let closing = false;
const shutdown = () => {
  if (closing) return;
  closing = true;
  logger.info('shutting down');
  const httpClosed = new Promise<void>((resolve) => server.close(() => resolve()));
  void Promise.all([httpClosed, worker?.stop()]).then(() => database?.close()).then(() => process.exit(0), () => process.exit(1));
  setTimeout(() => process.exit(1), 10_000).unref();
};
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
