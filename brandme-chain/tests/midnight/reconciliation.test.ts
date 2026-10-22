import { randomUUID } from 'node:crypto';
import express from 'express';
import type { Server } from 'node:http';
import { InMemoryOperationStore, newOperation, transition, type ChainEvidence } from '../../src/midnight/operations.js';
import { OperationReconciler, IndexerTransactionLookup } from '../../src/midnight/reconciler.js';
import { createOperationsRouter } from '../../src/routes/operations.js';
import { preprodEndpoints } from '../../src/midnight/network.js';
import { NodeRpcFinalityOracle } from '../../src/midnight/adapter.js';

const contractAddress = 'ab'.repeat(32);
const endpoints = preprodEndpoints('nightpreprodtestonly123');
const token = 'test-service-credential-'.repeat(3);
const owner = randomUUID();
const txId = 'tx-identifier-bound-before-broadcast';
const evidence: ChainEvidence = { txId, txHash: 'aa'.repeat(32), blockHash: 'bb'.repeat(32),
  blockHeight: 12, status: 'SucceedEntirely', observedAt: new Date().toISOString() };
let store: InMemoryOperationStore;
let lookup: { lookup: ReturnType<typeof vi.fn> };
let finality: { isFinal: ReturnType<typeof vi.fn> };
let reconciler: OperationReconciler;
let id: string;
let server: Server;
let base: string;
beforeEach(async () => {
  store = new InMemoryOperationStore();
  let op = await store.create(newOperation({ network: 'preprod', contractAddress, circuit: 'proveControl', args: [], ownerRef: owner }));
  op = (await store.update(transition(op, 'Proving'), op.version))!;
  op = (await store.update(transition(op, 'Reconciling', { evidence: { txId, observedAt: evidence.observedAt } }), op.version))!;
  id = op.operationId;
  lookup = { lookup: vi.fn().mockResolvedValue(evidence) };
  finality = { isFinal: vi.fn().mockResolvedValue({ final: true, finalizedHeadHeight: 15 }) };
  reconciler = new OperationReconciler({ store, endpoints, contractAddress, lookup, finality });
  const app = express(); app.use(express.json());
  app.use(createOperationsRouter({ token, store, reconciler, network: 'preprod', contractAddress }));
  server = app.listen(0, '127.0.0.1');
  await new Promise<void>((resolve) => server.once('listening', resolve));
  base = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
});
afterEach(async () => { await new Promise<void>((resolve) => { server.close(() => resolve()); server.closeAllConnections(); }); });
const call = (path: string, options: RequestInit = {}, member = owner) => fetch(`${base}${path}`, {
  ...options, headers: { authorization: `Bearer ${token}`, 'x-subject-ref': member, 'content-type': 'application/json', ...options.headers },
});
const reconcile = (extra = {}) => call('/operations/reconcile', { method: 'POST', body: JSON.stringify({ operation_id: id, tx_id: txId, network: 'preprod', ...extra }) });

describe('authenticated operation status and reconciliation', () => {
  it('requires the server credential before trusting a member header', async () => {
    expect((await fetch(`${base}/operations/${id}`, { headers: { 'x-subject-ref': owner } })).status).toBe(401);
    expect((await call(`/operations/${id}`, { headers: { authorization: 'Bearer member-token' } })).status).toBe(401);
    expect((await call(`/operations/${id}`, {}, 'not-a-member')).status).toBe(401);
  });
  it('does not disclose or mutate another member’s operation', async () => {
    expect((await call(`/operations/${id}`, {}, randomUUID())).status).toBe(404);
    expect((await call('/operations/reconcile', { method: 'POST', body: JSON.stringify({ operation_id: id, tx_id: txId, network: 'preprod' }) }, randomUUID())).status).toBe(404);
    expect(lookup.lookup).not.toHaveBeenCalled();
  });
  it('returns a bounded status without arguments, owner or idempotency key', async () => {
    const r = await call(`/operations/${id}`); expect(r.status).toBe(200);
    const body = await r.json();
    expect(body).toMatchObject({ id, network: 'preprod', state: 'reconciling', operation: 'prove_control' });
    expect(body.args).toBeUndefined(); expect(JSON.stringify(body)).not.toContain(owner);
  });
  it('refuses an unbound client transaction hint and caller-supplied proof', async () => {
    expect((await reconcile({ tx_id: 'unrelated-transaction' })).status).toBe(409);
    expect((await reconcile({ evidence })).status).toBe(400);
    expect((await reconcile({ network: 'preview' })).status).toBe(409);
    expect(lookup.lookup).not.toHaveBeenCalled();
  });
  it('finalizes from matching indexer data and canonical finality, and replay has no effect', async () => {
    expect((await (await reconcile()).json()).state).toBe('finalized');
    expect((await (await reconcile()).json()).state).toBe('finalized');
    expect(lookup.lookup).toHaveBeenCalledTimes(1);
    expect(finality.isFinal).toHaveBeenCalledWith(12, evidence.blockHash);
  });
  it('retains unresolved operations through restarts without any submit capability', async () => {
    lookup.lookup.mockResolvedValue(null);
    expect((await reconciler.reconcile(id)).state).toBe('Reconciling');
    lookup.lookup.mockResolvedValue(evidence);
    expect((await new OperationReconciler({ store, endpoints, contractAddress, lookup, finality }).reconcile(id)).state).toBe('Finalized');
  });
  it('does not finalize pending finality or unrelated evidence', async () => {
    lookup.lookup.mockResolvedValue({ ...evidence, txId: 'another' });
    expect((await reconcile()).status).toBe(503);
    expect((await store.get(id))!.state).toBe('Reconciling');
    lookup.lookup.mockResolvedValue(evidence); finality.isFinal.mockResolvedValue({ final: false, finalizedHeadHeight: 11 });
    expect((await (await reconcile()).json()).state).toBe('observed');
  });
  it('keeps a rejection pending until its block is finalized', async () => {
    lookup.lookup.mockResolvedValue({ ...evidence, status: 'FailEntirely' });
    finality.isFinal.mockResolvedValue({ final: false, finalizedHeadHeight: 11 });
    expect((await (await reconcile()).json()).state).toBe('reconciling');
    finality.isFinal.mockResolvedValue({ final: true, finalizedHeadHeight: 12 });
    expect((await (await reconcile()).json()).state).toBe('failed');
  });
  it('refuses terminal failure without complete rejected block evidence', async () => {
    const current = (await store.get(id))!;
    await expect(store.update(transition(current, 'Failed', { evidence: { ...current.evidence!,
      status: 'FailEntirely', finalizedHeadHeight: 12 } }), current.version)).rejects.toThrow(/block evidence/);
    expect((await store.get(id))!.state).toBe('Reconciling');
  });
  it('records rejected chain outcomes and hides provider secrets on errors', async () => {
    lookup.lookup.mockRejectedValue(new Error(`provider failed ${token}`));
    const response = await reconcile(); expect(response.status).toBe(503); expect(await response.text()).not.toContain(token);
    lookup.lookup.mockResolvedValue({ ...evidence, status: 'FailEntirely' });
    expect((await (await reconcile()).json()).state).toBe('failed');
    expect(finality.isFinal).toHaveBeenCalledTimes(1);
  });
});

describe('bounded provider lookups', () => {
  const tx = { hash: 'aa'.repeat(32), block: { height: 12, hash: 'bb'.repeat(32) }, identifiers: [txId], transactionResult: { status: 'SUCCESS' } };
  it('queries the persisted identifier and verifies it is present in the returned row', async () => {
    const doFetch = vi.fn().mockResolvedValue(Response.json({ data: { transactions: [tx] } }));
    expect(await new IndexerTransactionLookup(endpoints, doFetch).lookup(txId)).toMatchObject({ txId, status: 'SucceedEntirely', blockHeight: 12 });
    const init = doFetch.mock.calls[0]![1];
    expect(JSON.parse(init.body).variables.offset.identifier).toBe(txId); expect(init.redirect).toBe('error');
    doFetch.mockResolvedValue(Response.json({ data: { transactions: [{ ...tx, identifiers: ['unrelated'] }] } }));
    await expect(new IndexerTransactionLookup(endpoints, doFetch).lookup(txId)).rejects.toThrow(/identifier/);
  });
  it('rejects GraphQL errors and malformed or oversized provider responses', async () => {
    for (const body of [{ data: { transactions: [tx] }, errors: [{}] }, { data: { transactions: [{ ...tx, transactionResult: { status: 'NEW_STATUS' } }] } }]) {
      await expect(new IndexerTransactionLookup(endpoints, async () => Response.json(body)).lookup(txId)).rejects.toThrow();
    }
    await expect(new IndexerTransactionLookup(endpoints, async () => new Response('x'.repeat(1024 * 1024 + 1))).lookup(txId)).rejects.toThrow(/too large/);
  });
  it('requires the observed block to match the canonical finalized chain', async () => {
    const doFetch = vi.fn().mockResolvedValueOnce(Response.json({ result: '0xhead' }))
      .mockResolvedValueOnce(Response.json({ result: { number: '0xf' } }))
      .mockResolvedValueOnce(Response.json({ result: `0x${'cc'.repeat(32)}` }));
    expect(await new NodeRpcFinalityOracle('http://node.example', doFetch).isFinal(12, evidence.blockHash!))
      .toEqual({ final: false, finalizedHeadHeight: 15 });
  });
});

describe('unfinalized block reorganization', () => {
  it('rechecks observed transactions and recovers when their block changes', async () => {
    finality.isFinal.mockResolvedValue({ final: false, finalizedHeadHeight: 11 });
    expect((await reconciler.reconcile(id)).state).toBe('Observed');
    lookup.lookup.mockResolvedValue({ ...evidence, blockHash: 'cc'.repeat(32), blockHeight: 13 });
    expect((await reconciler.reconcile(id)).state).toBe('Reconciling');
    finality.isFinal.mockResolvedValue({ final: true, finalizedHeadHeight: 15 });
    expect(await reconciler.reconcile(id)).toMatchObject({ state: 'Finalized', evidence: { blockHash: 'cc'.repeat(32), blockHeight: 13 } });
  });
  it('does not finalize an observed transaction that disappears from the indexer', async () => {
    finality.isFinal.mockResolvedValue({ final: false, finalizedHeadHeight: 11 });
    expect((await reconciler.reconcile(id)).state).toBe('Observed');
    lookup.lookup.mockResolvedValue(null);
    expect((await reconciler.reconcile(id)).state).toBe('Reconciling');
    expect(finality.isFinal).toHaveBeenCalledTimes(1);
  });
});
