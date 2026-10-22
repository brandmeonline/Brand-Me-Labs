-- Durable, private application ownership and transaction observation timestamps.
-- Legacy rows remain unowned and cannot be served or executed as member commands.
ALTER TABLE ChainOperations ADD COLUMN environment STRING(16);
ALTER TABLE ChainOperations ADD COLUMN owner_ref STRING(36);
ALTER TABLE ChainOperations ADD COLUMN observed_at TIMESTAMP;
DROP INDEX ChainOperationsByIdempotencyKey;
CREATE UNIQUE NULL_FILTERED INDEX ChainOperationsByScopedKey
  ON ChainOperations(environment, owner_ref, network, contract_address, idempotency_key);

-- A row lock makes conflicting subject commands serialize even when neither
-- transaction has inserted its operation yet. Terminal operations allow reuse.
CREATE TABLE ChainOperationSubjects (
  environment STRING(16) NOT NULL,
  network STRING(16) NOT NULL,
  contract_address STRING(128) NOT NULL,
  subject_ref STRING(128) NOT NULL,
  operation_id STRING(36) NOT NULL,
) PRIMARY KEY (environment, network, contract_address, subject_ref);
