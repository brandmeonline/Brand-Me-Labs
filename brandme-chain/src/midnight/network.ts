/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Midnight network registry and wrong-network guard.
 *
 * Endpoints verified against https://docs.midnight.network/guides/networks-and-environments
 * on 2026-10-22. Preprod and Mainnet are served by Blockfrost and need a project token,
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

export const PUBLIC_ENDPOINTS: Readonly<Record<'preview', MidnightEndpoints>> = {
  preview: {
    networkId: 'preview',
    nodeRpc: 'https://rpc.preview.midnight.network',
    indexerHttp: 'https://indexer.preview.midnight.network/api/v4/graphql',
    indexerWs: 'wss://indexer.preview.midnight.network/api/v4/graphql/ws',
    badge: 'Preview test network',
    isTestNetwork: true,
  },

};

/** Credentials stay in server-side provider configuration, never capability responses. */
function blockfrostEndpoints(network: 'preprod' | 'mainnet', projectId: string): MidnightEndpoints {
  if (!new RegExp(`^night${network}[A-Za-z0-9_-]{8,}$`).test(projectId)) {
    throw new Error(`a Blockfrost Midnight ${network} project token is required`);
  }
  const q = `?project_id=${encodeURIComponent(projectId)}`;
  return {
    networkId: network,
    nodeRpc: `https://rpc.midnight-${network}.blockfrost.io${q}`,
    indexerHttp: `https://midnight-${network}.blockfrost.io/api/v0${q}`,
    indexerWs: `wss://midnight-${network}.blockfrost.io/api/v0/ws${q}`,
    badge: network === 'preprod' ? 'Preprod test network' : 'Mainnet',
    isTestNetwork: network === 'preprod',
  };
}

export const preprodEndpoints = (projectId: string): MidnightEndpoints => blockfrostEndpoints('preprod', projectId);
export const mainnetEndpoints = (projectId: string): MidnightEndpoints => blockfrostEndpoints('mainnet', projectId);

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
