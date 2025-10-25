/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Logger Configuration
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
  redact: {
    paths: [
      '*.wallet',
      '*.privateKey',
      '*.secret',
      '*.password',
    ],
    censor: '[REDACTED]',
  },
});
