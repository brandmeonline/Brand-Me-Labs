-- Copyright (c) Brand.Me, Inc. All rights reserved.
--
-- Consent Policies Table
-- Stores user consent preferences for garment data visibility

CREATE TABLE IF NOT EXISTS consent_policies (
  -- Primary Key
  policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Foreign Key
  garment_id UUID NOT NULL REFERENCES garments(garment_id) ON DELETE CASCADE,

  -- Visibility Scope
  visibility_scope TEXT NOT NULL, -- 'public', 'friends_only', 'private'

  -- Facet Type this policy applies to
  facet_type TEXT NOT NULL,

  -- Permission
  allowed BOOLEAN NOT NULL DEFAULT FALSE,

  -- Region-specific overrides
  region_code TEXT,

  -- Metadata
  policy_reason TEXT, -- User-provided reason for policy
  created_by_user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_consent_garment_id ON consent_policies(garment_id);
CREATE INDEX idx_consent_visibility_scope ON consent_policies(visibility_scope);
CREATE INDEX idx_consent_facet_type ON consent_policies(facet_type);
CREATE INDEX idx_consent_region_code ON consent_policies(region_code) WHERE region_code IS NOT NULL;
CREATE INDEX idx_consent_allowed ON consent_policies(allowed);

-- Unique constraint: One policy per (garment, scope, facet_type, region)
CREATE UNIQUE INDEX idx_consent_unique_policy
  ON consent_policies(garment_id, visibility_scope, facet_type, COALESCE(region_code, 'global'));

-- Trigger to update updated_at
CREATE TRIGGER update_consent_policies_updated_at
  BEFORE UPDATE ON consent_policies
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Comments
COMMENT ON TABLE consent_policies IS 'User consent policies for garment data visibility';
COMMENT ON COLUMN consent_policies.visibility_scope IS 'Scope: public, friends_only, private';
COMMENT ON COLUMN consent_policies.facet_type IS 'Which facet type this policy controls';
COMMENT ON COLUMN consent_policies.allowed IS 'Whether this facet is visible for this scope';
COMMENT ON COLUMN consent_policies.region_code IS 'Optional region-specific override';

-- Constraint: Ensure visibility_scope is valid
ALTER TABLE consent_policies
  ADD CONSTRAINT check_visibility_scope
  CHECK (visibility_scope IN ('public', 'friends_only', 'private'));
