/** Public entitlement facts derived from the compiled ledger at a finalized block. */
import { z } from 'zod';
import { ContractState } from '@midnight-ntwrk/compact-runtime';
import type { FinalityOracle } from './adapter.js';
import { indexerQuery } from './indexer-query.js';
import { fromHex, toHex } from './bytes.js';
import type { MidnightEndpoints } from './network.js';
import { validateOperation, type ChainOperation } from './operations.js';
import { derive, rightsLedger, networkTagFor, EntitlementStatus, type RightsLedger } from './rights-contract.js';

const hex = z.string().regex(/^[0-9a-f]{64}$/);
export const entitlementSchema = z.object({
  entitlementId: hex, issuerId: hex, epoch: z.number().int().min(1).max(0xffffffff),
  status: z.enum(['active', 'revoked']), transferable: z.boolean(), reprintable: z.boolean(),
  parentConsumption: hex.nullable(),
}).strict();
export type EntitlementProjection = z.infer<typeof entitlementSchema>;
export interface FinalizedLedgerReader { read(op: ChainOperation): Promise<RightsLedger> }

const query = `query FinalizedRightsState($address: HexEncoded!, $offset: ContractActionOffset) {
  contractAction(address: $address, offset: $offset) {
    address state transaction { block { height hash } }
  }
}`;
const blockHash = (value: string) => value.replace(/^0x/i, '').toLowerCase();

export class IndexerFinalizedLedgerReader implements FinalizedLedgerReader {
  constructor(private readonly endpoints: MidnightEndpoints, private readonly doFetch: typeof fetch = fetch) {}
  async read(op: ChainOperation): Promise<RightsLedger> {
    if (op.network !== this.endpoints.networkId) throw new Error('indexer network mismatch');
    const e = op.evidence!;
    const body = z.object({ errors: z.array(z.unknown()).optional(), data: z.object({ contractAction: z.object({
      address: hex, state: z.string().regex(/^(?:[0-9a-f]{2})+$/i),
      transaction: z.object({ block: z.object({ height: z.number().int().nonnegative().safe(), hash: z.string() }) }),
    }).nullable() }) }).parse(await indexerQuery(this.endpoints.indexerHttp, query,
      { address: op.contractAddress, offset: { blockOffset: { hash: blockHash(e.blockHash!) } } }, this.doFetch, 8 * 1024 * 1024));
    const action = body.data.contractAction;
    if (body.errors?.length || !action || action.address !== op.contractAddress ||
        action.transaction.block.height !== e.blockHeight || blockHash(action.transaction.block.hash) !== blockHash(e.blockHash!)) {
      throw new Error('contract state does not match the finalized block');
    }
    return rightsLedger(ContractState.deserialize(fromHex(action.state)).data);
  }
}

/** Resolve only contract-defined IDs; an application subject/owner is never an entitlement ID. */
export function affectedEntitlement(op: ChainOperation, ledger: RightsLedger): Uint8Array | null {
  const bytes = (i: number) => {
    const arg = op.args[i];
    if (arg?.t !== 'bytes' || !/^[0-9a-f]{64}$/.test(arg.v)) throw new Error('invalid entitlement circuit arguments');
    return fromHex(arg.v, 32);
  };
  switch (op.circuit) {
    case 'issueEntitlement': return derive.entitlementId(bytes(0), bytes(1));
    case 'acceptTransfer': return ledger.offers.lookup(bytes(0)).entitlementId;
    case 'revokeEntitlement': return bytes(0);
    case 'attestManufacture': {
      const unit = op.args[1];
      if (unit?.t !== 'uint' || BigInt(unit.v) > 0xffffffffn) throw new Error('invalid manufacture unit');
      return derive.childEntitlementId(bytes(0), BigInt(unit.v));
    }
    case 'registerIssuer': case 'rotateIssuerKey': case 'revokeIssuer': case 'proveControl':
    case 'offerTransfer': case 'cancelTransfer': case 'registerManufacturer': case 'deactivateManufacturer':
    case 'grantReprintAllowance': case 'consumeReprintAllowance': case 'grantReplacementAllowance': return null;
    default: throw new Error('unsupported projection circuit');
  }
}

export class FinalizedEntitlementProjector {
  constructor(private readonly o: { network: string; contractAddress: string; reader: FinalizedLedgerReader; finality: FinalityOracle }) {}
  async project(op: ChainOperation): Promise<EntitlementProjection | null> {
    validateOperation(op);
    if (op.network === 'mainnet' || op.network !== this.o.network || op.contractAddress !== this.o.contractAddress.toLowerCase() ||
        !['Finalized', 'HandoverPending', 'HandoverAcknowledged'].includes(op.state)) throw new Error('operation is not finalized in projection scope');
    const e = op.evidence!;
    if (!(await this.o.finality.isFinal(e.blockHeight!, e.blockHash!)).final) throw new Error('projection block is not canonical and finalized');
    // Even no-op projections validate the real contract instance and exact block.
    const ledger = await this.o.reader.read(op);
    if (toHex(ledger.networkTag) !== toHex(networkTagFor(op.network))) throw new Error('ledger network mismatch');
    const id = affectedEntitlement(op, ledger);
    if (!id) return null;
    const ent = ledger.entitlements.lookup(id);
    if (![EntitlementStatus.active, EntitlementStatus.revoked].includes(ent.status)) throw new Error('invalid entitlement status');
    return entitlementSchema.parse({ entitlementId: toHex(id), issuerId: toHex(ent.issuerId), epoch: Number(ent.epoch),
      status: ent.status === EntitlementStatus.active ? 'active' : 'revoked', transferable: ent.transferable,
      reprintable: ent.reprintable, parentConsumption: ent.parentConsumption.every((v) => v === 0) ? null : toHex(ent.parentConsumption) });
  }
}
