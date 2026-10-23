-- V006_providers.sql — provider registry, capability evidence, setup, ingestion (lane: opus-commerce-agents)
-- GoogleSQL for Cloud Spanner. Validated against cloud-spanner-emulator 1.5.58 (see lane status file).
-- No foreign keys into V001–V005 (owned by opus-foundation); member/environment ids are STRING references.
-- Secrets are never stored here: credential_secret_ref is a Secret Manager resource name.

CREATE TABLE ProviderConnections (
  environment STRING(16) NOT NULL,
  provider_id STRING(80) NOT NULL,
  display_name STRING(120) NOT NULL,
  simulation BOOL NOT NULL,
  access_level STRING(40) NOT NULL,
  operator_account_ref STRING(256),
  credential_secret_ref STRING(512),
  credential_rotated_at TIMESTAMP,
  country_codes ARRAY<STRING(2)> NOT NULL,
  disclosure STRING(1200) NOT NULL,
  data_use JSON NOT NULL,
  allowed_redirect_hosts ARRAY<STRING(253)> NOT NULL,
  protocols JSON NOT NULL,
  version INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_provider_env CHECK (environment IN ('demo', 'development', 'sandbox', 'production')),
  CONSTRAINT ck_no_simulation_outside_dev CHECK (NOT simulation OR environment IN ('demo', 'development')),
) PRIMARY KEY (environment, provider_id);

CREATE TABLE ProviderCapabilities (
  environment STRING(16) NOT NULL,
  provider_id STRING(80) NOT NULL,
  capability STRING(40) NOT NULL,
  state STRING(16) NOT NULL,
  reason_code STRING(80) NOT NULL,
  last_checked_at TIMESTAMP,
  evidence_ref STRING(256),
  evidence_kind STRING(40),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_capability_state CHECK (state IN ('unconfigured', 'sandbox', 'verified', 'degraded', 'suspended', 'unsupported')),
  CONSTRAINT ck_verified_has_evidence CHECK (state != 'verified' OR (evidence_ref IS NOT NULL AND last_checked_at IS NOT NULL
    AND evidence_kind IN ('sandbox_operation', 'production_operation', 'conformance_suite'))),
) PRIMARY KEY (environment, provider_id, capability),
  INTERLEAVE IN PARENT ProviderConnections ON DELETE CASCADE;

CREATE TABLE ProviderSetupItems (
  environment STRING(16) NOT NULL,
  provider_id STRING(80) NOT NULL,
  item_key STRING(40) NOT NULL,
  section STRING(20) NOT NULL,
  done BOOL NOT NULL,
  evidence_ref STRING(256),
  recorded_by STRING(128),
  recorded_at TIMESTAMP OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_setup_section CHECK (section IN ('enables', 'prerequisites', 'credentials', 'data_use', 'tests', 'activation')),
) PRIMARY KEY (environment, provider_id, item_key),
  INTERLEAVE IN PARENT ProviderConnections ON DELETE CASCADE;

-- Verification history is retained independently of the connection row (audit).
CREATE TABLE ProviderVerificationRuns (
  run_id STRING(36) NOT NULL,
  environment STRING(16) NOT NULL,
  provider_id STRING(80) NOT NULL,
  capability STRING(40) NOT NULL,
  evidence_kind STRING(40) NOT NULL,
  evidence_ref STRING(256) NOT NULL,
  result STRING(16) NOT NULL,
  sanitized_summary STRING(2000),
  ran_by STRING(128) NOT NULL,
  ran_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_verification_result CHECK (result IN ('passed', 'failed', 'blocked')),
) PRIMARY KEY (run_id);

CREATE INDEX ProviderVerificationRunsByProvider ON ProviderVerificationRuns (environment, provider_id, capability, ran_at DESC);

CREATE TABLE CatalogSourceVariants (
  provider_id STRING(80) NOT NULL,
  merchant_id STRING(256) NOT NULL,
  source_product_id STRING(256) NOT NULL,
  source_variant_id STRING(256) NOT NULL,
  variant_id STRING(36) NOT NULL,
  brand STRING(200),
  title STRING(500) NOT NULL,
  category STRING(80),
  size_system STRING(40),
  size_label STRING(40),
  color STRING(80),
  gtin STRING(14),
  product_url STRING(2048) NOT NULL,
  image_urls ARRAY<STRING(2048)>,
  observed_price_minor INT64,
  observed_price_currency STRING(3),
  availability STRING(20) NOT NULL,
  source_updated_at TIMESTAMP NOT NULL,
  rights_policy_ref STRING(256) NOT NULL,
  revision INT64 NOT NULL,
  tombstoned BOOL NOT NULL,
  first_seen_at TIMESTAMP NOT NULL,
  last_ingested_at TIMESTAMP NOT NULL,
  CONSTRAINT ck_variant_price CHECK (observed_price_minor IS NULL OR observed_price_minor > 0),
  CONSTRAINT ck_variant_https CHECK (STARTS_WITH(product_url, 'https://')),
  CONSTRAINT ck_variant_availability CHECK (availability IN ('in_stock', 'out_of_stock', 'unknown', 'discontinued')),
) PRIMARY KEY (provider_id, merchant_id, source_product_id, source_variant_id);

CREATE UNIQUE INDEX CatalogSourceVariantsByVariantId ON CatalogSourceVariants (variant_id);
CREATE INDEX CatalogSourceVariantsByProduct ON CatalogSourceVariants (provider_id, source_product_id, tombstoned);

CREATE TABLE IngestionCursors (
  environment STRING(16) NOT NULL,
  provider_id STRING(80) NOT NULL,
  feed_ref STRING(256) NOT NULL,
  cursor_value STRING(2048),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (environment, provider_id, feed_ref);

CREATE TABLE IngestionRuns (
  run_id STRING(36) NOT NULL,
  environment STRING(16) NOT NULL,
  provider_id STRING(80) NOT NULL,
  accepted INT64 NOT NULL,
  unchanged INT64 NOT NULL,
  rejected INT64 NOT NULL,
  tombstoned INT64 NOT NULL,
  rejection_sample JSON,
  final_cursor STRING(2048),
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP,
) PRIMARY KEY (run_id);

CREATE INDEX IngestionRunsByProvider ON IngestionRuns (environment, provider_id, started_at DESC);

-- Webhook dedupe: uniqueness on (provider, event_id) per ch.03 §4.
CREATE TABLE ProviderWebhookReceipts (
  provider_id STRING(80) NOT NULL,
  event_id STRING(256) NOT NULL,
  event_type STRING(80) NOT NULL,
  received_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  state STRING(24) NOT NULL,
  CONSTRAINT ck_webhook_state CHECK (state IN ('applied', 'pending_reconcile', 'ignored')),
) PRIMARY KEY (provider_id, event_id);

CREATE INDEX ProviderWebhookReceiptsPending ON ProviderWebhookReceipts (state, received_at);
