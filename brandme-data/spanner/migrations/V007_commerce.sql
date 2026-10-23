-- V007_commerce.sql — delegations, carts, quotes, approvals, budgets, purchases, orders (lane: opus-commerce-agents)
-- GoogleSQL for Cloud Spanner. Validated against cloud-spanner-emulator 1.5.58 (see lane status file).
-- Money = INT64 minor units + STRING(3) ISO currency; never FLOAT64.
-- Financial records are NOT interleaved under members so member deletion cannot erase them;
-- retention follows ch.03 §8 (jurisdiction/provider agreement).
-- Outbox/inbox tables belong to opus-foundation; commerce events are written there in the same transaction.

CREATE TABLE AgentDelegations (
  delegation_id STRING(36) NOT NULL,
  member_id STRING(36) NOT NULL,
  client_id STRING(256) NOT NULL,
  mode STRING(24) NOT NULL,
  scopes ARRAY<STRING(40)> NOT NULL,
  allowed_providers ARRAY<STRING(80)> NOT NULL,
  limits JSON,
  created_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  revoked_at TIMESTAMP,
  version INT64 NOT NULL,
  CONSTRAINT ck_delegation_mode CHECK (mode IN ('research', 'prepare', 'buy_within_rules')),
  CONSTRAINT ck_delegation_expiry CHECK (expires_at > created_at),
) PRIMARY KEY (delegation_id);

CREATE INDEX AgentDelegationsByMember ON AgentDelegations (member_id, expires_at DESC);

CREATE TABLE Carts (
  cart_id STRING(36) NOT NULL,
  member_id STRING(36) NOT NULL,
  provider_id STRING(80) NOT NULL,
  merchant_id STRING(256) NOT NULL,
  provider_cart_ref STRING(256) NOT NULL,
  revision INT64 NOT NULL,
  status STRING(16) NOT NULL,
  created_by_client STRING(256) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_cart_status CHECK (status IN ('draft', 'quoted', 'abandoned')),
) PRIMARY KEY (cart_id);

CREATE INDEX CartsByMember ON Carts (member_id, updated_at DESC);

CREATE TABLE CartLines (
  cart_id STRING(36) NOT NULL,
  variant_id STRING(36) NOT NULL,
  source_variant_ref STRING(256) NOT NULL,
  quantity INT64 NOT NULL,
  CONSTRAINT ck_cart_qty CHECK (quantity BETWEEN 1 AND 99),
) PRIMARY KEY (cart_id, variant_id),
  INTERLEAVE IN PARENT Carts ON DELETE CASCADE;

-- Immutable after insert. quote_hash = sha256(RFC 8785 material document, domain brandme.checkout_quote v1).
CREATE TABLE CheckoutQuotes (
  quote_id STRING(36) NOT NULL,
  member_id STRING(36) NOT NULL,
  environment STRING(16) NOT NULL,
  provider_id STRING(80) NOT NULL,
  merchant_id STRING(256) NOT NULL,
  payee_ref STRING(256) NOT NULL,
  cart_id STRING(36) NOT NULL,
  cart_revision INT64 NOT NULL,
  currency STRING(3) NOT NULL,
  subtotal_minor INT64 NOT NULL,
  tax_minor INT64 NOT NULL,
  shipping_minor INT64 NOT NULL,
  discount_minor INT64 NOT NULL,
  total_minor INT64 NOT NULL,
  delivery_ref STRING(256) NOT NULL,
  checkout_reference STRING(512) NOT NULL,
  terms_hash STRING(128) NOT NULL,
  quote_hash STRING(128) NOT NULL,
  hash_domain_version STRING(16) NOT NULL,
  material_document JSON NOT NULL,
  source_evidence_ref STRING(256),
  issued_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  CONSTRAINT ck_quote_amounts CHECK (subtotal_minor >= 0 AND tax_minor >= 0 AND shipping_minor >= 0
    AND discount_minor >= 0 AND total_minor >= 0),
  CONSTRAINT ck_quote_total CHECK (total_minor = subtotal_minor + tax_minor + shipping_minor - discount_minor),
  CONSTRAINT ck_quote_expiry CHECK (expires_at > issued_at),
) PRIMARY KEY (quote_id);

CREATE INDEX CheckoutQuotesByHash ON CheckoutQuotes (quote_hash);

CREATE TABLE QuoteLines (
  quote_id STRING(36) NOT NULL,
  variant_id STRING(36) NOT NULL,
  source_variant_ref STRING(256) NOT NULL,
  quantity INT64 NOT NULL,
  unit_price_minor INT64 NOT NULL,
  line_total_minor INT64 NOT NULL,
  category STRING(80),
  CONSTRAINT ck_quote_line CHECK (quantity BETWEEN 1 AND 99 AND unit_price_minor >= 0
    AND line_total_minor = unit_price_minor * quantity),
) PRIMARY KEY (quote_id, variant_id),
  INTERLEAVE IN PARENT CheckoutQuotes ON DELETE CASCADE;

CREATE TABLE ApprovalChallenges (
  challenge_id STRING(36) NOT NULL,
  member_id STRING(36) NOT NULL,
  operation_id STRING(36) NOT NULL,
  quote_id STRING(36) NOT NULL,
  quote_hash STRING(128) NOT NULL,
  nonce_hash STRING(128) NOT NULL,
  delegation_ref STRING(36),
  issued_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  used BOOL NOT NULL,
) PRIMARY KEY (challenge_id);

CREATE TABLE PurchaseApprovals (
  approval_id STRING(36) NOT NULL,
  member_id STRING(36) NOT NULL,
  delegation_ref STRING(36),
  quote_id STRING(36) NOT NULL,
  quote_hash STRING(128) NOT NULL,
  merchant_id STRING(256) NOT NULL,
  allowed_total_minor INT64 NOT NULL,
  currency STRING(3) NOT NULL,
  nonce STRING(128) NOT NULL,
  issued_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  assurance_level STRING(24) NOT NULL,
  method STRING(24) NOT NULL,
  materiality_rule STRING(64) NOT NULL,
  protocol_payload_hash STRING(128),
  state STRING(16) NOT NULL,
  CONSTRAINT ck_approval_state CHECK (state IN ('issued', 'consumed', 'void')),
  CONSTRAINT ck_approval_method CHECK (method IN ('trusted_surface', 'ap2_mandate')),
  CONSTRAINT ck_ap2_has_payload CHECK (method != 'ap2_mandate' OR protocol_payload_hash IS NOT NULL),
) PRIMARY KEY (approval_id);

CREATE UNIQUE INDEX PurchaseApprovalsByNonce ON PurchaseApprovals (member_id, nonce);

-- Member trusted-surface public keys for AP2 mandate verification (public JWK only).
CREATE TABLE MemberSurfaceKeys (
  member_id STRING(36) NOT NULL,
  key_thumbprint STRING(64) NOT NULL,
  public_jwk JSON NOT NULL,
  registered_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  revoked_at TIMESTAMP,
) PRIMARY KEY (member_id, key_thumbprint);

CREATE TABLE Ap2UsedMandates (
  mandate_digest STRING(128) NOT NULL,
  approval_id STRING(36) NOT NULL,
  used_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (mandate_digest);

CREATE TABLE PurchaseOperations (
  operation_id STRING(36) NOT NULL,
  member_id STRING(36) NOT NULL,
  delegation_id STRING(36),
  client_id STRING(256) NOT NULL,
  quote_id STRING(36) NOT NULL,
  quote_hash STRING(128) NOT NULL,
  approval_id STRING(36),
  provider_id STRING(80) NOT NULL,
  state STRING(24) NOT NULL,
  provider_idempotency_key STRING(128) NOT NULL,
  order_id STRING(36),
  reason_code STRING(80),
  attempts INT64 NOT NULL,
  version INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  CONSTRAINT ck_operation_state CHECK (state IN ('draft', 'quoting', 'awaiting_approval', 'approved', 'submitting',
    'outcome_unknown', 'accepted', 'rejected', 'cancel_requested', 'cancelled', 'partially_fulfilled', 'fulfilled',
    'return_requested', 'partially_refunded', 'refunded', 'disputed')),
) PRIMARY KEY (operation_id);

CREATE UNIQUE INDEX PurchaseOperationsByProviderKey ON PurchaseOperations (provider_id, provider_idempotency_key);
CREATE INDEX PurchaseOperationsByMember ON PurchaseOperations (member_id, created_at DESC);
-- Reconciliation worker scan: unknown outcomes and in-flight submissions.
CREATE INDEX PurchaseOperationsByState ON PurchaseOperations (state, updated_at);
CREATE INDEX PurchaseOperationsByQuoteHash ON PurchaseOperations (quote_hash, state);

-- Reservation/consumption/credit ledger for delegated budgets. Checked and written in the
-- same read/write transaction as approval consumption and the submission intent.
CREATE TABLE DelegationBudgetEntries (
  delegation_id STRING(36) NOT NULL,
  entry_id STRING(36) NOT NULL,
  operation_id STRING(36) NOT NULL,
  kind STRING(16) NOT NULL,
  state STRING(16) NOT NULL,
  amount_minor INT64 NOT NULL,
  currency STRING(3) NOT NULL,
  created_at TIMESTAMP NOT NULL,
  CONSTRAINT ck_budget_kind CHECK (kind IN ('reservation', 'credit')),
  CONSTRAINT ck_budget_state CHECK (state IN ('reserved', 'consumed', 'released', 'credited')),
  CONSTRAINT ck_budget_amount CHECK (amount_minor > 0),
) PRIMARY KEY (delegation_id, entry_id);

CREATE INDEX DelegationBudgetEntriesByOperation ON DelegationBudgetEntries (operation_id);

CREATE TABLE Orders (
  order_id STRING(36) NOT NULL,
  member_id STRING(36) NOT NULL,
  operation_id STRING(36) NOT NULL,
  provider_id STRING(80) NOT NULL,
  merchant_id STRING(256) NOT NULL,
  provider_order_ref STRING(256) NOT NULL,
  quote_hash STRING(128) NOT NULL,
  idempotency_key STRING(128) NOT NULL,
  order_status STRING(24) NOT NULL,
  payment_status STRING(24) NOT NULL,
  fulfillment_status STRING(24) NOT NULL,
  currency STRING(3) NOT NULL,
  total_minor INT64 NOT NULL,
  refunded_minor INT64 NOT NULL,
  evidence_refs ARRAY<STRING(256)> NOT NULL,
  last_observed_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  version INT64 NOT NULL,
  CONSTRAINT ck_order_refund CHECK (refunded_minor >= 0 AND refunded_minor <= total_minor),
  CONSTRAINT ck_payment_status CHECK (payment_status IN ('unknown', 'authorized', 'captured', 'partially_refunded',
    'refunded', 'failed')),
  CONSTRAINT ck_fulfillment_status CHECK (fulfillment_status IN ('unfulfilled', 'partially_fulfilled', 'fulfilled')),
) PRIMARY KEY (order_id);

CREATE UNIQUE INDEX OrdersByProviderRef ON Orders (provider_id, provider_order_ref);
CREATE INDEX OrdersByMember ON Orders (member_id, created_at DESC);

CREATE TABLE OrderLines (
  order_id STRING(36) NOT NULL,
  source_variant_ref STRING(256) NOT NULL,
  variant_id STRING(36),
  quantity_ordered INT64 NOT NULL,
  quantity_shipped INT64 NOT NULL,
  quantity_delivered INT64 NOT NULL,
  quantity_returned INT64 NOT NULL,
  exchanged_from_ref STRING(256),
  CONSTRAINT ck_order_line_qty CHECK (quantity_ordered >= 1 AND quantity_shipped BETWEEN 0 AND quantity_ordered
    AND quantity_delivered BETWEEN 0 AND quantity_ordered AND quantity_returned BETWEEN 0 AND quantity_ordered),
) PRIMARY KEY (order_id, source_variant_ref),
  INTERLEAVE IN PARENT Orders ON DELETE NO ACTION;

CREATE TABLE ReturnRequests (
  return_id STRING(36) NOT NULL,
  order_id STRING(36) NOT NULL,
  member_id STRING(36) NOT NULL,
  source_variant_ref STRING(256) NOT NULL,
  quantity INT64 NOT NULL,
  provider_reference STRING(256),
  status STRING(24) NOT NULL,
  requested_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT ck_return_status CHECK (status IN ('handoff', 'return_requested', 'received', 'rejected')),
) PRIMARY KEY (return_id);

CREATE INDEX ReturnRequestsByOrder ON ReturnRequests (order_id);

-- Idempotency scope (principal, environment, operation, delegation, key) per ch.03 §6.
CREATE TABLE CommerceIdempotencyKeys (
  member_id STRING(36) NOT NULL,
  environment STRING(16) NOT NULL,
  operation STRING(64) NOT NULL,
  delegation_scope STRING(36) NOT NULL,
  idempotency_key STRING(128) NOT NULL,
  request_digest STRING(128) NOT NULL,
  result_ref STRING(36) NOT NULL,
  created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (member_id, environment, operation, delegation_scope, idempotency_key);
