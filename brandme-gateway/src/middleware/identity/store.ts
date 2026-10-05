/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Spanner persistence for the identity boundary (V001 tables): external
 * identity → internal member mapping, server-side sessions, and the member
 * profile/settings aggregate. Every state change commits with its outbox event
 * in one read/write transaction (same row shape as brandme_core.events).
 *
 * Only SHA-256 hashes of session and CSRF secrets are stored.
 */

import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { Spanner, type Database } from '@google-cloud/spanner';
import type { Transaction } from '@google-cloud/spanner/build/src/transaction';

export type Mode = 'demo' | 'development' | 'sandbox' | 'production';
export type Assurance = 'simulated' | 'aal1' | 'aal2';

export interface MemberRow {
  member_id: string;
  handle: string | null;
  display_name: string | null;
  locale: string;
  timezone: string;
  age_eligibility_status: string;
  account_state: string;
  onboarding_state: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface SettingsRow {
  room_theme: string | null;
  motion_mode: string;
  quality_mode: string;
  default_visibility: string;
  notify_in_app: boolean;
  notify_email: boolean;
  notify_push: boolean;
  version: number;
}

export interface SessionRow {
  member_id: string;
  identity_provider: string;
  assurance_level: Assurance;
  client_id: string | null;
  csrf_hash: string;
  environment: Mode;
  expires_at: Date;
}

export interface MePatch {
  handle?: string;
  display_name?: string;
  locale?: string;
  timezone?: string;
  settings?: Partial<Pick<SettingsRow, 'room_theme' | 'motion_mode' | 'quality_mode' | 'default_visibility'>>;
}

export class VersionConflictError extends Error {
  constructor(public readonly currentVersion: number) {
    super(`revision conflict (current ${currentVersion})`);
  }
}
export class HandleTakenError extends Error {}
export class MemberInactiveError extends Error {}

export const sha256 = (s: string) => createHash('sha256').update(s).digest('hex');
const SHARDS = 16;
export const shardFor = (eventId: string) => parseInt(sha256(eventId).slice(0, 8), 16) % SHARDS;
const token = () => randomBytes(32).toString('base64url');

interface OutboxEvent {
  event_type: string;
  aggregate_type: string;
  aggregate_id: string;
  aggregate_version: number;
  privacy_class: 'public' | 'member_private' | 'restricted';
  payload: Record<string, unknown>;
}

export class IdentityStore {
  readonly database: Database;
  private readonly mode: Mode;

  constructor(opts: { projectId: string; instanceId: string; databaseId: string; mode: Mode }) {
    this.mode = opts.mode;
    if (process.env.SPANNER_EMULATOR_HOST) {
      // @google-cloud/spanner 9.0.0 + emulator 1.5.28: the emulator does not mark
      // multiplexed sessions, so read/write transactions fail on release
      // ("Unable to release unknown resource"). Emulator-only workaround;
      // see docs/build/compatibility-lock.md.
      process.env.GOOGLE_CLOUD_SPANNER_MULTIPLEXED_SESSIONS ??= 'false';
      process.env.GOOGLE_CLOUD_SPANNER_MULTIPLEXED_SESSIONS_FOR_RW ??= 'false';
    }
    this.database = new Spanner({ projectId: opts.projectId }).instance(opts.instanceId).database(opts.databaseId);
  }

  async ping(): Promise<void> {
    await this.database.run({ sql: 'SELECT 1' });
  }

  async close(): Promise<void> {
    await this.database.close();
  }

  private outbox(tx: Transaction, actorRef: string, correlationId: string, ev: OutboxEvent): void {
    const eventId = randomUUID();
    const now = new Date();
    tx.insert('OutboxEvents', {
      shard: shardFor(eventId),
      event_id: eventId,
      event_type: ev.event_type,
      schema_version: '1',
      aggregate_type: ev.aggregate_type,
      aggregate_id: ev.aggregate_id,
      aggregate_version: ev.aggregate_version,
      occurred_at: now,
      environment: this.mode,
      actor_ref: actorRef,
      correlation_id: correlationId,
      causation_id: null,
      privacy_class: ev.privacy_class,
      payload: JSON.stringify(ev.payload),
      status: 'pending',
      attempts: 0,
      next_attempt_at: now,
      created_at: Spanner.COMMIT_TIMESTAMP,
    });
  }

  /** Map (issuer, subject) to an internal member, creating one on first sight. Idempotent. */
  async resolveMember(issuer: string, subject: string, provider: string, correlationId: string): Promise<{ memberId: string; created: boolean }> {
    return this.database.runTransactionAsync(async (tx) => {
      const [rows] = await tx.read('MemberIdentities', { keys: [[issuer, subject]], columns: ['member_id'], json: true });
      if (rows.length) {
        const memberId = (rows[0] as { member_id: string }).member_id;
        tx.update('MemberIdentities', { issuer, subject, last_seen_at: Spanner.COMMIT_TIMESTAMP });
        await tx.commit();
        return { memberId, created: false };
      }
      const memberId = randomUUID();
      tx.insert('Members', {
        member_id: memberId,
        handle: null,
        display_name: null,
        locale: 'en-US',
        timezone: 'UTC',
        age_eligibility_status: 'unknown',
        account_state: 'active',
        environment: this.mode,
        onboarding_state: 'not_started',
        version: 1,
        created_at: Spanner.COMMIT_TIMESTAMP,
        updated_at: Spanner.COMMIT_TIMESTAMP,
      });
      tx.insert('MemberSettings', {
        member_id: memberId,
        room_theme: null,
        motion_mode: 'system',
        quality_mode: 'auto',
        default_visibility: 'private',
        notify_in_app: true,
        notify_email: false,
        notify_push: false,
        version: 1,
        updated_at: Spanner.COMMIT_TIMESTAMP,
      });
      tx.insert('MemberIdentities', {
        issuer,
        subject,
        member_id: memberId,
        identity_provider: provider,
        created_at: Spanner.COMMIT_TIMESTAMP,
        last_seen_at: Spanner.COMMIT_TIMESTAMP,
      });
      this.outbox(tx, `member:${memberId}`, correlationId, {
        event_type: 'member.created',
        aggregate_type: 'member',
        aggregate_id: memberId,
        aggregate_version: 1,
        privacy_class: 'member_private',
        payload: { member_id: memberId, identity_provider: provider },
      });
      await tx.commit();
      return { memberId, created: true };
    });
  }

  async createSession(memberId: string, provider: string, assurance: Assurance, clientId: string | null, ttlHours: number) {
    const secret = token();
    const csrf = token();
    const expiresAt = new Date(Date.now() + ttlHours * 3600_000);
    await this.database.table('Sessions').insert({
      session_hash: sha256(secret),
      member_id: memberId,
      identity_provider: provider,
      assurance_level: assurance,
      client_id: clientId,
      csrf_hash: sha256(csrf),
      environment: this.mode,
      created_at: Spanner.COMMIT_TIMESTAMP,
      expires_at: expiresAt,
      revoked_at: null,
    });
    return { secret, csrf, expiresAt };
  }

  /** Returns the session only if unrevoked, unexpired and minted in this mode. */
  async loadSession(secret: string): Promise<SessionRow | null> {
    const [rows] = await this.database.run({
      sql: `SELECT member_id, identity_provider, assurance_level, client_id, csrf_hash, environment, expires_at
            FROM Sessions WHERE session_hash = @h AND revoked_at IS NULL AND expires_at > CURRENT_TIMESTAMP()`,
      params: { h: sha256(secret) },
      json: true,
    });
    const row = rows[0] as (Omit<SessionRow, 'expires_at'> & { expires_at: string }) | undefined;
    if (!row || row.environment !== this.mode) return null;
    return { ...row, expires_at: new Date(row.expires_at) };
  }

  async rotateCsrf(secret: string): Promise<string> {
    const csrf = token();
    await this.database.table('Sessions').update({ session_hash: sha256(secret), csrf_hash: sha256(csrf) });
    return csrf;
  }

  async revokeSession(secret: string, memberId: string, reason: 'sign_out' | 'account_switch' | 'security' | 'deletion', correlationId: string): Promise<void> {
    await this.database.runTransactionAsync(async (tx) => {
      tx.update('Sessions', { session_hash: sha256(secret), revoked_at: Spanner.COMMIT_TIMESTAMP });
      this.outbox(tx, `member:${memberId}`, correlationId, {
        event_type: 'session.revoked',
        aggregate_type: 'member',
        aggregate_id: memberId,
        aggregate_version: 0,
        privacy_class: 'restricted',
        payload: { member_id: memberId, reason },
      });
      await tx.commit();
    });
  }

  async getMember(memberId: string): Promise<{ member: MemberRow; settings: SettingsRow } | null> {
    const [rows] = await this.database.run({
      sql: `SELECT m.member_id, m.handle, m.display_name, m.locale, m.timezone, m.age_eligibility_status,
                   m.account_state, m.onboarding_state, m.version, m.created_at, m.updated_at,
                   s.room_theme, s.motion_mode, s.quality_mode, s.default_visibility,
                   s.notify_in_app, s.notify_email, s.notify_push, s.version AS settings_version
            FROM Members m JOIN MemberSettings s ON s.member_id = m.member_id
            WHERE m.member_id = @id`,
      params: { id: memberId },
      json: true,
    });
    const r = rows[0] as Record<string, unknown> | undefined;
    if (!r) return null;
    return {
      member: {
        member_id: r.member_id as string,
        handle: r.handle as string | null,
        display_name: r.display_name as string | null,
        locale: r.locale as string,
        timezone: r.timezone as string,
        age_eligibility_status: r.age_eligibility_status as string,
        account_state: r.account_state as string,
        onboarding_state: r.onboarding_state as string,
        version: Number(r.version),
        created_at: new Date(r.created_at as string).toISOString(),
        updated_at: new Date(r.updated_at as string).toISOString(),
      },
      settings: {
        room_theme: r.room_theme as string | null,
        motion_mode: r.motion_mode as string,
        quality_mode: r.quality_mode as string,
        default_visibility: r.default_visibility as string,
        notify_in_app: r.notify_in_app as boolean,
        notify_email: r.notify_email as boolean,
        notify_push: r.notify_push as boolean,
        version: Number(r.settings_version),
      },
    };
  }

  /** Optimistic concurrency on the member aggregate (version covers settings too). */
  async patchMember(memberId: string, expectedVersion: number, patch: MePatch, correlationId: string): Promise<number> {
    return this.database.runTransactionAsync(async (tx) => {
      const [rows] = await tx.read('Members', { keys: [memberId], columns: ['version', 'account_state'], json: true });
      const row = rows[0] as { version: number | string; account_state: string } | undefined;
      if (!row || row.account_state !== 'active') throw new MemberInactiveError('member not active');
      const current = Number(row.version);
      if (current !== expectedVersion) throw new VersionConflictError(current);
      if (patch.handle !== undefined) {
        const [taken] = await tx.run({
          sql: 'SELECT member_id FROM Members@{FORCE_INDEX=MembersByHandle} WHERE handle = @h AND member_id != @id',
          params: { h: patch.handle, id: memberId },
          json: true,
        });
        if (taken.length) throw new HandleTakenError('handle taken');
      }
      const next = current + 1;
      const memberFields: Record<string, unknown> = { member_id: memberId, version: next, updated_at: Spanner.COMMIT_TIMESTAMP };
      const changed: string[] = [];
      for (const k of ['handle', 'display_name', 'locale', 'timezone'] as const) {
        if (patch[k] !== undefined) {
          memberFields[k] = patch[k];
          changed.push(k);
        }
      }
      tx.update('Members', memberFields);
      if (patch.settings && Object.keys(patch.settings).length) {
        const [srows] = await tx.read('MemberSettings', { keys: [memberId], columns: ['version'], json: true });
        const sv = Number((srows[0] as { version: number | string }).version);
        tx.update('MemberSettings', { member_id: memberId, ...patch.settings, version: sv + 1, updated_at: Spanner.COMMIT_TIMESTAMP });
        changed.push(...Object.keys(patch.settings).map((k) => `settings.${k}`));
      }
      this.outbox(tx, `member:${memberId}`, correlationId, {
        event_type: 'member.updated',
        aggregate_type: 'member',
        aggregate_id: memberId,
        aggregate_version: next,
        privacy_class: 'member_private',
        payload: { member_id: memberId, changed_fields: changed },
      });
      await tx.commit();
      return next;
    });
  }
}
