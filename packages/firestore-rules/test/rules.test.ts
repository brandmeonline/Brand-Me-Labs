// Evaluates firestore.rules in the Firestore emulator. Skips (not passes)
// when FIRESTORE_EMULATOR_HOST is unset or unreachable.
import { after, before, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createConnection } from 'node:net';
import { assertFails, assertSucceeds, initializeTestEnvironment, type RulesTestEnvironment } from '@firebase/rules-unit-testing';
import { doc, getDoc, setDoc, deleteDoc, collection, getDocs, Timestamp } from 'firebase/firestore';

const hostPort = process.env.FIRESTORE_EMULATOR_HOST ?? '';
const reachable = await new Promise<boolean>((res) => {
  const [host, port] = hostPort.split(':');
  if (!host || !port) return res(false);
  const s = createConnection({ host, port: Number(port) }, () => { s.end(); res(true); });
  s.on('error', () => res(false));
  s.setTimeout(1000, () => { s.destroy(); res(false); });
});

if (process.env.BRANDME_REQUIRE_EMULATORS === '1' && !reachable) {
  throw new Error('BRANDME_REQUIRE_EMULATORS=1 but the Firestore emulator is not reachable');
}

describe('firestore.rules', { skip: reachable ? false : 'Firestore emulator not reachable (FIRESTORE_EMULATOR_HOST)' }, () => {
  let env: RulesTestEnvironment;
  const later = () => Timestamp.fromMillis(Date.now() + 3600_000);

  before(async () => {
    const [host, port] = hostPort.split(':');
    env = await initializeTestEnvironment({
      projectId: `bm-rules-${Date.now()}`,
      firestore: { rules: readFileSync(new URL('../firestore.rules', import.meta.url), 'utf8'), host, port: Number(port) },
    });
    await env.withSecurityRulesDisabled(async (ctx) => {
      const db = ctx.firestore();
      await setDoc(doc(db, 'members/ada/views/profile'), { display_name: 'Ada', source_version: 1 });
      await setDoc(doc(db, 'shared/share-1/recipients/bo'), { title: 'Look', expires_at: later(), source_version: 1 });
      await setDoc(doc(db, 'shared/share-1/recipients/cy'), { title: 'Look', expires_at: later(), source_version: 1 });
      await setDoc(doc(db, 'shared/share-expired/recipients/bo'), { title: 'Old', expires_at: Timestamp.fromMillis(Date.now() - 1000), source_version: 1 });
      await setDoc(doc(db, 'projection_tombstones/abc'), { source_version: 2 });
    });
  });
  after(async () => { await env?.cleanup(); });

  test('a member reads only their own private views', async () => {
    await assertSucceeds(getDoc(doc(env.authenticatedContext('ada').firestore(), 'members/ada/views/profile')));
    await assertFails(getDoc(doc(env.authenticatedContext('bo').firestore(), 'members/ada/views/profile')));
    await assertFails(getDoc(doc(env.unauthenticatedContext().firestore(), 'members/ada/views/profile')));
  });

  test('clients cannot write any projection, including their own', async () => {
    const ada = env.authenticatedContext('ada').firestore();
    await assertFails(setDoc(doc(ada, 'members/ada/views/profile'), { display_name: 'Hacked', source_version: 99 }));
    await assertFails(deleteDoc(doc(ada, 'members/ada/views/profile')));
    await assertFails(setDoc(doc(ada, 'shared/new/recipients/ada'), { title: 'x' }));
  });

  test('shared views: each recipient reads only their own copy, no listing, expiry enforced', async () => {
    const bo = env.authenticatedContext('bo').firestore();
    await assertSucceeds(getDoc(doc(bo, 'shared/share-1/recipients/bo')));
    // Another recipient's copy (and so their member id) is not readable.
    await assertFails(getDoc(doc(bo, 'shared/share-1/recipients/cy')));
    await assertFails(getDoc(doc(env.authenticatedContext('eve').firestore(), 'shared/share-1/recipients/bo')));
    await assertFails(getDoc(doc(env.unauthenticatedContext().firestore(), 'shared/share-1/recipients/bo')));
    await assertFails(getDocs(collection(bo, 'shared/share-1/recipients')));
    await assertFails(getDocs(collection(bo, 'shared')));
    await assertFails(getDoc(doc(bo, 'shared/share-1')));
    await assertFails(getDoc(doc(bo, 'shared/share-expired/recipients/bo')));
  });

  test('revocation: once the server deletes the copies, the audience loses access', async () => {
    const bo = env.authenticatedContext('bo').firestore();
    await assertSucceeds(getDoc(doc(bo, 'shared/share-1/recipients/bo')));
    await env.withSecurityRulesDisabled(async (ctx) => {
      await deleteDoc(doc(ctx.firestore(), 'shared/share-1/recipients/bo'));
      await deleteDoc(doc(ctx.firestore(), 'shared/share-1/recipients/cy'));
    });
    await assertFails(getDoc(doc(bo, 'shared/share-1/recipients/bo')));
  });

  test('tombstones and unlisted collections are closed', async () => {
    const ada = env.authenticatedContext('ada').firestore();
    await assertFails(getDoc(doc(ada, 'projection_tombstones/abc')));
    await assertFails(getDoc(doc(ada, 'anything/else')));
    await assertFails(getDocs(collection(ada, 'members')));
  });

  test('rules file compiled in the emulator (sanity)', () => {
    assert.ok(env);
  });
});
