-- ============================================
-- SPANNER GRAPH SCHEMA: Global Integrity Spine
-- Brand.Me v9 - 2030 Agentic & Circular Economy
-- ============================================
--
-- Architecture:
--   - Native Property Graph (GQL) for O(1) consent traversal
--   - Circularity tracking (Materials, Lifecycle, DerivedFrom)
--   - Agentic oversight (ConsentedByAgent, EthicalAudit)
--   - Commit timestamps for global idempotency
--
-- ============================================

-- ============================================
-- NODE TABLES: Core Entities
-- ============================================

-- NODE: Users (Actors in the system - humans and agents)
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
  -- v9: Agent classification
  is_agent BOOL DEFAULT (false),
  agent_type STRING(50),                        -- "style_agent", "resale_agent", "rental_agent"
  agent_capabilities ARRAY<STRING(100)>,        -- ["wardrobe_view", "transact", "style_suggest"]
  -- Timestamps
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
CREATE INDEX UserAgents ON Users(is_agent) WHERE is_agent = true;

-- NODE: Assets (Garments/Cubes with DPP lifecycle)
CREATE TABLE Assets (
  asset_id STRING(36) NOT NULL,
  asset_type STRING(50) NOT NULL,               -- "garment", "accessory", "material_batch"
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
  -- v9: Digital Product Passport (DPP) fields
  lifecycle_state STRING(20) DEFAULT ('PRODUCED'),  -- PRODUCED, ACTIVE, REPAIR, DISSOLVE, REPRINT
  primary_material_id STRING(36),
  reprint_generation INT64 DEFAULT (0),
  parent_asset_id STRING(36),                   -- For reprinted items (DerivedFrom)
  dissolve_authorized_at TIMESTAMP,
  -- Timestamps
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  updated_at TIMESTAMP OPTIONS (allow_commit_timestamp=true),
  first_minted_at TIMESTAMP,
  last_scanned_at TIMESTAMP,
  CONSTRAINT FK_Asset_Creator FOREIGN KEY (creator_user_id) REFERENCES Users(user_id),
  CONSTRAINT FK_Asset_Owner FOREIGN KEY (current_owner_id) REFERENCES Users(user_id),
  CONSTRAINT CHK_Lifecycle_State CHECK (lifecycle_state IN ('PRODUCED', 'ACTIVE', 'REPAIR', 'DISSOLVE', 'REPRINT'))
) PRIMARY KEY (asset_id);

-- Indexes for Assets
CREATE INDEX AssetsByCreator ON Assets(creator_user_id);
CREATE INDEX AssetsByOwner ON Assets(current_owner_id);
CREATE INDEX AssetsByPhysicalTag ON Assets(physical_tag_id) WHERE physical_tag_id IS NOT NULL;
CREATE INDEX AssetsByCategory ON Assets(category) WHERE category IS NOT NULL;
CREATE INDEX AssetsByAuthHash ON Assets(authenticity_hash);
CREATE INDEX AssetsActive ON Assets(is_active) WHERE is_active = true;
CREATE INDEX AssetsByLifecycle ON Assets(lifecycle_state);
CREATE INDEX AssetsByParent ON Assets(parent_asset_id) WHERE parent_asset_id IS NOT NULL;

-- NODE: Materials (Molecular-level tracking for circularity)
CREATE TABLE Materials (
  material_id STRING(36) NOT NULL,
  material_type STRING(100) NOT NULL,           -- "organic_cotton", "recycled_polyester", "bio_silk"
  material_name STRING(255),
  -- Molecular properties
  tensile_strength_mpa FLOAT64,                 -- Mechanical property
  density_kg_m3 FLOAT64,
  biodegradability_years FLOAT64,
  molecular_signature_hash STRING(64),          -- Spectroscopy fingerprint
  -- Dissolution/Reprint authorization
  dissolve_auth_key_hash STRING(64),            -- SHA256 of auth key (key in Midnight)
  dissolve_method STRING(100),                  -- "chemical", "mechanical", "enzymatic"
  -- Supply chain
  supplier_id STRING(36),
  supplier_name STRING(255),
  batch_number STRING(100),
  origin_country STRING(100),
  certification_ids ARRAY<STRING(100)>,         -- ["GOTS", "OEKO-TEX", "GRS"]
  -- Environmental metrics (from Cardano ESG oracle)
  esg_score FLOAT64,                            -- 0.0-1.0 overall score
  carbon_footprint_kg FLOAT64,                  -- Per kg of material
  water_usage_liters FLOAT64,                   -- Per kg of material
  energy_usage_kwh FLOAT64,
  recyclability_pct FLOAT64,                    -- 0-100%
  -- Blockchain references
  cardano_material_cert STRING(255),            -- On-chain material certification
  midnight_dissolve_contract STRING(255),       -- ZK contract for dissolution
  -- Status
  is_active BOOL DEFAULT (true),
  is_recyclable BOOL DEFAULT (true),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  updated_at TIMESTAMP OPTIONS (allow_commit_timestamp=true)
) PRIMARY KEY (material_id);

-- Indexes for Materials
CREATE INDEX MaterialsByType ON Materials(material_type);
CREATE INDEX MaterialsBySupplier ON Materials(supplier_id) WHERE supplier_id IS NOT NULL;
CREATE INDEX MaterialsByESG ON Materials(esg_score DESC);
CREATE INDEX MaterialsRecyclable ON Materials(is_recyclable) WHERE is_recyclable = true;

-- ============================================
-- EDGE TABLES: Graph Relationships
-- ============================================

-- EDGE: OWNS (User -> Asset) - Current and historical ownership
CREATE TABLE Owns (
  owner_id STRING(36) NOT NULL,
  asset_id STRING(36) NOT NULL,
  acquired_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  transfer_method STRING(50),                   -- "purchase", "gift", "rental", "reprint"
  price FLOAT64,
  currency STRING(10) DEFAULT ('USD'),
  blockchain_tx_hash STRING(255),
  midnight_tx_hash STRING(255),
  -- v9: Agentic transaction metadata
  agent_facilitated BOOL DEFAULT (false),
  facilitating_agent_id STRING(36),
  esg_verified BOOL DEFAULT (false),            -- ESG check passed before transaction
  is_current BOOL DEFAULT (true),
  ended_at TIMESTAMP,
  CONSTRAINT FK_Owns_Owner FOREIGN KEY (owner_id) REFERENCES Users(user_id),
  CONSTRAINT FK_Owns_Asset FOREIGN KEY (asset_id) REFERENCES Assets(asset_id)
) PRIMARY KEY (owner_id, asset_id, acquired_at),
  INTERLEAVE IN PARENT Users ON DELETE CASCADE;

-- Index for finding current owner quickly
CREATE INDEX OwnsCurrent ON Owns(asset_id, is_current) WHERE is_current = true;
CREATE INDEX OwnsByAsset ON Owns(asset_id, acquired_at DESC);
CREATE INDEX OwnsAgentFacilitated ON Owns(agent_facilitated) WHERE agent_facilitated = true;

-- EDGE: CREATED (User -> Asset) - Immutable creator relationship
CREATE TABLE Created (
  creator_id STRING(36) NOT NULL,
  asset_id STRING(36) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  creation_method STRING(50) DEFAULT ('manual'),  -- "manual", "factory", "reprint"
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

-- EDGE: COMPOSED_OF (Asset -> Material) - Material composition
CREATE TABLE ComposedOf (
  asset_id STRING(36) NOT NULL,
  material_id STRING(36) NOT NULL,
  percentage FLOAT64 NOT NULL,                  -- 0.0-100.0
  layer_position INT64,                         -- For multi-layer garments (0=outer, 1=lining, etc)
  weight_grams FLOAT64,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT FK_ComposedOf_Asset FOREIGN KEY (asset_id) REFERENCES Assets(asset_id),
  CONSTRAINT FK_ComposedOf_Material FOREIGN KEY (material_id) REFERENCES Materials(material_id),
  CONSTRAINT CHK_Percentage CHECK (percentage >= 0 AND percentage <= 100)
) PRIMARY KEY (asset_id, material_id),
  INTERLEAVE IN PARENT Assets ON DELETE CASCADE;

-- EDGE: DERIVED_FROM (Asset -> Asset) - Reprint/Upcycle lineage
CREATE TABLE DerivedFrom (
  child_asset_id STRING(36) NOT NULL,
  parent_asset_id STRING(36) NOT NULL,
  derivation_type STRING(50) NOT NULL,          -- "reprint", "repair", "upcycle", "recycle"
  burn_proof_hash STRING(64) NOT NULL,          -- Midnight ZK proof of dissolution
  midnight_burn_tx STRING(255),                 -- Transaction hash for burn verification
  material_recovery_pct FLOAT64,                -- % material recovered (0-100)
  esg_improvement FLOAT64,                      -- ESG delta from parent
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  verified_at TIMESTAMP,
  CONSTRAINT FK_DerivedFrom_Child FOREIGN KEY (child_asset_id) REFERENCES Assets(asset_id),
  CONSTRAINT FK_DerivedFrom_Parent FOREIGN KEY (parent_asset_id) REFERENCES Assets(asset_id),
  CONSTRAINT CHK_Derivation_Type CHECK (derivation_type IN ('reprint', 'repair', 'upcycle', 'recycle'))
) PRIMARY KEY (child_asset_id, parent_asset_id);

CREATE INDEX DerivedFromParent ON DerivedFrom(parent_asset_id);
CREATE INDEX DerivedFromType ON DerivedFrom(derivation_type);

-- EDGE: CONSENTED_BY_AGENT (User -> Agent) - Agentic permissions
CREATE TABLE ConsentedByAgent (
  user_id STRING(36) NOT NULL,
  agent_id STRING(36) NOT NULL,
  permission_scope STRING(50) NOT NULL,         -- "view_wardrobe", "transact", "style_suggest", "rental", "resale"
  max_transaction_usd FLOAT64,                  -- Max single transaction value
  daily_limit_usd FLOAT64,                      -- Daily spending limit
  requires_human_approval BOOL DEFAULT (true),  -- Human-in-the-loop for transactions
  min_esg_score FLOAT64 DEFAULT (0.5),          -- Minimum ESG score for transactions
  allowed_categories ARRAY<STRING(100)>,        -- Allowed garment categories
  granted_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  expires_at TIMESTAMP,
  revoked_at TIMESTAMP,
  revoke_reason STRING(255),
  CONSTRAINT FK_ConsentedByAgent_User FOREIGN KEY (user_id) REFERENCES Users(user_id),
  CONSTRAINT FK_ConsentedByAgent_Agent FOREIGN KEY (agent_id) REFERENCES Users(user_id),
  CONSTRAINT CHK_Permission_Scope CHECK (permission_scope IN ('view_wardrobe', 'transact', 'style_suggest', 'rental', 'resale', 'repair_request', 'dissolve_request'))
) PRIMARY KEY (user_id, agent_id, permission_scope),
  INTERLEAVE IN PARENT Users ON DELETE CASCADE;

CREATE INDEX ConsentByAgent ON ConsentedByAgent(agent_id);
CREATE INDEX ConsentActive ON ConsentedByAgent(revoked_at) WHERE revoked_at IS NULL;

-- ============================================
-- LIFECYCLE & DPP (Digital Product Passport)
-- ============================================

-- Lifecycle Events (State Machine Transitions)
CREATE TABLE LifecycleEvents (
  event_id STRING(36) NOT NULL,
  asset_id STRING(36) NOT NULL,
  from_state STRING(20),                        -- NULL for initial PRODUCED state
  to_state STRING(20) NOT NULL,
  triggered_by STRING(36),                      -- user_id or agent_id
  trigger_type STRING(50) NOT NULL,             -- "user", "agent", "system", "burn_verified", "repair_complete"
  -- Dissolution/Reprint specific
  dissolve_auth_verified BOOL DEFAULT (false),
  burn_proof_hash STRING(64),                   -- Midnight ZK proof for DISSOLVE->REPRINT
  parent_material_batch STRING(36),             -- Link to dissolved material
  -- Environmental impact
  esg_delta FLOAT64,                            -- ESG impact of transition (positive = improvement)
  carbon_saved_kg FLOAT64,
  water_saved_liters FLOAT64,
  -- Blockchain anchoring
  cardano_tx_hash STRING(255),
  midnight_tx_hash STRING(255),
  -- Metadata
  notes STRING(MAX),
  occurred_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT FK_Lifecycle_Asset FOREIGN KEY (asset_id) REFERENCES Assets(asset_id),
  CONSTRAINT FK_Lifecycle_Trigger FOREIGN KEY (triggered_by) REFERENCES Users(user_id),
  CONSTRAINT CHK_From_State CHECK (from_state IS NULL OR from_state IN ('PRODUCED', 'ACTIVE', 'REPAIR', 'DISSOLVE', 'REPRINT')),
  CONSTRAINT CHK_To_State CHECK (to_state IN ('PRODUCED', 'ACTIVE', 'REPAIR', 'DISSOLVE', 'REPRINT'))
) PRIMARY KEY (event_id);

CREATE INDEX LifecycleByAsset ON LifecycleEvents(asset_id, occurred_at DESC);
CREATE INDEX LifecycleByState ON LifecycleEvents(to_state);
CREATE INDEX LifecycleByTrigger ON LifecycleEvents(triggered_by) WHERE triggered_by IS NOT NULL;

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
  grantee_type STRING(20) DEFAULT ('anyone'),   -- "anyone", "friends", "agent", "specific_user"
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
  CONSTRAINT CHK_Visibility CHECK (visibility IN ('public', 'friends_only', 'private', 'custom', 'agent_only'))
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
  -- v9: Agentic and ESG tracking
  agent_facilitated BOOL DEFAULT (false),
  agent_id STRING(36),
  esg_score_at_transfer FLOAT64,
  metadata BYTES(MAX),
  transfer_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT FK_Prov_Asset FOREIGN KEY (asset_id) REFERENCES Assets(asset_id),
  CONSTRAINT FK_Prov_From FOREIGN KEY (from_user_id) REFERENCES Users(user_id),
  CONSTRAINT FK_Prov_To FOREIGN KEY (to_user_id) REFERENCES Users(user_id),
  CONSTRAINT CHK_Transfer_Type CHECK (transfer_type IN ('mint', 'purchase', 'gift', 'trade', 'inheritance', 'return', 'rental_start', 'rental_end', 'reprint'))
) PRIMARY KEY (asset_id, sequence_num),
  INTERLEAVE IN PARENT Assets ON DELETE CASCADE;

-- Index for tracing provenance
CREATE INDEX ProvenanceByAsset ON ProvenanceChain(asset_id, transfer_at DESC);
CREATE INDEX ProvenanceByFrom ON ProvenanceChain(from_user_id) WHERE from_user_id IS NOT NULL;
CREATE INDEX ProvenanceByTo ON ProvenanceChain(to_user_id);

-- ============================================
-- CUBE FACES: Product Cube metadata (7 faces now)
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
  -- v9: Added molecular_data face
  CONSTRAINT CHK_Face_Name CHECK (face_name IN ('product_details', 'provenance', 'ownership', 'social_layer', 'esg_impact', 'lifecycle', 'molecular_data')),
  CONSTRAINT CHK_Face_Visibility CHECK (visibility IN ('public', 'friends_only', 'private', 'authenticated', 'agent_only'))
) PRIMARY KEY (cube_id, face_name),
  INTERLEAVE IN PARENT Assets ON DELETE CASCADE;

-- ============================================
-- AUDIT & COMPLIANCE (Enhanced for Agentic)
-- ============================================

-- Hash-chained audit log with ethical oversight
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
  -- v9: Agentic and ESG audit fields
  agent_involved BOOL DEFAULT (false),
  agent_id STRING(36),
  esg_score_checked FLOAT64,
  esg_threshold_met BOOL,
  ethical_check_passed BOOL,
  -- Chain integrity
  policy_version STRING(64) NOT NULL,
  policy_snapshot BYTES(MAX),
  prev_hash STRING(64),
  entry_hash STRING(64) NOT NULL,
  region_code STRING(50) DEFAULT ('us-east1'),
  retention_policy STRING(20) DEFAULT ('standard'),
  redacted BOOL DEFAULT (false),
  redacted_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT CHK_Actor_Type CHECK (actor_type IN ('system', 'governance_human', 'compliance_agent', 'policy_engine', 'ai_brain_hub', 'external_agent', 'mcp_tool')),
  CONSTRAINT CHK_Action_Type CHECK (action_type IN ('scan', 'reveal', 'policy_check', 'escalation', 'ownership_transfer', 'minting', 'consent_update', 'lifecycle_transition', 'agent_transaction', 'esg_verification', 'burn_proof_verify', 'zk_ownership_proof')),
  CONSTRAINT CHK_Risk_Level CHECK (risk_level IS NULL OR risk_level IN ('low', 'medium', 'high', 'critical'))
) PRIMARY KEY (audit_id);

-- Indexes for audit queries
CREATE INDEX AuditByAsset ON AuditLog(related_asset_id, created_at DESC) WHERE related_asset_id IS NOT NULL;
CREATE INDEX AuditByUser ON AuditLog(related_user_id, created_at DESC) WHERE related_user_id IS NOT NULL;
CREATE INDEX AuditByActor ON AuditLog(actor_id, created_at DESC) WHERE actor_id IS NOT NULL;
CREATE INDEX AuditEscalated ON AuditLog(escalated_to_human, human_approver_id) WHERE escalated_to_human = true;
CREATE INDEX AuditByHash ON AuditLog(entry_hash);
CREATE INDEX AuditByPrevHash ON AuditLog(prev_hash) WHERE prev_hash IS NOT NULL;
CREATE INDEX AuditByAgent ON AuditLog(agent_involved, agent_id) WHERE agent_involved = true;

-- Blockchain anchoring
CREATE TABLE ChainAnchor (
  anchor_id STRING(36) NOT NULL,
  related_audit_id STRING(36),
  related_asset_id STRING(36),
  anchor_type STRING(50) DEFAULT ('scan_event'),  -- "scan_event", "lifecycle_transition", "burn_proof", "esg_cert"
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

-- TTL index for auto-cleanup (handle in application)
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
  -- v9: AR/Biometric fields
  ar_device_id STRING(100),
  biometric_verified BOOL DEFAULT (false),
  occurred_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT FK_Scan_Scanner FOREIGN KEY (scanner_user_id) REFERENCES Users(user_id),
  CONSTRAINT FK_Scan_Asset FOREIGN KEY (asset_id) REFERENCES Assets(asset_id)
) PRIMARY KEY (scan_id);

CREATE INDEX ScanByScanner ON ScanEvent(scanner_user_id, occurred_at DESC);
CREATE INDEX ScanByAsset ON ScanEvent(asset_id, occurred_at DESC);
CREATE INDEX ScanByARDevice ON ScanEvent(ar_device_id) WHERE ar_device_id IS NOT NULL;

-- ============================================
-- MCP TOOL REGISTRY (Model Context Protocol)
-- ============================================

CREATE TABLE MCPTools (
  tool_id STRING(36) NOT NULL,
  tool_name STRING(100) NOT NULL,
  tool_version STRING(20) NOT NULL,
  description STRING(500),
  input_schema BYTES(MAX),                      -- JSON Schema
  requires_consent BOOL DEFAULT (true),
  requires_esg_check BOOL DEFAULT (false),
  min_trust_score FLOAT64 DEFAULT (0.5),
  is_active BOOL DEFAULT (true),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  updated_at TIMESTAMP OPTIONS (allow_commit_timestamp=true)
) PRIMARY KEY (tool_id);

CREATE UNIQUE INDEX MCPToolsByName ON MCPTools(tool_name, tool_version);

-- MCP Tool Invocations (for audit)
CREATE TABLE MCPInvocations (
  invocation_id STRING(36) NOT NULL,
  tool_id STRING(36) NOT NULL,
  agent_id STRING(36) NOT NULL,
  user_id STRING(36) NOT NULL,
  input_params_hash STRING(64),
  result_status STRING(20),                     -- "success", "denied", "error", "pending_approval"
  esg_check_passed BOOL,
  consent_verified BOOL,
  human_approval_required BOOL DEFAULT (false),
  human_approved_by STRING(36),
  invoked_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  completed_at TIMESTAMP,
  CONSTRAINT FK_MCP_Tool FOREIGN KEY (tool_id) REFERENCES MCPTools(tool_id),
  CONSTRAINT FK_MCP_Agent FOREIGN KEY (agent_id) REFERENCES Users(user_id),
  CONSTRAINT FK_MCP_User FOREIGN KEY (user_id) REFERENCES Users(user_id)
) PRIMARY KEY (invocation_id);

CREATE INDEX MCPInvocationsByTool ON MCPInvocations(tool_id, invoked_at DESC);
CREATE INDEX MCPInvocationsByAgent ON MCPInvocations(agent_id, invoked_at DESC);
CREATE INDEX MCPInvocationsPending ON MCPInvocations(human_approval_required) WHERE human_approval_required = true;

-- v9: Agent Transaction Tracking (rentals, resales, repairs, dissolves)
CREATE TABLE AgentTransaction (
  transaction_id STRING(36) NOT NULL,
  agent_id STRING(36) NOT NULL,
  user_id STRING(36) NOT NULL,
  transaction_type STRING(50) NOT NULL,           -- "rental", "resale_listing", "repair_request", "dissolve_request"
  asset_id STRING(36) NOT NULL,
  counterparty_id STRING(36),                     -- e.g., renter_id for rentals
  transaction_value_usd FLOAT64,
  status STRING(30) NOT NULL,                     -- "pending_approval", "submitted", "approved", "rejected", "completed"
  requires_human_review BOOL DEFAULT (true),
  human_reviewed_by STRING(36),
  human_review_at TIMESTAMP,
  review_notes STRING(500),
  esg_verified BOOL DEFAULT (false),
  initiated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  completed_at TIMESTAMP,
  CONSTRAINT FK_AgentTx_Agent FOREIGN KEY (agent_id) REFERENCES Users(user_id),
  CONSTRAINT FK_AgentTx_User FOREIGN KEY (user_id) REFERENCES Users(user_id),
  CONSTRAINT FK_AgentTx_Asset FOREIGN KEY (asset_id) REFERENCES Assets(asset_id),
  CONSTRAINT CHK_AgentTx_Type CHECK (transaction_type IN ('rental', 'resale_listing', 'repair_request', 'dissolve_request', 'transfer'))
) PRIMARY KEY (transaction_id);

CREATE INDEX AgentTxByUser ON AgentTransaction(user_id, initiated_at DESC);
CREATE INDEX AgentTxByAgent ON AgentTransaction(agent_id, initiated_at DESC);
CREATE INDEX AgentTxByAsset ON AgentTransaction(asset_id);
CREATE INDEX AgentTxPending ON AgentTransaction(status) WHERE status = 'pending_approval';

-- v9: Burn Proof Verification Cache (Midnight)
CREATE TABLE BurnProofCache (
  cache_id STRING(36) NOT NULL,
  proof_hash STRING(64) NOT NULL,
  parent_asset_id STRING(36) NOT NULL,
  material_recovery_pct FLOAT64,
  is_valid BOOL NOT NULL,
  verified_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT FK_BurnProof_Asset FOREIGN KEY (parent_asset_id) REFERENCES Assets(asset_id)
) PRIMARY KEY (cache_id);

CREATE UNIQUE INDEX BurnProofByHash ON BurnProofCache(proof_hash);
CREATE INDEX BurnProofByAsset ON BurnProofCache(parent_asset_id);

-- v9: Material ESG Score Cache (Cardano Oracle)
CREATE TABLE MaterialESGCache (
  cache_id STRING(36) NOT NULL,
  material_id STRING(36) NOT NULL,
  overall_score FLOAT64 NOT NULL,
  environmental FLOAT64,
  social FLOAT64,
  governance FLOAT64,
  carbon_footprint_kg FLOAT64,
  water_usage_liters FLOAT64,
  recyclability_pct FLOAT64,
  certifications ARRAY<STRING(100)>,
  cardano_tx_hash STRING(255),
  oracle_timestamp TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  CONSTRAINT FK_ESGCache_Material FOREIGN KEY (material_id) REFERENCES Materials(material_id)
) PRIMARY KEY (cache_id);

CREATE UNIQUE INDEX ESGCacheByMaterial ON MaterialESGCache(material_id);
CREATE INDEX ESGCacheByTimestamp ON MaterialESGCache(oracle_timestamp DESC);

-- ============================================
-- ZK PROOF CACHE (for AR glasses)
-- ============================================

CREATE TABLE ZKProofCache (
  proof_id STRING(36) NOT NULL,
  user_id STRING(36) NOT NULL,
  asset_id STRING(36) NOT NULL,
  proof_type STRING(50) NOT NULL,               -- "ownership", "consent", "age_verification"
  proof_hash STRING(64) NOT NULL,
  proof_data STRING(MAX),                       -- Serialized ZK proof data (JSON)
  public_signals STRING(MAX),                   -- Public signals from proof (JSON)
  challenge_nonce STRING(64),
  device_session_id STRING(100),
  is_valid BOOL DEFAULT (true),
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  expires_at TIMESTAMP NOT NULL,
  CONSTRAINT FK_ZKProof_User FOREIGN KEY (user_id) REFERENCES Users(user_id),
  CONSTRAINT FK_ZKProof_Asset FOREIGN KEY (asset_id) REFERENCES Assets(asset_id)
) PRIMARY KEY (proof_id);

CREATE INDEX ZKProofByUser ON ZKProofCache(user_id, expires_at DESC);
CREATE INDEX ZKProofByAsset ON ZKProofCache(asset_id);
CREATE INDEX ZKProofByDevice ON ZKProofCache(device_session_id) WHERE device_session_id IS NOT NULL;

-- ============================================
-- SPANNER PROPERTY GRAPH DEFINITION (GQL Native)
-- ============================================

CREATE PROPERTY GRAPH IntegritySpineGraph
  NODE TABLES (
    Users
      LABEL User
      PROPERTIES (user_id, handle, display_name, trust_score, is_agent, agent_type),
    Assets
      LABEL Asset
      PROPERTIES (asset_id, asset_type, display_name, lifecycle_state, reprint_generation, public_esg_score),
    Materials
      LABEL Material
      PROPERTIES (material_id, material_type, esg_score, tensile_strength_mpa, is_recyclable)
  )
  EDGE TABLES (
    Owns
      SOURCE KEY (owner_id) REFERENCES Users (user_id)
      DESTINATION KEY (asset_id) REFERENCES Assets (asset_id)
      LABEL OWNS
      PROPERTIES (acquired_at, transfer_method, is_current, agent_facilitated, esg_verified),
    Created
      SOURCE KEY (creator_id) REFERENCES Users (user_id)
      DESTINATION KEY (asset_id) REFERENCES Assets (asset_id)
      LABEL CREATED
      PROPERTIES (created_at, creation_method),
    FriendsWith
      SOURCE KEY (user_id_a) REFERENCES Users (user_id)
      DESTINATION KEY (user_id_b) REFERENCES Users (user_id)
      LABEL FRIENDS_WITH
      PROPERTIES (status, created_at),
    ComposedOf
      SOURCE KEY (asset_id) REFERENCES Assets (asset_id)
      DESTINATION KEY (material_id) REFERENCES Materials (material_id)
      LABEL COMPOSED_OF
      PROPERTIES (percentage, layer_position),
    DerivedFrom
      SOURCE KEY (child_asset_id) REFERENCES Assets (asset_id)
      DESTINATION KEY (parent_asset_id) REFERENCES Assets (asset_id)
      LABEL DERIVED_FROM
      PROPERTIES (derivation_type, burn_proof_hash, material_recovery_pct),
    ConsentedByAgent
      SOURCE KEY (user_id) REFERENCES Users (user_id)
      DESTINATION KEY (agent_id) REFERENCES Users (user_id)
      LABEL CONSENTED_TO_AGENT
      PROPERTIES (permission_scope, max_transaction_usd, requires_human_approval, min_esg_score)
  );
