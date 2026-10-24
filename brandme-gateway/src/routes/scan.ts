/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Scan Routes (legacy; BM-BASE-005)
 *
 * POST /scan publishes scan.requested to NATS JetStream. Without NATS it
 * answers 503 application/problem+json instead of failing with a 500.
 * GET /scan/:scan_id answers 501: this gateway does not persist scans, so it
 * has no status to report. Errors are spec Problems (no stack, no message).
 * Rate limiting and authentication are mounted in index.ts.
 */

import { Router, Response } from 'express';
import type { Router as IRouter } from 'express';
import { v4 as uuidv4 } from 'uuid';
import { z } from 'zod';
import { AuthenticatedRequest } from '../types';
import { publishEvent } from '../services/nats';
import { logger } from '../config/logger';
import { ApiProblem, handle, problems, resolveRequestId } from '../middleware/problem';
import { regionOf } from '../middleware/requestLogger';

export interface ScanRouterDeps {
  /** NATS_URL is configured (start() connects before listening). */
  natsConfigured: boolean;
  defaultRegion: string;
  publish?: typeof publishEvent;
}

// Request schema
const scanRequestSchema = z.object({
  garment_tag: z.string().min(1, 'Garment tag is required'),
});

export function createScanRouter(deps: ScanRouterDeps): IRouter {
  const router: IRouter = Router();
  const publish = deps.publish ?? publishEvent;

  /**
   * POST /scan
   * Initiate garment scan
   */
  router.post('/', handle(async (req: AuthenticatedRequest, res: Response) => {
    const parsed = scanRequestSchema.safeParse(req.body);
    if (!parsed.success) throw problems.invalid('garment_tag is required.');
    if (!deps.natsConfigured) {
      throw new ApiProblem(503, 'dependency_unavailable', 'Scanning unavailable', 'Scan publishing is not configured in this environment.', false);
    }

    const scan_id = uuidv4();
    const region_code = regionOf(req.headers['x-region'], deps.defaultRegion);
    const eventPayload = {
      scan_id,
      scanner_user_id: req.user!.userId,
      garment_tag: parsed.data.garment_tag,
      timestamp: new Date().toISOString(),
      region_code,
      request_id: resolveRequestId(req, res),
    };

    try {
      await publish('scan.requested', eventPayload);
    } catch {
      throw problems.unavailable('Scan publishing is temporarily unavailable.');
    }

    // Member ID and garment tag stay out of logs (REDACT_PATHS also covers them).
    logger.info({ scan_id, region_code }, 'Scan requested');

    res.status(202).json({
      scan_id,
      status: 'processing',
      message: 'Scan request received and is being processed',
    });
  }));

  /**
   * GET /scan/:scan_id
   * Scans are not persisted here, so there is no status to return.
   */
  router.get('/:scan_id', (_req, _res, next) => {
    next(problems.notImplemented('Scan status is not available: this gateway does not store scan results.'));
  });

  return router;
}
