# PLAN — End-to-End + ACP / AP2 / A2A

> Companion to `CLAUDE.md` (which describes today's reality). This plan
> describes the path from today's emulator-only consent/policy slice to a
> working agent-commerce platform that issues mandates, settles payments on
> Midnight + Cardano, and speaks A2A to peer agents.

## 1. Context

You want Brand.Me to actually run end-to-end (today only the consent /
policy / provenance slice does), and you want that end-to-end stack to
support three live 2025–2026 protocols:

- **A2A (Agent-to-Agent)** — Linux-Foundation-governed peer-discovery and
  task protocol. v1.0 (early 2026) introduced **Signed AgentCards**.
- **AP2 (Agent Payments Protocol)** — ships as a formal **A2A extension**.
  Three W3C-VC mandates: **Intent**, **Cart**, **Payment**.
- **ACP (Agentic Commerce Protocol)** — Stripe + OpenAI's open standard for
  buyer/agent/merchant flows. Latest spec (2026-04-17) supports REST or
  native MCP transport.

The intended outcome is a platform where: an external buyer agent
discovers Brand.Me via a signed AgentCard, negotiates a transaction
(rental / repair / dissolve / resale) under an Intent Mandate, the user
signs a Cart Mandate, payment settles privately on Midnight with the
cross-chain root anchored to Cardano, and the audit log carries the
full mandate chain. Today none of this exists in code.
## 2. Today's reality (one-paragraph recap)

Real: `brain`, `policy` (Spanner consent graph + provenance), `brandme_core`
shared lib, gateway framework, region YAMLs. Stub or unverified:
`orchestrator` (hardcoded `cardano_tx_*` strings), `cube` (startup
unverified), `governance` (no approve/deny endpoint), `compliance`
(`MIDNIGHT_ENABLED=false`), `knowledge` (init-only), `brandme-chain` Cardano
real impl is **commented out** at `brandme-chain/src/services/cardano-tx-builder.ts:77-155`,
Midnight is full stub awaiting IOG SDK. No `payment`, `mandate`, `settle`,
`VC`, `AgentCard`, `A2A`, `AP2`, `ACP` references anywhere in code. The
`did_cardano` column on `users` exists but is never populated. See
`CLAUDE.md` for full per-service status.
## 3. North-star architecture

```
                          External buyer agent (ChatGPT, Coinbase, etc.)
                                        │  A2A (Signed AgentCard, tasks/SSE)
                                        ▼
                          ┌──────────────────────────────┐
                          │  brandme-gateway             │
                          │  /.well-known/agent-card.json│
                          │  /a2a/v1/tasks/{send,sub}    │
                          │  /acp/v1/{cart,checkout}     │  ◄── ACP merchant surface
                          └───────────────┬──────────────┘
                                          │ (MCP transport)
                                          ▼
        ┌───────────────────────────────────────────────────────────────┐
        │  MCP Tool Executor (consent + ESG + human-approval gates)     │
        │  - existing 7 tools                                           │
        │  - NEW: acp.cart.{create,update}, acp.checkout.complete,      │
        │         ap2.mandate.{create,sign,verify}                      │
        └───────────────┬───────────────────────────────────────────────┘
                        │
       ┌────────────────┼────────────────────────────────────┐
       ▼                ▼                                    ▼
 ┌───────────┐   ┌─────────────────┐                ┌──────────────────┐
 │  policy   │   │ identity        │                │ commerce-agent   │
 │ consent   │   │ DID + VC issuer │                │ Cart Mandate flow│
 │ provenance│   │ AP2 mandate VCs │                │ ACP price/fulfil │
 └───────────┘   └────────┬────────┘                └────────┬─────────┘
                          │                                  │
                          ▼                                  ▼
                 ┌──────────────────────────────────────────────┐
                 │  payments-agent  (NEW service)              │
                 │  Payment Mandate → Midnight shielded TX     │
                 │  → Cardano cross-chain anchor               │
                 └────────────────────┬────────────────────────┘
                                      ▼
                  ┌───────────────────────────────────────┐
                  │  brandme-chain                        │
                  │  cardano-tx-builder (uncomment real)  │
                  │  midnight-client (real SDK when avail)│
                  │  → writes chain_anchor row            │
                  └───────────────────────────────────────┘
```

Three new architectural pieces:

1. **AgentCard / A2A surface on the gateway** — `/.well-known/agent-card.json`
   (signed JWS), plus `/a2a/v1/tasks/send` and `/a2a/v1/tasks/sendSubscribe`
   (SSE). Maps an inbound A2A task onto the existing
   `scan_agent → identity_agent → policy_agent → compliance_agent` chain.
2. **AP2 mandate engine inside `brandme-agents/identity`** — issues + verifies
   the three VCs (Intent, Cart, Payment), backed by a new `mandates` table.
   Reuses the unpopulated `did_cardano` column for issuer/holder DIDs.
3. **`payments-agent` service** — orchestrates Cart-Mandate-confirmed →
   Midnight shielded TX → Cardano anchor → settlement record. Uses the
   existing `chain_anchor` table (already has `cardano_tx_hash`,
   `midnight_tx_hash`, `crosschain_root_hash` columns) as the settlement
   commitment.
## 4. How the three protocols map onto existing scaffolding

### A2A → existing agent state machine

| A2A concept | Existing primitive | What's missing |
|---|---|---|
| AgentCard JSON | n/a | New file `brandme-gateway/src/routes/agentCard.ts` serving `/.well-known/agent-card.json`. |
| Signed AgentCard (v1.0) | `users.did_cardano` column reserved | Issuer key + JWS signing util; populate `did:web:brandme.io`. |
| Task lifecycle | `agentic/orchestrator/agents.py` `AgentState` (request_id, scan_id, etc.) | Map states to A2A `pending / in-progress / completed / failed`; return task object. |
| SSE streaming | none | New `/a2a/v1/tasks/sendSubscribe` route with `text/event-stream`. |
| Extensions field | none | Declare `https://ap2-protocol.org/extension/v1` in AgentCard. |

### AP2 → identity + chain layers

| AP2 concept | Existing primitive | What's missing |
|---|---|---|
| Holder/Issuer DID | `users.did_cardano TEXT NULL` | DID provisioning on user signup; `did:cardano` resolver or `did:web` for Brand.Me itself. |
| W3C VC envelope | `brandme_core/zk/proof_of_ownership.py` (commitment-based) | JSON-LD or JWT-VC issuer/verifier in `brandme-agents/identity`. Don't reuse ZK module — different primitive. |
| Intent Mandate | n/a | New table `mandates` (type=`intent`); created when an external agent first connects. |
| Cart Mandate | MCP transactional tools already gate `is_transactional=True` and `requires_human_review=True` | Cart-Mandate VC issued at user-approval time, signed by user's key. |
| Payment Mandate | n/a | Issued by Brand.Me to acquirer/settlement after Cart Mandate confirmed. |

### ACP → MCP tool layer

| ACP concept | Existing primitive | What's missing |
|---|---|---|
| Product feed | `search_wardrobe`, `get_cube_details` | ACP-shaped feed schema (`acp.feed`) advertising lifecycle services as products. |
| Cart create / update | n/a | New MCP tools `acp.cart.create`, `acp.cart.update` writing to `agent_carts` table. |
| Checkout complete | `initiate_rental`, `list_for_resale`, `request_dissolve` | Wrap each in an `acp.checkout.complete` adapter that produces a Cart Mandate then routes to payments-agent. |
| Scoped tokens | gateway JWT middleware | Token-scoping rules per ACP capability (read-only vs cart vs checkout). |
| Payment handlers | n/a | Pluggable handler interface; first impl = Midnight + Cardano. |
| MCP transport | `MCPToolExecutor` (real, logs to Spanner) | Mount the executor on an MCP server endpoint (currently commented out in compose). |

### Settlement → existing `chain_anchor` table

`brandme-data/schemas/006` already has the right shape:
`anchor_id, scan_id, cardano_tx_hash, midnight_tx_hash, crosschain_root_hash,
crosschain_proof, is_verified`. The settlement workflow writes one
`chain_anchor` row per completed Payment Mandate. Add `payment_id` FK to
make it explicit, but the cross-chain primitive itself is already there.

`brandme-chain/src/services/midnight-client.ts:258-269` already has
`anchorToCardano(midnightTxHash, cardanoTxHash)` skeleton — keep that
shape; replace stub innards when SDK lands.

`brandme-agents/compliance/src/lifecycle/burn_proof.py` already has a
working pattern (`allow_stub_fallback`, `require_midnight`) — copy it for
the new `payments-agent`.
## 5. Phase plan

Sequenced so each phase ends in something demonstrable. Earlier phases
unblock later ones; do not reorder.

### Phase 0 — Make the existing slice honest (1 week)

Goal: every "REAL" claim in `CLAUDE.md` survives `docker-compose up && pytest`
on a fresh clone.

- Verify `brandme-cube` actually starts (`PRODUCT_CUBE_SUMMARY.md` says
  untested). Fix any startup errors.
- Replace cube `tests/test_api.py` `test_placeholder()` with at least one
  real round-trip test against the Spanner emulator.
- Delete `brandme_gateway/` (now an orphan — see CLAUDE.md kill-list note;
  rateLimiter already moved out).
- Pick one: archive `docs/next_steps/ROADMAP.md` (16 months stale) **or**
  rewrite it to point at this PLAN.md.

### Phase 1 — Real Cardano provenance, one path end-to-end (2 weeks)

Goal: a single garment scan produces a real Cardano TX hash retrievable via
Blockfrost.

- Uncomment the real implementation at
  `brandme-chain/src/services/cardano-tx-builder.ts:77-155` (CIP-25 + Brand.Me
  metadata label 1967). Resolve any
  `cardano-serialization-lib-nodejs@12.0.0` API drift.
- Replace orchestrator stub at
  `brandme-core/orchestrator/main.py:99` (`f"cardano_tx_{transfer_id[:16]}"`)
  with a real call to `brandme-chain` `POST /tx/cardano`.
- Add `tests/test_cardano_anchor.py` that hits a Cardano **preprod** testnet
  with real Blockfrost creds and verifies the TX appears.
- Update `chain_anchor` writes to record the real hash + verification status.

Exit criteria: one happy-path scan writes a `chain_anchor` row with a real
preprod TX hash that round-trips through Blockfrost.

### Phase 2 — A2A AgentCard + task surface (2 weeks)

Goal: an external A2A client can discover Brand.Me, send a task, and get
back the same result the existing scan flow already produces.

New / changed files:

- `brandme-gateway/src/routes/agentCard.ts` — serves
  `/.well-known/agent-card.json` (capabilities, supported MCP tools,
  `extensions: ["https://ap2-protocol.org/extension/v1"]`).
- `brandme-gateway/src/routes/a2a.ts` — `POST /a2a/v1/tasks/send` and
  `POST /a2a/v1/tasks/sendSubscribe` (SSE).
- `brandme-gateway/src/services/agentCardSigner.ts` — JWS over the AgentCard
  using a Brand.Me service key. Use `did:web:brandme.io` for v1; revisit
  `did:cardano` in Phase 3.
- `brandme-agents/agentic/orchestrator/a2a_adapter.py` — translate inbound
  A2A task → existing `AgentState`, stream lifecycle states back as SSE
  events.

Tests: `tests/test_a2a_task.py` driving an A2A task through the existing
scan flow.

Exit criteria: a peer A2A client (Google's reference impl or
`a2aproject/A2A` SDK) can run a happy-path scan task end-to-end.

### Phase 3 — DIDs + VC issuer/verifier (2 weeks)

Goal: every user has a `did_cardano`; Brand.Me can issue and verify a W3C
VC over JWS.

- Pick DID method. Recommend `did:cardano` for users (existing column,
  on-chain provenance) and `did:web:brandme.io` for the platform itself.
  Open question — see §7.
- `brandme-agents/identity/src/credentials.py` (new) — VC issuer/verifier
  with JWT-VC encoding (start there, not JSON-LD; less tooling friction).
- Populate `users.did_cardano` on signup. Backfill existing users with a
  one-shot script.
- `tests/test_vc_round_trip.py` — issue a sample VC, verify signature,
  reject tampered payload.

Exit criteria: any user can be issued a verifiable credential bound to
their DID; verification works without trusting the issuer's logs.

### Phase 4 — AP2 mandates (3 weeks)

Goal: Intent, Cart, Payment mandates are issued, signed, stored, and
verified per AP2 spec.

- Add `mandates` table (schema in §6).
- `brandme-agents/identity/src/mandates.py` (new) — three mandate-type
  builders/verifiers wrapping the VC primitive from Phase 3.
- New MCP tools (extend `brandme_core/mcp/tools.py`):
  - `ap2.mandate.create_intent` — agent declares purchase authority.
  - `ap2.mandate.confirm_cart` — user signs final basket (Brand.Me holds
    the user key only with explicit consent; **otherwise** redirect to
    user's wallet for client-side signing — see §7).
  - `ap2.mandate.issue_payment` — Brand.Me-issued, rails-facing.
- Wire `requires_human_review=True` on Cart Mandate creation to the
  existing governance escalation flow (`brandme-governance` will need its
  approve/deny endpoint, currently absent — see Phase 0).

Exit criteria: full mandate chain (Intent → Cart → Payment) for a rental
flow, all three VCs verifiable independently.

### Phase 5 — ACP merchant surface (3 weeks)

Goal: an external buyer agent (e.g. ChatGPT with Instant Checkout) can
discover Brand.Me's lifecycle services and complete a checkout.

- `brandme-gateway/src/routes/acp.ts` — REST endpoints per
  Stripe/OpenAI ACP spec (cart, feed, orders, capabilities,
  authentication). Where ACP allows MCP transport, route through the
  existing `MCPToolExecutor`.
- `brandme_core/mcp/acp_tools.py` (new) — `acp.cart.create`,
  `acp.cart.update`, `acp.checkout.complete`. Each `acp.checkout.complete`
  emits an Intent Mandate (Phase 4) and routes to `payments-agent`
  (Phase 6).
- ACP **product feed** = lifecycle services (rental, repair, dissolve,
  resale). Reuse existing tool definitions; expose ACP shapes alongside.
- Token scoping: extend `brandme-gateway/src/middleware/auth.ts` with ACP
  capability scopes (`acp:read`, `acp:cart`, `acp:checkout`).

Exit criteria: a documented ACP integration test using the Stripe ACP
test harness completes a rental order against Brand.Me preprod.

### Phase 6 — Payment settlement on Midnight + Cardano (4 weeks, blocked on Midnight SDK)

Goal: a Payment Mandate triggers a real shielded settlement on Midnight,
anchored to Cardano, recorded in `chain_anchor`.

- New service `brandme-agents/payments/` (FastAPI, port 8008). Pattern off
  `brandme-agents/compliance/` — same `allow_stub_fallback` /
  `require_midnight` toggles.
- Implement `brandme-chain/src/services/midnight-client.ts`
  `buildShieldedTx` against the real Midnight SDK once IOG ships it.
  Until then, gate the entire phase behind
  `MIDNIGHT_ENABLED=true`; default stays `false`.
- Use the existing `anchorToCardano(midnightTxHash, cardanoTxHash)`
  skeleton at `brandme-chain/src/services/midnight-client.ts:258-269`.
- Add `agent_payments` and `settlement_records` tables (§6); link to
  `chain_anchor.anchor_id`.
- `audit_log.chain_anchor_id` already exists — populate it for every
  settlement.

Exit criteria: a Cart Mandate produces a Midnight shielded TX (or stub
when SDK absent), a Cardano anchor TX, and one row each in
`agent_payments`, `settlement_records`, `chain_anchor`, `audit_log`.

### Phase 7 — Outbound A2A (2 weeks)

Goal: Brand.Me can call peer agents (Coinbase wallet agent for fiat
on-ramp, an external repair-shop agent, etc.) using A2A.

- `brandme-agents/agentic/a2a_client.py` — outbound A2A client with
  AgentCard fetch + signature verification.
- Per-peer policy in `brandme-core/policies/peers/{peer-name}.yaml`
  (reuse the existing region-rules YAML loader pattern at
  `brandme-core/policy/region_rules.py:13`).
- One end-to-end demo: Brand.Me agent → Coinbase agent → fiat→USDC →
  payment-mandate confirmed.

Exit criteria: a public demo pairing Brand.Me as merchant with one
external A2A peer.
## 6. Schema additions

All tables go in a new migration `brandme-data/schemas/008_agent_commerce.sql`.
Existing relevant tables: `users.did_cardano` (already exists), `chain_anchor`
(already exists, the settlement primitive), `audit_log` (already FKs to
`chain_anchor`).

```sql
-- AP2 mandate storage. One row per VC issued.
CREATE TABLE mandates (
  mandate_id        STRING(64) NOT NULL,
  mandate_type      STRING(32) NOT NULL,    -- 'intent' | 'cart' | 'payment'
  subject_did       STRING(256) NOT NULL,   -- holder DID
  issuer_did        STRING(256) NOT NULL,   -- issuer DID
  payload_json      JSON NOT NULL,          -- VC body
  jws_signature     STRING(2048) NOT NULL,
  parent_mandate_id STRING(64),             -- e.g. cart references intent
  status            STRING(16) NOT NULL,    -- 'active' | 'revoked' | 'expired' | 'consumed'
  created_at        TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  expires_at        TIMESTAMP,
) PRIMARY KEY (mandate_id);

CREATE INDEX idx_mandates_subject ON mandates(subject_did, mandate_type, status);
CREATE INDEX idx_mandates_parent  ON mandates(parent_mandate_id);

-- ACP cart state. One row per active cart per agent.
CREATE TABLE agent_carts (
  cart_id           STRING(64) NOT NULL,
  agent_did         STRING(256) NOT NULL,
  user_id           STRING(64) NOT NULL,
  items_json        JSON NOT NULL,          -- ACP cart shape
  intent_mandate_id STRING(64),
  status            STRING(16) NOT NULL,    -- 'open' | 'confirmed' | 'cancelled' | 'expired'
  created_at        TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  updated_at        TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (cart_id),
  INTERLEAVE IN PARENT users ON DELETE CASCADE;

-- Payment + settlement. Links the mandate chain to chain_anchor.
CREATE TABLE agent_payments (
  payment_id          STRING(64) NOT NULL,
  cart_id             STRING(64) NOT NULL,
  cart_mandate_id     STRING(64) NOT NULL,
  payment_mandate_id  STRING(64),
  amount_minor        INT64 NOT NULL,        -- in minor units (cents/lovelace)
  currency            STRING(8) NOT NULL,
  status              STRING(16) NOT NULL,   -- 'pending' | 'settled' | 'failed' | 'refunded'
  chain_anchor_id     STRING(64),            -- FK to chain_anchor when settled
  created_at          TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  settled_at          TIMESTAMP,
) PRIMARY KEY (payment_id);

CREATE INDEX idx_payments_cart   ON agent_payments(cart_id);
CREATE INDEX idx_payments_anchor ON agent_payments(chain_anchor_id);

-- Settlement detail (one per chain). chain_anchor stays the cross-chain root.
CREATE TABLE settlement_records (
  settlement_id     STRING(64) NOT NULL,
  payment_id        STRING(64) NOT NULL,
  chain             STRING(16) NOT NULL,    -- 'cardano' | 'midnight'
  tx_hash           STRING(128) NOT NULL,
  status            STRING(16) NOT NULL,    -- 'submitted' | 'confirmed' | 'failed'
  raw_response_json JSON,
  created_at        TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (settlement_id);

CREATE INDEX idx_settlement_payment ON settlement_records(payment_id);
```

Notes:
- `chain_anchor` already has `cardano_tx_hash`, `midnight_tx_hash`,
  `crosschain_root_hash` — keep it; `settlement_records` adds per-chain
  detail (status, raw response) without duplicating the cross-chain root.
- All tables use `allow_commit_timestamp=true` for idempotency, matching
  the rest of the schema.
- Interleave `agent_carts` under `users` so cart cleanup follows user
  deletion (GDPR).
## 7. Open questions for the maintainer

These are decisions only you can make; flag any that should change the plan.

1. **Brand.Me's role in ACP**: merchant only (selling lifecycle services
   to external buyer agents), or also broker/marketplace (intermediating
   between two external agents)? The plan above assumes **merchant only**.
   Marketplace adds a second mandate hop and ~2 weeks.
2. **DID method**: `did:cardano` for users (on-chain, expensive,
   permanent) vs `did:web:brandme.io/users/<id>` (cheap, revocable, but
   centrally controlled). Plan currently assumes `did:cardano` for users
   + `did:web:brandme.io` for the platform itself. Mixed is fine; pure
   `did:web` ships ~1 week sooner.
3. **Cart Mandate signing key custody**: client-side (user's wallet
   signs, Brand.Me only relays) is more honest to the AP2 spec but
   requires a wallet integration on the frontend. Server-side custody is
   faster but weakens the "non-disputable" guarantee. Plan currently
   assumes client-side; flag if you want server-side as v1.
4. **Real money in scope?** If yes, this plan is incomplete: KYC/AML,
   licensed acquirer relationships, custody insurance, and fraud
   monitoring all need to come in. If the goal is a working *spec/demo*
   with testnet rails (Cardano preprod + Midnight devnet), the plan as
   written is sufficient.
5. **Midnight SDK timeline**: Phase 6 is gated on IOG shipping a usable
   SDK. If that slips beyond ~Q3 2026, fallback options are (a) a
   Brand.Me-operated stand-in shielded service or (b) settle on Cardano
   only (lose privacy).
6. **A2A authentication mode**: `did:web` + JWS for AgentCard signing is
   the v1.0 default. Want to also accept OAuth-bearer agents (existing
   gateway middleware)? Both can coexist.
## 8. Verification strategy

Each phase ships with one new pytest module that exercises the happy path
end-to-end against emulators / testnets, plus targeted unit tests.

| Phase | New test module | What it proves |
|---|---|---|
| 0 | `brandme-cube/tests/test_cube_roundtrip.py` | Cube service starts and round-trips a facet write/read against Spanner emulator. |
| 1 | `tests/test_cardano_anchor.py` | One scan produces a real Cardano preprod TX hash, confirmed via Blockfrost. |
| 2 | `tests/test_a2a_task.py` | An A2A client sends a task, receives `pending → in-progress → completed` SSE events. |
| 3 | `tests/test_vc_round_trip.py` | VC issued, verified, tampered VC rejected. |
| 4 | `tests/test_ap2_mandate_chain.py` | Intent → Cart → Payment mandate chain validates; revoked Intent invalidates downstream mandates. |
| 5 | `tests/test_acp_checkout.py` | ACP cart create → update → checkout completes; produces an Intent Mandate row. |
| 6 | `tests/test_payment_settlement.py` | Cart Mandate triggers Midnight stub TX + Cardano anchor; `chain_anchor`, `agent_payments`, `settlement_records` all populated. |
| 7 | `tests/test_a2a_outbound.py` | Brand.Me successfully calls a peer A2A agent (mocked endpoint) and verifies its signed AgentCard. |

Cross-cutting verification:

- **Schema**: `make migrate` runs cleanly against Spanner emulator after
  `008_agent_commerce.sql`.
- **Compose**: `docker-compose up -d` continues to start everything
  currently in scope; new `payments-agent` (Phase 6) added behind a feature
  flag so default-up stays green.
- **CI**: `.github/workflows/ci-cd.yml` gains one job per new test module.
- **Honesty**: each phase's exit criteria translate into a one-line bullet
  added to `CLAUDE.md` so the per-service status table flips REAL only
  when there's a passing test behind it.
