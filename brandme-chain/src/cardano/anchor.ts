/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Optional Cardano public provenance anchor (ch.04 §8).
 *
 * - Never on the Midnight critical path: Midnight operations finalize and
 *   project without waiting for this. Anchoring is a separate, later batch
 *   with its own status.
 * - Batches only approved, non-personal commitments (finalized Midnight tx
 *   hashes and random entitlement ids), as a domain-separated SHA-256 Merkle root.
 * - A Cardano anchor is a public timestamp of that root. It is NOT a
 *   cross-chain proof or a bridge, and is never described as one.
 *
 * No submitter is verified in this build, so the default is
 * UnavailableCardanoAnchor. The previous builder (which returned
 * `simulated_cardano_*` hashes) was removed.
 */

import { createHash } from 'node:crypto';

export type AnchorStatus = 'not_requested' | 'batched' | 'submitted' | 'confirmed' | 'failed' | 'unavailable';

export interface AnchorLeaf {
  readonly network: 'preview' | 'preprod' | 'mainnet' | 'undeployed';
  readonly midnightTxHash: string;   // finalized only
  readonly entitlementId: string;    // random 32-byte id, hex
}

export interface AnchorBatch {
  readonly batchId: string;
  readonly root: string;
  readonly leaves: readonly AnchorLeaf[];
  readonly status: AnchorStatus;
}

const H = (prefix: string, ...parts: Buffer[]) => createHash('sha256').update(Buffer.from(prefix)).update(Buffer.concat(parts)).digest();

export function leafHash(l: AnchorLeaf): Buffer {
  for (const [k, v] of [['midnightTxHash', l.midnightTxHash], ['entitlementId', l.entitlementId]] as const) {
    if (!/^[0-9a-f]{64}$/i.test(v)) throw new Error(`${k} must be 32-byte hex (approved non-personal commitment)`);
  }
  return H('brandme:anchor-leaf:v1', Buffer.from(l.network), Buffer.from(l.midnightTxHash, 'hex'), Buffer.from(l.entitlementId, 'hex'));
}

/** Domain-separated binary Merkle root; odd node is promoted (not duplicated). Leaves sorted for determinism. */
export function merkleRoot(leaves: readonly AnchorLeaf[]): string {
  if (!leaves.length) throw new Error('empty batch');
  if (new Set(leaves.map((l) => l.network)).size !== 1) throw new Error('a batch must not mix networks');
  let level = leaves.map(leafHash).sort(Buffer.compare);
  while (level.length > 1) {
    const next: Buffer[] = [];
    for (let i = 0; i < level.length; i += 2) next.push(i + 1 < level.length ? H('brandme:anchor-node:v1', level[i]!, level[i + 1]!) : level[i]!);
    level = next;
  }
  return level[0]!.toString('hex');
}

export interface CardanoAnchorSubmitter {
  readonly verified: boolean;
  capability(): { status: 'available' | 'unavailable'; reasons: string[] };
  submit(batch: AnchorBatch): Promise<{ txHash: string }>;
}

export class UnavailableCardanoAnchor implements CardanoAnchorSubmitter {
  readonly verified = false;
  capability() {
    return {
      status: 'unavailable' as const,
      reasons: ['No verified Cardano anchor adapter: requires Blockfrost Preprod credentials and an integration test before enablement.'],
    };
  }
  async submit(): Promise<{ txHash: string }> {
    throw new Error('Cardano anchoring is unavailable in this build');
  }
}
