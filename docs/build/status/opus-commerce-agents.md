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
