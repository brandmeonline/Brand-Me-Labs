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

---

## Stage S7 — Resumption, re-verified pins, interface decision amended (2026-10-23)

**State on resume:** PR #35 merged into `bench/opus-commerce-agents-20261005` as `7c61afd` (2026-10-06). The working branch
`claude/opus-commerce-agents-setup-szpmf7` was an ancestor of it and was fast-forwarded; this round starts from `7c61afd`.
Baseline re-run on `7c61afd` before any change: `tests/foundation` + lane suite **246 passed, 0 skipped**
(Spanner emulator 1.5.58, official AP2 SDK oracle). Retired aliases (`ap2.create_intent_mandate`, `ap2.mandate.*`,
`acp.*`, v9 stubs) still return documented 410s — `brandme_core/mcp/tools.py` `RETIRED_TOOLS`.

Other lanes since 2026-10-05 (fetched, not merged here): foundation unchanged at `67327e4`; astra-consumer-ui published
**console shell contract v1** (`9e21bd0`, `docs/build/status/astra-consumer-ui.md` on its bench branch) — this unblocks
`brandme-console/app/(ops)/{providers,commerce}/**`; consumer-domains, midnight-rights and spatial-ar merged their own
bench work (disjoint files).

### External versions re-verified 2026-10-23

| Protocol | Pin | Re-verification |
|---|---|---|
| AP2 | **v0.2**, release tag **`v0.2.0` = `b4587ac`** (2026-04-28); vendored schemas taken from `e1ea56d` | `main` is still `e1ea56d`; `git diff v0.2.0 e1ea56d -- code/sdk/schemas` is empty (the 4 later commits touch docs/CHANGELOG/`uv.lock` only), so the vendored schemas are byte-identical to the release. Spec page still "Agentic Payment Protocol (v0.2)", no newer draft or deprecation. Closed vct `mandate.checkout.1` / `mandate.payment.1` unchanged. |
| MCP | **2026-07-28** | Versioning page still lists 2026-07-28 as *current*. Authorization page re-read: audience validation per RFC 8707, "MUST NOT accept or transit any other tokens", 401/403/400 table, `insufficient_scope` challenge — unchanged. Noted: "Servers MUST account for scope hierarchies" — this lane's scopes are flat (no scope implies another), so no hierarchy logic is needed until one is defined. |
| ACP / UCP / A2A | unpinned, explicitly unconfigured | No approved merchant/processor/partner since S4. |

### Decision (amended): MCP executor ⇄ gateway transport, and principal mapping

The S0/S3 interface stands: the gateway (opus-foundation) terminates MCP Streamable HTTP and validates the external
token (iss, `aud` = canonical MCP URI, exp, ES256/RS256 allowlist), drops it, and calls the Python executor with an
ES256 executor assertion (`aud` `brandme:mcp-executor`, ≤60 s, single-use `jti`) carrying the principal; tool calls
carry `request_id, protocol_version, environment, tool, arguments, idempotency_key` only. Foundation has not built the
MCP transport yet (only `/api/v1` session + bearer). Amendments now that foundation's identity boundary exists:

1. **One Python principal.** Commerce, MCP and the orchestrator adopt `brandme_core.domains.base.Principal`
   (foundation) and drop `brandme_core/domains/commerce/principal.py`. Foundation's principal has no `issuer` or
   first-party flag, so the rule is: **first-party = `session_id is not None and delegation_id is None`** (cookie
   session, `via: 'session'` in TS). Bearer/MCP principals (`session_id` null) are agents.
2. **Delegations are resolved by the commerce domain**, not the gateway: foundation bearer principals arrive with
   `delegationId: null`. For an agent principal the domain looks up the single active `AgentDelegation` for
   `(member_id, client_id)`; creating a second active grant for the same pair is refused. A supplied `delegation_id`
   must match that grant.
3. **Scopes gate delegated clients, not the member.** Foundation session principals carry only
   `profile:*`/`privacy:manage`. A first-party session acts with the member's own authority on their own commerce
   objects (object-level ownership still enforced); `commerce:*` scopes are required for bearer/MCP agents and must
   also be in the delegation. Request to opus-foundation (non-blocking): if it prefers explicit scopes, add
   `commerce:research`, `commerce:cart`, `commerce:purchase` to session principals; the domain accepts either.
4. **Assurance.** Approvals need `aal2`. Foundation's dev identity is `simulated`; a `simulated` approval is accepted
   **only** in `demo`/`development` and **only** against a simulation provider — never sandbox/production.
5. **Audiences stay separate.** Gateway `/api/v1` bearer tokens use `cfg.oidcAudience`; MCP tokens must carry the
   canonical MCP resource URI. Neither is accepted at the other surface (no audience sharing, no passthrough).
6. **TS routers** read the principal from `res.locals.principal` (foundation convention) and map
   `via === 'session'` to first-party; errors use foundation's `ApiProblem`/problem+json shape.

### Plan for this round (each stage recorded here when done)
S8 adopt foundation `Principal`/errors/event registration/data categories · S9 Spanner repository for V006/V007
through `run_command` (outbox in the same transaction), tests parametrized over in-memory and emulator ·
S10 `packages/provider-contracts` extension · S11 routers aligned to foundation middleware + unmounted Python domain
HTTP adapter · S12 console `(ops)/providers/**` and `(ops)/commerce/operations` per shell contract v1 ·
S13 simulator exchange behavior (BM-COM-011 exchange case).

## Stage S8 — Commerce on the foundation principal, errors, event registry, data categories (2026-10-23)

**Done.** Lane + foundation suite: **274 passed, 0 skipped** (Spanner emulator 1.5.58, official AP2 SDK oracle;
baseline 246, +28 new). Exit-evidence tests from S1–S5 are unchanged in intent; only fixtures moved to the new
principal and 16-char idempotency keys.

- **Principal.** `brandme_core/domains/commerce/principal.py` is now a thin helper over
  `brandme_core.domains.base.Principal`: `is_first_party` (= `session_id` set, no delegation), `is_agent`,
  `validate_principal`, `meets_assurance`. Deviation from S7 point 1: the module is kept as the single home of those
  rules instead of being deleted; it defines no principal type of its own. The old `issuer`/`first_party_session`
  fields are gone everywhere (`grep` clean).
- **Binding.** `CommerceService.bind(principal)` runs first in every public method: environment check; first-party
  passes through; an agent needs a `client_id` and is resolved to its **one** active delegation for
  `(member_id, client_id)` (a supplied `delegation_id` must be that grant). `create_delegation` refuses a second active
  grant for the same pair (`409 active_delegation_exists`); expiry or revocation frees the slot. Agents cannot create
  or revoke grants (`not_trusted_surface`); revoked agents cannot read operations/orders either.
- **Scopes.** First-party sessions are not scope-gated (foundation sessions carry only `profile:*`/`privacy:manage`,
  test `test_profile_only_session_can_buy_for_itself`). Agents need the scope in **both** the token and the
  delegation (`test_agent_scope_is_token_and_grant_intersection`, MCP `test_token_scope_beyond_grant_is_not_honoured`).
- **Assurance.** Trusted-surface approval: `aal2`, or foundation `simulated` only in `demo`/`development` and only when
  the operation's provider is a simulation (`reauthentication_required` otherwise). AP2 device-key registration never
  accepts `simulated` — those keys sign real mandates.
- **Errors.** `commerce/errors.py` subclasses foundation `DomainError` (`NotFound`, `Forbidden`, `InvalidTransition`,
  `VersionConflict` → `revision_conflict`, `IdempotencyConflict` → `idempotency_key_reused`); new `InvalidRequest`
  (400) and `DelegationConflict` (409). One problem+json vocabulary for any adapter that maps `DomainError`.
- **Idempotency.** Keys follow the foundation contract (16–128 chars, `idempotency_key_invalid`); scope is
  `(actor_ref, environment, operation, key)`, same shape as `run_idempotent_command`, so the delegation is part of the
  scope (ch.03 §6). MCP `tool_invocation.schema.json` `idempotency_key.minLength` 8 → 16.
- **Events.** Outbox rows are foundation `EventEnvelope`s validated on emit (domain schema + registered closed payload +
  `FORBIDDEN_PAYLOAD_KEYS`). Registered in `commerce/events.py`, all `member_private`: `commerce.delegation.created`,
  `commerce.delegation.revoked` (renamed from `delegation.*`), `commerce.quote.ready`,
  `commerce.purchase.approval_requested`, `commerce.purchase.authorized`, `commerce.order.observed` (the wardrobe
  lane's input: per-line ordered/shipped/delivered/returned, `wardrobe_effect` incoming/arrived/returned/updated,
  acquisition evidence refs). `actor_ref` is foundation's `member:<id>[/delegation:<id>]`.
- **Data categories.** `commerce/data_categories.py` registers `commerce.agent_grants`, `commerce.carts_quotes`,
  `commerce.orders` with their V007 tables and truthful retention text (financial evidence kept per jurisdiction /
  provider agreement; merchant-held records outside Brand.Me's control). **`export`/`delete` are not wired yet** — they
  need the Spanner store (S9).
- **MCP / orchestrator.** `ExecutorAssertionVerifier` builds the foundation principal with `session_id=None` and
  **rejects** a session-bound principal on the MCP hop (401); `delegation_id` in the assertion is optional
  (`executor_assertion.schema.json` updated). `McpToolExecutor._dispatch` binds before the scope check and audits the
  resolved delegation. `AssistantRuntime` refuses member sessions (tasks run under a grant) and a task mode that
  differs from the grant's mode.

Files: `brandme_core/domains/commerce/{principal,errors,events,data_categories,delegation,store,service}.py`,
`brandme_core/mcp/{authz,tools}.py`, `brandme_core/mcp/schemas/{executor_assertion,tool_invocation}.schema.json`,
`brandme_core/orchestrator/runtime.py`, `tests/fixtures/commerce/harness.py`, `tests/test_commerce_principal.py` (new),
`tests/test_{mcp,commerce_assistant,commerce_purchase,commerce_ap2}.py`.

Still open from S7 plan: S9 Spanner store (+ data-category export/delete), S10, S11 (TS routers still use the round-1
`req.principal`/`firstPartySession` shape until then), S12, S13.

### S8 defect found in round 1: lane JSON files were never committed

The root `.gitignore` ignores `*.json` (with a short allowlist). Round 1 (PR #35, merged as `7c61afd`) therefore
shipped code that reads **25 files that were not in git**: the vendored AP2 v0.2 schemas
(`brandme_core/domains/commerce/ap2_schemas/{ap2,ucp}/**` — only `NOTICE.md` landed), the MCP wire schemas
(`brandme_core/mcp/schemas/{tool_invocation,executor_assertion}.schema.json`) and
`tests/fixtures/providers/impact_feed_fictional.json`. My S1–S6 test counts came from a working tree that had them; a
fresh checkout of `bench/opus-commerce-agents-20261005` cannot import the MCP executor or validate AP2 mandates. This
stage adds them with `git add -f` (no `.gitignore` edit — that file isn't lane-owned) and re-runs the suite from a
clean worktree of the pushed commit (result below). Request to whoever owns `.gitignore`: allowlist
`brandme_core/**/schemas/**/*.json`, `brandme_core/domains/commerce/ap2_schemas/**` and `tests/fixtures/**/*.json`, so the next
lane doesn't hit the same silent drop.

Verified 2026-10-23: a clean `git worktree` of `4325a4d` (no untracked files) runs `tests/foundation` + lane suite
**274 passed, 0 skipped**; a clean worktree of `origin/bench/opus-commerce-agents-20261005` fails collection of
`tests/test_mcp.py` with `FileNotFoundError: brandme_core/mcp/schemas/tool_invocation.schema.json`.

## Stage S9 — Spanner commerce store, retry-safe transactions, My Data jobs (2026-10-23)

**Done.** `tests/foundation` + lane suite: **352 passed, 0 skipped** (emulator 1.5.58, AP2 SDK oracle). **71** of those
are the purchase / principal / AP2 / privacy suites re-run on `SpannerCommerceStore` against a database migrated by
the repository runner (V001 + V006 + V007); the same tests run on the in-memory store.

- **Retry-safe transactions.** Every service write is now `store.run(fn)`; `fn(tx)` only reads/writes rows and emits
  events (no provider I/O), so Spanner may re-run it. Helpers that write take `tx` explicitly; there are no nested
  transactions and no table scans in domain code — reads go through `get` and named queries
  (`brandme_core/domains/commerce/store.py` `QUERIES`).
- **`SpannerCommerceStore`** (`brandme_core/domains/commerce/spanner_store.py`): one codec per logical table onto the
  V006/V007 tables (child rows for cart/quote/order lines); `run` wraps `database.run_in_transaction` with a fresh
  per-attempt overlay so a callback reads its own writes, and writes events with foundation `write_events` in the
  same commit. Named queries are SQL over V007 indexes, merged with the overlay through the same predicates the
  in-memory store uses. Verified directly: a delegated purchase leaves 1 row in each commerce table, a `consumed`
  reservation and 5 `OutboxEvents` (`commerce.delegation.created` … `commerce.order.observed`).
- **Behavior changes.**
  - Approval challenges store only `nonce_hash`; the plaintext nonce leaves once, to the trusted surface. The
    approval's `nonce` is that hash (unique per member, as V007 requires).
  - The challenge is bound to its operation as well as its quote.
  - A concurrent duplicate `execute` with the same key returns the winner's operation instead of failing.
  - Returns are now persisted as `ReturnRequests`, including handoffs.
  - **Removed** `brandme_core/domains/commerce/spanner_budget.py`, the round-1 standalone ledger. BM-COM-007 on
    Spanner is now covered through the service: `test_two_agents_cannot_overspend_shared_budget[spanner]` runs 20
    concurrent executions against one grant.
- **One active grant per (member, client) under concurrency.** `test_concurrent_grants_for_one_client_cannot_both_win`
  (6 threads) passes on both stores. Caveat: the emulator serializes read/write transactions, so this proves the
  check-and-insert sits in one transaction, not real-Spanner lock behavior. Production relies on Spanner's
  serializable read/write transactions (the scanned range is read-locked). No uniqueness index exists, because the
  "active" predicate depends on time.
- **My Data (`data_categories.py`) — export/delete now wired.**
  - `export(database, member_id)` returns JSON-safe rows per table; child rows are joined through their parent
    member.
  - `delete` runs `CommerceService.erase_*` as `system:privacy`, is idempotent, and needs an explicit `BRANDME_MODE`.
  - Grants: every active grant is revoked and its unsent work cancelled (`commerce.delegation.revoked` is emitted).
    Grants behind an order or a purchase still settling are kept, revoked; the rest are erased with their budget
    ledger.
  - Carts, challenges and unsent purchases' quotes are erased.
  - Device keys, order-less terminal operations and idempotency keys not guarding an in-flight purchase are erased.
  - Orders, their quotes/approvals and return requests are kept as financial evidence; the store refuses to delete
    orders.
  - Tests: `tests/test_commerce_privacy.py` (8). One of them caught over-retention of settled orders' idempotency
    keys, now fixed.
- **V007 amended (pre-integration).** Added `CheckoutQuotes.terms JSON NOT NULL` (return/recurrence terms; a quote
  could not be reconstructed or its hash re-verified without them), plus indexes `PurchaseOperationsByDelegation`,
  `CheckoutQuotesByMember` and `ApprovalChallengesByMember`. This changes V007's checksum. V007 has only ever been
  applied to throwaway emulator databases (bench branches, no shared environment), so no ledger anywhere holds the
  old checksum. If one does, it must be re-created, not migrated. The lane owns only V006/V007, so this is the only
  way to change them.
- **Known limits.**
  - Quote line titles (display-only, not hashed) are not persisted.
  - `rows()`/`outbox()` on the Spanner store are introspection helpers for tests and ops tooling, not domain paths.
  - Data-category deletion does not yet suppress re-import from provider order webhooks for an erased member. No
    provider sends member-keyed data today; the simulator's events key on orders, which are retained.

Files: `brandme_core/domains/commerce/{store,spanner_store,service,records,data_categories}.py` (−`spanner_budget.py`),
`brandme-data/spanner/migrations/V007_commerce.sql`, `tests/fixtures/commerce/{stores,harness}.py`,
`tests/test_commerce_{privacy,purchase,principal,ap2,migrations}.py`.

### S9 addendum — CI does not gate this lane's tests (request to file owners)

Green CI on PR #51 says nothing about the commerce lane:

- `.github/workflows/ci-cd.yml:87` runs `pytest tests/ -v || echo "Tests not implemented yet"`, so any failure is
  masked.
- Foundation's `pnpm check` (`scripts/brandme.mjs` `check()`) runs only `tests/foundation`.
- Foundation's hashed venv (`scripts/python/requirements.lock`) lacks four of this lane's runtime pins, so the lane
  suite could not even import there.

That is how the missing-JSON defect above stayed green. None of these files are lane-owned. Proposed patch for
opus-foundation, which owns `scripts/`:

1. `scripts/python/requirements.lock` — add these entries. Digests are from the PyPI JSON API for the exact releases.
   `cryptography==50.0.2`, `pyyaml` and `typing-extensions` are already locked.
   ```
   jwcrypto==1.6.1 \
       --hash=sha256:77e856818e514cb3d64a1043b6885a7d52f5cc37773f5e944de02103c8d3a54f \
       --hash=sha256:a1e1570da5c2e35dbcd375ec1d2891a24de8eb35ee2c1fe8e91978efb72cfe90
   pyjwt==2.15.1 \
       --hash=sha256:42d59d631f7768a1028a64c7ff581a9bf7519804daf91fc5b6c56e30eec5e193 \
       --hash=sha256:4f259e80cdfb6b3fc18a7de51fd1ef9ec79652f25019bae68975ca2468a34df8
   rfc8785==0.1.4 \
       --hash=sha256:520d690b448ecf0703691c76e1a34a24ddcd4fc5bc41d589cb7c58ec651bcd48 \
       --hash=sha256:e545841329fe0eee4f6a3b44e7034343100c12b4ec566dc06ca9735681deb4da
   sd-jwt==0.10.4 \
       --hash=sha256:82f93e2f570cfd31fab124e301febb81f3bcad70b10e38f5f9cff70ad659c2ce \
       --hash=sha256:d7ae669eb5d51bceeb38e0df8ab2faddd12e3b21ab64d831b6d048fc1e00ce75
   ```
2. `scripts/brandme.mjs` `check()` — add a step after the foundation tests. Without an emulator, the Spanner variants
   skip with a reason, like the foundation suites do; the AP2 SDK oracle tests skip without `AP2_SDK_PYTHON`.
   ```js
   ['python commerce lane tests' + (emulator ? '' : ' (emulator suites skipped)'), PY, ['-m', 'pytest',
     'tests/test_commerce_quote.py', 'tests/test_commerce_purchase.py', 'tests/test_commerce_ap2.py',
     'tests/test_commerce_protocols.py', 'tests/test_commerce_assistant.py', 'tests/test_commerce_migrations.py',
     'tests/test_commerce_principal.py', 'tests/test_commerce_privacy.py', 'tests/test_providers.py',
     'tests/test_mcp.py', '-q', '-p', 'no:cacheprovider', '--timeout=300']],
   ```
3. Drop the `|| echo` in `ci-cd.yml:87`, or remove that job if `foundation.yml` is the gate.

Until then, this file's local results (emulator + oracle, from a clean worktree) are the only evidence for this lane.

## Stage S10 — `packages/provider-contracts` normalized payloads (2026-10-23)

**Done.** Package `type-check` (tsc 5.9.3) and `test` both pass, 7/7, on Node **24.21.0**. That is the repo's
`.nvmrc`; the binary was fetched from nodejs.org and its SHA-256 checked against the release `SHASUMS256.txt`, because
the container only had Node 22. Python suite: **353 passed, 0 skipped**.

- **Added:**
  - Capability states, `EXECUTABLE_STATES`, `VERIFYING_EVIDENCE`, `PROVIDER_ERROR_KINDS`.
  - `ProviderPublic` / `Capability` / `CheckoutQuote` re-exports from `@brandme/contracts`.
  - `capabilityOf()` / `canExecute()`: an unlisted capability reads as `unsupported`.
  - Normalized payloads mirroring `brandme_core/domains/providers/contracts.py`: `SourceVariant`, `CatalogPage` (with
    tombstones), `InventoryObservation`, `CartLineRequest`, `ProviderCart`, `QuotedLine`, `ProviderQuote`,
    `CheckoutTerms`, `SubmitRequest`, `SubmitAck`, `HandoffLink`, `ObservedLine`, `OrderObservation`, `WebhookEvent`.
  - Interfaces `CatalogFeedProvider`, `CheckoutHandoffProvider`, `ReturnsProvider`.
- **Changed:**
  - The commerce interfaces use those payloads instead of `unknown`.
  - `CheckoutProvider.submit` takes a `SubmitRequest`.
  - `CartProvider` uses full replacement, guarded by the domain revision, as in Python.
  - `OrderProvider` gains `lookupByIdempotencyKey`, for reconciliation.
  - `ProviderError` gains `transmitted`, which is always set for `outcome_unknown`; a transmitted request is never
    `retryable`. No TypeScript code consumed the old signatures (`grep` across the repo).
  - Other lanes' interfaces (`ReceiptImporter`, `TryOnProvider`, `RightsIssuer`, `ManufacturingProvider`,
    `ContextProvider`) are unchanged.
- **Vocabulary alignment:** Python `ProviderErrorKind.MALFORMED_RESPONSE` is now `"malformed_provider_response"`,
  matching the TS package and ch.05 §1 wording. MCP problem code: `provider_malformed_provider_response`.
- **Drift guard:** `tests/test_providers.py::test_typescript_provider_contracts_share_the_python_vocabulary` parses the
  TS source and asserts the capability names, states, executable states, verifying evidence and error kinds equal the
  Python ones.

Files: `packages/provider-contracts/{src/index.ts,test/guard.test.ts,README.md}`,
`brandme_core/domains/providers/contracts.py`, `tests/test_providers.py`.

## Stage S11 — Routers on foundation middleware; unmounted domain HTTP API (2026-10-23)

**Done.** Results:

- Python: **368 passed, 0 skipped** (includes the new `tests/test_commerce_http.py`, 15 tests).
- Gateway, on Node 24.21.0: `tsc --noEmit` clean; ESLint clean on `src/routes/v1/*.ts`. Full gateway vitest run
  **34/34**, of which `commerce.test.ts` is 16 and foundation's `me.test.ts` still passes against the emulator.
- **Nothing is mounted.** `routes/v1/index.ts` (foundation) is untouched. No service starts the Python app.

**TypeScript routers** (`brandme-gateway/src/routes/v1/{commerce,catalog,providers,assistant,delegations}.ts`):

- **Foundation conventions.** The principal is `res.locals.principal` (foundation `Principal`); the round-1 local
  `Principal`/`req.principal`/`firstPartySession` are gone. Errors are foundation `ApiProblem` → problem+json via
  `handle`/`problemHandler`, with `request_id`.
- **Authority split:**
  - `requireAgentScope`: a first-party session (`via: 'session'`, no delegation) passes; bearer callers need the
    commerce scope.
  - `requireRole('provider:admin')`: always required, so a member session is never an operator.
  - `requireTrustedSurface`: a first-party session only.
- **Request handling:**
  - Idempotency-Key is 16–128 characters. Cart edits need `If-Match`; `ETag` passes through.
  - Domain problems keep their code and extras (e.g. `current_version`). A domain 401 (gateway assertion refused)
    becomes 503 `dependency_unavailable`, never "you are unauthenticated".
  - The webhook relay refuses a parsed body; it must be mounted with `express.raw` before JSON.
- **Routes:**
  - Contract routes from `@brandme/contracts` (carts, quote, approvals, `POST /commerce/purchases` with
    `PurchaseRequest`, orders, returns, catalog, delegations, capabilities, assistant).
  - **Lane extensions not yet in the contract**, for opus-foundation to add: `POST /commerce/operations` {quote_id}
    (request approval of an exact quote), `GET /commerce/operations/:id`, and
    `POST /commerce/operations/:id/approval-challenge`. Without them a member UI cannot reach the trusted-surface
    challenge.
- **Transport** — `createHttpCommerceDomainClient` in `commerce.ts`:
  - Each call signs an ES256 assertion: `aud` `brandme:commerce-domain`, at most 60 s, unique `jti`. The principal
    claim is snake_case, and `session_id` is only set for `via: 'session'`.
  - It posts to `/internal/commerce/v1/{operation}`. Webhooks go with a principal-less service assertion and the raw
    body base64-encoded.
  - It never retries. A transport failure is a retryable 503; the caller retries with the same Idempotency-Key.
  - Wire schema: `brandme_core/mcp/schemas/domain_assertion.schema.json`.

**Python** (`brandme_core/domains/commerce/http_api.py`, FastAPI 0.104.1 as pinned in `brandme_core/requirements.txt`
and the foundation lock):

- **`POST /internal/commerce/v1/{operation}`**, 25 operations. Each one has a strict argument allowlist, and unexpected
  fields are refused (`unexpected_field`). `DomainError` maps to problem+json.
- **Webhooks:** `POST /internal/commerce/v1/webhooks/{provider_id}` needs a service assertion. A signature or replay
  failure gets a bare `webhook_rejected`.
- **Assertions:** `ExecutorAssertionVerifier` gained `audience=` and `allow_session=`. The MCP audience can never be
  constructed with sessions allowed. The domain audience also accepts `simulated` assurance and principal-less service
  assertions.
- **Assistant:** a member session drives Brand.Me's assistant only through its grant to `brandme-assistant`. With no
  grant it gets `delegation_required`. The task runs under that grant via the same MCP dispatch path.
- **Operator console:** `provider.list/get/health/setup.get` are read-only views of the registry. They show whether a
  credential is configured, never its reference. **`provider.setup.update` and `provider.verify` answer 501
  `not_implemented`**: the operator setup workflow (V006 `ProviderSetupItems`) is not built, and the endpoint says so
  instead of pretending.
- **Service additions:** `list_delegations`, and `execute_approved_quote` (contract `PurchaseRequest`, where
  `delegation_id` must equal the caller's own grant). Catalog search moved to
  `brandme_core/domains/providers/catalog.py` and is shared by the MCP tool and this API.

**Cross-language check (one-off, local):** assertions signed by the TS client, for a session, a bearer and a webhook,
verify with the Python domain verifier. The MCP verifier refuses the domain token with "assertion not issued for
brandme:mcp-executor". `test_assertion_shape_matches_the_published_schema` holds the Python side to the schema. No CI
runs both languages together.

Addendum to the S9 CI request: also add `tests/test_commerce_http.py` to the proposed `check()` step.
`fastapi`/`httpx` are already in the foundation lock.

## Stage S12 — Console pages for providers and commerce operations (2026-10-23)

**Done.** Pages live under `brandme-console/app/(ops)/`, which is lane-owned:

| Route | What it shows | Gateway read |
|---|---|---|
| `/providers` | Registered providers | `GET /api/v1/providers` |
| `/providers/[id]` | Sanitized provider record and capabilities | `GET /api/v1/providers/{id}` |
| `/providers/[id]/setup` | Read-only checklist derived from the registry | `GET /api/v1/providers/{id}/setup` |
| `/providers/[id]/health` | Capability states with evidence kind, and what can run now | `GET /api/v1/providers/{id}/health` |
| `/commerce/operations` | Unknown outcomes, interrupted submissions, unreconciled provider events. Read-only, no member identifiers | `GET /api/v1/commerce/ops/queue` |

The shared server-only loader and page states are in `app/(ops)/providers/_data/`. The `_` prefix keeps them out of
routing; `lib/` would be swallowed by the global ignore rule.

- **Shell contract v1:**
  - Server Components returning fragments; `ConsolePageHeader` supplies the single `h1`; no `main`, nav or
    `html`/`body` of their own.
  - Wide tables sit in labeled, focusable `console-table-region`s.
  - Only `--bm-*`/shell helper classes; no new colors. No shell file changed.
- **Authorization:**
  - Pages forward only the incoming `Authorization: Bearer` header to the gateway, never cookies. Foundation's
    principal middleware verifies it, and the lane routers require `provider:admin` or `commerce:operator`.
  - Every non-200 outcome is a distinct state with no data: no gateway configured, signed out, missing role, provider
    not registered, `not built` (501), unavailable.
  - Navigation visibility grants nothing.
- **New domain read:** `CommerceService.operator_queue`, operation `commerce.ops.queue`. It needs the
  `commerce:operator` role, which a member session never implies, and returns no member identifiers. Gateway:
  `createCommerceOpsRouter`, to be mounted by foundation at `/api/v1/commerce/ops`. Tests run on both stores
  (`test_operator_queue_needs_operator_role_and_hides_members`) and as gateway route tests.
- **Evidence.** All of it ran in a scratch `git worktree` of `origin/bench/astra-consumer-ui-20261005` (`a37ec2b`)
  with these pages copied in. Nothing of astra's is committed here.
  - Toolchain: Node 24.21.0 and per-app `npm install` (Next 14.2.35, React 18.3.1, TypeScript 5.9.3). The ranges
    resolved newer than astra's 14.1.0 baseline.
  - `tsc --noEmit` clean. `next build` succeeds; all 5 routes are dynamic.
  - Chromium smoke (Playwright 1.56.1 + axe-core 4.10.2, preinstalled chromium-1194): **28/28**.
    - Fixtures were generated by the real Python `CommerceHttpApi` against the simulator, including a real
      `outcome_unknown` purchase, and served by a fake gateway that enforces a bearer.
    - Each page at 320×844 and 1440×900, light and dark: 200, exactly one `main` and one `h1`, expected content, no
      horizontal overflow, zero axe `wcag2a/2aa/21aa` violations, no page errors.
    - States: signed out, member token (role missing), unknown provider, no gateway configured. Each shows its notice
      and no tables.
  - The smoke caught one real defect, now fixed: a `sr-only` header label is `position:absolute` and escaped the
    table's scroll region, widening the page at 320px.
- **Not established:**
  - Screen readers, real devices, a real gateway with mounted routers, and an operator identity provider: `not_run`.
  - `networkidle` never settles on these pages because the shell's nav links prefetch other lanes' unbuilt routes.
    That is shell behavior, noted for astra, and harmless here.

## Stage S13 — Simulator exchange; BM-COM-011 exchange case (2026-10-23)

**Done.** Python suite: **374 passed, 0 skipped**.

- **Simulator** (`LocalAtelierProvider.exchange`): an even exchange, same price (e.g. another size), of delivered,
  unreturned units.
  - The original line records the return; a replacement line is added with `exchanged_from_ref`.
  - Stock moves. **No money moves.** A signed `exchange.created` webhook follows.
  - Refused: a different price (that is a return plus a new purchase), undelivered units, an unknown or out-of-stock
    replacement.
- **Domain:**
  - Replacement lines get their Brand.Me `variant_id` from the provider's own resolver. This is a pure lookup with no
    I/O, so it is safe inside the transaction. They previously arrived as `null`.
  - `commerce.order.observed` gains `wardrobe_effect: "exchanged"`. Schema v1 is not yet consumed by another lane, so
    the enum was widened in place.
  - Order fulfillment drops to `partially_fulfilled` until the replacement is delivered, then returns to `fulfilled`
    (`arrived`).
  - The purchase operation's summary state stays `fulfilled`. The state machine has no edge back, and the summary is
    advisory while the order facts are authoritative.
- **Tests** (both stores):
  - `test_exchange_keeps_history_and_tracks_the_replacement`: history kept; payment untouched; event lines carry
    `exchanged_from_ref` and evidence refs.
  - `test_uneven_or_undelivered_exchange_is_refused_by_the_provider`.
  - With the existing partial-shipment and refund tests, BM-COM-011 ("partial shipment, exchange and refund → correct
    order lines and wardrobe quantities with evidence") is covered against the simulator. No live provider is
    verified.

### S12 fix — console type-check on this branch (CI `regression`, 2026-10-23)

My S12 pages imported the shell's optional `@/components/console-page-header`. That component exists only on astra's
unmerged bench branch, so `regression` → `brandme-console: type-check` failed on `72e593e` (TS2307 in all five
pages). The scratch-merge evidence hid it, because astra's files were present there.

**Fixed:** a lane-owned `app/(ops)/providers/_data/page-header.tsx` renders the same markup and shell classes
(`console-page-header`, `console-eyebrow`, `console-page-actions`). The contract makes the shell header optional, so
this stays within it.

**Re-verified:**
- On this branch: `bash scripts/regression/modules/brandme_console.sh` ✅.
- In the astra scratch merge: `tsc` ✅, `next build` ✅, Chromium smoke **28/28**.

## Stage S14 — Independent review of the round-2 diff, and fixes (2026-10-23)

An independent reviewer read `git diff 7c61afd..HEAD` without seeing my conclusions. I re-verified every finding
before fixing it. Python suite: **398 passed, 0 skipped**, with 24 new regression tests, most of them run on both
stores. Gateway vitest 36/36, `tsc` and ESLint clean. `@brandme/provider-contracts` 7/7. Console regression module ✅.

| # | Finding (verified) | Fix | Test |
|---|---|---|---|
| 1 | **High.** After the member approved, an agent could edit the cart, and the purchase submitted the edited cart. Approval bound the quote hash, but the retailer received different goods (reproduced: approved size M, provider ordered L). The gap dates from round 1. | (a) Execute refuses unless the cart is still at `quote.cart_revision`. (b) `SubmitRequest` carries the exact quoted lines (Python and TS contracts), and the adapter must refuse a checkout whose provider-side cart differs; the simulator answers `checkout_changed`. This closes the window between the domain check and provider I/O. | `test_cart_edited_after_approval_is_never_bought`, `test_provider_cart_changed_behind_our_back_is_refused_at_checkout` |
| 2 | `update_cart`/`quote_cart` skipped the grant's mode and provider checks, and agents could edit carts other clients built. Returns needed only `commerce:cart`, so a prepare agent could return any of the member's orders. | `_guard_agent_cart`: no research mode, provider must be in the grant, own client's carts only. Returns need `commerce:purchase` (domain and gateway) and an order placed under the agent's own grant. | `test_agent_cannot_touch_carts…`, `test_returns_need_purchase_authority…`, gateway `returns need purchase authority from agents` |
| 3 | Returns ignored `Idempotency-Key` and did not count pending returns, so three identical calls reached the provider three times. | The intent and idempotency record commit before provider I/O. Open `return_requested` units count against the returnable quantity and become `received` when the provider reports the return. The HTTP adapter now passes the key. | `test_return_requests_are_idempotent_and_counted_until_received`, `test_return_idempotency_key_reaches_the_domain` |
| 4 | A bearer with no grant, or another grant, could read or cancel the member's assistant task. | `AssistantRuntime.get`: the member's own session sees their tasks; an agent only the tasks of its active grant. The adapter no longer exempts agents. | `test_agent_without_the_tasks_grant_cannot_read_or_cancel_it` |
| 5 | The member's own approved purchase was cancelled when the drafting prepare agent's grant expired. | `_submit` checks the executing grant (`approval.delegation_ref`). | `test_member_buys_its_approved_purchase_after_drafting_grant_expires` |
| 6 | Two challenges could approve one operation, leaving an orphan approval. | Approval requires `awaiting_approval` inside the transaction. | `test_an_operation_cannot_be_approved_twice` |
| 7 | Spanner: multi-line orders always looked changed, because the store returns lines in key order, giving duplicate events. | Lines are compared by `source_variant_ref`. | `test_unchanged_multi_line_observation_emits_nothing`; fails on `[spanner]` without the fix |
| 8 | A refused simulator exchange still moved stock. | Every check now runs before stock moves. | `test_refused_exchange_moves_no_stock` |
| 9a | Spanner: a $0 delegated purchase would violate `amount_minor > 0` at commit. | Zero amounts write no ledger row. | `test_zero_amount_reservation_writes_no_ledger_row` |
| 9b | Spanner: re-registering a revoked surface key would hit ALREADY_EXISTS. | `insert_or_update`, clearing `revoked_at`. | `test_surface_key_can_be_registered_again` |
| — | Found while writing 9a: a Spanner `run()` callback that touches nothing fails at commit. | Begin with `SELECT 1` when untouched. | Same test, `[spanner]` |

**Known limit, not fixed:** the single-use `jti` cache in `ExecutorAssertionVerifier` is per process. With several
domain replicas, a captured assertion could be replayed once per replica inside its ≤60 s lifetime. A shared replay
store (e.g. a Spanner table keyed by `jti` with TTL) is needed before more than one replica serves the commerce
domain or the MCP executor.

The reviewer also checked these and found them sound:
- The MCP hop refusing sessions and principal-less assertions.
- Scope intersection; the trusted-surface and assurance gates.
- Execute atomicity and retry safety.
- Spanner overlay merges.
- Privacy jobs keeping evidence.
- Operator roles, and the console pages forwarding only the bearer.

## Stage S15 — Reconciled with `main`: My Data, migration ledger, Next 15, shell seam (2026-10-23)

Founder Ultra Plan received (`Commerce Agents — Opus`). This stage is item 1, part one: bring round 2 onto
what `main` became after round 1 merged (W11 integration `3cdde59`, the My Data framework, the Pub/Sub outbox
worker, chain/rights work, migrations V002/V008–V014, the Next 15 console). A read-only investigation compared
`HEAD` with `origin/main` (`5174ec2`) before any change.

**Merge.** `origin/main` merged into the lane branch (`ce85fd0`). No textual conflicts: since `7c61afd` the two
sides changed disjoint files (74 vs 247). Main made no edits to lane files, and nothing outside the lane imports
`brandme_core.domains.commerce`, `brandme_core.mcp` or `brandme_core.orchestrator`. The semantic gaps found, and
what was done:

| Gap on `main` | Fix | Evidence |
|---|---|---|
| Main's runner checksums applied migrations. V007 was applied as merged, and round 2 had edited it in place (quote `terms`, three indexes). | V007 restored byte-for-byte; the round-2 schema is a new `V015_commerce_quote_terms.sql`. Rows written before V015 backfill `terms = {}`, which the store refuses to decode (`QuoteExpired`): unrecorded terms are never approvable. | `test_v007_is_unchanged_and_v015_backfills_unknown_terms` (pins V007's SHA-256, applies V015 over a populated V007) |
| My Data on main uses `DomainPrivacyHandler` + `register_domain`. Commerce registered foundation categories, which main only reaches through a bridge that labels every category `erase`: retained orders would have been reported "deleted". | Native `CommercePrivacyHandler` registered at package import. Foundation registration removed (one path). `delete()` runs in the orchestrator's transaction (`SpannerCommerceStore.within`), with commerce's own events. Each category is self-contained. `commerce.orders` is `retain_legal` with a stated basis. A grant or quote behind an order reports an exception; a purchase still settling keeps the job open (`done=False`). `export()` reads allowlisted columns from the orchestrator's snapshot. | `tests/test_commerce_privacy.py` drives the real `MyDataService` on the V009 tables: receipts, replay, order independence, settling purchases |
| Main requires `assert_processing_allowed` in every personal-data writer. Commerce had none. | Every member/agent write checks it inside its own transaction (`ProcessingRestricted`, 409). `processing_basis()` lets queued assistant work carry its start time. Revocation is always allowed. Provider settlement writes (acks, reconcile, webhooks, observations) are **not** guarded: they record what a provider did with money and are retained evidence. | `test_member_and_agent_writes_are_refused_while_deletion_is_pending`, `test_account_deletion_freezes_every_commerce_write`, `test_queued_assistant_work_cannot_recreate_deleted_data` |
| Main pins `next 15.5.28`; the pages used Next 14's synchronous `params` and `headers()` (`TS2339` under 15). | `await params` / `await headers()`. | `tsc` + `next build` with main's lockfile |
| Console header (Ultra Plan item 4). | Pages import `PageHeader` only from `providers/_data/shell.ts`. The local header mirrors shell contract **1.1.0** props and markup. Adopting the shell's `ConsolePageHeader` is one line in that module. | The pages, with that line swapped, type-check and build on the shell branch (`264b6a0`) |

Main's gateway tests (vitest 3.2.7) pass with the lane routers present; the lane's 18 router tests pass under
vitest 3.2.7 too. Python on the merged tree, emulator up: lane suites plus main's CI suites (foundation, rights,
privacy, privacy recovery, read API, privacy exports) **587 passed, 4 skipped** (the skips are main's Pub/Sub
emulator tests, which need the binary CI fetches).

**Deviation, recorded for the founder (outside the lane's owned paths):** the brief limits this lane to
V006/V007. Restoring V007 without losing round 2's schema needs a new migration, so this stage adds
`V015_commerce_quote_terms.sql` and the matching one-line reservation in `tests/foundation/test_migrations.py`
(`15: "commerce_quote_terms"`) plus a README paragraph. The integration lanes allocated V010–V014 the same way.
Alternative if refused: fold V015 back into V007 and accept checksum drift on any database that already applied V007.

**Still open from the investigation (handled in later stages of this round):**
- Commerce events are written but main's outbox worker publishes only the foundation catalog it imports.
- The assistant runtime calls the MCP executor's `_dispatch` directly, so model- or planner-proposed tool calls skip
  the audit record. The S11 note saying `_dispatch` audits was wrong; the audit lives in `invoke()`.
- Commerce events carry a random correlation id per event; the gateway does not forward `X-Request-Id`.
- `provider.setup.update` and `provider.verify` are still `_not_built`, so the setup page cannot save or test.

### Plan for the rest of this round (Ultra Plan order)

1. Round 2 review-ready: event catalog alignment, audited runtime tool path with correlation, provider setup save
   and connection tests (console forms), exchange fidelity against ch.05 §6 / BM-COM-011. Then undraft PR #51.
2. Payment and fulfillment adapter seams, chosen by dependency injection at startup; Stripe **test mode** as the
   first real payment adapter (refuses anything but `sk_test_` keys), with stripe-mock wire tests labelled as such.
3. A model-backed planner behind a provider-neutral adapter (Anthropic SDK first), deterministic fallback with no
   key, redacted run logs, token/cost budgets.
4. Check-in packet.

**PR target.** PR #51 targets `bench/opus-commerce-agents-20261005` (`7c61afd`), which `main` already contains.
With `main` merged in, its diff against the bench branch would include main's 57 commits. Default taken: retarget
PR #51 to `main`, as the rights and foundation lanes did for their round-2 PRs (#40, #41, #53, #54).

### Credential manifest (names and scope only — never values)

| Name | Scope | Stored in | Created | Status |
|---|---|---|---|---|
| `STRIPE_TEST_SECRET_KEY` | Stripe **test mode** secret key (`sk_test_…`) for the payment adapter's live test-mode run | Cloud environment secret (to be added by the founder; not in the repo) | — | **Not present.** The agent cannot create Stripe accounts or keys from this container; live test-mode runs are `not_run` until it exists. |
| `BRANDME_DEV_ANTHROPIC_API_KEY` | Anthropic API key for the dev model planner only | Cloud environment secret (to be added; not in the repo) | — | **Not present.** Deliberately not `ANTHROPIC_API_KEY`, which the Claude Code session itself may read. Live model runs are `not_run` until it exists. |
