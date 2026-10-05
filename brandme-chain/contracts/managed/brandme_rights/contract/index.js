import * as __compactRuntime from '@midnight-ntwrk/compact-runtime';
__compactRuntime.checkRuntimeVersion('0.16.0');

export var EntitlementStatus;
(function (EntitlementStatus) {
  EntitlementStatus[EntitlementStatus['active'] = 0] = 'active';
  EntitlementStatus[EntitlementStatus['revoked'] = 1] = 'revoked';
})(EntitlementStatus || (EntitlementStatus = {}));

export var OfferState;
(function (OfferState) {
  OfferState[OfferState['open'] = 0] = 'open';
  OfferState[OfferState['accepted'] = 1] = 'accepted';
  OfferState[OfferState['cancelled'] = 2] = 'cancelled';
})(OfferState || (OfferState = {}));

export var ConsumptionState;
(function (ConsumptionState) {
  ConsumptionState[ConsumptionState['reserved'] = 0] = 'reserved';
  ConsumptionState[ConsumptionState['cancelled'] = 1] = 'cancelled';
})(ConsumptionState || (ConsumptionState = {}));

const _descriptor_0 = new __compactRuntime.CompactTypeBytes(32);

const _descriptor_1 = new __compactRuntime.CompactTypeUnsignedInteger(4294967295n, 4);

const _descriptor_2 = new __compactRuntime.CompactTypeEnum(1, 1);

class _ConsumptionRecord_0 {
  alignment() {
    return _descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_1.alignment().concat(_descriptor_1.alignment().concat(_descriptor_0.alignment().concat(_descriptor_2.alignment().concat(_descriptor_0.alignment()))))));
  }
  fromValue(value_0) {
    return {
      allowanceId: _descriptor_0.fromValue(value_0),
      jobCommitment: _descriptor_0.fromValue(value_0),
      quantity: _descriptor_1.fromValue(value_0),
      attested: _descriptor_1.fromValue(value_0),
      childControllerCommitment: _descriptor_0.fromValue(value_0),
      state: _descriptor_2.fromValue(value_0),
      replacedBy: _descriptor_0.fromValue(value_0)
    }
  }
  toValue(value_0) {
    return _descriptor_0.toValue(value_0.allowanceId).concat(_descriptor_0.toValue(value_0.jobCommitment).concat(_descriptor_1.toValue(value_0.quantity).concat(_descriptor_1.toValue(value_0.attested).concat(_descriptor_0.toValue(value_0.childControllerCommitment).concat(_descriptor_2.toValue(value_0.state).concat(_descriptor_0.toValue(value_0.replacedBy)))))));
  }
}

const _descriptor_3 = new _ConsumptionRecord_0();

const _descriptor_4 = __compactRuntime.CompactTypeBoolean;

const _descriptor_5 = new __compactRuntime.CompactTypeUnsignedInteger(65535n, 2);

const _descriptor_6 = new __compactRuntime.CompactTypeUnsignedInteger(18446744073709551615n, 8);

class _ReprintAllowance_0 {
  alignment() {
    return _descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_1.alignment().concat(_descriptor_6.alignment().concat(_descriptor_0.alignment()))))));
  }
  fromValue(value_0) {
    return {
      issuerId: _descriptor_0.fromValue(value_0),
      entitlementId: _descriptor_0.fromValue(value_0),
      designDigest: _descriptor_0.fromValue(value_0),
      manufacturerId: _descriptor_0.fromValue(value_0),
      remaining: _descriptor_1.fromValue(value_0),
      validUntil: _descriptor_6.fromValue(value_0),
      policyDigest: _descriptor_0.fromValue(value_0)
    }
  }
  toValue(value_0) {
    return _descriptor_0.toValue(value_0.issuerId).concat(_descriptor_0.toValue(value_0.entitlementId).concat(_descriptor_0.toValue(value_0.designDigest).concat(_descriptor_0.toValue(value_0.manufacturerId).concat(_descriptor_1.toValue(value_0.remaining).concat(_descriptor_6.toValue(value_0.validUntil).concat(_descriptor_0.toValue(value_0.policyDigest)))))));
  }
}

const _descriptor_7 = new _ReprintAllowance_0();

const _descriptor_8 = new __compactRuntime.CompactTypeEnum(1, 1);

class _Entitlement_0 {
  alignment() {
    return _descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_1.alignment().concat(_descriptor_4.alignment().concat(_descriptor_4.alignment().concat(_descriptor_0.alignment().concat(_descriptor_8.alignment()))))))));
  }
  fromValue(value_0) {
    return {
      issuerId: _descriptor_0.fromValue(value_0),
      assetCommitment: _descriptor_0.fromValue(value_0),
      policyDigest: _descriptor_0.fromValue(value_0),
      controllerCommitment: _descriptor_0.fromValue(value_0),
      epoch: _descriptor_1.fromValue(value_0),
      transferable: _descriptor_4.fromValue(value_0),
      reprintable: _descriptor_4.fromValue(value_0),
      parentConsumption: _descriptor_0.fromValue(value_0),
      status: _descriptor_8.fromValue(value_0)
    }
  }
  toValue(value_0) {
    return _descriptor_0.toValue(value_0.issuerId).concat(_descriptor_0.toValue(value_0.assetCommitment).concat(_descriptor_0.toValue(value_0.policyDigest).concat(_descriptor_0.toValue(value_0.controllerCommitment).concat(_descriptor_1.toValue(value_0.epoch).concat(_descriptor_4.toValue(value_0.transferable).concat(_descriptor_4.toValue(value_0.reprintable).concat(_descriptor_0.toValue(value_0.parentConsumption).concat(_descriptor_8.toValue(value_0.status)))))))));
  }
}

const _descriptor_9 = new _Entitlement_0();

class _Manufacturer_0 {
  alignment() {
    return _descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_4.alignment()));
  }
  fromValue(value_0) {
    return {
      issuerId: _descriptor_0.fromValue(value_0),
      authCommitment: _descriptor_0.fromValue(value_0),
      active: _descriptor_4.fromValue(value_0)
    }
  }
  toValue(value_0) {
    return _descriptor_0.toValue(value_0.issuerId).concat(_descriptor_0.toValue(value_0.authCommitment).concat(_descriptor_4.toValue(value_0.active)));
  }
}

const _descriptor_10 = new _Manufacturer_0();

const _descriptor_11 = new __compactRuntime.CompactTypeEnum(2, 1);

class _TransferOffer_0 {
  alignment() {
    return _descriptor_0.alignment().concat(_descriptor_1.alignment().concat(_descriptor_0.alignment().concat(_descriptor_6.alignment().concat(_descriptor_0.alignment().concat(_descriptor_11.alignment())))));
  }
  fromValue(value_0) {
    return {
      entitlementId: _descriptor_0.fromValue(value_0),
      senderEpoch: _descriptor_1.fromValue(value_0),
      recipientCommitment: _descriptor_0.fromValue(value_0),
      expiry: _descriptor_6.fromValue(value_0),
      termsDigest: _descriptor_0.fromValue(value_0),
      state: _descriptor_11.fromValue(value_0)
    }
  }
  toValue(value_0) {
    return _descriptor_0.toValue(value_0.entitlementId).concat(_descriptor_1.toValue(value_0.senderEpoch).concat(_descriptor_0.toValue(value_0.recipientCommitment).concat(_descriptor_6.toValue(value_0.expiry).concat(_descriptor_0.toValue(value_0.termsDigest).concat(_descriptor_11.toValue(value_0.state))))));
  }
}

const _descriptor_12 = new _TransferOffer_0();

class _IssuerPolicy_0 {
  alignment() {
    return _descriptor_0.alignment().concat(_descriptor_1.alignment().concat(_descriptor_1.alignment().concat(_descriptor_1.alignment().concat(_descriptor_6.alignment().concat(_descriptor_4.alignment())))));
  }
  fromValue(value_0) {
    return {
      authCommitment: _descriptor_0.fromValue(value_0),
      policyVersion: _descriptor_1.fromValue(value_0),
      maxIssuance: _descriptor_1.fromValue(value_0),
      issued: _descriptor_1.fromValue(value_0),
      validUntil: _descriptor_6.fromValue(value_0),
      active: _descriptor_4.fromValue(value_0)
    }
  }
  toValue(value_0) {
    return _descriptor_0.toValue(value_0.authCommitment).concat(_descriptor_1.toValue(value_0.policyVersion).concat(_descriptor_1.toValue(value_0.maxIssuance).concat(_descriptor_1.toValue(value_0.issued).concat(_descriptor_6.toValue(value_0.validUntil).concat(_descriptor_4.toValue(value_0.active))))));
  }
}

const _descriptor_13 = new _IssuerPolicy_0();

const _descriptor_14 = new __compactRuntime.CompactTypeVector(3, _descriptor_0);

const _descriptor_15 = new __compactRuntime.CompactTypeVector(5, _descriptor_0);

const _descriptor_16 = new __compactRuntime.CompactTypeVector(6, _descriptor_0);

const _descriptor_17 = new __compactRuntime.CompactTypeVector(4, _descriptor_0);

class _Either_0 {
  alignment() {
    return _descriptor_4.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment()));
  }
  fromValue(value_0) {
    return {
      is_left: _descriptor_4.fromValue(value_0),
      left: _descriptor_0.fromValue(value_0),
      right: _descriptor_0.fromValue(value_0)
    }
  }
  toValue(value_0) {
    return _descriptor_4.toValue(value_0.is_left).concat(_descriptor_0.toValue(value_0.left).concat(_descriptor_0.toValue(value_0.right)));
  }
}

const _descriptor_18 = new _Either_0();

const _descriptor_19 = new __compactRuntime.CompactTypeUnsignedInteger(340282366920938463463374607431768211455n, 16);

class _ContractAddress_0 {
  alignment() {
    return _descriptor_0.alignment();
  }
  fromValue(value_0) {
    return {
      bytes: _descriptor_0.fromValue(value_0)
    }
  }
  toValue(value_0) {
    return _descriptor_0.toValue(value_0.bytes);
  }
}

const _descriptor_20 = new _ContractAddress_0();

const _descriptor_21 = new __compactRuntime.CompactTypeUnsignedInteger(255n, 1);

export class Contract {
  witnesses;
  constructor(...args_0) {
    if (args_0.length !== 1) {
      throw new __compactRuntime.CompactError(`Contract constructor: expected 1 argument, received ${args_0.length}`);
    }
    const witnesses_0 = args_0[0];
    if (typeof(witnesses_0) !== 'object') {
      throw new __compactRuntime.CompactError('first (witnesses) argument to Contract constructor is not an object');
    }
    if (typeof(witnesses_0.governanceSecret) !== 'function') {
      throw new __compactRuntime.CompactError('first (witnesses) argument to Contract constructor does not contain a function-valued field named governanceSecret');
    }
    if (typeof(witnesses_0.issuerSecret) !== 'function') {
      throw new __compactRuntime.CompactError('first (witnesses) argument to Contract constructor does not contain a function-valued field named issuerSecret');
    }
    if (typeof(witnesses_0.manufacturerSecret) !== 'function') {
      throw new __compactRuntime.CompactError('first (witnesses) argument to Contract constructor does not contain a function-valued field named manufacturerSecret');
    }
    if (typeof(witnesses_0.holderSecret) !== 'function') {
      throw new __compactRuntime.CompactError('first (witnesses) argument to Contract constructor does not contain a function-valued field named holderSecret');
    }
    this.witnesses = witnesses_0;
    this.circuits = {
      roleCommitment(context, ...args_1) {
        return { result: pureCircuits.roleCommitment(...args_1), context };
      },
      holderCommitment(context, ...args_1) {
        return { result: pureCircuits.holderCommitment(...args_1), context };
      },
      deriveEntitlementId(context, ...args_1) {
        return { result: pureCircuits.deriveEntitlementId(...args_1), context };
      },
      deriveChildEntitlementId(context, ...args_1) {
        return { result: pureCircuits.deriveChildEntitlementId(...args_1), context };
      },
      deriveOfferId(context, ...args_1) {
        return { result: pureCircuits.deriveOfferId(...args_1), context };
      },
      deriveAllowanceId(context, ...args_1) {
        return { result: pureCircuits.deriveAllowanceId(...args_1), context };
      },
      deriveConsumptionNullifier(context, ...args_1) {
        return { result: pureCircuits.deriveConsumptionNullifier(...args_1), context };
      },
      deriveChallengeKey(context, ...args_1) {
        return { result: pureCircuits.deriveChallengeKey(...args_1), context };
      },
      registerIssuer: (...args_1) => {
        if (args_1.length !== 6) {
          throw new __compactRuntime.CompactError(`registerIssuer: expected 6 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const issuerId_0 = args_1[1];
        const authCommitment_0 = args_1[2];
        const policyVersion_0 = args_1[3];
        const maxIssuance_0 = args_1[4];
        const validUntil_0 = args_1[5];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('registerIssuer',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 207 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(issuerId_0.buffer instanceof ArrayBuffer && issuerId_0.BYTES_PER_ELEMENT === 1 && issuerId_0.length === 32)) {
          __compactRuntime.typeError('registerIssuer',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 207 char 1',
                                     'Bytes<32>',
                                     issuerId_0)
        }
        if (!(authCommitment_0.buffer instanceof ArrayBuffer && authCommitment_0.BYTES_PER_ELEMENT === 1 && authCommitment_0.length === 32)) {
          __compactRuntime.typeError('registerIssuer',
                                     'argument 2 (argument 3 as invoked from Typescript)',
                                     'brandme_rights.compact line 207 char 1',
                                     'Bytes<32>',
                                     authCommitment_0)
        }
        if (!(typeof(policyVersion_0) === 'bigint' && policyVersion_0 >= 0n && policyVersion_0 <= 4294967295n)) {
          __compactRuntime.typeError('registerIssuer',
                                     'argument 3 (argument 4 as invoked from Typescript)',
                                     'brandme_rights.compact line 207 char 1',
                                     'Uint<0..4294967296>',
                                     policyVersion_0)
        }
        if (!(typeof(maxIssuance_0) === 'bigint' && maxIssuance_0 >= 0n && maxIssuance_0 <= 4294967295n)) {
          __compactRuntime.typeError('registerIssuer',
                                     'argument 4 (argument 5 as invoked from Typescript)',
                                     'brandme_rights.compact line 207 char 1',
                                     'Uint<0..4294967296>',
                                     maxIssuance_0)
        }
        if (!(typeof(validUntil_0) === 'bigint' && validUntil_0 >= 0n && validUntil_0 <= 18446744073709551615n)) {
          __compactRuntime.typeError('registerIssuer',
                                     'argument 5 (argument 6 as invoked from Typescript)',
                                     'brandme_rights.compact line 207 char 1',
                                     'Uint<0..18446744073709551616>',
                                     validUntil_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(issuerId_0).concat(_descriptor_0.toValue(authCommitment_0).concat(_descriptor_1.toValue(policyVersion_0).concat(_descriptor_1.toValue(maxIssuance_0).concat(_descriptor_6.toValue(validUntil_0))))),
            alignment: _descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_1.alignment().concat(_descriptor_1.alignment().concat(_descriptor_6.alignment()))))
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._registerIssuer_0(context,
                                                partialProofData,
                                                issuerId_0,
                                                authCommitment_0,
                                                policyVersion_0,
                                                maxIssuance_0,
                                                validUntil_0);
        partialProofData.output = { value: [], alignment: [] };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      rotateIssuerKey: (...args_1) => {
        if (args_1.length !== 4) {
          throw new __compactRuntime.CompactError(`rotateIssuerKey: expected 4 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const issuerId_0 = args_1[1];
        const newAuthCommitment_0 = args_1[2];
        const newPolicyVersion_0 = args_1[3];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('rotateIssuerKey',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 227 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(issuerId_0.buffer instanceof ArrayBuffer && issuerId_0.BYTES_PER_ELEMENT === 1 && issuerId_0.length === 32)) {
          __compactRuntime.typeError('rotateIssuerKey',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 227 char 1',
                                     'Bytes<32>',
                                     issuerId_0)
        }
        if (!(newAuthCommitment_0.buffer instanceof ArrayBuffer && newAuthCommitment_0.BYTES_PER_ELEMENT === 1 && newAuthCommitment_0.length === 32)) {
          __compactRuntime.typeError('rotateIssuerKey',
                                     'argument 2 (argument 3 as invoked from Typescript)',
                                     'brandme_rights.compact line 227 char 1',
                                     'Bytes<32>',
                                     newAuthCommitment_0)
        }
        if (!(typeof(newPolicyVersion_0) === 'bigint' && newPolicyVersion_0 >= 0n && newPolicyVersion_0 <= 4294967295n)) {
          __compactRuntime.typeError('rotateIssuerKey',
                                     'argument 3 (argument 4 as invoked from Typescript)',
                                     'brandme_rights.compact line 227 char 1',
                                     'Uint<0..4294967296>',
                                     newPolicyVersion_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(issuerId_0).concat(_descriptor_0.toValue(newAuthCommitment_0).concat(_descriptor_1.toValue(newPolicyVersion_0))),
            alignment: _descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_1.alignment()))
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._rotateIssuerKey_0(context,
                                                 partialProofData,
                                                 issuerId_0,
                                                 newAuthCommitment_0,
                                                 newPolicyVersion_0);
        partialProofData.output = { value: [], alignment: [] };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      revokeIssuer: (...args_1) => {
        if (args_1.length !== 2) {
          throw new __compactRuntime.CompactError(`revokeIssuer: expected 2 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const issuerId_0 = args_1[1];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('revokeIssuer',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 246 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(issuerId_0.buffer instanceof ArrayBuffer && issuerId_0.BYTES_PER_ELEMENT === 1 && issuerId_0.length === 32)) {
          __compactRuntime.typeError('revokeIssuer',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 246 char 1',
                                     'Bytes<32>',
                                     issuerId_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(issuerId_0),
            alignment: _descriptor_0.alignment()
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._revokeIssuer_0(context,
                                              partialProofData,
                                              issuerId_0);
        partialProofData.output = { value: [], alignment: [] };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      issueEntitlement: (...args_1) => {
        if (args_1.length !== 8) {
          throw new __compactRuntime.CompactError(`issueEntitlement: expected 8 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const issuerId_0 = args_1[1];
        const issuanceId_0 = args_1[2];
        const assetCommitment_0 = args_1[3];
        const policyDigest_0 = args_1[4];
        const transferable_0 = args_1[5];
        const reprintable_0 = args_1[6];
        const controllerCommitment_0 = args_1[7];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('issueEntitlement',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 264 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(issuerId_0.buffer instanceof ArrayBuffer && issuerId_0.BYTES_PER_ELEMENT === 1 && issuerId_0.length === 32)) {
          __compactRuntime.typeError('issueEntitlement',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 264 char 1',
                                     'Bytes<32>',
                                     issuerId_0)
        }
        if (!(issuanceId_0.buffer instanceof ArrayBuffer && issuanceId_0.BYTES_PER_ELEMENT === 1 && issuanceId_0.length === 32)) {
          __compactRuntime.typeError('issueEntitlement',
                                     'argument 2 (argument 3 as invoked from Typescript)',
                                     'brandme_rights.compact line 264 char 1',
                                     'Bytes<32>',
                                     issuanceId_0)
        }
        if (!(assetCommitment_0.buffer instanceof ArrayBuffer && assetCommitment_0.BYTES_PER_ELEMENT === 1 && assetCommitment_0.length === 32)) {
          __compactRuntime.typeError('issueEntitlement',
                                     'argument 3 (argument 4 as invoked from Typescript)',
                                     'brandme_rights.compact line 264 char 1',
                                     'Bytes<32>',
                                     assetCommitment_0)
        }
        if (!(policyDigest_0.buffer instanceof ArrayBuffer && policyDigest_0.BYTES_PER_ELEMENT === 1 && policyDigest_0.length === 32)) {
          __compactRuntime.typeError('issueEntitlement',
                                     'argument 4 (argument 5 as invoked from Typescript)',
                                     'brandme_rights.compact line 264 char 1',
                                     'Bytes<32>',
                                     policyDigest_0)
        }
        if (!(typeof(transferable_0) === 'boolean')) {
          __compactRuntime.typeError('issueEntitlement',
                                     'argument 5 (argument 6 as invoked from Typescript)',
                                     'brandme_rights.compact line 264 char 1',
                                     'Boolean',
                                     transferable_0)
        }
        if (!(typeof(reprintable_0) === 'boolean')) {
          __compactRuntime.typeError('issueEntitlement',
                                     'argument 6 (argument 7 as invoked from Typescript)',
                                     'brandme_rights.compact line 264 char 1',
                                     'Boolean',
                                     reprintable_0)
        }
        if (!(controllerCommitment_0.buffer instanceof ArrayBuffer && controllerCommitment_0.BYTES_PER_ELEMENT === 1 && controllerCommitment_0.length === 32)) {
          __compactRuntime.typeError('issueEntitlement',
                                     'argument 7 (argument 8 as invoked from Typescript)',
                                     'brandme_rights.compact line 264 char 1',
                                     'Bytes<32>',
                                     controllerCommitment_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(issuerId_0).concat(_descriptor_0.toValue(issuanceId_0).concat(_descriptor_0.toValue(assetCommitment_0).concat(_descriptor_0.toValue(policyDigest_0).concat(_descriptor_4.toValue(transferable_0).concat(_descriptor_4.toValue(reprintable_0).concat(_descriptor_0.toValue(controllerCommitment_0))))))),
            alignment: _descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_4.alignment().concat(_descriptor_4.alignment().concat(_descriptor_0.alignment()))))))
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._issueEntitlement_0(context,
                                                  partialProofData,
                                                  issuerId_0,
                                                  issuanceId_0,
                                                  assetCommitment_0,
                                                  policyDigest_0,
                                                  transferable_0,
                                                  reprintable_0,
                                                  controllerCommitment_0);
        partialProofData.output = { value: _descriptor_0.toValue(result_0), alignment: _descriptor_0.alignment() };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      proveControl: (...args_1) => {
        if (args_1.length !== 4) {
          throw new __compactRuntime.CompactError(`proveControl: expected 4 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const entitlementId_0 = args_1[1];
        const challenge_0 = args_1[2];
        const audience_0 = args_1[3];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('proveControl',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 300 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(entitlementId_0.buffer instanceof ArrayBuffer && entitlementId_0.BYTES_PER_ELEMENT === 1 && entitlementId_0.length === 32)) {
          __compactRuntime.typeError('proveControl',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 300 char 1',
                                     'Bytes<32>',
                                     entitlementId_0)
        }
        if (!(challenge_0.buffer instanceof ArrayBuffer && challenge_0.BYTES_PER_ELEMENT === 1 && challenge_0.length === 32)) {
          __compactRuntime.typeError('proveControl',
                                     'argument 2 (argument 3 as invoked from Typescript)',
                                     'brandme_rights.compact line 300 char 1',
                                     'Bytes<32>',
                                     challenge_0)
        }
        if (!(audience_0.buffer instanceof ArrayBuffer && audience_0.BYTES_PER_ELEMENT === 1 && audience_0.length === 32)) {
          __compactRuntime.typeError('proveControl',
                                     'argument 3 (argument 4 as invoked from Typescript)',
                                     'brandme_rights.compact line 300 char 1',
                                     'Bytes<32>',
                                     audience_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(entitlementId_0).concat(_descriptor_0.toValue(challenge_0).concat(_descriptor_0.toValue(audience_0))),
            alignment: _descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment()))
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._proveControl_0(context,
                                              partialProofData,
                                              entitlementId_0,
                                              challenge_0,
                                              audience_0);
        partialProofData.output = { value: [], alignment: [] };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      offerTransfer: (...args_1) => {
        if (args_1.length !== 6) {
          throw new __compactRuntime.CompactError(`offerTransfer: expected 6 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const entitlementId_0 = args_1[1];
        const nonce_0 = args_1[2];
        const recipientCommitment_0 = args_1[3];
        const expiry_0 = args_1[4];
        const termsDigest_0 = args_1[5];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('offerTransfer',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 309 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(entitlementId_0.buffer instanceof ArrayBuffer && entitlementId_0.BYTES_PER_ELEMENT === 1 && entitlementId_0.length === 32)) {
          __compactRuntime.typeError('offerTransfer',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 309 char 1',
                                     'Bytes<32>',
                                     entitlementId_0)
        }
        if (!(nonce_0.buffer instanceof ArrayBuffer && nonce_0.BYTES_PER_ELEMENT === 1 && nonce_0.length === 32)) {
          __compactRuntime.typeError('offerTransfer',
                                     'argument 2 (argument 3 as invoked from Typescript)',
                                     'brandme_rights.compact line 309 char 1',
                                     'Bytes<32>',
                                     nonce_0)
        }
        if (!(recipientCommitment_0.buffer instanceof ArrayBuffer && recipientCommitment_0.BYTES_PER_ELEMENT === 1 && recipientCommitment_0.length === 32)) {
          __compactRuntime.typeError('offerTransfer',
                                     'argument 3 (argument 4 as invoked from Typescript)',
                                     'brandme_rights.compact line 309 char 1',
                                     'Bytes<32>',
                                     recipientCommitment_0)
        }
        if (!(typeof(expiry_0) === 'bigint' && expiry_0 >= 0n && expiry_0 <= 18446744073709551615n)) {
          __compactRuntime.typeError('offerTransfer',
                                     'argument 4 (argument 5 as invoked from Typescript)',
                                     'brandme_rights.compact line 309 char 1',
                                     'Uint<0..18446744073709551616>',
                                     expiry_0)
        }
        if (!(termsDigest_0.buffer instanceof ArrayBuffer && termsDigest_0.BYTES_PER_ELEMENT === 1 && termsDigest_0.length === 32)) {
          __compactRuntime.typeError('offerTransfer',
                                     'argument 5 (argument 6 as invoked from Typescript)',
                                     'brandme_rights.compact line 309 char 1',
                                     'Bytes<32>',
                                     termsDigest_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(entitlementId_0).concat(_descriptor_0.toValue(nonce_0).concat(_descriptor_0.toValue(recipientCommitment_0).concat(_descriptor_6.toValue(expiry_0).concat(_descriptor_0.toValue(termsDigest_0))))),
            alignment: _descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_6.alignment().concat(_descriptor_0.alignment()))))
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._offerTransfer_0(context,
                                               partialProofData,
                                               entitlementId_0,
                                               nonce_0,
                                               recipientCommitment_0,
                                               expiry_0,
                                               termsDigest_0);
        partialProofData.output = { value: _descriptor_0.toValue(result_0), alignment: _descriptor_0.alignment() };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      acceptTransfer: (...args_1) => {
        if (args_1.length !== 2) {
          throw new __compactRuntime.CompactError(`acceptTransfer: expected 2 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const offerId_0 = args_1[1];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('acceptTransfer',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 334 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(offerId_0.buffer instanceof ArrayBuffer && offerId_0.BYTES_PER_ELEMENT === 1 && offerId_0.length === 32)) {
          __compactRuntime.typeError('acceptTransfer',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 334 char 1',
                                     'Bytes<32>',
                                     offerId_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(offerId_0),
            alignment: _descriptor_0.alignment()
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._acceptTransfer_0(context,
                                                partialProofData,
                                                offerId_0);
        partialProofData.output = { value: [], alignment: [] };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      cancelTransfer: (...args_1) => {
        if (args_1.length !== 2) {
          throw new __compactRuntime.CompactError(`cancelTransfer: expected 2 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const offerId_0 = args_1[1];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('cancelTransfer',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 369 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(offerId_0.buffer instanceof ArrayBuffer && offerId_0.BYTES_PER_ELEMENT === 1 && offerId_0.length === 32)) {
          __compactRuntime.typeError('cancelTransfer',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 369 char 1',
                                     'Bytes<32>',
                                     offerId_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(offerId_0),
            alignment: _descriptor_0.alignment()
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._cancelTransfer_0(context,
                                                partialProofData,
                                                offerId_0);
        partialProofData.output = { value: [], alignment: [] };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      revokeEntitlement: (...args_1) => {
        if (args_1.length !== 2) {
          throw new __compactRuntime.CompactError(`revokeEntitlement: expected 2 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const entitlementId_0 = args_1[1];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('revokeEntitlement',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 389 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(entitlementId_0.buffer instanceof ArrayBuffer && entitlementId_0.BYTES_PER_ELEMENT === 1 && entitlementId_0.length === 32)) {
          __compactRuntime.typeError('revokeEntitlement',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 389 char 1',
                                     'Bytes<32>',
                                     entitlementId_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(entitlementId_0),
            alignment: _descriptor_0.alignment()
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._revokeEntitlement_0(context,
                                                   partialProofData,
                                                   entitlementId_0);
        partialProofData.output = { value: [], alignment: [] };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      registerManufacturer: (...args_1) => {
        if (args_1.length !== 4) {
          throw new __compactRuntime.CompactError(`registerManufacturer: expected 4 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const issuerId_0 = args_1[1];
        const manufacturerId_0 = args_1[2];
        const authCommitment_0 = args_1[3];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('registerManufacturer',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 410 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(issuerId_0.buffer instanceof ArrayBuffer && issuerId_0.BYTES_PER_ELEMENT === 1 && issuerId_0.length === 32)) {
          __compactRuntime.typeError('registerManufacturer',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 410 char 1',
                                     'Bytes<32>',
                                     issuerId_0)
        }
        if (!(manufacturerId_0.buffer instanceof ArrayBuffer && manufacturerId_0.BYTES_PER_ELEMENT === 1 && manufacturerId_0.length === 32)) {
          __compactRuntime.typeError('registerManufacturer',
                                     'argument 2 (argument 3 as invoked from Typescript)',
                                     'brandme_rights.compact line 410 char 1',
                                     'Bytes<32>',
                                     manufacturerId_0)
        }
        if (!(authCommitment_0.buffer instanceof ArrayBuffer && authCommitment_0.BYTES_PER_ELEMENT === 1 && authCommitment_0.length === 32)) {
          __compactRuntime.typeError('registerManufacturer',
                                     'argument 3 (argument 4 as invoked from Typescript)',
                                     'brandme_rights.compact line 410 char 1',
                                     'Bytes<32>',
                                     authCommitment_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(issuerId_0).concat(_descriptor_0.toValue(manufacturerId_0).concat(_descriptor_0.toValue(authCommitment_0))),
            alignment: _descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment()))
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._registerManufacturer_0(context,
                                                      partialProofData,
                                                      issuerId_0,
                                                      manufacturerId_0,
                                                      authCommitment_0);
        partialProofData.output = { value: [], alignment: [] };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      deactivateManufacturer: (...args_1) => {
        if (args_1.length !== 3) {
          throw new __compactRuntime.CompactError(`deactivateManufacturer: expected 3 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const issuerId_0 = args_1[1];
        const manufacturerId_0 = args_1[2];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('deactivateManufacturer',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 421 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(issuerId_0.buffer instanceof ArrayBuffer && issuerId_0.BYTES_PER_ELEMENT === 1 && issuerId_0.length === 32)) {
          __compactRuntime.typeError('deactivateManufacturer',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 421 char 1',
                                     'Bytes<32>',
                                     issuerId_0)
        }
        if (!(manufacturerId_0.buffer instanceof ArrayBuffer && manufacturerId_0.BYTES_PER_ELEMENT === 1 && manufacturerId_0.length === 32)) {
          __compactRuntime.typeError('deactivateManufacturer',
                                     'argument 2 (argument 3 as invoked from Typescript)',
                                     'brandme_rights.compact line 421 char 1',
                                     'Bytes<32>',
                                     manufacturerId_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(issuerId_0).concat(_descriptor_0.toValue(manufacturerId_0)),
            alignment: _descriptor_0.alignment().concat(_descriptor_0.alignment())
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._deactivateManufacturer_0(context,
                                                        partialProofData,
                                                        issuerId_0,
                                                        manufacturerId_0);
        partialProofData.output = { value: [], alignment: [] };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      grantReprintAllowance: (...args_1) => {
        if (args_1.length !== 9) {
          throw new __compactRuntime.CompactError(`grantReprintAllowance: expected 9 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const issuerId_0 = args_1[1];
        const nonce_0 = args_1[2];
        const entitlementId_0 = args_1[3];
        const designDigest_0 = args_1[4];
        const manufacturerId_0 = args_1[5];
        const quota_0 = args_1[6];
        const validUntil_0 = args_1[7];
        const policyDigest_0 = args_1[8];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('grantReprintAllowance',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 432 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(issuerId_0.buffer instanceof ArrayBuffer && issuerId_0.BYTES_PER_ELEMENT === 1 && issuerId_0.length === 32)) {
          __compactRuntime.typeError('grantReprintAllowance',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 432 char 1',
                                     'Bytes<32>',
                                     issuerId_0)
        }
        if (!(nonce_0.buffer instanceof ArrayBuffer && nonce_0.BYTES_PER_ELEMENT === 1 && nonce_0.length === 32)) {
          __compactRuntime.typeError('grantReprintAllowance',
                                     'argument 2 (argument 3 as invoked from Typescript)',
                                     'brandme_rights.compact line 432 char 1',
                                     'Bytes<32>',
                                     nonce_0)
        }
        if (!(entitlementId_0.buffer instanceof ArrayBuffer && entitlementId_0.BYTES_PER_ELEMENT === 1 && entitlementId_0.length === 32)) {
          __compactRuntime.typeError('grantReprintAllowance',
                                     'argument 3 (argument 4 as invoked from Typescript)',
                                     'brandme_rights.compact line 432 char 1',
                                     'Bytes<32>',
                                     entitlementId_0)
        }
        if (!(designDigest_0.buffer instanceof ArrayBuffer && designDigest_0.BYTES_PER_ELEMENT === 1 && designDigest_0.length === 32)) {
          __compactRuntime.typeError('grantReprintAllowance',
                                     'argument 4 (argument 5 as invoked from Typescript)',
                                     'brandme_rights.compact line 432 char 1',
                                     'Bytes<32>',
                                     designDigest_0)
        }
        if (!(manufacturerId_0.buffer instanceof ArrayBuffer && manufacturerId_0.BYTES_PER_ELEMENT === 1 && manufacturerId_0.length === 32)) {
          __compactRuntime.typeError('grantReprintAllowance',
                                     'argument 5 (argument 6 as invoked from Typescript)',
                                     'brandme_rights.compact line 432 char 1',
                                     'Bytes<32>',
                                     manufacturerId_0)
        }
        if (!(typeof(quota_0) === 'bigint' && quota_0 >= 0n && quota_0 <= 4294967295n)) {
          __compactRuntime.typeError('grantReprintAllowance',
                                     'argument 6 (argument 7 as invoked from Typescript)',
                                     'brandme_rights.compact line 432 char 1',
                                     'Uint<0..4294967296>',
                                     quota_0)
        }
        if (!(typeof(validUntil_0) === 'bigint' && validUntil_0 >= 0n && validUntil_0 <= 18446744073709551615n)) {
          __compactRuntime.typeError('grantReprintAllowance',
                                     'argument 7 (argument 8 as invoked from Typescript)',
                                     'brandme_rights.compact line 432 char 1',
                                     'Uint<0..18446744073709551616>',
                                     validUntil_0)
        }
        if (!(policyDigest_0.buffer instanceof ArrayBuffer && policyDigest_0.BYTES_PER_ELEMENT === 1 && policyDigest_0.length === 32)) {
          __compactRuntime.typeError('grantReprintAllowance',
                                     'argument 8 (argument 9 as invoked from Typescript)',
                                     'brandme_rights.compact line 432 char 1',
                                     'Bytes<32>',
                                     policyDigest_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(issuerId_0).concat(_descriptor_0.toValue(nonce_0).concat(_descriptor_0.toValue(entitlementId_0).concat(_descriptor_0.toValue(designDigest_0).concat(_descriptor_0.toValue(manufacturerId_0).concat(_descriptor_1.toValue(quota_0).concat(_descriptor_6.toValue(validUntil_0).concat(_descriptor_0.toValue(policyDigest_0)))))))),
            alignment: _descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_1.alignment().concat(_descriptor_6.alignment().concat(_descriptor_0.alignment())))))))
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._grantReprintAllowance_0(context,
                                                       partialProofData,
                                                       issuerId_0,
                                                       nonce_0,
                                                       entitlementId_0,
                                                       designDigest_0,
                                                       manufacturerId_0,
                                                       quota_0,
                                                       validUntil_0,
                                                       policyDigest_0);
        partialProofData.output = { value: _descriptor_0.toValue(result_0), alignment: _descriptor_0.alignment() };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      consumeReprintAllowance: (...args_1) => {
        if (args_1.length !== 5) {
          throw new __compactRuntime.CompactError(`consumeReprintAllowance: expected 5 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const allowanceId_0 = args_1[1];
        const jobCommitment_0 = args_1[2];
        const quantity_0 = args_1[3];
        const childControllerCommitment_0 = args_1[4];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('consumeReprintAllowance',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 468 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(allowanceId_0.buffer instanceof ArrayBuffer && allowanceId_0.BYTES_PER_ELEMENT === 1 && allowanceId_0.length === 32)) {
          __compactRuntime.typeError('consumeReprintAllowance',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 468 char 1',
                                     'Bytes<32>',
                                     allowanceId_0)
        }
        if (!(jobCommitment_0.buffer instanceof ArrayBuffer && jobCommitment_0.BYTES_PER_ELEMENT === 1 && jobCommitment_0.length === 32)) {
          __compactRuntime.typeError('consumeReprintAllowance',
                                     'argument 2 (argument 3 as invoked from Typescript)',
                                     'brandme_rights.compact line 468 char 1',
                                     'Bytes<32>',
                                     jobCommitment_0)
        }
        if (!(typeof(quantity_0) === 'bigint' && quantity_0 >= 0n && quantity_0 <= 4294967295n)) {
          __compactRuntime.typeError('consumeReprintAllowance',
                                     'argument 3 (argument 4 as invoked from Typescript)',
                                     'brandme_rights.compact line 468 char 1',
                                     'Uint<0..4294967296>',
                                     quantity_0)
        }
        if (!(childControllerCommitment_0.buffer instanceof ArrayBuffer && childControllerCommitment_0.BYTES_PER_ELEMENT === 1 && childControllerCommitment_0.length === 32)) {
          __compactRuntime.typeError('consumeReprintAllowance',
                                     'argument 4 (argument 5 as invoked from Typescript)',
                                     'brandme_rights.compact line 468 char 1',
                                     'Bytes<32>',
                                     childControllerCommitment_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(allowanceId_0).concat(_descriptor_0.toValue(jobCommitment_0).concat(_descriptor_1.toValue(quantity_0).concat(_descriptor_0.toValue(childControllerCommitment_0)))),
            alignment: _descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_1.alignment().concat(_descriptor_0.alignment())))
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._consumeReprintAllowance_0(context,
                                                         partialProofData,
                                                         allowanceId_0,
                                                         jobCommitment_0,
                                                         quantity_0,
                                                         childControllerCommitment_0);
        partialProofData.output = { value: _descriptor_0.toValue(result_0), alignment: _descriptor_0.alignment() };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      attestManufacture: (...args_1) => {
        if (args_1.length !== 5) {
          throw new __compactRuntime.CompactError(`attestManufacture: expected 5 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const nullifier_0 = args_1[1];
        const unit_0 = args_1[2];
        const childAssetCommitment_0 = args_1[3];
        const evidenceDigest_0 = args_1[4];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('attestManufacture',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 508 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(nullifier_0.buffer instanceof ArrayBuffer && nullifier_0.BYTES_PER_ELEMENT === 1 && nullifier_0.length === 32)) {
          __compactRuntime.typeError('attestManufacture',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 508 char 1',
                                     'Bytes<32>',
                                     nullifier_0)
        }
        if (!(typeof(unit_0) === 'bigint' && unit_0 >= 0n && unit_0 <= 4294967295n)) {
          __compactRuntime.typeError('attestManufacture',
                                     'argument 2 (argument 3 as invoked from Typescript)',
                                     'brandme_rights.compact line 508 char 1',
                                     'Uint<0..4294967296>',
                                     unit_0)
        }
        if (!(childAssetCommitment_0.buffer instanceof ArrayBuffer && childAssetCommitment_0.BYTES_PER_ELEMENT === 1 && childAssetCommitment_0.length === 32)) {
          __compactRuntime.typeError('attestManufacture',
                                     'argument 3 (argument 4 as invoked from Typescript)',
                                     'brandme_rights.compact line 508 char 1',
                                     'Bytes<32>',
                                     childAssetCommitment_0)
        }
        if (!(evidenceDigest_0.buffer instanceof ArrayBuffer && evidenceDigest_0.BYTES_PER_ELEMENT === 1 && evidenceDigest_0.length === 32)) {
          __compactRuntime.typeError('attestManufacture',
                                     'argument 4 (argument 5 as invoked from Typescript)',
                                     'brandme_rights.compact line 508 char 1',
                                     'Bytes<32>',
                                     evidenceDigest_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(nullifier_0).concat(_descriptor_1.toValue(unit_0).concat(_descriptor_0.toValue(childAssetCommitment_0).concat(_descriptor_0.toValue(evidenceDigest_0)))),
            alignment: _descriptor_0.alignment().concat(_descriptor_1.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment())))
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._attestManufacture_0(context,
                                                   partialProofData,
                                                   nullifier_0,
                                                   unit_0,
                                                   childAssetCommitment_0,
                                                   evidenceDigest_0);
        partialProofData.output = { value: _descriptor_0.toValue(result_0), alignment: _descriptor_0.alignment() };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      },
      grantReplacementAllowance: (...args_1) => {
        if (args_1.length !== 5) {
          throw new __compactRuntime.CompactError(`grantReplacementAllowance: expected 5 arguments (as invoked from Typescript), received ${args_1.length}`);
        }
        const contextOrig_0 = args_1[0];
        const issuerId_0 = args_1[1];
        const failedNullifier_0 = args_1[2];
        const nonce_0 = args_1[3];
        const validUntil_0 = args_1[4];
        if (!(typeof(contextOrig_0) === 'object' && contextOrig_0.currentQueryContext != undefined)) {
          __compactRuntime.typeError('grantReplacementAllowance',
                                     'argument 1 (as invoked from Typescript)',
                                     'brandme_rights.compact line 552 char 1',
                                     'CircuitContext',
                                     contextOrig_0)
        }
        if (!(issuerId_0.buffer instanceof ArrayBuffer && issuerId_0.BYTES_PER_ELEMENT === 1 && issuerId_0.length === 32)) {
          __compactRuntime.typeError('grantReplacementAllowance',
                                     'argument 1 (argument 2 as invoked from Typescript)',
                                     'brandme_rights.compact line 552 char 1',
                                     'Bytes<32>',
                                     issuerId_0)
        }
        if (!(failedNullifier_0.buffer instanceof ArrayBuffer && failedNullifier_0.BYTES_PER_ELEMENT === 1 && failedNullifier_0.length === 32)) {
          __compactRuntime.typeError('grantReplacementAllowance',
                                     'argument 2 (argument 3 as invoked from Typescript)',
                                     'brandme_rights.compact line 552 char 1',
                                     'Bytes<32>',
                                     failedNullifier_0)
        }
        if (!(nonce_0.buffer instanceof ArrayBuffer && nonce_0.BYTES_PER_ELEMENT === 1 && nonce_0.length === 32)) {
          __compactRuntime.typeError('grantReplacementAllowance',
                                     'argument 3 (argument 4 as invoked from Typescript)',
                                     'brandme_rights.compact line 552 char 1',
                                     'Bytes<32>',
                                     nonce_0)
        }
        if (!(typeof(validUntil_0) === 'bigint' && validUntil_0 >= 0n && validUntil_0 <= 18446744073709551615n)) {
          __compactRuntime.typeError('grantReplacementAllowance',
                                     'argument 4 (argument 5 as invoked from Typescript)',
                                     'brandme_rights.compact line 552 char 1',
                                     'Uint<0..18446744073709551616>',
                                     validUntil_0)
        }
        const context = { ...contextOrig_0, gasCost: __compactRuntime.emptyRunningCost() };
        const partialProofData = {
          input: {
            value: _descriptor_0.toValue(issuerId_0).concat(_descriptor_0.toValue(failedNullifier_0).concat(_descriptor_0.toValue(nonce_0).concat(_descriptor_6.toValue(validUntil_0)))),
            alignment: _descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_0.alignment().concat(_descriptor_6.alignment())))
          },
          output: undefined,
          publicTranscript: [],
          privateTranscriptOutputs: []
        };
        const result_0 = this._grantReplacementAllowance_0(context,
                                                           partialProofData,
                                                           issuerId_0,
                                                           failedNullifier_0,
                                                           nonce_0,
                                                           validUntil_0);
        partialProofData.output = { value: _descriptor_0.toValue(result_0), alignment: _descriptor_0.alignment() };
        return { result: result_0, context: context, proofData: partialProofData, gasCost: context.gasCost };
      }
    };
    this.impureCircuits = {
      registerIssuer: this.circuits.registerIssuer,
      rotateIssuerKey: this.circuits.rotateIssuerKey,
      revokeIssuer: this.circuits.revokeIssuer,
      issueEntitlement: this.circuits.issueEntitlement,
      proveControl: this.circuits.proveControl,
      offerTransfer: this.circuits.offerTransfer,
      acceptTransfer: this.circuits.acceptTransfer,
      cancelTransfer: this.circuits.cancelTransfer,
      revokeEntitlement: this.circuits.revokeEntitlement,
      registerManufacturer: this.circuits.registerManufacturer,
      deactivateManufacturer: this.circuits.deactivateManufacturer,
      grantReprintAllowance: this.circuits.grantReprintAllowance,
      consumeReprintAllowance: this.circuits.consumeReprintAllowance,
      attestManufacture: this.circuits.attestManufacture,
      grantReplacementAllowance: this.circuits.grantReplacementAllowance
    };
    this.provableCircuits = {
      registerIssuer: this.circuits.registerIssuer,
      rotateIssuerKey: this.circuits.rotateIssuerKey,
      revokeIssuer: this.circuits.revokeIssuer,
      issueEntitlement: this.circuits.issueEntitlement,
      proveControl: this.circuits.proveControl,
      offerTransfer: this.circuits.offerTransfer,
      acceptTransfer: this.circuits.acceptTransfer,
      cancelTransfer: this.circuits.cancelTransfer,
      revokeEntitlement: this.circuits.revokeEntitlement,
      registerManufacturer: this.circuits.registerManufacturer,
      deactivateManufacturer: this.circuits.deactivateManufacturer,
      grantReprintAllowance: this.circuits.grantReprintAllowance,
      consumeReprintAllowance: this.circuits.consumeReprintAllowance,
      attestManufacture: this.circuits.attestManufacture,
      grantReplacementAllowance: this.circuits.grantReplacementAllowance
    };
  }
  initialState(...args_0) {
    if (args_0.length !== 4) {
      throw new __compactRuntime.CompactError(`Contract state constructor: expected 4 arguments (as invoked from Typescript), received ${args_0.length}`);
    }
    const constructorContext_0 = args_0[0];
    const salt_0 = args_0[1];
    const network_0 = args_0[2];
    const governance_0 = args_0[3];
    if (typeof(constructorContext_0) !== 'object') {
      throw new __compactRuntime.CompactError(`Contract state constructor: expected 'constructorContext' in argument 1 (as invoked from Typescript) to be an object`);
    }
    if (!('initialPrivateState' in constructorContext_0)) {
      throw new __compactRuntime.CompactError(`Contract state constructor: expected 'initialPrivateState' in argument 1 (as invoked from Typescript)`);
    }
    if (!('initialZswapLocalState' in constructorContext_0)) {
      throw new __compactRuntime.CompactError(`Contract state constructor: expected 'initialZswapLocalState' in argument 1 (as invoked from Typescript)`);
    }
    if (typeof(constructorContext_0.initialZswapLocalState) !== 'object') {
      throw new __compactRuntime.CompactError(`Contract state constructor: expected 'initialZswapLocalState' in argument 1 (as invoked from Typescript) to be an object`);
    }
    if (!(salt_0.buffer instanceof ArrayBuffer && salt_0.BYTES_PER_ELEMENT === 1 && salt_0.length === 32)) {
      __compactRuntime.typeError('Contract state constructor',
                                 'argument 1 (argument 2 as invoked from Typescript)',
                                 'brandme_rights.compact line 118 char 1',
                                 'Bytes<32>',
                                 salt_0)
    }
    if (!(network_0.buffer instanceof ArrayBuffer && network_0.BYTES_PER_ELEMENT === 1 && network_0.length === 32)) {
      __compactRuntime.typeError('Contract state constructor',
                                 'argument 2 (argument 3 as invoked from Typescript)',
                                 'brandme_rights.compact line 118 char 1',
                                 'Bytes<32>',
                                 network_0)
    }
    if (!(governance_0.buffer instanceof ArrayBuffer && governance_0.BYTES_PER_ELEMENT === 1 && governance_0.length === 32)) {
      __compactRuntime.typeError('Contract state constructor',
                                 'argument 3 (argument 4 as invoked from Typescript)',
                                 'brandme_rights.compact line 118 char 1',
                                 'Bytes<32>',
                                 governance_0)
    }
    const state_0 = new __compactRuntime.ContractState();
    let stateValue_0 = __compactRuntime.StateValue.newArray();
    stateValue_0 = stateValue_0.arrayPush(__compactRuntime.StateValue.newNull());
    stateValue_0 = stateValue_0.arrayPush(__compactRuntime.StateValue.newNull());
    stateValue_0 = stateValue_0.arrayPush(__compactRuntime.StateValue.newNull());
    stateValue_0 = stateValue_0.arrayPush(__compactRuntime.StateValue.newNull());
    stateValue_0 = stateValue_0.arrayPush(__compactRuntime.StateValue.newNull());
    stateValue_0 = stateValue_0.arrayPush(__compactRuntime.StateValue.newNull());
    stateValue_0 = stateValue_0.arrayPush(__compactRuntime.StateValue.newNull());
    stateValue_0 = stateValue_0.arrayPush(__compactRuntime.StateValue.newNull());
    stateValue_0 = stateValue_0.arrayPush(__compactRuntime.StateValue.newNull());
    stateValue_0 = stateValue_0.arrayPush(__compactRuntime.StateValue.newNull());
    stateValue_0 = stateValue_0.arrayPush(__compactRuntime.StateValue.newNull());
    state_0.data = new __compactRuntime.ChargedState(stateValue_0);
    state_0.setOperation('registerIssuer', new __compactRuntime.ContractOperation());
    state_0.setOperation('rotateIssuerKey', new __compactRuntime.ContractOperation());
    state_0.setOperation('revokeIssuer', new __compactRuntime.ContractOperation());
    state_0.setOperation('issueEntitlement', new __compactRuntime.ContractOperation());
    state_0.setOperation('proveControl', new __compactRuntime.ContractOperation());
    state_0.setOperation('offerTransfer', new __compactRuntime.ContractOperation());
    state_0.setOperation('acceptTransfer', new __compactRuntime.ContractOperation());
    state_0.setOperation('cancelTransfer', new __compactRuntime.ContractOperation());
    state_0.setOperation('revokeEntitlement', new __compactRuntime.ContractOperation());
    state_0.setOperation('registerManufacturer', new __compactRuntime.ContractOperation());
    state_0.setOperation('deactivateManufacturer', new __compactRuntime.ContractOperation());
    state_0.setOperation('grantReprintAllowance', new __compactRuntime.ContractOperation());
    state_0.setOperation('consumeReprintAllowance', new __compactRuntime.ContractOperation());
    state_0.setOperation('attestManufacture', new __compactRuntime.ContractOperation());
    state_0.setOperation('grantReplacementAllowance', new __compactRuntime.ContractOperation());
    const context = __compactRuntime.createCircuitContext(__compactRuntime.dummyContractAddress(), constructorContext_0.initialZswapLocalState.coinPublicKey, state_0.data, constructorContext_0.initialPrivateState);
    const partialProofData = {
      input: { value: [], alignment: [] },
      output: undefined,
      publicTranscript: [],
      privateTranscriptOutputs: []
    };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(0n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(new Uint8Array(32)),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(1n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(new Uint8Array(32)),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(2n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(new Uint8Array(32)),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(3n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newMap(
                                                          new __compactRuntime.StateMap()
                                                        ).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(4n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newMap(
                                                          new __compactRuntime.StateMap()
                                                        ).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(5n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newMap(
                                                          new __compactRuntime.StateMap()
                                                        ).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(6n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newMap(
                                                          new __compactRuntime.StateMap()
                                                        ).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(7n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newMap(
                                                          new __compactRuntime.StateMap()
                                                        ).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(8n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newMap(
                                                          new __compactRuntime.StateMap()
                                                        ).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(9n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newMap(
                                                          new __compactRuntime.StateMap()
                                                        ).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(10n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_6.toValue(0n),
                                                                                              alignment: _descriptor_6.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    __compactRuntime.assert(!this._equal_0(salt_0, new Uint8Array(32)),
                            'salt required');
    __compactRuntime.assert(!this._equal_1(network_0, new Uint8Array(32)),
                            'network required');
    __compactRuntime.assert(!this._equal_2(governance_0, new Uint8Array(32)),
                            'governance required');
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(0n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(salt_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(1n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(network_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_21.toValue(2n),
                                                                                              alignment: _descriptor_21.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(governance_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } }]);
    state_0.data = new __compactRuntime.ChargedState(context.currentQueryContext.state.state);
    return {
      currentContractState: state_0,
      currentPrivateState: context.currentPrivateState,
      currentZswapLocalState: context.currentZswapLocalState
    }
  }
  _blockTimeLt_0(context, partialProofData, time_0) {
    return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                     partialProofData,
                                                                     [
                                                                      { dup: { n: 2 } },
                                                                      { idx: { cached: true,
                                                                               pushPath: false,
                                                                               path: [
                                                                                      { tag: 'value',
                                                                                        value: { value: _descriptor_21.toValue(2n),
                                                                                                 alignment: _descriptor_21.alignment() } }] } },
                                                                      { push: { storage: false,
                                                                                value: __compactRuntime.StateValue.newCell({ value: _descriptor_6.toValue(time_0),
                                                                                                                             alignment: _descriptor_6.alignment() }).encode() } },
                                                                      'lt',
                                                                      { popeq: { cached: true,
                                                                                 result: undefined } }]).value);
  }
  _persistentHash_0(value_0) {
    const result_0 = __compactRuntime.persistentHash(_descriptor_16, value_0);
    return result_0;
  }
  _persistentHash_1(value_0) {
    const result_0 = __compactRuntime.persistentHash(_descriptor_17, value_0);
    return result_0;
  }
  _persistentHash_2(value_0) {
    const result_0 = __compactRuntime.persistentHash(_descriptor_14, value_0);
    return result_0;
  }
  _persistentHash_3(value_0) {
    const result_0 = __compactRuntime.persistentHash(_descriptor_15, value_0);
    return result_0;
  }
  _governanceSecret_0(context, partialProofData) {
    const witnessContext_0 = __compactRuntime.createWitnessContext(ledger(context.currentQueryContext.state), context.currentPrivateState, context.currentQueryContext.address);
    const [nextPrivateState_0, result_0] = this.witnesses.governanceSecret(witnessContext_0);
    context.currentPrivateState = nextPrivateState_0;
    if (!(result_0.buffer instanceof ArrayBuffer && result_0.BYTES_PER_ELEMENT === 1 && result_0.length === 32)) {
      __compactRuntime.typeError('governanceSecret',
                                 'return value',
                                 'brandme_rights.compact line 109 char 1',
                                 'Bytes<32>',
                                 result_0)
    }
    partialProofData.privateTranscriptOutputs.push({
      value: _descriptor_0.toValue(result_0),
      alignment: _descriptor_0.alignment()
    });
    return result_0;
  }
  _issuerSecret_0(context, partialProofData, issuerId_0) {
    const witnessContext_0 = __compactRuntime.createWitnessContext(ledger(context.currentQueryContext.state), context.currentPrivateState, context.currentQueryContext.address);
    const [nextPrivateState_0, result_0] = this.witnesses.issuerSecret(witnessContext_0,
                                                                       issuerId_0);
    context.currentPrivateState = nextPrivateState_0;
    if (!(result_0.buffer instanceof ArrayBuffer && result_0.BYTES_PER_ELEMENT === 1 && result_0.length === 32)) {
      __compactRuntime.typeError('issuerSecret',
                                 'return value',
                                 'brandme_rights.compact line 110 char 1',
                                 'Bytes<32>',
                                 result_0)
    }
    partialProofData.privateTranscriptOutputs.push({
      value: _descriptor_0.toValue(result_0),
      alignment: _descriptor_0.alignment()
    });
    return result_0;
  }
  _manufacturerSecret_0(context, partialProofData, manufacturerId_0) {
    const witnessContext_0 = __compactRuntime.createWitnessContext(ledger(context.currentQueryContext.state), context.currentPrivateState, context.currentQueryContext.address);
    const [nextPrivateState_0, result_0] = this.witnesses.manufacturerSecret(witnessContext_0,
                                                                             manufacturerId_0);
    context.currentPrivateState = nextPrivateState_0;
    if (!(result_0.buffer instanceof ArrayBuffer && result_0.BYTES_PER_ELEMENT === 1 && result_0.length === 32)) {
      __compactRuntime.typeError('manufacturerSecret',
                                 'return value',
                                 'brandme_rights.compact line 111 char 1',
                                 'Bytes<32>',
                                 result_0)
    }
    partialProofData.privateTranscriptOutputs.push({
      value: _descriptor_0.toValue(result_0),
      alignment: _descriptor_0.alignment()
    });
    return result_0;
  }
  _holderSecret_0(context, partialProofData, entitlementId_0) {
    const witnessContext_0 = __compactRuntime.createWitnessContext(ledger(context.currentQueryContext.state), context.currentPrivateState, context.currentQueryContext.address);
    const [nextPrivateState_0, result_0] = this.witnesses.holderSecret(witnessContext_0,
                                                                       entitlementId_0);
    context.currentPrivateState = nextPrivateState_0;
    if (!(result_0.buffer instanceof ArrayBuffer && result_0.BYTES_PER_ELEMENT === 1 && result_0.length === 32)) {
      __compactRuntime.typeError('holderSecret',
                                 'return value',
                                 'brandme_rights.compact line 114 char 1',
                                 'Bytes<32>',
                                 result_0)
    }
    partialProofData.privateTranscriptOutputs.push({
      value: _descriptor_0.toValue(result_0),
      alignment: _descriptor_0.alignment()
    });
    return result_0;
  }
  _roleCommitment_0(domain_0, scope_0, secret_0, salt_0, network_0) {
    return this._persistentHash_3([domain_0,
                                   salt_0,
                                   network_0,
                                   scope_0,
                                   secret_0]);
  }
  _holderCommitment_0(entitlementId_0, epoch_0, secret_0, salt_0, network_0) {
    return this._persistentHash_0([new Uint8Array([98, 114, 97, 110, 100, 109, 101, 58, 104, 111, 108, 100, 101, 114, 58, 118, 49, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
                                   salt_0,
                                   network_0,
                                   entitlementId_0,
                                   __compactRuntime.convertFieldToBytes(32,
                                                                        epoch_0,
                                                                        'brandme_rights.compact line 137 char 66'),
                                   secret_0]);
  }
  _deriveEntitlementId_0(issuerId_0, issuanceId_0) {
    return this._persistentHash_2([new Uint8Array([98, 114, 97, 110, 100, 109, 101, 58, 101, 110, 116, 105, 116, 108, 101, 109, 101, 110, 116, 58, 118, 49, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
                                   issuerId_0,
                                   issuanceId_0]);
  }
  _deriveChildEntitlementId_0(nullifier_0, unit_0) {
    return this._persistentHash_2([new Uint8Array([98, 114, 97, 110, 100, 109, 101, 58, 99, 104, 105, 108, 100, 58, 118, 49, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
                                   nullifier_0,
                                   __compactRuntime.convertFieldToBytes(32,
                                                                        unit_0,
                                                                        'brandme_rights.compact line 145 char 88')]);
  }
  _deriveOfferId_0(entitlementId_0, epoch_0, nonce_0) {
    return this._persistentHash_1([new Uint8Array([98, 114, 97, 110, 100, 109, 101, 58, 111, 102, 102, 101, 114, 58, 118, 49, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
                                   entitlementId_0,
                                   __compactRuntime.convertFieldToBytes(32,
                                                                        epoch_0,
                                                                        'brandme_rights.compact line 150 char 50'),
                                   nonce_0]);
  }
  _deriveAllowanceId_0(issuerId_0, nonce_0) {
    return this._persistentHash_2([new Uint8Array([98, 114, 97, 110, 100, 109, 101, 58, 97, 108, 108, 111, 119, 97, 110, 99, 101, 58, 118, 49, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
                                   issuerId_0,
                                   nonce_0]);
  }
  _deriveConsumptionNullifier_0(allowanceId_0, jobCommitment_0) {
    return this._persistentHash_2([new Uint8Array([98, 114, 97, 110, 100, 109, 101, 58, 114, 101, 112, 114, 105, 110, 116, 45, 110, 102, 58, 118, 49, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
                                   allowanceId_0,
                                   jobCommitment_0]);
  }
  _deriveChallengeKey_0(entitlementId_0, epoch_0, challenge_0, audience_0) {
    return this._persistentHash_3([new Uint8Array([98, 114, 97, 110, 100, 109, 101, 58, 99, 104, 97, 108, 108, 101, 110, 103, 101, 58, 118, 49, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
                                   entitlementId_0,
                                   __compactRuntime.convertFieldToBytes(32,
                                                                        epoch_0,
                                                                        'brandme_rights.compact line 164 char 54'),
                                   challenge_0,
                                   audience_0]);
  }
  _assertGovernance_0(context, partialProofData) {
    const c_0 = this._roleCommitment_0(new Uint8Array([98, 114, 97, 110, 100, 109, 101, 58, 103, 111, 118, 101, 114, 110, 97, 110, 99, 101, 58, 118, 49, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
                                       new Uint8Array(32),
                                       this._governanceSecret_0(context,
                                                                partialProofData),
                                       _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                                 partialProofData,
                                                                                                 [
                                                                                                  { dup: { n: 0 } },
                                                                                                  { idx: { cached: false,
                                                                                                           pushPath: false,
                                                                                                           path: [
                                                                                                                  { tag: 'value',
                                                                                                                    value: { value: _descriptor_21.toValue(0n),
                                                                                                                             alignment: _descriptor_21.alignment() } }] } },
                                                                                                  { popeq: { cached: false,
                                                                                                             result: undefined } }]).value),
                                       _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                                 partialProofData,
                                                                                                 [
                                                                                                  { dup: { n: 0 } },
                                                                                                  { idx: { cached: false,
                                                                                                           pushPath: false,
                                                                                                           path: [
                                                                                                                  { tag: 'value',
                                                                                                                    value: { value: _descriptor_21.toValue(1n),
                                                                                                                             alignment: _descriptor_21.alignment() } }] } },
                                                                                                  { popeq: { cached: false,
                                                                                                             result: undefined } }]).value));
    __compactRuntime.assert(this._equal_3(c_0,
                                          _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                                    partialProofData,
                                                                                                    [
                                                                                                     { dup: { n: 0 } },
                                                                                                     { idx: { cached: false,
                                                                                                              pushPath: false,
                                                                                                              path: [
                                                                                                                     { tag: 'value',
                                                                                                                       value: { value: _descriptor_21.toValue(2n),
                                                                                                                                alignment: _descriptor_21.alignment() } }] } },
                                                                                                     { popeq: { cached: false,
                                                                                                                result: undefined } }]).value)),
                            'not governance');
    return [];
  }
  _assertIssuer_0(context, partialProofData, issuerId_0) {
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(3n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(issuerId_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown issuer');
    const p_0 = _descriptor_13.fromValue(__compactRuntime.queryLedgerState(context,
                                                                           partialProofData,
                                                                           [
                                                                            { dup: { n: 0 } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_21.toValue(3n),
                                                                                                       alignment: _descriptor_21.alignment() } }] } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_0.toValue(issuerId_0),
                                                                                                       alignment: _descriptor_0.alignment() } }] } },
                                                                            { popeq: { cached: false,
                                                                                       result: undefined } }]).value);
    __compactRuntime.assert(p_0.active, 'issuer revoked');
    __compactRuntime.assert(this._blockTimeLt_0(context,
                                                partialProofData,
                                                p_0.validUntil),
                            'issuer authority expired');
    const c_0 = this._roleCommitment_0(new Uint8Array([98, 114, 97, 110, 100, 109, 101, 58, 105, 115, 115, 117, 101, 114, 58, 118, 49, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
                                       issuerId_0,
                                       this._issuerSecret_0(context,
                                                            partialProofData,
                                                            issuerId_0),
                                       _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                                 partialProofData,
                                                                                                 [
                                                                                                  { dup: { n: 0 } },
                                                                                                  { idx: { cached: false,
                                                                                                           pushPath: false,
                                                                                                           path: [
                                                                                                                  { tag: 'value',
                                                                                                                    value: { value: _descriptor_21.toValue(0n),
                                                                                                                             alignment: _descriptor_21.alignment() } }] } },
                                                                                                  { popeq: { cached: false,
                                                                                                             result: undefined } }]).value),
                                       _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                                 partialProofData,
                                                                                                 [
                                                                                                  { dup: { n: 0 } },
                                                                                                  { idx: { cached: false,
                                                                                                           pushPath: false,
                                                                                                           path: [
                                                                                                                  { tag: 'value',
                                                                                                                    value: { value: _descriptor_21.toValue(1n),
                                                                                                                             alignment: _descriptor_21.alignment() } }] } },
                                                                                                  { popeq: { cached: false,
                                                                                                             result: undefined } }]).value));
    __compactRuntime.assert(this._equal_4(c_0, p_0.authCommitment), 'not issuer');
    return p_0;
  }
  _assertManufacturer_0(context, partialProofData, manufacturerId_0) {
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(7n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(manufacturerId_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown manufacturer');
    const m_0 = _descriptor_10.fromValue(__compactRuntime.queryLedgerState(context,
                                                                           partialProofData,
                                                                           [
                                                                            { dup: { n: 0 } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_21.toValue(7n),
                                                                                                       alignment: _descriptor_21.alignment() } }] } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_0.toValue(manufacturerId_0),
                                                                                                       alignment: _descriptor_0.alignment() } }] } },
                                                                            { popeq: { cached: false,
                                                                                       result: undefined } }]).value);
    __compactRuntime.assert(m_0.active, 'manufacturer inactive');
    const c_0 = this._roleCommitment_0(new Uint8Array([98, 114, 97, 110, 100, 109, 101, 58, 109, 97, 110, 117, 102, 97, 99, 116, 117, 114, 101, 114, 58, 118, 49, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
                                       manufacturerId_0,
                                       this._manufacturerSecret_0(context,
                                                                  partialProofData,
                                                                  manufacturerId_0),
                                       _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                                 partialProofData,
                                                                                                 [
                                                                                                  { dup: { n: 0 } },
                                                                                                  { idx: { cached: false,
                                                                                                           pushPath: false,
                                                                                                           path: [
                                                                                                                  { tag: 'value',
                                                                                                                    value: { value: _descriptor_21.toValue(0n),
                                                                                                                             alignment: _descriptor_21.alignment() } }] } },
                                                                                                  { popeq: { cached: false,
                                                                                                             result: undefined } }]).value),
                                       _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                                 partialProofData,
                                                                                                 [
                                                                                                  { dup: { n: 0 } },
                                                                                                  { idx: { cached: false,
                                                                                                           pushPath: false,
                                                                                                           path: [
                                                                                                                  { tag: 'value',
                                                                                                                    value: { value: _descriptor_21.toValue(1n),
                                                                                                                             alignment: _descriptor_21.alignment() } }] } },
                                                                                                  { popeq: { cached: false,
                                                                                                             result: undefined } }]).value));
    __compactRuntime.assert(this._equal_5(c_0, m_0.authCommitment),
                            'not manufacturer');
    return m_0;
  }
  _assertController_0(context, partialProofData, entitlementId_0) {
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(4n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(entitlementId_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown entitlement');
    const e_0 = _descriptor_9.fromValue(__compactRuntime.queryLedgerState(context,
                                                                          partialProofData,
                                                                          [
                                                                           { dup: { n: 0 } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_21.toValue(4n),
                                                                                                      alignment: _descriptor_21.alignment() } }] } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_0.toValue(entitlementId_0),
                                                                                                      alignment: _descriptor_0.alignment() } }] } },
                                                                           { popeq: { cached: false,
                                                                                      result: undefined } }]).value);
    __compactRuntime.assert(e_0.status === 0, 'entitlement not active');
    const c_0 = this._holderCommitment_0(entitlementId_0,
                                         e_0.epoch,
                                         this._holderSecret_0(context,
                                                              partialProofData,
                                                              entitlementId_0),
                                         _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                                   partialProofData,
                                                                                                   [
                                                                                                    { dup: { n: 0 } },
                                                                                                    { idx: { cached: false,
                                                                                                             pushPath: false,
                                                                                                             path: [
                                                                                                                    { tag: 'value',
                                                                                                                      value: { value: _descriptor_21.toValue(0n),
                                                                                                                               alignment: _descriptor_21.alignment() } }] } },
                                                                                                    { popeq: { cached: false,
                                                                                                               result: undefined } }]).value),
                                         _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                                   partialProofData,
                                                                                                   [
                                                                                                    { dup: { n: 0 } },
                                                                                                    { idx: { cached: false,
                                                                                                             pushPath: false,
                                                                                                             path: [
                                                                                                                    { tag: 'value',
                                                                                                                      value: { value: _descriptor_21.toValue(1n),
                                                                                                                               alignment: _descriptor_21.alignment() } }] } },
                                                                                                    { popeq: { cached: false,
                                                                                                               result: undefined } }]).value));
    __compactRuntime.assert(this._equal_6(c_0, e_0.controllerCommitment),
                            'not controller');
    return e_0;
  }
  _registerIssuer_0(context,
                    partialProofData,
                    issuerId_0,
                    authCommitment_0,
                    policyVersion_0,
                    maxIssuance_0,
                    validUntil_0)
  {
    this._assertGovernance_0(context, partialProofData);
    const id_0 = issuerId_0;
    __compactRuntime.assert(!this._equal_7(id_0, new Uint8Array(32)),
                            'malformed issuer id');
    __compactRuntime.assert(!this._equal_8(authCommitment_0, new Uint8Array(32)),
                            'malformed issuer key');
    __compactRuntime.assert(!_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                       partialProofData,
                                                                                       [
                                                                                        { dup: { n: 0 } },
                                                                                        { idx: { cached: false,
                                                                                                 pushPath: false,
                                                                                                 path: [
                                                                                                        { tag: 'value',
                                                                                                          value: { value: _descriptor_21.toValue(3n),
                                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                                        { push: { storage: false,
                                                                                                  value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(id_0),
                                                                                                                                               alignment: _descriptor_0.alignment() }).encode() } },
                                                                                        'member',
                                                                                        { popeq: { cached: true,
                                                                                                   result: undefined } }]).value),
                            'issuer exists');
    let t_0;
    __compactRuntime.assert((t_0 = maxIssuance_0, t_0 > 0n), 'zero issuance cap');
    const tmp_0 = { authCommitment: authCommitment_0,
                    policyVersion: policyVersion_0,
                    maxIssuance: maxIssuance_0,
                    issued: 0n,
                    validUntil: validUntil_0,
                    active: true };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(3n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(id_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_13.toValue(tmp_0),
                                                                                              alignment: _descriptor_13.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_1 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_1),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return [];
  }
  _rotateIssuerKey_0(context,
                     partialProofData,
                     issuerId_0,
                     newAuthCommitment_0,
                     newPolicyVersion_0)
  {
    this._assertGovernance_0(context, partialProofData);
    const id_0 = issuerId_0;
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(3n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(id_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown issuer');
    const p_0 = _descriptor_13.fromValue(__compactRuntime.queryLedgerState(context,
                                                                           partialProofData,
                                                                           [
                                                                            { dup: { n: 0 } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_21.toValue(3n),
                                                                                                       alignment: _descriptor_21.alignment() } }] } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_0.toValue(id_0),
                                                                                                       alignment: _descriptor_0.alignment() } }] } },
                                                                            { popeq: { cached: false,
                                                                                       result: undefined } }]).value);
    __compactRuntime.assert(p_0.active, 'issuer revoked');
    __compactRuntime.assert(!this._equal_9(newAuthCommitment_0,
                                           new Uint8Array(32)),
                            'malformed issuer key');
    let t_0;
    __compactRuntime.assert((t_0 = newPolicyVersion_0, t_0 > p_0.policyVersion),
                            'policy version must increase');
    const tmp_0 = { authCommitment: newAuthCommitment_0,
                    policyVersion: newPolicyVersion_0,
                    maxIssuance: p_0.maxIssuance,
                    issued: p_0.issued,
                    validUntil: p_0.validUntil,
                    active: true };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(3n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(id_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_13.toValue(tmp_0),
                                                                                              alignment: _descriptor_13.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_1 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_1),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return [];
  }
  _revokeIssuer_0(context, partialProofData, issuerId_0) {
    this._assertGovernance_0(context, partialProofData);
    const id_0 = issuerId_0;
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(3n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(id_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown issuer');
    const p_0 = _descriptor_13.fromValue(__compactRuntime.queryLedgerState(context,
                                                                           partialProofData,
                                                                           [
                                                                            { dup: { n: 0 } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_21.toValue(3n),
                                                                                                       alignment: _descriptor_21.alignment() } }] } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_0.toValue(id_0),
                                                                                                       alignment: _descriptor_0.alignment() } }] } },
                                                                            { popeq: { cached: false,
                                                                                       result: undefined } }]).value);
    const tmp_0 = { authCommitment: p_0.authCommitment,
                    policyVersion: p_0.policyVersion,
                    maxIssuance: p_0.maxIssuance,
                    issued: p_0.issued,
                    validUntil: p_0.validUntil,
                    active: false };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(3n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(id_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_13.toValue(tmp_0),
                                                                                              alignment: _descriptor_13.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_1 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_1),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return [];
  }
  _issueEntitlement_0(context,
                      partialProofData,
                      issuerId_0,
                      issuanceId_0,
                      assetCommitment_0,
                      policyDigest_0,
                      transferable_0,
                      reprintable_0,
                      controllerCommitment_0)
  {
    const iid_0 = issuerId_0;
    const p_0 = this._assertIssuer_0(context, partialProofData, iid_0);
    let t_0;
    __compactRuntime.assert((t_0 = p_0.issued, t_0 < p_0.maxIssuance),
                            'issuance cap reached');
    __compactRuntime.assert(!this._equal_10(assetCommitment_0,
                                            new Uint8Array(32)),
                            'malformed asset commitment');
    __compactRuntime.assert(!this._equal_11(controllerCommitment_0,
                                            new Uint8Array(32)),
                            'malformed controller commitment');
    const eid_0 = this._deriveEntitlementId_0(iid_0, issuanceId_0);
    __compactRuntime.assert(!_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                       partialProofData,
                                                                                       [
                                                                                        { dup: { n: 0 } },
                                                                                        { idx: { cached: false,
                                                                                                 pushPath: false,
                                                                                                 path: [
                                                                                                        { tag: 'value',
                                                                                                          value: { value: _descriptor_21.toValue(4n),
                                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                                        { push: { storage: false,
                                                                                                  value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(eid_0),
                                                                                                                                               alignment: _descriptor_0.alignment() }).encode() } },
                                                                                        'member',
                                                                                        { popeq: { cached: true,
                                                                                                   result: undefined } }]).value),
                            'issuance id already used');
    const tmp_0 = { issuerId: iid_0,
                    assetCommitment: assetCommitment_0,
                    policyDigest: policyDigest_0,
                    controllerCommitment: controllerCommitment_0,
                    epoch: 1n,
                    transferable: transferable_0,
                    reprintable: reprintable_0,
                    parentConsumption: new Uint8Array(32),
                    status: 0 };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(4n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(eid_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_9.toValue(tmp_0),
                                                                                              alignment: _descriptor_9.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_1 = { authCommitment: p_0.authCommitment,
                    policyVersion: p_0.policyVersion,
                    maxIssuance: p_0.maxIssuance,
                    issued:
                      ((t1) => {
                        if (t1 > 4294967295n) {
                          throw new __compactRuntime.CompactError('brandme_rights.compact line 289 char 13: cast from Field or Uint value to smaller Uint value failed: ' + t1 + ' is greater than 4294967295');
                        }
                        return t1;
                      })(p_0.issued + 1n),
                    validUntil: p_0.validUntil,
                    active: p_0.active };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(3n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(iid_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_13.toValue(tmp_1),
                                                                                              alignment: _descriptor_13.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_2 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_2),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return eid_0;
  }
  _proveControl_0(context,
                  partialProofData,
                  entitlementId_0,
                  challenge_0,
                  audience_0)
  {
    const eid_0 = entitlementId_0;
    const e_0 = this._assertController_0(context, partialProofData, eid_0);
    const k_0 = this._deriveChallengeKey_0(eid_0,
                                           e_0.epoch,
                                           challenge_0,
                                           audience_0);
    __compactRuntime.assert(!_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                       partialProofData,
                                                                                       [
                                                                                        { dup: { n: 0 } },
                                                                                        { idx: { cached: false,
                                                                                                 pushPath: false,
                                                                                                 path: [
                                                                                                        { tag: 'value',
                                                                                                          value: { value: _descriptor_21.toValue(6n),
                                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                                        { push: { storage: false,
                                                                                                  value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(k_0),
                                                                                                                                               alignment: _descriptor_0.alignment() }).encode() } },
                                                                                        'member',
                                                                                        { popeq: { cached: true,
                                                                                                   result: undefined } }]).value),
                            'challenge already used');
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(6n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(k_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newNull().encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_0 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_0),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return [];
  }
  _offerTransfer_0(context,
                   partialProofData,
                   entitlementId_0,
                   nonce_0,
                   recipientCommitment_0,
                   expiry_0,
                   termsDigest_0)
  {
    const eid_0 = entitlementId_0;
    const e_0 = this._assertController_0(context, partialProofData, eid_0);
    __compactRuntime.assert(e_0.transferable, 'right is not transferable');
    __compactRuntime.assert(!this._equal_12(recipientCommitment_0,
                                            new Uint8Array(32)),
                            'malformed recipient commitment');
    __compactRuntime.assert(this._blockTimeLt_0(context,
                                                partialProofData,
                                                expiry_0),
                            'offer already expired');
    const oid_0 = this._deriveOfferId_0(eid_0, e_0.epoch, nonce_0);
    __compactRuntime.assert(!_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                       partialProofData,
                                                                                       [
                                                                                        { dup: { n: 0 } },
                                                                                        { idx: { cached: false,
                                                                                                 pushPath: false,
                                                                                                 path: [
                                                                                                        { tag: 'value',
                                                                                                          value: { value: _descriptor_21.toValue(5n),
                                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                                        { push: { storage: false,
                                                                                                  value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(oid_0),
                                                                                                                                               alignment: _descriptor_0.alignment() }).encode() } },
                                                                                        'member',
                                                                                        { popeq: { cached: true,
                                                                                                   result: undefined } }]).value),
                            'offer nonce already used');
    const tmp_0 = { entitlementId: eid_0,
                    senderEpoch: e_0.epoch,
                    recipientCommitment: recipientCommitment_0,
                    expiry: expiry_0,
                    termsDigest: termsDigest_0,
                    state: 0 };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(5n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(oid_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_12.toValue(tmp_0),
                                                                                              alignment: _descriptor_12.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_1 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_1),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return oid_0;
  }
  _acceptTransfer_0(context, partialProofData, offerId_0) {
    const oid_0 = offerId_0;
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(5n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(oid_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown offer');
    const o_0 = _descriptor_12.fromValue(__compactRuntime.queryLedgerState(context,
                                                                           partialProofData,
                                                                           [
                                                                            { dup: { n: 0 } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_21.toValue(5n),
                                                                                                       alignment: _descriptor_21.alignment() } }] } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_0.toValue(oid_0),
                                                                                                       alignment: _descriptor_0.alignment() } }] } },
                                                                            { popeq: { cached: false,
                                                                                       result: undefined } }]).value);
    __compactRuntime.assert(o_0.state === 0, 'offer not open');
    __compactRuntime.assert(this._blockTimeLt_0(context,
                                                partialProofData,
                                                o_0.expiry),
                            'offer expired');
    let tmp_0;
    __compactRuntime.assert((tmp_0 = o_0.entitlementId,
                             _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                       partialProofData,
                                                                                       [
                                                                                        { dup: { n: 0 } },
                                                                                        { idx: { cached: false,
                                                                                                 pushPath: false,
                                                                                                 path: [
                                                                                                        { tag: 'value',
                                                                                                          value: { value: _descriptor_21.toValue(4n),
                                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                                        { push: { storage: false,
                                                                                                  value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(tmp_0),
                                                                                                                                               alignment: _descriptor_0.alignment() }).encode() } },
                                                                                        'member',
                                                                                        { popeq: { cached: true,
                                                                                                   result: undefined } }]).value)),
                            'unknown entitlement');
    let tmp_1;
    const e_0 = (tmp_1 = o_0.entitlementId,
                 _descriptor_9.fromValue(__compactRuntime.queryLedgerState(context,
                                                                           partialProofData,
                                                                           [
                                                                            { dup: { n: 0 } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_21.toValue(4n),
                                                                                                       alignment: _descriptor_21.alignment() } }] } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_0.toValue(tmp_1),
                                                                                                       alignment: _descriptor_0.alignment() } }] } },
                                                                            { popeq: { cached: false,
                                                                                       result: undefined } }]).value));
    __compactRuntime.assert(e_0.status === 0, 'entitlement not active');
    __compactRuntime.assert(this._equal_13(e_0.epoch, o_0.senderEpoch),
                            'stale offer epoch');
    const nextEpoch_0 = ((t1) => {
                          if (t1 > 4294967295n) {
                            throw new __compactRuntime.CompactError('brandme_rights.compact line 344 char 21: cast from Field or Uint value to smaller Uint value failed: ' + t1 + ' is greater than 4294967295');
                          }
                          return t1;
                        })(e_0.epoch + 1n);
    const c_0 = this._holderCommitment_0(o_0.entitlementId,
                                         nextEpoch_0,
                                         this._holderSecret_0(context,
                                                              partialProofData,
                                                              o_0.entitlementId),
                                         _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                                   partialProofData,
                                                                                                   [
                                                                                                    { dup: { n: 0 } },
                                                                                                    { idx: { cached: false,
                                                                                                             pushPath: false,
                                                                                                             path: [
                                                                                                                    { tag: 'value',
                                                                                                                      value: { value: _descriptor_21.toValue(0n),
                                                                                                                               alignment: _descriptor_21.alignment() } }] } },
                                                                                                    { popeq: { cached: false,
                                                                                                               result: undefined } }]).value),
                                         _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                                   partialProofData,
                                                                                                   [
                                                                                                    { dup: { n: 0 } },
                                                                                                    { idx: { cached: false,
                                                                                                             pushPath: false,
                                                                                                             path: [
                                                                                                                    { tag: 'value',
                                                                                                                      value: { value: _descriptor_21.toValue(1n),
                                                                                                                               alignment: _descriptor_21.alignment() } }] } },
                                                                                                    { popeq: { cached: false,
                                                                                                               result: undefined } }]).value));
    __compactRuntime.assert(this._equal_14(c_0, o_0.recipientCommitment),
                            'not the offered recipient');
    const tmp_2 = o_0.entitlementId;
    const tmp_3 = { issuerId: e_0.issuerId,
                    assetCommitment: e_0.assetCommitment,
                    policyDigest: e_0.policyDigest,
                    controllerCommitment: o_0.recipientCommitment,
                    epoch: nextEpoch_0,
                    transferable: e_0.transferable,
                    reprintable: e_0.reprintable,
                    parentConsumption: e_0.parentConsumption,
                    status: e_0.status };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(4n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(tmp_2),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_9.toValue(tmp_3),
                                                                                              alignment: _descriptor_9.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_4 = { entitlementId: o_0.entitlementId,
                    senderEpoch: o_0.senderEpoch,
                    recipientCommitment: o_0.recipientCommitment,
                    expiry: o_0.expiry,
                    termsDigest: o_0.termsDigest,
                    state: 1 };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(5n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(oid_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_12.toValue(tmp_4),
                                                                                              alignment: _descriptor_12.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_5 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_5),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return [];
  }
  _cancelTransfer_0(context, partialProofData, offerId_0) {
    const oid_0 = offerId_0;
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(5n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(oid_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown offer');
    const o_0 = _descriptor_12.fromValue(__compactRuntime.queryLedgerState(context,
                                                                           partialProofData,
                                                                           [
                                                                            { dup: { n: 0 } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_21.toValue(5n),
                                                                                                       alignment: _descriptor_21.alignment() } }] } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_0.toValue(oid_0),
                                                                                                       alignment: _descriptor_0.alignment() } }] } },
                                                                            { popeq: { cached: false,
                                                                                       result: undefined } }]).value);
    __compactRuntime.assert(o_0.state === 0, 'offer not open');
    const e_0 = this._assertController_0(context,
                                         partialProofData,
                                         o_0.entitlementId);
    __compactRuntime.assert(this._equal_15(e_0.epoch, o_0.senderEpoch),
                            'stale offer epoch');
    const tmp_0 = { entitlementId: o_0.entitlementId,
                    senderEpoch: o_0.senderEpoch,
                    recipientCommitment: o_0.recipientCommitment,
                    expiry: o_0.expiry,
                    termsDigest: o_0.termsDigest,
                    state: 2 };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(5n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(oid_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_12.toValue(tmp_0),
                                                                                              alignment: _descriptor_12.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_1 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_1),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return [];
  }
  _revokeEntitlement_0(context, partialProofData, entitlementId_0) {
    this._assertGovernance_0(context, partialProofData);
    const eid_0 = entitlementId_0;
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(4n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(eid_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown entitlement');
    const e_0 = _descriptor_9.fromValue(__compactRuntime.queryLedgerState(context,
                                                                          partialProofData,
                                                                          [
                                                                           { dup: { n: 0 } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_21.toValue(4n),
                                                                                                      alignment: _descriptor_21.alignment() } }] } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_0.toValue(eid_0),
                                                                                                      alignment: _descriptor_0.alignment() } }] } },
                                                                           { popeq: { cached: false,
                                                                                      result: undefined } }]).value);
    const tmp_0 = { issuerId: e_0.issuerId,
                    assetCommitment: e_0.assetCommitment,
                    policyDigest: e_0.policyDigest,
                    controllerCommitment: e_0.controllerCommitment,
                    epoch: e_0.epoch,
                    transferable: e_0.transferable,
                    reprintable: e_0.reprintable,
                    parentConsumption: e_0.parentConsumption,
                    status: 1 };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(4n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(eid_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_9.toValue(tmp_0),
                                                                                              alignment: _descriptor_9.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_1 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_1),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return [];
  }
  _registerManufacturer_0(context,
                          partialProofData,
                          issuerId_0,
                          manufacturerId_0,
                          authCommitment_0)
  {
    const iid_0 = issuerId_0;
    this._assertIssuer_0(context, partialProofData, iid_0);
    const mid_0 = manufacturerId_0;
    __compactRuntime.assert(!this._equal_16(mid_0, new Uint8Array(32)),
                            'malformed manufacturer id');
    __compactRuntime.assert(!this._equal_17(authCommitment_0, new Uint8Array(32)),
                            'malformed manufacturer key');
    __compactRuntime.assert(!_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                       partialProofData,
                                                                                       [
                                                                                        { dup: { n: 0 } },
                                                                                        { idx: { cached: false,
                                                                                                 pushPath: false,
                                                                                                 path: [
                                                                                                        { tag: 'value',
                                                                                                          value: { value: _descriptor_21.toValue(7n),
                                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                                        { push: { storage: false,
                                                                                                  value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(mid_0),
                                                                                                                                               alignment: _descriptor_0.alignment() }).encode() } },
                                                                                        'member',
                                                                                        { popeq: { cached: true,
                                                                                                   result: undefined } }]).value),
                            'manufacturer exists');
    const tmp_0 = { issuerId: iid_0,
                    authCommitment: authCommitment_0,
                    active: true };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(7n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(mid_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_10.toValue(tmp_0),
                                                                                              alignment: _descriptor_10.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_1 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_1),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return [];
  }
  _deactivateManufacturer_0(context,
                            partialProofData,
                            issuerId_0,
                            manufacturerId_0)
  {
    const iid_0 = issuerId_0;
    this._assertIssuer_0(context, partialProofData, iid_0);
    const mid_0 = manufacturerId_0;
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(7n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(mid_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown manufacturer');
    const m_0 = _descriptor_10.fromValue(__compactRuntime.queryLedgerState(context,
                                                                           partialProofData,
                                                                           [
                                                                            { dup: { n: 0 } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_21.toValue(7n),
                                                                                                       alignment: _descriptor_21.alignment() } }] } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_0.toValue(mid_0),
                                                                                                       alignment: _descriptor_0.alignment() } }] } },
                                                                            { popeq: { cached: false,
                                                                                       result: undefined } }]).value);
    __compactRuntime.assert(this._equal_18(m_0.issuerId, iid_0),
                            'manufacturer belongs to another issuer');
    const tmp_0 = { issuerId: m_0.issuerId,
                    authCommitment: m_0.authCommitment,
                    active: false };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(7n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(mid_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_10.toValue(tmp_0),
                                                                                              alignment: _descriptor_10.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_1 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_1),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return [];
  }
  _grantReprintAllowance_0(context,
                           partialProofData,
                           issuerId_0,
                           nonce_0,
                           entitlementId_0,
                           designDigest_0,
                           manufacturerId_0,
                           quota_0,
                           validUntil_0,
                           policyDigest_0)
  {
    const iid_0 = issuerId_0;
    this._assertIssuer_0(context, partialProofData, iid_0);
    const eid_0 = entitlementId_0;
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(4n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(eid_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown entitlement');
    const e_0 = _descriptor_9.fromValue(__compactRuntime.queryLedgerState(context,
                                                                          partialProofData,
                                                                          [
                                                                           { dup: { n: 0 } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_21.toValue(4n),
                                                                                                      alignment: _descriptor_21.alignment() } }] } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_0.toValue(eid_0),
                                                                                                      alignment: _descriptor_0.alignment() } }] } },
                                                                           { popeq: { cached: false,
                                                                                      result: undefined } }]).value);
    __compactRuntime.assert(e_0.status === 0, 'entitlement not active');
    __compactRuntime.assert(e_0.reprintable,
                            'entitlement carries no reproduction right');
    __compactRuntime.assert(this._equal_19(e_0.issuerId, iid_0),
                            'entitlement issued by another issuer');
    const mid_0 = manufacturerId_0;
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(7n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(mid_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown manufacturer');
    const m_0 = _descriptor_10.fromValue(__compactRuntime.queryLedgerState(context,
                                                                           partialProofData,
                                                                           [
                                                                            { dup: { n: 0 } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_21.toValue(7n),
                                                                                                       alignment: _descriptor_21.alignment() } }] } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_0.toValue(mid_0),
                                                                                                       alignment: _descriptor_0.alignment() } }] } },
                                                                            { popeq: { cached: false,
                                                                                       result: undefined } }]).value);
    __compactRuntime.assert(m_0.active, 'manufacturer inactive');
    __compactRuntime.assert(this._equal_20(m_0.issuerId, iid_0),
                            'manufacturer not authorized by issuer');
    let t_0; __compactRuntime.assert((t_0 = quota_0, t_0 > 0n), 'zero quota');
    __compactRuntime.assert(!this._equal_21(designDigest_0, new Uint8Array(32)),
                            'malformed design digest');
    const aid_0 = this._deriveAllowanceId_0(iid_0, nonce_0);
    __compactRuntime.assert(!_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                       partialProofData,
                                                                                       [
                                                                                        { dup: { n: 0 } },
                                                                                        { idx: { cached: false,
                                                                                                 pushPath: false,
                                                                                                 path: [
                                                                                                        { tag: 'value',
                                                                                                          value: { value: _descriptor_21.toValue(8n),
                                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                                        { push: { storage: false,
                                                                                                  value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(aid_0),
                                                                                                                                               alignment: _descriptor_0.alignment() }).encode() } },
                                                                                        'member',
                                                                                        { popeq: { cached: true,
                                                                                                   result: undefined } }]).value),
                            'allowance nonce already used');
    const tmp_0 = { issuerId: iid_0,
                    entitlementId: eid_0,
                    designDigest: designDigest_0,
                    manufacturerId: mid_0,
                    remaining: quota_0,
                    validUntil: validUntil_0,
                    policyDigest: policyDigest_0 };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(8n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(aid_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_7.toValue(tmp_0),
                                                                                              alignment: _descriptor_7.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_1 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_1),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return aid_0;
  }
  _consumeReprintAllowance_0(context,
                             partialProofData,
                             allowanceId_0,
                             jobCommitment_0,
                             quantity_0,
                             childControllerCommitment_0)
  {
    const aid_0 = allowanceId_0;
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(8n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(aid_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown allowance');
    const a_0 = _descriptor_7.fromValue(__compactRuntime.queryLedgerState(context,
                                                                          partialProofData,
                                                                          [
                                                                           { dup: { n: 0 } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_21.toValue(8n),
                                                                                                      alignment: _descriptor_21.alignment() } }] } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_0.toValue(aid_0),
                                                                                                      alignment: _descriptor_0.alignment() } }] } },
                                                                           { popeq: { cached: false,
                                                                                      result: undefined } }]).value);
    __compactRuntime.assert(this._blockTimeLt_0(context,
                                                partialProofData,
                                                a_0.validUntil),
                            'allowance expired');
    this._assertController_0(context, partialProofData, a_0.entitlementId);
    __compactRuntime.assert(!this._equal_22(jobCommitment_0, new Uint8Array(32)),
                            'malformed job commitment');
    const nf_0 = this._deriveConsumptionNullifier_0(aid_0, jobCommitment_0);
    __compactRuntime.assert(!_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                       partialProofData,
                                                                                       [
                                                                                        { dup: { n: 0 } },
                                                                                        { idx: { cached: false,
                                                                                                 pushPath: false,
                                                                                                 path: [
                                                                                                        { tag: 'value',
                                                                                                          value: { value: _descriptor_21.toValue(9n),
                                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                                        { push: { storage: false,
                                                                                                  value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(nf_0),
                                                                                                                                               alignment: _descriptor_0.alignment() }).encode() } },
                                                                                        'member',
                                                                                        { popeq: { cached: true,
                                                                                                   result: undefined } }]).value),
                            'job already consumed');
    const q_0 = quantity_0;
    __compactRuntime.assert(q_0 > 0n, 'quantity must be positive');
    __compactRuntime.assert(q_0 <= a_0.remaining, 'quota exceeded');
    __compactRuntime.assert(!this._equal_23(childControllerCommitment_0,
                                            new Uint8Array(32)),
                            'malformed child controller');
    let t_0;
    const tmp_0 = { issuerId: a_0.issuerId,
                    entitlementId: a_0.entitlementId,
                    designDigest: a_0.designDigest,
                    manufacturerId: a_0.manufacturerId,
                    remaining:
                      (t_0 = a_0.remaining,
                       (__compactRuntime.assert(t_0 >= q_0,
                                                'result of subtraction would be negative'),
                        t_0 - q_0)),
                    validUntil: a_0.validUntil,
                    policyDigest: a_0.policyDigest };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(8n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(aid_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_7.toValue(tmp_0),
                                                                                              alignment: _descriptor_7.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_1 = { allowanceId: aid_0,
                    jobCommitment: jobCommitment_0,
                    quantity: q_0,
                    attested: 0n,
                    childControllerCommitment: childControllerCommitment_0,
                    state: 0,
                    replacedBy: new Uint8Array(32) };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(9n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(nf_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_3.toValue(tmp_1),
                                                                                              alignment: _descriptor_3.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_2 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_2),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return nf_0;
  }
  _attestManufacture_0(context,
                       partialProofData,
                       nullifier_0,
                       unit_0,
                       childAssetCommitment_0,
                       evidenceDigest_0)
  {
    const nf_0 = nullifier_0;
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(9n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(nf_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown consumption');
    const r_0 = _descriptor_3.fromValue(__compactRuntime.queryLedgerState(context,
                                                                          partialProofData,
                                                                          [
                                                                           { dup: { n: 0 } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_21.toValue(9n),
                                                                                                      alignment: _descriptor_21.alignment() } }] } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_0.toValue(nf_0),
                                                                                                      alignment: _descriptor_0.alignment() } }] } },
                                                                           { popeq: { cached: false,
                                                                                      result: undefined } }]).value);
    __compactRuntime.assert(r_0.state === 0, 'consumption cancelled');
    let tmp_0;
    const a_0 = (tmp_0 = r_0.allowanceId,
                 _descriptor_7.fromValue(__compactRuntime.queryLedgerState(context,
                                                                           partialProofData,
                                                                           [
                                                                            { dup: { n: 0 } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_21.toValue(8n),
                                                                                                       alignment: _descriptor_21.alignment() } }] } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_0.toValue(tmp_0),
                                                                                                       alignment: _descriptor_0.alignment() } }] } },
                                                                            { popeq: { cached: false,
                                                                                       result: undefined } }]).value));
    this._assertManufacturer_0(context, partialProofData, a_0.manufacturerId);
    const u_0 = unit_0;
    __compactRuntime.assert(this._equal_24(u_0, r_0.attested),
                            'units must be attested in order');
    __compactRuntime.assert(u_0 < r_0.quantity, 'all units already attested');
    __compactRuntime.assert(!this._equal_25(childAssetCommitment_0,
                                            new Uint8Array(32)),
                            'malformed child asset');
    __compactRuntime.assert(!this._equal_26(evidenceDigest_0, new Uint8Array(32)),
                            'missing production evidence');
    const cid_0 = this._deriveChildEntitlementId_0(nf_0, u_0);
    __compactRuntime.assert(!_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                       partialProofData,
                                                                                       [
                                                                                        { dup: { n: 0 } },
                                                                                        { idx: { cached: false,
                                                                                                 pushPath: false,
                                                                                                 path: [
                                                                                                        { tag: 'value',
                                                                                                          value: { value: _descriptor_21.toValue(4n),
                                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                                        { push: { storage: false,
                                                                                                  value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(cid_0),
                                                                                                                                               alignment: _descriptor_0.alignment() }).encode() } },
                                                                                        'member',
                                                                                        { popeq: { cached: true,
                                                                                                   result: undefined } }]).value),
                            'child already issued');
    let tmp_1;
    const parent_0 = (tmp_1 = a_0.entitlementId,
                      _descriptor_9.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                partialProofData,
                                                                                [
                                                                                 { dup: { n: 0 } },
                                                                                 { idx: { cached: false,
                                                                                          pushPath: false,
                                                                                          path: [
                                                                                                 { tag: 'value',
                                                                                                   value: { value: _descriptor_21.toValue(4n),
                                                                                                            alignment: _descriptor_21.alignment() } }] } },
                                                                                 { idx: { cached: false,
                                                                                          pushPath: false,
                                                                                          path: [
                                                                                                 { tag: 'value',
                                                                                                   value: { value: _descriptor_0.toValue(tmp_1),
                                                                                                            alignment: _descriptor_0.alignment() } }] } },
                                                                                 { popeq: { cached: false,
                                                                                            result: undefined } }]).value));
    const tmp_2 = { issuerId: a_0.issuerId,
                    assetCommitment: childAssetCommitment_0,
                    policyDigest: evidenceDigest_0,
                    controllerCommitment: r_0.childControllerCommitment,
                    epoch: 1n,
                    transferable: parent_0.transferable,
                    reprintable: false,
                    parentConsumption: nf_0,
                    status: 0 };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(4n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(cid_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_9.toValue(tmp_2),
                                                                                              alignment: _descriptor_9.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_3 = { allowanceId: r_0.allowanceId,
                    jobCommitment: r_0.jobCommitment,
                    quantity: r_0.quantity,
                    attested:
                      ((t1) => {
                        if (t1 > 4294967295n) {
                          throw new __compactRuntime.CompactError('brandme_rights.compact line 539 char 15: cast from Field or Uint value to smaller Uint value failed: ' + t1 + ' is greater than 4294967295');
                        }
                        return t1;
                      })(r_0.attested + 1n),
                    childControllerCommitment: r_0.childControllerCommitment,
                    state: r_0.state,
                    replacedBy: r_0.replacedBy };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(9n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(nf_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_3.toValue(tmp_3),
                                                                                              alignment: _descriptor_3.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_4 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_4),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return cid_0;
  }
  _grantReplacementAllowance_0(context,
                               partialProofData,
                               issuerId_0,
                               failedNullifier_0,
                               nonce_0,
                               validUntil_0)
  {
    const iid_0 = issuerId_0;
    this._assertIssuer_0(context, partialProofData, iid_0);
    const nf_0 = failedNullifier_0;
    __compactRuntime.assert(_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                      partialProofData,
                                                                                      [
                                                                                       { dup: { n: 0 } },
                                                                                       { idx: { cached: false,
                                                                                                pushPath: false,
                                                                                                path: [
                                                                                                       { tag: 'value',
                                                                                                         value: { value: _descriptor_21.toValue(9n),
                                                                                                                  alignment: _descriptor_21.alignment() } }] } },
                                                                                       { push: { storage: false,
                                                                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(nf_0),
                                                                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                                                                       'member',
                                                                                       { popeq: { cached: true,
                                                                                                  result: undefined } }]).value),
                            'unknown consumption');
    const r_0 = _descriptor_3.fromValue(__compactRuntime.queryLedgerState(context,
                                                                          partialProofData,
                                                                          [
                                                                           { dup: { n: 0 } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_21.toValue(9n),
                                                                                                      alignment: _descriptor_21.alignment() } }] } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_0.toValue(nf_0),
                                                                                                      alignment: _descriptor_0.alignment() } }] } },
                                                                           { popeq: { cached: false,
                                                                                      result: undefined } }]).value);
    __compactRuntime.assert(r_0.state === 0, 'already cancelled or replaced');
    let t_0;
    __compactRuntime.assert((t_0 = r_0.attested, t_0 < r_0.quantity),
                            'job fully attested; nothing to replace');
    let tmp_0;
    const a_0 = (tmp_0 = r_0.allowanceId,
                 _descriptor_7.fromValue(__compactRuntime.queryLedgerState(context,
                                                                           partialProofData,
                                                                           [
                                                                            { dup: { n: 0 } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_21.toValue(8n),
                                                                                                       alignment: _descriptor_21.alignment() } }] } },
                                                                            { idx: { cached: false,
                                                                                     pushPath: false,
                                                                                     path: [
                                                                                            { tag: 'value',
                                                                                              value: { value: _descriptor_0.toValue(tmp_0),
                                                                                                       alignment: _descriptor_0.alignment() } }] } },
                                                                            { popeq: { cached: false,
                                                                                       result: undefined } }]).value));
    __compactRuntime.assert(this._equal_27(a_0.issuerId, iid_0),
                            'allowance granted by another issuer');
    const aid_0 = this._deriveAllowanceId_0(iid_0, nonce_0);
    __compactRuntime.assert(!_descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                                       partialProofData,
                                                                                       [
                                                                                        { dup: { n: 0 } },
                                                                                        { idx: { cached: false,
                                                                                                 pushPath: false,
                                                                                                 path: [
                                                                                                        { tag: 'value',
                                                                                                          value: { value: _descriptor_21.toValue(8n),
                                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                                        { push: { storage: false,
                                                                                                  value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(aid_0),
                                                                                                                                               alignment: _descriptor_0.alignment() }).encode() } },
                                                                                        'member',
                                                                                        { popeq: { cached: true,
                                                                                                   result: undefined } }]).value),
                            'allowance nonce already used');
    let t_1, t_2;
    const tmp_1 = { issuerId: iid_0,
                    entitlementId: a_0.entitlementId,
                    designDigest: a_0.designDigest,
                    manufacturerId: a_0.manufacturerId,
                    remaining:
                      (t_1 = r_0.quantity,
                       (t_2 = r_0.attested,
                        (__compactRuntime.assert(t_1 >= t_2,
                                                 'result of subtraction would be negative'),
                         t_1 - t_2))),
                    validUntil: validUntil_0,
                    policyDigest: a_0.policyDigest };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(8n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(aid_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_7.toValue(tmp_1),
                                                                                              alignment: _descriptor_7.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_2 = { allowanceId: r_0.allowanceId,
                    jobCommitment: r_0.jobCommitment,
                    quantity: r_0.quantity,
                    attested: r_0.attested,
                    childControllerCommitment: r_0.childControllerCommitment,
                    state: 1,
                    replacedBy: aid_0 };
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(9n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { push: { storage: false,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(nf_0),
                                                                                              alignment: _descriptor_0.alignment() }).encode() } },
                                       { push: { storage: true,
                                                 value: __compactRuntime.StateValue.newCell({ value: _descriptor_3.toValue(tmp_2),
                                                                                              alignment: _descriptor_3.alignment() }).encode() } },
                                       { ins: { cached: false, n: 1 } },
                                       { ins: { cached: true, n: 1 } }]);
    const tmp_3 = 1n;
    __compactRuntime.queryLedgerState(context,
                                      partialProofData,
                                      [
                                       { idx: { cached: false,
                                                pushPath: true,
                                                path: [
                                                       { tag: 'value',
                                                         value: { value: _descriptor_21.toValue(10n),
                                                                  alignment: _descriptor_21.alignment() } }] } },
                                       { addi: { immediate: parseInt(__compactRuntime.valueToBigInt(
                                                              { value: _descriptor_5.toValue(tmp_3),
                                                                alignment: _descriptor_5.alignment() }
                                                                .value
                                                            )) } },
                                       { ins: { cached: true, n: 1 } }]);
    return aid_0;
  }
  _equal_0(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_1(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_2(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_3(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_4(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_5(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_6(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_7(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_8(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_9(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_10(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_11(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_12(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_13(x0, y0) {
    if (x0 !== y0) { return false; }
    return true;
  }
  _equal_14(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_15(x0, y0) {
    if (x0 !== y0) { return false; }
    return true;
  }
  _equal_16(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_17(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_18(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_19(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_20(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_21(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_22(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_23(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_24(x0, y0) {
    if (x0 !== y0) { return false; }
    return true;
  }
  _equal_25(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_26(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
  _equal_27(x0, y0) {
    if (!x0.every((x, i) => y0[i] === x)) { return false; }
    return true;
  }
}
export function ledger(stateOrChargedState) {
  const state = stateOrChargedState instanceof __compactRuntime.StateValue ? stateOrChargedState : stateOrChargedState.state;
  const chargedState = stateOrChargedState instanceof __compactRuntime.StateValue ? new __compactRuntime.ChargedState(stateOrChargedState) : stateOrChargedState;
  const context = {
    currentQueryContext: new __compactRuntime.QueryContext(chargedState, __compactRuntime.dummyContractAddress()),
    costModel: __compactRuntime.CostModel.initialCostModel()
  };
  const partialProofData = {
    input: { value: [], alignment: [] },
    output: undefined,
    publicTranscript: [],
    privateTranscriptOutputs: []
  };
  return {
    get instanceSalt() {
      return _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                       partialProofData,
                                                                       [
                                                                        { dup: { n: 0 } },
                                                                        { idx: { cached: false,
                                                                                 pushPath: false,
                                                                                 path: [
                                                                                        { tag: 'value',
                                                                                          value: { value: _descriptor_21.toValue(0n),
                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                        { popeq: { cached: false,
                                                                                   result: undefined } }]).value);
    },
    get networkTag() {
      return _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                       partialProofData,
                                                                       [
                                                                        { dup: { n: 0 } },
                                                                        { idx: { cached: false,
                                                                                 pushPath: false,
                                                                                 path: [
                                                                                        { tag: 'value',
                                                                                          value: { value: _descriptor_21.toValue(1n),
                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                        { popeq: { cached: false,
                                                                                   result: undefined } }]).value);
    },
    get governanceCommitment() {
      return _descriptor_0.fromValue(__compactRuntime.queryLedgerState(context,
                                                                       partialProofData,
                                                                       [
                                                                        { dup: { n: 0 } },
                                                                        { idx: { cached: false,
                                                                                 pushPath: false,
                                                                                 path: [
                                                                                        { tag: 'value',
                                                                                          value: { value: _descriptor_21.toValue(2n),
                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                        { popeq: { cached: false,
                                                                                   result: undefined } }]).value);
    },
    issuers: {
      isEmpty(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`isEmpty: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(3n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_6.toValue(0n),
                                                                                                                                 alignment: _descriptor_6.alignment() }).encode() } },
                                                                          'eq',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      size(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`size: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_6.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(3n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      member(...args_0) {
        if (args_0.length !== 1) {
          throw new __compactRuntime.CompactError(`member: expected 1 argument, received ${args_0.length}`);
        }
        const key_0 = args_0[0];
        if (!(key_0.buffer instanceof ArrayBuffer && key_0.BYTES_PER_ELEMENT === 1 && key_0.length === 32)) {
          __compactRuntime.typeError('member',
                                     'argument 1',
                                     'brandme_rights.compact line 97 char 1',
                                     'Bytes<32>',
                                     key_0)
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(3n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(key_0),
                                                                                                                                 alignment: _descriptor_0.alignment() }).encode() } },
                                                                          'member',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      lookup(...args_0) {
        if (args_0.length !== 1) {
          throw new __compactRuntime.CompactError(`lookup: expected 1 argument, received ${args_0.length}`);
        }
        const key_0 = args_0[0];
        if (!(key_0.buffer instanceof ArrayBuffer && key_0.BYTES_PER_ELEMENT === 1 && key_0.length === 32)) {
          __compactRuntime.typeError('lookup',
                                     'argument 1',
                                     'brandme_rights.compact line 97 char 1',
                                     'Bytes<32>',
                                     key_0)
        }
        return _descriptor_13.fromValue(__compactRuntime.queryLedgerState(context,
                                                                          partialProofData,
                                                                          [
                                                                           { dup: { n: 0 } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_21.toValue(3n),
                                                                                                      alignment: _descriptor_21.alignment() } }] } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_0.toValue(key_0),
                                                                                                      alignment: _descriptor_0.alignment() } }] } },
                                                                           { popeq: { cached: false,
                                                                                      result: undefined } }]).value);
      },
      [Symbol.iterator](...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`iter: expected 0 arguments, received ${args_0.length}`);
        }
        const self_0 = state.asArray()[3];
        return self_0.asMap().keys().map(  (key) => {    const value = self_0.asMap().get(key).asCell();    return [      _descriptor_0.fromValue(key.value),      _descriptor_13.fromValue(value.value)    ];  })[Symbol.iterator]();
      }
    },
    entitlements: {
      isEmpty(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`isEmpty: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(4n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_6.toValue(0n),
                                                                                                                                 alignment: _descriptor_6.alignment() }).encode() } },
                                                                          'eq',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      size(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`size: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_6.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(4n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      member(...args_0) {
        if (args_0.length !== 1) {
          throw new __compactRuntime.CompactError(`member: expected 1 argument, received ${args_0.length}`);
        }
        const key_0 = args_0[0];
        if (!(key_0.buffer instanceof ArrayBuffer && key_0.BYTES_PER_ELEMENT === 1 && key_0.length === 32)) {
          __compactRuntime.typeError('member',
                                     'argument 1',
                                     'brandme_rights.compact line 98 char 1',
                                     'Bytes<32>',
                                     key_0)
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(4n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(key_0),
                                                                                                                                 alignment: _descriptor_0.alignment() }).encode() } },
                                                                          'member',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      lookup(...args_0) {
        if (args_0.length !== 1) {
          throw new __compactRuntime.CompactError(`lookup: expected 1 argument, received ${args_0.length}`);
        }
        const key_0 = args_0[0];
        if (!(key_0.buffer instanceof ArrayBuffer && key_0.BYTES_PER_ELEMENT === 1 && key_0.length === 32)) {
          __compactRuntime.typeError('lookup',
                                     'argument 1',
                                     'brandme_rights.compact line 98 char 1',
                                     'Bytes<32>',
                                     key_0)
        }
        return _descriptor_9.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(4n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_0.toValue(key_0),
                                                                                                     alignment: _descriptor_0.alignment() } }] } },
                                                                          { popeq: { cached: false,
                                                                                     result: undefined } }]).value);
      },
      [Symbol.iterator](...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`iter: expected 0 arguments, received ${args_0.length}`);
        }
        const self_0 = state.asArray()[4];
        return self_0.asMap().keys().map(  (key) => {    const value = self_0.asMap().get(key).asCell();    return [      _descriptor_0.fromValue(key.value),      _descriptor_9.fromValue(value.value)    ];  })[Symbol.iterator]();
      }
    },
    offers: {
      isEmpty(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`isEmpty: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(5n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_6.toValue(0n),
                                                                                                                                 alignment: _descriptor_6.alignment() }).encode() } },
                                                                          'eq',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      size(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`size: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_6.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(5n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      member(...args_0) {
        if (args_0.length !== 1) {
          throw new __compactRuntime.CompactError(`member: expected 1 argument, received ${args_0.length}`);
        }
        const key_0 = args_0[0];
        if (!(key_0.buffer instanceof ArrayBuffer && key_0.BYTES_PER_ELEMENT === 1 && key_0.length === 32)) {
          __compactRuntime.typeError('member',
                                     'argument 1',
                                     'brandme_rights.compact line 99 char 1',
                                     'Bytes<32>',
                                     key_0)
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(5n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(key_0),
                                                                                                                                 alignment: _descriptor_0.alignment() }).encode() } },
                                                                          'member',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      lookup(...args_0) {
        if (args_0.length !== 1) {
          throw new __compactRuntime.CompactError(`lookup: expected 1 argument, received ${args_0.length}`);
        }
        const key_0 = args_0[0];
        if (!(key_0.buffer instanceof ArrayBuffer && key_0.BYTES_PER_ELEMENT === 1 && key_0.length === 32)) {
          __compactRuntime.typeError('lookup',
                                     'argument 1',
                                     'brandme_rights.compact line 99 char 1',
                                     'Bytes<32>',
                                     key_0)
        }
        return _descriptor_12.fromValue(__compactRuntime.queryLedgerState(context,
                                                                          partialProofData,
                                                                          [
                                                                           { dup: { n: 0 } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_21.toValue(5n),
                                                                                                      alignment: _descriptor_21.alignment() } }] } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_0.toValue(key_0),
                                                                                                      alignment: _descriptor_0.alignment() } }] } },
                                                                           { popeq: { cached: false,
                                                                                      result: undefined } }]).value);
      },
      [Symbol.iterator](...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`iter: expected 0 arguments, received ${args_0.length}`);
        }
        const self_0 = state.asArray()[5];
        return self_0.asMap().keys().map(  (key) => {    const value = self_0.asMap().get(key).asCell();    return [      _descriptor_0.fromValue(key.value),      _descriptor_12.fromValue(value.value)    ];  })[Symbol.iterator]();
      }
    },
    usedChallenges: {
      isEmpty(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`isEmpty: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(6n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_6.toValue(0n),
                                                                                                                                 alignment: _descriptor_6.alignment() }).encode() } },
                                                                          'eq',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      size(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`size: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_6.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(6n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      member(...args_0) {
        if (args_0.length !== 1) {
          throw new __compactRuntime.CompactError(`member: expected 1 argument, received ${args_0.length}`);
        }
        const elem_0 = args_0[0];
        if (!(elem_0.buffer instanceof ArrayBuffer && elem_0.BYTES_PER_ELEMENT === 1 && elem_0.length === 32)) {
          __compactRuntime.typeError('member',
                                     'argument 1',
                                     'brandme_rights.compact line 100 char 1',
                                     'Bytes<32>',
                                     elem_0)
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(6n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(elem_0),
                                                                                                                                 alignment: _descriptor_0.alignment() }).encode() } },
                                                                          'member',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      [Symbol.iterator](...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`iter: expected 0 arguments, received ${args_0.length}`);
        }
        const self_0 = state.asArray()[6];
        return self_0.asMap().keys().map((elem) => _descriptor_0.fromValue(elem.value))[Symbol.iterator]();
      }
    },
    manufacturers: {
      isEmpty(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`isEmpty: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(7n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_6.toValue(0n),
                                                                                                                                 alignment: _descriptor_6.alignment() }).encode() } },
                                                                          'eq',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      size(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`size: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_6.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(7n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      member(...args_0) {
        if (args_0.length !== 1) {
          throw new __compactRuntime.CompactError(`member: expected 1 argument, received ${args_0.length}`);
        }
        const key_0 = args_0[0];
        if (!(key_0.buffer instanceof ArrayBuffer && key_0.BYTES_PER_ELEMENT === 1 && key_0.length === 32)) {
          __compactRuntime.typeError('member',
                                     'argument 1',
                                     'brandme_rights.compact line 101 char 1',
                                     'Bytes<32>',
                                     key_0)
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(7n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(key_0),
                                                                                                                                 alignment: _descriptor_0.alignment() }).encode() } },
                                                                          'member',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      lookup(...args_0) {
        if (args_0.length !== 1) {
          throw new __compactRuntime.CompactError(`lookup: expected 1 argument, received ${args_0.length}`);
        }
        const key_0 = args_0[0];
        if (!(key_0.buffer instanceof ArrayBuffer && key_0.BYTES_PER_ELEMENT === 1 && key_0.length === 32)) {
          __compactRuntime.typeError('lookup',
                                     'argument 1',
                                     'brandme_rights.compact line 101 char 1',
                                     'Bytes<32>',
                                     key_0)
        }
        return _descriptor_10.fromValue(__compactRuntime.queryLedgerState(context,
                                                                          partialProofData,
                                                                          [
                                                                           { dup: { n: 0 } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_21.toValue(7n),
                                                                                                      alignment: _descriptor_21.alignment() } }] } },
                                                                           { idx: { cached: false,
                                                                                    pushPath: false,
                                                                                    path: [
                                                                                           { tag: 'value',
                                                                                             value: { value: _descriptor_0.toValue(key_0),
                                                                                                      alignment: _descriptor_0.alignment() } }] } },
                                                                           { popeq: { cached: false,
                                                                                      result: undefined } }]).value);
      },
      [Symbol.iterator](...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`iter: expected 0 arguments, received ${args_0.length}`);
        }
        const self_0 = state.asArray()[7];
        return self_0.asMap().keys().map(  (key) => {    const value = self_0.asMap().get(key).asCell();    return [      _descriptor_0.fromValue(key.value),      _descriptor_10.fromValue(value.value)    ];  })[Symbol.iterator]();
      }
    },
    allowances: {
      isEmpty(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`isEmpty: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(8n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_6.toValue(0n),
                                                                                                                                 alignment: _descriptor_6.alignment() }).encode() } },
                                                                          'eq',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      size(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`size: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_6.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(8n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      member(...args_0) {
        if (args_0.length !== 1) {
          throw new __compactRuntime.CompactError(`member: expected 1 argument, received ${args_0.length}`);
        }
        const key_0 = args_0[0];
        if (!(key_0.buffer instanceof ArrayBuffer && key_0.BYTES_PER_ELEMENT === 1 && key_0.length === 32)) {
          __compactRuntime.typeError('member',
                                     'argument 1',
                                     'brandme_rights.compact line 102 char 1',
                                     'Bytes<32>',
                                     key_0)
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(8n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(key_0),
                                                                                                                                 alignment: _descriptor_0.alignment() }).encode() } },
                                                                          'member',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      lookup(...args_0) {
        if (args_0.length !== 1) {
          throw new __compactRuntime.CompactError(`lookup: expected 1 argument, received ${args_0.length}`);
        }
        const key_0 = args_0[0];
        if (!(key_0.buffer instanceof ArrayBuffer && key_0.BYTES_PER_ELEMENT === 1 && key_0.length === 32)) {
          __compactRuntime.typeError('lookup',
                                     'argument 1',
                                     'brandme_rights.compact line 102 char 1',
                                     'Bytes<32>',
                                     key_0)
        }
        return _descriptor_7.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(8n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_0.toValue(key_0),
                                                                                                     alignment: _descriptor_0.alignment() } }] } },
                                                                          { popeq: { cached: false,
                                                                                     result: undefined } }]).value);
      },
      [Symbol.iterator](...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`iter: expected 0 arguments, received ${args_0.length}`);
        }
        const self_0 = state.asArray()[8];
        return self_0.asMap().keys().map(  (key) => {    const value = self_0.asMap().get(key).asCell();    return [      _descriptor_0.fromValue(key.value),      _descriptor_7.fromValue(value.value)    ];  })[Symbol.iterator]();
      }
    },
    consumptions: {
      isEmpty(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`isEmpty: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(9n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_6.toValue(0n),
                                                                                                                                 alignment: _descriptor_6.alignment() }).encode() } },
                                                                          'eq',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      size(...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`size: expected 0 arguments, received ${args_0.length}`);
        }
        return _descriptor_6.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(9n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          'size',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      member(...args_0) {
        if (args_0.length !== 1) {
          throw new __compactRuntime.CompactError(`member: expected 1 argument, received ${args_0.length}`);
        }
        const key_0 = args_0[0];
        if (!(key_0.buffer instanceof ArrayBuffer && key_0.BYTES_PER_ELEMENT === 1 && key_0.length === 32)) {
          __compactRuntime.typeError('member',
                                     'argument 1',
                                     'brandme_rights.compact line 103 char 1',
                                     'Bytes<32>',
                                     key_0)
        }
        return _descriptor_4.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(9n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          { push: { storage: false,
                                                                                    value: __compactRuntime.StateValue.newCell({ value: _descriptor_0.toValue(key_0),
                                                                                                                                 alignment: _descriptor_0.alignment() }).encode() } },
                                                                          'member',
                                                                          { popeq: { cached: true,
                                                                                     result: undefined } }]).value);
      },
      lookup(...args_0) {
        if (args_0.length !== 1) {
          throw new __compactRuntime.CompactError(`lookup: expected 1 argument, received ${args_0.length}`);
        }
        const key_0 = args_0[0];
        if (!(key_0.buffer instanceof ArrayBuffer && key_0.BYTES_PER_ELEMENT === 1 && key_0.length === 32)) {
          __compactRuntime.typeError('lookup',
                                     'argument 1',
                                     'brandme_rights.compact line 103 char 1',
                                     'Bytes<32>',
                                     key_0)
        }
        return _descriptor_3.fromValue(__compactRuntime.queryLedgerState(context,
                                                                         partialProofData,
                                                                         [
                                                                          { dup: { n: 0 } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_21.toValue(9n),
                                                                                                     alignment: _descriptor_21.alignment() } }] } },
                                                                          { idx: { cached: false,
                                                                                   pushPath: false,
                                                                                   path: [
                                                                                          { tag: 'value',
                                                                                            value: { value: _descriptor_0.toValue(key_0),
                                                                                                     alignment: _descriptor_0.alignment() } }] } },
                                                                          { popeq: { cached: false,
                                                                                     result: undefined } }]).value);
      },
      [Symbol.iterator](...args_0) {
        if (args_0.length !== 0) {
          throw new __compactRuntime.CompactError(`iter: expected 0 arguments, received ${args_0.length}`);
        }
        const self_0 = state.asArray()[9];
        return self_0.asMap().keys().map(  (key) => {    const value = self_0.asMap().get(key).asCell();    return [      _descriptor_0.fromValue(key.value),      _descriptor_3.fromValue(value.value)    ];  })[Symbol.iterator]();
      }
    },
    get sequence() {
      return _descriptor_6.fromValue(__compactRuntime.queryLedgerState(context,
                                                                       partialProofData,
                                                                       [
                                                                        { dup: { n: 0 } },
                                                                        { idx: { cached: false,
                                                                                 pushPath: false,
                                                                                 path: [
                                                                                        { tag: 'value',
                                                                                          value: { value: _descriptor_21.toValue(10n),
                                                                                                   alignment: _descriptor_21.alignment() } }] } },
                                                                        { popeq: { cached: true,
                                                                                   result: undefined } }]).value);
    }
  };
}
const _emptyContext = {
  currentQueryContext: new __compactRuntime.QueryContext(new __compactRuntime.ContractState().data, __compactRuntime.dummyContractAddress())
};
const _dummyContract = new Contract({
  governanceSecret: (...args) => undefined,
  issuerSecret: (...args) => undefined,
  manufacturerSecret: (...args) => undefined,
  holderSecret: (...args) => undefined
});
export const pureCircuits = {
  roleCommitment: (...args_0) => {
    if (args_0.length !== 5) {
      throw new __compactRuntime.CompactError(`roleCommitment: expected 5 arguments (as invoked from Typescript), received ${args_0.length}`);
    }
    const domain_0 = args_0[0];
    const scope_0 = args_0[1];
    const secret_0 = args_0[2];
    const salt_0 = args_0[3];
    const network_0 = args_0[4];
    if (!(domain_0.buffer instanceof ArrayBuffer && domain_0.BYTES_PER_ELEMENT === 1 && domain_0.length === 32)) {
      __compactRuntime.typeError('roleCommitment',
                                 'argument 1',
                                 'brandme_rights.compact line 129 char 1',
                                 'Bytes<32>',
                                 domain_0)
    }
    if (!(scope_0.buffer instanceof ArrayBuffer && scope_0.BYTES_PER_ELEMENT === 1 && scope_0.length === 32)) {
      __compactRuntime.typeError('roleCommitment',
                                 'argument 2',
                                 'brandme_rights.compact line 129 char 1',
                                 'Bytes<32>',
                                 scope_0)
    }
    if (!(secret_0.buffer instanceof ArrayBuffer && secret_0.BYTES_PER_ELEMENT === 1 && secret_0.length === 32)) {
      __compactRuntime.typeError('roleCommitment',
                                 'argument 3',
                                 'brandme_rights.compact line 129 char 1',
                                 'Bytes<32>',
                                 secret_0)
    }
    if (!(salt_0.buffer instanceof ArrayBuffer && salt_0.BYTES_PER_ELEMENT === 1 && salt_0.length === 32)) {
      __compactRuntime.typeError('roleCommitment',
                                 'argument 4',
                                 'brandme_rights.compact line 129 char 1',
                                 'Bytes<32>',
                                 salt_0)
    }
    if (!(network_0.buffer instanceof ArrayBuffer && network_0.BYTES_PER_ELEMENT === 1 && network_0.length === 32)) {
      __compactRuntime.typeError('roleCommitment',
                                 'argument 5',
                                 'brandme_rights.compact line 129 char 1',
                                 'Bytes<32>',
                                 network_0)
    }
    return _dummyContract._roleCommitment_0(domain_0,
                                            scope_0,
                                            secret_0,
                                            salt_0,
                                            network_0);
  },
  holderCommitment: (...args_0) => {
    if (args_0.length !== 5) {
      throw new __compactRuntime.CompactError(`holderCommitment: expected 5 arguments (as invoked from Typescript), received ${args_0.length}`);
    }
    const entitlementId_0 = args_0[0];
    const epoch_0 = args_0[1];
    const secret_0 = args_0[2];
    const salt_0 = args_0[3];
    const network_0 = args_0[4];
    if (!(entitlementId_0.buffer instanceof ArrayBuffer && entitlementId_0.BYTES_PER_ELEMENT === 1 && entitlementId_0.length === 32)) {
      __compactRuntime.typeError('holderCommitment',
                                 'argument 1',
                                 'brandme_rights.compact line 134 char 1',
                                 'Bytes<32>',
                                 entitlementId_0)
    }
    if (!(typeof(epoch_0) === 'bigint' && epoch_0 >= 0n && epoch_0 <= 4294967295n)) {
      __compactRuntime.typeError('holderCommitment',
                                 'argument 2',
                                 'brandme_rights.compact line 134 char 1',
                                 'Uint<0..4294967296>',
                                 epoch_0)
    }
    if (!(secret_0.buffer instanceof ArrayBuffer && secret_0.BYTES_PER_ELEMENT === 1 && secret_0.length === 32)) {
      __compactRuntime.typeError('holderCommitment',
                                 'argument 3',
                                 'brandme_rights.compact line 134 char 1',
                                 'Bytes<32>',
                                 secret_0)
    }
    if (!(salt_0.buffer instanceof ArrayBuffer && salt_0.BYTES_PER_ELEMENT === 1 && salt_0.length === 32)) {
      __compactRuntime.typeError('holderCommitment',
                                 'argument 4',
                                 'brandme_rights.compact line 134 char 1',
                                 'Bytes<32>',
                                 salt_0)
    }
    if (!(network_0.buffer instanceof ArrayBuffer && network_0.BYTES_PER_ELEMENT === 1 && network_0.length === 32)) {
      __compactRuntime.typeError('holderCommitment',
                                 'argument 5',
                                 'brandme_rights.compact line 134 char 1',
                                 'Bytes<32>',
                                 network_0)
    }
    return _dummyContract._holderCommitment_0(entitlementId_0,
                                              epoch_0,
                                              secret_0,
                                              salt_0,
                                              network_0);
  },
  deriveEntitlementId: (...args_0) => {
    if (args_0.length !== 2) {
      throw new __compactRuntime.CompactError(`deriveEntitlementId: expected 2 arguments (as invoked from Typescript), received ${args_0.length}`);
    }
    const issuerId_0 = args_0[0];
    const issuanceId_0 = args_0[1];
    if (!(issuerId_0.buffer instanceof ArrayBuffer && issuerId_0.BYTES_PER_ELEMENT === 1 && issuerId_0.length === 32)) {
      __compactRuntime.typeError('deriveEntitlementId',
                                 'argument 1',
                                 'brandme_rights.compact line 140 char 1',
                                 'Bytes<32>',
                                 issuerId_0)
    }
    if (!(issuanceId_0.buffer instanceof ArrayBuffer && issuanceId_0.BYTES_PER_ELEMENT === 1 && issuanceId_0.length === 32)) {
      __compactRuntime.typeError('deriveEntitlementId',
                                 'argument 2',
                                 'brandme_rights.compact line 140 char 1',
                                 'Bytes<32>',
                                 issuanceId_0)
    }
    return _dummyContract._deriveEntitlementId_0(issuerId_0, issuanceId_0);
  },
  deriveChildEntitlementId: (...args_0) => {
    if (args_0.length !== 2) {
      throw new __compactRuntime.CompactError(`deriveChildEntitlementId: expected 2 arguments (as invoked from Typescript), received ${args_0.length}`);
    }
    const nullifier_0 = args_0[0];
    const unit_0 = args_0[1];
    if (!(nullifier_0.buffer instanceof ArrayBuffer && nullifier_0.BYTES_PER_ELEMENT === 1 && nullifier_0.length === 32)) {
      __compactRuntime.typeError('deriveChildEntitlementId',
                                 'argument 1',
                                 'brandme_rights.compact line 144 char 1',
                                 'Bytes<32>',
                                 nullifier_0)
    }
    if (!(typeof(unit_0) === 'bigint' && unit_0 >= 0n && unit_0 <= 4294967295n)) {
      __compactRuntime.typeError('deriveChildEntitlementId',
                                 'argument 2',
                                 'brandme_rights.compact line 144 char 1',
                                 'Uint<0..4294967296>',
                                 unit_0)
    }
    return _dummyContract._deriveChildEntitlementId_0(nullifier_0, unit_0);
  },
  deriveOfferId: (...args_0) => {
    if (args_0.length !== 3) {
      throw new __compactRuntime.CompactError(`deriveOfferId: expected 3 arguments (as invoked from Typescript), received ${args_0.length}`);
    }
    const entitlementId_0 = args_0[0];
    const epoch_0 = args_0[1];
    const nonce_0 = args_0[2];
    if (!(entitlementId_0.buffer instanceof ArrayBuffer && entitlementId_0.BYTES_PER_ELEMENT === 1 && entitlementId_0.length === 32)) {
      __compactRuntime.typeError('deriveOfferId',
                                 'argument 1',
                                 'brandme_rights.compact line 148 char 1',
                                 'Bytes<32>',
                                 entitlementId_0)
    }
    if (!(typeof(epoch_0) === 'bigint' && epoch_0 >= 0n && epoch_0 <= 4294967295n)) {
      __compactRuntime.typeError('deriveOfferId',
                                 'argument 2',
                                 'brandme_rights.compact line 148 char 1',
                                 'Uint<0..4294967296>',
                                 epoch_0)
    }
    if (!(nonce_0.buffer instanceof ArrayBuffer && nonce_0.BYTES_PER_ELEMENT === 1 && nonce_0.length === 32)) {
      __compactRuntime.typeError('deriveOfferId',
                                 'argument 3',
                                 'brandme_rights.compact line 148 char 1',
                                 'Bytes<32>',
                                 nonce_0)
    }
    return _dummyContract._deriveOfferId_0(entitlementId_0, epoch_0, nonce_0);
  },
  deriveAllowanceId: (...args_0) => {
    if (args_0.length !== 2) {
      throw new __compactRuntime.CompactError(`deriveAllowanceId: expected 2 arguments (as invoked from Typescript), received ${args_0.length}`);
    }
    const issuerId_0 = args_0[0];
    const nonce_0 = args_0[1];
    if (!(issuerId_0.buffer instanceof ArrayBuffer && issuerId_0.BYTES_PER_ELEMENT === 1 && issuerId_0.length === 32)) {
      __compactRuntime.typeError('deriveAllowanceId',
                                 'argument 1',
                                 'brandme_rights.compact line 153 char 1',
                                 'Bytes<32>',
                                 issuerId_0)
    }
    if (!(nonce_0.buffer instanceof ArrayBuffer && nonce_0.BYTES_PER_ELEMENT === 1 && nonce_0.length === 32)) {
      __compactRuntime.typeError('deriveAllowanceId',
                                 'argument 2',
                                 'brandme_rights.compact line 153 char 1',
                                 'Bytes<32>',
                                 nonce_0)
    }
    return _dummyContract._deriveAllowanceId_0(issuerId_0, nonce_0);
  },
  deriveConsumptionNullifier: (...args_0) => {
    if (args_0.length !== 2) {
      throw new __compactRuntime.CompactError(`deriveConsumptionNullifier: expected 2 arguments (as invoked from Typescript), received ${args_0.length}`);
    }
    const allowanceId_0 = args_0[0];
    const jobCommitment_0 = args_0[1];
    if (!(allowanceId_0.buffer instanceof ArrayBuffer && allowanceId_0.BYTES_PER_ELEMENT === 1 && allowanceId_0.length === 32)) {
      __compactRuntime.typeError('deriveConsumptionNullifier',
                                 'argument 1',
                                 'brandme_rights.compact line 157 char 1',
                                 'Bytes<32>',
                                 allowanceId_0)
    }
    if (!(jobCommitment_0.buffer instanceof ArrayBuffer && jobCommitment_0.BYTES_PER_ELEMENT === 1 && jobCommitment_0.length === 32)) {
      __compactRuntime.typeError('deriveConsumptionNullifier',
                                 'argument 2',
                                 'brandme_rights.compact line 157 char 1',
                                 'Bytes<32>',
                                 jobCommitment_0)
    }
    return _dummyContract._deriveConsumptionNullifier_0(allowanceId_0,
                                                        jobCommitment_0);
  },
  deriveChallengeKey: (...args_0) => {
    if (args_0.length !== 4) {
      throw new __compactRuntime.CompactError(`deriveChallengeKey: expected 4 arguments (as invoked from Typescript), received ${args_0.length}`);
    }
    const entitlementId_0 = args_0[0];
    const epoch_0 = args_0[1];
    const challenge_0 = args_0[2];
    const audience_0 = args_0[3];
    if (!(entitlementId_0.buffer instanceof ArrayBuffer && entitlementId_0.BYTES_PER_ELEMENT === 1 && entitlementId_0.length === 32)) {
      __compactRuntime.typeError('deriveChallengeKey',
                                 'argument 1',
                                 'brandme_rights.compact line 161 char 1',
                                 'Bytes<32>',
                                 entitlementId_0)
    }
    if (!(typeof(epoch_0) === 'bigint' && epoch_0 >= 0n && epoch_0 <= 4294967295n)) {
      __compactRuntime.typeError('deriveChallengeKey',
                                 'argument 2',
                                 'brandme_rights.compact line 161 char 1',
                                 'Uint<0..4294967296>',
                                 epoch_0)
    }
    if (!(challenge_0.buffer instanceof ArrayBuffer && challenge_0.BYTES_PER_ELEMENT === 1 && challenge_0.length === 32)) {
      __compactRuntime.typeError('deriveChallengeKey',
                                 'argument 3',
                                 'brandme_rights.compact line 161 char 1',
                                 'Bytes<32>',
                                 challenge_0)
    }
    if (!(audience_0.buffer instanceof ArrayBuffer && audience_0.BYTES_PER_ELEMENT === 1 && audience_0.length === 32)) {
      __compactRuntime.typeError('deriveChallengeKey',
                                 'argument 4',
                                 'brandme_rights.compact line 161 char 1',
                                 'Bytes<32>',
                                 audience_0)
    }
    return _dummyContract._deriveChallengeKey_0(entitlementId_0,
                                                epoch_0,
                                                challenge_0,
                                                audience_0);
  }
};
export const contractReferenceLocations =
  { tag: 'publicLedgerArray', indices: { } };
//# sourceMappingURL=index.js.map
