import { resolveNetwork } from '../network/env.js';

afterEach(() => vi.unstubAllEnvs());

describe('Preprod test configuration', () => {
  const seeds = [101, 102, 103].map(n => n.toString(16).padStart(64, '0')).join(',');
  it('requires distinct test seeds and a matching provider token before opening connections', () => {
    vi.stubEnv('MIDNIGHT_NETWORK', 'preprod');
    vi.stubEnv('MN_PREPROD_SEEDS', '');
    expect(() => resolveNetwork()).toThrow(/3\+ distinct/);
    vi.stubEnv('MN_PREPROD_SEEDS', seeds);
    vi.stubEnv('MIDNIGHT_BLOCKFROST_PROJECT_ID', 'nightmainnettestonly123');
    expect(() => resolveNetwork()).toThrow(/Midnight preprod project token/);
  });
  it('configures every network transport on Blockfrost and keeps proving on loopback', () => {
    vi.stubEnv('MIDNIGHT_NETWORK', 'preprod'); vi.stubEnv('MN_PREPROD_SEEDS', seeds);
    vi.stubEnv('MIDNIGHT_BLOCKFROST_PROJECT_ID', 'nightpreprodtestonly123');
    const { env } = resolveNetwork();
    for (const url of [env.node, env.nodeWS, env.indexer, env.indexerWS]) {
      expect(new URL(url).hostname).toMatch(/midnight-preprod.blockfrost.io$/);
      expect(new URL(url).searchParams.get('project_id')).toBe('nightpreprodtestonly123');
    }
    expect(env.walletNetworkId).toBe('preprod');
    expect(new URL(env.proofServer).hostname).toBe('127.0.0.1');
  });
  it('never permits Mainnet tests', () => {
    vi.stubEnv('MIDNIGHT_NETWORK', 'mainnet');
    expect(() => resolveNetwork()).toThrow(/never run against Mainnet/);
  });
});
