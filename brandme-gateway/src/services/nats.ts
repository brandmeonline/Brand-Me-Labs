/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * NATS JetStream Service
 */

import { connect, NatsConnection, JetStreamClient, JetStreamManager } from 'nats';
import { config } from '../config';
import { logger } from '../config/logger';

let natsConnection: NatsConnection | null = null;
let jetStream: JetStreamClient | null = null;

/**
 * Connect to NATS and setup JetStream
 */
export async function connectNATS(): Promise<void> {
  try {
    logger.info({ url: config.natsUrl }, 'Connecting to NATS...');

    natsConnection = await connect({
      servers: config.natsUrl,
      name: 'brandme-gateway',
      maxReconnectAttempts: config.natsMaxReconnectAttempts,
      reconnect: true,
      reconnectTimeWait: 1000,
      reconnectJitter: 100,
    });

    logger.info('Connected to NATS');

    // Setup JetStream
    jetStream = natsConnection.jetstream();

    // Setup stream if it doesn't exist
    const jsm: JetStreamManager = await natsConnection.jetstreamManager();

    try {
      await jsm.streams.info('SCANS');
      logger.info('JetStream stream "SCANS" already exists');
    } catch {
      // Stream doesn't exist, create it
      await jsm.streams.add({
        name: 'SCANS',
        subjects: ['scan.*'],
        retention: 'workqueue' as any, // RetentionPolicy enum
        max_age: 7 * 24 * 60 * 60 * 1_000_000_000, // 7 days in nanoseconds
        storage: 'file' as any, // StorageType enum
      });
      logger.info('Created JetStream stream "SCANS"');
    }

    // Handle connection events
    (async () => {
      for await (const status of natsConnection!.status()) {
        logger.info({ status: status.type }, 'NATS connection status');
      }
    })().catch((err) => {
      logger.error({ err }, 'NATS status error');
    });

  } catch (error) {
    logger.error({ error }, 'Failed to connect to NATS');
    throw error;
  }
}

/**
 * Publish event to NATS JetStream
 */
export async function publishEvent(
  subject: string,
  data: Record<string, unknown>
): Promise<void> {
  if (!jetStream) {
    throw new Error('JetStream not initialized');
  }

  try {
    const payload = JSON.stringify(data);
    await jetStream.publish(subject, new TextEncoder().encode(payload));

    logger.debug({ subject, data }, 'Published event to NATS');
  } catch (error) {
    logger.error({ error, subject }, 'Failed to publish event to NATS');
    throw error;
  }
}

/**
 * Close NATS connection
 */
export async function closeNATS(): Promise<void> {
  if (natsConnection) {
    await natsConnection.close();
    natsConnection = null;
    jetStream = null;
    logger.info('NATS connection closed');
  }
}
