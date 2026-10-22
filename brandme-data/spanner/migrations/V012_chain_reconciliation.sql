-- Leased read-only reconciliation and projection progress. Legacy owned rows
-- are due immediately; no transaction is ever resubmitted by this worker.
ALTER TABLE ChainOperations ADD COLUMN reconciliation_lease_id STRING(36);
ALTER TABLE ChainOperations ADD COLUMN reconciliation_lease_until TIMESTAMP;
ALTER TABLE ChainOperations ADD COLUMN reconciliation_attempts INT64;
ALTER TABLE ChainOperations ADD COLUMN projection_completed_at TIMESTAMP;
ALTER TABLE ChainOperations ADD COLUMN projection_outcome STRING(32);
CREATE INDEX ChainOperationsForReconciliation
  ON ChainOperations(environment, network, contract_address, projection_completed_at, next_check_at)
  STORING (state, owner_ref, tx_id, reconciliation_lease_until, reconciliation_attempts);
