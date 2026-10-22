/** Read-only network reconciliation. This component has no wallet or prover. */
import { z } from 'zod';
import type { FinalityOracle } from './adapter.js';
import type { MidnightEndpoints } from './network.js';
import { transition, type ChainEvidence, type ChainOperation, type OperationStore } from './operations.js';

export interface TransactionLookup { lookup(txId: string): Promise<ChainEvidence | null> }

const query = `query OperationTransaction($offset: TransactionOffset!) {
  transactions(offset: $offset) {
    hash block { height hash }
    ... on RegularTransaction { identifiers transactionResult { status } }
  }
}`;
const txSchema = z.object({
  hash: z.string().regex(/^[0-9a-f]{64}$/i),
  block: z.object({ height: z.number().int().nonnegative().safe(), hash: z.string().regex(/^(0x)?[0-9a-f]{64}$/i) }),
  identifiers: z.array(z.string().min(1).max(256)).max(256),
  transactionResult: z.object({ status: z.enum(['SUCCESS', 'PARTIAL_SUCCESS', 'FAILURE']) }),
});

/** One bounded query using the pinned Midnight.js indexer schema; no indefinite subscription. */
export class IndexerTransactionLookup implements TransactionLookup {
  constructor(private readonly endpoints: MidnightEndpoints, private readonly doFetch: typeof fetch = fetch) {}
  async lookup(txId: string): Promise<ChainEvidence | null> {
    const res = await this.doFetch(this.endpoints.indexerHttp, {
      method: 'POST', headers: { 'content-type': 'application/json' }, redirect: 'error',
      signal: AbortSignal.timeout(2000), body: JSON.stringify({ query, variables: { offset: { identifier: txId } } }),
    });
    if (!res.ok) { await res.body?.cancel(); throw new Error('indexer unavailable'); }
    const reader = res.body?.getReader();
    if (!reader) throw new Error('empty indexer response');
    const chunks: Uint8Array[] = []; let bytes = 0;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        bytes += value.byteLength;
        if (bytes > 1024 * 1024) throw new Error('indexer response too large');
        chunks.push(value);
      }
    } finally { await reader.cancel(); }
    const body = z.object({ data: z.object({ transactions: z.array(z.unknown()).max(256) }), errors: z.array(z.unknown()).optional() })
      .parse(JSON.parse(Buffer.concat(chunks).toString('utf8')));
    if (body.errors?.length) throw new Error('indexer query failed');
    if (!body.data.transactions.length) return null;
    // An offset can return additional transactions. Never attribute an unrelated row to this operation.
    const rows = body.data.transactions.map((value) => txSchema.parse(value));
    const matches = rows.filter((tx) => tx.identifiers.includes(txId));
    if (matches.length !== 1) throw new Error('indexer transaction identifier mismatch');
    const tx = matches[0]!;
    const status = { SUCCESS: 'SucceedEntirely', PARTIAL_SUCCESS: 'FailFallible', FAILURE: 'FailEntirely' } as const;
    return { txId, txHash: tx.hash, blockHeight: tx.block.height, blockHash: tx.block.hash,
      status: status[tx.transactionResult.status], observedAt: new Date().toISOString() };
  }
}

export class OperationReconciler {
  constructor(private readonly o: {
    store: OperationStore; endpoints: MidnightEndpoints; contractAddress: string;
    lookup: TransactionLookup; finality: FinalityOracle;
  }) {}

  async reconcile(id: string): Promise<ChainOperation> {
    let op = await this.o.store.get(id);
    if (!op || op.network !== this.o.endpoints.networkId || op.contractAddress !== this.o.contractAddress.toLowerCase()) {
      throw new Error('operation outside reconciler scope');
    }
    if (!['Submitted', 'Reconciling', 'Observed'].includes(op.state) || !op.evidence?.txId) return op;
    if (op.state !== 'Observed') {
      const evidence = await this.o.lookup.lookup(op.evidence.txId);
      if (!evidence) {
        return op.state === 'Submitted' ? this.save(op, transition(op, 'Reconciling')) : op;
      }
      if (evidence.txId !== op.evidence.txId) throw new Error('transaction identifier mismatch');
      if (evidence.status !== 'SucceedEntirely') {
        if (!['FailEntirely', 'FailFallible'].includes(evidence.status ?? '')) throw new Error('invalid chain status');
        const finality = await this.o.finality.isFinal(evidence.blockHeight!, evidence.blockHash!);
        if (!finality.final) return op.state === 'Submitted' ? this.save(op, transition(op, 'Reconciling')) : op;
        return this.save(op, transition(op, 'Failed', { evidence: { ...evidence, finalizedHeadHeight: finality.finalizedHeadHeight }, failureReason: `chain_${evidence.status}` }));
      }
      op = await this.save(op, transition(op, 'Observed', { evidence }));
    }
    if (op.state !== 'Observed') return op; // A concurrent reconciler may already have finished.
    const e = op.evidence!;
    const finality = await this.o.finality.isFinal(e.blockHeight!, e.blockHash!);
    if (!finality.final) return op;
    return this.save(op, transition(op, 'Finalized', { evidence: { ...e, finalizedHeadHeight: finality.finalizedHeadHeight } }));
  }

  private async save(previous: ChainOperation, next: ChainOperation): Promise<ChainOperation> {
    const saved = await this.o.store.update(next, previous.version);
    if (saved) return saved;
    const current = await this.o.store.get(previous.operationId);
    if (!current) throw new Error('operation no longer available');
    return current;
  }
}
