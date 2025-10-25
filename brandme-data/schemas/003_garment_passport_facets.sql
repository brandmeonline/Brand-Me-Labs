-- Copyright (c) Brand.Me, Inc. All rights reserved.
--
-- Garment Passport Facets Table
-- Stores granular metadata and provenance data for garments

CREATE TABLE IF NOT EXISTS garment_passport_facets (
  -- Primary Key
  facet_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Foreign Key
  garment_id UUID NOT NULL REFERENCES garments(garment_id) ON DELETE CASCADE,

  -- Facet Type
  facet_type TEXT NOT NULL, -- 'authenticity', 'esg', 'ownership', 'pricing', 'materials', 'story'

  -- Facet Payload (JSON)
  facet_payload JSONB NOT NULL,

  -- Visibility
  is_public_default BOOLEAN NOT NULL DEFAULT FALSE,

  -- Blockchain References
  midnight_ref TEXT, -- Reference to Midnight chain data (private)
  cardano_ref TEXT, -- Reference to Cardano chain data (public)

  -- Metadata
  created_by_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
  last_updated_by_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_facets_garment_id ON garment_passport_facets(garment_id);
CREATE INDEX idx_facets_facet_type ON garment_passport_facets(facet_type);
CREATE INDEX idx_facets_is_public ON garment_passport_facets(is_public_default);
CREATE INDEX idx_facets_midnight_ref ON garment_passport_facets(midnight_ref) WHERE midnight_ref IS NOT NULL;
CREATE INDEX idx_facets_cardano_ref ON garment_passport_facets(cardano_ref) WHERE cardano_ref IS NOT NULL;

-- GIN index for JSONB queries
CREATE INDEX idx_facets_payload_gin ON garment_passport_facets USING GIN (facet_payload);

-- Trigger to update last_updated_at
CREATE TRIGGER update_facets_updated_at
  BEFORE UPDATE ON garment_passport_facets
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Comments
COMMENT ON TABLE garment_passport_facets IS 'Granular garment metadata with public/private visibility control';
COMMENT ON COLUMN garment_passport_facets.facet_type IS 'Type: authenticity, esg, ownership, pricing, materials, story';
COMMENT ON COLUMN garment_passport_facets.facet_payload IS 'JSON payload with facet-specific data';
COMMENT ON COLUMN garment_passport_facets.is_public_default IS 'True if this facet is visible publicly by default';
COMMENT ON COLUMN garment_passport_facets.midnight_ref IS 'Reference to private Midnight chain data';
COMMENT ON COLUMN garment_passport_facets.cardano_ref IS 'Reference to public Cardano chain data';

-- Constraint: Ensure facet_type is from allowed set
ALTER TABLE garment_passport_facets
  ADD CONSTRAINT check_facet_type
  CHECK (facet_type IN ('authenticity', 'esg', 'ownership', 'pricing', 'materials', 'story', 'certificates', 'repairs'));
