/**
 * Network test environment resolution + evidence recorder.
 */
import { LocalTestConfiguration, MidnightWalletProvider, type EnvironmentConfiguration } from '@midnight-ntwrk/testkit-js';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { localEndpoints, preprodEndpoints, type MidnightEndpoints } from '../../src/midnight/network.js';

import { pino } from 'pino';
import { redactProviderSecrets } from '../../src/midnight/redaction.js';

const secrets = () => (process.env.MN_PREPROD_SEEDS ?? '').split(',').map(s => s.trim()).filter(Boolean);
const redact = (value: string) => redactProviderSecrets(value, secrets());
// Testkit's default logger writes provider URLs to an unredacted file. Use only this redacted stream.
export const logger = pino({ level: 'info' }, { write: (line: string) => process.stdout.write(redact(line)) });

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
      // Seeds 1–3 are funded in the dev genesis (exercised on node 1.0.300 and 1.0.400); seed 4 was unfunded on 1.0.300.
      seeds: ['0000000000000000000000000000000000000000000000000000000000000001',
        '0000000000000000000000000000000000000000000000000000000000000002',
        '0000000000000000000000000000000000000000000000000000000000000003',
        '0000000000000000000000000000000000000000000000000000000000000004'],
    };
  }
  if (net === 'preprod') {
    const seeds = (process.env.MN_PREPROD_SEEDS ?? '').split(',').map(s => s.trim()).filter(Boolean);
    if (seeds.length < 3 || seeds.some(s => !/^[0-9a-f]{64}$/i.test(s)) || new Set(seeds).size !== seeds.length) {
      throw new Error('MN_PREPROD_SEEDS must list 3+ distinct 32-byte hex seeds for Preprod wallets funded with tNIGHT and DUST');
    }
    const endpoints = preprodEndpoints(process.env.MIDNIGHT_BLOCKFROST_PROJECT_ID ?? '');
    const proofPort = Number(process.env.MN_PROOF_PORT ?? 6300);
    if (!Number.isInteger(proofPort) || proofPort < 1 || proofPort > 65535) throw new Error('invalid MN_PROOF_PORT');
    const env: EnvironmentConfiguration = {
      networkId: 'preprod', walletNetworkId: 'preprod',
      node: endpoints.nodeRpc, nodeWS: endpoints.nodeRpc.replace(/^https:/, 'wss:'),
      indexer: endpoints.indexerHttp, indexerWS: endpoints.indexerWs,
      proofServer: `http://127.0.0.1:${proofPort}`, faucet: undefined,
    };
    return { env, endpoints, seeds };
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
    this.entries.push(JSON.parse(redact(JSON.stringify(e, (_k, v) => typeof v === 'bigint' ? v.toString() : v))));
    logger.info(e, `evidence: ${step}`);
  }
  write() {
    const dir = join(__dirname, '../../evidence');
    mkdirSync(dir, { recursive: true });
    const file = join(dir, `${this.network}-${new Date().toISOString().replace(/[:.]/g, '-')}.json`);
    writeFileSync(file, redact(JSON.stringify({ network: this.network, ...this.meta, entries: this.entries }, (_k, v) => (typeof v === 'bigint' ? v.toString() : v), 2)));
    return file;
  }
}
