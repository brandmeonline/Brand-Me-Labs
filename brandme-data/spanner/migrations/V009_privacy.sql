-- V009_privacy.sql — My Data: export, deletion, tombstones, processing freeze (W10)
-- Owner: opus-midnight-rights lane. GoogleSQL (Cloud Spanner). Verified on emulator 1.5.45.

CREATE TABLE ExportJobs (
  job_id STRING(36) NOT NULL,
  subject_ref STRING(128) NOT NULL,
  state STRING(16) NOT NULL,                   -- requested | running | ready | expired | failed
  categories ARRAY<STRING(64)> NOT NULL,
  manifest_json JSON,
  package_ref STRING(512),                     -- object-storage ref; short-lived signed URL is minted on demand
  package_sha256 STRING(64),
  reauth_at TIMESTAMP NOT NULL,
  requested_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  expires_at TIMESTAMP,
  CONSTRAINT ck_export_state CHECK (state IN ('requested','running','ready','expired','failed')),
) PRIMARY KEY (job_id);

CREATE INDEX ExportJobsBySubject ON ExportJobs(subject_ref, requested_at DESC);

CREATE TABLE DeletionJobs (
  job_id STRING(36) NOT NULL,
  subject_ref STRING(128) NOT NULL,
  scope STRING(16) NOT NULL,                   -- account | category
  categories ARRAY<STRING(64)> NOT NULL,
  state STRING(32) NOT NULL,                   -- requested | running | completed | completed_with_exceptions | failed
  reauth_at TIMESTAMP NOT NULL,
  requested_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  receipt_json JSON,
  version INT64 NOT NULL,
  CONSTRAINT ck_deletion_state CHECK (state IN ('requested','running','completed','completed_with_exceptions','failed')),
) PRIMARY KEY (job_id);

CREATE INDEX DeletionJobsBySubject ON DeletionJobs(subject_ref, requested_at DESC);
CREATE INDEX DeletionJobsByState ON DeletionJobs(state);

-- One row per (job, category handler step); resumable.
CREATE TABLE DeletionSteps (
  job_id STRING(36) NOT NULL,
  category STRING(64) NOT NULL,
  step STRING(32) NOT NULL,                    -- freeze | revoke | cancel_jobs | delete_records | delete_projections | delete_media | provider_request | exceptions
  state STRING(16) NOT NULL,                   -- pending | done | exception | failed
  rows_affected INT64,
  detail STRING(1024),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (job_id, category, step),
  INTERLEAVE IN PARENT DeletionJobs ON DELETE CASCADE;

-- Tombstones survive deletion and are reapplied after any restore from backup,
-- before restored data becomes accessible. They hold no personal data.
CREATE TABLE DeletionTombstones (
  subject_ref STRING(128) NOT NULL,
  category STRING(64) NOT NULL,
  tombstone_id STRING(36) NOT NULL,
  deletion_job_id STRING(36) NOT NULL,
  record_keys ARRAY<STRING(256)>,              -- domain-specific opaque keys, when deletion is narrower than the whole category
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (subject_ref, category, tombstone_id);

CREATE INDEX DeletionTombstonesByCreated ON DeletionTombstones(created_at);

-- Processing freeze: set in the same transaction that accepts a deletion request.
-- Every writer of personal/derived data checks it inside its own read/write
-- transaction, so a queued inference job that commits later cannot recreate data.
CREATE TABLE ProcessingFreezes (
  subject_ref STRING(128) NOT NULL,
  category STRING(64) NOT NULL,                -- '*' for whole account
  reason STRING(32) NOT NULL,                  -- deletion | restriction | consent_revoked
  deletion_job_id STRING(36),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (subject_ref, category);

-- Restore ledger: a restored database is not served until tombstones are reapplied.
CREATE TABLE RestoreRuns (
  restore_id STRING(36) NOT NULL,
  backup_ref STRING(512) NOT NULL,
  backup_taken_at TIMESTAMP NOT NULL,
  state STRING(24) NOT NULL,                   -- restoring | tombstones_reapplied | serving | failed
  tombstones_applied INT64,
  started_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
) PRIMARY KEY (restore_id);
