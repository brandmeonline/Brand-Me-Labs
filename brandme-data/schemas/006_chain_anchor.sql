-- Copyright (c) Brand.Me, Inc. All rights reserved.
--
-- Chain Anchor Table
-- Stores blockchain transaction references linking Cardano and Midnight chains

CREATE TABLE IF NOT EXISTS chain_anchor (
  -- Primary Key
  anchor_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Foreign Key
  scan_id UUID NOT NULL REFERENCES scan_event(scan_id) ON DELETE CASCADE,

  -- Cardano Chain (Public)
  cardano_tx_hash TEXT,
  cardano_payload_ref TEXT, -- Reference to payload in Cardano tx
  cardano_block_number BIGINT,
  cardano_slot_number BIGINT,

  -- Midnight Chain (Private)
  midnight_tx_hash TEXT,
  midnight_payload_ref TEXT, -- Reference to payload in Midnight tx
  midnight_block_number BIGINT,

  -- Cross-Chain Verification
  crosschain_root_hash TEXT NOT NULL, -- Cryptographic link between chains
  crosschain_proof JSONB, -- Merkle proof or similar

  -- Verification Status
  is_verified BOOLEAN DEFAULT FALSE,
  verified_at TIMESTAMPTZ,
  verification_method TEXT, -- 'cross_chain_verifier', 'manual', etc.

  -- Metadata
  anchor_type TEXT DEFAULT 'scan_event', -- 'scan_event', 'ownership_transfer', 'minting'

  -- Timestamps
  anchored_at TIMESTAMPTZ DEFAULT NOW(),
  last_verified_at TIMESTAMPTZ
);

-- Indexes
CREATE INDEX idx_chain_anchor_scan_id ON chain_anchor(scan_id);
CREATE INDEX idx_chain_anchor_cardano_tx ON chain_anchor(cardano_tx_hash);
CREATE INDEX idx_chain_anchor_midnight_tx ON chain_anchor(midnight_tx_hash);
CREATE INDEX idx_chain_anchor_crosschain_root ON chain_anchor(crosschain_root_hash);
CREATE INDEX idx_chain_anchor_is_verified ON chain_anchor(is_verified);
CREATE INDEX idx_chain_anchor_anchored_at ON chain_anchor(anchored_at DESC);
CREATE INDEX idx_chain_anchor_anchor_type ON chain_anchor(anchor_type);

-- GIN index for crosschain_proof JSONB
CREATE INDEX idx_chain_anchor_proof_gin ON chain_anchor USING GIN (crosschain_proof);

-- Comments
COMMENT ON TABLE chain_anchor IS 'Blockchain transaction references linking Cardano and Midnight';
COMMENT ON COLUMN chain_anchor.cardano_tx_hash IS 'Cardano transaction hash (public chain)';
COMMENT ON COLUMN chain_anchor.midnight_tx_hash IS 'Midnight transaction hash (private chain)';
COMMENT ON COLUMN chain_anchor.crosschain_root_hash IS 'Cryptographic link between both chains';
COMMENT ON COLUMN chain_anchor.crosschain_proof IS 'Merkle proof or verification data';
COMMENT ON COLUMN chain_anchor.is_verified IS 'True if cross-chain verification succeeded';

-- Constraint: At least one chain reference must be present
ALTER TABLE chain_anchor
  ADD CONSTRAINT check_at_least_one_chain
  CHECK (cardano_tx_hash IS NOT NULL OR midnight_tx_hash IS NOT NULL);

-- Unique constraint: One anchor per scan_id and anchor_type
CREATE UNIQUE INDEX idx_chain_anchor_unique_scan_type
  ON chain_anchor(scan_id, anchor_type);
