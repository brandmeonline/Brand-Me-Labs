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

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
