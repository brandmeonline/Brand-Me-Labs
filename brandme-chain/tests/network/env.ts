/**
 * Network test environment resolution + evidence recorder.
 */
import { LocalTestConfiguration, PreprodTestEnvironment, createDefaultTestLogger, MidnightWalletProvider, type EnvironmentConfiguration } from '@midnight-ntwrk/testkit-js';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { localEndpoints, PUBLIC_ENDPOINTS, type MidnightEndpoints } from '../../src/midnight/network.js';

export const logger = createDefaultTestLogger();

export function resolveNetwork(): { env: EnvironmentConfiguration; endpoints: MidnightEndpoints; seeds: string[] } {
  const net = process.env.MIDNIGHT_NETWORK ?? 'undeployed';
  if (net === 'mainnet') throw new Error('network tests never run against Mainnet');
  if (net === 'undeployed') {
    const ports = { node: Number(process.env.MN_NODE_PORT), indexer: Number(process.env.MN_INDEXER_PORT), proofServer: Number(process.env.MN_PROOF_PORT ?? 6300) };
    if (!ports.node || !ports.indexer) throw new Error('MN_NODE_PORT / MN_INDEXER_PORT not set (run scripts/local-network.sh up)');
    return {
      env: new LocalTestConfiguration(ports),
      endpoints: localEndpoints(ports),
      // Genesis-funded seeds of the local dev chain (testkit LocalTestEnvironment.genesisMintWalletSeed).
      // Seeds 1–3 are funded in the node 1.0.300 dev genesis (seed 4 is not).
      seeds: ['0000000000000000000000000000000000000000000000000000000000000001',
        '0000000000000000000000000000000000000000000000000000000000000002',
        '0000000000000000000000000000000000000000000000000000000000000003',
        '0000000000000000000000000000000000000000000000000000000000000004'],
    };
  }
  if (net === 'preprod') {
    const seeds = (process.env.MN_PREPROD_SEEDS ?? '').split(',').filter(Boolean);
    if (seeds.length < 3) throw new Error('MN_PREPROD_SEEDS must list 3+ funded Preprod wallet seeds (never Mainnet seeds)');
    const env = { ...new PreprodTestEnvironment(logger).getEnvironmentConfiguration(), proofServer: `http://127.0.0.1:${process.env.MN_PROOF_PORT ?? 6300}` };
    return { env, endpoints: PUBLIC_ENDPOINTS.preprod, seeds };
  }
  throw new Error(`unsupported MIDNIGHT_NETWORK ${net}`);
}

export async function startWallet(env: EnvironmentConfiguration, seed: string) {
  const w = await MidnightWalletProvider.build(logger, env, seed);
  await w.start(true);
  return w;
}

export class Evidence {
  readonly entries: Record<string, unknown>[] = [];
  constructor(readonly network: string, readonly meta: Record<string, unknown>) {}
  add(step: string, data: Record<string, unknown>) {
    const e = { step, at: new Date().toISOString(), ...data };
    this.entries.push(e);
    logger.info(e, `evidence: ${step}`);
  }
  write() {
    const dir = join(__dirname, '../../evidence');
    mkdirSync(dir, { recursive: true });
    const file = join(dir, `${this.network}-${new Date().toISOString().replace(/[:.]/g, '-')}.json`);
    writeFileSync(file, JSON.stringify({ network: this.network, ...this.meta, entries: this.entries }, (_k, v) => (typeof v === 'bigint' ? v.toString() : v), 2));
    return file;
  }
}
