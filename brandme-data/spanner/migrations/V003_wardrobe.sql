-- V003 wardrobe, closet placement, outfits, packing and try-on media
-- (owner: opus-consumer-domains lane). Chapter 03 §4 "Catalog, wardrobe and
-- social"; chapter 01 §5; chapter 02 §4.5 placement contract.
--
-- Three distinct things (ch.03 §4): a CatalogProduct (referenced by product_id,
-- owned by the providers lane), an AssetInstance (an attested physical item,
-- owned by the rights/cube lanes, referenced by asset_instance_id) and a
-- WardrobeItem (a member's relationship to a possession or aspiration). A
-- wishlist entry never implies ownership; an owned item may be self-declared.
--
-- Member-owned aggregates are interleaved in V001 Members (deleted with the
-- member). category is NULL only for provider-order units whose catalog
-- category is not yet known (never guessed). The try-on/media tables live here because the media domain has no
-- reserved migration number (proposed deviation PD-08).

CREATE TABLE WardrobeItems (
  member_id STRING(36) NOT NULL,
  item_id STRING(36) NOT NULL,
  product_id STRING(36),
  variant_ref STRING(256),
  asset_instance_id STRING(36),
  title STRING(200) NOT NULL,
  category STRING(16),
  collection STRING(16) NOT NULL,
  claim_level STRING(16) NOT NULL,
  evidence_status STRING(32) NOT NULL,
  acquisition_source STRING(16) NOT NULL,
  acquisition_status STRING(16) NOT NULL,
  source_ref STRING(256),
  receipt_line_ref STRING(256),
  unit_index INT64,
  tag_serial_hash STRING(64),
  color_family STRING(8),
  colors ARRAY<STRING(32)>,
  materials ARRAY<STRING(60)>,
  size_label STRING(40),
  item_condition STRING(16),
  care_state STRING(16) NOT NULL,
  care_notes STRING(1000),
  user_notes STRING(2000),
  worn_count INT64 NOT NULL,
  last_worn_at TIMESTAMP,
  price_minor INT64,
  price_currency STRING(3),
  price_is_estimate BOOL,
  duplicate_of STRING(36),
  pre_archive_collection STRING(16),
  version INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_wi_category CHECK (category IS NULL OR category IN ('top', 'bottom', 'dress', 'outerwear', 'shoes', 'accessory')),
  CONSTRAINT ck_wi_collection CHECK (collection IN ('owned', 'want', 'on_the_way', 'digital', 'archive')),
  CONSTRAINT ck_wi_claim CHECK (claim_level IN ('self_reported', 'receipt_backed', 'tag_verified', 'issuer_attested')),
  CONSTRAINT ck_wi_care CHECK (care_state IN ('clean', 'needs_care', 'at_cleaner', 'in_repair')),
  CONSTRAINT ck_wi_worn CHECK (worn_count >= 0),
  CONSTRAINT ck_wi_price CHECK (price_minor IS NULL OR price_minor >= 0),
  CONSTRAINT ck_wi_unit CHECK (unit_index IS NULL OR unit_index >= 0),
  CONSTRAINT ck_wi_version CHECK (version >= 1),
) PRIMARY KEY (member_id, item_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE INDEX WardrobeItemsByCollection
  ON WardrobeItems (member_id, collection, updated_at DESC),
  INTERLEAVE IN Members;

CREATE NULL_FILTERED INDEX WardrobeItemsByVariant
  ON WardrobeItems (member_id, product_id, variant_ref),
  INTERLEAVE IN Members;

CREATE NULL_FILTERED INDEX WardrobeItemsByReceiptLine
  ON WardrobeItems (member_id, receipt_line_ref, unit_index),
  INTERLEAVE IN Members;

-- Two physical items can never share a tag serial within one closet; this is
-- what stops silent merging (or silent duplication) of unique instances.
CREATE UNIQUE NULL_FILTERED INDEX WardrobeItemsByTagSerial
  ON WardrobeItems (member_id, tag_serial_hash),
  INTERLEAVE IN Members;

-- Provider order units: deterministic item per (order, variant, unit) so the
-- order reducer is idempotent; last applied order version for monotonicity.
CREATE TABLE WardrobeOrderLinks (
  member_id STRING(36) NOT NULL,
  order_id STRING(36) NOT NULL,
  last_order_version INT64 NOT NULL,
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, order_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE TABLE ClosetLayouts (
  member_id STRING(36) NOT NULL,
  layout_id STRING(36) NOT NULL,
  room_template_id STRING(32) NOT NULL,
  room_revision STRING(128) NOT NULL,
  version INT64 NOT NULL,
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_cl_room CHECK (room_template_id IN ('walnut_atelier', 'limestone_gallery', 'garden_studio')),
  CONSTRAINT ck_cl_version CHECK (version >= 1),
) PRIMARY KEY (member_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

-- semantic_group/slot_id NULL = the "Unplaced" tray (still accessible).
CREATE TABLE ClosetPlacements (
  member_id STRING(36) NOT NULL,
  item_id STRING(36) NOT NULL,
  layout_id STRING(36) NOT NULL,
  room_template_id STRING(32) NOT NULL,
  semantic_group STRING(32),
  slot_id STRING(64),
  pos_x FLOAT64,
  pos_y FLOAT64,
  pos_z FLOAT64,
  rot_x FLOAT64,
  rot_y FLOAT64,
  rot_z FLOAT64,
  rot_w FLOAT64,
  uniform_scale FLOAT64,
  asset_revision STRING(128) NOT NULL,
  version INT64 NOT NULL,
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_cp_scale CHECK (uniform_scale IS NULL OR (uniform_scale > 0 AND uniform_scale <= 10)),
  CONSTRAINT ck_cp_version CHECK (version >= 1),
) PRIMARY KEY (member_id, item_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

-- One item per (room, group, slot); unplaced rows are filtered out.
CREATE UNIQUE NULL_FILTERED INDEX ClosetPlacementsBySlot
  ON ClosetPlacements (member_id, room_template_id, semantic_group, slot_id),
  INTERLEAVE IN Members;

CREATE TABLE Outfits (
  member_id STRING(36) NOT NULL,
  outfit_id STRING(36) NOT NULL,
  title STRING(120) NOT NULL,
  visibility STRING(16) NOT NULL,
  head_version INT64 NOT NULL,
  version INT64 NOT NULL,
  archived BOOL NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_of_visibility CHECK (visibility IN ('private', 'friends', 'selected', 'public')),
) PRIMARY KEY (member_id, outfit_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

-- Outfit ids are global; proposers address an outfit by id alone.
CREATE UNIQUE INDEX OutfitsByOutfitId ON Outfits (outfit_id);

-- Immutable versions; author may differ from owner (accepted friend proposal).
CREATE TABLE OutfitVersions (
  member_id STRING(36) NOT NULL,
  outfit_id STRING(36) NOT NULL,
  version_no INT64 NOT NULL,
  item_refs ARRAY<STRING(36)> NOT NULL,
  layer_order ARRAY<STRING(36)> NOT NULL,
  substitutes JSON,
  occasion STRING(60),
  notes STRING(1000),
  author_member_id STRING(36) NOT NULL,
  source_proposal_id STRING(36),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, outfit_id, version_no),
  INTERLEAVE IN PARENT Outfits ON DELETE CASCADE;

CREATE TABLE OutfitProposals (
  member_id STRING(36) NOT NULL,
  outfit_id STRING(36) NOT NULL,
  proposal_id STRING(36) NOT NULL,
  proposer_member_id STRING(36) NOT NULL,
  base_version INT64 NOT NULL,
  item_refs ARRAY<STRING(36)> NOT NULL,
  layer_order ARRAY<STRING(36)> NOT NULL,
  notes STRING(1000),
  content_digest STRING(64) NOT NULL,
  state STRING(16) NOT NULL,
  accepted_version INT64,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  decided_at TIMESTAMP OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_op_state CHECK (state IN ('pending', 'accepted', 'declined', 'withdrawn')),
) PRIMARY KEY (member_id, outfit_id, proposal_id),
  INTERLEAVE IN PARENT Outfits ON DELETE CASCADE;

-- A proposer cannot submit the same content twice for one outfit.
CREATE UNIQUE INDEX OutfitProposalsByContent
  ON OutfitProposals (member_id, outfit_id, proposer_member_id, content_digest),
  INTERLEAVE IN Outfits;

CREATE INDEX OutfitProposalsByProposer ON OutfitProposals (proposer_member_id, created_at DESC);

CREATE TABLE PackingLists (
  member_id STRING(36) NOT NULL,
  list_id STRING(36) NOT NULL,
  title STRING(120) NOT NULL,
  starts_on DATE,
  ends_on DATE,
  version INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, list_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE TABLE PackingEntries (
  member_id STRING(36) NOT NULL,
  list_id STRING(36) NOT NULL,
  entry_id STRING(36) NOT NULL,
  outfit_id STRING(36),
  item_id STRING(36),
  quantity INT64 NOT NULL,
  state STRING(16) NOT NULL,
  CONSTRAINT ck_pe_state CHECK (state IN ('to_pack', 'packed', 'needs_care')),
  CONSTRAINT ck_pe_qty CHECK (quantity >= 1 AND quantity <= 99),
) PRIMARY KEY (member_id, list_id, entry_id),
  INTERLEAVE IN PARENT PackingLists ON DELETE CASCADE;

-- Try-on media (W08 server side). Raw frames are never stored. Unsaved inputs
-- and outputs expire (<= 24 h, ch.03 §8); saved media stays until deleted.
CREATE TABLE TryOnConsents (
  member_id STRING(36) NOT NULL,
  consent_id STRING(36) NOT NULL,
  mode STRING(24) NOT NULL,
  provider_id STRING(64),
  purposes ARRAY<STRING(40)> NOT NULL,
  granted_at TIMESTAMP NOT NULL,
  revoked_at TIMESTAMP,
  terms_version STRING(32) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, consent_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE TABLE TryOnJobs (
  member_id STRING(36) NOT NULL,
  job_id STRING(36) NOT NULL,
  mode STRING(24) NOT NULL,
  consent_id STRING(36) NOT NULL,
  item_id STRING(36),
  product_id STRING(36),
  provider_id STRING(64),
  provider_job_ref STRING(256),
  state STRING(24) NOT NULL,
  fidelity_label STRING(64) NOT NULL,
  input_media_ref STRING(256),
  output_media_ref STRING(256),
  saved BOOL NOT NULL,
  expires_at TIMESTAMP,
  error_code STRING(64),
  version INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_tj_mode CHECK (mode IN ('photo_preview', 'live_overlay', 'calibrated_fit')),
  CONSTRAINT ck_tj_state CHECK (state IN ('awaiting_upload', 'queued', 'processing', 'succeeded', 'failed', 'cancelled', 'expired', 'deleted', 'unavailable')),
) PRIMARY KEY (member_id, job_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE NULL_FILTERED INDEX TryOnJobsByExpiry ON TryOnJobs (expires_at, state);

-- App-owned media objects (originals + derivatives) with a deletion manifest.
CREATE TABLE MediaObjects (
  member_id STRING(36) NOT NULL,
  media_id STRING(36) NOT NULL,
  job_id STRING(36),
  kind STRING(24) NOT NULL,
  storage_ref STRING(512) NOT NULL,
  content_hash STRING(64),
  bytes INT64,
  saved BOOL NOT NULL,
  expires_at TIMESTAMP,
  deleted_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_mo_kind CHECK (kind IN ('tryon_input', 'tryon_output', 'tryon_derivative', 'wardrobe_photo')),
) PRIMARY KEY (member_id, media_id),
  INTERLEAVE IN PARENT Members ON DELETE CASCADE;

CREATE NULL_FILTERED INDEX MediaObjectsByExpiry ON MediaObjects (expires_at);
