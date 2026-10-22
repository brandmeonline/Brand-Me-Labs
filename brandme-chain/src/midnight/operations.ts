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

import { z } from 'zod';
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
  Proving: ['Reconciling', 'Submitted', 'Failed'],
  Submitted: ['Observed', 'Reconciling', 'Failed'],
  Reconciling: ['Submitted', 'Observed', 'Failed'],
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
  /** Internal member UUID; private application authorization, never a chain argument. */
  readonly ownerRef?: string;
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

export function requestDigest(r: { network: string; contractAddress: string; circuit: string; args: readonly ArgValue[]; expiresAt?: string; subjectRef?: string; ownerRef?: string }): string {
  const canonical = JSON.stringify(['brandme.chain-op/v2', r.network, r.contractAddress.toLowerCase(), r.circuit, r.args, r.expiresAt ?? null, r.subjectRef ?? null, r.ownerRef ?? null]);
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
  subjectRef?: string; ownerRef?: string; idempotencyKey?: string; expiresAt?: Date; initial?: 'Draft' | 'AwaitingRecipient' | 'ReadyToProve';
}): ChainOperation {
  const now = new Date().toISOString();
  const args = p.args.map(encodeArg);
  const expiresAt = p.expiresAt?.toISOString();
  const state = p.initial ?? 'ReadyToProve';
  return {
    operationId: randomUUID(),
    network: p.network,
    contractAddress: p.contractAddress.toLowerCase(),
    circuit: p.circuit,
    args,
    requestDigest: requestDigest({ network: p.network, contractAddress: p.contractAddress.toLowerCase(), circuit: p.circuit, args, expiresAt, subjectRef: p.subjectRef, ownerRef: p.ownerRef }),
    subjectRef: p.subjectRef,
    ownerRef: p.ownerRef,
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

/** Storage invariants are checked by both stores, not left to individual callers. */
const timestamp = z.string().datetime();
const opSchema = z.object({
  operationId: z.string().uuid(), network: z.enum(['undeployed', 'preview', 'preprod', 'mainnet']),
  contractAddress: z.string().regex(/^[0-9a-f]{64}$/), circuit: z.string().regex(/^[a-zA-Z][a-zA-Z0-9]{0,63}$/),
  args: z.array(z.discriminatedUnion('t', [
    z.object({ t: z.literal('bytes'), v: z.string().regex(/^(?:[0-9a-f]{2})*$/).max(8192) }).strict(),
    z.object({ t: z.literal('uint'), v: z.string().regex(/^(0|[1-9][0-9]*)$/).max(78) }).strict(),
    z.object({ t: z.literal('bool'), v: z.boolean() }).strict(),
  ])).max(64), requestDigest: z.string().regex(/^[0-9a-f]{64}$/),
  subjectRef: z.string().min(1).max(128).optional(), ownerRef: z.string().uuid().optional(),
  idempotencyKey: z.string().min(1).max(128), expiresAt: timestamp.optional(),
  state: z.string().refine((s) => Object.hasOwn(TRANSITIONS, s)), version: z.number().int().positive().max(256),
  failureReason: z.string().max(64).optional(),
  evidence: z.object({
    txId: z.string().min(1).max(256), txHash: z.string().max(128).optional(),
    blockHeight: z.number().int().nonnegative().safe().optional(), blockHash: z.string().min(1).max(128).optional(),
    status: z.enum(['SucceedEntirely', 'FailFallible', 'FailEntirely']).optional(),
    finalizedHeadHeight: z.number().int().nonnegative().safe().optional(), observedAt: timestamp,
  }).strict().optional(),
  history: z.array(z.object({ state: z.string(), at: timestamp, reason: z.string().max(300).optional() }).strict()).min(1).max(256),
  createdAt: timestamp, updatedAt: timestamp,
}).strict();

export function validateOperation(op: ChainOperation, initial = false): void {
  opSchema.parse(op);
  if (requestDigest(op) !== op.requestDigest) throw new Error('request digest mismatch');
  if (op.version !== op.history.length || op.history[0]!.at !== op.createdAt ||
      op.history.at(-1)!.state !== op.state || op.history.at(-1)!.at !== op.updatedAt) throw new Error('invalid operation history');
  if (!['Draft', 'AwaitingRecipient', 'ReadyToProve'].includes(op.history[0]!.state)) throw new Error('invalid initial state');
  for (let i = 1; i < op.history.length; i++) {
    const prev = op.history[i - 1]!; const next = op.history[i]!;
    if (!TRANSITIONS[prev.state]?.includes(next.state) || Date.parse(next.at) < Date.parse(prev.at)) throw new Error('invalid operation history');
  }
  if (initial && (op.version !== 1 || op.evidence || op.failureReason)) throw new Error('create requires a new operation');
  if (['Submitted', 'Observed', 'Finalized', 'HandoverPending', 'HandoverAcknowledged'].includes(op.state) && !op.evidence?.txId) throw new Error('missing transaction evidence');
  if (['Observed', 'Finalized', 'HandoverPending', 'HandoverAcknowledged'].includes(op.state) &&
      (!op.evidence?.blockHash || op.evidence.blockHeight === undefined || op.evidence.status !== 'SucceedEntirely')) throw new Error('missing successful block evidence');
  if (op.state === 'Failed' && op.evidence && (!op.evidence.blockHash || op.evidence.blockHeight === undefined ||
      !['FailEntirely', 'FailFallible'].includes(op.evidence.status ?? ''))) throw new Error('missing rejected block evidence');
  if ((['Finalized', 'HandoverPending', 'HandoverAcknowledged'].includes(op.state) || op.state === 'Failed' && op.evidence) &&
      (op.evidence?.finalizedHeadHeight === undefined || op.evidence.finalizedHeadHeight < op.evidence.blockHeight!)) throw new Error('missing finality evidence');
}

export function validateUpdate(prev: ChainOperation, next: ChainOperation): void {
  validateOperation(next);
  for (const key of ['operationId', 'network', 'contractAddress', 'circuit', 'requestDigest', 'subjectRef', 'ownerRef', 'idempotencyKey', 'expiresAt', 'createdAt'] as const) {
    if (prev[key] !== next[key]) throw new Error(`immutable operation field: ${key}`);
  }
  if (next.version !== prev.version + 1 || next.history.slice(0, -1).some((entry, i) => entry.state !== prev.history[i]?.state || entry.at !== prev.history[i]?.at || entry.reason !== prev.history[i]?.reason)) throw new Error('invalid operation revision');
  if (prev.evidence && next.state === 'Failed' && !['FailEntirely', 'FailFallible'].includes(next.evidence?.status ?? '')) throw new Error('broadcast failure requires chain rejection');
  if (prev.evidence?.txId && prev.evidence.txId !== next.evidence?.txId) throw new Error('immutable transaction identifier');
}

export class ActiveOperationError extends Error {
  constructor() { super('conflicting operation is still active'); this.name = 'ActiveOperationError'; }
}

export function operationKey(op: ChainOperation): string {
  return JSON.stringify([op.ownerRef ?? null, op.network, op.contractAddress, op.idempotencyKey]);
}

/** In-process store for local tests only. Durable deployments use SpannerOperationStore. */
export class InMemoryOperationStore implements OperationStore {
  private readonly ops = new Map<string, ChainOperation>();
  private readonly byKey = new Map<string, string>();

  private assertSubject(op: ChainOperation) {
    if (op.subjectRef && !TERMINAL.has(op.state) && [...this.ops.values()].some((other) =>
      other.operationId !== op.operationId && other.network === op.network && other.contractAddress === op.contractAddress &&
      other.subjectRef === op.subjectRef && !TERMINAL.has(other.state))) throw new ActiveOperationError();
  }
  async create(op: ChainOperation): Promise<ChainOperation> {
    validateOperation(op, true);
    const existing = this.byKey.get(operationKey(op));
    if (existing) {
      const e = this.ops.get(existing)!;
      if (e.requestDigest !== op.requestDigest) throw new IdempotencyConflictError(op.idempotencyKey);
      return structuredClone(e);
    }
    if (this.ops.has(op.operationId)) throw new Error('operation already exists');
    this.assertSubject(op);
    this.ops.set(op.operationId, structuredClone(op));
    this.byKey.set(operationKey(op), op.operationId);
    return structuredClone(op);
  }
  async get(id: string) { return structuredClone(this.ops.get(id) ?? null); }
  async update(op: ChainOperation, expectedVersion: number) {
    const cur = this.ops.get(op.operationId);
    if (!cur || cur.version !== expectedVersion) return null;
    validateUpdate(cur, op);
    this.assertSubject(op);
    this.ops.set(op.operationId, structuredClone(op));
    return structuredClone(op);
  }
  async listByState(network: MidnightNetworkId, states: readonly OperationState[]) {
    return structuredClone([...this.ops.values()].filter((o) => o.network === network && states.includes(o.state)));
  }
  async activeForSubject(network: MidnightNetworkId, subjectRef: string) {
    return structuredClone([...this.ops.values()].filter((o) => o.network === network && o.subjectRef === subjectRef && !TERMINAL.has(o.state)));
  }
}
