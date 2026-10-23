/** Durable operation journal. Transactions contain database work only. */
import { createHash, randomInt, randomUUID } from 'node:crypto';
import { Spanner, type Database, type Transaction } from '@google-cloud/spanner';
import type { MidnightNetworkId } from './network.js';
import {
  ActiveOperationError, IdempotencyConflictError, TERMINAL, validateOperation, validateUpdate,
  type ChainOperation, type OperationState, type OperationStore,
} from './operations.js';

type Row = Record<string, any>; // Spanner JSON rows are validated before use.
const iso = (value: unknown): string => new Date(value instanceof Date ? value.getTime() : String(value)).toISOString();
const numeric = (value: any): number => Number(value?.value ?? value);
const json = (value: any): any => typeof value === 'string' ? JSON.parse(value) : value;

function fromRow(r: Row): ChainOperation {
  const op: ChainOperation = {
    operationId: r.operation_id, network: r.network, contractAddress: r.contract_address, circuit: r.circuit,
    args: json(r.args_json), requestDigest: r.request_digest, subjectRef: r.subject_ref ?? undefined,
    ownerRef: r.owner_ref ?? undefined, idempotencyKey: r.idempotency_key,
    expiresAt: r.expires_at ? iso(r.expires_at) : undefined, state: r.state, version: numeric(r.version),
    failureReason: r.failure_reason ?? undefined, history: json(r.history_json),
    createdAt: iso(r.created_at), updatedAt: iso(r.updated_at),
    evidence: r.tx_id ? {
      txId: r.tx_id, txHash: r.tx_hash ?? undefined, blockHash: r.block_hash ?? undefined,
      blockHeight: r.block_height == null ? undefined : numeric(r.block_height),
      status: r.chain_status ?? undefined,
      finalizedHeadHeight: r.finalized_head_height == null ? undefined : numeric(r.finalized_head_height),
      observedAt: iso(r.observed_at),
    } : undefined,
  };
  validateOperation(op);
  return op;
}

function toRow(op: ChainOperation, environment: string): Row {
  const e = op.evidence;
  return {
    operation_id: op.operationId, environment, owner_ref: op.ownerRef, network: op.network,
    contract_address: op.contractAddress, circuit: op.circuit, args_json: JSON.stringify(op.args),
    request_digest: op.requestDigest, subject_ref: op.subjectRef ?? null, idempotency_key: op.idempotencyKey,
    expires_at: op.expiresAt ? new Date(op.expiresAt) : null, state: op.state, version: op.version,
    failure_reason: op.failureReason ?? null, tx_id: e?.txId ?? null, tx_hash: e?.txHash ?? null,
    block_height: e?.blockHeight ?? null, block_hash: e?.blockHash ?? null, chain_status: e?.status ?? null,
    finalized_head_height: e?.finalizedHeadHeight ?? null, observed_at: e ? new Date(e.observedAt) : null,
    history_json: JSON.stringify(op.history), created_at: new Date(op.createdAt), updated_at: new Date(op.updatedAt),
  };
}

export async function runSpannerTransaction<T>(database: Database, fn: (tx: Transaction) => Promise<T>): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    const [tx] = await database.getTransaction();
    try {
      const result = await fn(tx);
      await tx.commit();
      return result;
    } catch (error) {
      await tx.rollback().catch(() => undefined);
      if ((error as { code?: number }).code !== 10 || attempt >= 7) throw error;
    } finally { tx.end(); }
    await new Promise((resolve) => setTimeout(resolve, randomInt(20, Math.min(1000, 50 * 2 ** attempt))));
  }
}

export class SpannerOperationStore implements OperationStore {
  constructor(readonly database: Database, readonly environment: string) {
    if (!['demo', 'development', 'sandbox', 'production'].includes(environment)) throw new Error('invalid operation environment');
  }

  /** Fail startup if V012 is missing; never silently substitute memory storage. */
  async initialize(): Promise<void> {
    await this.database.run('SELECT environment, owner_ref, observed_at, reconciliation_lease_id, reconciliation_lease_until, reconciliation_attempts, projection_completed_at, projection_outcome FROM ChainOperations LIMIT 0');
    await this.database.run('SELECT operation_id FROM ChainOperationSubjects LIMIT 0');
  }

  private rw<T>(fn: (tx: Transaction) => Promise<T>): Promise<T> { return runSpannerTransaction(this.database, fn); }

  private async read(reader: Database | Transaction, id: string): Promise<ChainOperation | null> {
    const [rows] = await reader.run({
      sql: 'SELECT * FROM ChainOperations WHERE operation_id = @id AND environment = @env',
      params: { id, env: this.environment }, json: true,
    });
    return rows.length ? fromRow(rows[0] as Row) : null;
  }

  private async lockSubject(tx: Transaction, op: ChainOperation): Promise<void> {
    if (!op.subjectRef || TERMINAL.has(op.state)) return;
    const key = [this.environment, op.network, op.contractAddress, op.subjectRef];
    const [rows] = await tx.read('ChainOperationSubjects', { keys: [key], columns: ['operation_id'], json: true });
    if (rows.length) {
      const otherId = (rows[0] as Row).operation_id;
      if (otherId === op.operationId) return;
      const other = await this.read(tx, otherId);
      if (!other || !TERMINAL.has(other.state)) throw new ActiveOperationError();
    }
    tx.upsert('ChainOperationSubjects', {
      environment: this.environment, network: op.network, contract_address: op.contractAddress,
      subject_ref: op.subjectRef, operation_id: op.operationId,
    });
  }

  private async assertProcessingAllowed(tx: Transaction, op: ChainOperation): Promise<void> {
    const params = { owner: op.ownerRef!, categories: ['*', 'rights.operations'] };
    const [freezes] = await tx.run({
      sql: 'SELECT category FROM ProcessingFreezes WHERE subject_ref = @owner AND category IN UNNEST(@categories) LIMIT 1',
      params,
    });
    if (freezes.length) throw new Error('operation processing is frozen');
    // A separately owned consent/restriction freeze may have been removed.
    // Pending category deletions and every account deletion remain authoritative.
    const [deletions] = await tx.run({
      sql: `SELECT job_id FROM DeletionJobs WHERE subject_ref = @owner AND
        (scope = 'account' OR ('rights.operations' IN UNNEST(categories)
          AND state NOT IN ('completed', 'completed_with_exceptions'))) LIMIT 1`,
      params: { owner: op.ownerRef! },
    });
    if (deletions.length) throw new Error('operation processing is frozen');
    const [tombstones] = await tx.run({
      sql: "SELECT tombstone_id FROM DeletionTombstones WHERE subject_ref = @owner AND category = 'rights.operations' AND created_at >= @basis LIMIT 1",
      params: { owner: op.ownerRef!, basis: new Date(op.createdAt) },
    });
    if (tombstones.length) throw new Error('operation processing basis was deleted');
  }

  async create(op: ChainOperation): Promise<ChainOperation> {
    validateOperation(op, true);
    if (!op.ownerRef) throw new Error('durable operations require an authenticated owner');
    if (op.network === 'mainnet') throw new Error('Mainnet writes are not authorized');
    return this.rw(async (tx) => {
      const [rows] = await tx.run({
        sql: `SELECT * FROM ChainOperations WHERE environment = @env AND owner_ref = @owner
          AND network = @network AND contract_address = @contract AND idempotency_key = @key`,
        params: { env: this.environment, owner: op.ownerRef!, network: op.network, contract: op.contractAddress, key: op.idempotencyKey }, json: true,
      });
      if (rows.length) {
        const existing = fromRow(rows[0] as Row);
        if (existing.requestDigest !== op.requestDigest) throw new IdempotencyConflictError(op.idempotencyKey);
        return existing;
      }
      await this.assertProcessingAllowed(tx, op);
      await this.lockSubject(tx, op);
      tx.insert('ChainOperations', toRow(op, this.environment));
      return op;
    });
  }

  get(id: string) { return this.read(this.database, id); }

  async update(op: ChainOperation, expectedVersion: number): Promise<ChainOperation | null> {
    if (op.network === 'mainnet') throw new Error('Mainnet writes are not authorized');
    return this.rw(async (tx) => {
      const previous = await this.read(tx, op.operationId);
      if (!previous || previous.version !== expectedVersion) return null;
      validateUpdate(previous, op);
      if (op.state === 'Proving' || previous.state === 'Proving' && op.state === 'Reconciling') await this.assertProcessingAllowed(tx, op);
      await this.lockSubject(tx, op);
      tx.update('ChainOperations', toRow(op, this.environment));
      if (op.state === 'Observed' || op.state === 'Finalized') {
        const id = randomUUID(); const e = op.evidence!;
        tx.insert('OutboxEvents', {
          shard: parseInt(createHash('sha256').update(id).digest('hex').slice(0, 8), 16) % 16,
          event_id: id, event_type: 'chain.operation.observed', schema_version: '1',
          aggregate_type: 'chain_operation', aggregate_id: op.operationId, aggregate_version: op.version,
          occurred_at: new Date(op.updatedAt), environment: this.environment, actor_ref: 'service:chain',
          correlation_id: op.operationId, causation_id: null, privacy_class: 'restricted',
          payload: JSON.stringify({ operation_id: op.operationId, network: op.network, tx_id: e.txId,
            block_height: String(e.blockHeight), block_hash: e.blockHash, state: op.state }),
          status: 'pending', attempts: 0, next_attempt_at: new Date(), created_at: Spanner.COMMIT_TIMESTAMP,
        });
      }
      return op;
    });
  }

  async listByState(network: MidnightNetworkId, states: readonly OperationState[]): Promise<ChainOperation[]> {
    if (!states.length) return [];
    const [rows] = await this.database.run({
      sql: 'SELECT * FROM ChainOperations WHERE environment = @env AND network = @network AND state IN UNNEST(@states)',
      params: { env: this.environment, network, states: [...states] }, json: true,
    });
    return rows.map((r) => fromRow(r as Row));
  }

  async activeForSubject(network: MidnightNetworkId, subjectRef: string): Promise<ChainOperation[]> {
    const [rows] = await this.database.run({
      sql: 'SELECT * FROM ChainOperations WHERE environment = @env AND network = @network AND subject_ref = @subject',
      params: { env: this.environment, network, subject: subjectRef }, json: true,
    });
    return rows.map((r) => fromRow(r as Row)).filter((op) => !TERMINAL.has(op.state));
  }
}

export function operationDatabase(projectId: string, instanceId: string, databaseId: string): Database {
  // The emulator does not advertise multiplexed sessions correctly (SDK 9).
  if (process.env.SPANNER_EMULATOR_HOST) {
    process.env.GOOGLE_CLOUD_SPANNER_MULTIPLEXED_SESSIONS ??= 'false';
    process.env.GOOGLE_CLOUD_SPANNER_MULTIPLEXED_SESSIONS_FOR_RW ??= 'false';
  }
  return new Spanner({ projectId }).instance(instanceId).database(databaseId);
}
