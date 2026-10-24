/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Legacy route authentication adapter.
 *
 * The previous implementation verified HS-signed JWTs with a shared secret, no
 * algorithm allowlist and no audience check, and logged raw user IDs. It is
 * replaced by the principal resolved in middleware/session.ts (server-side
 * session or JWKS-verified OIDC bearer). Legacy routes keep `req.user`.
 */

import type { NextFunction, Request, Response } from 'express';
import type { AuthenticatedRequest, Principal } from '../types';
import { problems } from './problem';

export function authMiddleware(req: Request, res: Response, next: NextFunction): void {
  const principal = res.locals.principal as Principal | undefined;
  if (!principal) return next(problems.unauthenticated());
  (req as AuthenticatedRequest).user = { userId: principal.memberId };
  next();
}
