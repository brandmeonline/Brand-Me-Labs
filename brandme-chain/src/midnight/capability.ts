/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Midnight capability report. The consumer UI and gateway read this to decide
 * what to offer; an unavailable capability is shown as unavailable with its
 * reason — never as a green badge.
 */

import type { ChainConfig } from '../config/index.js';
import { ArtifactIntegrityError, verifyArtifactsOrThrow } from './adapter.js';
import { localEndpoints, mainnetEndpoints, preprodEndpoints, PUBLIC_ENDPOINTS, type MidnightEndpoints } from './network.js';
import manifest from '../../contracts/artifact-manifest.json' with { type: 'json' };
import toolchain from '../../contracts/toolchain.json' with { type: 'json' };

export type CapabilityStatus = 'available' | 'read_only' | 'unavailable';

export interface MidnightCapability {
  readonly network: string;
  readonly badge: string | null;
  readonly status: CapabilityStatus;
  readonly reasons: readonly string[];
  readonly contractAddress: string | null;
  readonly writesAuthorized: boolean;
  readonly tuple: { compactc: string; runtime: string; proofServerImage: string };
  readonly artifacts: { verified: boolean; contracts: readonly string[] };
  /** Who sees witness inputs in each supported proving mode (ch.04 §9). */
  readonly witnessExposure: Readonly<Record<string, string>>;
}

export function resolveEndpoints(c: ChainConfig): MidnightEndpoints | null {
  switch (c.midnightNetwork) {
    case 'preview': return PUBLIC_ENDPOINTS.preview;
    case 'preprod':
    case 'mainnet':
      try {
        return c.midnightBlockfrostProjectId
          ? (c.midnightNetwork === 'preprod' ? preprodEndpoints : mainnetEndpoints)(c.midnightBlockfrostProjectId) : null;
      } catch { return null; }
    case 'undeployed':
      return c.midnightLocalNodePort && c.midnightLocalIndexerPort
        ? localEndpoints({ node: c.midnightLocalNodePort, indexer: c.midnightLocalIndexerPort })
        : null;
  }
}

export function midnightCapability(c: ChainConfig): MidnightCapability {
  const reasons: string[] = [];
  const endpoints = resolveEndpoints(c);
  if (!endpoints) reasons.push(`no endpoint configuration for ${c.midnightNetwork}`);
  let verified = true;
  try {
    verifyArtifactsOrThrow();
  } catch (e) {
    verified = false;
    reasons.push(e instanceof ArtifactIntegrityError ? e.message : 'artifact verification failed');
  }
  if (!c.midnightContractAddress) reasons.push('no rights contract deployed/configured for this network');
  const writesAuthorized = false; // HTTP write orchestration is not configured yet.
  if (c.midnightNetwork === 'mainnet') reasons.push('Mainnet writes are not authorized in this build');
  reasons.push('member command submission is not configured');
  if (!(c.chainServiceToken && c.spannerProjectId && c.spannerInstanceId && c.spannerDatabaseId)) {
    reasons.push('durable operation status and reconciliation are not configured');
  }
  const status: CapabilityStatus =
    !endpoints || !verified || !c.midnightContractAddress ? 'unavailable' : reasons.length ? 'read_only' : 'available';
  return {
    network: c.midnightNetwork,
    badge: { undeployed: 'Local test network', preview: 'Preview test network', preprod: 'Preprod test network', mainnet: 'Mainnet' }[c.midnightNetwork],
    status,
    reasons,
    contractAddress: c.midnightContractAddress ?? null,
    writesAuthorized,
    tuple: { compactc: manifest.compactc, runtime: manifest.runtimeVersion, proofServerImage: toolchain.proofServerImage },
    artifacts: { verified, contracts: Object.keys(manifest.contracts) },
    witnessExposure: {
      'local-proof-server': 'Only the member’s own machine/companion running the proof server.',
      wallet: 'The wallet/prover the member connected.',
      managed: 'The named prover operator sees all witness inputs. Requires explicit consent; never automatic.',
    },
  };
}
