/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Health Check Routes
 */

import { Router, Request, Response } from 'express';
import type { Router as IRouter } from 'express';

const router: IRouter = Router();

/**
 * GET /healthz
 * Health check endpoint (Kubernetes liveness probe)
 */
router.get('/', (_req: Request, res: Response) => {
  res.status(200).json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    service: 'brandme-gateway',
  });
});

export default router;
