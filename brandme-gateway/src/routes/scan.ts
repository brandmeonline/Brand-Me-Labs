/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Scan Routes
 */

import { Router, Response } from 'express';
import type { Router as IRouter } from 'express';
import { v4 as uuidv4 } from 'uuid';
import { z } from 'zod';
import rateLimit from 'express-rate-limit';
import { AuthenticatedRequest } from '../types';
import { publishEvent } from '../services/nats';
import { logger } from '../config/logger';
import { config } from '../config';

const router: IRouter = Router();

// Rate limiting for scan endpoint
const scanRateLimiter = rateLimit({
  windowMs: config.rateLimitWindow,
  max: config.rateLimitMaxRequests,
  message: 'Too many scan requests, please try again later',
  standardHeaders: true,
  legacyHeaders: false,
});

// Request schema
const scanRequestSchema = z.object({
  garment_tag: z.string().min(1, 'Garment tag is required'),
});

/**
 * POST /scan
 * Initiate garment scan
 */
router.post('/', scanRateLimiter, async (req: AuthenticatedRequest, res: Response) => {
  try {
    // Validate request body
    const { garment_tag } = scanRequestSchema.parse(req.body);

    // Extract user ID from authenticated request
    const scanner_user_id = req.user!.userId;

    // Generate scan ID
    const scan_id = uuidv4();

    // Get region from header or use default
    const region_code = req.headers['x-region'] as string || config.defaultRegion;

    // Get request ID
    const request_id = req.headers['x-request-id'] as string;

    // Prepare event payload
    const eventPayload = {
      scan_id,
      scanner_user_id,
      garment_tag,
      timestamp: new Date().toISOString(),
      region_code,
      request_id,
    };

    // Publish to NATS
    await publishEvent('scan.requested', eventPayload);

    logger.info({
      scan_id,
      scanner_user_id,
      garment_tag,
      region_code,
    }, 'Scan requested');

    // Return 202 Accepted
    res.status(202).json({
      scan_id,
      status: 'processing',
      message: 'Scan request received and is being processed',
    });

  } catch (error) {
    if (error instanceof z.ZodError) {
      res.status(400).json({
        error: 'Validation Error',
        message: 'Invalid request data',
        details: error.errors,
      });
      return;
    }

    logger.error({ error }, 'Error processing scan request');
    res.status(500).json({
      error: 'Internal Server Error',
      message: 'Failed to process scan request',
    });
  }
});

/**
 * GET /scan/:scan_id
 * Get scan status and results
 */
router.get('/:scan_id', async (req: AuthenticatedRequest, res: Response) => {
  const { scan_id } = req.params;

  // TODO: Implement scan status/results retrieval
  // This would query the database or cache for scan results

  res.status(200).json({
    scan_id,
    status: 'processing',
    message: 'Scan results endpoint - implementation pending',
  });
});

export default router;
