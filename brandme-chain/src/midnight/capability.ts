/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Midnight capability report. The consumer UI and gateway read this to decide
 * what to offer; an unavailable capability is shown as unavailable with its
 * reason — never as a green badge.
 */

import type { ChainConfig } from '../config/index.js';
import { ArtifactIntegrityError, verifyArtifactsOrThrow } from './adapter.js';
import { localEndpoints, mainnetEndpoints, PUBLIC_ENDPOINTS, type MidnightEndpoints } from './network.js';
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
    case 'preview':
    case 'preprod':
      return PUBLIC_ENDPOINTS[c.midnightNetwork];
    case 'mainnet':
      return c.midnightBlockfrostProjectId ? mainnetEndpoints(c.midnightBlockfrostProjectId) : null;
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
  const writesAuthorized = c.midnightNetwork !== 'mainnet';
  if (!writesAuthorized) reasons.push('Mainnet writes are not authorized in this build');
  if (c.environment !== 'development' && c.environment !== 'demo') {
    reasons.push('durable operation store not configured (Spanner ChainOperations); writes disabled outside development');
  }
  const status: CapabilityStatus =
    !endpoints || !verified || !c.midnightContractAddress ? 'unavailable' : reasons.length ? 'read_only' : 'available';
  return {
    network: c.midnightNetwork,
    badge: endpoints?.badge ?? null,
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
