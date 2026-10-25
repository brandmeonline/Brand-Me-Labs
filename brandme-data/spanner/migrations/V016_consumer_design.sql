-- V016 consumer design alignment, part 1 (lane: opus-consumer-domains; Ultra plan 02 items 2-4).
-- Additive except two CHECK constraints that are replaced to widen what they allow.

-- Now loop: asker-set windows around the five-minute default, and the asker's stated "why".
ALTER TABLE Decisions DROP CONSTRAINT ck_dec_duration;
ALTER TABLE Decisions ADD CONSTRAINT ck_dec_window CHECK (duration_seconds IN (180, 300, 600, 900));
ALTER TABLE Decisions ADD COLUMN why STRING(280);

-- In-window comment thread on a decision (creator and invited audience only).
CREATE TABLE DecisionComments (
  member_id STRING(36) NOT NULL,
  decision_id STRING(36) NOT NULL,
  comment_id STRING(36) NOT NULL,
  author_id STRING(36) NOT NULL,
  body STRING(500) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  removed_at TIMESTAMP,
  removed_reason STRING(24),
  CONSTRAINT ck_dc_removed CHECK ((removed_at IS NULL) = (removed_reason IS NULL)),
  CONSTRAINT ck_dc_reason CHECK (removed_reason IS NULL OR removed_reason IN ('author', 'moderation', 'privacy_deleted')),
) PRIMARY KEY (member_id, decision_id, comment_id),
  INTERLEAVE IN PARENT Decisions ON DELETE CASCADE;

CREATE INDEX DecisionCommentsByAuthor ON DecisionComments (author_id, created_at);

ALTER TABLE MemberReports DROP CONSTRAINT ck_mr_target;
ALTER TABLE MemberReports ADD CONSTRAINT ck_mr_target_v2 CHECK (target_type IN ('decision_response', 'decision_comment', 'share', 'outfit_proposal', 'member'));

-- Houses a member follows (Flow source) and whether they share their standing with that house.
CREATE TABLE MemberHouses (
  member_id STRING(36) NOT NULL,
  house_ref STRING(120) NOT NULL,
  share_standing BOOL NOT NULL,
  followed_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  version INT64 NOT NULL,
  CONSTRAINT ck_mh_version CHECK (version >= 1),
) PRIMARY KEY (member_id, house_ref),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE INDEX MemberHousesByHouse ON MemberHouses (house_ref, share_standing);

-- Per-house loyalty standing, recomputed by the jobs process from verified purchases.
-- Only the tier is stored; spend and counts are never persisted here.
CREATE TABLE HouseStandings (
  member_id STRING(36) NOT NULL,
  house_ref STRING(120) NOT NULL,
  tier STRING(16) NOT NULL,
  computed_at TIMESTAMP NOT NULL,
  run_id STRING(36) NOT NULL,
  CONSTRAINT ck_hs_tier CHECK (tier IN ('top_1', 'top_5', 'top_10', 'top_25', 'member')),
) PRIMARY KEY (member_id, house_ref),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE INDEX HouseStandingsByHouse ON HouseStandings (house_ref, tier);

-- House rewards gated by standing (exclusive drops, events, gifts).
ALTER TABLE Benefits ADD COLUMN house_ref STRING(120);
ALTER TABLE Benefits ADD COLUMN min_standing STRING(16);
ALTER TABLE Benefits ADD CONSTRAINT ck_benefit_standing CHECK (
  (house_ref IS NULL AND min_standing IS NULL)
  OR (house_ref IS NOT NULL AND kind = 'partner' AND min_standing IN ('top_1', 'top_5', 'top_10', 'top_25', 'member')));

-- Flow excitement: recent platform engagement per catalog piece (Now decisions about it, want-list adds).
CREATE INDEX DecisionsBySubject ON Decisions (subject_type, subject_id, opened_at);
CREATE INDEX WardrobeItemsByProduct ON WardrobeItems (product_id, collection, created_at);
