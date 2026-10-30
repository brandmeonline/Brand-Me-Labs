-- V016: transfer invites and fixed offer terms (lane: opus-midnight-rights).
--
-- The sender's app generates a high-entropy invite and gives it to the recipient
-- privately; only its SHA-256 digest is stored, never the invite. The offer terms
-- are fixed when the intent is created, so the sender's wallet proves exactly what
-- the member reviewed: offerTransfer(entitlementId, nonce, recipientCommitment,
-- expiry, termsDigest) (brandme-chain/contracts/src/brandme_rights.compact:309).
-- The recipient's wallet computes its commitment locally; no witness is stored.
--
-- Rows written before V016 have NULL in every new column. The command service
-- never binds a recipient to such an intent; it can only expire.
ALTER TABLE TransferIntents ADD COLUMN contract_address STRING(128);
ALTER TABLE TransferIntents ADD COLUMN invite_digest STRING(64);
ALTER TABLE TransferIntents ADD COLUMN offer_nonce STRING(64);
ALTER TABLE TransferIntents ADD COLUMN terms_digest STRING(64);
ALTER TABLE TransferIntents ADD COLUMN recipient_subject_ref STRING(128);

-- Member-scoped privacy export/erasure for both parties.
CREATE INDEX TransferIntentsBySender ON TransferIntents(from_subject_ref);
CREATE INDEX TransferIntentsByRecipient ON TransferIntents(recipient_subject_ref);
