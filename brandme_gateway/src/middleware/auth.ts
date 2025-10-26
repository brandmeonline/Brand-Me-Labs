/**
 * Brand.Me Gateway - Authentication Middleware
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 * 
 * Handles OAuth 2.0 JWT token validation for authenticated routes
 */

import { Request, Response, NextFunction } from 'express';
import { logger } from '../config/logger';

export interface AuthRequest extends Request {
  user?: {
    userId: string;
    email: string;
    roles: string[];
  };
}

/**
 * Middleware to validate JWT tokens
 * TODO: Implement proper JWT validation with public key
 */
export function authMiddleware(
  req: AuthRequest,
  res: Response,
  next: NextFunction
): void {
  const authHeader = req.headers.authorization;

  if (!authHeader) {
    logger.warn('Unauthorized: No authorization header', {
      path: req.path,
      method: req.method,
    });
    res.status(401).json({ error: 'Unauthorized', message: 'Missing authorization header' });
    return;
  }

  const parts = authHeader.split(' ');
  
  if (parts.length !== 2 || parts[0] !== 'Bearer') {
    logger.warn('Unauthorized: Invalid authorization header format', {
      path: req.path,
      method: req.method,
    });
    res.status(401).json({ error: 'Unauthorized', message: 'Invalid authorization header format' });
    return;
  }

  const token = parts[1];

  // TODO: Validate JWT token with proper public key
  // For now, extract basic info from token
  try {
    // In production, this would decode and validate the JWT
    // For now, we'll use a simple mock validation
    
    const decodedToken = parseJWTMock(token);
    
    if (!decodedToken) {
      logger.warn('Unauthorized: Invalid token', {
        path: req.path,
        method: req.method,
      });
      res.status(401).json({ error: 'Unauthorized', message: 'Invalid or expired token' });
      return;
    }

    // Attach user info to request
    req.user = {
      userId: decodedToken.sub || 'unknown',
      email: decodedToken.email || 'unknown@example.com',
      roles: decodedToken.roles || ['ROLE_USER'],
    };

    logger.debug('Request authenticated', {
      userId: req.user.userId,
      path: req.path,
    });

    next();
  } catch (error) {
    logger.error('Authentication error', {
      error: error instanceof Error ? error.message : String(error),
      path: req.path,
    });
    res.status(401).json({ error: 'Unauthorized', message: 'Authentication failed' });
  }
}

/**
 * Mock JWT parser - Replace with proper JWT validation in production
 * TODO: Use jsonwebtoken library with public key validation
 */
function parseJWTMock(token: string): any {
  // Simple mock for development
  // In production, use: jwt.verify(token, publicKey, { algorithms: ['RS256'] })
  
  if (!token || token.length < 10) {
    return null;
  }

  // For development/testing, accept tokens with basic structure
  try {
    // Extract user ID from token (in production, decode JWT)
    const mockUser = {
      sub: token.slice(0, 8), // Mock user ID
      email: 'user@example.com',
      roles: ['ROLE_USER'],
      exp: Date.now() / 1000 + 3600, // 1 hour from now
    };
    
    return mockUser;
  } catch (error) {
    return null;
  }
}

/**
 * Middleware to check for specific roles
 */
export function requireRole(...allowedRoles: string[]) {
  return (req: AuthRequest, res: Response, next: NextFunction): void => {
    if (!req.user) {
      res.status(401).json({ error: 'Unauthorized', message: 'Authentication required' });
      return;
    }

    const hasRole = req.user.roles.some(role => allowedRoles.includes(role));

    if (!hasRole) {
      logger.warn('Forbidden: Insufficient permissions', {
        userId: req.user.userId,
        requiredRoles: allowedRoles,
        userRoles: req.user.roles,
        path: req.path,
      });
      res.status(403).json({ 
        error: 'Forbidden', 
        message: 'Insufficient permissions',
        required: allowedRoles,
        actual: req.user.roles,
      });
      return;
    }

    next();
  };
}

/**
 * Export user from request
 */
export function getUser(req: AuthRequest) {
  return req.user;
}

