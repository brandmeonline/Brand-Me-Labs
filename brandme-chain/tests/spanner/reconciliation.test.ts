import { randomUUID } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { operationDatabase, SpannerOperationStore } from '../../src/midnight/spanner-store.js';
import { SpannerReconciliationQueue, entitlementAggregateId } from '../../src/midnight/reconciliation-queue.js';
import { ReconciliationWorker } from '../../src/midnight/reconciliation-worker.js';
import { OperationReconciler } from '../../src/midnight/reconciler.js';
import { FinalizedEntitlementProjector, IndexerFinalizedLedgerReader, type EntitlementProjection } from '../../src/midnight/projection.js';
import { newOperation, transition, type ChainOperation } from '../../src/midnight/operations.js';
import { localEndpoints } from '../../src/midnight/network.js';
import { Actor, RightsSimulator, registerIssuer, issue } from '../support/scenario.js';
import { random32, toHex } from '../../src/midnight/bytes.js';

const databaseId = `queue-${randomUUID().slice(0, 8)}`;
const setup = (action: string) => execFileSync(process.env.BRANDME_PYTHON ?? 'python3',
  [fileURLToPath(new URL('../support/store-database.py', import.meta.url)), action, databaseId],
  { env: { ...process.env, BRANDME_MODE: 'development' }, stdio: 'pipe' });
const db = operationDatabase('test-project', 'brandme-instance', databaseId);
const store = new SpannerOperationStore(db, 'development');
const queue = new SpannerReconciliationQueue(store);
const endpoints = localEndpoints({ node: 9944, indexer: 8088 });
let contract: string;
const hash = 'cd'.repeat(32);
const projection = (): EntitlementProjection => ({ entitlementId: toHex(random32()), issuerId: 'ab'.repeat(32),
  epoch: 1, status: 'active', transferable: true, reprintable: false, parentConsumption: null });
beforeAll(async () => { setup('create'); await store.initialize(); });
beforeEach(() => { contract = toHex(random32()); });
afterAll(async () => { setup('validate-events'); await db.close(); setup('drop'); });
async function pending(circuit = 'revokeEntitlement', args: unknown[] = [random32()]) {
  let op = await store.create(newOperation({ network: 'undeployed', contractAddress: contract, circuit, args, ownerRef: randomUUID() }));
  op = (await store.update(transition(op, 'Proving'), op.version))!;
  return (await store.update(transition(op, 'Reconciling', { evidence: { txId: randomUUID(), observedAt: new Date().toISOString() } }), op.version))!;
}
async function finalized(height = 12) {
  let op = await pending();
  op = (await store.update(transition(op, 'Observed', { evidence: { ...op.evidence!, blockHeight: height, blockHash: hash, status: 'SucceedEntirely' } }), op.version))!;
  return (await store.update(transition(op, 'Finalized', { evidence: { ...op.evidence!, finalizedHeadHeight: height } }), op.version))!;
}
const claim = () => queue.claim('undeployed', contract);
const rows = async (table: string, op: ChainOperation) => (await db.run({ sql: `SELECT * FROM ${table} WHERE contract_address = @c`, params: { c: op.contractAddress }, json: true }))[0] as any[];
const progress = async (id: string) => (await db.run({ sql: 'SELECT * FROM ChainOperations WHERE operation_id = @id', params: { id }, json: true }))[0][0] as any;

it('claims at most once across replicas and scopes by environment, network and contract', async () => {
  const op = await pending();
  expect(await queue.claim('preview', contract)).toBeNull();
  expect(await queue.claim('undeployed', toHex(random32()))).toBeNull();
  expect(await new SpannerReconciliationQueue(new SpannerOperationStore(db, 'sandbox')).claim('undeployed', contract)).toBeNull();
  const claimed = (await Promise.all([claim(), claim(), claim()])).filter(Boolean);
  expect(claimed).toHaveLength(1); expect(claimed[0]!.operationId).toBe(op.operationId);
  await expect(queue.claim('mainnet', contract)).rejects.toThrow(/Mainnet/);
});

it('backs off unresolved work, recovers an expired lease after restart, and fences the former worker', async () => {
  const op = await finalized(); const first = (await claim())!;
  await db.table('ChainOperations').update({ operation_id: op.operationId, reconciliation_lease_until: new Date(0) });
  const reopened = new SpannerReconciliationQueue(new SpannerOperationStore(db, 'development'));
  const second = (await reopened.claim('undeployed', contract))!;
  expect(second.leaseId).not.toBe(first.leaseId); expect(second.attempt).toBe(2);
  expect(await queue.release(first, 15_000)).toBe(false);
  expect(await queue.complete(first, op, projection())).toBe(false);
  expect(await reopened.release(second, 60_000)).toBe(true);
  expect(await claim()).toBeNull();
  expect((await progress(op.operationId)).projection_completed_at).toBeNull();
});

it('atomically commits an entitlement, registered event and completion without owner/asset fabrication', async () => {
  const op = await finalized(); const lease = (await claim())!; const p = projection();
  expect(await queue.complete(lease, op, p)).toBe(true);
  expect(await queue.complete(lease, op, p)).toBe(false);
  expect(await claim()).toBeNull();
  const [ent] = await rows('RightsEntitlements', op);
  expect(ent).toMatchObject({ entitlement_id: p.entitlementId, controller_subject_ref: null, asset_id: null, epoch: 1, projection_version: 1 });
  const [events] = await db.run({ sql: "SELECT payload, aggregate_id FROM OutboxEvents WHERE correlation_id = @id AND event_type = 'rights.entitlement.projected'", params: { id: op.operationId }, json: true });
  expect(events).toHaveLength(1); expect(JSON.stringify(events)).not.toContain(op.ownerRef);
  expect((events[0] as any).aggregate_id).toBe(entitlementAggregateId(op.network, contract, p.entitlementId));
  expect((await progress(op.operationId)).projection_outcome).toBe('inserted');
});

it('serializes two final operations for the same entitlement without duplicate projection events', async () => {
  const a = await finalized(); const b = await finalized(); const p = projection();
  const leases = [(await claim())!, (await claim())!];
  const ops = new Map([a, b].map((o) => [o.operationId, o]));
  expect(await Promise.all(leases.map((lease) => queue.complete(lease, ops.get(lease.operationId)!, p)))).toEqual([true, true]);
  const [ent] = await rows('RightsEntitlements', a); expect(ent.projection_version).toBe(1);
  const [events] = await db.run({ sql: "SELECT event_id FROM OutboxEvents WHERE aggregate_id = @id", params: { id: entitlementAggregateId(a.network, contract, p.entitlementId) } });
  expect(events).toHaveLength(1);
});

it('preserves an existing link in the same epoch, drops it on transfer, and cannot restore erased links', async () => {
  const p = projection(); const a = await finalized(); await queue.complete((await claim())!, a, p);
  const key = { network: a.network, contract_address: contract, entitlement_id: p.entitlementId };
  await db.table('RightsEntitlements').update({ ...key, controller_subject_ref: a.ownerRef });
  const b = await finalized(13); await queue.complete((await claim())!, b, p);
  expect((await rows('RightsEntitlements', a))[0]!.controller_subject_ref).toBe(a.ownerRef);
  // Privacy erasure between claim and projection must win, even with the same owner on the operation.
  const c = await finalized(14); const lease = (await claim())!;
  await db.table('RightsEntitlements').update({ ...key, controller_subject_ref: null });
  await queue.complete(lease, c, p);
  expect((await rows('RightsEntitlements', a))[0]!.controller_subject_ref).toBeNull();
  await db.table('RightsEntitlements').update({ ...key, controller_subject_ref: a.ownerRef });
  const d = await finalized(15); await queue.complete((await claim())!, d, { ...p, epoch: 2 });
  expect((await rows('RightsEntitlements', a))[0]!.controller_subject_ref).toBeNull();
});

it('ignores stale blocks and refuses conflicting, decreasing or reactivated entitlement state', async () => {
  const p = projection(); const a = await finalized(20); await queue.complete((await claim())!, a, { ...p, epoch: 2, status: 'revoked' });
  const stale = await finalized(10); await queue.complete((await claim())!, stale, p);
  expect((await progress(stale.operationId)).projection_outcome).toBe('unchanged');
  for (const [height, value] of [[20, p], [21, { ...p, epoch: 1, status: 'revoked' }], [22, { ...p, epoch: 2 }]] as const) {
    const op = await finalized(height); const lease = (await claim())!;
    await expect(queue.complete(lease, op, value)).rejects.toThrow(/conflicting|nonmonotonic/);
    expect((await progress(op.operationId)).projection_completed_at).toBeNull();
    await queue.release(lease, 900_000);
  }
  expect((await rows('RightsEntitlements', a))[0]).toMatchObject({ status: 'revoked', epoch: 2, last_block_height: 20 });
});

it('rolls back projection and completion if its transactional outbox write fails', async () => {
  const op = await finalized(); const lease = (await claim())!;
  const original = db.getTransaction.bind(db);
  const intercept = vi.spyOn(db, 'getTransaction').mockImplementationOnce(async () => {
    const result = await original(); const tx = result[0]; const insert = tx.insert.bind(tx);
    vi.spyOn(tx, 'insert').mockImplementation((table, values) => {
      if (table === 'OutboxEvents') throw new Error('outbox unavailable');
      return insert(table, values);
    }); return result;
  });
  try { await expect(queue.complete(lease, op, projection())).rejects.toThrow(/outbox unavailable/); }
  finally { intercept.mockRestore(); }
  expect(await rows('RightsEntitlements', op)).toHaveLength(0);
  expect((await progress(op.operationId)).projection_completed_at).toBeNull();
  expect(await queue.complete(lease, op, projection())).toBe(true);
});

it('cannot resurrect an erased operation or commit against a changed journal revision', async () => {
  let op = await finalized(); const lease = (await claim())!;
  op = (await store.update(transition(op, 'HandoverPending'), op.version))!;
  expect(await queue.complete(lease, { ...op, version: op.version - 1, state: 'Finalized', history: op.history.slice(0, -1), updatedAt: op.history.at(-2)!.at }, projection())).toBe(false);
  await db.table('ChainOperations').deleteRows([op.operationId]);
  expect(await queue.complete(lease, op, projection())).toBe(false);
  expect(await rows('RightsEntitlements', op)).toHaveLength(0);
});

it('runs the compiled-ledger projection through the actual worker and durable journal', async () => {
  const sim = new RightsSimulator(); contract = sim.address;
  const issuer = new Actor('issuer'); const issuerId = registerIssuer(sim, issuer);
  const { eid, issuanceId } = issue(sim, issuer, issuerId, new Actor('holder'));
  const op = await pending('issueEntitlement', [issuerId, issuanceId]);
  const finality = { isFinal: async () => ({ final: true, finalizedHeadHeight: 15 }) };
  const reconciler = new OperationReconciler({ store, endpoints, contractAddress: contract, finality,
    lookup: { lookup: async () => ({ ...op.evidence!, blockHeight: 12, blockHash: hash, status: 'SucceedEntirely' }) } });
  const reader = new IndexerFinalizedLedgerReader(endpoints, async () => Response.json({ data: { contractAction: {
    address: contract, state: sim.serializedState(), transaction: { block: { height: 12, hash } },
  } } }));
  const projector = new FinalizedEntitlementProjector({ network: op.network, contractAddress: contract, reader, finality });
  const worker = new ReconciliationWorker({ network: op.network, contractAddress: contract, store, queue, reconciler, projector });
  const first = worker.tick(); expect(worker.tick()).toBe(first);
  expect(await first).toEqual({ processed: 1, errors: 0 });
  expect((await store.get(op.operationId))!.state).toBe('Finalized');
  expect((await rows('RightsEntitlements', op))[0]).toMatchObject({ entitlement_id: toHex(eid), controller_subject_ref: null });
  expect(await worker.tick()).toEqual({ processed: 0, errors: 0 });
  await worker.stop();
});

it('retries provider failures after a durable delay without leaking their message or submitting anything', async () => {
  const op = await pending();
  const worker = new ReconciliationWorker({ network: op.network, contractAddress: contract, store, queue,
    reconciler: { reconcile: async () => { throw new Error('secret-provider-token'); } },
    projector: { project: async () => { throw new Error('must not project'); } } });
  expect(await worker.tick()).toEqual({ processed: 1, errors: 1 });
  expect(await worker.tick()).toEqual({ processed: 0, errors: 0 });
  expect((await store.get(op.operationId))!.state).toBe('Reconciling');
  expect(JSON.stringify(await progress(op.operationId))).not.toContain('secret-provider-token');
  await worker.stop();
});
