import type * as __compactRuntime from '@midnight-ntwrk/compact-runtime';

export enum EntitlementStatus { active = 0, revoked = 1 }

export enum OfferState { open = 0, accepted = 1, cancelled = 2 }

export enum ConsumptionState { reserved = 0, cancelled = 1 }

export type IssuerPolicy = { authCommitment: Uint8Array;
                             policyVersion: bigint;
                             maxIssuance: bigint;
                             issued: bigint;
                             validUntil: bigint;
                             active: boolean
                           };

export type Entitlement = { issuerId: Uint8Array;
                            assetCommitment: Uint8Array;
                            policyDigest: Uint8Array;
                            controllerCommitment: Uint8Array;
                            epoch: bigint;
                            transferable: boolean;
                            reprintable: boolean;
                            parentConsumption: Uint8Array;
                            status: EntitlementStatus
                          };

export type TransferOffer = { entitlementId: Uint8Array;
                              senderEpoch: bigint;
                              recipientCommitment: Uint8Array;
                              expiry: bigint;
                              termsDigest: Uint8Array;
                              state: OfferState
                            };

export type Manufacturer = { issuerId: Uint8Array;
                             authCommitment: Uint8Array;
                             active: boolean
                           };

export type ReprintAllowance = { issuerId: Uint8Array;
                                 entitlementId: Uint8Array;
                                 designDigest: Uint8Array;
                                 manufacturerId: Uint8Array;
                                 remaining: bigint;
                                 validUntil: bigint;
                                 policyDigest: Uint8Array
                               };

export type ConsumptionRecord = { allowanceId: Uint8Array;
                                  jobCommitment: Uint8Array;
                                  quantity: bigint;
                                  attested: bigint;
                                  childControllerCommitment: Uint8Array;
                                  state: ConsumptionState;
                                  replacedBy: Uint8Array
                                };

export type Witnesses<PS> = {
  governanceSecret(context: __compactRuntime.WitnessContext<Ledger, PS>): [PS, Uint8Array];
  issuerSecret(context: __compactRuntime.WitnessContext<Ledger, PS>,
               issuerId_0: Uint8Array): [PS, Uint8Array];
  manufacturerSecret(context: __compactRuntime.WitnessContext<Ledger, PS>,
                     manufacturerId_0: Uint8Array): [PS, Uint8Array];
  holderSecret(context: __compactRuntime.WitnessContext<Ledger, PS>,
               entitlementId_0: Uint8Array): [PS, Uint8Array];
}

export type ImpureCircuits<PS> = {
  registerIssuer(context: __compactRuntime.CircuitContext<PS>,
                 issuerId_0: Uint8Array,
                 authCommitment_0: Uint8Array,
                 policyVersion_0: bigint,
                 maxIssuance_0: bigint,
                 validUntil_0: bigint): __compactRuntime.CircuitResults<PS, []>;
  rotateIssuerKey(context: __compactRuntime.CircuitContext<PS>,
                  issuerId_0: Uint8Array,
                  newAuthCommitment_0: Uint8Array,
                  newPolicyVersion_0: bigint): __compactRuntime.CircuitResults<PS, []>;
  revokeIssuer(context: __compactRuntime.CircuitContext<PS>,
               issuerId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  issueEntitlement(context: __compactRuntime.CircuitContext<PS>,
                   issuerId_0: Uint8Array,
                   issuanceId_0: Uint8Array,
                   assetCommitment_0: Uint8Array,
                   policyDigest_0: Uint8Array,
                   transferable_0: boolean,
                   reprintable_0: boolean,
                   controllerCommitment_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  proveControl(context: __compactRuntime.CircuitContext<PS>,
               entitlementId_0: Uint8Array,
               challenge_0: Uint8Array,
               audience_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  offerTransfer(context: __compactRuntime.CircuitContext<PS>,
                entitlementId_0: Uint8Array,
                nonce_0: Uint8Array,
                recipientCommitment_0: Uint8Array,
                expiry_0: bigint,
                termsDigest_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  acceptTransfer(context: __compactRuntime.CircuitContext<PS>,
                 offerId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  cancelTransfer(context: __compactRuntime.CircuitContext<PS>,
                 offerId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  revokeEntitlement(context: __compactRuntime.CircuitContext<PS>,
                    entitlementId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  registerManufacturer(context: __compactRuntime.CircuitContext<PS>,
                       issuerId_0: Uint8Array,
                       manufacturerId_0: Uint8Array,
                       authCommitment_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  deactivateManufacturer(context: __compactRuntime.CircuitContext<PS>,
                         issuerId_0: Uint8Array,
                         manufacturerId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  grantReprintAllowance(context: __compactRuntime.CircuitContext<PS>,
                        issuerId_0: Uint8Array,
                        nonce_0: Uint8Array,
                        entitlementId_0: Uint8Array,
                        designDigest_0: Uint8Array,
                        manufacturerId_0: Uint8Array,
                        quota_0: bigint,
                        validUntil_0: bigint,
                        policyDigest_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  consumeReprintAllowance(context: __compactRuntime.CircuitContext<PS>,
                          allowanceId_0: Uint8Array,
                          jobCommitment_0: Uint8Array,
                          quantity_0: bigint,
                          childControllerCommitment_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  attestManufacture(context: __compactRuntime.CircuitContext<PS>,
                    nullifier_0: Uint8Array,
                    unit_0: bigint,
                    childAssetCommitment_0: Uint8Array,
                    evidenceDigest_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  grantReplacementAllowance(context: __compactRuntime.CircuitContext<PS>,
                            issuerId_0: Uint8Array,
                            failedNullifier_0: Uint8Array,
                            nonce_0: Uint8Array,
                            validUntil_0: bigint): __compactRuntime.CircuitResults<PS, Uint8Array>;
}

export type ProvableCircuits<PS> = {
  registerIssuer(context: __compactRuntime.CircuitContext<PS>,
                 issuerId_0: Uint8Array,
                 authCommitment_0: Uint8Array,
                 policyVersion_0: bigint,
                 maxIssuance_0: bigint,
                 validUntil_0: bigint): __compactRuntime.CircuitResults<PS, []>;
  rotateIssuerKey(context: __compactRuntime.CircuitContext<PS>,
                  issuerId_0: Uint8Array,
                  newAuthCommitment_0: Uint8Array,
                  newPolicyVersion_0: bigint): __compactRuntime.CircuitResults<PS, []>;
  revokeIssuer(context: __compactRuntime.CircuitContext<PS>,
               issuerId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  issueEntitlement(context: __compactRuntime.CircuitContext<PS>,
                   issuerId_0: Uint8Array,
                   issuanceId_0: Uint8Array,
                   assetCommitment_0: Uint8Array,
                   policyDigest_0: Uint8Array,
                   transferable_0: boolean,
                   reprintable_0: boolean,
                   controllerCommitment_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  proveControl(context: __compactRuntime.CircuitContext<PS>,
               entitlementId_0: Uint8Array,
               challenge_0: Uint8Array,
               audience_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  offerTransfer(context: __compactRuntime.CircuitContext<PS>,
                entitlementId_0: Uint8Array,
                nonce_0: Uint8Array,
                recipientCommitment_0: Uint8Array,
                expiry_0: bigint,
                termsDigest_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  acceptTransfer(context: __compactRuntime.CircuitContext<PS>,
                 offerId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  cancelTransfer(context: __compactRuntime.CircuitContext<PS>,
                 offerId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  revokeEntitlement(context: __compactRuntime.CircuitContext<PS>,
                    entitlementId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  registerManufacturer(context: __compactRuntime.CircuitContext<PS>,
                       issuerId_0: Uint8Array,
                       manufacturerId_0: Uint8Array,
                       authCommitment_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  deactivateManufacturer(context: __compactRuntime.CircuitContext<PS>,
                         issuerId_0: Uint8Array,
                         manufacturerId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  grantReprintAllowance(context: __compactRuntime.CircuitContext<PS>,
                        issuerId_0: Uint8Array,
                        nonce_0: Uint8Array,
                        entitlementId_0: Uint8Array,
                        designDigest_0: Uint8Array,
                        manufacturerId_0: Uint8Array,
                        quota_0: bigint,
                        validUntil_0: bigint,
                        policyDigest_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  consumeReprintAllowance(context: __compactRuntime.CircuitContext<PS>,
                          allowanceId_0: Uint8Array,
                          jobCommitment_0: Uint8Array,
                          quantity_0: bigint,
                          childControllerCommitment_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  attestManufacture(context: __compactRuntime.CircuitContext<PS>,
                    nullifier_0: Uint8Array,
                    unit_0: bigint,
                    childAssetCommitment_0: Uint8Array,
                    evidenceDigest_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  grantReplacementAllowance(context: __compactRuntime.CircuitContext<PS>,
                            issuerId_0: Uint8Array,
                            failedNullifier_0: Uint8Array,
                            nonce_0: Uint8Array,
                            validUntil_0: bigint): __compactRuntime.CircuitResults<PS, Uint8Array>;
}

export type PureCircuits = {
  roleCommitment(domain_0: Uint8Array,
                 scope_0: Uint8Array,
                 secret_0: Uint8Array,
                 salt_0: Uint8Array,
                 network_0: Uint8Array): Uint8Array;
  holderCommitment(entitlementId_0: Uint8Array,
                   epoch_0: bigint,
                   secret_0: Uint8Array,
                   salt_0: Uint8Array,
                   network_0: Uint8Array): Uint8Array;
  deriveEntitlementId(issuerId_0: Uint8Array, issuanceId_0: Uint8Array): Uint8Array;
  deriveChildEntitlementId(nullifier_0: Uint8Array, unit_0: bigint): Uint8Array;
  deriveOfferId(entitlementId_0: Uint8Array,
                epoch_0: bigint,
                nonce_0: Uint8Array): Uint8Array;
  deriveAllowanceId(issuerId_0: Uint8Array, nonce_0: Uint8Array): Uint8Array;
  deriveConsumptionNullifier(allowanceId_0: Uint8Array,
                             jobCommitment_0: Uint8Array): Uint8Array;
  deriveChallengeKey(entitlementId_0: Uint8Array,
                     epoch_0: bigint,
                     challenge_0: Uint8Array,
                     audience_0: Uint8Array): Uint8Array;
}

export type Circuits<PS> = {
  roleCommitment(context: __compactRuntime.CircuitContext<PS>,
                 domain_0: Uint8Array,
                 scope_0: Uint8Array,
                 secret_0: Uint8Array,
                 salt_0: Uint8Array,
                 network_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  holderCommitment(context: __compactRuntime.CircuitContext<PS>,
                   entitlementId_0: Uint8Array,
                   epoch_0: bigint,
                   secret_0: Uint8Array,
                   salt_0: Uint8Array,
                   network_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  deriveEntitlementId(context: __compactRuntime.CircuitContext<PS>,
                      issuerId_0: Uint8Array,
                      issuanceId_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  deriveChildEntitlementId(context: __compactRuntime.CircuitContext<PS>,
                           nullifier_0: Uint8Array,
                           unit_0: bigint): __compactRuntime.CircuitResults<PS, Uint8Array>;
  deriveOfferId(context: __compactRuntime.CircuitContext<PS>,
                entitlementId_0: Uint8Array,
                epoch_0: bigint,
                nonce_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  deriveAllowanceId(context: __compactRuntime.CircuitContext<PS>,
                    issuerId_0: Uint8Array,
                    nonce_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  deriveConsumptionNullifier(context: __compactRuntime.CircuitContext<PS>,
                             allowanceId_0: Uint8Array,
                             jobCommitment_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  deriveChallengeKey(context: __compactRuntime.CircuitContext<PS>,
                     entitlementId_0: Uint8Array,
                     epoch_0: bigint,
                     challenge_0: Uint8Array,
                     audience_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  registerIssuer(context: __compactRuntime.CircuitContext<PS>,
                 issuerId_0: Uint8Array,
                 authCommitment_0: Uint8Array,
                 policyVersion_0: bigint,
                 maxIssuance_0: bigint,
                 validUntil_0: bigint): __compactRuntime.CircuitResults<PS, []>;
  rotateIssuerKey(context: __compactRuntime.CircuitContext<PS>,
                  issuerId_0: Uint8Array,
                  newAuthCommitment_0: Uint8Array,
                  newPolicyVersion_0: bigint): __compactRuntime.CircuitResults<PS, []>;
  revokeIssuer(context: __compactRuntime.CircuitContext<PS>,
               issuerId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  issueEntitlement(context: __compactRuntime.CircuitContext<PS>,
                   issuerId_0: Uint8Array,
                   issuanceId_0: Uint8Array,
                   assetCommitment_0: Uint8Array,
                   policyDigest_0: Uint8Array,
                   transferable_0: boolean,
                   reprintable_0: boolean,
                   controllerCommitment_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  proveControl(context: __compactRuntime.CircuitContext<PS>,
               entitlementId_0: Uint8Array,
               challenge_0: Uint8Array,
               audience_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  offerTransfer(context: __compactRuntime.CircuitContext<PS>,
                entitlementId_0: Uint8Array,
                nonce_0: Uint8Array,
                recipientCommitment_0: Uint8Array,
                expiry_0: bigint,
                termsDigest_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  acceptTransfer(context: __compactRuntime.CircuitContext<PS>,
                 offerId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  cancelTransfer(context: __compactRuntime.CircuitContext<PS>,
                 offerId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  revokeEntitlement(context: __compactRuntime.CircuitContext<PS>,
                    entitlementId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  registerManufacturer(context: __compactRuntime.CircuitContext<PS>,
                       issuerId_0: Uint8Array,
                       manufacturerId_0: Uint8Array,
                       authCommitment_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  deactivateManufacturer(context: __compactRuntime.CircuitContext<PS>,
                         issuerId_0: Uint8Array,
                         manufacturerId_0: Uint8Array): __compactRuntime.CircuitResults<PS, []>;
  grantReprintAllowance(context: __compactRuntime.CircuitContext<PS>,
                        issuerId_0: Uint8Array,
                        nonce_0: Uint8Array,
                        entitlementId_0: Uint8Array,
                        designDigest_0: Uint8Array,
                        manufacturerId_0: Uint8Array,
                        quota_0: bigint,
                        validUntil_0: bigint,
                        policyDigest_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  consumeReprintAllowance(context: __compactRuntime.CircuitContext<PS>,
                          allowanceId_0: Uint8Array,
                          jobCommitment_0: Uint8Array,
                          quantity_0: bigint,
                          childControllerCommitment_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  attestManufacture(context: __compactRuntime.CircuitContext<PS>,
                    nullifier_0: Uint8Array,
                    unit_0: bigint,
                    childAssetCommitment_0: Uint8Array,
                    evidenceDigest_0: Uint8Array): __compactRuntime.CircuitResults<PS, Uint8Array>;
  grantReplacementAllowance(context: __compactRuntime.CircuitContext<PS>,
                            issuerId_0: Uint8Array,
                            failedNullifier_0: Uint8Array,
                            nonce_0: Uint8Array,
                            validUntil_0: bigint): __compactRuntime.CircuitResults<PS, Uint8Array>;
}

export type Ledger = {
  readonly instanceSalt: Uint8Array;
  readonly networkTag: Uint8Array;
  readonly governanceCommitment: Uint8Array;
  issuers: {
    isEmpty(): boolean;
    size(): bigint;
    member(key_0: Uint8Array): boolean;
    lookup(key_0: Uint8Array): IssuerPolicy;
    [Symbol.iterator](): Iterator<[Uint8Array, IssuerPolicy]>
  };
  entitlements: {
    isEmpty(): boolean;
    size(): bigint;
    member(key_0: Uint8Array): boolean;
    lookup(key_0: Uint8Array): Entitlement;
    [Symbol.iterator](): Iterator<[Uint8Array, Entitlement]>
  };
  offers: {
    isEmpty(): boolean;
    size(): bigint;
    member(key_0: Uint8Array): boolean;
    lookup(key_0: Uint8Array): TransferOffer;
    [Symbol.iterator](): Iterator<[Uint8Array, TransferOffer]>
  };
  usedChallenges: {
    isEmpty(): boolean;
    size(): bigint;
    member(elem_0: Uint8Array): boolean;
    [Symbol.iterator](): Iterator<Uint8Array>
  };
  manufacturers: {
    isEmpty(): boolean;
    size(): bigint;
    member(key_0: Uint8Array): boolean;
    lookup(key_0: Uint8Array): Manufacturer;
    [Symbol.iterator](): Iterator<[Uint8Array, Manufacturer]>
  };
  allowances: {
    isEmpty(): boolean;
    size(): bigint;
    member(key_0: Uint8Array): boolean;
    lookup(key_0: Uint8Array): ReprintAllowance;
    [Symbol.iterator](): Iterator<[Uint8Array, ReprintAllowance]>
  };
  consumptions: {
    isEmpty(): boolean;
    size(): bigint;
    member(key_0: Uint8Array): boolean;
    lookup(key_0: Uint8Array): ConsumptionRecord;
    [Symbol.iterator](): Iterator<[Uint8Array, ConsumptionRecord]>
  };
  readonly sequence: bigint;
}

export type ContractReferenceLocations = any;

export declare const contractReferenceLocations : ContractReferenceLocations;

export declare class Contract<PS = any, W extends Witnesses<PS> = Witnesses<PS>> {
  witnesses: W;
  circuits: Circuits<PS>;
  impureCircuits: ImpureCircuits<PS>;
  provableCircuits: ProvableCircuits<PS>;
  constructor(witnesses: W);
  initialState(context: __compactRuntime.ConstructorContext<PS>,
               salt_0: Uint8Array,
               network_0: Uint8Array,
               governance_0: Uint8Array): __compactRuntime.ConstructorResult<PS>;
}

export declare function ledger(state: __compactRuntime.StateValue | __compactRuntime.ChargedState): Ledger;
export declare const pureCircuits: PureCircuits;
