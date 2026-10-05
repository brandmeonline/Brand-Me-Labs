/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Midnight network registry and wrong-network guard.
 *
 * Endpoints from https://docs.midnight.network/relnotes/network (fetched
 * 2026-10-05). Midnight-hosted Mainnet endpoints were retired 2026-09-30
 * 22:00 UTC; Mainnet is served by Blockfrost and needs a project token,
 * which is only ever attached server-side (never in a browser URL).
 */

export type MidnightNetworkId = 'undeployed' | 'preview' | 'preprod' | 'mainnet';

export interface MidnightEndpoints {
  readonly networkId: MidnightNetworkId;
  readonly nodeRpc: string;
  readonly indexerHttp: string;
  readonly indexerWs: string;
  /** Human label that must stay visible on every surface showing evidence from this network. */
  readonly badge: 'Local test network' | 'Preview test network' | 'Preprod test network' | 'Mainnet';
  readonly isTestNetwork: boolean;
}

export const PUBLIC_ENDPOINTS: Readonly<Record<Exclude<MidnightNetworkId, 'undeployed' | 'mainnet'>, MidnightEndpoints>> = {
  preview: {
    networkId: 'preview',
    nodeRpc: 'https://rpc.preview.midnight.network',
    indexerHttp: 'https://indexer.preview.midnight.network/api/v4/graphql',
    indexerWs: 'wss://indexer.preview.midnight.network/api/v4/graphql/ws',
    badge: 'Preview test network',
    isTestNetwork: true,
  },
  preprod: {
    networkId: 'preprod',
    nodeRpc: 'https://rpc.preprod.midnight.network',
    indexerHttp: 'https://indexer.preprod.midnight.network/api/v4/graphql',
    indexerWs: 'wss://indexer.preprod.midnight.network/api/v4/graphql/ws',
    badge: 'Preprod test network',
    isTestNetwork: true,
  },
};

/** Mainnet via Blockfrost. Token appended server-side only. */
export function mainnetEndpoints(blockfrostProjectId: string): MidnightEndpoints {
  if (!/^[A-Za-z0-9_-]{8,}$/.test(blockfrostProjectId)) throw new Error('invalid Blockfrost project id');
  const q = `?project_id=${encodeURIComponent(blockfrostProjectId)}`;
  return {
    networkId: 'mainnet',
    nodeRpc: `https://rpc.midnight-mainnet.blockfrost.io${q}`,
    indexerHttp: `https://midnight-mainnet.blockfrost.io/api/v0${q}`,
    indexerWs: `wss://midnight-mainnet.blockfrost.io/api/v0/ws${q}`,
    badge: 'Mainnet',
    isTestNetwork: false,
  };
}

export function localEndpoints(ports: { node: number; indexer: number }): MidnightEndpoints {
  return {
    networkId: 'undeployed',
    nodeRpc: `http://127.0.0.1:${ports.node}`,
    indexerHttp: `http://127.0.0.1:${ports.indexer}/api/v4/graphql`,
    indexerWs: `ws://127.0.0.1:${ports.indexer}/api/v4/graphql/ws`,
    badge: 'Local test network',
    isTestNetwork: true,
  };
}

export class WrongNetworkError extends Error {
  constructor(readonly expected: MidnightNetworkId, readonly actual: string, readonly where: string) {
    super(`wrong network at ${where}: expected ${expected}, got ${actual}`);
    this.name = 'WrongNetworkError';
  }
}

export class WritesNotAuthorizedError extends Error {
  constructor(network: MidnightNetworkId) {
    super(`writes to ${network} are not authorized in this build`);
    this.name = 'WritesNotAuthorizedError';
  }
}

/**
 * No Mainnet writes. This build has no switch to enable them: a Mainnet
 * deployment/custody decision is a separately authorized launch action
 * (README "Release interpretation"; ch.04 §1).
 */
export function assertWritable(network: MidnightNetworkId): void {
  if (network === 'mainnet') throw new WritesNotAuthorizedError(network);
}

/** Compare a wallet/connector-reported network id to the deployment's allowed network. */
export function assertSameNetwork(expected: MidnightNetworkId, actual: string | undefined, where: string): void {
  if (actual !== expected) throw new WrongNetworkError(expected, String(actual), where);
}
