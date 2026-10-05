/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Midnight rights adapter — replaces the former `services/midnight-client.ts`
 * stub. Uses the official Midnight.js 4.1.1 provider boundaries (ch.04 §3):
 *
 *   privateStateProvider  — PrivateStateSession (level provider, account-scoped, encrypted)
 *   publicDataProvider    — indexerPublicDataProvider (network indexer)
 *   zkConfigProvider      — NodeZkConfigProvider over manifest-verified artifacts
 *   proofProvider         — httpClientProofProvider to a LOCAL proof server only,
 *                           or a wallet/connector proof provider passed in by the caller
 *   walletProvider /
 *   midnightProvider      — the connected wallet (user-controlled) or an operator wallet
 *
 * There is no fallback. If any provider is missing or misconfigured, or the
 * artifacts do not match the manifest, construction fails. A failed proof,
 * a rejected transaction or an aborted session never advances app state.
 */

import { CompiledContract } from '@midnight-ntwrk/compact-js';
import { findDeployedContract, deployContract, submitCallTxAsync } from '@midnight-ntwrk/midnight-js-contracts';
import { httpClientProofProvider } from '@midnight-ntwrk/midnight-js-http-client-proof-provider';
import { indexerPublicDataProvider } from '@midnight-ntwrk/midnight-js-indexer-public-data-provider';
import { setNetworkId } from '@midnight-ntwrk/midnight-js-network-id';
import { NodeZkConfigProvider } from '@midnight-ntwrk/midnight-js-node-zk-config-provider';
import type {
  FinalizedTxData,
  MidnightProvider,
  MidnightProviders,
  ProofProvider,
  WalletProvider,
} from '@midnight-ntwrk/midnight-js-types';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { assertSameNetwork, assertWritable, type MidnightEndpoints, WrongNetworkError } from './network.js';
import {
  type ChainOperation,
  decodeArg,
  newOperation,
  type OperationStore,
  requestDigest,
  transition,
} from './operations.js';
import { PRIVATE_STATE_ID, type PrivateStateSession } from './private-state.js';
import {
  RIGHTS_ARTIFACT_DIR,
  RIGHTS_CONTRACT_TAG,
  RightsContract,
  rightsWitnesses,
  type RightsPrivateState,
} from './rights-contract.js';

export type RightsCircuit = keyof RightsContract<RightsPrivateState>['provableCircuits'] & string;

/** Circuits that a member's own wallet runs (user-controlled mode). */
export const MEMBER_CIRCUITS: ReadonlySet<RightsCircuit> = new Set([
  'proveControl', 'offerTransfer', 'acceptTransfer', 'cancelTransfer', 'consumeReprintAllowance',
]);

export const compiledRightsContract = CompiledContract.make(RIGHTS_CONTRACT_TAG, RightsContract).pipe(
  CompiledContract.withWitnesses(rightsWitnesses as never),
  CompiledContract.withCompiledFileAssets(RIGHTS_ARTIFACT_DIR),
);

export class ArtifactIntegrityError extends Error {
  constructor(detail: string) { super(`contract artifacts failed manifest verification: ${detail}`); this.name = 'ArtifactIntegrityError'; }
}

/** Run scripts/verify-artifacts.mjs; refuse to serve proving material that does not match the pinned manifest. */
export function verifyArtifactsOrThrow(): void {
  const script = fileURLToPath(new URL('../../scripts/verify-artifacts.mjs', import.meta.url));
  try {
    execFileSync(process.execPath, [script], { stdio: 'pipe' });
  } catch (e) {
    const err = e as { stderr?: Buffer; message: string };
    throw new ArtifactIntegrityError(err.stderr?.toString().trim() || err.message);
  }
}

export type ProvingMode =
  | { kind: 'local-proof-server'; url: string }
  /** Wallet/connector-supplied proving (the wallet's prover sees witness inputs). */
  | { kind: 'wallet'; provider: ProofProvider; operator: string }
  /** Third-party prover: requires a recorded, explicit disclosure consent. Never chosen automatically. */
  | { kind: 'managed'; url: string; operator: string; consentRecordId: string };

export interface ConnectedWallet {
  readonly walletProvider: WalletProvider;
  readonly midnightProvider: MidnightProvider;
  /** Network id as reported by the wallet/connector right now. */
  networkId(): Promise<string> | string;
  /** Account identity as reported by the wallet right now (e.g. coin public key). */
  accountId(): Promise<string> | string;
}

const isLoopback = (u: string) => {
  const h = new URL(u).hostname;
  return h === 'localhost' || h === '127.0.0.1' || h === '::1' || h === '[::1]';
};

export function buildProviders(p: {
  endpoints: MidnightEndpoints;
  session: PrivateStateSession;
  wallet: ConnectedWallet;
  proving: ProvingMode;
}): MidnightProviders<RightsCircuit, string, RightsPrivateState> {
  verifyArtifactsOrThrow();
  setNetworkId(p.endpoints.networkId);
  const zkConfigProvider = new NodeZkConfigProvider<RightsCircuit>(RIGHTS_ARTIFACT_DIR);
  let proofProvider: ProofProvider;
  switch (p.proving.kind) {
    case 'local-proof-server':
      if (!isLoopback(p.proving.url)) {
        throw new Error('local-proof-server must be a loopback URL; a remote prover sees witness inputs and requires managed-mode consent');
      }
      proofProvider = httpClientProofProvider(p.proving.url, zkConfigProvider);
      break;
    case 'wallet':
      proofProvider = p.proving.provider;
      break;
    case 'managed':
      if (!p.proving.consentRecordId) throw new Error('managed proving requires an explicit consent record');
      proofProvider = httpClientProofProvider(p.proving.url, zkConfigProvider);
      break;
  }
  return {
    privateStateProvider: p.session.stateProvider,
    publicDataProvider: indexerPublicDataProvider(p.endpoints.indexerHttp, p.endpoints.indexerWs),
    zkConfigProvider,
    proofProvider,
    walletProvider: p.wallet.walletProvider,
    midnightProvider: p.wallet.midnightProvider,
  };
}

/** Finality: a block is final once the node's finalized head has reached it AND its hash is canonical. */
export interface FinalityOracle {
  isFinal(blockHeight: number, blockHash: string): Promise<{ final: boolean; finalizedHeadHeight: number }>;
}

/**
 * Substrate JSON-RPC finality (chain_getFinalizedHead / chain_getHeader /
 * chain_getBlockHash). Observed semantics are verified by the network tests;
 * no fixed confirmation count is assumed.
 */
export class NodeRpcFinalityOracle implements FinalityOracle {
  constructor(private readonly rpcUrl: string, private readonly fetchImpl: typeof fetch = fetch) {}
  private async rpc<T>(method: string, params: unknown[] = []): Promise<T> {
    const res = await this.fetchImpl(this.rpcUrl.replace(/^ws/, 'http'), {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
    });
    if (!res.ok) throw new Error(`${method}: HTTP ${res.status}`);
    const body = (await res.json()) as { result?: T; error?: { message: string } };
    if (body.error) throw new Error(`${method}: ${body.error.message}`);
    return body.result as T;
  }
  async isFinal(blockHeight: number, blockHash: string) {
    const head = await this.rpc<string>('chain_getFinalizedHead');
    const header = await this.rpc<{ number: string }>('chain_getHeader', [head]);
    const finalizedHeadHeight = parseInt(header.number, 16);
    if (finalizedHeadHeight < blockHeight) return { final: false, finalizedHeadHeight };
    const canonical = await this.rpc<string>('chain_getBlockHash', [blockHeight]);
    const norm = (h: string) => h.toLowerCase().replace(/^0x/, '');
    return { final: norm(canonical) === norm(blockHash), finalizedHeadHeight };
  }
}

export class ReplayRejectedError extends Error {
  constructor(reason: string) { super(`operation rejected before execution: ${reason}`); this.name = 'ReplayRejectedError'; }
}

export class SessionChangedError extends Error {
  constructor() { super('wallet account or private-state session changed during proving; aborted before submission'); this.name = 'SessionChangedError'; }
}

export interface RightsAdapterOptions {
  readonly endpoints: MidnightEndpoints;
  readonly contractAddress: string;
  readonly providers: MidnightProviders<RightsCircuit, string, RightsPrivateState>;
  readonly session: PrivateStateSession;
  readonly wallet: ConnectedWallet;
  readonly store: OperationStore;
  readonly finality: FinalityOracle;
  /** How long to watch the indexer before moving a submitted op to Reconciling. */
  readonly observeTimeoutMs?: number;
  /** Lets tests and operators swap the submission function; production uses submitCallTxAsync. */
  readonly submit?: typeof submitCallTxAsync;
}

/**
 * Coordinates one account's operations on one deployed rights contract on one
 * network. Construct a new adapter on account or network change.
 */
export class RightsAdapter {
  private readonly submit: typeof submitCallTxAsync;
  constructor(private readonly o: RightsAdapterOptions) {
    this.submit = o.submit ?? submitCallTxAsync;
  }

  get network() { return this.o.endpoints.networkId; }
  get contractAddress() { return this.o.contractAddress; }
  get badge() { return this.o.endpoints.badge; }

  /** Persist an operation before any wallet interaction. */
  async prepare(circuit: RightsCircuit, args: readonly unknown[], meta: { subjectRef?: string; idempotencyKey?: string; expiresAt?: Date } = {}) {
    assertWritable(this.network);
    if (meta.subjectRef) {
      const active = (await this.o.store.activeForSubject(this.network, meta.subjectRef)).filter((x) => x.idempotencyKey !== meta.idempotencyKey);
      if (active.length) throw new Error(`conflicting operation ${active[0]!.operationId} is still ${active[0]!.state}`);
    }
    return this.o.store.create(newOperation({ network: this.network, contractAddress: this.contractAddress, circuit, args, ...meta }));
  }

  /**
   * Execute a persisted operation. All binding checks run before the wallet,
   * prover or private state are touched; a mismatch leaves the operation and
   * chain untouched.
   */
  async execute(operationId: string, opts: { privateStateOverride?: (ps: RightsPrivateState) => RightsPrivateState } = {}): Promise<ChainOperation> {
    const op = await this.o.store.get(operationId);
    if (!op) throw new Error('unknown operation');
    // --- replay / binding checks (no side effects) ---
    if (op.network !== this.network) throw new WrongNetworkError(op.network, this.network, 'operation replay');
    if (op.contractAddress.toLowerCase() !== this.contractAddress.toLowerCase()) throw new ReplayRejectedError('operation bound to another contract');
    if (requestDigest(op) !== op.requestDigest) throw new ReplayRejectedError('request digest mismatch (tampered operation)');
    if (op.state !== 'ReadyToProve') throw new ReplayRejectedError(`operation is ${op.state}`);
    if (op.expiresAt && Date.parse(op.expiresAt) <= Date.now()) {
      return this.save(op, transition(op, 'Expired'));
    }
    assertWritable(this.network);
    assertSameNetwork(this.network, await this.o.wallet.networkId(), 'wallet');
    const account = await this.o.wallet.accountId();
    if (account !== this.o.session.config.accountId) {
      await this.o.session.onAccountChanged(account).catch(() => undefined);
      throw new SessionChangedError();
    }

    // --- prove + submit ---
    let cur = await this.save(op, transition(op, 'Proving'));
    const generation = this.o.session.currentGeneration;
    const originalPs = await this.o.session.load();
    const callPs = opts.privateStateOverride ? opts.privateStateOverride(originalPs) : originalPs;
    if (callPs !== originalPs) await this.o.session.save(callPs);

    const guardedWallet: WalletProvider = {
      getCoinPublicKey: () => this.o.providers.walletProvider.getCoinPublicKey(),
      getEncryptionPublicKey: () => this.o.providers.walletProvider.getEncryptionPublicKey(),
      // Balancing happens after proving and before submission: the last point to abort safely.
      balanceTx: async (tx, ttl) => {
        if (this.o.session.currentGeneration !== generation || this.o.session.isLocked) throw new SessionChangedError();
        if ((await this.o.wallet.accountId()) !== this.o.session.config.accountId) throw new SessionChangedError();
        assertSameNetwork(this.network, await this.o.wallet.networkId(), 'wallet (pre-submit)');
        return this.o.providers.walletProvider.balanceTx(tx, ttl);
      },
    };

    let txId: string;
    try {
      const submitted = await this.submit({ ...this.o.providers, walletProvider: guardedWallet } as never, {
        compiledContract: compiledRightsContract,
        contractAddress: this.contractAddress,
        circuitId: op.circuit,
        args: op.args.map(decodeArg),
        privateStateId: PRIVATE_STATE_ID,
      } as never);
      txId = (submitted as { txId: string }).txId;
    } catch (e) {
      // Nothing was submitted: restore the private state if we changed it and fail.
      if (callPs !== originalPs && !this.o.session.isLocked) await this.o.session.save(originalPs);
      return this.save(cur, transition(cur, 'Failed', { failureReason: reasonCode(e) }, (e as Error).message));
    }
    cur = await this.save(cur, transition(cur, 'Submitted', { evidence: { txId, observedAt: new Date().toISOString() } }));
    return this.observe(cur.operationId);
  }

  /** Watch the indexer for a submitted/reconciling operation. Safe to call repeatedly (e.g. after a restart). */
  async observe(operationId: string): Promise<ChainOperation> {
    let cur = (await this.o.store.get(operationId))!;
    if (cur.state !== 'Submitted' && cur.state !== 'Reconciling' && cur.state !== 'Observed') return cur;
    if (cur.state !== 'Observed') {
      let data: FinalizedTxData;
      try {
        data = await withTimeout(this.o.providers.publicDataProvider.watchForTxData(cur.evidence!.txId), this.o.observeTimeoutMs ?? 300_000);
      } catch (e) {
        if (cur.state === 'Submitted') cur = await this.save(cur, transition(cur, 'Reconciling', {}, (e as Error).message));
        return cur;
      }
      const evidence = {
        txId: data.txId, txHash: data.txHash, blockHeight: data.blockHeight, blockHash: data.blockHash,
        status: data.status, observedAt: new Date().toISOString(),
      };
      if (data.status !== 'SucceedEntirely') {
        return this.save(cur, transition(cur, 'Failed', { evidence, failureReason: `chain_${data.status}` }));
      }
      cur = await this.save(cur, transition(cur, 'Observed', { evidence }));
    }
    return this.checkFinality(cur.operationId);
  }

  async checkFinality(operationId: string): Promise<ChainOperation> {
    const cur = (await this.o.store.get(operationId))!;
    if (cur.state !== 'Observed') return cur;
    const ev = cur.evidence!;
    const f = await this.o.finality.isFinal(ev.blockHeight!, ev.blockHash!);
    if (!f.final) return cur;
    return this.save(cur, transition(cur, 'Finalized', { evidence: { ...ev, finalizedHeadHeight: f.finalizedHeadHeight } }));
  }

  private async save(prev: ChainOperation, next: ChainOperation): Promise<ChainOperation> {
    const r = await this.o.store.update(next, prev.version);
    if (!r) throw new Error(`concurrent update of operation ${prev.operationId}`);
    return r;
  }
}

function reasonCode(e: unknown): string {
  const n = (e as Error)?.name ?? 'Error';
  const m = (e as Error)?.message ?? '';
  if (n === 'SessionChangedError') return 'session_changed';
  if (n === 'MissingWitnessError') return 'missing_private_state';
  if (n === 'WrongNetworkError') return 'wrong_network';
  if (/failed assert/.test(m)) return 'contract_precondition_failed';
  if (/prov/i.test(m)) return 'proof_failed';
  return 'submission_failed';
}

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(`timed out after ${ms} ms`)), ms);
    p.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}

/** Operator-only: deploy a new rights contract instance (never on Mainnet in this build). */
export async function deployRightsContract(
  providers: MidnightProviders<RightsCircuit, string, RightsPrivateState>,
  endpoints: MidnightEndpoints,
  args: { salt: Uint8Array; networkTag: Uint8Array; governanceCommitment: Uint8Array; initialPrivateState: RightsPrivateState },
) {
  assertWritable(endpoints.networkId);
  return deployContract(providers as never, {
    compiledContract: compiledRightsContract,
    privateStateId: PRIVATE_STATE_ID,
    initialPrivateState: args.initialPrivateState,
    args: [args.salt, args.networkTag, args.governanceCommitment],
  } as never);
}

export async function attachRightsContract(providers: MidnightProviders<RightsCircuit, string, RightsPrivateState>, contractAddress: string) {
  // findDeployedContract verifies the on-chain verifier keys equal our compiled keys.
  return findDeployedContract(providers as never, {
    compiledContract: compiledRightsContract,
    contractAddress,
    privateStateId: PRIVATE_STATE_ID,
  } as never);
}
