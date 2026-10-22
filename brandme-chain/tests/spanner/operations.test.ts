import { randomUUID } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { SpannerOperationStore, operationDatabase } from '../../src/midnight/spanner-store.js';
import { newOperation, transition, requestDigest, type ChainOperation } from '../../src/midnight/operations.js';

const databaseId = `chain-${randomUUID().slice(0, 8)}`;
const setup = (action: string) => execFileSync(process.env.BRANDME_PYTHON ?? 'python3',
  [fileURLToPath(new URL('../support/store-database.py', import.meta.url)), action, databaseId],
  { env: { ...process.env, BRANDME_MODE: 'development' }, stdio: 'pipe' });
const db = operationDatabase('test-project', 'brandme-instance', databaseId);
const store = new SpannerOperationStore(db, 'development');
const op = (extra: Partial<Parameters<typeof newOperation>[0]> = {}) => newOperation({
  network: 'preprod', contractAddress: 'ab'.repeat(32), circuit: 'proveControl', args: [1n],
  ownerRef: randomUUID(), subjectRef: randomUUID(), idempotencyKey: randomUUID(), ...extra,
});
beforeAll(async () => { setup('create'); await store.initialize(); });
afterAll(async () => { await db.close(); setup('drop'); });

describe('Spanner operation journal against real migrations', () => {
  it('survives a new client and preserves arguments, history, dates and evidence', async () => {
    let a = await store.create(op({ args: [new Uint8Array([1, 2]), 9999999999999999999n, true] }));
    a = (await store.update(transition(a, 'Proving'), a.version))!;
    a = (await store.update(transition(a, 'Reconciling', { evidence: { txId: 'bound-transaction', observedAt: new Date().toISOString() } }), a.version))!;
    const reopenedDb = operationDatabase('test-project', 'brandme-instance', databaseId);
    try { expect(await new SpannerOperationStore(reopenedDb, 'development').get(a.operationId)).toEqual(a); }
    finally { await reopenedDb.close(); }
  });

  it('serializes concurrent identical requests to one durable operation', async () => {
    const a = op();
    const results = await Promise.all(Array.from({ length: 6 }, () => store.create({ ...a, operationId: randomUUID() })));
    expect(new Set(results.map((r) => r.operationId)).size).toBe(1);
  });

  it('scopes idempotency by owner, network, contract and environment', async () => {
    const a = op({ subjectRef: undefined }); await store.create(a);
    for (const extra of [{ ownerRef: randomUUID() }, { network: 'preview' as const }, { contractAddress: 'cd'.repeat(32) }]) {
      const b = newOperation({ ...a, ...extra, args: [1n] });
      expect((await store.create(b)).operationId).toBe(b.operationId);
    }
    const sandbox = new SpannerOperationStore(db, 'sandbox');
    expect(await sandbox.get(a.operationId)).toBeNull();
    const b = newOperation({ ...a, args: [1n] });
    expect((await sandbox.create(b)).operationId).toBe(b.operationId);
  });

  it('rejects idempotency reuse with a different subject or arguments', async () => {
    const a = op(); await store.create(a);
    for (const extra of [{ subjectRef: randomUUID() }, { args: [2n] }]) {
      await expect(store.create(newOperation({ ...a, args: [1n], ...extra }))).rejects.toThrow(/idempotency/);
    }
  });

  it('serializes conflicting subject commands across different owners', async () => {
    const subjectRef = randomUUID();
    const results = await Promise.allSettled(Array.from({ length: 4 }, () => store.create(op({ subjectRef }))));
    expect(results.filter((r) => r.status === 'fulfilled')).toHaveLength(1);
    expect(results.filter((r) => r.status === 'rejected')).toHaveLength(3);
  });

  it('allows only one compare-and-set and refuses changed immutable fields', async () => {
    const a = await store.create(op());
    const results = await Promise.all([store.update(transition(a, 'Proving'), 1), store.update(transition(a, 'Cancelled'), 1)]);
    expect(results.filter(Boolean)).toHaveLength(1);
    const current = (await store.get(a.operationId))!;
    const next = current.state === 'Proving' ? transition(current, 'Failed') : { ...current, version: current.version + 1 };
    const altered = { ...next, ownerRef: randomUUID() }; altered.requestDigest = requestDigest(altered);
    await expect(store.update(altered, current.version)).rejects.toThrow();
  });

  it('releases a terminal subject lock and refuses noninitial or ownerless creation', async () => {
    const a = await store.create(op());
    await store.update(transition(a, 'Cancelled'), a.version);
    expect((await store.create(op({ subjectRef: a.subjectRef }))).state).toBe('ReadyToProve');
    await expect(store.create(transition(op(), 'Proving'))).rejects.toThrow();
    await expect(store.create(op({ ownerRef: undefined }))).rejects.toThrow(/owner/);
    await expect(store.create(op({ network: 'mainnet' }))).rejects.toThrow(/Mainnet/);
  });

  it('commits observation events with the row and emits no duplicate on a stale revision', async () => {
    let a = await store.create(op());
    const save = async (next: ChainOperation) => { a = (await store.update(next, a.version))!; };
    await save(transition(a, 'Proving'));
    await save(transition(a, 'Reconciling', { evidence: { txId: 'bound-transaction', observedAt: new Date().toISOString() } }));
    await save(transition(a, 'Observed', { evidence: { ...a.evidence!, blockHeight: 12, blockHash: 'cd'.repeat(32), status: 'SucceedEntirely' } }));
    const finalized = transition(a, 'Finalized', { evidence: { ...a.evidence!, finalizedHeadHeight: 12 } });
    await save(finalized);
    expect(await store.update(finalized, a.version - 1)).toBeNull();
    const [rows] = await db.run({ sql: 'SELECT payload FROM OutboxEvents WHERE aggregate_id = @id', params: { id: a.operationId }, json: true });
    expect(rows).toHaveLength(2);
    expect(JSON.stringify(rows)).not.toContain(a.ownerRef);
  });

  it('honors deletion freezes at command creation and immediately before broadcast', async () => {
    const a = await store.create(op());
    const proving = (await store.update(transition(a, 'Proving'), a.version))!;
    await db.table('ProcessingFreezes').insert({ subject_ref: a.ownerRef, category: 'rights.operations',
      reason: 'deletion', deletion_job_id: randomUUID(), created_at: new Date() });
    await expect(store.create(op({ ownerRef: a.ownerRef }))).rejects.toThrow(/frozen/);
    await expect(store.update(transition(proving, 'Reconciling', { evidence: { txId: 'never-broadcast', observedAt: new Date().toISOString() } }), proving.version))
      .rejects.toThrow(/frozen/);
    expect((await store.update(transition(proving, 'Failed'), proving.version))!.state).toBe('Failed');
  });

  it('rejects stale work after a deletion tombstone without blocking fresh commands', async () => {
    const a = op();
    await db.table('DeletionTombstones').insert({ subject_ref: a.ownerRef, category: 'rights.operations',
      tombstone_id: randomUUID(), deletion_job_id: randomUUID(), record_keys: [], created_at: new Date(a.createdAt) });
    await expect(store.create(a)).rejects.toThrow(/deleted/);
    expect((await store.create(op({ ownerRef: a.ownerRef }))).ownerRef).toBe(a.ownerRef);
  });
});
