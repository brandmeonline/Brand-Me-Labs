-- Copyright (c) Brand.Me, Inc. All rights reserved.
--
-- Users Table
-- Stores user accounts, personas, and trust scores

CREATE TABLE IF NOT EXISTS users (
  -- Primary Key
  user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Identity
  handle TEXT UNIQUE NOT NULL,
  display_name TEXT,
  email TEXT UNIQUE,

  -- Cardano DID (future support)
  did_cardano TEXT NULL,

  -- Region & Locale
  region_code TEXT NOT NULL DEFAULT 'us-east1',
  locale TEXT DEFAULT 'en-US',

  -- Persona Scores (ML-derived)
  persona_warm_cold NUMERIC(3,2) CHECK (persona_warm_cold >= 0 AND persona_warm_cold <= 1),
  persona_sport_couture NUMERIC(3,2) CHECK (persona_sport_couture >= 0 AND persona_sport_couture <= 1),

  -- Trust & Reputation
  trust_score NUMERIC(6,2) DEFAULT 0.00 CHECK (trust_score >= 0),

  -- OAuth Providers
  oauth_provider TEXT, -- 'google', 'github', 'twitter', etc.
  oauth_provider_id TEXT,

  -- Status
  is_active BOOLEAN DEFAULT TRUE,
  is_verified BOOLEAN DEFAULT FALSE,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  last_login_at TIMESTAMPTZ
);

-- Indexes for performance
CREATE INDEX idx_users_handle ON users(handle);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_did_cardano ON users(did_cardano) WHERE did_cardano IS NOT NULL;
CREATE INDEX idx_users_region_code ON users(region_code);
CREATE INDEX idx_users_oauth_provider ON users(oauth_provider, oauth_provider_id);
CREATE INDEX idx_users_is_active ON users(is_active) WHERE is_active = TRUE;

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Comments
COMMENT ON TABLE users IS 'User accounts with persona scores and Cardano DID support';
COMMENT ON COLUMN users.persona_warm_cold IS 'Persona dimension: 0=warm, 1=cold';
COMMENT ON COLUMN users.persona_sport_couture IS 'Persona dimension: 0=sport, 1=couture';
COMMENT ON COLUMN users.trust_score IS 'Reputation score (0-999.99)';
COMMENT ON COLUMN users.did_cardano IS 'Future: Cardano Decentralized Identifier';
