-- Copyright (c) Brand.Me, Inc. All rights reserved.
--
-- Garments Table
-- Stores garment registry with creator and owner references

CREATE TABLE IF NOT EXISTS garments (
  -- Primary Key
  garment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Identity
  creator_id UUID NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
  current_owner_id UUID NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,

  -- Basic Info
  display_name TEXT NOT NULL,
  category TEXT, -- 'jacket', 'sneakers', 'dress', etc.
  description TEXT,

  -- Blockchain References
  cardano_asset_ref TEXT, -- Cardano asset/NFT reference
  authenticity_hash TEXT NOT NULL, -- Immutable provenance hash

  -- Public Metadata (visible to all)
  public_esg_score TEXT, -- 'A+', 'B', 'C', etc.
  public_story_snippet TEXT, -- Short creator story

  -- Physical Tag
  physical_tag_id TEXT UNIQUE, -- NFC/QR code identifier
  physical_tag_type TEXT, -- 'nfc', 'qr', 'rfid'

  -- Status
  is_authentic BOOLEAN DEFAULT TRUE,
  is_active BOOLEAN DEFAULT TRUE,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  first_minted_at TIMESTAMPTZ,
  last_scanned_at TIMESTAMPTZ
);

-- Indexes
CREATE INDEX idx_garments_creator_id ON garments(creator_id);
CREATE INDEX idx_garments_current_owner_id ON garments(current_owner_id);
CREATE INDEX idx_garments_physical_tag_id ON garments(physical_tag_id);
CREATE INDEX idx_garments_category ON garments(category);
CREATE INDEX idx_garments_authenticity_hash ON garments(authenticity_hash);
CREATE INDEX idx_garments_cardano_asset_ref ON garments(cardano_asset_ref) WHERE cardano_asset_ref IS NOT NULL;
CREATE INDEX idx_garments_is_active ON garments(is_active) WHERE is_active = TRUE;

-- Trigger to update updated_at
CREATE TRIGGER update_garments_updated_at
  BEFORE UPDATE ON garments
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Comments
COMMENT ON TABLE garments IS 'Garment registry with provenance and ownership tracking';
COMMENT ON COLUMN garments.authenticity_hash IS 'Immutable hash anchored to Cardano';
COMMENT ON COLUMN garments.public_esg_score IS 'Environmental, Social, Governance score (public)';
COMMENT ON COLUMN garments.physical_tag_id IS 'NFC/QR code on physical garment';
