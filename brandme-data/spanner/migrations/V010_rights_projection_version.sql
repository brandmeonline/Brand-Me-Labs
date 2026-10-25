-- Existing projections acquire version 1 on their next verified observation.
-- Separate from chain epoch: revocation can change state without changing epoch.
ALTER TABLE RightsEntitlements ADD COLUMN projection_version INT64;
