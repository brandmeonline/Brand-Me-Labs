// Typed client generated from OpenAPI (openapi-fetch over generated/api.d.ts).
// Conventions:
// - wire fields are snake_case; no renaming happens in the client
// - mutations that need Idempotency-Key / If-Match take them as typed header params
// - errors are application/problem+json, surfaced as BrandmeApiError
import createClient, { type Middleware } from 'openapi-fetch';
import type { paths, components } from '../generated/api.ts';

type Problem = components['schemas']['Problem'];

export class BrandmeApiError extends Error {
  readonly status: number;
  readonly problem: Problem | null;
  constructor(status: number, problem: Problem | null) {
    super(problem ? `${problem.code}: ${problem.title}` : `HTTP ${status}`);
    this.name = 'BrandmeApiError';
    this.status = status;
    this.problem = problem;
  }
}

export interface BrandmeClientOptions {
  /** e.g. http://localhost:3001/api/v1 (gateway) or /api/v1 (same-origin BFF) */
  baseUrl: string;
  /** Read for every state-changing request; sent as X-CSRF-Token. */
  csrfToken?: () => string | undefined;
  fetch?: typeof globalThis.fetch;
  /** Server-side callers forward the cookie explicitly. */
  headers?: Record<string, string>;
}

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export function createBrandmeClient(options: BrandmeClientOptions) {
  const client = createClient<paths>({
    baseUrl: options.baseUrl,
    credentials: 'include',
    fetch: options.fetch,
    headers: options.headers,
  });
  const csrf: Middleware = {
    onRequest({ request }) {
      const token = options.csrfToken?.();
      if (token && UNSAFE.has(request.method)) request.headers.set('X-CSRF-Token', token);
      return request;
    },
  };
  client.use(csrf);
  return client;
}

export type BrandmeClient = ReturnType<typeof createBrandmeClient>;

/** Unwrap an openapi-fetch result, throwing BrandmeApiError on problem responses. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.response.ok && result.data !== undefined) return result.data;
  if (result.response.ok && result.response.status === 204) return undefined as T;
  throw new BrandmeApiError(result.response.status, (result.error as Problem | undefined) ?? null);
}
