/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Request Logger Middleware
 *
 * Logs carry only gateway-controlled values (ch.03 §9):
 *   - the request ID from resolveRequestId (an inbound X-Request-Id is used
 *     only when it is a UUID, exactly as requestContext accepts it);
 *   - the path with identifier segments templated (logPath.ts), no query;
 *   - a region code only when it has the shape of a region (us-east1).
 * User agents and other free-form client headers are not logged.
 */

import { Request, Response, NextFunction } from 'express';
import { logger } from '../config/logger';
import { templatePath } from './logPath';
import { resolveRequestId } from './problem';

const REGION_RE = /^[a-z]{2,12}-[a-z]{2,16}[0-9]{1,2}$/;

export function regionOf(header: string | string[] | undefined, fallback: string): string {
  const value = Array.isArray(header) ? header[0] : header;
  return value && REGION_RE.test(value) ? value : fallback;
}

export function requestLogger(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const requestId = resolveRequestId(req, res);

  // Region header: normalized so legacy readers never see arbitrary text.
  const regionCode = regionOf(req.headers['x-region'], regionOf(process.env.DEFAULT_REGION, 'us-east1'));
  req.headers['x-region'] = regionCode;

  // Captured now: req.url is rewritten while sub-routers run.
  const path = templatePath(req.originalUrl);
  const start = Date.now();

  logger.info({
    requestId,
    method: req.method,
    path,
    regionCode,
  }, 'Incoming request');

  res.on('finish', () => {
    logger.info({
      requestId,
      method: req.method,
      path,
      statusCode: res.statusCode,
      duration: Date.now() - start,
      regionCode,
    }, 'Request completed');
  });

  next();
}
