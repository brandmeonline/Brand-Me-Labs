/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Request context (X-Request-Id, X-Brandme-Environment) and
 * application/problem+json errors for /api/v1. Stack traces and provider
 * bodies are never sent.
 */

import { randomUUID } from 'node:crypto';
import type { NextFunction, Request, Response } from 'express';
import { logger } from '../config/logger';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export class ApiProblem extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly title: string,
    public readonly detail: string,
    public readonly retryable = false,
    public readonly extra: Record<string, unknown> = {},
  ) {
    super(detail);
    this.name = 'ApiProblem';
  }
}

export const problems = {
  unauthenticated: () => new ApiProblem(401, 'unauthenticated', 'Sign-in required', 'A valid session or bearer token is required.'),
  forbidden: (detail = 'This action is not permitted.') => new ApiProblem(403, 'forbidden', 'Forbidden', detail),
  csrf: () => new ApiProblem(403, 'csrf_failed', 'Request origin not verified', 'State-changing requests need a matching X-CSRF-Token and an allowed Origin.'),
  notFound: () => new ApiProblem(404, 'not_found', 'Not found', 'The resource does not exist or is not visible to you.'),
  conflict: (detail: string, extra: Record<string, unknown> = {}) => new ApiProblem(409, 'revision_conflict', 'Revision conflict', detail, false, extra),
  preconditionRequired: () => new ApiProblem(428, 'if_match_required', 'If-Match required', 'Send If-Match with the current revision.'),
  invalid: (detail: string) => new ApiProblem(422, 'invalid_request', 'Invalid request', detail),
  unavailable: (detail: string) => new ApiProblem(503, 'dependency_unavailable', 'Temporarily unavailable', detail, true),
};

export function requestContext(environment: string) {
  return (req: Request, res: Response, next: NextFunction): void => {
    const incoming = req.header('x-request-id');
    const requestId = incoming && UUID_RE.test(incoming) ? incoming : randomUUID();
    res.locals.requestId = requestId;
    res.setHeader('X-Request-Id', requestId);
    res.setHeader('X-Brandme-Environment', environment);
    res.setHeader('Cache-Control', 'private, no-store');
    next();
  };
}

export function sendProblem(res: Response, req: Request, p: ApiProblem): void {
  res
    .status(p.status)
    .type('application/problem+json')
    .send(
      JSON.stringify({
        type: `https://brand.me/problems/${p.code}`,
        title: p.title,
        status: p.status,
        code: p.code,
        detail: p.detail,
        instance: req.originalUrl.split('?')[0].slice(0, 256),
        request_id: res.locals.requestId ?? randomUUID(),
        retryable: p.retryable,
        ...p.extra,
      }),
    );
}

export function problemHandler(err: unknown, req: Request, res: Response, _next: NextFunction): void {
  if (err instanceof ApiProblem) return sendProblem(res, req, err);
  if (err instanceof SyntaxError && 'body' in (err as object)) {
    return sendProblem(res, req, problems.invalid('Request body is not valid JSON.'));
  }
  logger.error({ requestId: res.locals.requestId, errName: (err as Error)?.name, path: req.path }, 'unhandled api error');
  sendProblem(res, req, new ApiProblem(500, 'internal_error', 'Internal error', 'An unexpected error occurred.', true));
}

/** Wrap async handlers so rejections reach the problem handler. */
export const handle =
  <T extends Request>(fn: (req: T, res: Response) => Promise<void>) =>
  (req: Request, res: Response, next: NextFunction) =>
    fn(req as T, res).catch(next);
