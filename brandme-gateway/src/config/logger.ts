/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Logger Configuration (Pino)
 */

import pino from 'pino';
import { config } from './index';

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
    paths: [
      'req.headers.authorization',
      'req.headers.cookie',
      'req.body.password',
      'req.body.token',
      '*.password',
      '*.token',
      '*.secret',
      '*.apiKey',
      '*.wallet',
    ],
    censor: '[REDACTED]',
  },
});
