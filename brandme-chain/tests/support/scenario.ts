/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Role-level helpers over RightsSimulator. Each helper performs the same
 * off-chain preparation the production adapter performs (fresh random secrets,
 * commitments bound to the instance salt + network tag) and records secrets
 * only in the acting party's private state.
 */

import { Actor, RightsSimulator } from './simulator.js';
import { random32 } from '../../src/midnight/bytes.js';
import { commitments, derive, withSecret } from '../../src/midnight/rights-contract.js';

export { Actor, RightsSimulator };
export { default as fc } from 'fast-check';

export const FAR_FUTURE = 4_000_000_000n;

export function registerIssuer(sim: RightsSimulator, issuer: Actor, opts: { maxIssuance?: bigint; validUntil?: bigint } = {}) {
  const issuerId = random32();
  const secret = random32();
  issuer.privateState = withSecret(issuer.privateState, 'issuer', issuerId, secret);
  sim.call(sim.governance, 'registerIssuer', issuerId, commitments.issuer(issuerId, secret, sim.binding), 1n,
    opts.maxIssuance ?? 1000n, opts.validUntil ?? FAR_FUTURE);
  return issuerId;
}

/** Holder generates a fresh per-entitlement secret and hands only the commitment to the issuer. */
export function prepareHolder(sim: RightsSimulator, holder: Actor, entitlementId: Uint8Array, epoch: bigint) {
  const secret = random32();
  holder.privateState = withSecret(holder.privateState, 'holder', entitlementId, secret);
  return commitments.holder(entitlementId, epoch, secret, sim.binding);
}

export function issue(sim: RightsSimulator, issuer: Actor, issuerId: Uint8Array, holder: Actor,
                      opts: { transferable?: boolean; reprintable?: boolean } = {}) {
  const issuanceId = random32();
  const eid = derive.entitlementId(issuerId, issuanceId);
  const controller = prepareHolder(sim, holder, eid, 1n);
  const got = sim.call<Uint8Array>(issuer, 'issueEntitlement', issuerId, issuanceId, random32(), random32(),
    opts.transferable ?? true, opts.reprintable ?? false, controller);
  return { eid: got, issuanceId };
}

export function offer(sim: RightsSimulator, sender: Actor, eid: Uint8Array, recipient: Actor,
                      opts: { expiry?: bigint } = {}) {
  const epoch = sim.ledger().entitlements.lookup(eid).epoch;
  const recipientCommitment = prepareHolder(sim, recipient, eid, epoch + 1n);
  const oid = sim.call<Uint8Array>(sender, 'offerTransfer', eid, random32(), recipientCommitment,
    opts.expiry ?? BigInt(sim.now + 3600), random32());
  return oid;
}

export function registerManufacturer(sim: RightsSimulator, issuer: Actor, issuerId: Uint8Array, mfr: Actor) {
  const mid = random32();
  const secret = random32();
  mfr.privateState = withSecret(mfr.privateState, 'manufacturer', mid, secret);
  sim.call(issuer, 'registerManufacturer', issuerId, mid, commitments.manufacturer(mid, secret, sim.binding));
  return mid;
}

export function grantAllowance(sim: RightsSimulator, issuer: Actor, issuerId: Uint8Array, eid: Uint8Array,
                               mid: Uint8Array, quota: bigint, validUntil: bigint = FAR_FUTURE) {
  return sim.call<Uint8Array>(issuer, 'grantReprintAllowance', issuerId, random32(), eid, random32(), mid, quota,
    validUntil, random32());
}

/** Full fixture: governance, one issuer, one holder with a reprintable entitlement, one manufacturer + allowance. */
export function reprintFixture(quota = 3n) {
  const sim = new RightsSimulator();
  const issuer = new Actor('issuer');
  const holder = new Actor('holder');
  const mfr = new Actor('manufacturer');
  const issuerId = registerIssuer(sim, issuer);
  const { eid } = issue(sim, issuer, issuerId, holder, { reprintable: true });
  const mid = registerManufacturer(sim, issuer, issuerId, mfr);
  const aid = grantAllowance(sim, issuer, issuerId, eid, mid, quota);
  return { sim, issuer, holder, mfr, issuerId, eid, mid, aid };
}
