/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Request Logger Middleware
 */

import { Request, Response, NextFunction } from 'express';
import { randomUUID } from 'node:crypto';
import { logger } from '../config/logger.js';

export function requestLogger(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const requestId = req.headers['x-request-id'] || randomUUID();
  req.headers['x-request-id'] = requestId as string;

  const start = Date.now();

  logger.info({
    requestId,
    method: req.method,
    path: req.path,
  }, 'Incoming request');

  res.on('finish', () => {
    const duration = Date.now() - start;

    logger.info({
      requestId,
      method: req.method,
      path: req.path,
      statusCode: res.statusCode,
      duration,
    }, 'Request completed');
  });

  next();
}
