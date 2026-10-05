/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * User-controlled private state: account-scoped, encrypted at rest, with an
 * explicit backup/restore flow (ch.04 §3).
 *
 * Storage and encryption are the official
 * @midnight-ntwrk/midnight-js-level-private-state-provider (password-derived
 * key, account-scoped namespaces). This module adds:
 *   - lock/unlock/account-changed lifecycle; decrypted caches are dropped on lock;
 *   - a backup envelope bound to {network, contract, account} so a backup
 *     cannot be restored against another network or contract;
 *   - restore into a clean profile with conflict policy "error" by default.
 *
 * What a wallet seed alone restores: NOTHING in this state. Holder/issuer
 * secrets are random values independent of the wallet seed. Recovery requires
 * this backup file AND its backup password. This is stated in the UI copy.
 */

import { levelPrivateStateProvider, type LevelFactory } from '@midnight-ntwrk/midnight-js-level-private-state-provider';
import type { PrivateStateExport, PrivateStateProvider } from '@midnight-ntwrk/midnight-js-types';
import { createHash } from 'node:crypto';
import type { MidnightNetworkId } from './network.js';
import { emptyPrivateState, type RightsPrivateState } from './rights-contract.js';

export const PRIVATE_STATE_ID = 'brandme-rights';

export interface PrivateStateSessionConfig {
  readonly network: MidnightNetworkId;
  readonly contractAddress: string;
  /** Wallet account identity (e.g. coin public key). Private state is namespaced by it. */
  readonly accountId: string;
  /** Storage password. Never a hard-coded value or a shared server secret. */
  readonly passwordProvider: () => string | Promise<string>;
  readonly levelFactory?: LevelFactory;
  readonly dbName?: string;
}

export class PrivateStateLockedError extends Error {
  constructor() { super('private state is locked'); this.name = 'PrivateStateLockedError'; }
}

export class AccountChangedError extends Error {
  constructor(readonly from: string, readonly to: string) {
    super('wallet account changed; private state session closed');
    this.name = 'AccountChangedError';
  }
}

export class BackupBindingError extends Error {
  constructor(field: string, expected: string, got: string) {
    super(`backup belongs to a different ${field} (expected ${expected.slice(0, 18)}…, got ${got.slice(0, 18)}…)`);
    this.name = 'BackupBindingError';
  }
}

export interface PrivateStateBackup {
  readonly format: 'brandme.rights.private-state-backup/v1';
  readonly network: MidnightNetworkId;
  readonly contractAddress: string;
  /** sha256(accountId) — binds without storing the raw account identifier. */
  readonly accountDigest: string;
  readonly createdAt: string;
  readonly export: PrivateStateExport;
}

const accountDigest = (accountId: string) => createHash('sha256').update(`brandme:account:${accountId}`).digest('hex');

export class PrivateStateSession {
  private provider: (PrivateStateProvider<string, RightsPrivateState> & { invalidateEncryptionCache(): Promise<void> }) | null;
  /** Bumped on every lock/account change; in-flight operations compare it before submitting. */
  private generation = 0;

  constructor(readonly config: PrivateStateSessionConfig) {
    this.provider = this.open();
  }

  private open() {
    const p = levelPrivateStateProvider<string, RightsPrivateState>({
      accountId: this.config.accountId,
      privateStoragePasswordProvider: this.config.passwordProvider,
      levelFactory: this.config.levelFactory,
      midnightDbName: this.config.dbName ?? `brandme-midnight-${this.config.network}`,
    });
    p.setContractAddress(this.config.contractAddress as never);
    return p;
  }

  get currentGeneration(): number { return this.generation; }
  get isLocked(): boolean { return this.provider === null; }

  /** The provider handed to midnight-js for this session. Throws when locked. */
  get stateProvider(): PrivateStateProvider<string, RightsPrivateState> {
    if (!this.provider) throw new PrivateStateLockedError();
    return this.provider;
  }

  async load(): Promise<RightsPrivateState> {
    return (await this.stateProvider.get(PRIVATE_STATE_ID)) ?? emptyPrivateState();
  }

  async save(ps: RightsPrivateState): Promise<void> {
    await this.stateProvider.set(PRIVATE_STATE_ID, ps);
  }

  /** Drop decrypted material and refuse further access until unlock(). */
  async lock(): Promise<void> {
    this.generation++;
    if (this.provider) await this.provider.invalidateEncryptionCache();
    this.provider = null;
  }

  unlock(): void {
    if (!this.provider) this.provider = this.open();
  }

  /**
   * Called when the connected wallet reports a different account. The old
   * account's state is never carried over: we lock, and the caller must open
   * a new session for the new account.
   */
  async onAccountChanged(newAccountId: string): Promise<never> {
    await this.lock();
    throw new AccountChangedError(this.config.accountId, newAccountId);
  }

  async exportBackup(backupPassword: string): Promise<PrivateStateBackup> {
    if (backupPassword.length < 12) throw new Error('backup password must be at least 12 characters');
    const exp = await this.stateProvider.exportPrivateStates({ password: backupPassword });
    return {
      format: 'brandme.rights.private-state-backup/v1',
      network: this.config.network,
      contractAddress: this.config.contractAddress,
      accountDigest: accountDigest(this.config.accountId),
      createdAt: new Date().toISOString(),
      export: exp,
    };
  }

  /**
   * Restore into this session. Refuses a backup for another network, contract
   * or account BEFORE touching storage.
   */
  async restoreBackup(backup: PrivateStateBackup, backupPassword: string, conflictStrategy: 'error' | 'skip' | 'overwrite' = 'error') {
    if (backup.format !== 'brandme.rights.private-state-backup/v1') throw new Error('unrecognized backup format');
    if (backup.network !== this.config.network) throw new BackupBindingError('network', this.config.network, backup.network);
    if (backup.contractAddress.toLowerCase() !== this.config.contractAddress.toLowerCase()) {
      throw new BackupBindingError('contract', this.config.contractAddress, backup.contractAddress);
    }
    const mine = accountDigest(this.config.accountId);
    if (backup.accountDigest !== mine) throw new BackupBindingError('account', mine, backup.accountDigest);
    return this.stateProvider.importPrivateStates(backup.export, { password: backupPassword, conflictStrategy });
  }
}
