-- V016 consumer design alignment (lane: opus-consumer-domains; Ultra plan 02 items 2-7).
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
ALTER TABLE MemberReports ADD CONSTRAINT ck_mr_target_v2 CHECK (target_type IN ('decision_response', 'decision_comment', 'room_post', 'share', 'outfit_proposal', 'member'));

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

-- Daily-capped surveys and quizzes (item 5). Operator-authored; answers stay in the member's own data.
CREATE TABLE Surveys (
  survey_id STRING(36) NOT NULL,
  kind STRING(8) NOT NULL,
  purpose STRING(24) NOT NULL,
  title STRING(120) NOT NULL,
  questions JSON NOT NULL,
  active BOOL NOT NULL,
  available_until TIMESTAMP,
  created_by STRING(64) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  version INT64 NOT NULL,
  CONSTRAINT ck_sv_kind CHECK (kind IN ('survey', 'quiz')),
  CONSTRAINT ck_sv_purpose CHECK (purpose IN ('style', 'product_feedback', 'house_knowledge')),
) PRIMARY KEY (survey_id);

CREATE TABLE SurveyResponses (
  member_id STRING(36) NOT NULL,
  survey_id STRING(36) NOT NULL,
  answers JSON NOT NULL,
  score INT64,
  submitted_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, survey_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE INDEX SurveyResponsesBySurvey ON SurveyResponses (survey_id);

-- Points convert to in-app purchase credit only: never cash, never transferable.
-- The points stay reserved while the credit is outstanding, are spent when it is
-- applied to an in-app order, and return to the member if it expires.
CREATE TABLE PurchaseCredits (
  member_id STRING(36) NOT NULL,
  credit_id STRING(36) NOT NULL,
  points INT64 NOT NULL,
  amount_minor INT64 NOT NULL,
  currency STRING(3) NOT NULL,
  state STRING(12) NOT NULL,
  applied_ref STRING(120),
  expires_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  settled_at TIMESTAMP OPTIONS (allow_commit_timestamp = true),
  version INT64 NOT NULL,
  CONSTRAINT ck_pc_state CHECK (state IN ('available', 'applied', 'expired')),
  CONSTRAINT ck_pc_amount CHECK (points > 0 AND amount_minor > 0),
  CONSTRAINT ck_pc_applied CHECK ((state = 'applied') = (applied_ref IS NOT NULL)),
) PRIMARY KEY (member_id, credit_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE INDEX PurchaseCreditsByExpiry ON PurchaseCredits (state, expires_at);

-- Per-piece closet visibility (item 6): owner-curated, private (NULL) by default.
-- Strangers ("members") see at most the story; price ("full") is for friends only.
ALTER TABLE WardrobeItems ADD COLUMN visibility STRING(12);
ALTER TABLE WardrobeItems ADD COLUMN visible_detail STRING(8);
ALTER TABLE WardrobeItems ADD COLUMN showcase_note STRING(280);
ALTER TABLE WardrobeItems ADD CONSTRAINT ck_wi_visibility CHECK (
  (visibility IS NULL AND visible_detail IS NULL)
  OR (visibility = 'friends' AND visible_detail IN ('piece', 'story', 'full'))
  OR (visibility = 'members' AND visible_detail IN ('piece', 'story')));

-- The living persona card (item 6), recomposed on trigger events and backfilled daily.
CREATE TABLE PersonaCards (
  member_id STRING(36) NOT NULL,
  audience STRING(12) NOT NULL,
  show_standings BOOL NOT NULL,
  highlight_item_ids ARRAY<STRING(36)>,
  card JSON,
  composed_at TIMESTAMP,
  stale_since TIMESTAMP,
  last_trigger STRING(40),
  version INT64 NOT NULL,
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_pcard_audience CHECK (audience IN ('private', 'friends', 'members')),
  CONSTRAINT ck_pcard_highlights CHECK (highlight_item_ids IS NULL OR ARRAY_LENGTH(highlight_item_ids) <= 6),
) PRIMARY KEY (member_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE INDEX PersonaCardsByStale ON PersonaCards (stale_since);

-- Small-group rooms (item 7): invite-only, friends of the owner, at most 12 people.
CREATE TABLE Rooms (
  room_id STRING(36) NOT NULL,
  owner_id STRING(36) NOT NULL,
  title STRING(80) NOT NULL,
  purpose STRING(200),
  state STRING(12) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  version INT64 NOT NULL,
  CONSTRAINT ck_room_state CHECK (state IN ('open', 'archived')),
) PRIMARY KEY (room_id);

CREATE INDEX RoomsByOwner ON Rooms (owner_id, state);

CREATE TABLE RoomMembers (
  room_id STRING(36) NOT NULL,
  member_id STRING(36) NOT NULL,
  role STRING(8) NOT NULL,
  added_by STRING(36) NOT NULL,
  joined_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_rm_role CHECK (role IN ('owner', 'member')),
) PRIMARY KEY (room_id, member_id),
  INTERLEAVE IN PARENT Rooms ON DELETE CASCADE;

CREATE INDEX RoomMembersByMember ON RoomMembers (member_id);

CREATE TABLE RoomPosts (
  room_id STRING(36) NOT NULL,
  post_id STRING(36) NOT NULL,
  author_id STRING(36) NOT NULL,
  kind STRING(8) NOT NULL,
  body STRING(1000),
  subject_type STRING(24),
  subject_id STRING(36),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  removed_at TIMESTAMP,
  removed_reason STRING(24),
  CONSTRAINT ck_rp_kind CHECK (kind IN ('note', 'piece')),
  CONSTRAINT ck_rp_subject CHECK ((kind = 'piece') = (subject_id IS NOT NULL)),
  CONSTRAINT ck_rp_removed CHECK ((removed_at IS NULL) = (removed_reason IS NULL)),
) PRIMARY KEY (room_id, post_id),
  INTERLEAVE IN PARENT Rooms ON DELETE CASCADE;

CREATE INDEX RoomPostsByAuthor ON RoomPosts (author_id, created_at);

CREATE TABLE RoomReactions (
  room_id STRING(36) NOT NULL,
  post_id STRING(36) NOT NULL,
  member_id STRING(36) NOT NULL,
  reaction STRING(8) NOT NULL,
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_rr_reaction CHECK (reaction IN ('yes', 'maybe', 'no')),
) PRIMARY KEY (room_id, post_id, member_id),
  INTERLEAVE IN PARENT RoomPosts ON DELETE CASCADE;

CREATE INDEX RoomReactionsByMember ON RoomReactions (member_id);
