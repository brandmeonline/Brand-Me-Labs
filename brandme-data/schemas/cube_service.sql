-- Brand.Me Cube Service Schema
-- Stores Product Cube data for all garments

CREATE TABLE IF NOT EXISTS cubes (
    cube_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Six faces stored as JSONB
    product_details JSONB,
    provenance JSONB,
    ownership JSONB,
    social_layer JSONB,
    esg_impact JSONB,
    lifecycle JSONB,

    -- Visibility settings per face
    visibility_settings JSONB DEFAULT '{"product_details": "public", "provenance": "public", "ownership": "private", "social_layer": "public", "esg_impact": "public", "lifecycle": "authenticated"}'::jsonb,

    -- Blockchain anchors
    blockchain_tx_hash TEXT,
    midnight_tx_hash TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_cubes_owner ON cubes(owner_id);
CREATE INDEX IF NOT EXISTS idx_cubes_created ON cubes(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cubes_blockchain ON cubes(blockchain_tx_hash) WHERE blockchain_tx_hash IS NOT NULL;

-- GIN indexes for JSONB queries
CREATE INDEX IF NOT EXISTS idx_product_details_gin ON cubes USING gin(product_details);
CREATE INDEX IF NOT EXISTS idx_provenance_gin ON cubes USING gin(provenance);

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_cubes_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS cubes_updated_at ON cubes;
CREATE TRIGGER cubes_updated_at
    BEFORE UPDATE ON cubes
    FOR EACH ROW
    EXECUTE FUNCTION update_cubes_updated_at();

-- Cube face access log (for policy auditing)
CREATE TABLE IF NOT EXISTS cube_face_access_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cube_id UUID NOT NULL,
    face_name TEXT NOT NULL,
    viewer_id UUID NOT NULL,
    owner_id UUID NOT NULL,
    policy_decision TEXT NOT NULL,
    request_id TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_cube FOREIGN KEY (cube_id) REFERENCES cubes(cube_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_access_log_cube ON cube_face_access_log(cube_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_access_log_viewer ON cube_face_access_log(viewer_id, timestamp DESC);
