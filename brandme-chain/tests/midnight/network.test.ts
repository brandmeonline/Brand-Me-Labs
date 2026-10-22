import { preprodEndpoints, mainnetEndpoints, assertWritable } from '../../src/midnight/network.js';
import { midnightCapability } from '../../src/midnight/capability.js';
import { redactProviderSecrets } from '../../src/midnight/redaction.js';
import { rootCauseMessage } from '../../src/midnight/adapter.js';

describe('current Preprod connectivity', () => {
  it('uses authenticated Blockfrost endpoints for both indexer transports and RPC', () => {
    const endpoints = preprodEndpoints('nightpreprodtestonly123');
    expect(new URL(endpoints.nodeRpc).hostname).toBe('rpc.midnight-preprod.blockfrost.io');
    expect(new URL(endpoints.indexerHttp).pathname).toBe('/api/v0');
    expect(new URL(endpoints.indexerWs).pathname).toBe('/api/v0/ws');
    for (const url of [endpoints.nodeRpc, endpoints.indexerHttp, endpoints.indexerWs]) {
      expect(new URL(url).searchParams.get('project_id')).toBe('nightpreprodtestonly123');
    }
  });
  it('rejects absent, invalid and wrong-network credentials without echoing them', () => {
    for (const token of ['', 'bad-secret', 'nightmainnettestonly123']) expect(() => preprodEndpoints(token)).toThrow('Midnight preprod project token is required');
    expect(() => mainnetEndpoints('nightpreprodtestonly123')).toThrow('Midnight mainnet project token is required');
  });
  it('does not equate configured endpoints with application write readiness', () => {
    const base = { port: 3003, environment: 'development' as const, corsOrigins: [], logLevel: 'info' as const,
      midnightNetwork: 'preprod' as const, midnightContractAddress: 'ab'.repeat(32) };
    expect(midnightCapability(base).status).toBe('unavailable');
    const cap = midnightCapability({ ...base, midnightBlockfrostProjectId: 'nightpreprodtestonly123' });
    expect(cap.status).toBe('read_only');
    expect(JSON.stringify(cap)).not.toContain('nightpreprodtestonly123');
    expect(() => assertWritable('mainnet')).toThrow(/not authorized/);
  });
  it('redacts credentials before persisting provider error reasons', () => {
    const message = 'request https://example/?project_id=otherSecret and nightpreprodtestonly123 failed';
    expect(rootCauseMessage(new Error(message))).not.toMatch(/otherSecret|nightpreprodtestonly123/);
    expect(redactProviderSecrets('seed-value in evidence', ['seed-value'])).toBe('[REDACTED] in evidence');
  });
});
