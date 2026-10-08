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

export function authMiddleware(req: Request, res: Response, next: NextFunction): void {
  const principal = res.locals.principal as Principal | undefined;
  if (!principal) {
    res.status(401).json({ error: 'Unauthorized', message: 'Sign-in required' });
    return;
  }
  (req as AuthenticatedRequest).user = { userId: principal.memberId };
  next();
}
