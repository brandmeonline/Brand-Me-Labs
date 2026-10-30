/** Internal gateway boundary. Only a server credential may assert member identity. */
import { createHash, timingSafeEqual } from 'node:crypto';
import { Router, type Router as IRouter, type Request, type Response } from 'express';
import { z } from 'zod';
import type { ChainOperation, OperationStore } from '../midnight/operations.js';
import type { OperationReconciler } from '../midnight/reconciler.js';
import type { MidnightNetworkId } from '../midnight/network.js';

const report = z.object({ operation_id: z.string().uuid(), tx_id: z.string().min(8).max(256),
  network: z.enum(['undeployed', 'preview', 'preprod']) }).strict();

/** Wire shape matches the shared ChainOperation contract. No arguments or member references. */
export function operationView(op: ChainOperation) {
  const states = { Draft: 'prepared', AwaitingRecipient: 'awaiting_wallet', ReadyToProve: 'awaiting_wallet', Proving: 'proving',
    Submitted: 'submitted', Reconciling: 'reconciling', Observed: 'observed', Finalized: 'finalized', Failed: 'failed',
    Cancelled: 'cancelled', Expired: 'cancelled', HandoverPending: 'finalized', HandoverAcknowledged: 'finalized' } as const;
  const circuits: Record<string, string> = { issueEntitlement: 'issue', proveControl: 'prove_control', offerTransfer: 'transfer',
    acceptTransfer: 'transfer', cancelTransfer: 'transfer', consumeReprintAllowance: 'consume_reprint', attestManufacture: 'attest_manufacture',
    revokeEntitlement: 'revoke', grantReplacementAllowance: 'recover' };
  const operation = circuits[op.circuit];
  if (!operation) throw new Error('operator-only operation');
  return { id: op.operationId, contract_ref: op.contractAddress, network: op.network === 'undeployed' ? 'local' : op.network,
    operation, state: states[op.state], request_digest: op.requestDigest, transaction_id: op.evidence?.txId ?? null,
    observed_block: op.evidence?.blockHash ?? null, updated_at: op.updatedAt };
}

export function createOperationsRouter(o: {
  token?: string; store?: OperationStore; reconciler?: OperationReconciler;
  network: MidnightNetworkId; contractAddress?: string;
}): IRouter {
  const router = Router();
  const credential = (value: string) => createHash('sha256').update(value).digest();
  router.use((req, res, next) => {
    if (!o.token || !o.store) { res.status(503).json({ error: 'operation_service_unavailable' }); return; }
    if (!timingSafeEqual(credential(req.get('authorization') ?? ''), credential(`Bearer ${o.token}`))) {
      res.status(401).json({ error: 'unauthenticated' }); return;
    }
    if (!z.string().uuid().safeParse(req.get('x-subject-ref')).success) { res.status(401).json({ error: 'unauthenticated' }); return; }
    next();
  });
  const owned = async (req: Request, id: string) => {
    const op = await o.store!.get(id);
    return op && op.ownerRef === req.get('x-subject-ref') && op.network === o.network &&
      op.contractAddress === o.contractAddress?.toLowerCase() ? op : null;
  };
  const unavailable = (res: Response) => { res.status(503).json({ error: 'operation_service_unavailable' }); };
  router.get('/operations/:operationId', async (req, res) => {
    if (!z.string().uuid().safeParse(req.params.operationId).success) { res.status(400).json({ error: 'invalid_operation_id' }); return; }
    try {
      const op = await owned(req, req.params.operationId);
      if (!op) { res.status(404).json({ error: 'not_found' }); return; }
      res.json(operationView(op));
    } catch { unavailable(res); }
  });
  router.post('/operations/reconcile', async (req, res) => {
    const body = report.safeParse(req.body);
    if (!body.success) { res.status(400).json({ error: 'invalid_request' }); return; }
    try {
      const op = await owned(req, body.data.operation_id);
      if (!op) { res.status(404).json({ error: 'not_found' }); return; }
      if (op.network !== body.data.network) { res.status(409).json({ error: 'wrong_network' }); return; }
      // A client hint can only request observation of an ID already persisted by the guarded submitter.
      if (!op.evidence?.txId || op.evidence.txId !== body.data.tx_id) { res.status(409).json({ error: 'transaction_not_bound' }); return; }
      if (!o.reconciler) { unavailable(res); return; }
      res.json(operationView(await o.reconciler.reconcile(op.operationId)));
    } catch { unavailable(res); }
  });
  return router;
}
