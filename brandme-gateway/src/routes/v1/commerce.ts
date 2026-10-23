/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1/commerce — UNMOUNTED router (lane: opus-commerce-agents).
 *
 * Built on foundation's /api/v1 conventions: the principal comes from
 * `res.locals.principal` (session cookie or verified bearer, set by
 * `principalMiddleware`), errors are `ApiProblem` → application/problem+json.
 * Identity is never read from the body or query. All domain decisions (quote
 * hashing, approvals, budgets, delegation resolution, provider submission)
 * happen in the Python commerce domain; this layer checks shape, rejects
 * identity fields, gates obvious authority, and forwards the principal in a
 * gateway-signed assertion (`createHttpCommerceDomainClient`).
 *
 * Authority split:
 * - A first-party session (`via: 'session'`, no delegation) is the member on
 *   Brand.Me's own UI. It acts with the member's authority; `commerce:*` scopes
 *   gate delegated clients, not the member.
 * - Bearer callers are agents. They need the commerce scope here; the domain
 *   also requires it in their one active grant for (member, client).
 * - Operator roles (`provider:admin`) are always required, for everyone.
 */

import { randomUUID } from 'node:crypto';
import { Router, type NextFunction, type Request, type Response } from 'express';
import { SignJWT, type KeyLike } from 'jose';
import { z } from 'zod';
import { ApiProblem, handle, problems } from '../../middleware/problem';
import type { Principal } from '../../types';

export interface DomainResult {
  status: number;
  body: unknown;
  headers?: Record<string, string>;
}

export interface CommerceDomainClient {
  call(
    operation: string,
    principal: Principal,
    body: unknown,
    options?: { idempotencyKey?: string; ifMatch?: string },
  ): Promise<DomainResult>;
  /** Provider webhook relay: no principal; the domain verifies the provider's signature. */
  webhook(providerId: string, headers: Record<string, string>, rawBody: Buffer): Promise<DomainResult>;
}

/** Fields that would claim identity, authority or approval. Never accepted from a request. */
const IDENTITY_FIELDS = ['user_id', 'member_id', 'principal', 'owner_id', 'approved', 'scopes', 'subject', 'session_id'];

export const principalOf = (res: Response): Principal | undefined => res.locals.principal as Principal | undefined;

export const isFirstParty = (p: Principal): boolean =>
  p.via === 'session' && p.sessionId !== null && p.delegationId === null;

function insufficientScope(scopes: string[]): ApiProblem {
  return new ApiProblem(403, 'insufficient_scope', 'Additional scope required', `This call needs: ${scopes.join(' ')}.`,
    false, { required_scopes: scopes });
}

/** Delegated clients need the scope; the member's own session acts with the member's authority. */
export function requireAgentScope(...scopes: string[]) {
  return (_req: Request, res: Response, next: NextFunction): void => {
    const p = principalOf(res);
    if (!p) return next(problems.unauthenticated());
    if (isFirstParty(p)) return next();
    if (scopes.some((s) => !p.scopes.includes(s))) {
      res.setHeader('WWW-Authenticate', `Bearer error="insufficient_scope", scope="${scopes.join(' ')}"`);
      return next(insufficientScope(scopes));
    }
    next();
  };
}

/** Operator roles are never implied by a member session. */
export function requireRole(scope: string) {
  return (_req: Request, res: Response, next: NextFunction): void => {
    const p = principalOf(res);
    if (!p) return next(problems.unauthenticated());
    if (!p.scopes.includes(scope)) return next(insufficientScope([scope]));
    next();
  };
}

/** Trusted approval surface: the member's first-party session only — never an agent or MCP client. */
export function requireTrustedSurface(_req: Request, res: Response, next: NextFunction): void {
  const p = principalOf(res);
  if (!p) return next(problems.unauthenticated());
  if (!isFirstParty(p)) {
    return next(new ApiProblem(403, 'not_trusted_surface', 'Not the trusted surface',
      'Grants and approvals are only accepted from your own Brand.Me session.'));
  }
  next();
}

export function rejectIdentityFields(req: Request, _res: Response, next: NextFunction): void {
  const body = req.body && typeof req.body === 'object' && !Buffer.isBuffer(req.body) ? (req.body as Record<string, unknown>) : {};
  const query = req.query as Record<string, unknown>;
  if (IDENTITY_FIELDS.some((f) => f in body || f in query)) {
    return next(new ApiProblem(400, 'identity_argument_rejected', 'Identity comes from sign-in',
      'Identity, scope and approval come from authentication, not request fields.'));
  }
  next();
}

export function validate<T extends z.ZodTypeAny>(schema: T, source: 'body' | 'query' = 'body') {
  return (req: Request, res: Response, next: NextFunction): void => {
    const parsed = schema.safeParse(source === 'body' ? (req.body ?? {}) : req.query);
    if (!parsed.success) return next(problems.invalid(parsed.error.issues[0]?.message ?? 'invalid request'));
    res.locals.input = parsed.data;
    next();
  };
}

/** Foundation contract: 16-128 characters, scoped by the domain to principal + operation + environment. */
export function requireIdempotencyKey(req: Request, _res: Response, next: NextFunction): void {
  const key = req.get('Idempotency-Key');
  if (!key || key.length < 16 || key.length > 128) {
    return next(new ApiProblem(400, 'idempotency_key_required', 'Idempotency-Key required',
      'Send an Idempotency-Key header of 16-128 characters.'));
  }
  next();
}

export function requireIfMatch(req: Request, _res: Response, next: NextFunction): void {
  if (!req.get('If-Match')) return next(problems.preconditionRequired());
  next();
}

const PROBLEM_CORE = new Set(['type', 'title', 'status', 'code', 'detail', 'instance', 'request_id', 'retryable']);

type DomainProblem = { code?: string; title?: string; detail?: string; retryable?: boolean } & Record<string, unknown>;

/** Map a domain problem onto foundation's problem shape; a refused gateway assertion is our fault, not the caller's. */
export function domainProblem(result: DomainResult): ApiProblem {
  const body = (result.body ?? {}) as DomainProblem;
  if (result.status === 401) return problems.unavailable('The commerce service is unavailable.');
  const { code, title, detail, retryable } = body;
  // Keep domain extras (e.g. current_version); the gateway sets its own type/status/instance/request_id.
  const extra = Object.fromEntries(Object.entries(body).filter(([k]) => !PROBLEM_CORE.has(k)));
  return new ApiProblem(result.status, code ?? 'commerce_error', title ?? 'Commerce request refused',
    detail ?? 'The commerce service refused this request.', retryable ?? (result.status === 429 || result.status === 503),
    extra);
}

export function forward(client: CommerceDomainClient, operation: string, pick: (req: Request, res: Response) => unknown) {
  return handle(async (req: Request, res: Response) => {
    const principal = principalOf(res);
    if (!principal) throw problems.unauthenticated();
    const result = await client.call(operation, principal, pick(req, res), {
      idempotencyKey: req.get('Idempotency-Key') ?? undefined,
      ifMatch: req.get('If-Match') ?? undefined,
    });
    if (result.status >= 400) throw domainProblem(result);
    const etag = result.headers?.etag ?? result.headers?.ETag;
    if (etag) res.setHeader('ETag', etag);
    res.setHeader('Cache-Control', 'private, no-store');
    res.status(result.status).json(result.body);
  });
}

const input = <T>(res: Response): T => res.locals.input as T;

const uuid = z.string().uuid();
const line = z
  .object({ variant_id: uuid, source_variant_ref: z.string().min(1).max(256), quantity: z.number().int().min(1).max(99) })
  .strict();
const lines = z.array(line).min(1).max(50);

export const CartCreate = z
  .object({ provider_id: z.string().min(1).max(80), merchant_id: z.string().min(1).max(256), lines })
  .strict();
export const CartUpdate = z.object({ lines }).strict();
/** Lane extension (not yet in @brandme/contracts): ask for approval of an exact quote. */
export const PurchaseRequestCreate = z.object({ quote_id: uuid }).strict();
export const ApprovalCreate = z
  .object({
    operation_id: uuid,
    challenge_id: uuid,
    nonce: z.string().min(16).max(128),
    displayed_quote_hash: z.string().regex(/^sha256:[0-9a-f]{64}$/),
  })
  .strict();
/** `PurchaseRequest` in @brandme/contracts. `delegation_id` is a consistency check the domain enforces, not authority. */
export const PurchaseCreate = z.object({ quote_id: uuid, approval_id: uuid, delegation_id: uuid.nullable() }).strict();
export const ReturnCreate = z
  .object({ source_variant_ref: z.string().min(1).max(256), quantity: z.number().int().min(1).max(99) })
  .strict();

export function createCommerceRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.use(rejectIdentityFields);

  router.post('/carts', requireAgentScope('commerce:cart'), requireIdempotencyKey, validate(CartCreate),
    forward(client, 'cart.create', (_q, res) => input(res)));
  router.patch('/carts/:id', requireAgentScope('commerce:cart'), requireIfMatch, validate(CartUpdate),
    forward(client, 'cart.update', (req, res) => ({ cart_id: req.params.id, ...input<object>(res) })));
  router.post('/carts/:id/quote', requireAgentScope('commerce:cart'),
    forward(client, 'cart.quote', (req) => ({ cart_id: req.params.id })));

  // Lane extensions: the purchase operation and its trusted-surface challenge.
  router.post('/operations', requireAgentScope('commerce:cart'), validate(PurchaseRequestCreate),
    forward(client, 'purchase.request', (_q, res) => input(res)));
  router.get('/operations/:id', requireAgentScope('commerce:research'),
    forward(client, 'operation.get', (req) => ({ operation_id: req.params.id })));
  router.post('/operations/:id/approval-challenge', requireTrustedSurface,
    forward(client, 'approval.challenge', (req) => ({ operation_id: req.params.id })));

  router.post('/approvals', requireTrustedSurface, validate(ApprovalCreate),
    forward(client, 'approval.create', (_q, res) => input(res)));
  router.post('/purchases', requireAgentScope('commerce:purchase'), requireIdempotencyKey, validate(PurchaseCreate),
    forward(client, 'purchase.execute', (_q, res) => input(res)));
  router.get('/orders/:id', requireAgentScope('commerce:research'),
    forward(client, 'order.get', (req) => ({ order_id: req.params.id })));
  // Returns move money back: agents need purchase authority, and the domain checks the order is theirs.
  router.post('/orders/:id/returns', requireAgentScope('commerce:purchase'), requireIdempotencyKey, validate(ReturnCreate),
    forward(client, 'order.return', (req, res) => ({ order_id: req.params.id, ...input<object>(res) })));
  return router;
}

/** `GET /commerce/ops/queue` — operator view of purchases needing attention (no member identifiers). */
export function createCommerceOpsRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.use(rejectIdentityFields, requireRole('commerce:operator'));
  router.get('/queue', forward(client, 'commerce.ops.queue', () => ({})));
  return router;
}

/**
 * Provider webhooks: no session; the domain verifies signature, replay window and
 * (provider, event_id) dedupe. Mount with `express.raw({ type: '*\/*', limit: '256kb' })`
 * before any JSON parser so the signed bytes arrive unchanged.
 */
export function createCommerceWebhookRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.post('/:providerId', handle(async (req: Request, res: Response) => {
    if (!Buffer.isBuffer(req.body)) throw problems.invalid('Webhook body must be delivered raw.');
    const headers: Record<string, string> = {};
    for (const [k, v] of Object.entries(req.headers)) if (typeof v === 'string') headers[k] = v;
    const result = await client.webhook(req.params.providerId, headers, req.body);
    // Say nothing about why a delivery was refused.
    res.status(result.status === 200 ? 202 : result.status >= 500 ? 503 : 400).json({ received: result.status === 200 });
  }));
  return router;
}

// --------------------------------------------------------------------- transport
export interface HttpCommerceClientOptions {
  /** Internal base URL of the commerce domain service. */
  baseUrl: string;
  /** Gateway issuer the domain trusts (`iss`). */
  issuer: string;
  kid: string;
  /** ES256 private key; from Secret Manager at boot, never from the repo. */
  privateKey: KeyLike;
  fetchImpl?: typeof fetch;
  ttlSeconds?: number;
  timeoutMs?: number;
}

export const DOMAIN_AUDIENCE = 'brandme:commerce-domain';

/** The assertion's principal claim (snake_case, as the Python verifier reads it). */
export function principalClaim(p: Principal): Record<string, unknown> {
  return {
    member_id: p.memberId,
    subject: p.subject,
    session_id: p.via === 'session' ? p.sessionId : null,
    client_id: p.clientId,
    scopes: p.scopes,
    assurance_level: p.assuranceLevel,
    environment: p.environment,
    delegation_id: p.delegationId,
    identity_provider: p.identityProvider,
  };
}

/**
 * Gateway → commerce domain over HTTP with an ES256 assertion (aud
 * `brandme:commerce-domain`, ≤60 s, unique `jti`). Never retried here: a
 * purchase that timed out after sending is reconciled by the domain through its
 * idempotency key, and the caller retries with the same Idempotency-Key.
 */
export function createHttpCommerceDomainClient(opts: HttpCommerceClientOptions): CommerceDomainClient {
  const doFetch = opts.fetchImpl ?? fetch;
  const ttl = Math.min(opts.ttlSeconds ?? 30, 60);
  const base = opts.baseUrl.replace(/\/$/, '');
  const sign = (principal: Record<string, unknown> | null) =>
    new SignJWT({ principal })
      .setProtectedHeader({ alg: 'ES256', kid: opts.kid })
      .setIssuer(opts.issuer)
      .setAudience(DOMAIN_AUDIENCE)
      .setIssuedAt()
      .setExpirationTime(`${ttl}s`)
      .setJti(randomUUID())
      .sign(opts.privateKey);

  async function post(path: string, token: string, body: string, extra: Record<string, string>): Promise<DomainResult> {
    let r: globalThis.Response;
    try {
      r = await doFetch(`${base}${path}`, {
        method: 'POST',
        headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json', ...extra },
        body,
        signal: AbortSignal.timeout(opts.timeoutMs ?? 10_000),
      });
    } catch {
      throw problems.unavailable('The commerce service did not answer. Retry with the same Idempotency-Key.');
    }
    const text = await r.text();
    let parsed: unknown = null;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      throw problems.unavailable('The commerce service returned an unreadable response.');
    }
    const headers: Record<string, string> = {};
    const etag = r.headers.get('etag');
    if (etag) headers.etag = etag;
    return { status: r.status, body: parsed, headers };
  }

  return {
    async call(operation, principal, body, options) {
      if (!/^[a-z]+(\.[a-z_]+)+$/.test(operation)) throw new Error(`invalid operation ${operation}`);
      const extra: Record<string, string> = {};
      if (options?.idempotencyKey) extra['idempotency-key'] = options.idempotencyKey;
      if (options?.ifMatch) extra['if-match'] = options.ifMatch;
      return post(`/internal/commerce/v1/${operation}`, await sign(principalClaim(principal)), JSON.stringify(body ?? {}), extra);
    },
    async webhook(providerId, headers, rawBody) {
      if (!/^[a-z0-9_]{1,80}$/.test(providerId)) return { status: 404, body: null };
      const envelope = JSON.stringify({ headers, body_b64: rawBody.toString('base64') });
      return post(`/internal/commerce/v1/webhooks/${providerId}`, await sign(null), envelope, {});
    },
  };
}
