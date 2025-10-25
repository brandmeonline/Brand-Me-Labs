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
