/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Paths as they may appear in logs (ch.03 §9: no raw user identifiers). A
 * segment is kept only when it is a static word of a route the gateway knows:
 * the contract's path templates plus the legacy and lane-local routes listed
 * below. Every other segment (member, asset, job and scan IDs, handles,
 * tokens) becomes `:id`. The query string is always dropped. A new route that
 * is missing from the vocabulary is over-redacted, never leaked.
 */

import type { Request } from 'express';
import { contractPaths } from './validation';

// Static segments served by the gateway but absent from the contract paths.
const LOCAL_SEGMENTS = [
  'api', 'v1', 'scan', 'health', 'healthz',
  'capability', 'operations', 'ownership', 'challenges', 'submissions',
  'approval-challenge', 'providers', 'setup', 'verification-runs',
];

const VOCABULARY: ReadonlySet<string> = new Set([
  ...LOCAL_SEGMENTS,
  ...contractPaths.flatMap((p) => p.split('/')).filter((s) => s && !s.startsWith('{')),
]);

const MAX_SEGMENTS = 12;
const MAX_LENGTH = 256;

export function templatePath(url: string | undefined): string {
  const path = (url ?? '/').split('?')[0].split('#')[0];
  const segments = path.split('/').slice(1);
  const out = segments.slice(0, MAX_SEGMENTS).map((segment) => {
    if (segment === '') return '';
    const word = segment.toLowerCase();
    return VOCABULARY.has(word) ? word : ':id';
  });
  if (segments.length > MAX_SEGMENTS) out.push('…');
  return `/${out.join('/')}`.slice(0, MAX_LENGTH);
}

/**
 * Path the router matched. Express accepts absolute-form request targets
 * ("DELETE http://host/api/v1/session"); originalUrl then still carries the
 * scheme and host, so exemptions must use the parsed pathname.
 */
export function requestPath(req: Pick<Request, 'originalUrl'>): string {
  try {
    return new URL(req.originalUrl, 'http://gateway.invalid').pathname || '/';
  } catch {
    return (req.originalUrl.split('?')[0] || '/');
  }
}
