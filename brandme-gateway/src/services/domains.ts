/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * DomainClient for the consumer-domain service (lane: opus-consumer-domains;
 * check-in ruling Q12). Each request carries a fresh ES256 principal assertion
 * (audience brandme:consumer-domains, 30 s, single-use jti) signed with the
 * gateway's key. The member's cookie or bearer token never leaves the gateway.
 * Verified by brandme_core/domains/persona/assertion.py.
 *
 * Only router-built fields cross this boundary: method, path, query, JSON
 * body, If-Match, Idempotency-Key and the request id. Try-on result images come
 * back as bytes for tryon.ts to relay; anything else must be JSON.
 */

import { randomUUID } from 'node:crypto';
import { SignJWT, importPKCS8, type KeyLike } from 'jose';
import type { GatewayConfig } from '../config';
import { problems } from '../middleware/problem';
import type { DomainClient, DomainRequest, DomainResponse } from '../routes/v1/persona';
import type { Principal } from '../types';

export const DOMAIN_AUDIENCE = 'brandme:consumer-domains';
export const DOMAIN_ISSUER = 'brandme-gateway';
const TTL_SECONDS = 30;
const TIMEOUT_MS = 10_000;
const IMAGE = /^image\/(png|jpeg|webp)$/;

export async function signDomainAssertion(key: KeyLike, kid: string, p: Principal, now = Math.floor(Date.now() / 1000)): Promise<string> {
  const principal = {
    member_id: p.memberId, subject: p.subject, session_id: p.sessionId, client_id: p.clientId, scopes: p.scopes,
    assurance_level: p.assuranceLevel, environment: p.environment, delegation_id: p.delegationId,
  };
  return new SignJWT({ principal }).setProtectedHeader({ alg: 'ES256', kid }).setIssuer(DOMAIN_ISSUER).setAudience(DOMAIN_AUDIENCE)
    .setIssuedAt(now).setExpirationTime(now + TTL_SECONDS).setJti(randomUUID()).sign(key);
}

export function consumerDomainClient(cfg: GatewayConfig, doFetch: typeof fetch = fetch): DomainClient {
  const base = cfg.consumerDomainUrl?.replace(/\/$/, '');
  const kid = cfg.consumerDomainAssertionKid;
  let key: Promise<KeyLike> | undefined;
  return {
    async request(req: DomainRequest): Promise<DomainResponse> {
      if (!base || !kid || !cfg.consumerDomainAssertionKey) throw problems.unavailable('This service is not configured.');
      key ??= importPKCS8(cfg.consumerDomainAssertionKey, 'ES256');
      const headers: Record<string, string> = { 'x-request-id': req.requestId, accept: 'application/json, image/*' };
      if (req.principal) headers.authorization = `Bearer ${await signDomainAssertion(await key, kid, req.principal)}`;
      if (req.ifMatch) headers['if-match'] = req.ifMatch;
      if (req.idempotencyKey) headers['idempotency-key'] = req.idempotencyKey;
      let body: string | undefined;
      if (req.body !== undefined && req.method !== 'GET') {
        headers['content-type'] = 'application/json';
        body = JSON.stringify(req.body);
      }
      const query = req.query && Object.keys(req.query).length ? `?${new URLSearchParams(req.query)}` : '';
      let res: Response;
      try {
        res = await doFetch(`${base}${req.path}${query}`, { method: req.method, headers, body, redirect: 'error', signal: AbortSignal.timeout(TIMEOUT_MS) });
      } catch {
        throw problems.unavailable('This service is temporarily unavailable.');
      }
      const out: Record<string, string> = {};
      const etag = res.headers.get('etag');
      if (etag) out.etag = etag;
      const ctype = (res.headers.get('content-type') ?? '').split(';')[0].trim();
      if (ctype) out['content-type'] = ctype;
      if (res.status === 204) return { status: 204, body: null, headers: out };
      if (res.status === 200 && IMAGE.test(ctype)) return { status: 200, body: Buffer.from(await res.arrayBuffer()), headers: out };
      try {
        return { status: res.status, body: await res.json(), headers: out };
      } catch {
        // A non-JSON body is an upstream failure; its text may hold internals, so it is not relayed.
        throw problems.unavailable('This service is temporarily unavailable.');
      }
    },
  };
}
