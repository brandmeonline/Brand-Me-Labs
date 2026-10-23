-- V004 social: relationships, blocks, five-minute decisions, shares and
-- in-app notifications (owner: opus-consumer-domains lane).
-- Chapter 01 §6/§8; chapter 03 §4 "Catalog, wardrobe and social".
--
-- Relationships are stored as two mirrored rows (one per member) written in
-- one transaction, so each side can list its own circle privately. Friend
-- lists are never public. Blocks are directional rows; either direction
-- blocks interaction.

CREATE TABLE Relationships (
  member_id STRING(36) NOT NULL,
  other_member_id STRING(36) NOT NULL,
  relationship_id STRING(36) NOT NULL,
  state STRING(16) NOT NULL,
  requested_by STRING(36) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  accepted_at TIMESTAMP OPTIONS (allow_commit_timestamp = true),
  version INT64 NOT NULL,
  CONSTRAINT ck_rel_state CHECK (state IN ('requested_out', 'requested_in', 'accepted')),
  CONSTRAINT ck_rel_self CHECK (member_id != other_member_id),
) PRIMARY KEY (member_id, other_member_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE INDEX RelationshipsById ON Relationships (relationship_id);

CREATE TABLE MemberBlocks (
  member_id STRING(36) NOT NULL,
  blocked_member_id STRING(36) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_block_self CHECK (member_id != blocked_member_id),
) PRIMARY KEY (member_id, blocked_member_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE INDEX MemberBlocksByBlocked ON MemberBlocks (blocked_member_id, member_id);

-- opened_at / closes_at are server times (Spanner CURRENT_TIMESTAMP in the
-- opening transaction); clients only display the remaining interval.
CREATE TABLE Decisions (
  member_id STRING(36) NOT NULL,
  decision_id STRING(36) NOT NULL,
  subject_type STRING(24) NOT NULL,
  subject_id STRING(36) NOT NULL,
  prompt STRING(280) NOT NULL,
  discussion_mode STRING(24) NOT NULL,
  duration_seconds INT64 NOT NULL,
  state STRING(16) NOT NULL,
  created_by_actor STRING(256) NOT NULL,
  request_fingerprint STRING(64) NOT NULL,
  repeat_of STRING(36),
  opened_at TIMESTAMP,
  closes_at TIMESTAMP,
  closed_at TIMESTAMP,
  close_reason STRING(16),
  yes_count INT64 NOT NULL,
  pass_count INT64 NOT NULL,
  alternative_count INT64 NOT NULL,
  requester_outcome STRING(16),
  version INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_dec_state CHECK (state IN ('draft', 'open', 'closed', 'cancelled')),
  CONSTRAINT ck_dec_subject CHECK (subject_type IN ('wardrobe_item', 'catalog_product', 'outfit_version')),
  CONSTRAINT ck_dec_mode CHECK (discussion_mode IN ('blind_until_response', 'open')),
  CONSTRAINT ck_dec_duration CHECK (duration_seconds = 300),
  CONSTRAINT ck_dec_outcome CHECK (requester_outcome IS NULL OR requester_outcome IN ('bought', 'saved', 'passed', 'still_deciding')),
) PRIMARY KEY (member_id, decision_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE UNIQUE INDEX DecisionsById ON Decisions (decision_id);
CREATE INDEX DecisionsByStateClose ON Decisions (state, closes_at);
CREATE INDEX DecisionsByCreatorFingerprint ON Decisions (member_id, request_fingerprint, created_at DESC), INTERLEAVE IN Members;

-- Audience snapshot; one invitation per recipient per request (primary key).
CREATE TABLE DecisionAudience (
  member_id STRING(36) NOT NULL,
  decision_id STRING(36) NOT NULL,
  recipient_id STRING(36) NOT NULL,
  closes_at TIMESTAMP,
  removed BOOL NOT NULL,
) PRIMARY KEY (member_id, decision_id, recipient_id),
  INTERLEAVE IN PARENT Decisions ON DELETE CASCADE;

CREATE INDEX DecisionAudienceByRecipient ON DecisionAudience (recipient_id, closes_at DESC);

-- One response record per respondent/decision (primary key). submitted_at is
-- the server time read inside the responding transaction.
CREATE TABLE DecisionResponses (
  member_id STRING(36) NOT NULL,
  decision_id STRING(36) NOT NULL,
  respondent_id STRING(36) NOT NULL,
  choice STRING(16) NOT NULL,
  alternative_ref STRING(36),
  note STRING(500),
  revision INT64 NOT NULL,
  first_submitted_at TIMESTAMP NOT NULL,
  submitted_at TIMESTAMP NOT NULL,
  committed_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  eligible BOOL,
  CONSTRAINT ck_resp_choice CHECK (choice IN ('yes', 'pass', 'alternative')),
  CONSTRAINT ck_resp_alt CHECK ((choice = 'alternative') = (alternative_ref IS NOT NULL)),
) PRIMARY KEY (member_id, decision_id, respondent_id),
  INTERLEAVE IN PARENT Decisions ON DELETE CASCADE;

CREATE INDEX DecisionResponsesByRespondent ON DecisionResponses (respondent_id, submitted_at DESC);

-- Revocable, least-disclosure shares. Only a hash of the opaque token is kept.
-- subject_version pins the outfit version / snapshot profile version shared.
CREATE TABLE ShareGrants (
  member_id STRING(36) NOT NULL,
  share_id STRING(36) NOT NULL,
  subject_type STRING(24) NOT NULL,
  subject_id STRING(36) NOT NULL,
  subject_version INT64,
  audience STRING(24) NOT NULL,
  allowed_fields ARRAY<STRING(64)> NOT NULL,
  recipient_ids ARRAY<STRING(36)>,
  token_hash STRING(64) NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  revoked_at TIMESTAMP,
  version INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_share_audience CHECK (audience IN ('selected_members', 'unlisted', 'public')),
  CONSTRAINT ck_share_subject CHECK (subject_type IN ('outfit_version', 'wardrobe_item', 'persona_snapshot')),
) PRIMARY KEY (member_id, share_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE UNIQUE INDEX ShareGrantsByToken ON ShareGrants (token_hash);
CREATE UNIQUE INDEX ShareGrantsById ON ShareGrants (share_id);

-- The controlled preview cache: the filtered copy rendered at share time.
-- Revocation deletes it in the same transaction as revoked_at is set.
CREATE TABLE SharePreviews (
  member_id STRING(36) NOT NULL,
  share_id STRING(36) NOT NULL,
  preview JSON NOT NULL,
  rendered_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, share_id),
  INTERLEAVE IN PARENT ShareGrants ON DELETE CASCADE;

-- In-app notifications, deduplicated by (recipient, event, type).
CREATE TABLE Notifications (
  member_id STRING(36) NOT NULL,
  notification_id STRING(36) NOT NULL,
  event_id STRING(36) NOT NULL,
  type STRING(48) NOT NULL,
  actor_member_id STRING(36),
  subject_ref STRING(80),
  sanitized_payload JSON NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  read_at TIMESTAMP OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, notification_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE UNIQUE INDEX NotificationsByEvent ON Notifications (member_id, event_id, type), INTERLEAVE IN Members;
CREATE INDEX NotificationsByCreated ON Notifications (member_id, created_at DESC), INTERLEAVE IN Members;
