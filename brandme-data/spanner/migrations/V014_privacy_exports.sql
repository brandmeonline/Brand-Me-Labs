-- Selected-category exports. Separate from the legacy synchronous ExportJobs.
-- One isolated database and private bucket per environment. No object URLs or
-- credentials are stored in jobs; object names derive from opaque attempt IDs.
CREATE TABLE PrivacyExportJobs (
  environment STRING(16) NOT NULL,
  job_id STRING(36) NOT NULL,
  subject_ref STRING(128) NOT NULL,
  network STRING(16) NOT NULL,
  contract_address STRING(64) NOT NULL,
  categories ARRAY<STRING(64)> NOT NULL,
  state STRING(16) NOT NULL,
  requested_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  attempt_id STRING(36),
  attempts INT64 NOT NULL,
  lease_until TIMESTAMP,
  next_attempt_at TIMESTAMP NOT NULL,
  object_generation STRING(32),
  package_sha256 STRING(64),
  package_bytes INT64,
  failure_code STRING(32),
  CONSTRAINT ck_privacy_export_state CHECK (state IN ('requested','building','ready','failed','expired')),
  CONSTRAINT ck_privacy_export_network CHECK (network IN ('undeployed','preview','preprod')),
) PRIMARY KEY (environment, job_id);

CREATE INDEX PrivacyExportsBySubject ON PrivacyExportJobs(environment, subject_ref, requested_at DESC);
CREATE INDEX PrivacyExportsByWork ON PrivacyExportJobs(environment, state, next_attempt_at);
CREATE INDEX PrivacyExportsByExpiry ON PrivacyExportJobs(environment, expires_at);

CREATE TABLE PrivacyExportRequests (
  environment STRING(16) NOT NULL,
  subject_ref STRING(128) NOT NULL,
  key_hash STRING(64) NOT NULL,
  request_hash STRING(64) NOT NULL,
  job_id STRING(36) NOT NULL,
) PRIMARY KEY (environment, subject_ref, key_hash);

-- A durable cleanup ledger, created BEFORE any external upload. Retain rows:
-- even a process resuming late after its lease expires cannot create an orphan
-- that is forgotten after a single successful delete. Cleanup is recurring;
-- bucket lifecycle is an additional backstop, not proof of physical deletion.
CREATE TABLE PrivacyExportObjects (
  environment STRING(16) NOT NULL,
  job_id STRING(36) NOT NULL,
  attempt_id STRING(36) NOT NULL,
  cleanup_at TIMESTAMP NOT NULL,
) PRIMARY KEY (environment, job_id, attempt_id);

CREATE INDEX PrivacyExportObjectsByCleanup ON PrivacyExportObjects(environment, cleanup_at);
