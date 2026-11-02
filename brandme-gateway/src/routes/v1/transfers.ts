/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * /v1/transfers/:transferId — a transfer intent's status and the recipient's binding.
 * Shipped unmounted: the mount file is foundation's (routes/v1/index.ts). Mount it
 * under /api/v1/transfers behind the gateway principal boundary.
 *
 * Accepting here binds the recipient's commitment, which their wallet computed
 * locally for the next epoch. The transfer is final only when the recipient's
 * acceptTransfer proof is observed and finalized on chain.
 */

import { handle } from '../../middleware/problem';

import { Router } from 'express';
import type { Router as IRouter } from 'express';
import { z } from 'zod';
import { recipientInvite, TRANSFER_REAUTH_SECONDS } from './assets';
import { commandHeaders, commandsOf, idempotencyKeyOr400, relay, subjectOr401, type V1Deps } from './chain';

const transferId = z.string().regex(/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/);

const acceptSchema = z.object({
  recipient_invite: recipientInvite,
  recipient_commitment: z.string().regex(/^[0-9a-f]{64}$/).refine((c) => c !== '0'.repeat(64)),
}).strict();

export function createTransfersRouter(deps: V1Deps): IRouter {
  const router: IRouter = Router();

  // Sender or recipient only; anyone else gets 404. The sender's view carries the exact
  // offerTransfer arguments once a recipient is bound; witnesses never leave the wallet.
  router.get('/:transferId', deps.requireScope('rights:read'), handle(async (req, res) => {
    const subject = subjectOr401(deps, req, res);
    if (!subject) return;
    const id = transferId.safeParse(req.params.transferId);
    if (!id.success) { res.status(400).json({ error: 'invalid_transfer_id' }); return; }
    relay(res, await commandsOf(deps).get(`/rights/transfers/${id.data}`, commandHeaders(deps, req, subject)));
  }));

  router.post('/:transferId/accept', deps.requireScope('rights:transfer'), deps.requireRecentAuth(TRANSFER_REAUTH_SECONDS),
    handle(async (req, res) => {
      const subject = subjectOr401(deps, req, res);
      if (!subject) return;
      const id = transferId.safeParse(req.params.transferId);
      const body = acceptSchema.safeParse(req.body);
      if (!id.success || !body.success) { res.status(400).json({ error: 'invalid_request', details: body.success ? undefined : body.error.issues }); return; }
      const idem = idempotencyKeyOr400(req, res);
      if (!idem) return;
      relay(res, await commandsOf(deps).post(`/rights/transfers/${id.data}/accept`, body.data,
        commandHeaders(deps, req, subject, { 'idempotency-key': idem })));
    }));

  return router;
}
