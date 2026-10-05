/**
 * Private-state lifecycle: encryption at rest, account isolation, lock,
 * backup → clean-profile restore (then actually used to prove control),
 * and wrong-network / wrong-contract / wrong-password rejection.
 */
import { MemoryLevel } from 'memory-level';
import { PrivateStateSession, PrivateStateLockedError, AccountChangedError, BackupBindingError } from '../../src/midnight/private-state.js';
import { Actor, RightsSimulator, issue, registerIssuer } from '../support/scenario.js';
import { random32, toHex } from '../../src/midnight/bytes.js';

const pw = () => 'Storage-Pass-2026!';

function session(dbs: Map<string, MemoryLevel<string, string>>, accountId: string, opts: { network?: 'preprod' | 'preview'; contract?: string } = {}) {
  return new PrivateStateSession({
    network: opts.network ?? 'preprod',
    contractAddress: opts.contract ?? 'aa'.repeat(32),
    accountId,
    passwordProvider: pw,
    levelFactory: (name) => {
      if (!dbs.has(name)) dbs.set(name, new MemoryLevel<string, string>());
      return dbs.get(name)! as never;
    },
  });
}

describe('PrivateStateSession', () => {
  it('stores state encrypted (no secret appears in raw storage)', async () => {
    const dbs = new Map();
    const s = session(dbs, 'acct-A');
    const secret = toHex(random32());
    await s.save({ schema: 'brandme.rights.private/v1', issuerSecrets: {}, manufacturerSecrets: {}, holderSecrets: { ['11'.repeat(32)]: secret } });
    expect((await s.load()).holderSecrets['11'.repeat(32)]).toBe(secret);
    let raw = '';
    for (const db of dbs.values()) {
      const d = db as MemoryLevel<string, string>;
      if (d.status !== 'open') await d.open();
      for await (const [k, v] of d.iterator()) raw += `${k}${v}`;
    }
    expect(raw.length).toBeGreaterThan(0);
    expect(raw).not.toContain(secret);
  });

  it('isolates accounts: a different wallet account does not inherit state', async () => {
    const dbs = new Map();
    const a = session(dbs, 'acct-A');
    await a.save({ schema: 'brandme.rights.private/v1', issuerSecrets: {}, manufacturerSecrets: {}, holderSecrets: { ['22'.repeat(32)]: toHex(random32()) } });
    const b = session(dbs, 'acct-B');
    expect(Object.keys((await b.load()).holderSecrets)).toHaveLength(0);
  });

  it('lock drops access; account change locks and throws', async () => {
    const s = session(new Map(), 'acct-A');
    await s.load();
    const g = s.currentGeneration;
    await s.lock();
    expect(s.currentGeneration).toBe(g + 1);
    await expect(s.load()).rejects.toBeInstanceOf(PrivateStateLockedError);
    s.unlock();
    await s.load();
    await expect(s.onAccountChanged('acct-B')).rejects.toBeInstanceOf(AccountChangedError);
    expect(s.isLocked).toBe(true);
  });

  it('backup → clean profile restore → restored secret proves control on the contract', async () => {
    const sim = new RightsSimulator('preprod');
    const issuer = new Actor('issuer');
    const holder = new Actor('holder');
    const iid = registerIssuer(sim, issuer);
    const { eid } = issue(sim, issuer, iid, holder);

    const original = session(new Map(), 'acct-A');
    await original.save(holder.privateState);
    const backup = await original.exportBackup('Backup-Pass-2026!');
    expect(JSON.stringify(backup)).not.toContain(holder.privateState.holderSecrets[toHex(eid)]);

    // Device lost: fresh storage, same wallet account.
    const restored = session(new Map(), 'acct-A');
    expect(Object.keys((await restored.load()).holderSecrets)).toHaveLength(0);
    const r = await restored.restoreBackup(backup, 'Backup-Pass-2026!');
    expect(r.imported).toBe(1);
    const recovered = new Actor('holder-restored', await restored.load());
    sim.call(recovered, 'proveControl', eid, random32(), random32()); // real circuit accepts restored secret
  });

  it('refuses wrong network, wrong contract, wrong account and wrong password before writing', async () => {
    const src = session(new Map(), 'acct-A');
    await src.save({ schema: 'brandme.rights.private/v1', issuerSecrets: {}, manufacturerSecrets: {}, holderSecrets: { ['33'.repeat(32)]: toHex(random32()) } });
    const backup = await src.exportBackup('Backup-Pass-2026!');

    const wrongNet = session(new Map(), 'acct-A', { network: 'preview' });
    await expect(wrongNet.restoreBackup(backup, 'Backup-Pass-2026!')).rejects.toBeInstanceOf(BackupBindingError);
    expect(Object.keys((await wrongNet.load()).holderSecrets)).toHaveLength(0);

    const wrongContract = session(new Map(), 'acct-A', { contract: 'bb'.repeat(32) });
    await expect(wrongContract.restoreBackup(backup, 'Backup-Pass-2026!')).rejects.toBeInstanceOf(BackupBindingError);

    const wrongAccount = session(new Map(), 'acct-B');
    await expect(wrongAccount.restoreBackup(backup, 'Backup-Pass-2026!')).rejects.toBeInstanceOf(BackupBindingError);

    const ok = session(new Map(), 'acct-A');
    await expect(ok.restoreBackup(backup, 'Wrong-Pass-2026!')).rejects.toThrow();
    expect(Object.keys((await ok.load()).holderSecrets)).toHaveLength(0);
  });

  it('rejects weak backup passwords', async () => {
    await expect(session(new Map(), 'a').exportBackup('short')).rejects.toThrow(/at least 12/);
  });
});
