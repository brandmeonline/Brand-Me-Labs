-- Copyright (c) Brand.Me, Inc. All rights reserved.
--
-- Audit Log Table
-- Tamper-evident, hash-chained audit trail for all critical decisions

CREATE TABLE IF NOT EXISTS audit_log (
  -- Primary Key
  audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Related Entity
  related_scan_id UUID REFERENCES scan_event(scan_id) ON DELETE SET NULL,
  related_garment_id UUID REFERENCES garments(garment_id) ON DELETE SET NULL,
  related_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,

  -- Timestamp
  created_at TIMESTAMPTZ DEFAULT NOW(),

  -- Actor
  actor_type TEXT NOT NULL, -- 'system', 'governance_human', 'compliance_agent', 'policy_engine'
  actor_id UUID REFERENCES users(user_id) ON DELETE SET NULL, -- NULL for system actors

  -- Action
  action_type TEXT NOT NULL, -- 'scan', 'reveal', 'policy_check', 'escalation', 'ownership_transfer'
  action_summary TEXT NOT NULL, -- Human-readable summary

  -- Decision Details
  decision_summary TEXT NOT NULL,
  decision_detail JSONB NOT NULL,

  -- Risk & Escalation
  risk_flagged BOOLEAN DEFAULT FALSE,
  risk_level TEXT, -- 'low', 'medium', 'high', 'critical'
  escalated_to_human BOOLEAN DEFAULT FALSE,
  human_approver_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
  approval_status TEXT, -- 'pending', 'approved', 'rejected'

  -- Policy Reference
  policy_version TEXT NOT NULL, -- SHA256 hash of policy used
  policy_snapshot JSONB, -- Full policy snapshot for auditability

  -- Hash Chain (Tamper-Evident)
  prev_hash TEXT, -- Hash of previous audit log entry (NULL for first entry)
  entry_hash TEXT NOT NULL, -- SHA256 hash of this entry

  -- Blockchain Anchor Reference
  chain_anchor_id UUID REFERENCES chain_anchor(anchor_id) ON DELETE SET NULL,

  -- Compliance & Legal
  region_code TEXT NOT NULL DEFAULT 'us-east1',
  retention_policy TEXT DEFAULT 'standard', -- 'standard', 'extended', 'legal_hold'
  redacted BOOLEAN DEFAULT FALSE, -- True if PII has been redacted post-retention
  redacted_at TIMESTAMPTZ
);

-- Indexes
CREATE INDEX idx_audit_log_related_scan_id ON audit_log(related_scan_id);
CREATE INDEX idx_audit_log_related_garment_id ON audit_log(related_garment_id);
CREATE INDEX idx_audit_log_related_user_id ON audit_log(related_user_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at DESC);
CREATE INDEX idx_audit_log_actor_type ON audit_log(actor_type);
CREATE INDEX idx_audit_log_actor_id ON audit_log(actor_id);
CREATE INDEX idx_audit_log_action_type ON audit_log(action_type);
CREATE INDEX idx_audit_log_risk_flagged ON audit_log(risk_flagged) WHERE risk_flagged = TRUE;
CREATE INDEX idx_audit_log_escalated ON audit_log(escalated_to_human) WHERE escalated_to_human = TRUE;
CREATE INDEX idx_audit_log_policy_version ON audit_log(policy_version);
CREATE INDEX idx_audit_log_prev_hash ON audit_log(prev_hash) WHERE prev_hash IS NOT NULL;
CREATE INDEX idx_audit_log_entry_hash ON audit_log(entry_hash);
CREATE INDEX idx_audit_log_chain_anchor_id ON audit_log(chain_anchor_id);
CREATE INDEX idx_audit_log_region_code ON audit_log(region_code);
CREATE INDEX idx_audit_log_redacted ON audit_log(redacted) WHERE redacted = TRUE;

-- GIN indexes for JSONB queries
CREATE INDEX idx_audit_log_decision_detail_gin ON audit_log USING GIN (decision_detail);
CREATE INDEX idx_audit_log_policy_snapshot_gin ON audit_log USING GIN (policy_snapshot);

-- Composite index for actor audit trail
CREATE INDEX idx_audit_log_actor_trail ON audit_log(actor_id, created_at DESC) WHERE actor_id IS NOT NULL;

-- Comments
COMMENT ON TABLE audit_log IS 'Tamper-evident, hash-chained audit trail for all critical decisions';
COMMENT ON COLUMN audit_log.actor_type IS 'Type: system, governance_human, compliance_agent, policy_engine';
COMMENT ON COLUMN audit_log.action_type IS 'Type: scan, reveal, policy_check, escalation, ownership_transfer';
COMMENT ON COLUMN audit_log.prev_hash IS 'Hash of previous audit entry (creates tamper-evident chain)';
COMMENT ON COLUMN audit_log.entry_hash IS 'SHA256 hash of this entry (for chain integrity)';
COMMENT ON COLUMN audit_log.policy_snapshot IS 'Full policy snapshot at time of decision';
COMMENT ON COLUMN audit_log.redacted IS 'True if PII has been redacted for data retention compliance';

-- Constraint: Ensure actor_type is valid
ALTER TABLE audit_log
  ADD CONSTRAINT check_actor_type
  CHECK (actor_type IN ('system', 'governance_human', 'compliance_agent', 'policy_engine', 'ai_brain_hub'));

-- Constraint: Ensure action_type is valid
ALTER TABLE audit_log
  ADD CONSTRAINT check_action_type
  CHECK (action_type IN ('scan', 'reveal', 'policy_check', 'escalation', 'ownership_transfer', 'minting', 'consent_update'));

-- Constraint: Ensure risk_level is valid
ALTER TABLE audit_log
  ADD CONSTRAINT check_risk_level
  CHECK (risk_level IS NULL OR risk_level IN ('low', 'medium', 'high', 'critical'));

-- Constraint: Human approver must be set if escalated
ALTER TABLE audit_log
  ADD CONSTRAINT check_escalation_approver
  CHECK (
    (escalated_to_human = FALSE AND human_approver_id IS NULL)
    OR
    (escalated_to_human = TRUE)
  );

-- Function to compute entry hash
CREATE OR REPLACE FUNCTION compute_audit_entry_hash(
  p_audit_id UUID,
  p_created_at TIMESTAMPTZ,
  p_actor_type TEXT,
  p_action_type TEXT,
  p_decision_summary TEXT,
  p_decision_detail JSONB,
  p_policy_version TEXT,
  p_prev_hash TEXT
) RETURNS TEXT AS $$
BEGIN
  RETURN encode(
    digest(
      p_audit_id::TEXT ||
      p_created_at::TEXT ||
      p_actor_type ||
      p_action_type ||
      p_decision_summary ||
      p_decision_detail::TEXT ||
      p_policy_version ||
      COALESCE(p_prev_hash, ''),
      'sha256'
    ),
    'hex'
  );
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Trigger to automatically compute entry_hash before insert
CREATE OR REPLACE FUNCTION set_audit_entry_hash()
RETURNS TRIGGER AS $$
BEGIN
  NEW.entry_hash := compute_audit_entry_hash(
    NEW.audit_id,
    NEW.created_at,
    NEW.actor_type,
    NEW.action_type,
    NEW.decision_summary,
    NEW.decision_detail,
    NEW.policy_version,
    NEW.prev_hash
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER compute_audit_log_entry_hash
  BEFORE INSERT ON audit_log
  FOR EACH ROW
  EXECUTE FUNCTION set_audit_entry_hash();

-- View: Latest audit log entry (for chaining)
CREATE OR REPLACE VIEW v_latest_audit_log AS
SELECT audit_id, entry_hash, created_at
FROM audit_log
ORDER BY created_at DESC
LIMIT 1;

-- View: Audit trail verification status
CREATE OR REPLACE VIEW v_audit_chain_integrity AS
WITH chain_check AS (
  SELECT
    a1.audit_id,
    a1.entry_hash,
    a1.prev_hash,
    LAG(a1.entry_hash) OVER (ORDER BY a1.created_at) AS expected_prev_hash,
    CASE
      WHEN a1.prev_hash IS NULL THEN TRUE -- First entry
      WHEN a1.prev_hash = LAG(a1.entry_hash) OVER (ORDER BY a1.created_at) THEN TRUE
      ELSE FALSE
    END AS is_valid_link
  FROM audit_log a1
)
SELECT
  COUNT(*) AS total_entries,
  SUM(CASE WHEN is_valid_link THEN 1 ELSE 0 END) AS valid_links,
  SUM(CASE WHEN NOT is_valid_link THEN 1 ELSE 0 END) AS broken_links,
  CASE
    WHEN SUM(CASE WHEN NOT is_valid_link THEN 1 ELSE 0 END) = 0 THEN TRUE
    ELSE FALSE
  END AS chain_is_intact
FROM chain_check;

COMMENT ON VIEW v_audit_chain_integrity IS 'Verifies integrity of hash-chained audit log';
