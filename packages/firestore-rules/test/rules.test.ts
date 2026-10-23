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
      await setDoc(doc(db, 'shared/share-1'), { title: 'Look', audience: ['bo'], expires_at: later(), source_version: 1 });
      await setDoc(doc(db, 'shared/share-expired'), { title: 'Old', audience: ['bo'], expires_at: Timestamp.fromMillis(Date.now() - 1000), source_version: 1 });
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
    await assertFails(setDoc(doc(ada, 'shared/new'), { audience: ['ada'] }));
  });

  test('shared views: audience-only get, no listing, expiry enforced', async () => {
    await assertSucceeds(getDoc(doc(env.authenticatedContext('bo').firestore(), 'shared/share-1')));
    await assertFails(getDoc(doc(env.authenticatedContext('eve').firestore(), 'shared/share-1')));
    await assertFails(getDoc(doc(env.unauthenticatedContext().firestore(), 'shared/share-1')));
    await assertFails(getDocs(collection(env.authenticatedContext('bo').firestore(), 'shared')));
    await assertFails(getDoc(doc(env.authenticatedContext('bo').firestore(), 'shared/share-expired')));
  });

  test('revocation: once the server deletes the share, the audience loses access', async () => {
    const bo = env.authenticatedContext('bo').firestore();
    await assertSucceeds(getDoc(doc(bo, 'shared/share-1')));
    await env.withSecurityRulesDisabled(async (ctx) => { await deleteDoc(doc(ctx.firestore(), 'shared/share-1')); });
    await assertFails(getDoc(doc(bo, 'shared/share-1')));
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
