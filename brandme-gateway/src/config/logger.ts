/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Logger Configuration (Pino)
 */

import pino from 'pino';
import { config } from './index';

// Identifiers and secrets that must never reach logs (spec ch.03 §9:
// sanitized reason codes; no raw user identifiers). Covers the legacy /scan
// route, which logs scanner_user_id and garment_tag at the top level.
export const REDACT_PATHS = [
  'req.headers.authorization',
  'req.headers.cookie',
  'req.headers["x-csrf-token"]',
  'res.headers["set-cookie"]',
  'req.body.password',
  'req.body.token',
  'scanner_user_id',
  'garment_tag',
  'userId',
  'user_id',
  'member_id',
  'memberId',
  'email',
  'csrf_token',
  '*.scanner_user_id',
  '*.garment_tag',
  '*.userId',
  '*.user_id',
  '*.member_id',
  '*.memberId',
  '*.email',
  '*.csrf_token',
  '*.password',
  '*.token',
  '*.secret',
  '*.apiKey',
  '*.wallet',
];

export const logger = pino({
  level: config.logLevel,
  transport: config.environment === 'development'
    ? {
        target: 'pino-pretty',
        options: {
          colorize: true,
          translateTime: 'SYS:standard',
          ignore: 'pid,hostname',
        },
      }
    : undefined,
  formatters: {
    level: (label) => {
      return { level: label };
    },
  },
  redact: {
    paths: REDACT_PATHS,
    censor: '[REDACTED]',
  },
});
