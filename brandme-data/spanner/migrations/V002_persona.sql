-- V002 persona (owner: opus-consumer-domains lane)
-- Chapter 03 §4 "Identity and persona"; chapter 01 §4 Looking Glass.
--
-- Twelve independent axis rows per member (not two legacy columns). Declared,
-- inferred and effective state are stored separately; NULL means
-- unknown/unanswered, never a fabricated neutral 50.
--
-- Depends on V001 (members). No foreign key to Members is declared yet because
-- V001 had not been published when this file was written; member_id is the
-- internal UUID from V001. See lane status file, proposed deviation PD-02.

CREATE TABLE PersonaProfiles (
  member_id STRING(36) NOT NULL,
  schema_version INT64 NOT NULL,
  version INT64 NOT NULL,
  learning_enabled BOOL NOT NULL,
  social_signals_enabled BOOL NOT NULL,
  prefer_owned BOOL NOT NULL,
  budget_ceiling_minor INT64,
  budget_currency STRING(3),
  excluded_brands ARRAY<STRING(120)>,
  excluded_materials ARRAY<STRING(120)>,
  excluded_categories ARRAY<STRING(60)>,
  goals ARRAY<STRING(60)>,
  onboarding_intent STRING(60),
  inference_model_version STRING(64),
  inferred_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id);

-- One row per (member, axis). declared_revision is the profile version at which
-- the declared value / lock last changed; it drives mergeable-conflict guidance.
CREATE TABLE PersonaAxes (
  member_id STRING(36) NOT NULL,
  axis_key STRING(32) NOT NULL,
  declared_value INT64,
  locked BOOL NOT NULL,
  adapt_enabled BOOL NOT NULL,
  adapt_first_accepted BOOL NOT NULL,
  adapt_last_applied_at TIMESTAMP,
  inference_allowed BOOL NOT NULL,
  hidden BOOL NOT NULL,
  declared_revision INT64 NOT NULL,
  inferred_value INT64,
  inferred_confidence FLOAT64,
  inferred_evidence_count INT64 NOT NULL,
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_axis_declared_range CHECK (declared_value IS NULL OR (declared_value >= 0 AND declared_value <= 100)),
  CONSTRAINT ck_axis_inferred_range CHECK (inferred_value IS NULL OR (inferred_value >= 0 AND inferred_value <= 100)),
) PRIMARY KEY (member_id, axis_key),
  INTERLEAVE IN PARENT PersonaProfiles ON DELETE CASCADE;

-- Evidence with lineage. source_fingerprint identifies the underlying observation
-- so a suppression rule can block re-ingestion of the same observation.
CREATE TABLE PersonaEvidence (
  member_id STRING(36) NOT NULL,
  evidence_id STRING(36) NOT NULL,
  source_type STRING(40) NOT NULL,
  source_ref STRING(256) NOT NULL,
  source_fingerprint STRING(64) NOT NULL,
  purpose STRING(40) NOT NULL,
  consent_id STRING(36),
  axis_contributions JSON NOT NULL,
  weight FLOAT64 NOT NULL,
  model_version STRING(64) NOT NULL,
  observed_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP,
  suppression_state STRING(16) NOT NULL,
  suppressed_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, evidence_id),
  INTERLEAVE IN PARENT PersonaProfiles ON DELETE CASCADE;

CREATE UNIQUE INDEX PersonaEvidenceByFingerprint
  ON PersonaEvidence (member_id, source_fingerprint),
  INTERLEAVE IN PersonaProfiles;

-- Suppression rules outlive the evidence rows they were created from.
CREATE TABLE PersonaSuppressions (
  member_id STRING(36) NOT NULL,
  source_fingerprint STRING(64) NOT NULL,
  reason STRING(40) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, source_fingerprint),
  INTERLEAVE IN PARENT PersonaProfiles ON DELETE CASCADE;

CREATE TABLE PersonaContextOverrides (
  member_id STRING(36) NOT NULL,
  override_id STRING(36) NOT NULL,
  label STRING(120) NOT NULL,
  axes JSON NOT NULL,
  starts_at TIMESTAMP NOT NULL,
  ends_at TIMESTAMP NOT NULL,
  enabled BOOL NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, override_id),
  INTERLEAVE IN PARENT PersonaProfiles ON DELETE CASCADE;

CREATE TABLE PersonaSnapshots (
  member_id STRING(36) NOT NULL,
  snapshot_id STRING(36) NOT NULL,
  profile_version INT64 NOT NULL,
  saved_name STRING(80) NOT NULL,
  axes_snapshot JSON NOT NULL,
  redacted_summary STRING(400) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, snapshot_id),
  INTERLEAVE IN PARENT PersonaProfiles ON DELETE CASCADE;

-- Recommendation feedback (purpose-limited evidence input for the recommender's
-- feedback-affinity feature).
CREATE TABLE RecommendationFeedback (
  member_id STRING(36) NOT NULL,
  feedback_id STRING(36) NOT NULL,
  product_id STRING(36) NOT NULL,
  category STRING(60) NOT NULL,
  signal STRING(16) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, feedback_id),
  INTERLEAVE IN PARENT PersonaProfiles ON DELETE CASCADE;

-- Guest-to-account migration ledger: one row per (member, guest namespace).
CREATE TABLE GuestMigrations (
  member_id STRING(36) NOT NULL,
  guest_namespace_id STRING(64) NOT NULL,
  payload_digest STRING(64) NOT NULL,
  migrated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, guest_namespace_id);

CREATE UNIQUE INDEX GuestMigrationsByNamespace ON GuestMigrations (guest_namespace_id);

-- Deletion tombstone: an in-flight inference job cannot recreate a deleted
-- profile (ch.06 §4 "Account deletion races a queued inference job").
CREATE TABLE PersonaTombstones (
  member_id STRING(36) NOT NULL,
  deleted_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id);
