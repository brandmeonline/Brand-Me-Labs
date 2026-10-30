/** Durable leases fence workers; network reads stay outside database transactions. */
import { createHash, randomUUID } from 'node:crypto';
import { Spanner, type Transaction } from '@google-cloud/spanner';
import { SpannerOperationStore, runSpannerTransaction } from './spanner-store.js';
import { validateOperation, type ChainOperation } from './operations.js';
import { entitlementSchema, type EntitlementProjection } from './projection.js';

export interface ReconciliationClaim { operationId: string; leaseId: string; attempt: number }
const FINAL_STATES = ['Finalized', 'HandoverPending', 'HandoverAcknowledged'];
const STATES = ['Submitted', 'Reconciling', 'Observed', ...FINAL_STATES];
const numeric = (value: any): number => Number(value?.value ?? value);
const date = (value: any): Date => new Date(value instanceof Date ? value.getTime() : String(value));

/** Same UUIDv5 namespace and name as the Python rights domain's event aggregate. */
export function entitlementAggregateId(network: string, contract: string, entitlement: string): string {
  const digest = createHash('sha1').update(Buffer.from('6ba7b8119dad11d180b400c04fd430c8', 'hex'))
    .update(`brandme:rights:${network}:${contract}:${entitlement}`).digest();
  digest[6] = (digest[6]! & 0x0f) | 0x50; digest[8] = (digest[8]! & 0x3f) | 0x80;
  const h = digest.subarray(0, 16).toString('hex');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export class SpannerReconciliationQueue {
  constructor(private readonly store: SpannerOperationStore) {}
  private async now(tx: Transaction): Promise<Date> {
    const [rows] = await tx.run({ sql: 'SELECT CURRENT_TIMESTAMP() AS now', json: true });
    return date((rows[0] as any).now);
  }

  /** Claims one item so time waiting behind other items never consumes its lease. */
  async claim(network: string, contractAddress: string): Promise<ReconciliationClaim | null> {
    if (network === 'mainnet') throw new Error('Mainnet worker is disabled');
    return runSpannerTransaction(this.store.database, async (tx) => {
      const now = await this.now(tx);
      const [rows] = await tx.run({
        sql: `SELECT operation_id, reconciliation_attempts FROM ChainOperations
          WHERE environment = @env AND network = @network AND contract_address = @contract
          AND owner_ref IS NOT NULL AND state IN UNNEST(@states) AND tx_id IS NOT NULL
          AND projection_completed_at IS NULL
          AND (next_check_at IS NULL OR next_check_at <= @now)
          AND (reconciliation_lease_until IS NULL OR reconciliation_lease_until <= @now)
          ORDER BY next_check_at, operation_id LIMIT 1`,
        params: { env: this.store.environment, network, contract: contractAddress.toLowerCase(), states: STATES, now }, json: true,
      });
      if (!rows.length) return null;
      const row = rows[0] as any;
      const claim = { operationId: row.operation_id as string, leaseId: randomUUID(),
        attempt: Math.min(numeric(row.reconciliation_attempts ?? 0) + 1, 1_000_000) };
      tx.update('ChainOperations', { operation_id: claim.operationId, reconciliation_lease_id: claim.leaseId,
        reconciliation_lease_until: new Date(now.getTime() + 60_000), reconciliation_attempts: claim.attempt });
      return claim;
    });
  }

  private async leasedRow(tx: Transaction, claim: ReconciliationClaim): Promise<{ row: any; now: Date } | null> {
    const now = await this.now(tx);
    const [rows] = await tx.run({ sql: `SELECT * FROM ChainOperations WHERE operation_id = @id
      AND environment = @env AND reconciliation_lease_id = @lease AND reconciliation_lease_until > @now`,
      params: { id: claim.operationId, env: this.store.environment, lease: claim.leaseId, now }, json: true });
    return rows.length ? { row: rows[0], now } : null;
  }

  async release(claim: ReconciliationClaim, delayMs: number): Promise<boolean> {
    if (!Number.isSafeInteger(delayMs) || delayMs < 1000 || delayMs > 900_000) throw new Error('invalid reconciliation delay');
    return runSpannerTransaction(this.store.database, async (tx) => {
      const current = await this.leasedRow(tx, claim);
      if (!current) return false;
      tx.update('ChainOperations', { operation_id: claim.operationId, reconciliation_lease_id: null,
        reconciliation_lease_until: null, next_check_at: new Date(current.now.getTime() + delayMs) });
      return true;
    });
  }

  /** Projection, event, and completion marker are one transaction, fenced by lease and journal revision. */
  async complete(claim: ReconciliationClaim, op: ChainOperation, projection: EntitlementProjection | null): Promise<boolean> {
    validateOperation(op);
    if (op.operationId !== claim.operationId || op.network === 'mainnet' || !FINAL_STATES.includes(op.state)) throw new Error('invalid projection operation');
    const p = projection === null ? null : entitlementSchema.parse(projection);
    return runSpannerTransaction(this.store.database, async (tx) => {
      const current = await this.leasedRow(tx, claim);
      if (!current) return false;
      const { row, now } = current;
      const e = op.evidence!;
      if (row.projection_completed_at || numeric(row.version) !== op.version || row.request_digest !== op.requestDigest ||
          row.state !== op.state || row.tx_id !== e.txId || row.block_hash !== e.blockHash || numeric(row.block_height) !== e.blockHeight) {
        return false;
      }
      let outcome = 'not_applicable';
      if (p) {
        const [previous] = await tx.run({ sql: `SELECT * FROM RightsEntitlements
          WHERE network = @network AND contract_address = @contract AND entitlement_id = @id`,
          params: { network: op.network, contract: op.contractAddress, id: p.entitlementId }, json: true });
        const old = previous[0] as any;
        const height = e.blockHeight!;
        if (old && height < numeric(old.last_block_height)) outcome = 'unchanged';
        else if (old && height === numeric(old.last_block_height)) {
          if (numeric(old.epoch) !== p.epoch || old.status !== p.status || old.issuer_id !== p.issuerId ||
              old.transferable !== p.transferable || old.reprintable !== p.reprintable || old.parent_consumption !== p.parentConsumption) {
            throw new Error('conflicting entitlement facts for one block');
          }
          outcome = 'unchanged';
        } else {
          if (old && (p.epoch < numeric(old.epoch) || old.status === 'revoked' && p.status !== 'revoked' ||
              old.issuer_id !== p.issuerId || old.transferable !== p.transferable || old.reprintable !== p.reprintable ||
              old.parent_consumption !== p.parentConsumption)) throw new Error('nonmonotonic entitlement projection');
          const version = numeric(old?.projection_version ?? 0) + 1;
          // Never manufacture a private controller or asset link from the operation's owner/subject.
          // Reading and preserving an existing link in this transaction serializes with privacy erasure.
          const record = { network: op.network, contract_address: op.contractAddress, entitlement_id: p.entitlementId,
            issuer_id: p.issuerId, epoch: p.epoch, status: p.status, transferable: p.transferable, reprintable: p.reprintable,
            parent_consumption: p.parentConsumption, asset_id: old?.asset_id ?? null,
            controller_subject_ref: old && p.epoch === numeric(old.epoch) && p.status === 'active' ? old.controller_subject_ref : null,
            last_tx_id: e.txId, last_block_height: height, finalized_at: new Date(op.history.find((h) => h.state === 'Finalized')!.at),
            updated_at: Spanner.COMMIT_TIMESTAMP, projection_version: version };
          if (old) tx.update('RightsEntitlements', record); else tx.insert('RightsEntitlements', record);
          const id = randomUUID();
          tx.insert('OutboxEvents', {
            shard: parseInt(createHash('sha256').update(id).digest('hex').slice(0, 8), 16) % 16,
            event_id: id, event_type: 'rights.entitlement.projected', schema_version: '1',
            aggregate_type: 'rights_entitlement', aggregate_id: entitlementAggregateId(op.network, op.contractAddress, p.entitlementId),
            aggregate_version: version, occurred_at: now, environment: this.store.environment,
            actor_ref: 'service:chain-reconciler', correlation_id: op.operationId, causation_id: null, privacy_class: 'restricted',
            payload: JSON.stringify({ network: op.network, contract_address: op.contractAddress, entitlement_id: p.entitlementId,
              epoch: String(p.epoch), tx_id: e.txId, block_height: String(height), block_hash: e.blockHash }),
            status: 'pending', attempts: 0, next_attempt_at: now, created_at: Spanner.COMMIT_TIMESTAMP,
          });
          if (op.circuit === 'attestManufacture' && !old) await this.attested(tx, op, p.entitlementId, now);
          outcome = old ? 'advanced' : 'inserted';
        }
      }
      tx.update('ChainOperations', { operation_id: claim.operationId, projection_completed_at: now, projection_outcome: outcome,
        reconciliation_lease_id: null, reconciliation_lease_until: null, next_check_at: null });
      return true;
    });
  }

  /**
   * A manufactured unit's first projection, linked to the app's reprint job by the
   * consumption nullifier it attests (never by the operation owner). A unit outside
   * the app workflow emits nothing. Same transaction as the projection, so it is
   * emitted at most once.
   */
  private async attested(tx: Transaction, op: ChainOperation, childEntitlementId: string, now: Date): Promise<void> {
    const [nullifier, unit] = op.args;
    if (nullifier?.t !== 'bytes' || unit?.t !== 'uint') throw new Error('invalid manufacture arguments');
    const [jobs] = await tx.run({ sql: `SELECT job_id FROM ReprintJobs WHERE network = @network AND consumption_nullifier = @nullifier LIMIT 2`,
      params: { network: op.network, nullifier: nullifier.v }, json: true });
    if (jobs.length !== 1) return;
    const jobId = (jobs[0] as { job_id: string }).job_id;
    const unitIndex = Number(unit.v);
    const id = randomUUID();
    tx.insert('OutboxEvents', {
      shard: parseInt(createHash('sha256').update(id).digest('hex').slice(0, 8), 16) % 16,
      event_id: id, event_type: 'reprint.attested', schema_version: '1',
      aggregate_type: 'reprint_job', aggregate_id: jobId, aggregate_version: unitIndex + 1, occurred_at: now,
      environment: this.store.environment, actor_ref: 'service:chain-reconciler', correlation_id: op.operationId,
      causation_id: null, privacy_class: 'member_private',
      payload: JSON.stringify({ job_id: jobId, network: op.network, child_entitlement_id: childEntitlementId, unit_index: unitIndex }),
      status: 'pending', attempts: 0, next_attempt_at: now, created_at: Spanner.COMMIT_TIMESTAMP,
    });
  }
}
