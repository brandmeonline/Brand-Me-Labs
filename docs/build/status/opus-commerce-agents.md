# Lane brief: opus-commerce-agents

**Bench:** Opus 5.5 (Claude Code) · **Branch:** `bench/opus-commerce-agents-20261005`
**Base:** `docs/brandme-full-experience-2026-10-05` · **Spec:** `docs/design/brandme/` + `contracts/`
**Work packages:** W06 (discovery + provider operations), W07 (assistant + bounded commerce)
**Position in merge order:** After `opus-foundation` merges. Independent of the other Opus lanes (disjoint files).

## What you are building
Commerce and agent infrastructure — quote canonicalization and hash binding, the purchase state machine with reconciliation, AP2/ACP protocol adapters, MCP authorization, the deterministic local provider, and the operator provider console. Read chapters 05, 03, 06 and the root `CLAUDE.md` first. Re-verify AP2 Checkout/Payment mandate (v0.2 per spec table — confirm against current official docs) and MCP authorization at build time; record actual pinned versions here.

## You own exclusively (no other lane may touch these)
- `brandme_core/domains/{commerce,providers}/` — full domain logic
- `brandme_core/mcp/` — retire fake tool aliases (including `ap2.create_intent_mandate`); implement the ch.05 tool table; decide and document the explicit interface between the Python tool executor and the gateway MCP transport in your first status update
- `brandme_core/orchestrator/` — task runtime
- `brandme-agents/`, `brandme-governance/` — agent review surfaces
- `brandme-data/spanner/migrations/` — `V006_providers.sql`, `V007_commerce.sql` ONLY
- `brandme-gateway/src/routes/v1/{commerce,catalog,providers,assistant,delegations}.ts` — unmounted router files; never touch `index.ts`, `middleware/`, `types/`
- `packages/provider-contracts/` — you are the SOLE writer after Lane 1 merges (Lane 1 creates interfaces only)
- `tests/test_{commerce,providers,mcp}*.py`, `tests/fixtures/{commerce,providers}/`
- `brandme-console/app/(ops)/{providers,commerce}/**` — check Lane 5's shell layout contract in `docs/build/status/astra-consumer-ui.md` before building pages

## Read-only for you
`packages/contracts` (generated clients), gateway shared files, `docs/build/*`.

## Forbidden
`packages/contracts` (any edits), `docs/design/brandme/**`, `contracts/**`, any `brandme-frontend/` files, other lanes' domains/routes/migrations.

## Exit evidence (from ch.06 §2, W06–W07)
- Deterministic local provider covering ALL 8 required failure behaviors: stock loss, price change, rejected auth, timeout-after-accept, duplicate webhook, partial fulfillment, refund, expired quote — each with retained references
- Quote canonical hash + approval binding: price change after approval → new quote required, old approval rejected; all quote components in one ISO currency with integer arithmetic
- An agent can research and prepare; CANNOT purchase without valid authority; CANNOT mutate approved material terms; CANNOT overspend through concurrency; unknown outcome reconciles without duplicate purchase/charge
- AP2 v0.2 Checkout/Payment mandate conformance against official schemas (version pinned); A2A only for an actual approved integration need, otherwise explicitly unconfigured with contract tests
- MCP: audience-bound tokens; agent reading a product description containing instructions → text stays data, no scope change or unauthorized tool call
- Nordstrom = Impact publisher/deep-link path ONLY unless richer access is actually verified — no guessed retailer APIs, no unauthorized scraping; setup checklist + link-only path complete, missing approval recorded as an explicit integration gate
- Order reconciliation connects real observations to wardrobe states; return/refund handling tested

## Status protocol
Record status ONLY in this file. Propose deviations here. Publish dependency pins here. Document the MCP executor/transport interface decision in your first update.

## Global rules (all lanes)
Never edit another lane's owned files. Never edit `docs/design/brandme/**` or `contracts/**`. Fixtures stay in per-lane `tests/fixtures/<domain>/`. No `latest` tags — pin everything. Demo adapters carry visible simulation labels. No real money movement, no production provider credentials in the repo.

---

# Status log

## Stage S0 — Inspection, pins and MCP executor/transport interface (2026-10-05)

**Baseline:** `305a24b` (brief commit on top of spec `4511236`, audited baseline `0f5f58a`).
**Working branch:** the session harness designates `claude/opus-commerce-agents-setup-szpmf7`; at start it pointed at the
same commit as `bench/opus-commerce-agents-20261005` (`305a24b`). All lane commits land on the `claude/...` branch;
the bench branch can fast-forward to it. Not pushed to `bench/...` without explicit permission.

### Repository facts verified at baseline (code, not docs)

| Fact | Evidence |
|---|---|
| `opus-foundation` has **not** merged: no `packages/`, no `brandme-data/spanner/migrations/`, no `brandme_core/domains/`, no `brandme_core/orchestrator/`, no `docs/build/status/astra-consumer-ui.md` | `ls` at `305a24b` |
| `MCPToolExecutor` has **no callers** anywhere in the repo; the `mcp-server` compose service is commented out | `grep -rn MCPToolExecutor` → only `brandme_core/mcp/{__init__,tools}.py`; `docker-compose.yml:440` |
| Executor trusts `params["user_id"]` as identity | `brandme_core/mcp/tools.py:586` |
| Fake protocol tools: `ap2.mandate.create_intent` / `confirm_cart` / `issue_payment` mint random UUIDs; `acp.checkout.complete` returns `status: "completed"` with three fake mandate IDs | `brandme_core/mcp/tools.py:854-923`. Note: the brief calls the alias `ap2.create_intent_mandate`; the actual registered name is `ap2.mandate.create_intent`. Both names are retired. |
| Gateway auth is HS256 shared-secret `jwt.verify` with issuer check only — **no audience check** | `brandme-gateway/src/middleware/auth.ts:42-49` (read-only for this lane) |
| No Spanner/Firestore emulator available in this container (no Docker daemon) | `docker ps` → socket missing |

### External versions re-verified today (pinned)

| Protocol | Pinned version | Verified against | Notes |
|---|---|---|---|
| AP2 | **v0.2**; closed mandates `vct = "mandate.checkout.1"` and `"mandate.payment.1"`; open `mandate.checkout.open.1` / `mandate.payment.open.1` | [ap2-protocol.org/ap2/specification](https://ap2-protocol.org/ap2/specification/), [checkout_mandate](https://ap2-protocol.org/ap2/checkout_mandate/), [payment_mandate](https://ap2-protocol.org/ap2/payment_mandate/); official JSON Schemas in `google-agentic-commerce/AP2@e1ea56db72a6385bce3e5c1112b3a56ce60acb43` (`code/sdk/schemas/ap2/*.json`, Apache-2.0, commit date 2026-04-29) | Two mandate types only (Checkout + Payment); Cart mandate retired in v0.2. `checkout_hash` = base64url(hash(`checkout_jwt`)), sha-256 unless `_sd_alg` says otherwise. Payment `transaction_id` = same hash. Merchant Checkout JWT must use a non-deterministic signature (ECDSA, reference SDK uses ES256). Holder binding = KB-SD-JWT with `aud`, `nonce`, `iat`, `sd_hash`. Trusted Surface MUST be non-agentic. Agent-to-agent delegation out of scope. Spec prose says vct `'mandate.checkout'` while the schema `const` is `'mandate.checkout.1'` — the codec follows the schema `const` and records the discrepancy. |
| AP2 crypto deps | `jwcrypto==1.5.6`, `sd-jwt==0.10.4` (same pins as the official SDK) | official SDK `pyproject.toml` at the commit above | The official `ap2` package itself is **not** taken as a dependency: it pins `pydantic==2.12.5`, `cryptography==46.0.5`, `pytest==9.0.2`, conflicting with repo pins. The codec validates against vendored official schemas instead. |
| MCP | **2026-07-28** (current per [versioning page](https://modelcontextprotocol.io/specification/versioning)) | [2026-07-28 authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) | Stateless revision: version travels per request in `_meta["io.modelcontextprotocol/protocolVersion"]` and `MCP-Protocol-Version` header; `server/discover` replaces initialize. Server MUST publish RFC 9728 Protected Resource Metadata, MUST validate token audience per RFC 8707, MUST NOT accept or transit other tokens; 401 invalid/expired, 403 `insufficient_scope` with `WWW-Authenticate: Bearer error=..., scope=..., resource_metadata=...`. |
| Canonical JSON | RFC 8785 (JCS) via `rfc8785==0.1.4` | PyPI | Quote hash encoder. |
| ACP / UCP / A2A | **Not pinned — explicitly unconfigured.** No approved merchant, processor or partner agent exists for this lane. | — | Adapters ship as `unconfigured` capability gates with contract tests proving they cannot advertise or execute. Will pin only when a real integration is approved. |

### Decision: MCP executor ⇄ gateway transport interface

```
external MCP client
  │  Authorization: Bearer <AS-issued token, aud = canonical MCP URI>
  ▼
gateway MCP transport (TypeScript, Streamable HTTP, 2026-07-28)      ← opus-foundation mount/middleware
  • serves /.well-known/oauth-protected-resource (RFC 9728)
  • validates iss, aud == canonical MCP URI, exp/nbf, alg allowlist (ES256/RS256 via JWKS; never HS256 shared secret)
  • 401 / 403 insufficient_scope challenges; JSON-RPC framing; protocolVersion check
  • maps (iss, sub) → internal member_id; resolves client_id + delegation_id
  • DROPS the external bearer token (no passthrough)
  │  POST {EXECUTOR}/internal/mcp/v1/invoke
  │  Authorization: Bearer <gateway-signed principal assertion, aud = "brandme:mcp-executor", ttl ≤ 60 s, jti>
  │  body: ToolInvocation (schema: brandme_core/mcp/schemas/tool_invocation.schema.json)
  ▼
Python tool executor (brandme_core/mcp, this lane)
  • re-verifies the assertion: issuer, audience "brandme:mcp-executor", ttl, jti replay cache
  • tool arguments are validated against the tool's input schema; any `user_id`/`member_id`/`principal` argument is REJECTED
  • scope check → delegation check (state, expiry, limits, providers) → object-level policy → handler
  • returns ToolOutcome {status, structured_content | problem, side_effects[], requires_trusted_surface?}
```

Why: the TS gateway is the identity boundary per ch.03 §1.4, so MCP token validation happens there (BM-COM-003 "rejects before
domain execution"). The Python executor still refuses to run without a second, executor-audience credential, so a request
that bypasses the gateway, or carries a user/provider token, cannot execute a tool. The external token never crosses the
hop (MCP "MUST NOT transit other tokens"). Identity comes only from the assertion's `principal` block, never from tool arguments.

`ToolInvocation` fields: `request_id`, `protocol_version` (`"2026-07-28"`), `environment`, `principal {member_id, subject,
issuer, client_id, session_id|null, scopes[], assurance_level, delegation_id|null}`, `tool`, `arguments`, `idempotency_key|null`.
Purchases additionally require a trusted-surface `approval_id`; the executor cannot create one.

**Dependency request to `opus-foundation`:** the gateway MCP transport and an audience-checking verifier in `middleware/`
(current `auth.ts` checks issuer only). Until it lands, this lane ships (a) the Python executor + assertion verifier,
(b) a reference `McpAccessTokenValidator` in Python implementing the exact same RFC 8707/9728 rules with tests,
usable by the foundation lane as the conformance oracle, and (c) the JSON schema above.

### Proposed deviations / sequencing (no founder approval needed)

1. `packages/provider-contracts/` is created by Lane 1 first. Because Lane 1 has not merged, the provider capability
   vocabulary and adapter protocols are implemented in Python under `brandme_core/domains/providers/` now; the
   TypeScript package is written after Lane 1 merges, generated from the same definitions.
2. `brandme_core/domains/__init__.py` does not exist. This lane creates only `brandme_core/domains/{commerce,providers}/`
   plus an empty namespace `__init__.py`; if Lane 1 creates the same file the merge is trivial (empty file).
3. `V006`/`V007` reference foundation tables (`Members`, outbox) by STRING id without Spanner FKs, so they apply on any
   V001–V005 that defines those IDs. Will validate DDL against the emulator once one is available; until then marked `not_run`.
4. `brandme_core/orchestrator/` (task runtime) is new; legacy `brandme-core/orchestrator` (fake `cardano_tx_*`) is not edited.

### Next actions
S1 commerce domain core → S2 providers/local provider/Nordstrom → S3 MCP → S4 AP2 codec → S5 migrations, routes, orchestrator.

## Stage S1+S2 — Commerce core, providers, local provider, Nordstrom gate (2026-10-05)

**Code:** `brandme_core/domains/commerce/{money,quote,principal,delegation,records,store,service,errors}.py`,
`brandme_core/domains/providers/{contracts,registry,local_atelier,nordstrom,ingestion,url_guard}.py`.
**Tests:** `tests/test_commerce_quote.py` (23), `tests/test_commerce_purchase.py` (32), `tests/test_providers.py` (26) —
**81 passed** locally (`python3 -m pytest tests/test_commerce_quote.py tests/test_commerce_purchase.py tests/test_providers.py`),
Python 3.11.15, pytest 7.4.3 (repo pin), rfc8785 0.1.4, jsonschema 4.26.0. Overspend concurrency test re-run 5× — stable.

Persistence here is `InMemoryCommerceStore` (same transaction contract as Spanner RW transactions). **Not** Spanner-verified:
no emulator in this container. Any claim below is domain-level evidence only.

| Exit evidence item | Status | Test(s) |
|---|---|---|
| Local provider: stock loss | passed (fixture) | `test_stock_loss_blocks_quote_without_substitution`, `test_stock_loss_after_approval_rejected_by_provider` |
| price change | passed (fixture) | `test_price_change_after_approval_requires_new_quote` |
| rejected auth | passed (fixture) | `test_rejected_authorization` |
| timeout-after-accept | passed (fixture) | `test_timeout_after_accept_reconciles_to_one_order` |
| duplicate webhook | passed (fixture) | `test_duplicate_webhook_applied_once` |
| partial fulfillment | passed (fixture) | `test_partial_fulfillment_then_full` |
| refund | passed (fixture) | `test_refund_before_delayed_fulfillment_keeps_facts_independent`, `test_refund_credit_back_follows_grant_policy` |
| expired quote | passed (fixture) | `test_expired_quote`, `test_expiry_between_approval_and_execution` |
| Retained references | passed | provider evidence refs kept on `Order.evidence_refs` and in `commerce.order.observed` payloads |
| Quote canonical hash (RFC 8785, domain `brandme.checkout_quote` v1) + approval binding | passed | `TestQuoteHash::*`, `test_full_purchase_binds_exact_terms_and_emits_wardrobe_incoming` (BM-COM-004) |
| Price/variant change → old approval rejected (BM-COM-005) | passed | `test_price_change_after_approval_requires_new_quote`, `test_agent_cannot_mutate_approved_terms` |
| One ISO currency, integer arithmetic | passed | `TestMoney::*`, `test_invalid_arithmetic_currency_expiry_recurrence` |
| Research/prepare but no purchase without authority (BM-COM-001, -006) | passed | `test_research_mode_*`, `test_prepare_mode_*`, `test_cannot_purchase_without_valid_approval`, `test_agent_cannot_open_challenge_or_approve` |
| No overspend through concurrency (BM-COM-007) | passed (in-memory lock; Spanner txn `not_run`) | `test_two_agents_cannot_overspend_shared_budget` |
| Revocation before submission (BM-COM-008) | passed | `test_revocation_before_submission_*`, `test_revocation_racing_submission_stops_unsent_work` |
| Unknown outcome reconciles, no duplicate (BM-COM-009) | passed | `test_timeout_after_accept_reconciles_to_one_order` |
| Out-of-order callbacks; payment vs fulfillment independent (BM-COM-010) | passed | refund-before-fulfillment test |
| Partial shipment / refund / return → wardrobe events (BM-COM-011) | passed for partial + refund + return-not-refund; **exchange** handled in `_apply_observation` (new variant line with `exchanged_from_ref`) but no simulator exchange behavior yet → `not_run` |
| Unregistered redirect rejected (BM-COM-013) | passed | `test_checkout_redirect_must_be_registered` |
| Nordstrom: unconfigured gate, no guessed API, link-only path (BM-PROV-001/002) | passed | `test_nordstrom_*`, `test_link_only_path` |
| Impact sandbox read-only test (BM-PROV-003) | **blocked** — no approved Nordstrom/Impact publisher account; the gate is `partner_approval_required` |
| Feed replay/deletion (BM-PROV-004), forbidden derivative (‑005), stale price (‑006), SSRF redirect (‑010) | passed | `test_feed_replay_and_tombstone`, `test_forbidden_media_derivative_blocked`, `test_stale_feed_price_*`, `test_redirect_to_private_network_rejected_before_request` |
| Simulation refused in sandbox/production | passed | `test_simulation_provider_refused_in_production` |

Design notes recorded for review:
- Approvals come only from a first-party session (`Principal.first_party_session`, no delegation) at `aal2`, through a
  server-issued single-use challenge (nonce shown only on the trusted surface) bound to the recomputed quote hash.
- `buy_within_rules` grants **require final human approval**; `require_final_human_approval=False` is refused with
  `autonomous_not_supported` until a provider + AP2 open-mandate path is verified. A prepared (prepare-mode) purchase is
  completed by the member's own session; only a buy-within-rules delegation can execute an approved purchase.
- Budget limits are all-in totals; currency mismatch → `currency_mismatch` (no FX). Reservations commit with approval
  consumption + submission intent in one transaction before provider I/O; refund credit-back only if the grant says so.
- Webhooks: provider signature + 5-min replay window, dedupe on `(provider, event_id)`, then source re-read and monotonic merge.
- Existing CLAUDE.md "passing" suites (`tests/test_consent_graph.py` etc.) do **not** collect in this container
  (missing `google-cloud-*` deps, no emulator). Not this lane's to fix; noted for opus-foundation W00.

## Stage S3 — MCP tool surface, authorization, retired aliases (2026-10-05)

**Code:** `brandme_core/mcp/{tools,authz,__init__}.py`, `brandme_core/mcp/schemas/{tool_invocation,executor_assertion}.schema.json`.
`brandme_core/mcp/consent.py` unchanged. Dependency pins: `brandme_core/domains/commerce/requirements.txt` (for
opus-foundation to merge into the shared manifest).
**Tests:** `tests/test_mcp.py` — 36 passed. Full lane suite: **117 passed**.

**Interface correction to S0:** the principal is **not** in the `ToolInvocation` body. It travels only in the
gateway-signed executor assertion's `principal` claim (schema `executor_assertion.schema.json`); the body carries
`request_id, protocol_version, environment, tool, arguments, idempotency_key`. This removes a second, unauthenticated
copy of identity.

| Item | Status | Evidence |
|---|---|---|
| Fake tools retired: `ap2.create_intent_mandate`, `ap2.mandate.create_intent/confirm_cart/issue_payment`, `acp.cart.create/update`, `acp.checkout.complete`, plus v9 stubs (`search_wardrobe`, `get_cube_details`, `suggest_outfit`, `initiate_rental`, `list_for_resale`, `request_repair`, `request_dissolve`) | passed | not listed; each returns 410 `tool_retired` with replacement name (`test_retired_fake_tools_return_documented_problem`) |
| ch.05 tools implemented: `brandme.catalog.search`, `cart.create`, `cart.update`, `checkout.quote`, `purchase.request`, `purchase.execute`, `order.status` | passed | `test_agent_flow_research_prepare_then_member_approval` |
| ch.05 tools owned by other lanes (`persona.*`, `wardrobe.search`, `outfits.suggest`, `social.request_decision`, `rights.transfer_request`, `reprint.*`) | not advertised; 501 `tool_unavailable` | `UNAVAILABLE_TOOLS` |
| Advertised tools match real capability (BM-COM-016) | passed | `test_tools_list_advertises_only_working_tools` |
| `user_id` impersonation (BM-COM-002) | passed | `test_user_id_argument_cannot_impersonate` |
| Audience-bound tokens; wrong resource rejected (BM-COM-003) | passed for the Python reference validator and executor hop; **gateway transport `not_run`** (foundation-owned) | `test_wrong_audience_issuer_expiry_key_rejected`, `test_external_token_cannot_be_used_at_executor`, `test_symmetric_and_none_algorithms_rejected` |
| Executor assertion: ES256 only, ≤60 s, single-use `jti`, environment-bound | passed | `test_assertion_replay_ttl_and_forgery_rejected` |
| Malicious product text stays data (BM-COM-017) | passed | `test_malicious_product_text_stays_data` |
| PAN/CVV never accepted or logged (BM-COM-018) | passed (MCP surface) | `test_payment_card_data_rejected_and_never_logged`, `test_audit_records_no_arguments` |
| MCP interop test against a real client | **not_run** — needs the gateway Streamable HTTP transport |

## Stage S4 — AP2 v0.2 codec; ACP/UCP/A2A explicit gates (2026-10-05)

**Code:** `brandme_core/domains/commerce/ap2.py`, vendored official schemas in
`brandme_core/domains/commerce/ap2_schemas/` (verbatim from `google-agentic-commerce/AP2@e1ea56db72a6385bce3e5c1112b3a56ce60acb43`,
Apache-2.0, `NOTICE.md`), `CommerceService.register_surface_key` / `approve_with_ap2`, `protocols.py`.
**Tests:** `tests/test_commerce_ap2.py` (21), `tests/test_commerce_protocols.py` (5).

Role decision: Brand.Me **verifies** AP2 mandates and maps them to an internal approval; it never signs a mandate for
the member. The member's trusted-surface device key (EC P-256, registered from an `aal2` first-party session) signs
closed Checkout/Payment mandates. Verification: SD-JWT signature (`sd-jwt==0.10.4`), exactly one `delegate_payload`,
official JSON Schema, `vct` const, `checkout_hash` = b64url(sha-256 or `_sd_alg`) of `checkout_jwt`, merchant Checkout JWT
ES256-only (spec forbids deterministic signatures) against the provider's registered merchant key, UCP checkout ↔ canonical
quote material terms, payment `transaction_id`/amount/currency/payee, `iat`+`exp` required and `exp` ≤ quote expiry, KB-JWT
`aud`/`nonce` enforced when present, single use by mandate digest. Approval stores `protocol_payload_hash` separately
from the internal quote hash. Open mandates and `~~` chains → `unsupported_chain`.

| Item | Status | Evidence |
|---|---|---|
| AP2 conformance vs official schemas (BM-COM-014) | **passed** (local, against simulated merchant) | 18 local tests |
| Cross-verification with the **official AP2 SDK** at the pinned commit | **passed** — SDK verifies mandates Brand.Me accepts; Brand.Me verifies mandates the SDK issues; SDK rejects wrong key/expired as we do | `test_official_sdk_*` (3), run with `AP2_SDK_PYTHON=<venv with ap2 @ e1ea56d>`; skipped (not passed) when unset |
| Invalid signatures / replays fail (BM-COM-014) | passed | `test_tampered_*`, `test_replayed_mandate_rejected`, `test_mandate_signed_by_unregistered_key_rejected` |
| AP2 against a real merchant/PSP | **blocked** — no merchant supporting AP2 is approved for Brand.Me |
| ACP / UCP | `unconfigured`, no version pinned; adapters fail closed (BM-COM-015 contract half passed; provider suites blocked on approved accounts) | `test_commerce_protocols.py` |
| A2A | `unconfigured`; no Agent Card published; no `a2a.*` tools | `test_no_agent_card_and_no_protocol_tools_advertised` |

Oracle reproduction: `python3 -m venv /tmp/ap2venv && /tmp/ap2venv/bin/pip install -e <AP2 checkout @ e1ea56d> &&
AP2_SDK_PYTHON=/tmp/ap2venv/bin/python python3 -m pytest tests/test_commerce_ap2.py`.

## Stage S5 — Migrations, unmounted gateway routers, task runtime, Spanner budget (2026-10-05)

**Code:** `brandme-data/spanner/migrations/V006_providers.sql`, `V007_commerce.sql`;
`brandme_core/domains/commerce/spanner_budget.py`; `brandme_core/orchestrator/{__init__,runtime}.py`;
`brandme-gateway/src/routes/v1/{commerce,catalog,providers,assistant,delegations}.ts` (+ `commerce.test.ts`).
Hardening from self-review: unclassified submit exceptions → `outcome_unknown`; stale `submitting` (crash between
durable intent and provider response, ≥2 min) → reconciled; `record_verification` now yields `verified` only for
production evidence in production (sandbox/conformance → `sandbox`).

| Item | Status | Evidence |
|---|---|---|
| V006/V007 apply to Cloud Spanner | **passed on emulator 1.5.58** (downloaded binary, no Docker) — all statements applied to an empty DB; CHECKs proven: simulation-outside-dev, quote total arithmetic, verified-needs-evidence; unique provider idempotency key | `tests/test_commerce_migrations.py` (requires `SPANNER_EMULATOR_REST`; skipped otherwise). Disposable cloud DB run: `not_run` |
| Overspend prevention on real Spanner transactions (BM-COM-007) | **passed on emulator** — 12 concurrent reservations of $96.12 against $300.00 → exactly 3 admitted | `test_concurrent_reservations_cannot_overspend_on_spanner` |
| Full Spanner repository for carts/quotes/operations/orders | **not done** — domain uses `InMemoryCommerceStore`; only the budget ledger has a Spanner implementation. Next lane step. |
| Gateway routers (unmounted) | typecheck clean (`tsc 5.3.3`, repo strict tsconfig) and **8/8 vitest** in an isolated scratch install (repo lockfile untouched). Not mounted — `index.ts` is opus-foundation's. |
| Assistant runtime: research/prepare, allowlist per mode, budgets, cancellation, injection | passed | `tests/test_commerce_assistant.py` (6) |
| Console pages `brandme-console/app/(ops)/{providers,commerce}` | **blocked** — `docs/build/status/astra-consumer-ui.md` (Lane 5 shell layout contract) does not exist yet; building pages first would guess the layout. Router + domain setup checklist are ready to back them. |
| `packages/provider-contracts` (TS) | **deferred** until opus-foundation merges (Lane 1 creates the package first); Python source of truth is `brandme_core/domains/providers/contracts.py`. |

**Lane test totals (2026-10-05):** 157 passed with `SPANNER_EMULATOR_REST` + `AP2_SDK_PYTHON` set;
148 passed + 9 skipped without them. Gateway: 8 vitest passed.

### Domain HTTP contract the routers expect (for whoever mounts them)
`POST {COMMERCE_DOMAIN}/internal/commerce/v1/{operation}` with `Authorization: Bearer <gateway principal assertion>`
(same claims as `brandme_core/mcp/schemas/executor_assertion.schema.json`, audience to be `brandme:commerce-domain`),
`Idempotency-Key` / `If-Match` forwarded verbatim, JSON body = validated request. Operations: `cart.create|update|quote`,
`approval.challenge|create`, `purchase.execute`, `operation.get`, `order.get|return`, `webhook.receive` (raw body + headers,
no principal), `catalog.search|product`, `provider.*`, `capabilities.effective`, `delegation.list|create|revoke`,
`assistant.task.create|cancel|events`. The Python HTTP adapter for these is not yet written (needs the brain/service mount owner).

### Exit evidence roll-up (brief)
| Brief item | Result |
|---|---|
| Deterministic local provider, all 8 failure behaviors, retained refs | **met (fixture)** |
| Quote canonical hash + approval binding; integer one-currency arithmetic | **met** |
| Research/prepare yes; purchase without authority no; approved terms immutable; no overspend under concurrency; unknown outcome reconciled once | **met** (domain + Spanner-emulator budget) |
| AP2 v0.2 Checkout/Payment conformance vs official schemas, version pinned | **met locally + official-SDK cross-verification**; real merchant/PSP **blocked** |
| A2A only for approved need, else unconfigured with contract tests | **met** (unconfigured) |
| MCP audience-bound tokens; product-text instructions stay data | **met in Python** (validator, executor hop, runtime); gateway transport **pending opus-foundation** |
| Nordstrom = Impact publisher/deep-link only; checklist + link-only; approval as explicit gate | **met**; live Impact test **blocked** on approval |
| Order reconciliation → wardrobe states; return/refund tested | **met** as `commerce.order.observed` events (`incoming/arrived/returned`); wardrobe reducer belongs to the wardrobe lane |

### Open gates / next actions
1. opus-foundation: MCP Streamable HTTP transport + audience-checking middleware (use `McpAccessTokenValidator` rules as oracle), mount these routers, outbox tables, shared requirements (merge `brandme_core/domains/commerce/requirements.txt`).
2. This lane next: Spanner repository for the remaining commerce tables; Python internal HTTP adapter; console pages once Lane 5's shell contract exists; TS `packages/provider-contracts` after Lane 1 merges; simulator exchange behavior (BM-COM-011 exchange case).
3. Founder/operator: Nordstrom program application via Impact and approval evidence; any merchant that supports AP2/ACP/UCP sandbox. No production credentials are in the repo; none were used.

## Stage S6 — Foundation merge reconciliation (2026-10-05)

opus-foundation PR #33 merged into `bench/opus-foundation-20261005` (`3704ec7`, verified by fetch). Merged it into this
lane branch (merge commit `bdcbad9`, no history rewrite). Only conflict: `brandme_core/domains/__init__.py` (add/add) —
foundation's version kept.

| Check after merge | Result |
|---|---|
| Lane suite (emulator + AP2 oracle) | 158 passed |
| Lane suite (no external tools) | 149 passed, 9 skipped |
| `tests/foundation` on the merged tree | 77 passed, 11 skipped |
| V006/V007 through foundation `runner.py up/status/verify` on top of V001 (emulator 1.5.58) | applied, `verify` exit 0 |

Fix found while re-running: the MCP card-number guard accepted hyphen-separated digit runs, so ~0.3% of random UUIDs
were refused as card data (flaky `test_agent_flow_research_prepare_then_member_approval`). UUIDs are now stripped before
scanning; regression test added (`test_uuids_are_not_mistaken_for_card_numbers`, 20 000 random UUIDs, zero hits).

### Reconciliation plan (next lane work, now unblocked)
1. Replace `brandme_core/domains/commerce/principal.Principal` and `commerce/errors` with `brandme_core.domains.base`
   (`Principal`, `DomainError` family, `authorize`, `run_command` / `run_idempotent_command`); register commerce/provider
   event payload schemas with `brandme_core.domains.events.register`; register data categories.
2. Spanner repositories for V006/V007 through `run_command` (outbox in the same transaction), replacing `InMemoryCommerceStore`.
3. `packages/provider-contracts`: extend foundation's interfaces with the normalized payload types from
   `brandme_core/domains/providers/contracts.py` (this lane is now sole writer).
4. Add commerce/provider API shapes to `packages/contracts` via `scripts/endpoints.mjs` and regenerate (never hand-edit
   `generated/`) — coordinate with opus-foundation since that package is read-only for this lane.
5. Align gateway routers with foundation `middleware/{session,validation,problem}` and `types.Principal` for mounting in
   `routes/v1/index.ts` (foundation-owned mount).

### S6 addendum — dependency CVEs (Trivy on PR #35)
Bumped lane pins: PyJWT 2.13.0 → **2.15.1**, cryptography 49.0.0 → **50.0.2**, jwcrypto 1.5.6 → **1.6.1** (deviation from
the AP2 SDK's 1.5.6 pin, taken for CVE-2026-39373; AP2 tests still pass, and the official-SDK oracle still runs in its
own pinned venv). PyJWT CVE-2026-103001 has no fixed release; this lane never shares or mutates a decode options dict.
After the bump: lane + foundation suites 229 passed / 11 skipped; the emulator migration tests 6/6 (they first errored
because the local emulator had stopped).
Remaining Trivy alerts on the PR are outside this lane's files (merged foundation lockfiles / existing manifests).

### S6 addendum — Foundation `check` blocker (2026-10-05 23:45 UTC)
Foundation workflow on `31bea91`: 4 failures in `tests/foundation/test_migrations.py` (foundation-owned). The tests hardcode
"only V001 exists", so any lane adding its reserved migration (V006/V007 here) breaks them. My earlier local foundation
run had skipped them (no `SPANNER_EMULATOR_HOST`); reproduced with the emulator. A patch that runs V001 behaviour against
a V001-only temp dir and checks reserved numbers/names passes 6/6 locally. Posted on PR #35 for opus-foundation; not
applied here because the file belongs to another lane. **Blocked on:** foundation landing it, or founder authorizing this
lane to carry it. The real chain V001+V006+V007 applies and `runner.py verify` exits 0.
