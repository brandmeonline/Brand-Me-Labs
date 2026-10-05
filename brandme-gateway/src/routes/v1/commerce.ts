/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /api/v1/commerce — UNMOUNTED router (lane: opus-commerce-agents).
 *
 * Mounting, session/CSRF middleware and principal resolution belong to opus-foundation.
 * These routers expect upstream middleware to set `req.principal` from a verified session
 * or MCP token and never read identity from the body or query. All domain decisions
 * (quote hashing, approvals, budgets, provider submission) happen in the Python commerce
 * service; the gateway validates shape, enforces scope and forwards with the principal.
 */

import { Router, Request, Response, NextFunction } from 'express';
import { randomUUID } from 'crypto';
import { z } from 'zod';

export interface Principal {
  memberId: string;
  subject: string;
  issuer: string;
  clientId: string;
  scopes: string[];
  assuranceLevel: 'aal1' | 'aal2' | 'aal3';
  environment: 'demo' | 'development' | 'sandbox' | 'production';
  sessionId: string | null;
  delegationId: string | null;
  /** True only for Brand.Me's own first-party session (the trusted approval surface). */
  firstPartySession: boolean;
}

export type PrincipalRequest = Request & { principal?: Principal; requestId?: string };

export interface DomainResult {
  status: number;
  body: unknown;
}

/**
 * Transport to the Python commerce domain: POST {domain}/internal/commerce/v1/{operation}
 * with a gateway-signed principal assertion (same format as the MCP executor assertion).
 */
export interface CommerceDomainClient {
  call(
    operation: string,
    principal: Principal | null,
    body: unknown,
    options?: { idempotencyKey?: string; ifMatch?: string; rawBody?: Buffer; headers?: Record<string, string> }
  ): Promise<DomainResult>;
}

const IDENTITY_FIELDS = ['user_id', 'member_id', 'principal', 'owner_id', 'approved', 'scopes'];

export function problem(res: Response, status: number, code: string, detail: string, requestId?: string): void {
  res
    .status(status)
    .type('application/problem+json')
    .json({
      type: `https://brand.me/problems/${code}`,
      title: code.replace(/_/g, ' '),
      status,
      code,
      detail,
      instance: res.req?.originalUrl ?? '',
      request_id: requestId ?? randomUUID(),
      retryable: status === 429 || status === 503,
    });
}

export function requireScope(...scopes: string[]) {
  return (req: PrincipalRequest, res: Response, next: NextFunction): void => {
    const p = req.principal;
    if (!p) {
      problem(res, 401, 'unauthenticated', 'authentication required', req.requestId);
      return;
    }
    const missing = scopes.filter((s) => !p.scopes.includes(s));
    if (missing.length) {
      res.setHeader('WWW-Authenticate', `Bearer error="insufficient_scope", scope="${scopes.join(' ')}"`);
      problem(res, 403, 'insufficient_scope', 'additional scope required', req.requestId);
      return;
    }
    next();
  };
}

/** Trusted approval surface: first-party member session only — never an agent or MCP client. */
export function requireTrustedSurface(req: PrincipalRequest, res: Response, next: NextFunction): void {
  const p = req.principal;
  if (!p || !p.firstPartySession || p.delegationId) {
    problem(res, 403, 'not_trusted_surface', 'approvals are only accepted from the member trusted surface', req.requestId);
    return;
  }
  next();
}

export function rejectIdentityFields(req: PrincipalRequest, res: Response, next: NextFunction): void {
  const body = req.body && typeof req.body === 'object' ? (req.body as Record<string, unknown>) : {};
  const query = req.query as Record<string, unknown>;
  if (IDENTITY_FIELDS.some((f) => f in body || f in query)) {
    problem(res, 400, 'identity_argument_rejected', 'identity comes from authentication, not request fields', req.requestId);
    return;
  }
  next();
}

export function validate<T extends z.ZodTypeAny>(schema: T) {
  return (req: PrincipalRequest, res: Response, next: NextFunction): void => {
    const parsed = schema.safeParse(req.body ?? {});
    if (!parsed.success) {
      problem(res, 400, 'invalid_request', parsed.error.issues[0]?.message ?? 'invalid request', req.requestId);
      return;
    }
    req.body = parsed.data;
    next();
  };
}

export function forward(client: CommerceDomainClient, operation: string, pick: (req: PrincipalRequest) => unknown) {
  return async (req: PrincipalRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const result = await client.call(operation, req.principal ?? null, pick(req), {
        idempotencyKey: req.get('Idempotency-Key') ?? undefined,
        ifMatch: req.get('If-Match') ?? undefined,
      });
      res.setHeader('Cache-Control', 'private, no-store');
      res.status(result.status).json(result.body);
    } catch (err) {
      next(err);
    }
  };
}

export function requireIdempotencyKey(req: PrincipalRequest, res: Response, next: NextFunction): void {
  const key = req.get('Idempotency-Key');
  if (!key || key.length < 8 || key.length > 128) {
    problem(res, 400, 'idempotency_key_required', 'Idempotency-Key header (8-128 chars) is required', req.requestId);
    return;
  }
  next();
}

const uuid = z.string().uuid();
const line = z
  .object({ variant_id: uuid, source_variant_ref: z.string().min(1).max(256), quantity: z.number().int().min(1).max(99) })
  .strict();
const lines = z.array(line).min(1).max(50);

export const CartCreate = z
  .object({ provider_id: z.string().min(1).max(80), merchant_id: z.string().min(1).max(256), lines })
  .strict();
export const CartUpdate = z.object({ lines }).strict();
export const ApprovalCreate = z
  .object({
    operation_id: uuid,
    challenge_id: uuid,
    nonce: z.string().min(16).max(128),
    displayed_quote_hash: z.string().regex(/^sha256:[0-9a-f]{64}$/),
  })
  .strict();
/** Mirrors `PurchaseRequest` in contracts/domain.schema.json (no user_id, no approved flag). */
export const PurchaseCreate = z
  .object({ quote_id: uuid, approval_id: uuid, delegation_id: uuid.nullable() })
  .strict();
export const ReturnCreate = z
  .object({ source_variant_ref: z.string().min(1).max(256), quantity: z.number().int().min(1).max(99) })
  .strict();

export function createCommerceRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.use(rejectIdentityFields);

  router.post('/carts', requireScope('commerce:cart'), requireIdempotencyKey, validate(CartCreate),
    forward(client, 'cart.create', (r) => r.body));
  router.patch('/carts/:id', requireScope('commerce:cart'), validate(CartUpdate), (req, res, next) => {
    if (!req.get('If-Match')) {
      problem(res, 428, 'if_match_required', 'If-Match with the cart revision is required');
      return;
    }
    next();
  }, forward(client, 'cart.update', (r) => ({ cart_id: r.params.id, ...r.body })));
  router.post('/carts/:id/quote', requireScope('commerce:cart'),
    forward(client, 'cart.quote', (r) => ({ cart_id: r.params.id })));

  router.post('/operations/:id/approval-challenge', requireTrustedSurface,
    forward(client, 'approval.challenge', (r) => ({ operation_id: r.params.id })));
  router.post('/approvals', requireTrustedSurface, validate(ApprovalCreate),
    forward(client, 'approval.create', (r) => r.body));

  router.post('/purchases', requireScope('commerce:purchase'), requireIdempotencyKey, validate(PurchaseCreate),
    (req: PrincipalRequest, res, next) => {
      if ((req.body as z.infer<typeof PurchaseCreate>).delegation_id !== (req.principal?.delegationId ?? null)) {
        problem(res, 403, 'delegation_mismatch', 'delegation must match the authenticated principal', req.requestId);
        return;
      }
      next();
    },
    forward(client, 'purchase.execute', (r) => r.body));
  router.get('/operations/:id', requireScope('commerce:research'),
    forward(client, 'operation.get', (r) => ({ operation_id: r.params.id })));
  router.get('/orders/:id', requireScope('commerce:research'),
    forward(client, 'order.get', (r) => ({ order_id: r.params.id })));
  router.post('/orders/:id/returns', requireScope('commerce:purchase'), requireIdempotencyKey, validate(ReturnCreate),
    forward(client, 'order.return', (r) => ({ order_id: r.params.id, ...r.body })));
  return router;
}

/**
 * Provider webhooks: unauthenticated by session; the domain verifies the provider's signature,
 * replay window and event-id dedupe. Must be mounted with a raw-body parser.
 */
export function createCommerceWebhookRouter(client: CommerceDomainClient): Router {
  const router = Router();
  router.post('/:providerId', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const raw = Buffer.isBuffer(req.body) ? req.body : Buffer.from('');
      const headers: Record<string, string> = {};
      for (const [k, v] of Object.entries(req.headers)) if (typeof v === 'string') headers[k] = v;
      const result = await client.call('webhook.receive', null, { provider_id: req.params.providerId }, {
        rawBody: raw,
        headers,
      });
      res.status(result.status === 200 ? 202 : result.status).json({ received: result.status === 200 });
    } catch (err) {
      next(err);
    }
  });
  return router;
}
