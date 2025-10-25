-- Copyright (c) Brand.Me, Inc. All rights reserved.
--
-- Scan Event Table
-- Stores history of garment scans with resolved visibility and shown data

CREATE TABLE IF NOT EXISTS scan_event (
  -- Primary Key
  scan_id UUID PRIMARY KEY,

  -- Foreign Keys
  scanner_user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  garment_id UUID NOT NULL REFERENCES garments(garment_id) ON DELETE CASCADE,

  -- Event Details
  occurred_at TIMESTAMPTZ DEFAULT NOW(),

  -- Policy Decision
  resolved_scope TEXT NOT NULL, -- 'public', 'friends_only', 'private'
  policy_version TEXT NOT NULL, -- SHA256 hash of policy used
  decision_summary TEXT, -- Human-readable summary

  -- Region & Context
  region_code TEXT NOT NULL DEFAULT 'us-east1',
  scan_location_lat NUMERIC(10,7),
  scan_location_lng NUMERIC(10,7),

  -- Data Shown
  shown_facets JSONB, -- Array of facet objects shown to scanner

  -- Security Flags
  risk_flagged BOOLEAN DEFAULT FALSE,
  escalated_to_human BOOLEAN DEFAULT FALSE,

  -- Client Info
  client_type TEXT, -- 'mobile_app', 'web', 'kiosk'
  client_version TEXT,
  user_agent TEXT
);

-- Indexes
CREATE INDEX idx_scan_event_scanner_user_id ON scan_event(scanner_user_id);
CREATE INDEX idx_scan_event_garment_id ON scan_event(garment_id);
CREATE INDEX idx_scan_event_occurred_at ON scan_event(occurred_at DESC);
CREATE INDEX idx_scan_event_resolved_scope ON scan_event(resolved_scope);
CREATE INDEX idx_scan_event_policy_version ON scan_event(policy_version);
CREATE INDEX idx_scan_event_region_code ON scan_event(region_code);
CREATE INDEX idx_scan_event_risk_flagged ON scan_event(risk_flagged) WHERE risk_flagged = TRUE;
CREATE INDEX idx_scan_event_escalated ON scan_event(escalated_to_human) WHERE escalated_to_human = TRUE;

-- GIN index for shown_facets JSONB queries
CREATE INDEX idx_scan_event_shown_facets_gin ON scan_event USING GIN (shown_facets);

-- Composite index for user scan history
CREATE INDEX idx_scan_event_user_history ON scan_event(scanner_user_id, occurred_at DESC);

-- Composite index for garment scan history
CREATE INDEX idx_scan_event_garment_history ON scan_event(garment_id, occurred_at DESC);

-- Comments
COMMENT ON TABLE scan_event IS 'Historical record of all garment scans with policy decisions';
COMMENT ON COLUMN scan_event.resolved_scope IS 'Visibility scope applied: public, friends_only, private';
COMMENT ON COLUMN scan_event.policy_version IS 'Hash of consent policy version used';
COMMENT ON COLUMN scan_event.shown_facets IS 'JSON array of facets actually shown to scanner';
COMMENT ON COLUMN scan_event.risk_flagged IS 'True if scan was flagged for review';
COMMENT ON COLUMN scan_event.escalated_to_human IS 'True if scan required human governance review';

-- Constraint: Ensure resolved_scope is valid
ALTER TABLE scan_event
  ADD CONSTRAINT check_scan_resolved_scope
  CHECK (resolved_scope IN ('public', 'friends_only', 'private'));
