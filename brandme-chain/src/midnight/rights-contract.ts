/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Binding to the compiled `brandme_rights` Compact contract
 * (contracts/src/brandme_rights.compact, compactc 0.31.1).
 *
 * The witnesses here are the only place private secrets enter a circuit.
 * They fail closed: a missing secret throws. They never return a default,
 * a constant, or a value that would let a circuit "authorize itself".
 */

import { fileURLToPath } from 'node:url';
import {
  Contract,

  pureCircuits,
  type Ledger,
  type Witnesses,
} from '../../contracts/managed/brandme_rights/contract/index.js';
import { fromHex, toHex } from './bytes.js';

export {
  Contract as RightsContract,
  ledger as rightsLedger,
  pureCircuits as rightsPure,
  EntitlementStatus,
  OfferState,
  ConsumptionState,
} from '../../contracts/managed/brandme_rights/contract/index.js';
export type {
  Ledger as RightsLedger,
  Entitlement,
  TransferOffer,
  ReprintAllowance,
  ConsumptionRecord,
  IssuerPolicy,
  Manufacturer,
} from '../../contracts/managed/brandme_rights/contract/index.js';

/** Directory holding contract/, keys/, zkir/ for the zk-config provider. */
export const RIGHTS_ARTIFACT_DIR = fileURLToPath(
  new URL('../../contracts/managed/brandme_rights', import.meta.url),
);

export const RIGHTS_CONTRACT_TAG = 'brandme_rights';

/** Role domains — must match the `pad(32, ...)` literals in the contract. */
export const Domain = {
  governance: 'brandme:governance:v1',
  issuer: 'brandme:issuer:v1',
  manufacturer: 'brandme:manufacturer:v1',
} as const;

/**
 * Private state for one account on one contract instance. Secrets are hex
 * strings so every provider serializer round-trips them exactly. This object
 * is only ever persisted through the encrypted, account-scoped private-state
 * provider; it is never logged and never sent to the application backend.
 */
export interface RightsPrivateState {
  readonly schema: 'brandme.rights.private/v1';
  readonly governanceSecret?: string;
  readonly issuerSecrets: Readonly<Record<string, string>>;
  readonly manufacturerSecrets: Readonly<Record<string, string>>;
  /** Keyed by entitlement id (hex). Holds the secret for the epoch the holder controls or is accepting. */
  readonly holderSecrets: Readonly<Record<string, string>>;
}

export const emptyPrivateState = (): RightsPrivateState => ({
  schema: 'brandme.rights.private/v1',
  issuerSecrets: {},
  manufacturerSecrets: {},
  holderSecrets: {},
});

export class MissingWitnessError extends Error {
  constructor(readonly witness: string, readonly key?: string) {
    super(`private state has no ${witness}${key ? ` for ${key.slice(0, 16)}…` : ''}`);
    this.name = 'MissingWitnessError';
  }
}

function secretOrThrow(map: Readonly<Record<string, string>>, witness: string, key: Uint8Array): Uint8Array {
  const k = toHex(key);
  const s = map[k];
  if (!s) throw new MissingWitnessError(witness, k);
  return fromHex(s, 32);
}

export const rightsWitnesses: Witnesses<RightsPrivateState> = {
  governanceSecret: ({ privateState }) => {
    if (!privateState.governanceSecret) throw new MissingWitnessError('governanceSecret');
    return [privateState, fromHex(privateState.governanceSecret, 32)];
  },
  issuerSecret: ({ privateState }, issuerId) => [
    privateState,
    secretOrThrow(privateState.issuerSecrets, 'issuerSecret', issuerId),
  ],
  manufacturerSecret: ({ privateState }, manufacturerId) => [
    privateState,
    secretOrThrow(privateState.manufacturerSecrets, 'manufacturerSecret', manufacturerId),
  ],
  holderSecret: ({ privateState }, entitlementId) => [
    privateState,
    secretOrThrow(privateState.holderSecrets, 'holderSecret', entitlementId),
  ],
};

export const newRightsContract = () => new Contract<RightsPrivateState>(rightsWitnesses);

const padDomain = (s: string): Uint8Array => {
  const b = new TextEncoder().encode(s);
  if (b.length > 32) throw new Error('domain too long');
  const out = new Uint8Array(32);
  out.set(b);
  return out;
};
const ZERO32 = new Uint8Array(32);

/** Instance parameters read from the public ledger; every commitment is bound to them. */
export interface InstanceBinding {
  readonly salt: Uint8Array;
  readonly networkTag: Uint8Array;
}

export const bindingFromLedger = (l: Ledger): InstanceBinding => ({ salt: l.instanceSalt, networkTag: l.networkTag });

export const commitments = {
  governance: (secret: Uint8Array, b: InstanceBinding) =>
    pureCircuits.roleCommitment(padDomain(Domain.governance), ZERO32, secret, b.salt, b.networkTag),
  issuer: (issuerId: Uint8Array, secret: Uint8Array, b: InstanceBinding) =>
    pureCircuits.roleCommitment(padDomain(Domain.issuer), issuerId, secret, b.salt, b.networkTag),
  manufacturer: (manufacturerId: Uint8Array, secret: Uint8Array, b: InstanceBinding) =>
    pureCircuits.roleCommitment(padDomain(Domain.manufacturer), manufacturerId, secret, b.salt, b.networkTag),
  holder: (entitlementId: Uint8Array, epoch: bigint, secret: Uint8Array, b: InstanceBinding) =>
    pureCircuits.holderCommitment(entitlementId, epoch, secret, b.salt, b.networkTag),
};

/** Network tag stored in the contract at deploy time (domain-separated, not a secret). */
export const networkTagFor = (networkId: string): Uint8Array => padDomain(`brandme:net:${networkId}`);

export const derive = {
  entitlementId: pureCircuits.deriveEntitlementId,
  childEntitlementId: pureCircuits.deriveChildEntitlementId,
  offerId: pureCircuits.deriveOfferId,
  allowanceId: pureCircuits.deriveAllowanceId,
  consumptionNullifier: pureCircuits.deriveConsumptionNullifier,
  challengeKey: pureCircuits.deriveChallengeKey,
};

/** Returns a private state with one more secret recorded (immutable update). */
export const withSecret = (
  ps: RightsPrivateState,
  kind: 'issuer' | 'manufacturer' | 'holder',
  key: Uint8Array,
  secret: Uint8Array,
): RightsPrivateState => {
  const field = `${kind}Secrets` as const;
  return { ...ps, [field]: { ...ps[field], [toHex(key)]: toHex(secret) } };
};

export const withoutHolderSecret = (ps: RightsPrivateState, entitlementId: Uint8Array): RightsPrivateState => {
  const { [toHex(entitlementId)]: _dropped, ...rest } = ps.holderSecrets;
  void _dropped;
  return { ...ps, holderSecrets: rest };
};
