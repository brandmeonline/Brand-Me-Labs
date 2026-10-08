/**
 * Guards: no stub/simulated fallback can enter the Midnight trust path.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { midnightCapability } from '../../src/midnight/capability.js';

const SRC = join(__dirname, '../../src');
const walk = (d: string): string[] => readdirSync(d).flatMap((n) => (statSync(join(d, n)).isDirectory() ? walk(join(d, n)) : [join(d, n)]));

describe('trust path', () => {
  const files = walk(SRC).filter((f) => f.endsWith('.ts'));

  it('production source never imports test-only code (simulator, mocks, testkit)', () => {
    for (const f of files) {
      const s = readFileSync(f, 'utf8');
      expect(s, f).not.toMatch(/from ['"][^'"]*\/tests\//);
      expect(s, f).not.toMatch(/@midnight-ntwrk\/testkit-js/);
      expect(s, f).not.toMatch(/inMemoryPrivateStateProvider/);
    }
  });

  it('the Midnight adapter contains no simulated/stub/fallback paths', () => {
    for (const f of files.filter((x) => x.includes('/midnight/'))) {
      const code = readFileSync(f, 'utf8').replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
      expect(code, f).not.toMatch(/simulat|stub_|_stub|fallback|encrypted_|Math\.random/i);
    }
  });

  it('removed fallback flags abort startup', async () => {
    process.env.MIDNIGHT_FALLBACK_MODE = 'true';
    await expect(import('../../src/config/index.js?fallback')).rejects.toThrow(/no longer supported/);
    delete process.env.MIDNIGHT_FALLBACK_MODE;
  });

  it('capability is unavailable (not green) without a deployed contract, and Mainnet is never writable', () => {
    const base = { port: 0, environment: 'development' as const, corsOrigins: [], logLevel: 'info' as const };
    const pre = midnightCapability({ ...base, midnightNetwork: 'preprod' });
    expect(pre.status).toBe('unavailable');
    expect(pre.reasons.join(' ')).toMatch(/no rights contract/);
    expect(pre.badge).toBe('Preprod test network');
    expect(pre.artifacts.verified).toBe(true);
    const main = midnightCapability({ ...base, midnightNetwork: 'mainnet', midnightBlockfrostProjectId: 'abcdefgh12', midnightContractAddress: 'ab'.repeat(32) });
    expect(main.writesAuthorized).toBe(false);
    expect(main.status).not.toBe('available');
  });
});
