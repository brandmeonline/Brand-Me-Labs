/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Error Handler Middleware
 */

import { Request, Response, NextFunction } from 'express';
import { logger } from '../config/logger';

export function errorHandler(
  err: Error,
  req: Request,
  res: Response,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  next: NextFunction
): void {
  logger.error({
    err,
    path: req.path,
    method: req.method,
  }, 'Error handling request');

  res.status(500).json({
    error: 'Internal Server Error',
    message: 'An unexpected error occurred',
  });
}
