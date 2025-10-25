/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Health Check Routes
 */

import { Router, Request, Response } from 'express';

const router = Router();

/**
 * GET /healthz
 * Health check endpoint (Kubernetes liveness probe)
 */
router.get('/', (req: Request, res: Response) => {
  res.status(200).json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    service: 'brandme-gateway',
  });
});

export default router;
