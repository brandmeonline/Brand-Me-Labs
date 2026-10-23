# brandme_core/domains/commerce

Reserved by the opus-foundation lane; implemented by the **commerce-agents** lane (W06/W07).
Stage log and evidence: `docs/build/status/opus-commerce-agents.md`.

- **Migrations:** V007 (as merged) and V015 (`brandme-data/spanner/migrations/`)
- **Entities (ch.03 §4):** AgentDelegation, Cart/CartLine, CheckoutQuote, ApprovalChallenge, PurchaseApproval,
  PurchaseOperation, Order/OrderLine, ReturnRequest, budget ledger, webhook receipts

How the foundation contract is met:
- **Identity:** the foundation `Principal` only. A first-party session acts as the member; any other caller is an
  agent bound to its one active delegation (agent scopes = token ∩ grant). No method takes a member id.
- **Object authorization:** foundation `authorize` (deny by default; another member's object is a 404).
- **Writes:** `store.run(fn)` instead of `run_command`, so the same retry-safe callbacks run on the in-memory store
  and on Spanner. Domain rows, the idempotency record and foundation `EventEnvelope`s commit together; callbacks
  never call a provider or a model. Commerce idempotency is scoped per (member, environment, operation,
  delegation, key), which `run_idempotent_command` does not express.
- **Events:** registered with closed payload schemas in `events.py` (`commerce.*`). Main's outbox worker publishes
  them once it imports `brandme_core.domains.commerce.events` (see `tests/test_commerce_events_catalog.py`).
- **My Data:** a native `DomainPrivacyHandler` (`privacy_handler.py`) registered with `register_domain` at package
  import. Every member/agent write calls `assert_processing_allowed` inside its own transaction.
- **API shapes:** routers in `brandme-gateway/src/routes/v1/` (unmounted); three lane routes still need adding to
  `packages/contracts` by its owner.
