import { randomUUID } from 'node:crypto';
import { FinalizedEntitlementProjector, IndexerFinalizedLedgerReader, affectedEntitlement } from '../../src/midnight/projection.js';
import { newOperation, transition, type ChainOperation } from '../../src/midnight/operations.js';
import { localEndpoints } from '../../src/midnight/network.js';
import { toHex, random32 } from '../../src/midnight/bytes.js';
import { derive } from '../../src/midnight/rights-contract.js';
import { Actor, RightsSimulator, registerIssuer, issue, offer, reprintFixture } from '../support/scenario.js';

const endpoints = localEndpoints({ node: 9944, indexer: 8088 });
const hash = 'ab'.repeat(32);
function finalized(sim: RightsSimulator, circuit: string, args: unknown[]): ChainOperation {
  let op = newOperation({ network: 'undeployed', contractAddress: sim.address, circuit, args,
    ownerRef: randomUUID(), subjectRef: randomUUID() });
  op = transition(op, 'Proving');
  op = transition(op, 'Reconciling', { evidence: { txId: randomUUID(), observedAt: new Date().toISOString() } });
  op = transition(op, 'Observed', { evidence: { ...op.evidence!, blockHeight: 12, blockHash: hash, status: 'SucceedEntirely' } });
  return transition(op, 'Finalized', { evidence: { ...op.evidence!, finalizedHeadHeight: 15 } });
}
const response = (sim: RightsSimulator) => ({ data: { contractAction: { address: sim.address,
  state: sim.serializedState(), transaction: { block: { height: 12, hash } } } } });
function fixture() {
  const sim = new RightsSimulator(); const issuer = new Actor('issuer'); const holder = new Actor('holder');
  const issuerId = registerIssuer(sim, issuer); const { eid, issuanceId } = issue(sim, issuer, issuerId, holder);
  const op = finalized(sim, 'issueEntitlement', [issuerId, issuanceId]);
  const finality = { isFinal: vi.fn().mockResolvedValue({ final: true, finalizedHeadHeight: 15 }) };
  const doFetch = vi.fn().mockImplementation(async () => Response.json(response(sim)));
  const reader = new IndexerFinalizedLedgerReader(endpoints, doFetch);
  const projector = new FinalizedEntitlementProjector({ network: 'undeployed', contractAddress: sim.address, reader, finality });
  return { sim, issuer, holder, issuerId, eid, op, finality, doFetch, projector };
}

describe('finalized public entitlement projection', () => {
  it('decodes real compiled ledger state at the requested block without deriving private links', async () => {
    const f = fixture();
    const result = await f.projector.project(f.op);
    expect(result).toEqual({ entitlementId: toHex(f.eid), issuerId: toHex(f.issuerId), epoch: 1,
      status: 'active', transferable: true, reprintable: false, parentConsumption: null });
    expect(JSON.stringify(result)).not.toContain(f.op.ownerRef);
    const init = f.doFetch.mock.calls[0]![1];
    expect(JSON.parse(init.body).variables).toEqual({ address: f.sim.address, offset: { blockOffset: { hash } } });
    expect(init.redirect).toBe('error');
  });
  it('reads transferred and revoked state from the ledger, never from request arguments', async () => {
    const f = fixture(); const recipient = new Actor('recipient');
    const oid = offer(f.sim, f.holder, f.eid, recipient); f.sim.call(recipient, 'acceptTransfer', oid);
    expect(await f.projector.project(finalized(f.sim, 'acceptTransfer', [oid])))
      .toMatchObject({ entitlementId: toHex(f.eid), epoch: 2, status: 'active' });
    f.sim.call(f.sim.governance, 'revokeEntitlement', f.eid);
    expect(await f.projector.project(finalized(f.sim, 'revokeEntitlement', [f.eid])))
      .toMatchObject({ entitlementId: toHex(f.eid), epoch: 2, status: 'revoked' });
  });
  it('derives a manufactured child from the nullifier and unit through the real circuit', async () => {
    const f = reprintFixture();
    const nf = f.sim.call<Uint8Array>(f.holder, 'consumeReprintAllowance', f.aid, random32(), 1n, random32());
    const cid = f.sim.call<Uint8Array>(f.mfr, 'attestManufacture', nf, 0n, random32(), random32());
    const projector = new FinalizedEntitlementProjector({ network: 'undeployed', contractAddress: f.sim.address,
      finality: { isFinal: async () => ({ final: true, finalizedHeadHeight: 15 }) },
      reader: new IndexerFinalizedLedgerReader(endpoints, async () => Response.json(response(f.sim))) });
    expect(await projector.project(finalized(f.sim, 'attestManufacture', [nf, 0n])))
      .toMatchObject({ entitlementId: toHex(cid), parentConsumption: toHex(nf), epoch: 1, reprintable: false });
    expect(toHex(cid)).toBe(toHex(derive.childEntitlementId(nf, 0n)));
  });
  it('rejects unfinalized, noncanonical, out-of-scope and wrong-network evidence before projection', async () => {
    const f = fixture();
    await expect(f.projector.project({ ...f.op, state: 'Observed' })).rejects.toThrow();
    f.finality.isFinal.mockResolvedValue({ final: false, finalizedHeadHeight: 11 });
    await expect(f.projector.project(f.op)).rejects.toThrow(/canonical/); expect(f.doFetch).not.toHaveBeenCalled();
    f.finality.isFinal.mockResolvedValue({ final: true, finalizedHeadHeight: 15 });
    const wrong = new FinalizedEntitlementProjector({ network: 'preview', contractAddress: f.sim.address,
      finality: f.finality, reader: { read: async () => f.sim.ledger() } });
    await expect(wrong.project(f.op)).rejects.toThrow(/scope/);
    const other = new RightsSimulator('preview');
    f.doFetch.mockResolvedValue(Response.json({ data: { contractAction: { ...response(f.sim).data.contractAction, state: other.serializedState() } } }));
    await expect(f.projector.project(f.op)).rejects.toThrow(/network/);
  });
  it('rejects the latest state, another contract, GraphQL errors, invalid serialization and oversized responses', async () => {
    const f = fixture(); const body = response(f.sim);
    for (const value of [
      { data: { contractAction: { ...body.data.contractAction, transaction: { block: { height: 13, hash } } } } },
      { data: { contractAction: { ...body.data.contractAction, transaction: { block: { height: 12, hash: 'cd'.repeat(32) } } } } },
      { data: { contractAction: { ...body.data.contractAction, address: 'ef'.repeat(32) } } },
      { ...body, errors: [{}] }, { data: { contractAction: null } },
      { data: { contractAction: { ...body.data.contractAction, state: '00' } } },
    ]) {
      f.doFetch.mockImplementation(async () => Response.json(value));
      await expect(f.projector.project(f.op)).rejects.toThrow();
    }
    f.doFetch.mockImplementation(async () => new Response('x'.repeat(8 * 1024 * 1024 + 1)));
    await expect(f.projector.project(f.op)).rejects.toThrow(/too large/);
  });
  it('does not silently complete unknown circuits or malformed entitlement references', () => {
    const f = fixture();
    expect(() => affectedEntitlement({ ...f.op, circuit: 'unknownCircuit' }, f.sim.ledger())).toThrow(/unsupported/);
    expect(() => affectedEntitlement({ ...f.op, args: [] }, f.sim.ledger())).toThrow(/arguments/);
    expect(affectedEntitlement({ ...f.op, circuit: 'proveControl' }, f.sim.ledger())).toBeNull();
  });
});
