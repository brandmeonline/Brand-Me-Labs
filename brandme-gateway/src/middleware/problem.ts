/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Request context (X-Request-Id, X-Brandme-Environment) and
 * application/problem+json errors for /api/v1. Stack traces and provider
 * bodies are never sent.
 *
 * Problem bodies carry exactly the members of the spec Problem
 * (docs/design/brandme/contracts/domain.schema.json $defs.Problem, which has
 * additionalProperties:false): type, title, status, code, detail, instance,
 * request_id, retryable. There is no extension member. Metadata a client needs
 * travels in response headers instead (ETag on 409, Retry-After on 429).
 */

import { randomUUID } from 'node:crypto';
import type { NextFunction, Request, Response } from 'express';
import { logger } from '../config/logger';
import { requestPath, templatePath } from './logPath';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const CODE_RE = /^[a-z][a-z0-9_]{0,79}$/;
const TITLE_MAX = 200;
const DETAIL_MAX = 1000;
const INSTANCE_MAX = 256;

export class ApiProblem extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly title: string,
    public readonly detail: string,
    public readonly retryable = false,
    /**
     * Kept for the signature lane routes already use (main before 2026-10-24
     * spread these into the body). The spec Problem allows no extension
     * members, so they are never sent; sendProblem logs the dropped keys.
     */
    public readonly extra: Record<string, unknown> = {},
    /** Response headers sent with the problem (ETag on 409, Retry-After on 429). */
    public readonly headers: Readonly<Record<string, string>> = {},
  ) {
    super(detail);
    this.name = 'ApiProblem';
    // Refuse values the spec Problem cannot carry instead of emitting an invalid body.
    if (!Number.isInteger(status) || status < 400 || status > 599) throw new TypeError(`problem status must be 400-599, got ${status}`);
    if (!CODE_RE.test(code)) throw new TypeError(`problem code must match ${CODE_RE}`);
  }
}

export const problems = {
  unauthenticated: () => new ApiProblem(401, 'unauthenticated', 'Sign-in required', 'A valid session or bearer token is required.'),
  forbidden: (detail = 'This action is not permitted.') => new ApiProblem(403, 'forbidden', 'Forbidden', detail),
  csrf: () => new ApiProblem(403, 'csrf_failed', 'Request origin not verified', 'State-changing requests need a matching X-CSRF-Token and an allowed Origin.'),
  notFound: () => new ApiProblem(404, 'not_found', 'Not found', 'The resource does not exist or is not visible to you.'),
  /** The current revision goes in the ETag header (quoted, as If-Match expects), not the body. */
  conflict: (detail: string, currentRevision?: number | string) =>
    new ApiProblem(409, 'revision_conflict', 'Revision conflict', detail, false, {}, currentRevision === undefined ? {} : { ETag: `"${currentRevision}"` }),
  preconditionRequired: () => new ApiProblem(428, 'if_match_required', 'If-Match required', 'Send If-Match with the current revision.'),
  invalid: (detail: string) => new ApiProblem(422, 'invalid_request', 'Invalid request', detail),
  rateLimited: (retryAfterSeconds: number) =>
    new ApiProblem(429, 'rate_limited', 'Too many requests', `Rate limit exceeded. Retry after ${retryAfterSeconds} seconds.`, true, {}, {
      'Retry-After': String(retryAfterSeconds),
    }),
  notImplemented: (detail: string) => new ApiProblem(501, 'not_implemented', 'Not implemented', detail),
  unavailable: (detail: string) => new ApiProblem(503, 'dependency_unavailable', 'Temporarily unavailable', detail, true),
};

/**
 * The request's ID, resolved once: an inbound X-Request-Id is accepted only if
 * it is a UUID; anything else is replaced. Sets res.locals.requestId, the
 * X-Request-Id response header and the normalized request header (legacy
 * routes read it).
 */
export function resolveRequestId(req: Request, res: Response): string {
  const known = res.locals.requestId;
  if (typeof known === 'string') return known;
  const incoming = req.header('x-request-id');
  const requestId = incoming && UUID_RE.test(incoming) ? incoming : randomUUID();
  res.locals.requestId = requestId;
  req.headers['x-request-id'] = requestId;
  res.setHeader('X-Request-Id', requestId);
  return requestId;
}

export function requestContext(environment: string) {
  return (req: Request, res: Response, next: NextFunction): void => {
    resolveRequestId(req, res);
    res.setHeader('X-Brandme-Environment', environment);
    res.setHeader('Cache-Control', 'private, no-store');
    next();
  };
}

const bounded = (text: string, max: number, fallback: string) => {
  const t = text.trim() || fallback;
  return t.length > max ? `${t.slice(0, max - 1)}…` : t;
};

/** The spec Problem body: exactly its eight members, within its length bounds. */
export function problemBody(req: Request, res: Response, p: ApiProblem) {
  return {
    type: `https://brand.me/problems/${p.code}`,
    title: bounded(p.title, TITLE_MAX, 'Error'),
    status: p.status,
    code: p.code,
    detail: bounded(p.detail, DETAIL_MAX, p.title),
    instance: requestPath(req).slice(0, INSTANCE_MAX),
    request_id: resolveRequestId(req, res),
    retryable: p.retryable,
  };
}

export function sendProblem(res: Response, req: Request, p: ApiProblem): void {
  const body = problemBody(req, res, p);
  const dropped = Object.keys(p.extra);
  if (dropped.length) {
    // Loud, not silent: a route still relies on body extensions the contract forbids.
    logger.warn({ requestId: body.request_id, code: p.code, droppedMembers: dropped }, 'problem extension members dropped (spec Problem has none; use a header)');
  }
  for (const [name, value] of Object.entries(p.headers)) res.setHeader(name, value);
  if (!res.getHeader('Cache-Control')) res.setHeader('Cache-Control', 'no-store');
  res.status(p.status).type('application/problem+json').send(JSON.stringify(body));
}

/** body-parser marks client errors (oversized, unreadable) as expose:true 4xx. */
function clientBodyError(err: unknown): ApiProblem | undefined {
  const e = err as { expose?: unknown; status?: unknown; type?: unknown } | null;
  if (!e || e.expose !== true || typeof e.status !== 'number' || e.status < 400 || e.status > 499) return undefined;
  if (e.type === 'entity.too.large') return new ApiProblem(413, 'payload_too_large', 'Request too large', 'The request body exceeds the size limit.');
  return new ApiProblem(e.status, 'invalid_request', 'Invalid request', 'The request body could not be read.');
}

export function problemHandler(err: unknown, req: Request, res: Response, next: NextFunction): void {
  if (res.headersSent) return next(err);
  if (err instanceof ApiProblem) return sendProblem(res, req, err);
  if (err instanceof SyntaxError && 'body' in (err as object)) {
    return sendProblem(res, req, problems.invalid('Request body is not valid JSON.'));
  }
  const bodyError = clientBodyError(err);
  if (bodyError) return sendProblem(res, req, bodyError);
  logger.error({ requestId: res.locals.requestId, errName: (err as Error)?.name, path: templatePath(req.originalUrl) }, 'unhandled api error');
  sendProblem(res, req, new ApiProblem(500, 'internal_error', 'Internal error', 'An unexpected error occurred.', true));
}

/** Wrap async handlers so rejections reach the problem handler. */
export const handle =
  <T extends Request>(fn: (req: T, res: Response) => Promise<void>) =>
  (req: Request, res: Response, next: NextFunction) =>
    fn(req as T, res).catch(next);
