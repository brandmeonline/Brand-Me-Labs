-- V005 rewards: append-only points ledger, reducer account, badges, benefit
-- inventory and reservations, member disputes (owner: opus-consumer-domains).
-- Chapter 01 §7; chapter 03 §4 "Trust, rewards and commerce";
-- contracts/reward-rules.json.
--
-- Points are nontransferable application credits. The account row is a
-- reducer over RewardEntries; nothing edits a balance except a ledger entry
-- written in the same transaction. Spendable points never go negative: a
-- reversal of already-spent points becomes a disclosed recovery_due amount.

CREATE TABLE RewardAccounts (
  member_id STRING(36) NOT NULL,
  available INT64 NOT NULL,
  reserved INT64 NOT NULL,
  gross_earned INT64 NOT NULL,
  reversed_total INT64 NOT NULL,
  spent_total INT64 NOT NULL,
  recovery_due INT64 NOT NULL,
  version INT64 NOT NULL,
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_ra_available CHECK (available >= 0),
  CONSTRAINT ck_ra_reserved CHECK (reserved >= 0),
  CONSTRAINT ck_ra_recovery CHECK (recovery_due >= 0),
  CONSTRAINT ck_ra_totals CHECK (gross_earned >= 0 AND reversed_total >= 0 AND spent_total >= 0),
) PRIMARY KEY (member_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

-- Append-only journal. Credits use a deterministic entry_id derived from the
-- cause key (member, rule, rule version, qualifying event), so a duplicate
-- cause collides on the primary key inside the settling transaction.
CREATE TABLE RewardEntries (
  member_id STRING(36) NOT NULL,
  entry_id STRING(36) NOT NULL,
  kind STRING(16) NOT NULL,
  state STRING(16) NOT NULL,
  rule_id STRING(48),
  rule_version INT64,
  cause_event_id STRING(64),
  qualifying_at TIMESTAMP,
  points INT64 NOT NULL,
  available_delta INT64 NOT NULL,
  reserved_delta INT64 NOT NULL,
  recovery_delta INT64 NOT NULL,
  outcome_reason STRING(48),
  reverses_entry_id STRING(36),
  reservation_id STRING(36),
  evidence_refs ARRAY<STRING(128)> NOT NULL,
  actor_ref STRING(256) NOT NULL,
  reason STRING(500),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_re_kind CHECK (kind IN ('credit', 'reversal', 'reserve', 'redeem', 'release', 'correction')),
  CONSTRAINT ck_re_state CHECK (state IN ('posted', 'capped', 'excluded')),
  CONSTRAINT ck_re_points CHECK (points >= 0),
  CONSTRAINT ck_re_credit CHECK (kind != 'credit' OR (rule_id IS NOT NULL AND rule_version IS NOT NULL AND cause_event_id IS NOT NULL AND qualifying_at IS NOT NULL)),
  CONSTRAINT ck_re_reversal CHECK (kind != 'reversal' OR reverses_entry_id IS NOT NULL),
) PRIMARY KEY (member_id, entry_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE UNIQUE NULL_FILTERED INDEX RewardEntriesByCause ON RewardEntries (member_id, rule_id, rule_version, cause_event_id), INTERLEAVE IN Members;
CREATE UNIQUE NULL_FILTERED INDEX RewardEntriesByReversal ON RewardEntries (member_id, reverses_entry_id), INTERLEAVE IN Members;
CREATE INDEX RewardEntriesByCreated ON RewardEntries (member_id, created_at DESC), INTERLEAVE IN Members;

-- Facts that complete multi-step rules (e.g. saved profile + first saved look).
CREATE TABLE RewardFacts (
  member_id STRING(36) NOT NULL,
  fact STRING(32) NOT NULL,
  event_id STRING(64) NOT NULL,
  occurred_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, fact),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE TABLE BadgeAwards (
  member_id STRING(36) NOT NULL,
  badge_id STRING(32) NOT NULL,
  criteria_version INT64 NOT NULL,
  evidence_refs ARRAY<STRING(128)> NOT NULL,
  awarded_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  revoked_at TIMESTAMP OPTIONS (allow_commit_timestamp = true),
  revoke_reason STRING(200),
) PRIMARY KEY (member_id, badge_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

-- Operator-defined benefits. Partner benefits must be funded to exist.
CREATE TABLE Benefits (
  benefit_id STRING(36) NOT NULL,
  kind STRING(24) NOT NULL,
  title STRING(120) NOT NULL,
  description STRING(500) NOT NULL,
  cost_points INT64 NOT NULL,
  inventory_total INT64 NOT NULL,
  inventory_reserved INT64 NOT NULL,
  inventory_fulfilled INT64 NOT NULL,
  funded BOOL NOT NULL,
  sponsor STRING(120),
  active BOOL NOT NULL,
  available_until TIMESTAMP,
  reservation_ttl_seconds INT64 NOT NULL,
  version INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_bf_kind CHECK (kind IN ('room_finish', 'composition_template', 'partner')),
  CONSTRAINT ck_bf_cost CHECK (cost_points > 0),
  CONSTRAINT ck_bf_inventory CHECK (inventory_reserved >= 0 AND inventory_fulfilled >= 0 AND inventory_reserved + inventory_fulfilled <= inventory_total),
  CONSTRAINT ck_bf_partner CHECK (kind != 'partner' OR (funded AND sponsor IS NOT NULL)),
  CONSTRAINT ck_bf_ttl CHECK (reservation_ttl_seconds BETWEEN 60 AND 2592000),
) PRIMARY KEY (benefit_id);

CREATE TABLE BenefitReservations (
  member_id STRING(36) NOT NULL,
  reservation_id STRING(36) NOT NULL,
  benefit_id STRING(36) NOT NULL,
  cost_points INT64 NOT NULL,
  state STRING(16) NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  release_reason STRING(48),
  version INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  settled_at TIMESTAMP OPTIONS (allow_commit_timestamp = true),
  -- Fulfillment lease: a worker claims a pending reservation (server time)
  -- before calling an external fulfiller, so overlapping schedulers cannot both
  -- deliver it and the expiry sweeper cannot release it mid-delivery.
  claim_token STRING(36),
  claimed_until TIMESTAMP,
  CONSTRAINT ck_br_state CHECK (state IN ('pending', 'fulfilled', 'refunded')),
  CONSTRAINT ck_br_cost CHECK (cost_points > 0),
) PRIMARY KEY (member_id, reservation_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE UNIQUE INDEX BenefitReservationsById ON BenefitReservations (reservation_id);
CREATE INDEX BenefitReservationsByStateExpiry ON BenefitReservations (state, expires_at);

-- Member disputes ("audit and member dispute available"); operators resolve
-- them in the console with a reasoned ledger correction or no change.
CREATE TABLE RewardDisputes (
  member_id STRING(36) NOT NULL,
  dispute_id STRING(36) NOT NULL,
  entry_id STRING(36),
  category STRING(24) NOT NULL,
  message STRING(1000) NOT NULL,
  state STRING(24) NOT NULL,
  resolution_note STRING(1000),
  resolved_by STRING(256),
  correction_entry_id STRING(36),
  version INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  resolved_at TIMESTAMP OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_rd_category CHECK (category IN ('missing_reward', 'wrong_amount', 'reversal', 'reservation', 'other')),
  CONSTRAINT ck_rd_state CHECK (state IN ('open', 'resolved_correction', 'resolved_no_change', 'withdrawn')),
) PRIMARY KEY (member_id, dispute_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE UNIQUE INDEX RewardDisputesById ON RewardDisputes (dispute_id);
CREATE INDEX RewardDisputesByState ON RewardDisputes (state, created_at);
