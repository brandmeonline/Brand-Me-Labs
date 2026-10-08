-- INTERIM test-only DDL for tables owned by the opus-foundation lane (V001 +
-- event framework). It exists so the consumer-domain migrations V002-V005 can be
-- exercised against the Spanner emulator before foundation merges. It is NOT a
-- migration and must be deleted once V001 / brandme_core/events ship these
-- tables. Column names follow chapter 03 §4/§5; reconcile at integration.

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
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (shard, event_id);

CREATE INDEX OutboxEventsByStatus ON OutboxEvents (shard, status, next_attempt_at);

CREATE TABLE InboxReceipts (
  consumer STRING(80) NOT NULL,
  event_id STRING(36) NOT NULL,
  processed_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (consumer, event_id);

CREATE TABLE IdempotencyRecords (
  principal_ref STRING(256) NOT NULL,
  environment STRING(16) NOT NULL,
  operation STRING(80) NOT NULL,
  idempotency_key STRING(128) NOT NULL,
  request_digest STRING(64) NOT NULL,
  response JSON NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  expires_at TIMESTAMP NOT NULL,
) PRIMARY KEY (principal_ref, environment, operation, idempotency_key);
