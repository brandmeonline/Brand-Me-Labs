import { merkleRoot, leafHash, UnavailableCardanoAnchor } from '../../src/cardano/anchor.js';
const leaf = (i: number) => ({ network: 'preprod' as const, midnightTxHash: i.toString(16).padStart(64, '0'), entitlementId: (i + 100).toString(16).padStart(64, '0') });
describe('Cardano anchor (optional, independent of Midnight)', () => {
  it('root is deterministic and order-independent', () => {
    const ls = [1, 2, 3, 4, 5].map(leaf);
    expect(merkleRoot(ls)).toBe(merkleRoot([...ls].reverse()));
    expect(merkleRoot(ls)).not.toBe(merkleRoot(ls.slice(0, 4)));
  });
  it('accepts only 32-byte hex commitments (no personal data) and refuses mixed networks', () => {
    expect(() => leafHash({ network: 'preprod', midnightTxHash: 'alice@example.com', entitlementId: '00'.repeat(32) })).toThrow();
    expect(() => merkleRoot([leaf(1), { ...leaf(2), network: 'preview' }])).toThrow(/mix networks/);
  });
  it('no unverified submitter: reports unavailable and refuses to submit', async () => {
    const a = new UnavailableCardanoAnchor();
    expect(a.capability().status).toBe('unavailable');
    await expect(a.submit()).rejects.toThrow();
  });
});
