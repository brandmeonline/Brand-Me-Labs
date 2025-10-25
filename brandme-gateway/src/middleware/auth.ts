/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * OAuth Authentication Middleware
 */

import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { config } from '../config';
import { logger } from '../config/logger';
import { AuthenticatedRequest } from '../types';

export interface JWTPayload {
  sub: string; // user_id
  email?: string;
  name?: string;
  iss: string;
  aud: string;
  exp: number;
  iat: number;
}

/**
 * Middleware to verify OAuth JWT token
 */
export function authMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    res.status(401).json({
      error: 'Unauthorized',
      message: 'Missing or invalid Authorization header',
    });
    return;
  }

  const token = authHeader.substring(7); // Remove 'Bearer ' prefix

  try {
    // Verify JWT
    const decoded = jwt.verify(token, config.jwtSecret) as JWTPayload;

    // Validate issuer
    if (decoded.iss !== config.oauthIssuer) {
      throw new Error('Invalid token issuer');
    }

    // Attach user info to request
    (req as AuthenticatedRequest).user = {
      userId: decoded.sub,
      email: decoded.email,
      name: decoded.name,
    };

    logger.debug({ userId: decoded.sub }, 'User authenticated');

    next();
  } catch (error) {
    if (error instanceof jwt.TokenExpiredError) {
      res.status(401).json({
        error: 'Unauthorized',
        message: 'Token expired',
      });
      return;
    }

    if (error instanceof jwt.JsonWebTokenError) {
      res.status(401).json({
        error: 'Unauthorized',
        message: 'Invalid token',
      });
      return;
    }

    logger.error({ error }, 'Authentication error');
    res.status(500).json({
      error: 'Internal Server Error',
      message: 'Authentication failed',
    });
  }
}
