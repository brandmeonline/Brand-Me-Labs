/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Circuit constraint tests for brandme_rights (ch.04 §4 transition table).
 * Every negative case asserts that the failed call left public AND private
 * state byte-identical (RightsSimulator.attempt enforces this).
 */

import {
  Actor, FAR_FUTURE, RightsSimulator, grantAllowance, issue, offer, prepareHolder, registerIssuer,
  registerManufacturer, reprintFixture,
} from '../../brandme-chain/tests/support/scenario.js';
import { random32 } from '../../brandme-chain/src/midnight/bytes.js';
import { ConsumptionState, EntitlementStatus, OfferState, commitments, derive } from '../../brandme-chain/src/midnight/rights-contract.js';

const ZERO = new Uint8Array(32);

const expectFail = (r: { ok: boolean; error?: string }, msg: string) => {
  expect(r.ok).toBe(false);
  expect((r as { error: string }).error).toContain(msg);
};

describe('registerIssuer', () => {
  it('requires the governance secret', () => {
    const sim = new RightsSimulator();
    const imposter = new Actor('imposter', { ...sim.governance.privateState, governanceSecret: Buffer.from(random32()).toString('hex') });
    expectFail(sim.attempt(imposter, 'registerIssuer', random32(), random32(), 1n, 10n, FAR_FUTURE), 'not governance');
  });

  it('fails closed when the witness has no secret at all', () => {
    const sim = new RightsSimulator();
    expectFail(sim.attempt(new Actor('nobody'), 'registerIssuer', random32(), random32(), 1n, 10n, FAR_FUTURE),
      'private state has no governanceSecret');
  });

  it('rejects duplicate ids, zero keys and zero caps', () => {
    const sim = new RightsSimulator();
    const id = random32();
    sim.call(sim.governance, 'registerIssuer', id, random32(), 1n, 10n, FAR_FUTURE);
    expectFail(sim.attempt(sim.governance, 'registerIssuer', id, random32(), 1n, 10n, FAR_FUTURE), 'issuer exists');
    expectFail(sim.attempt(sim.governance, 'registerIssuer', random32(), ZERO, 1n, 10n, FAR_FUTURE), 'malformed issuer key');
    expectFail(sim.attempt(sim.governance, 'registerIssuer', ZERO, random32(), 1n, 10n, FAR_FUTURE), 'malformed issuer id');
    expectFail(sim.attempt(sim.governance, 'registerIssuer', random32(), random32(), 1n, 0n, FAR_FUTURE), 'zero issuance cap');
  });

  it('rotation requires an increasing policy version and invalidates the old key', () => {
    const sim = new RightsSimulator();
    const issuer = new Actor('issuer');
    const iid = registerIssuer(sim, issuer);
    expectFail(sim.attempt(sim.governance, 'rotateIssuerKey', iid, random32(), 1n), 'policy version must increase');
    sim.call(sim.governance, 'rotateIssuerKey', iid, random32(), 2n);
    expectFail(sim.attempt(issuer, 'issueEntitlement', iid, random32(), random32(), random32(), true, false, random32()), 'not issuer');
  });
});

describe('issueEntitlement', () => {
  it('issues exactly one active entitlement at epoch 1 bound to the holder commitment', () => {
    const sim = new RightsSimulator();
    const issuer = new Actor('issuer');
    const holder = new Actor('holder');
    const iid = registerIssuer(sim, issuer);
    const { eid } = issue(sim, issuer, iid, holder);
    const e = sim.ledger().entitlements.lookup(eid);
    expect(e.epoch).toBe(1n);
    expect(e.status).toBe(EntitlementStatus.active);
    expect(sim.ledger().issuers.lookup(iid).issued).toBe(1n);
  });

  it('rejects reuse of an issuance id', () => {
    const sim = new RightsSimulator();
    const issuer = new Actor('issuer');
    const iid = registerIssuer(sim, issuer);
    const issuanceId = random32();
    sim.call(issuer, 'issueEntitlement', iid, issuanceId, random32(), random32(), true, false, random32());
    expectFail(sim.attempt(issuer, 'issueEntitlement', iid, issuanceId, random32(), random32(), true, false, random32()),
      'issuance id already used');
  });

  it('enforces the issuer cap (invariant 4)', () => {
    const sim = new RightsSimulator();
    const issuer = new Actor('issuer');
    const iid = registerIssuer(sim, issuer, { maxIssuance: 2n });
    issue(sim, issuer, iid, new Actor('a'));
    issue(sim, issuer, iid, new Actor('b'));
    expectFail(sim.attempt(issuer, 'issueEntitlement', iid, random32(), random32(), random32(), true, false, random32()),
      'issuance cap reached');
  });

  it('revoked or expired issuer authority cannot mint (invariant 6)', () => {
    const sim = new RightsSimulator();
    const issuer = new Actor('issuer');
    const iid = registerIssuer(sim, issuer);
    sim.call(sim.governance, 'revokeIssuer', iid);
    expectFail(sim.attempt(issuer, 'issueEntitlement', iid, random32(), random32(), random32(), true, false, random32()), 'issuer revoked');

    const issuer2 = new Actor('issuer2');
    const iid2 = registerIssuer(sim, issuer2, { validUntil: BigInt(sim.now + 10) });
    sim.now += 11;
    expectFail(sim.attempt(issuer2, 'issueEntitlement', iid2, random32(), random32(), random32(), true, false, random32()),
      'issuer authority expired');
  });

  it('another issuer secret cannot mint under this issuer', () => {
    const sim = new RightsSimulator();
    const a = new Actor('a');
    const b = new Actor('b');
    const ia = registerIssuer(sim, a);
    registerIssuer(sim, b);
    // b holds no secret for ia → witness fails closed; b forging ia's secret → hash mismatch.
    expectFail(sim.attempt(b, 'issueEntitlement', ia, random32(), random32(), random32(), true, false, random32()), 'issuerSecret');
    b.privateState = { ...b.privateState, issuerSecrets: { ...b.privateState.issuerSecrets, [Buffer.from(ia).toString('hex')]: Buffer.from(random32()).toString('hex') } };
    expectFail(sim.attempt(b, 'issueEntitlement', ia, random32(), random32(), random32(), true, false, random32()), 'not issuer');
  });

  it('rejects malformed (zero) commitments (invariant 7)', () => {
    const sim = new RightsSimulator();
    const issuer = new Actor('issuer');
    const iid = registerIssuer(sim, issuer);
    expectFail(sim.attempt(issuer, 'issueEntitlement', iid, random32(), ZERO, random32(), true, false, random32()), 'malformed asset');
    expectFail(sim.attempt(issuer, 'issueEntitlement', iid, random32(), random32(), random32(), true, false, ZERO), 'malformed controller');
  });
});

describe('proveControl', () => {
  it('proves control without mutating rights and rejects challenge replay', () => {
    const sim = new RightsSimulator();
    const issuer = new Actor('issuer');
    const holder = new Actor('holder');
    const iid = registerIssuer(sim, issuer);
    const { eid } = issue(sim, issuer, iid, holder);
    const before = sim.ledger().entitlements.lookup(eid);
    const challenge = random32();
    const audience = random32();
    sim.call(holder, 'proveControl', eid, challenge, audience);
    expect(sim.ledger().entitlements.lookup(eid)).toEqual(before);
    expectFail(sim.attempt(holder, 'proveControl', eid, challenge, audience), 'challenge already used');
    // Same challenge for a different audience is a different statement.
    sim.call(holder, 'proveControl', eid, challenge, random32());
  });

  it('a non-holder cannot prove control', () => {
    const sim = new RightsSimulator();
    const issuer = new Actor('issuer');
    const iid = registerIssuer(sim, issuer);
    const { eid } = issue(sim, issuer, iid, new Actor('holder'));
    const thief = new Actor('thief');
    prepareHolder(sim, thief, eid, 1n); // thief has *a* secret for this id, just not the right one
    expectFail(sim.attempt(thief, 'proveControl', eid, random32(), random32()), 'not controller');
  });
});

describe('transfer', () => {
  function setup() {
    const sim = new RightsSimulator();
    const issuer = new Actor('issuer');
    const alice = new Actor('alice');
    const bob = new Actor('bob');
    const iid = registerIssuer(sim, issuer);
    const { eid } = issue(sim, issuer, iid, alice);
    return { sim, issuer, iid, alice, bob, eid };
  }

  it('moves control exactly once and advances the epoch (invariants 1, 2)', () => {
    const { sim, alice, bob, eid } = setup();
    const oid = offer(sim, alice, eid, bob);
    sim.call(bob, 'acceptTransfer', oid);
    const e = sim.ledger().entitlements.lookup(eid);
    expect(e.epoch).toBe(2n);
    expect(sim.ledger().offers.lookup(oid).state).toBe(OfferState.accepted);
    expectFail(sim.attempt(bob, 'acceptTransfer', oid), 'offer not open');
    expectFail(sim.attempt(alice, 'proveControl', eid, random32(), random32()), 'not controller');
    sim.call(bob, 'proveControl', eid, random32(), random32());
  });

  it('only the offered recipient can accept', () => {
    const { sim, alice, bob, eid } = setup();
    const oid = offer(sim, alice, eid, bob);
    const mallory = new Actor('mallory');
    prepareHolder(sim, mallory, eid, 2n);
    expectFail(sim.attempt(mallory, 'acceptTransfer', oid), 'not the offered recipient');
    expectFail(sim.attempt(alice, 'acceptTransfer', oid), 'not the offered recipient');
  });

  it('two concurrent offers at the same epoch: only the first acceptance wins', () => {
    const { sim, alice, bob, eid } = setup();
    const carol = new Actor('carol');
    const o1 = offer(sim, alice, eid, bob);
    const o2 = offer(sim, alice, eid, carol);
    sim.call(carol, 'acceptTransfer', o2);
    expectFail(sim.attempt(bob, 'acceptTransfer', o1), 'stale offer epoch');
  });

  it('expired offers cannot be accepted; non-transferable rights cannot be offered', () => {
    const { sim, issuer, iid, alice, bob, eid } = setup();
    const oid = offer(sim, alice, eid, bob, { expiry: BigInt(sim.now + 5) });
    sim.now += 6;
    expectFail(sim.attempt(bob, 'acceptTransfer', oid), 'offer expired');
    const { eid: locked } = issue(sim, issuer, iid, alice, { transferable: false });
    expectFail(sim.attempt(alice, 'offerTransfer', locked, random32(), random32(), BigInt(sim.now + 100), random32()),
      'right is not transferable');
  });

  it('cancel makes the offer unusable and keeps the entitlement with the sender', () => {
    const { sim, alice, bob, eid } = setup();
    const oid = offer(sim, alice, eid, bob);
    expectFail(sim.attempt(bob, 'cancelTransfer', oid), 'not controller');
    sim.call(alice, 'cancelTransfer', oid);
    expectFail(sim.attempt(bob, 'acceptTransfer', oid), 'offer not open');
    expect(sim.ledger().entitlements.lookup(eid).epoch).toBe(1n);
    sim.call(alice, 'proveControl', eid, random32(), random32());
  });

  it('offer nonce cannot be reused at the same epoch', () => {
    const { sim, alice, eid } = setup();
    const nonce = random32();
    sim.call(alice, 'offerTransfer', eid, nonce, random32(), BigInt(sim.now + 100), random32());
    expectFail(sim.attempt(alice, 'offerTransfer', eid, nonce, random32(), BigInt(sim.now + 100), random32()),
      'offer nonce already used');
  });

  it('revoked entitlements are visibly revoked and inert', () => {
    const { sim, alice, bob, eid } = setup();
    const oid = offer(sim, alice, eid, bob);
    sim.call(sim.governance, 'revokeEntitlement', eid);
    expect(sim.ledger().entitlements.lookup(eid).status).toBe(EntitlementStatus.revoked);
    expectFail(sim.attempt(bob, 'acceptTransfer', oid), 'entitlement not active');
    expectFail(sim.attempt(alice, 'proveControl', eid, random32(), random32()), 'entitlement not active');
  });
});

describe('licensed reproduction', () => {
  it('consumes quota exactly once per job (invariant 5)', () => {
    const { sim, holder, aid } = reprintFixture(3n);
    const job = random32();
    const child = random32();
    sim.call(holder, 'consumeReprintAllowance', aid, job, 2n, child);
    expect(sim.ledger().allowances.lookup(aid).remaining).toBe(1n);
    // Duplicate callback for the same job.
    expectFail(sim.attempt(holder, 'consumeReprintAllowance', aid, job, 2n, child), 'job already consumed');
    expectFail(sim.attempt(holder, 'consumeReprintAllowance', aid, job, 1n, child), 'job already consumed');
    expect(sim.ledger().allowances.lookup(aid).remaining).toBe(1n);
  });

  it('rejects zero quantity, over-quota and over-width quantities (invariant 7)', () => {
    const { sim, holder, aid } = reprintFixture(3n);
    expectFail(sim.attempt(holder, 'consumeReprintAllowance', aid, random32(), 0n, random32()), 'quantity must be positive');
    expectFail(sim.attempt(holder, 'consumeReprintAllowance', aid, random32(), 4n, random32()), 'quota exceeded');
    const overflow = sim.attempt(holder, 'consumeReprintAllowance', aid, random32(), 1n << 32n, random32());
    expect(overflow.ok).toBe(false);
    const negative = sim.attempt(holder, 'consumeReprintAllowance', aid, random32(), -1n, random32());
    expect(negative.ok).toBe(false);
    expect(sim.ledger().allowances.lookup(aid).remaining).toBe(3n);
  });

  it('only the current controller can consume; a transferred-away holder cannot', () => {
    const { sim, holder, eid, aid } = reprintFixture(3n);
    const stranger = new Actor('stranger');
    prepareHolder(sim, stranger, eid, 1n);
    expectFail(sim.attempt(stranger, 'consumeReprintAllowance', aid, random32(), 1n, random32()), 'not controller');
    const bob = new Actor('bob');
    const oid = offer(sim, holder, eid, bob);
    sim.call(bob, 'acceptTransfer', oid);
    expectFail(sim.attempt(holder, 'consumeReprintAllowance', aid, random32(), 1n, random32()), 'not controller');
    sim.call(bob, 'consumeReprintAllowance', aid, random32(), 1n, random32());
  });

  it('one child entitlement per attested unit, only by the authorized manufacturer', () => {
    const { sim, holder, mfr, aid, eid } = reprintFixture(3n);
    const nf = sim.call<Uint8Array>(holder, 'consumeReprintAllowance', aid, random32(), 2n, random32());
    const other = new Actor('other-mfr');
    expectFail(sim.attempt(other, 'attestManufacture', nf, 0n, random32(), random32()), 'manufacturerSecret');
    const c0 = sim.call<Uint8Array>(mfr, 'attestManufacture', nf, 0n, random32(), random32());
    expect(c0).toEqual(derive.childEntitlementId(nf, 0n));
    // Duplicate manufacturer callback for unit 0.
    expectFail(sim.attempt(mfr, 'attestManufacture', nf, 0n, random32(), random32()), 'units must be attested in order');
    sim.call(mfr, 'attestManufacture', nf, 1n, random32(), random32());
    expectFail(sim.attempt(mfr, 'attestManufacture', nf, 2n, random32(), random32()), 'all units already attested');
    const child = sim.ledger().entitlements.lookup(c0);
    expect(child.parentConsumption).toEqual(nf);
    expect(child.reprintable).toBe(false);
    expect(sim.ledger().entitlements.lookup(eid).status).toBe(EntitlementStatus.active); // original remains
  });

  it('manufacturer must be authorized by the same issuer, and active', () => {
    const { sim, issuer, issuerId, eid } = reprintFixture(1n);
    const otherIssuer = new Actor('other-issuer');
    const oiid = registerIssuer(sim, otherIssuer);
    const foreign = registerManufacturer(sim, otherIssuer, oiid, new Actor('foreign'));
    expectFail(sim.attempt(issuer, 'grantReprintAllowance', issuerId, random32(), eid, random32(), foreign, 1n, FAR_FUTURE, random32()),
      'manufacturer not authorized by issuer');
    const m2 = registerManufacturer(sim, issuer, issuerId, new Actor('m2'));
    sim.call(issuer, 'deactivateManufacturer', issuerId, m2);
    expectFail(sim.attempt(issuer, 'grantReprintAllowance', issuerId, random32(), eid, random32(), m2, 1n, FAR_FUTURE, random32()),
      'manufacturer inactive');
  });

  it('non-reprintable rights cannot receive allowances; zero quota rejected', () => {
    const sim = new RightsSimulator();
    const issuer = new Actor('issuer');
    const iid = registerIssuer(sim, issuer);
    const { eid } = issue(sim, issuer, iid, new Actor('h'), { reprintable: false });
    const mid = registerManufacturer(sim, issuer, iid, new Actor('m'));
    expectFail(sim.attempt(issuer, 'grantReprintAllowance', iid, random32(), eid, random32(), mid, 1n, FAR_FUTURE, random32()),
      'no reproduction right');
    const { eid: e2 } = issue(sim, issuer, iid, new Actor('h2'), { reprintable: true });
    expectFail(sim.attempt(issuer, 'grantReprintAllowance', iid, random32(), e2, random32(), mid, 0n, FAR_FUTURE, random32()), 'zero quota');
  });

  it('expired allowances cannot be consumed', () => {
    const { sim, issuer, issuerId, holder, eid, mid } = reprintFixture(1n);
    const aid = grantAllowance(sim, issuer, issuerId, eid, mid, 1n, BigInt(sim.now + 10));
    sim.now += 11;
    expectFail(sim.attempt(holder, 'consumeReprintAllowance', aid, random32(), 1n, random32()), 'allowance expired');
  });

  it('replacement allowance compensates a failed job exactly once and blocks late attestation', () => {
    const { sim, issuer, issuerId, holder, mfr, aid } = reprintFixture(2n);
    const nf = sim.call<Uint8Array>(holder, 'consumeReprintAllowance', aid, random32(), 2n, random32());
    sim.call(mfr, 'attestManufacture', nf, 0n, random32(), random32());
    const repl = sim.call<Uint8Array>(issuer, 'grantReplacementAllowance', issuerId, nf, random32(), FAR_FUTURE);
    expect(sim.ledger().allowances.lookup(repl).remaining).toBe(1n); // only the unproduced unit
    expect(sim.ledger().allowances.lookup(aid).remaining).toBe(0n); // original quota never restored
    expect(sim.ledger().consumptions.lookup(nf).state).toBe(ConsumptionState.cancelled);
    expectFail(sim.attempt(issuer, 'grantReplacementAllowance', issuerId, nf, random32(), FAR_FUTURE), 'already cancelled or replaced');
    expectFail(sim.attempt(mfr, 'attestManufacture', nf, 1n, random32(), random32()), 'consumption cancelled');
  });
});

describe('cross-instance / cross-network binding (invariant 3)', () => {
  it('a holder secret and commitment prepared for one network do not verify on another', () => {
    const preprod = new RightsSimulator('preprod');
    const mainnet = new RightsSimulator('mainnet');
    const issuerP = new Actor('issuerP');
    const iidP = registerIssuer(preprod, issuerP);
    const holder = new Actor('holder');
    const { eid } = issue(preprod, issuerP, iidP, holder);
    // Same issuer/holder ids re-created on the other instance with the *same* secrets.
    const issuerM = new Actor('issuerM');
    const iidM = registerIssuer(mainnet, issuerM);
    const secret = Buffer.from(holder.privateState.holderSecrets[Buffer.from(eid).toString('hex')]!, 'hex');
    const preprodCommitment = commitments.holder(eid, 1n, secret, preprod.binding);
    const mainnetCommitment = commitments.holder(eid, 1n, secret, mainnet.binding);
    expect(Buffer.from(preprodCommitment).equals(Buffer.from(mainnetCommitment))).toBe(false);
    // An offer created on preprod is unknown to mainnet state.
    const bob = new Actor('bob');
    const oid = offer(preprod, holder, eid, bob);
    expect(mainnet.attempt(bob, 'acceptTransfer', oid)).toMatchObject({ ok: false, error: expect.stringContaining('unknown offer') });
    void iidM;
  });
});
