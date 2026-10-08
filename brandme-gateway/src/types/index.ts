/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Type Definitions
 */

import { Request } from 'express';

/**
 * User information from JWT
 */
export interface User {
  userId: string;
  email?: string;
  name?: string;
}

/**
 * Express Request with authenticated user
 */
export interface AuthenticatedRequest extends Request {
  user?: User;
}

/**
 * Scan event payload
 */
export interface ScanEventPayload {
  scan_id: string;
  scanner_user_id: string;
  garment_tag: string;
  timestamp: string;
  region_code: string;
  request_id: string;
}

/**
 * Authenticated principal for /api/v1 (spec ch.03 §3). Resolved from a
 * server-side session or a verified OIDC bearer token — never from request
 * fields.
 */
export interface Principal {
  memberId: string;
  subject: string;
  sessionId: string | null;
  clientId: string | null;
  scopes: string[];
  assuranceLevel: 'simulated' | 'aal1' | 'aal2';
  environment: 'demo' | 'development' | 'sandbox' | 'production';
  delegationId: string | null;
  identityProvider: string;
  expiresAt: Date;
  via: 'session' | 'bearer';
}
