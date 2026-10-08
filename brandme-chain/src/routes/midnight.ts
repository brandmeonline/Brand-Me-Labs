/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Read-only Midnight routes on the chain service. Member rights operations are
 * proved and submitted by the member's connected wallet (user-controlled mode);
 * this service never holds member secrets.
 */

import { Router, type Request, type Response } from 'express';
import type { Router as IRouter } from 'express';
import { config } from '../config/index.js';
import { midnightCapability } from '../midnight/capability.js';

const router: IRouter = Router();

router.get('/capability', (_req: Request, res: Response) => {
  res.status(200).json(midnightCapability(config));
});

export default router;
