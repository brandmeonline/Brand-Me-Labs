/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Request Logger Middleware
 */

import { Request, Response, NextFunction } from 'express';
import { v4 as uuidv4 } from 'uuid';
import { logger } from '../config/logger';

export function requestLogger(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  // Generate request ID if not present
  const requestId = req.headers['x-request-id'] || uuidv4();
  req.headers['x-request-id'] = requestId as string;

  // Attach region header
  const regionCode = req.headers['x-region'] || process.env.DEFAULT_REGION || 'us-east1';
  req.headers['x-region'] = regionCode as string;

  const start = Date.now();

  // Log incoming request
  logger.info({
    requestId,
    method: req.method,
    path: req.path,
    regionCode,
    userAgent: req.headers['user-agent'],
  }, 'Incoming request');

  // Log response when finished
  res.on('finish', () => {
    const duration = Date.now() - start;

    logger.info({
      requestId,
      method: req.method,
      path: req.path,
      statusCode: res.statusCode,
      duration,
      regionCode,
    }, 'Request completed');
  });

  next();
}
