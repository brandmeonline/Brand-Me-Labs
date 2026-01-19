-- ============================================
-- SPANNER GRAPH SCHEMA: Global Integrity Spine
-- Brand.Me v8 - Spanner + Firestore Architecture
-- ============================================

-- ============================================
-- NODE TABLES
-- ============================================

-- NODE: Users (Actors in the system)
CREATE TABLE Users (
  user_id STRING(36) NOT NULL,
  handle STRING(255) NOT NULL,
  display_name STRING(255),
  email STRING(255),
  did_cardano STRING(255),
  region_code STRING(50) DEFAULT ('us-east1'),
  locale STRING(10) DEFAULT ('en-US'),
  trust_score FLOAT64 DEFAULT (0.5),
  persona_warm_cold FLOAT64,
  persona_sport_couture FLOAT64,
  consent_version STRING(36) DEFAULT ('consent_v1'),
  oauth_provider STRING(50),
  oauth_provider_id STRING(255),
  is_active BOOL DEFAULT (true),
  is_verified BOOL DEFAULT (false),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  updated_at TIMESTAMP OPTIONS (allow_commit_timestamp=true),
  last_login_at TIMESTAMP
) PRIMARY KEY (user_id);

-- Indexes for Users
CREATE UNIQUE INDEX UsersByHandle ON Users(handle);
CREATE INDEX UsersByEmail ON Users(email) WHERE email IS NOT NULL;
CREATE INDEX UsersByDidCardano ON Users(did_cardano) WHERE did_cardano IS NOT NULL;
CREATE INDEX UsersByRegion ON Users(region_code);
CREATE INDEX UsersActive ON Users(is_active) WHERE is_active = true;

-- NODE: Assets (Garments/Cubes)
CREATE TABLE Assets (
  asset_id STRING(36) NOT NULL,
  asset_type STRING(50) NOT NULL,
  display_name STRING(255),
  category STRING(100),
  description STRING(MAX),
  creator_user_id STRING(36) NOT NULL,
  current_owner_id STRING(36) NOT NULL,
  authenticity_hash STRING(64) NOT NULL,
  cardano_asset_ref STRING(255),
  midnight_asset_ref STRING(255),
  physical_tag_id STRING(255),
  physical_tag_type STRING(50),
  public_esg_score STRING(10),
  public_story_snippet STRING(500),
  is_authentic BOOL DEFAULT (true),
  is_active BOOL DEFAULT (true),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  updated_at TIMESTAMP OPTIONS (allow_commit_timestamp=true),
  first_minted_at TIMESTAMP,
  last_scanned_at TIMESTAMP,
  CONSTRAINT FK_Asset_Creator FOREIGN KEY (creator_user_id) REFERENCES Users(user_id),
  CONSTRAINT FK_Asset_Owner FOREIGN KEY (current_owner_id) REFERENCES Users(user_id)
) PRIMARY KEY (asset_id);

-- Indexes for Assets
CREATE INDEX AssetsByCreator ON Assets(creator_user_id);
CREATE INDEX AssetsByOwner ON Assets(current_owner_id);
CREATE INDEX AssetsByPhysicalTag ON Assets(physical_tag_id) WHERE physical_tag_id IS NOT NULL;
CREATE INDEX AssetsByCategory ON Assets(category) WHERE category IS NOT NULL;
CREATE INDEX AssetsByAuthHash ON Assets(authenticity_hash);
CREATE INDEX AssetsActive ON Assets(is_active) WHERE is_active = true;

-- ============================================
-- EDGE TABLES: Relationships for O(1) traversal
-- ============================================

-- EDGE: OWNS (User -> Asset) - Current and historical ownership
CREATE TABLE Owns (
  owner_id STRING(36) NOT NULL,
  asset_id STRING(36) NOT NULL,
  acquired_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  transfer_method STRING(50),
  price FLOAT64,
  currency STRING(10) DEFAULT ('USD'),
  blockchain_tx_hash STRING(255),
  midnight_tx_hash STRING(255),
  is_current BOOL DEFAULT (true),
  ended_at TIMESTAMP,
  CONSTRAINT FK_Owns_Owner FOREIGN KEY (owner_id) REFERENCES Users(user_id),
  CONSTRAINT FK_Owns_Asset FOREIGN KEY (asset_id) REFERENCES Assets(asset_id)
) PRIMARY KEY (owner_id, asset_id, acquired_at),
  INTERLEAVE IN PARENT Users ON DELETE CASCADE;

-- Index for finding current owner quickly
CREATE INDEX OwnsCurrent ON Owns(asset_id, is_current) WHERE is_current = true;
CREATE INDEX OwnsByAsset ON Owns(asset_id, acquired_at DESC);

-- EDGE: CREATED (User -> Asset) - Immutable creator relationship
CREATE TABLE Created (
  creator_id STRING(36) NOT NULL,
  asset_id STRING(36) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  creation_method STRING(50) DEFAULT ('manual'),
  blockchain_mint_tx STRING(255),
  CONSTRAINT FK_Created_Creator FOREIGN KEY (creator_id) REFERENCES Users(user_id),
  CONSTRAINT FK_Created_Asset FOREIGN KEY (asset_id) REFERENCES Assets(asset_id)
) PRIMARY KEY (creator_id, asset_id),
  INTERLEAVE IN PARENT Users ON DELETE CASCADE;

-- EDGE: FRIENDS_WITH (User <-> User) - Bidirectional friendship
CREATE TABLE FriendsWith (
  user_id_a STRING(36) NOT NULL,
  user_id_b STRING(36) NOT NULL,
  status STRING(20) DEFAULT ('pending'),
  initiated_by STRING(36),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  accepted_at TIMESTAMP,
  CONSTRAINT FK_Friends_A FOREIGN KEY (user_id_a) REFERENCES Users(user_id),
  CONSTRAINT FK_Friends_B FOREIGN KEY (user_id_b) REFERENCES Users(user_id),
  CONSTRAINT CHK_Friends_Order CHECK (user_id_a < user_id_b)
) PRIMARY KEY (user_id_a, user_id_b);

-- Index for finding friends of a user
CREATE INDEX FriendsByUserA ON FriendsWith(user_id_a, status);
CREATE INDEX FriendsByUserB ON FriendsWith(user_id_b, status);
CREATE INDEX FriendsAccepted ON FriendsWith(status) WHERE status = 'accepted';

-- ============================================
-- CONSENT GRAPH: Global Revocation Support
-- ============================================

-- Consent Policies with hierarchical scope
CREATE TABLE ConsentPolicies (
  consent_id STRING(36) NOT NULL,
  user_id STRING(36) NOT NULL,
  scope STRING(50) NOT NULL,
  asset_id STRING(36),
  facet_type STRING(50),
  visibility STRING(20) NOT NULL,
  grantee_user_id STRING(36),
  grantee_type STRING(20) DEFAULT ('anyone'),
  region_code STRING(50),
  is_revoked BOOL DEFAULT (false),
  revoked_at TIMESTAMP,
  revocation_reason STRING(255),
  policy_version STRING(36) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  updated_at TIMESTAMP OPTIONS (allow_commit_timestamp=true),
  expires_at TIMESTAMP,
  CONSTRAINT FK_Consent_User FOREIGN KEY (user_id) REFERENCES Users(user_id),
  CONSTRAINT FK_Consent_Asset FOREIGN KEY (asset_id) REFERENCES Assets(asset_id),
  CONSTRAINT FK_Consent_Grantee FOREIGN KEY (grantee_user_id) REFERENCES Users(user_id),
  CONSTRAINT CHK_Scope CHECK (scope IN ('global', 'asset_specific', 'facet_specific', 'grantee_specific')),
  CONSTRAINT CHK_Visibility CHECK (visibility IN ('public', 'friends_only', 'private', 'custom'))
) PRIMARY KEY (consent_id);

-- Indexes for fast consent lookups
CREATE INDEX ConsentByUser ON ConsentPolicies(user_id, is_revoked);
CREATE INDEX ConsentByAsset ON ConsentPolicies(asset_id, is_revoked) WHERE asset_id IS NOT NULL;
CREATE INDEX ConsentByGrantee ON ConsentPolicies(grantee_user_id, is_revoked) WHERE grantee_user_id IS NOT NULL;
CREATE INDEX ConsentGlobal ON ConsentPolicies(user_id, scope) WHERE scope = 'global';
CREATE INDEX ConsentActive ON ConsentPolicies(is_revoked) WHERE is_revoked = false;

-- ============================================
-- PROVENANCE CHAIN: Immutable Ownership History
-- ============================================

CREATE TABLE ProvenanceChain (
  provenance_id STRING(36) NOT NULL,
  asset_id STRING(36) NOT NULL,
  sequence_num INT64 NOT NULL,
  from_user_id STRING(36),
  to_user_id STRING(36) NOT NULL,
  transfer_type STRING(50) NOT NULL,
  price FLOAT64,
  currency STRING(10),
  blockchain_tx_hash STRING(255),
  midnight_proof_hash STRING(255),
  crosschain_root_hash STRING(255),
  region_code STRING(50),
  policy_version STRING(36),
  metadata BYTES(MAX),
  transfer_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT FK_Prov_Asset FOREIGN KEY (asset_id) REFERENCES Assets(asset_id),
  CONSTRAINT FK_Prov_From FOREIGN KEY (from_user_id) REFERENCES Users(user_id),
  CONSTRAINT FK_Prov_To FOREIGN KEY (to_user_id) REFERENCES Users(user_id),
  CONSTRAINT CHK_Transfer_Type CHECK (transfer_type IN ('mint', 'purchase', 'gift', 'trade', 'inheritance', 'return'))
) PRIMARY KEY (asset_id, sequence_num),
  INTERLEAVE IN PARENT Assets ON DELETE CASCADE;

-- Index for tracing provenance
CREATE INDEX ProvenanceByAsset ON ProvenanceChain(asset_id, transfer_at DESC);
CREATE INDEX ProvenanceByFrom ON ProvenanceChain(from_user_id) WHERE from_user_id IS NOT NULL;
CREATE INDEX ProvenanceByTo ON ProvenanceChain(to_user_id);

-- ============================================
-- CUBE FACES: Product Cube metadata
-- ============================================

CREATE TABLE CubeFaces (
  cube_id STRING(36) NOT NULL,
  face_name STRING(50) NOT NULL,
  data BYTES(MAX),
  data_hash STRING(64),
  visibility STRING(20) DEFAULT ('public'),
  is_immutable BOOL DEFAULT (false),
  blockchain_tx_hash STRING(255),
  midnight_tx_hash STRING(255),
  last_modified_by STRING(36),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  updated_at TIMESTAMP OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT FK_Face_Cube FOREIGN KEY (cube_id) REFERENCES Assets(asset_id),
  CONSTRAINT FK_Face_Modifier FOREIGN KEY (last_modified_by) REFERENCES Users(user_id),
  CONSTRAINT CHK_Face_Name CHECK (face_name IN ('product_details', 'provenance', 'ownership', 'social_layer', 'esg_impact', 'lifecycle')),
  CONSTRAINT CHK_Face_Visibility CHECK (visibility IN ('public', 'friends_only', 'private', 'authenticated'))
) PRIMARY KEY (cube_id, face_name),
  INTERLEAVE IN PARENT Assets ON DELETE CASCADE;

-- ============================================
-- AUDIT & COMPLIANCE
-- ============================================

-- Hash-chained audit log
CREATE TABLE AuditLog (
  audit_id STRING(36) NOT NULL,
  related_asset_id STRING(36),
  related_user_id STRING(36),
  actor_type STRING(50) NOT NULL,
  actor_id STRING(36),
  action_type STRING(50) NOT NULL,
  action_summary STRING(500) NOT NULL,
  decision_summary STRING(500) NOT NULL,
  decision_detail BYTES(MAX),
  risk_flagged BOOL DEFAULT (false),
  risk_level STRING(20),
  escalated_to_human BOOL DEFAULT (false),
  human_approver_id STRING(36),
  approval_status STRING(20),
  policy_version STRING(64) NOT NULL,
  policy_snapshot BYTES(MAX),
  prev_hash STRING(64),
  entry_hash STRING(64) NOT NULL,
  region_code STRING(50) DEFAULT ('us-east1'),
  retention_policy STRING(20) DEFAULT ('standard'),
  redacted BOOL DEFAULT (false),
  redacted_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT CHK_Actor_Type CHECK (actor_type IN ('system', 'governance_human', 'compliance_agent', 'policy_engine', 'ai_brain_hub')),
  CONSTRAINT CHK_Action_Type CHECK (action_type IN ('scan', 'reveal', 'policy_check', 'escalation', 'ownership_transfer', 'minting', 'consent_update')),
  CONSTRAINT CHK_Risk_Level CHECK (risk_level IS NULL OR risk_level IN ('low', 'medium', 'high', 'critical'))
) PRIMARY KEY (audit_id);

-- Indexes for audit queries
CREATE INDEX AuditByAsset ON AuditLog(related_asset_id, created_at DESC) WHERE related_asset_id IS NOT NULL;
CREATE INDEX AuditByUser ON AuditLog(related_user_id, created_at DESC) WHERE related_user_id IS NOT NULL;
CREATE INDEX AuditByActor ON AuditLog(actor_id, created_at DESC) WHERE actor_id IS NOT NULL;
CREATE INDEX AuditEscalated ON AuditLog(escalated_to_human, human_approver_id) WHERE escalated_to_human = true;
CREATE INDEX AuditByHash ON AuditLog(entry_hash);
CREATE INDEX AuditByPrevHash ON AuditLog(prev_hash) WHERE prev_hash IS NOT NULL;

-- Blockchain anchoring
CREATE TABLE ChainAnchor (
  anchor_id STRING(36) NOT NULL,
  related_audit_id STRING(36),
  related_asset_id STRING(36),
  anchor_type STRING(50) DEFAULT ('scan_event'),
  cardano_tx_hash STRING(255),
  midnight_tx_hash STRING(255),
  crosschain_root_hash STRING(255),
  anchor_status STRING(20) DEFAULT ('pending'),
  retry_count INT64 DEFAULT (0),
  last_error STRING(500),
  anchored_at TIMESTAMP OPTIONS (allow_commit_timestamp=true),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT FK_Anchor_Audit FOREIGN KEY (related_audit_id) REFERENCES AuditLog(audit_id),
  CONSTRAINT FK_Anchor_Asset FOREIGN KEY (related_asset_id) REFERENCES Assets(asset_id)
) PRIMARY KEY (anchor_id);

CREATE INDEX AnchorByAudit ON ChainAnchor(related_audit_id);
CREATE INDEX AnchorByAsset ON ChainAnchor(related_asset_id) WHERE related_asset_id IS NOT NULL;
CREATE INDEX AnchorPending ON ChainAnchor(anchor_status) WHERE anchor_status = 'pending';

-- ============================================
-- IDEMPOTENCY: Mutation deduplication
-- ============================================

CREATE TABLE MutationLog (
  mutation_id STRING(32) NOT NULL,
  operation_name STRING(255) NOT NULL,
  params_hash STRING(64),
  actor_id STRING(36),
  result_status STRING(20),
  commit_timestamp TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true)
) PRIMARY KEY (mutation_id);

-- TTL index for auto-cleanup (Spanner doesn't have TTL, handle in application)
CREATE INDEX MutationByTimestamp ON MutationLog(commit_timestamp);

-- ============================================
-- SCAN EVENTS (for compatibility)
-- ============================================

CREATE TABLE ScanEvent (
  scan_id STRING(36) NOT NULL,
  scanner_user_id STRING(36) NOT NULL,
  asset_id STRING(36) NOT NULL,
  region_code STRING(50),
  policy_version STRING(100),
  resolved_scope STRING(50),
  shown_facets BYTES(MAX),
  occurred_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT FK_Scan_Scanner FOREIGN KEY (scanner_user_id) REFERENCES Users(user_id),
  CONSTRAINT FK_Scan_Asset FOREIGN KEY (asset_id) REFERENCES Assets(asset_id)
) PRIMARY KEY (scan_id);

CREATE INDEX ScanByScanner ON ScanEvent(scanner_user_id, occurred_at DESC);
CREATE INDEX ScanByAsset ON ScanEvent(asset_id, occurred_at DESC);
