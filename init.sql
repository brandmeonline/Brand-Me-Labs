-- init.sql - Database schema initialization for Brand.Me

-- scan_event table: records every scan with policy decision
CREATE TABLE IF NOT EXISTS scan_event (
    scan_id VARCHAR(255) PRIMARY KEY,
    scanner_user_id VARCHAR(255) NOT NULL,
    garment_id VARCHAR(255) NOT NULL,
    region_code VARCHAR(50),
    policy_version VARCHAR(100),
    resolved_scope VARCHAR(50),
    shown_facets JSONB,
    occurred_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- chain_anchor table: blockchain anchoring records
CREATE TABLE IF NOT EXISTS chain_anchor (
    scan_id VARCHAR(255) PRIMARY KEY,
    cardano_tx_hash VARCHAR(255),
    midnight_tx_hash VARCHAR(255),
    crosschain_root_hash VARCHAR(255),
    anchored_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (scan_id) REFERENCES scan_event(scan_id)
);

-- audit_log table: hash-chained audit trail with escalation support
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id VARCHAR(255) PRIMARY KEY,
    related_scan_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    decision_summary TEXT,
    decision_detail JSONB,
    risk_flagged BOOLEAN DEFAULT FALSE,
    escalated_to_human BOOLEAN DEFAULT FALSE,
    human_approver_id VARCHAR(255),
    prev_hash VARCHAR(255),
    entry_hash VARCHAR(255) NOT NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_scan_event_scanner ON scan_event(scanner_user_id);
CREATE INDEX IF NOT EXISTS idx_scan_event_garment ON scan_event(garment_id);
CREATE INDEX IF NOT EXISTS idx_scan_event_occurred ON scan_event(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_scan ON audit_log(related_scan_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_escalated ON audit_log(escalated_to_human, human_approver_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at DESC);

-- cubes table: Product Cube storage for all garments
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

-- Indexes for cube performance
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

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
