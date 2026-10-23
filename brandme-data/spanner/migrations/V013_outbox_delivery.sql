-- Keep dispatch selection within one environment. Each claim stores a fresh
-- fencing token in the existing lease_owner column; no old row is rewritten.
CREATE INDEX OutboxByEnvironmentStatus
  ON OutboxEvents(environment, shard, status, next_attempt_at)
  STORING (lease_expires_at, event_type);
