/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Chain operation tracking (ch.04 §5).
 *
 * Every operation is persisted BEFORE any wallet interaction. Its request
 * digest commits to network, contract, circuit and all arguments, so a
 * persisted operation can only ever be executed against the network/contract
 * it was created for. "Submitted" requires a real transaction id;
 * "Finalized" requires chain evidence. A timeout after submission moves to
 * Reconciling — never to a new automatic attempt.
 *
 * Direction of evidence: chain observation → projection. Nothing here can
 * make a contract state valid.
 */

import { createHash, randomUUID } from 'node:crypto';
import type { MidnightNetworkId } from './network.js';

export type OperationState =
  | 'Draft'
  | 'AwaitingRecipient'
  | 'ReadyToProve'
  | 'Proving'
  | 'Submitted'
  | 'Reconciling'
  | 'Observed'
  | 'Finalized'
  | 'Failed'
  | 'Cancelled'
  | 'Expired'
  | 'HandoverPending'
  | 'HandoverAcknowledged';

const TRANSITIONS: Readonly<Record<OperationState, readonly OperationState[]>> = {
  Draft: ['AwaitingRecipient', 'ReadyToProve', 'Cancelled'],
  AwaitingRecipient: ['ReadyToProve', 'Cancelled', 'Expired'],
  ReadyToProve: ['Proving', 'Cancelled', 'Expired', 'Failed'],
  Proving: ['Submitted', 'Failed'],
  Submitted: ['Observed', 'Reconciling', 'Failed'],
  Reconciling: ['Observed', 'Failed'],
  Observed: ['Finalized', 'Reconciling'],
  Finalized: ['HandoverPending'],
  HandoverPending: ['HandoverAcknowledged'],
  Failed: [],
  Cancelled: [],
  Expired: [],
  HandoverAcknowledged: [],
};

export const TERMINAL: ReadonlySet<OperationState> = new Set(['Failed', 'Cancelled', 'Expired', 'Finalized', 'HandoverAcknowledged']);

export class IllegalTransitionError extends Error {
  constructor(readonly from: OperationState, readonly to: OperationState) {
    super(`illegal operation transition ${from} → ${to}`);
    this.name = 'IllegalTransitionError';
  }
}

export interface ChainEvidence {
  readonly txId: string;
  readonly txHash?: string;
  readonly blockHeight?: number;
  readonly blockHash?: string;
  readonly status?: 'SucceedEntirely' | 'FailFallible' | 'FailEntirely';
  readonly finalizedHeadHeight?: number;
  readonly observedAt: string;
}

/** Serializable circuit argument (bigint → decimal string, bytes → hex). */
export type ArgValue = { t: 'bytes'; v: string } | { t: 'uint'; v: string } | { t: 'bool'; v: boolean };

export interface ChainOperation {
  readonly operationId: string;
  readonly network: MidnightNetworkId;
  readonly contractAddress: string;
  readonly circuit: string;
  readonly args: readonly ArgValue[];
  /** sha256 over the canonical request; see requestDigest(). */
  readonly requestDigest: string;
  /** Opaque app references (entitlement / asset / job ids). Never personal data. */
  readonly subjectRef?: string;
  readonly idempotencyKey: string;
  readonly expiresAt?: string;
  readonly state: OperationState;
  readonly version: number;
  readonly failureReason?: string;
  readonly evidence?: ChainEvidence;
  readonly history: readonly { state: OperationState; at: string; reason?: string }[];
  readonly createdAt: string;
  readonly updatedAt: string;
}

export function encodeArg(a: unknown): ArgValue {
  if (a instanceof Uint8Array) return { t: 'bytes', v: Buffer.from(a).toString('hex') };
  if (typeof a === 'bigint') return { t: 'uint', v: a.toString(10) };
  if (typeof a === 'boolean') return { t: 'bool', v: a };
  throw new TypeError(`unsupported circuit argument type ${typeof a}`);
}

export function decodeArg(a: ArgValue): Uint8Array | bigint | boolean {
  switch (a.t) {
    case 'bytes': return new Uint8Array(Buffer.from(a.v, 'hex'));
    case 'uint': return BigInt(a.v);
    case 'bool': return a.v;
  }
}

export function requestDigest(r: { network: string; contractAddress: string; circuit: string; args: readonly ArgValue[]; expiresAt?: string }): string {
  const canonical = JSON.stringify(['brandme.chain-op/v1', r.network, r.contractAddress.toLowerCase(), r.circuit, r.args, r.expiresAt ?? null]);
  return createHash('sha256').update(canonical).digest('hex');
}

export interface OperationStore {
  /** Insert, or return the existing operation for the same idempotency key (must have the same digest). */
  create(op: ChainOperation): Promise<ChainOperation>;
  get(operationId: string): Promise<ChainOperation | null>;
  /** Compare-and-set on version. Returns null if the version moved (concurrent writer). */
  update(op: ChainOperation, expectedVersion: number): Promise<ChainOperation | null>;
  listByState(network: MidnightNetworkId, states: readonly OperationState[]): Promise<ChainOperation[]>;
  /** An active (non-terminal) operation already touching this subject blocks conflicting commands. */
  activeForSubject(network: MidnightNetworkId, subjectRef: string): Promise<ChainOperation[]>;
}

export class IdempotencyConflictError extends Error {
  constructor(key: string) {
    super(`idempotency key ${key} reused with a different request`);
    this.name = 'IdempotencyConflictError';
  }
}

export function newOperation(p: {
  network: MidnightNetworkId; contractAddress: string; circuit: string; args: readonly unknown[];
  subjectRef?: string; idempotencyKey?: string; expiresAt?: Date; initial?: 'Draft' | 'AwaitingRecipient' | 'ReadyToProve';
}): ChainOperation {
  const now = new Date().toISOString();
  const args = p.args.map(encodeArg);
  const expiresAt = p.expiresAt?.toISOString();
  const state = p.initial ?? 'ReadyToProve';
  return {
    operationId: randomUUID(),
    network: p.network,
    contractAddress: p.contractAddress,
    circuit: p.circuit,
    args,
    requestDigest: requestDigest({ network: p.network, contractAddress: p.contractAddress, circuit: p.circuit, args, expiresAt }),
    subjectRef: p.subjectRef,
    idempotencyKey: p.idempotencyKey ?? randomUUID(),
    expiresAt,
    state,
    version: 1,
    history: [{ state, at: now }],
    createdAt: now,
    updatedAt: now,
  };
}

export function transition(op: ChainOperation, to: OperationState, patch: Partial<Pick<ChainOperation, 'failureReason' | 'evidence'>> = {}, reason?: string): ChainOperation {
  if (!TRANSITIONS[op.state].includes(to)) throw new IllegalTransitionError(op.state, to);
  if (to === 'Submitted' && !(patch.evidence?.txId ?? op.evidence?.txId)) {
    throw new Error('Submitted requires a real transaction id');
  }
  if ((to === 'Observed' || to === 'Finalized') && !(patch.evidence ?? op.evidence)?.blockHash) {
    throw new Error(`${to} requires block evidence`);
  }
  const at = new Date().toISOString();
  return { ...op, ...patch, state: to, version: op.version + 1, updatedAt: at, history: [...op.history, { state: to, at, reason }] };
}

/** In-process store. Used by tests and the local-network harness; Spanner store implements the same contract. */
export class InMemoryOperationStore implements OperationStore {
  private readonly ops = new Map<string, ChainOperation>();
  private readonly byKey = new Map<string, string>();

  async create(op: ChainOperation): Promise<ChainOperation> {
    const existing = this.byKey.get(op.idempotencyKey);
    if (existing) {
      const e = this.ops.get(existing)!;
      if (e.requestDigest !== op.requestDigest) throw new IdempotencyConflictError(op.idempotencyKey);
      return e;
    }
    this.ops.set(op.operationId, op);
    this.byKey.set(op.idempotencyKey, op.operationId);
    return op;
  }
  async get(id: string) { return this.ops.get(id) ?? null; }
  async update(op: ChainOperation, expectedVersion: number) {
    const cur = this.ops.get(op.operationId);
    if (!cur || cur.version !== expectedVersion) return null;
    this.ops.set(op.operationId, op);
    return op;
  }
  async listByState(network: MidnightNetworkId, states: readonly OperationState[]) {
    return [...this.ops.values()].filter((o) => o.network === network && states.includes(o.state));
  }
  async activeForSubject(network: MidnightNetworkId, subjectRef: string) {
    return [...this.ops.values()].filter((o) => o.network === network && o.subjectRef === subjectRef && !TERMINAL.has(o.state));
  }
}
