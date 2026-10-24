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

## Assistant planner (dev form)

Assistant tasks (`assistant.task.*`) run in `brandme_core/orchestrator`. The deterministic planner is the
default. A model planner (`model_planner.py`, Anthropic Messages API) exists for development and demo only; it
is **not** a production integration, and its live test is `not_run` unless a dev key is present.

- **Selection** (`planner_from_env`, once at startup; `orchestrator/composition.py` wires it):
  `BRANDME_ASSISTANT_PLANNER=deterministic|anthropic`. Unset, a `BRANDME_DEV_ANTHROPIC_API_KEY` in development or
  demo selects the model planner. A dev key in sandbox or production, or with `BRANDME_MODE` unset, refuses to
  boot whatever the planner choice, and so does `anthropic` outside development and demo. `BRANDME_ASSISTANT_MODEL` (default `claude-opus-5-5`), `BRANDME_ASSISTANT_EFFORT` (`low|medium|high`,
  default `medium`), `BRANDME_ASSISTANT_EGRESS_PROXY` and `BRANDME_ASSISTANT_CA_BUNDLE` (explicit only; no ambient
  proxy), `BRANDME_LOG_REF_KEY` (base64url, at least 32 bytes, from the secret store). Brand.Me code reads no
  `ANTHROPIC_*` or proxy variable. The SDK still reads some itself (`ANTHROPIC_CUSTOM_HEADERS`, `ANTHROPIC_LOG`);
  none of it reaches the wire: the key and base URL are explicit, outgoing headers are rebuilt from the adapter's
  own values, the transport ignores ambient proxy settings and the SDK loggers stay at WARNING.
- **Authority:** the model only proposes one tool call per step. Runtime guards (approval stop, mode allowlist,
  duplicates, identifier provenance, the member's `budget_hint` price ceiling) and the audited MCP executor
  decide what runs; `purchase.execute` is never offered to the model, so buy-within-rules plans up to approval.
- **Data:** each step is one fresh request built from the task's own results (no conversation is kept). The goal
  is sent with emails, phone numbers, card numbers and labelled card security codes masked (a goal with card
  data is refused before a task exists); provider text is labelled untrusted; payee, delivery and hash fields
  are dropped. Model text and thinking are discarded unread.
- **Spend and logs:** tokens and cost are reserved before every call and settled after (per task, per member
  day, per environment day; in memory in this form). One closed-schema JSON line per model call, task end and
  tool call goes to stdout with keyed refs only.
- **HTTP:** every `assistant.task.create` answers 202 (a retried create 200); a model-planned task runs on a
  bounded background runner and a full runner is a retryable 503 `assistant_busy`.
- **Not done yet:** durable task, ledger and audit storage; a durable job queue; a non-dev key, DPA and retention
  review before any real member data is sent to a model provider.
