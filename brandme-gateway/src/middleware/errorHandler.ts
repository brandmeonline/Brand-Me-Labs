/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Error Handler Middleware (app level: legacy /scan and anything outside
 * /api/v1, which has its own problemHandler). Every error leaves as an
 * application/problem+json spec Problem; stack traces, error messages and
 * request bodies are neither sent nor logged.
 */

import { Request, Response, NextFunction } from 'express';
import { ZodError } from 'zod';
import { ApiProblem, problemHandler, problems } from './problem';

export class AppError extends Error {
  constructor(
    public statusCode: number,
    public message: string,
    public isOperational = true
  ) {
    super(message);
    Object.setPrototypeOf(this, AppError.prototype);
  }
}

export function errorHandler(
  err: Error,
  req: Request,
  res: Response,
  next: NextFunction
): void {
  if (err instanceof ZodError) {
    return problemHandler(problems.invalid('The request data is invalid.'), req, res, next);
  }
  if (err instanceof AppError && err.statusCode >= 400 && err.statusCode <= 599) {
    return problemHandler(new ApiProblem(err.statusCode, 'request_failed', 'Request failed', 'The request could not be completed.', err.statusCode >= 500), req, res, next);
  }
  problemHandler(err, req, res, next);
}
