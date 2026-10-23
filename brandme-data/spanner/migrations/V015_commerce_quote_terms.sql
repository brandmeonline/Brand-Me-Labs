-- V015: commerce round 2 (lane: opus-commerce-agents). V007 is unchanged; it was applied
-- as merged. This adds what round 2 needs on top of it.

-- Return/recurrence terms; terms_hash is their digest and a material quote term.
-- Existing rows (written before this migration) get '{}', which the store refuses to decode:
-- such a quote's terms were never recorded, so it can only be re-quoted, never approved.
-- Quotes expire within minutes, so no live quote is lost in practice.
ALTER TABLE CheckoutQuotes ADD COLUMN terms JSON NOT NULL DEFAULT (JSON '{}');
ALTER TABLE CheckoutQuotes ALTER COLUMN terms DROP DEFAULT;

-- Member-scoped privacy export/erasure reads.
CREATE INDEX CheckoutQuotesByMember ON CheckoutQuotes (member_id);
CREATE INDEX ApprovalChallengesByMember ON ApprovalChallenges (member_id);

-- Revocation cancels a grant's unsent work.
CREATE INDEX PurchaseOperationsByDelegation ON PurchaseOperations (delegation_id, state);
