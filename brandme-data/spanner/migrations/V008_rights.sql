-- V008_rights.sql — Midnight rights projections, chain operations, reprint workflow (W09)
-- Owner: opus-midnight-rights lane. GoogleSQL (Cloud Spanner). Verified on emulator 1.5.45.
--
-- Direction of evidence: chain observation → these projections. Nothing in these
-- tables can make a contract state valid. Personal data is not stored here: subject
-- references are opaque app ids; chain fields are the public commitments/ids.

-- Persisted operations (mirror of brandme-chain/src/midnight/operations.ts).
CREATE TABLE ChainOperations (
  operation_id STRING(36) NOT NULL,
  network STRING(16) NOT NULL,                 -- undeployed | preview | preprod | mainnet
  contract_address STRING(128) NOT NULL,
  circuit STRING(64) NOT NULL,
  args_json JSON NOT NULL,                     -- encoded circuit args (hex/decimal), no personal data
  request_digest STRING(64) NOT NULL,
  subject_ref STRING(128),
  idempotency_key STRING(128) NOT NULL,
  expires_at TIMESTAMP,
  state STRING(24) NOT NULL,
  version INT64 NOT NULL,
  failure_reason STRING(64),
  tx_id STRING(256),
  tx_hash STRING(128),
  block_height INT64,
  block_hash STRING(128),
  chain_status STRING(24),
  finalized_head_height INT64,
  history_json JSON NOT NULL,
  next_check_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT ck_chainop_state CHECK (state IN ('Draft','AwaitingRecipient','ReadyToProve','Proving','Submitted','Reconciling',
    'Observed','Finalized','Failed','Cancelled','Expired','HandoverPending','HandoverAcknowledged')),
  CONSTRAINT ck_chainop_network CHECK (network IN ('undeployed','preview','preprod','mainnet')),
) PRIMARY KEY (operation_id);

CREATE UNIQUE INDEX ChainOperationsByIdempotencyKey ON ChainOperations(idempotency_key);
-- "chain operations by network/state/next check" (ch.03 indexes)
CREATE INDEX ChainOperationsByNetworkState ON ChainOperations(network, state, next_check_at);
CREATE INDEX ChainOperationsBySubject ON ChainOperations(network, subject_ref, state);

-- Issuer registry projection (governance-registered issuers).
CREATE TABLE RightsIssuers (
  network STRING(16) NOT NULL,
  contract_address STRING(128) NOT NULL,
  issuer_id STRING(64) NOT NULL,               -- hex, random on-chain id
  brand_ref STRING(128),                        -- app-side brand/partner reference
  policy_version INT64 NOT NULL,
  max_issuance INT64 NOT NULL,
  issued INT64 NOT NULL,
  valid_until TIMESTAMP NOT NULL,
  active BOOL NOT NULL,
  last_tx_id STRING(256) NOT NULL,
  observed_at TIMESTAMP NOT NULL,
) PRIMARY KEY (network, contract_address, issuer_id);

-- Entitlement projection. controller_subject_ref is app-side and private:
-- it is set only when the controlling member's own client reports it after a
-- finalized operation, and is never published.
CREATE TABLE RightsEntitlements (
  network STRING(16) NOT NULL,
  contract_address STRING(128) NOT NULL,
  entitlement_id STRING(64) NOT NULL,
  asset_id STRING(36),
  issuer_id STRING(64) NOT NULL,
  epoch INT64 NOT NULL,
  status STRING(16) NOT NULL,                  -- active | revoked
  transferable BOOL NOT NULL,
  reprintable BOOL NOT NULL,
  parent_consumption STRING(64),               -- nullifier for reprint children
  controller_subject_ref STRING(128),
  last_tx_id STRING(256) NOT NULL,
  last_block_height INT64 NOT NULL,
  finalized_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT ck_ent_status CHECK (status IN ('active','revoked')),
) PRIMARY KEY (network, contract_address, entitlement_id);

CREATE INDEX RightsEntitlementsByAsset ON RightsEntitlements(asset_id);
CREATE INDEX RightsEntitlementsByController ON RightsEntitlements(controller_subject_ref);

-- Transfer intents (ch.03 TransferIntent; app workflow around offer/accept).
CREATE TABLE TransferIntents (
  intent_id STRING(36) NOT NULL,
  network STRING(16) NOT NULL,
  entitlement_id STRING(64) NOT NULL,
  from_subject_ref STRING(128) NOT NULL,
  recipient_commitment STRING(64),
  rights_scope_json JSON NOT NULL,
  expected_epoch INT64 NOT NULL,
  offer_id STRING(64),
  offer_operation_id STRING(36),
  accept_operation_id STRING(36),
  state STRING(24) NOT NULL,
  physical_handover STRING(24) NOT NULL DEFAULT ('not_applicable'),
  expires_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (intent_id);

CREATE INDEX TransferIntentsByEntitlement ON TransferIntents(network, entitlement_id, state);

-- License grants (ch.03 LicenseGrant).
CREATE TABLE LicenseGrants (
  license_id STRING(36) NOT NULL,
  network STRING(16) NOT NULL,
  entitlement_id STRING(64) NOT NULL,
  issuer_id STRING(64) NOT NULL,
  permissions ARRAY<STRING(32)> NOT NULL,      -- display | transfer | personal_manufacture | repair_parts | commercial_reproduction
  territory ARRAY<STRING(8)>,
  allowance_id STRING(64),
  quota_granted INT64,
  valid_until TIMESTAMP,
  revocation_policy STRING(64),
  created_at TIMESTAMP NOT NULL,
) PRIMARY KEY (license_id);

-- Manufacturer capability registry (who may produce what, where).
CREATE TABLE ManufacturerCapabilities (
  manufacturer_id STRING(64) NOT NULL,         -- on-chain manufacturer id (hex)
  issuer_id STRING(64) NOT NULL,
  display_name STRING(256) NOT NULL,
  processes ARRAY<STRING(64)> NOT NULL,
  territories ARRAY<STRING(8)> NOT NULL,
  materials ARRAY<STRING(64)>,
  active BOOL NOT NULL,
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (manufacturer_id);

-- Reprint jobs (ch.04 §7). Payment state is separate from rights state.
CREATE TABLE ReprintJobs (
  job_id STRING(36) NOT NULL,
  network STRING(16) NOT NULL,
  allowance_id STRING(64) NOT NULL,
  entitlement_id STRING(64) NOT NULL,
  manufacturer_id STRING(64) NOT NULL,
  member_subject_ref STRING(128) NOT NULL,
  job_commitment STRING(64) NOT NULL,          -- blinded; nullifier = H(allowance, job_commitment)
  quantity INT64 NOT NULL,
  state STRING(24) NOT NULL,
  payment_state STRING(24) NOT NULL DEFAULT ('none'),
  quote_json JSON,
  consumption_nullifier STRING(64),
  consume_operation_id STRING(36),
  units_attested INT64 NOT NULL DEFAULT (0),
  replacement_allowance_id STRING(64),
  version INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT ck_reprint_qty CHECK (quantity > 0),
  CONSTRAINT ck_reprint_state CHECK (state IN ('eligibility_check','quoted','approved','reserved','rights_consuming','rights_consumed',
    'accepted','manufacturing','quality_review','shipped','delivered','cancel_requested','cancelled','failed','disputed')),
) PRIMARY KEY (job_id);

CREATE UNIQUE INDEX ReprintJobsByCommitment ON ReprintJobs(allowance_id, job_commitment);
CREATE INDEX ReprintJobsByMember ON ReprintJobs(member_subject_ref, created_at DESC);

-- Inbox for manufacturer callbacks: duplicate deliveries are recorded once.
CREATE TABLE ManufacturerCallbacks (
  manufacturer_id STRING(64) NOT NULL,
  callback_id STRING(128) NOT NULL,            -- provider-supplied idempotency id
  job_id STRING(36) NOT NULL,
  kind STRING(32) NOT NULL,                    -- accepted | unit_produced | quality | shipped | failed
  unit_index INT64,
  payload_digest STRING(64) NOT NULL,
  outcome STRING(32) NOT NULL,                 -- applied | duplicate | rejected
  received_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (manufacturer_id, callback_id);

-- Claim-level passport evidence (ch.04 §6). One row per claim; never collapsed into a single "verified".
CREATE TABLE PassportClaims (
  asset_id STRING(36) NOT NULL,
  claim_id STRING(36) NOT NULL,
  facet STRING(32) NOT NULL,                   -- product | provenance | ownership | social | esg | lifecycle | molecular
  claim_type STRING(48) NOT NULL,              -- product_identified | tag_verified | issuer_recognized | entitlement_controlled | ownership_claim_reviewed | lifecycle_attested | esg_claim
  assurance STRING(32) NOT NULL,               -- member_entered | merchant_receipt | static_identifier | secure_nfc | authorized_inspection | midnight_control_proof | manufacturer_attestation
  source STRING(256) NOT NULL,
  environment STRING(16) NOT NULL,             -- demo | development | sandbox | production
  network STRING(16),
  evidence_ref STRING(256),
  visibility STRING(16) NOT NULL,              -- public | owner | private
  value_json JSON,
  observed_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP,
  revoked_at TIMESTAMP,
) PRIMARY KEY (asset_id, claim_id);

CREATE INDEX PassportClaimsByFacet ON PassportClaims(asset_id, facet, visibility);
