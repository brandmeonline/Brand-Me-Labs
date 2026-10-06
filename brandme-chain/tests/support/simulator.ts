/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Local ledger simulator for the compiled brandme_rights contract.
 *
 * TEST-ONLY. It executes the real compiled circuit logic from
 * contracts/managed (compact-runtime 0.16.0, onchain-runtime-v3 3.0.0) against
 * an in-memory public ledger, with one private state per actor. It does not
 * generate proofs; proof generation/verification is exercised by the network
 * tests against the pinned proof server. It lives under tests/ so it can never
 * be loaded on a sandbox/production trust path.
 *
 * Atomicity mirrors the ledger: a circuit that throws leaves the public state
 * and the caller's private state exactly as they were.
 */

import {
  createCircuitContext,
  createConstructorContext,
  sampleContractAddress,
  type ChargedState,
  type ContractAddress,
} from '@midnight-ntwrk/compact-runtime';
import {
  bindingFromLedger,
  commitments,
  emptyPrivateState,
  networkTagFor,
  newRightsContract,
  rightsLedger,
  type InstanceBinding,
  type RightsLedger,
  type RightsPrivateState,
} from '../../src/midnight/rights-contract.js';
import { random32 } from '../../src/midnight/bytes.js';

const COIN_PK = '00'.repeat(32);

export type Circuit = keyof ReturnType<typeof newRightsContract>['impureCircuits'];

export class Actor {
  constructor(public readonly name: string, public privateState: RightsPrivateState = emptyPrivateState()) {}
}

export class RightsSimulator {
  readonly contract = newRightsContract();
  readonly address: ContractAddress = sampleContractAddress();
  private state: ChargedState;
  /** Simulated block time, seconds since epoch. */
  now = 1_790_000_000;
  readonly governance: Actor;
  readonly binding: InstanceBinding;
  readonly calls: { circuit: string; ok: boolean; error?: string }[] = [];

  constructor(networkId = 'undeployed') {
    const govSecret = random32();
    const salt = random32();
    const tag = networkTagFor(networkId);
    // The governance commitment depends on salt+network, which the constructor stores.
    const govCommitment = commitments.governance(govSecret, { salt, networkTag: tag });
    const gov = new Actor('governance', { ...emptyPrivateState(), governanceSecret: Buffer.from(govSecret).toString('hex') });
    const r = this.contract.initialState(createConstructorContext(gov.privateState, COIN_PK), salt, tag, govCommitment);
    this.state = r.currentContractState.data;
    this.governance = gov;
    this.binding = bindingFromLedger(this.ledger());
  }

  ledger(): RightsLedger {
    return rightsLedger(this.state);
  }

  /** Opaque snapshot of public state, for "state unchanged" assertions. */
  snapshot(): string {
    return this.state.state.toString();
  }

  call<R = unknown>(actor: Actor, circuit: Circuit, ...args: unknown[]): R {
    const ctx = createCircuitContext(this.address, COIN_PK, this.state, actor.privateState, undefined, undefined, this.now);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const res = (this.contract.impureCircuits[circuit] as any)(ctx, ...args);
      this.state = res.context.currentQueryContext.state;
      actor.privateState = res.context.currentPrivateState;
      this.calls.push({ circuit, ok: true });
      return res.result as R;
    } catch (e) {
      this.calls.push({ circuit, ok: false, error: (e as Error).message });
      throw e;
    }
  }

  /** Like call() but returns the error message instead of throwing; asserts state unchanged on failure. */
  attempt(actor: Actor, circuit: Circuit, ...args: unknown[]): { ok: true; result: unknown } | { ok: false; error: string } {
    const before = this.snapshot();
    const psBefore = JSON.stringify(actor.privateState);
    try {
      return { ok: true, result: this.call(actor, circuit, ...args) };
    } catch (e) {
      if (this.snapshot() !== before) throw new Error(`state mutated by failed ${circuit}`);
      if (JSON.stringify(actor.privateState) !== psBefore) throw new Error(`private state mutated by failed ${circuit}`);
      return { ok: false, error: (e as Error).message };
    }
  }
}
