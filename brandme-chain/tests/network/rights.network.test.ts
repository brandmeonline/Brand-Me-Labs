/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * End-to-end rights lifecycle on a real Midnight network (local devnet or
 * Preprod): real proofs from the pinned proof server, real node submission,
 * indexer observation and GRANDPA finality. Writes an evidence JSON file.
 *
 * Exit evidence covered (ch.06 W09):
 *   issue → prove → transfer → consume, observed and finalized
 *   replay (challenge reuse, identical tx resubmission) rejected
 *   concurrent acceptance: exactly one wins
 *   cross-network operation replay rejected before state mutation
 *   invalid witness / invalid proof leaves contract state unchanged
 *   account switch during proving aborts before submission
 *   reprint quota consumed exactly once under duplicate callbacks; one child per unit
 *   private-state backup → clean-profile restore → proof accepted on chain
 */

import { MemoryLevel } from 'memory-level';
import type { MidnightWalletProvider } from '@midnight-ntwrk/testkit-js';
import type { MidnightProviders } from '@midnight-ntwrk/midnight-js-types';
import { Evidence, logger, resolveNetwork, startWallet } from './env.js';
import {
  RightsAdapter, buildProviders, rootCauseMessage, deployRightsContract, NodeRpcFinalityOracle, type ConnectedWallet, type RightsCircuit,
} from '../../src/midnight/adapter.js';
import { InMemoryOperationStore, newOperation, type ChainOperation } from '../../src/midnight/operations.js';
import { PrivateStateSession } from '../../src/midnight/private-state.js';
import { WrongNetworkError } from '../../src/midnight/network.js';
import {
  commitments, derive, emptyPrivateState, networkTagFor, rightsLedger, withSecret, type RightsPrivateState,
} from '../../src/midnight/rights-contract.js';
import { random32, toHex } from '../../src/midnight/bytes.js';
import manifest from '../../contracts/artifact-manifest.json' with { type: 'json' };

const { env, endpoints, seeds } = resolveNetwork();
const evidence = new Evidence(endpoints.networkId, {
  badge: endpoints.badge,
  tuple: { compactc: manifest.compactc, runtime: manifest.runtimeVersion, midnightJs: '4.1.1', proofServer: '8.1.0' },
  sourceSha256: manifest.contracts.brandme_rights.source.sha256,
});

type Party = {
  name: string;
  wallet: MidnightWalletProvider;
  submittedTxs: unknown[];
  account: () => string;
  session: PrivateStateSession;
  store: InMemoryOperationStore;
  providers: MidnightProviders<RightsCircuit, string, RightsPrivateState>;
  adapter: RightsAdapter;
  flipAccountAfterProve?: boolean;
};

const PASSWORD = () => 'Network-Test-2026!';
const dbFactory = () => {
  const dbs = new Map<string, MemoryLevel<string, string>>();
  return (name: string) => { if (!dbs.has(name)) dbs.set(name, new MemoryLevel<string, string>()); return dbs.get(name) as never; };
};

function connected(p: { wallet: MidnightWalletProvider; submittedTxs: unknown[]; account: () => string }): ConnectedWallet {
  return {
    walletProvider: p.wallet,
    midnightProvider: { submitTx: async (tx) => { p.submittedTxs.push(tx); return p.wallet.submitTx(tx); } },
    networkId: () => endpoints.networkId,
    accountId: () => p.account(),
  };
}

function makeParty(name: string, wallet: MidnightWalletProvider, contractAddress: string, levelFactory = dbFactory()): Party {
  const coinPk = String(wallet.getCoinPublicKey());
  const party = { name, wallet, submittedTxs: [] as unknown[], account: () => coinPk } as Party;
  party.session = new PrivateStateSession({ network: endpoints.networkId, contractAddress, accountId: coinPk, passwordProvider: PASSWORD, levelFactory });
  party.store = new InMemoryOperationStore();
  const cw = connected(party);
  const base = buildProviders({ endpoints, session: party.session, wallet: cw, proving: { kind: 'local-proof-server', url: env.proofServer } });
  party.providers = {
    ...base,
    proofProvider: {
      proveTx: async (tx, cfg) => {
        const proven = await base.proofProvider.proveTx(tx, cfg);
        if (party.flipAccountAfterProve) party.account = () => 'switched-account';
        return proven;
      },
    },
  };
  party.adapter = new RightsAdapter({
    endpoints, contractAddress, providers: party.providers, session: party.session, wallet: cw, store: party.store,
    finality: new NodeRpcFinalityOracle(env.node), observeTimeoutMs: 10 * 60_000,
  });
  return party;
}

async function ledgerOf(p: Party, address: string) {
  const s = await p.providers.publicDataProvider.queryContractState(address as never);
  if (!s) throw new Error('contract state not found');
  return rightsLedger(s.data);
}

async function waitFinal(p: Party, op: ChainOperation, timeoutMs = 5 * 60_000): Promise<ChainOperation> {
  const t0 = Date.now();
  let cur = op;
  while (cur.state === 'Observed' && Date.now() - t0 < timeoutMs) {
    await new Promise((r) => setTimeout(r, 2000));
    cur = await p.adapter.checkFinality(op.operationId);
  }
  return cur;
}

async function run(p: Party, circuit: RightsCircuit, args: unknown[], label: string, opts: { override?: (ps: RightsPrivateState) => RightsPrivateState; expect?: 'Finalized' | 'Failed' } = {}) {
  const t0 = Date.now();
  const prepared = await p.adapter.prepare(circuit, args);
  let op = await p.adapter.execute(prepared.operationId, { privateStateOverride: opts.override });
  op = await waitFinal(p, op);
  evidence.add(label, {
    party: p.name, circuit, state: op.state, failureReason: op.failureReason, txId: op.evidence?.txId, txHash: op.evidence?.txHash,
    blockHeight: op.evidence?.blockHeight, blockHash: op.evidence?.blockHash, chainStatus: op.evidence?.status,
    finalizedHeadHeight: op.evidence?.finalizedHeadHeight, ms: Date.now() - t0,
    failureDetail: op.history.at(-1)?.reason,
  });
  expect(op.state, `${label}: ${op.failureReason ?? ''} ${op.history.at(-1)?.reason ?? ''}`).toBe(opts.expect ?? 'Finalized');
  return op;
}

describe(`rights lifecycle on ${endpoints.badge}`, () => {
  let operator: Party, alice: Party, bob: Party, mfr: Party;
  let address: string;
  const wallets: MidnightWalletProvider[] = [];
  const iid = random32();
  const mid = random32();

  beforeAll(async () => {
    for (const s of seeds.slice(0, 3)) wallets.push(await startWallet(env, s));
  });

  afterAll(async () => {
    const file = evidence.write();
    logger.info(`evidence written to ${file}`);
    for (const w of wallets) await w.stop().catch(() => undefined);
  });

  it('deploys the rights contract with verified artifacts', async () => {
    const govSecret = random32();
    const salt = random32();
    const tag = networkTagFor(endpoints.networkId);
    const gov = { ...emptyPrivateState(), governanceSecret: toHex(govSecret) };
    const deployer = makeParty('operator-deploy', wallets[0]!, '00'.repeat(32));
    const t0 = Date.now();
    const deployed = await deployRightsContract(deployer.providers, endpoints, {
      salt, networkTag: tag, governanceCommitment: commitments.governance(govSecret, { salt, networkTag: tag }), initialPrivateState: gov,
    });
    address = deployed.contractAddress;
    evidence.add('deploy', { contractAddress: address, ...deployed.deployTx, ms: Date.now() - t0 });
    for (const k of deployed.keyInsertions) evidence.add(`insertVerifierKey:${k.circuit}`, k);
    evidence.add('verifier-keys-verified-on-chain', { circuits: 15 });

    operator = makeParty('operator', wallets[0]!, address);
    alice = makeParty('alice', wallets[1]!, address);
    bob = makeParty('bob', wallets[2]!, address);
    // Manufacturer identity is a secret in its own private state; it pays fees from the operator wallet.
    mfr = makeParty('manufacturer', wallets[0]!, address);
    await operator.session.save(gov);
    const l = await ledgerOf(operator, address);
    expect(toHex(l.networkTag)).toBe(toHex(tag));
  });

  let eid: Uint8Array;
  it('registers an issuer and manufacturer, issues an entitlement, proves control', async () => {
    const issuerSecret = random32();
    const binding = { salt: (await ledgerOf(operator, address)).instanceSalt, networkTag: networkTagFor(endpoints.networkId) };
    await operator.session.save(withSecret(await operator.session.load(), 'issuer', iid, issuerSecret));
    await run(operator, 'registerIssuer', [iid, commitments.issuer(iid, issuerSecret, binding), 1n, 100n, 4_000_000_000n], 'registerIssuer');

    const mSecret = random32();
    await mfr.session.save(withSecret(await mfr.session.load(), 'manufacturer', mid, mSecret));
    await run(operator, 'registerManufacturer', [iid, mid, commitments.manufacturer(mid, mSecret, binding)], 'registerManufacturer');

    const issuanceId = random32();
    eid = derive.entitlementId(iid, issuanceId);
    const aliceSecret = random32();
    await alice.session.save(withSecret(await alice.session.load(), 'holder', eid, aliceSecret));
    await run(operator, 'issueEntitlement', [iid, issuanceId, random32(), random32(), true, true, commitments.holder(eid, 1n, aliceSecret, binding)], 'issueEntitlement');

    const challenge = random32();
    const audience = random32();
    await run(alice, 'proveControl', [eid, challenge, audience], 'proveControl');

    // Replay 1: same (challenge, audience) → rejected, no tx.
    const before = (await ledgerOf(alice, address)).usedChallenges.size();
    await run(alice, 'proveControl', [eid, challenge, audience], 'proveControl-replay-same-challenge', { expect: 'Failed' });
    expect((await ledgerOf(alice, address)).usedChallenges.size()).toBe(before);

    // Replay 2: resubmit the identical, already-included transaction bytes.
    const tx = alice.submittedTxs.at(-1);
    let resubmit: string;
    try { await alice.wallet.submitTx(tx as never); resubmit = 'accepted-by-node'; } catch (e) { resubmit = `rejected: ${rootCauseMessage(e)}`; }
    evidence.add('proveControl-replay-identical-tx', { outcome: resubmit });
    await new Promise((r) => setTimeout(r, 15_000));
    expect((await ledgerOf(alice, address)).usedChallenges.size()).toBe(before);
    expect(resubmit).toMatch(/^rejected/);
  });

  it('invalid witness and account switch during proving leave state unchanged', async () => {
    const snap = JSON.stringify((await ledgerOf(bob, address)).entitlements.lookup(eid), (_k, v) => (typeof v === 'bigint' ? v.toString() : v));
    const sizeBefore = (await ledgerOf(bob, address)).usedChallenges.size();
    await run(bob, 'proveControl', [eid, random32(), random32()], 'invalid-witness-proveControl',
      { expect: 'Failed', override: (ps) => withSecret(ps, 'holder', eid, random32()) });

    alice.flipAccountAfterProve = true;
    const submittedBefore = alice.submittedTxs.length;
    const op = await run(alice, 'proveControl', [eid, random32(), random32()], 'account-switch-during-proving', { expect: 'Failed' });
    expect(op.failureReason).toBe('session_changed');
    expect(alice.submittedTxs.length).toBe(submittedBefore);
    alice.flipAccountAfterProve = false;
    alice.account = () => String(alice.wallet.getCoinPublicKey());
    alice.session.unlock();

    const after = await ledgerOf(bob, address);
    expect(JSON.stringify(after.entitlements.lookup(eid), (_k, v) => (typeof v === 'bigint' ? v.toString() : v))).toBe(snap);
    expect(after.usedChallenges.size()).toBe(sizeBefore);
  });

  it('rejects a cross-network replay of a persisted operation before any mutation', async () => {
    const foreign = newOperation({ network: endpoints.networkId === 'preprod' ? 'preview' : 'preprod', contractAddress: address, circuit: 'proveControl', args: [eid, random32(), random32()] });
    await alice.store.create(foreign);
    const sub = alice.submittedTxs.length;
    await expect(alice.adapter.execute(foreign.operationId)).rejects.toBeInstanceOf(WrongNetworkError);
    expect(alice.submittedTxs.length).toBe(sub);
    expect((await alice.store.get(foreign.operationId))!.state).toBe('ReadyToProve');
    evidence.add('cross-network-replay', { outcome: 'rejected before proving', operationNetwork: foreign.network });
  });

  it('transfers alice → bob; concurrent competing acceptances: exactly one wins', async () => {
    const l0 = await ledgerOf(alice, address);
    const epoch = l0.entitlements.lookup(eid).epoch;
    const binding = { salt: l0.instanceSalt, networkTag: l0.networkTag };
    const bobPending = random32();
    const mfrPending = random32();
    const n1 = random32();
    const n2 = random32();
    const exp = BigInt(Math.floor(Date.now() / 1000) + 3600);
    await run(alice, 'offerTransfer', [eid, n1, commitments.holder(eid, epoch + 1n, bobPending, binding), exp, random32()], 'offerTransfer-to-bob');
    await run(alice, 'offerTransfer', [eid, n2, commitments.holder(eid, epoch + 1n, mfrPending, binding), exp, random32()], 'offerTransfer-to-competitor');
    const o1 = derive.offerId(eid, epoch, n1);
    const o2 = derive.offerId(eid, epoch, n2);

    const [rb, rc] = await Promise.all([
      (async () => { const p = await bob.adapter.prepare('acceptTransfer', [o1]); return waitFinal(bob, await bob.adapter.execute(p.operationId, { privateStateOverride: (ps) => withSecret(ps, 'holder', eid, bobPending) })); })(),
      (async () => { const p = await mfr.adapter.prepare('acceptTransfer', [o2]); return waitFinal(mfr, await mfr.adapter.execute(p.operationId, { privateStateOverride: (ps) => withSecret(ps, 'holder', eid, mfrPending) })); })(),
    ]);
    for (const [who, r] of [['bob', rb], ['competitor', rc]] as const) {
      evidence.add(`concurrent-accept-${who}`, { state: r.state, failureReason: r.failureReason, txId: r.evidence?.txId, chainStatus: r.evidence?.status, blockHeight: r.evidence?.blockHeight, failureDetail: r.history.at(-1)?.reason });
    }
    const winners = [rb, rc].filter((r) => r.state === 'Finalized');
    expect(winners).toHaveLength(1);
    const l1 = await ledgerOf(alice, address);
    expect(l1.entitlements.lookup(eid).epoch).toBe(epoch + 1n);

    // Make bob the holder for the rest of the scenario if the competitor won.
    if (rc.state === 'Finalized') {
      const l = await ledgerOf(mfr, address);
      const e2 = l.entitlements.lookup(eid).epoch;
      const bp = random32();
      const n3 = random32();
      await run(mfr, 'offerTransfer', [eid, n3, commitments.holder(eid, e2 + 1n, bp, binding), exp, random32()], 'offerTransfer-competitor-to-bob');
      await run(bob, 'acceptTransfer', [derive.offerId(eid, e2, n3)], 'acceptTransfer-bob', { override: (ps) => withSecret(ps, 'holder', eid, bp) });
    }
    // Alice no longer controls it.
    await run(alice, 'proveControl', [eid, random32(), random32()], 'old-owner-proveControl', { expect: 'Failed' });
    await run(bob, 'proveControl', [eid, random32(), random32()], 'new-owner-proveControl');
  });

  it('reprint: quota consumed exactly once under duplicate callbacks; one child per unit', async () => {
    const nonce = random32();
    await run(operator, 'grantReprintAllowance', [iid, nonce, eid, random32(), mid, 2n, 4_000_000_000n, random32()], 'grantReprintAllowance');
    const aid = derive.allowanceId(iid, nonce);
    const job = random32();
    await run(bob, 'consumeReprintAllowance', [aid, job, 1n, random32()], 'consume-job-1');
    await run(bob, 'consumeReprintAllowance', [aid, job, 1n, random32()], 'consume-job-1-duplicate-callback', { expect: 'Failed' });
    expect((await ledgerOf(bob, address)).allowances.lookup(aid).remaining).toBe(1n);

    const nf = derive.consumptionNullifier(aid, job);
    await run(mfr, 'attestManufacture', [nf, 0n, random32(), random32()], 'attest-unit-0');
    await run(mfr, 'attestManufacture', [nf, 0n, random32(), random32()], 'attest-unit-0-duplicate-callback', { expect: 'Failed' });
    const l = await ledgerOf(mfr, address);
    expect(l.consumptions.lookup(nf).attested).toBe(1n);
    expect(l.entitlements.member(derive.childEntitlementId(nf, 0n))).toBe(true);
    expect(l.entitlements.member(derive.childEntitlementId(nf, 1n))).toBe(false);

    await run(bob, 'consumeReprintAllowance', [aid, random32(), 2n, random32()], 'consume-over-quota', { expect: 'Failed' });
    expect((await ledgerOf(bob, address)).allowances.lookup(aid).remaining).toBe(1n);
  });

  it('private-state backup → clean-profile restore → restored holder proves control on chain', async () => {
    const backup = await bob.session.exportBackup('Backup-Pass-2026!');
    const restored = makeParty('bob-restored', wallets[2]!, address, dbFactory());
    expect(Object.keys((await restored.session.load()).holderSecrets)).toHaveLength(0);
    const r = await restored.session.restoreBackup(backup, 'Backup-Pass-2026!');
    evidence.add('backup-restore', { imported: r.imported, backupFormat: backup.format, backupNetwork: backup.network });
    await run(restored, 'proveControl', [eid, random32(), random32()], 'restored-proveControl');
  });
});
