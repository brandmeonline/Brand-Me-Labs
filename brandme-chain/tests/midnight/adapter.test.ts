/**
 * RightsAdapter behaviour without a network. `submit` is replaced by a
 * test double that executes the REAL compiled circuit (RightsSimulator) with
 * the session's private state, then passes through the adapter's guarded
 * wallet (balanceTx) and the wallet's submitTx — the same order as
 * submitCallTxAsync (execute → prove → balance → submit).
 */
import { MemoryLevel } from 'memory-level';
import { RightsAdapter, type ConnectedWallet, type FinalityOracle, buildProviders } from '../../src/midnight/adapter.js';
import { InMemoryOperationStore } from '../../src/midnight/operations.js';
import { PRIVATE_STATE_ID, PrivateStateSession } from '../../src/midnight/private-state.js';
import { PUBLIC_ENDPOINTS, WrongNetworkError, WritesNotAuthorizedError, mainnetEndpoints, type MidnightEndpoints } from '../../src/midnight/network.js';
import { Actor, RightsSimulator, issue, prepareHolder, registerIssuer } from '../support/scenario.js';
import { random32, toHex } from '../../src/midnight/bytes.js';
import { withSecret } from '../../src/midnight/rights-contract.js';

const CONTRACT = 'cc'.repeat(32);

function harness(opts: { endpoints?: MidnightEndpoints; walletNetwork?: string; watch?: 'ok' | 'fail' | 'hang' } = {}) {
  const endpoints = opts.endpoints ?? PUBLIC_ENDPOINTS.preprod;
  const sim = new RightsSimulator(endpoints.networkId);
  const issuer = new Actor('issuer');
  const iid = registerIssuer(sim, issuer);
  const member = new Actor('member');
  const { eid } = issue(sim, issuer, iid, member);

  const dbs = new Map<string, MemoryLevel<string, string>>();
  let account = 'acct-member';
  const submitted: string[] = [];
  const wallet: ConnectedWallet = {
    walletProvider: {
      getCoinPublicKey: () => '00'.repeat(32) as never,
      getEncryptionPublicKey: () => '00'.repeat(32) as never,
      balanceTx: async (tx) => tx as never,
    },
    midnightProvider: { submitTx: async () => { const id = `tx-${submitted.length}`; submitted.push(id); return id; } },
    networkId: () => opts.walletNetwork ?? endpoints.networkId,
    accountId: () => account,
  };
  const session = new PrivateStateSession({
    network: endpoints.networkId, contractAddress: CONTRACT, accountId: 'acct-member',
    passwordProvider: () => 'Storage-Pass-2026!', levelFactory: (name) => { if (!dbs.has(name)) dbs.set(name, new MemoryLevel<string, string>()); return dbs.get(name) as never; },
  });
  const store = new InMemoryOperationStore();
  let finalHead = 0;
  const finality: FinalityOracle = { isFinal: async (h) => ({ final: finalHead >= h, finalizedHeadHeight: finalHead }) };
  let duringProve: () => void = () => {};

  const providers = {
    privateStateProvider: session.stateProvider,
    publicDataProvider: {
      watchForTxData: async (txId: string) => {
        if (opts.watch === 'hang') return new Promise(() => {});
        return { txId, txHash: `h-${txId}`, blockHeight: 10, blockHash: `b-${txId}`, status: opts.watch === 'fail' ? 'FailEntirely' : 'SucceedEntirely' };
      },
    },
    walletProvider: wallet.walletProvider,
    midnightProvider: wallet.midnightProvider,
  } as never;

  const submit = (async (prov: { walletProvider: { balanceTx: (t: unknown) => Promise<unknown> }; midnightProvider: { submitTx: (t: unknown) => Promise<string> } }, o: { circuitId: string; args: unknown[] }) => {
    const ps = (await prov && (await session.stateProvider.get(PRIVATE_STATE_ID)))!;
    const actor = new Actor('exec', ps);
    sim.call(actor, o.circuitId as never, ...o.args); // throws on failed assert / missing witness — like local execution
    duringProve();
    const balanced = await prov.walletProvider.balanceTx({});
    const txId = await prov.midnightProvider.submitTx(balanced);
    return { txId };
  }) as never;

  const adapter = new RightsAdapter({ endpoints, contractAddress: CONTRACT, providers, session, wallet, store, finality, submit, observeTimeoutMs: 50 });
  return {
    sim, issuer, iid, member, eid, session, store, adapter, submitted, wallet,
    setAccount: (a: string) => { account = a; },
    setFinalHead: (h: number) => { finalHead = h; },
    onProve: (f: () => void) => { duringProve = f; },
    async loadMember() { await session.save(member.privateState); },
  };
}

describe('RightsAdapter', () => {
  it('happy path: persisted → Proving → Submitted → Observed → Finalized only on finality evidence', async () => {
    const h = harness();
    await h.loadMember();
    const op = await h.adapter.prepare('proveControl', [h.eid, random32(), random32()], { subjectRef: toHex(h.eid) });
    expect(op.state).toBe('ReadyToProve');
    let done = await h.adapter.execute(op.operationId);
    expect(done.state).toBe('Observed');
    expect(done.evidence?.txId).toBe('tx-0');
    h.setFinalHead(10);
    done = await h.adapter.checkFinality(op.operationId);
    expect(done.state).toBe('Finalized');
    expect(done.history.map((x) => x.state)).toEqual(['ReadyToProve', 'Proving', 'Submitted', 'Observed', 'Finalized']);
  });

  it('replay of an operation on a different network is rejected before any state mutation', async () => {
    const pre = harness();
    await pre.loadMember();
    const op = await pre.adapter.prepare('proveControl', [pre.eid, random32(), random32()]);
    const preview = harness({ endpoints: PUBLIC_ENDPOINTS.preview });
    await preview.store.create(op); // attacker copies the persisted preprod operation into a preview deployment
    const before = preview.sim.snapshot();
    await expect(preview.adapter.execute(op.operationId)).rejects.toBeInstanceOf(WrongNetworkError);
    expect(preview.sim.snapshot()).toBe(before);
    expect(preview.submitted).toHaveLength(0);
    expect((await preview.store.get(op.operationId))!.state).toBe('ReadyToProve');
  });

  it('rejects a tampered operation (digest mismatch) before execution', async () => {
    const h = harness();
    await h.loadMember();
    const op = await h.adapter.prepare('proveControl', [h.eid, random32(), random32()]);
    const tampered = { ...op, args: [op.args[0]!, { t: 'bytes' as const, v: toHex(random32()) }, op.args[2]!] };
    await h.store.update(tampered, op.version);
    await expect(h.adapter.execute(op.operationId)).rejects.toThrow(/digest mismatch/);
    expect(h.submitted).toHaveLength(0);
  });

  it('wallet reporting the wrong network blocks execution', async () => {
    const h = harness({ walletNetwork: 'preview' });
    await h.loadMember();
    const op = await h.adapter.prepare('proveControl', [h.eid, random32(), random32()]);
    const before = h.sim.snapshot();
    await expect(h.adapter.execute(op.operationId)).rejects.toBeInstanceOf(WrongNetworkError);
    expect(h.sim.snapshot()).toBe(before);
  });

  it('account switch during proving aborts before submission; nothing is submitted', async () => {
    const h = harness();
    await h.loadMember();
    const op = await h.adapter.prepare('proveControl', [h.eid, random32(), random32()]);
    h.onProve(() => h.setAccount('acct-someone-else'));
    const r = await h.adapter.execute(op.operationId);
    expect(r.state).toBe('Failed');
    expect(r.failureReason).toBe('session_changed');
    expect(h.submitted).toHaveLength(0);
  });

  it('session lock during proving aborts before submission', async () => {
    const h = harness();
    await h.loadMember();
    const op = await h.adapter.prepare('proveControl', [h.eid, random32(), random32()]);
    h.onProve(() => { void h.session.lock(); });
    const r = await h.adapter.execute(op.operationId);
    expect(r.state).toBe('Failed');
    expect(h.submitted).toHaveLength(0);
  });

  it('invalid witness → Failed, contract state unchanged, private state restored', async () => {
    const h = harness();
    // Member's private state has the wrong secret for this entitlement.
    await h.session.save(withSecret(h.member.privateState, 'holder', h.eid, random32()));
    const ps0 = JSON.stringify(await h.session.load());
    const before = h.sim.snapshot();
    const op = await h.adapter.prepare('proveControl', [h.eid, random32(), random32()]);
    const r = await h.adapter.execute(op.operationId);
    expect(r.state).toBe('Failed');
    expect(r.failureReason).toBe('contract_precondition_failed');
    expect(h.sim.snapshot()).toBe(before);
    expect(JSON.stringify(await h.session.load())).toBe(ps0);
    expect(h.submitted).toHaveLength(0);
  });

  it('acceptTransfer uses an offer-specific pending secret; a failed accept restores private state', async () => {
    const h = harness();
    const bob = new Actor('bob');
    const epoch = h.sim.ledger().entitlements.lookup(h.eid).epoch;
    const pending = random32();
    const recipientCommitment = (await import('../../src/midnight/rights-contract.js')).commitments.holder(h.eid, epoch + 1n, pending, h.sim.binding);
    const oid = h.sim.call<Uint8Array>(h.member, 'offerTransfer', h.eid, random32(), recipientCommitment, BigInt(h.sim.now + 600), random32());
    // Session belongs to bob in this scenario.
    await h.session.save(bob.privateState);
    const wrong = await h.adapter.prepare('acceptTransfer', [oid]);
    const r1 = await h.adapter.execute(wrong.operationId, { privateStateOverride: (ps) => withSecret(ps, 'holder', h.eid, random32()) });
    expect(r1.state).toBe('Failed');
    expect(Object.keys((await h.session.load()).holderSecrets)).toHaveLength(0);
    const ok = await h.adapter.prepare('acceptTransfer', [oid]);
    const r2 = await h.adapter.execute(ok.operationId, { privateStateOverride: (ps) => withSecret(ps, 'holder', h.eid, pending) });
    expect(r2.state).toBe('Observed');
    expect(h.sim.ledger().entitlements.lookup(h.eid).epoch).toBe(epoch + 1n);
    expect((await h.session.load()).holderSecrets[toHex(h.eid)]).toBe(toHex(pending));
  });

  it('chain-reported failure → Failed with evidence (app never projects it)', async () => {
    const h = harness({ watch: 'fail' });
    await h.loadMember();
    const op = await h.adapter.prepare('proveControl', [h.eid, random32(), random32()]);
    const r = await h.adapter.execute(op.operationId);
    expect(r.state).toBe('Failed');
    expect(r.failureReason).toBe('chain_FailEntirely');
    expect(r.evidence?.blockHash).toBeDefined();
  });

  it('timeout after submission → Reconciling, never a new automatic attempt', async () => {
    const h = harness({ watch: 'hang' });
    await h.loadMember();
    const op = await h.adapter.prepare('proveControl', [h.eid, random32(), random32()]);
    const r = await h.adapter.execute(op.operationId);
    expect(r.state).toBe('Reconciling');
    expect(h.submitted).toHaveLength(1);
    await expect(h.adapter.execute(op.operationId)).rejects.toThrow(/Reconciling/);
    expect(h.submitted).toHaveLength(1);
  });

  it('blocks conflicting commands on the same subject while one is active', async () => {
    const h = harness();
    await h.adapter.prepare('offerTransfer', [h.eid, random32(), random32(), 1n, random32()], { subjectRef: toHex(h.eid) });
    await expect(h.adapter.prepare('proveControl', [h.eid, random32(), random32()], { subjectRef: toHex(h.eid) })).rejects.toThrow(/conflicting operation/);
  });

  it('idempotency key reuse returns the same operation; different request is refused', async () => {
    const h = harness();
    const a = await h.adapter.prepare('proveControl', [h.eid, new Uint8Array(32).fill(1), new Uint8Array(32).fill(2)], { idempotencyKey: 'k1' });
    const b = await h.adapter.prepare('proveControl', [h.eid, new Uint8Array(32).fill(1), new Uint8Array(32).fill(2)], { idempotencyKey: 'k1' });
    expect(b.operationId).toBe(a.operationId);
    await expect(h.adapter.prepare('proveControl', [h.eid, random32(), random32()], { idempotencyKey: 'k1' })).rejects.toThrow(/idempotency/);
  });

  it('no Mainnet writes: prepare is refused', async () => {
    const h = harness({ endpoints: mainnetEndpoints('projectid123') });
    await expect(h.adapter.prepare('proveControl', [h.eid, random32(), random32()])).rejects.toBeInstanceOf(WritesNotAuthorizedError);
  });

  it('refuses a non-loopback "local" proof server (remote provers see witnesses)', () => {
    const h = harness();
    expect(() => buildProviders({ endpoints: PUBLIC_ENDPOINTS.preprod, session: h.session, wallet: h.wallet,
      proving: { kind: 'local-proof-server', url: 'https://prover.example.com' } })).toThrow(/loopback/);
  });

  it('builds real providers with manifest-verified artifacts for a loopback prover', () => {
    const h = harness();
    const p = buildProviders({ endpoints: PUBLIC_ENDPOINTS.preprod, session: h.session, wallet: h.wallet,
      proving: { kind: 'local-proof-server', url: 'http://127.0.0.1:6300' } });
    expect(typeof p.publicDataProvider.watchForTxData).toBe('function');
    expect(typeof p.proofProvider.proveTx).toBe('function');
  });

  void prepareHolder;
});
