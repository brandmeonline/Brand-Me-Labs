-- V001 identity + platform foundation (opus-foundation lane)
-- Spanner GoogleSQL. Applied by runner.py; recorded in SchemaMigrations.
--
-- Identity: members, external identity mapping (issuer+subject -> member),
-- settings, server-side sessions, purpose-specific consent grants.
-- Platform: transactional outbox, inbox receipts, idempotency records and an
-- audit trail. Every domain migration (V002+) relies on these.
--
-- Rules: UUID STRING(36) keys (no monotonically increasing leading keys);
-- `version` INT64 on mutable aggregates; UTC TIMESTAMP; no email as a key.

CREATE TABLE Members (
  member_id STRING(36) NOT NULL,
  handle STRING(30),
  display_name STRING(80),
  locale STRING(35) NOT NULL,
  timezone STRING(64) NOT NULL,
  age_eligibility_status STRING(32) NOT NULL,
  account_state STRING(32) NOT NULL,
  environment STRING(16) NOT NULL,
  onboarding_state STRING(32) NOT NULL,
  version INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT members_account_state CHECK (account_state IN ('active', 'suspended', 'deletion_requested', 'deleted')),
  CONSTRAINT members_age CHECK (age_eligibility_status IN ('unknown', 'self_declared_adult', 'verified_adult', 'ineligible')),
  CONSTRAINT members_env CHECK (environment IN ('demo', 'development', 'sandbox', 'production')),
  CONSTRAINT members_version CHECK (version >= 1),
) PRIMARY KEY (member_id);

CREATE UNIQUE NULL_FILTERED INDEX MembersByHandle ON Members(handle);

CREATE TABLE MemberSettings (
  member_id STRING(36) NOT NULL,
  room_theme STRING(32),
  motion_mode STRING(16) NOT NULL,
  quality_mode STRING(16) NOT NULL,
  default_visibility STRING(32) NOT NULL,
  notify_in_app BOOL NOT NULL,
  notify_email BOOL NOT NULL,
  notify_push BOOL NOT NULL,
  version INT64 NOT NULL,
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

-- External identity -> internal member. (issuer, subject) is the identity;
-- email is never a key.
CREATE TABLE MemberIdentities (
  issuer STRING(512) NOT NULL,
  subject STRING(256) NOT NULL,
  member_id STRING(36) NOT NULL,
  identity_provider STRING(40) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  last_seen_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (issuer, subject);

CREATE INDEX MemberIdentitiesByMember ON MemberIdentities(member_id);

-- Sessions store only SHA-256 hashes of the cookie secret and CSRF token.
CREATE TABLE Sessions (
  session_hash STRING(64) NOT NULL,
  member_id STRING(36) NOT NULL,
  identity_provider STRING(40) NOT NULL,
  assurance_level STRING(16) NOT NULL,
  client_id STRING(128),
  csrf_hash STRING(64) NOT NULL,
  environment STRING(16) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  expires_at TIMESTAMP NOT NULL,
  revoked_at TIMESTAMP,
  CONSTRAINT sessions_assurance CHECK (assurance_level IN ('simulated', 'aal1', 'aal2')),
) PRIMARY KEY (session_hash),
  ROW DELETION POLICY (OLDER_THAN(expires_at, INTERVAL 30 DAY));

CREATE INDEX SessionsByMember ON Sessions(member_id, expires_at DESC);

CREATE TABLE ConsentGrants (
  member_id STRING(36) NOT NULL,
  consent_id STRING(36) NOT NULL,
  purpose STRING(64) NOT NULL,
  data_categories ARRAY<STRING(64)> NOT NULL,
  grantee_ref STRING(256),
  scope STRING(64) NOT NULL,
  valid_until TIMESTAMP,
  state STRING(16) NOT NULL,
  revision INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  revoked_at TIMESTAMP,
  CONSTRAINT consent_state CHECK (state IN ('active', 'revoked', 'expired')),
) PRIMARY KEY (member_id, consent_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE INDEX ConsentGrantsByPurpose ON ConsentGrants(member_id, purpose, state), INTERLEAVE IN Members;

-- Transactional outbox. shard = stable hash(event_id) % 16 (spreads writes;
-- the dispatcher scans shards independently). Delivery is at least once.
CREATE TABLE OutboxEvents (
  shard INT64 NOT NULL,
  event_id STRING(36) NOT NULL,
  event_type STRING(80) NOT NULL,
  schema_version STRING(32) NOT NULL,
  aggregate_type STRING(80) NOT NULL,
  aggregate_id STRING(36) NOT NULL,
  aggregate_version INT64 NOT NULL,
  occurred_at TIMESTAMP NOT NULL,
  environment STRING(16) NOT NULL,
  actor_ref STRING(256) NOT NULL,
  correlation_id STRING(36) NOT NULL,
  causation_id STRING(36),
  privacy_class STRING(16) NOT NULL,
  payload JSON NOT NULL,
  status STRING(16) NOT NULL,
  attempts INT64 NOT NULL,
  next_attempt_at TIMESTAMP NOT NULL,
  lease_owner STRING(64),
  lease_expires_at TIMESTAMP,
  delivered_at TIMESTAMP,
  last_error STRING(512),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT outbox_status CHECK (status IN ('pending', 'leased', 'delivered', 'dead')),
  CONSTRAINT outbox_shard CHECK (shard >= 0 AND shard < 16),
) PRIMARY KEY (shard, event_id);

CREATE INDEX OutboxByStatus ON OutboxEvents(shard, status, next_attempt_at);
CREATE INDEX OutboxByAggregate ON OutboxEvents(aggregate_type, aggregate_id, aggregate_version);

-- Consumer-side dedupe: a consumer records the receipt in the same
-- transaction as its state change.
CREATE TABLE InboxReceipts (
  consumer STRING(80) NOT NULL,
  event_id STRING(36) NOT NULL,
  event_type STRING(80) NOT NULL,
  received_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (consumer, event_id);

-- Idempotency scoped to (principal, environment, operation, key); the
-- canonical request digest detects key reuse with a different request.
CREATE TABLE IdempotencyRecords (
  principal_ref STRING(256) NOT NULL,
  environment STRING(16) NOT NULL,
  operation STRING(80) NOT NULL,
  idempotency_key STRING(128) NOT NULL,
  request_digest STRING(64) NOT NULL,
  state STRING(16) NOT NULL,
  response_status INT64,
  response_body JSON,
  resource_ref STRING(256),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  expires_at TIMESTAMP NOT NULL,
  CONSTRAINT idem_state CHECK (state IN ('in_progress', 'completed')),
) PRIMARY KEY (principal_ref, environment, operation, idempotency_key);

CREATE TABLE AuditEntries (
  audit_id STRING(36) NOT NULL,
  occurred_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  environment STRING(16) NOT NULL,
  actor_ref STRING(256) NOT NULL,
  action STRING(80) NOT NULL,
  target_ref STRING(256),
  reason STRING(512),
  request_id STRING(36),
  detail JSON,
) PRIMARY KEY (audit_id);

CREATE INDEX AuditEntriesByTarget ON AuditEntries(target_ref, occurred_at DESC);
