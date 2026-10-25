# Lux → Brand.Me Lift and Shift

> Companion to `BRANDME_AUDIT.md`. Wave 1 is **built, tested, and in this
> commit**. Waves 2–4 are planned and sized, not built.

## Why this works

The two products are unrelated — luxury real estate and garment
authentication — but the *platform underneath* is the same shape:

| | Lux | Brand.Me |
|---|---|---|
| Runtime | FastAPI on Cloud Run | FastAPI on Cloud Run |
| Tenant key | `realtor_id` | `owner_id` |
| Graph store | Cloud Spanner Graph | Cloud Spanner |
| Doc store | — | Firestore |
| Events | Pub/Sub, 30 topics | Pub/Sub (planned) |
| Agent surface | MCP servers | MCP tools (`brandme_core/mcp/`) |
| Language | Python 3.12 + TS | Python 3.11 + TS |

Both are FastAPI-on-GCP multi-tenant platforms with an MCP agent surface. The
plumbing — tenancy, config, observability, event brokering, quality gates — is
domain-independent, and Lux's version of it is already hardened.

## How coupled is Lux's foundation, actually

Measured, not assumed. Counting domain vocabulary per file:

| Lux file | LOC | `realtor` | real-estate terms | Tier |
|---|---:|---:|---:|---|
| `services/runtime/db.py` | 160 | 0 | 0 | A |
| `services/runtime/health.py` | 46 | 0 | 0 | A |
| `services/runtime/http.py` | 50 | 0 | 0 | A |
| `services/api_gateway/rbac.py` | 46 | 0 | 0 | A |
| `services/api_gateway/errors.py` | 39 | 0 | 1 | A |
| `compass_mcp/errors.py` | 62 | 2 | 0 | A |
| `services/persistence/projection_outbox.py` | 215 | 0 | 0 | A |
| `protocols/v1/tenancy.py` | 437 | 1 | 0 | A |
| `gates/__init__.py` | 41 | 0 | 0 | A |
| `services/runtime/config.py` | 321 | 0 | 7¹ | B |
| `services/observability.py` | 361 | 59 | 0 | B |
| `hooks/broker.py` | 284 | 14 | 3 | B |
| `services/api_gateway/auth.py` | 549 | 20 | 1 | B |
| `compass_mcp/_base.py` | 157 | 11 | 1 | B |
| `services/runtime/migrate.py` | 3,007 | 21 | 216 | C |
| `graph/client.py` | 1,369 | 99 | 202 | C |
| `services/persistence/uow.py` | 1,883 | 0 | 290 | C |

¹ Six of the seven are the `@property` decorator. Real coupling ≈ 1.

- **Tier A — copy.** No domain vocabulary. Import-path rewrite only.
- **Tier B — copy + rename.** `realtor_id` → `owner_id`, plus a retargeted
  env-var or topic inventory. Logic unchanged.
- **Tier C — pattern, not code.** Structure and tests are the asset; the SQL
  and schema are Lux's and must be rewritten for Brand.Me's model.

The important result: **the entire Tier A + B set is 2,768 lines of hardened
platform code with essentially no real-estate in it.**

## Wave 1 — built (this commit)

`brandme_foundation/` — 1,646 lines ported, **62 tests passing**.

| Module | Source | Change |
|---|---|---|
| `errors.py` | `compass_mcp/errors.py` | Verbatim |
| `gates/__init__.py` | `gates/__init__.py` | Verbatim |
| `runtime/http.py` | `services/runtime/http.py` | Import paths |
| `runtime/health.py` | `services/runtime/health.py` | Import paths |
| `tenancy/models.py` | `protocols/v1/tenancy.py` | Domain enums (below) |
| `hooks/broker.py` | `hooks/broker.py` | `realtor_id` → `owner_id` |
| `hooks/events.py` | `protocols/v1/entities.HookEvent` | Extracted; `owner_id` |
| `hooks/topics.yaml` | `hooks/topics.yaml` | Brand.Me's 9 topics replace Lux's 30 |
| `observability.py` | `services/observability.py` | Broker injection; cost categories |
| `runtime/config.py` | `services/runtime/config.py` | Full env-contract retarget |

### Domain decisions made

- **Tenant key is `owner_id`.** Chosen from the repo's own inventory (931
  `user_id`, 195 `owner_id`, 2 `brand_id`) and from the consent graph's
  `check_consent(viewer_id, owner_id, …)` signature — the viewer→owner pair is
  already Brand.Me's authorization boundary.
- **`OrganizationKind`** `brokerage|team|solo` → `brand|retailer|individual`.
- **`MembershipRole`** `realtor` → `custodian` (Lux's `OWNER` already existed;
  a blind rename would have collided the two enum members).
- **`OrganizationCapability`** `clients.*`/`properties.*` →
  `assets.*`/`provenance.*`/`consent.*`.
- **Runtime role** `graph_projector` → `cube_projector`, with its least-
  privilege check moved from `DB_USER=lux_graph_projector` to
  `SPANNER_DB_ROLE=brandme_cube_projector`.
- **Cost categories** `model|gpu|tts` → `model|zk_proof|chain_anchor`.

### Two behavioral changes, both deliberate

1. **Observability broker lookup is injected.** Lux resolved its broker by
   lazy-importing its own gateway module. Brand.Me's services are separate
   processes with no shared gateway, so `install_broker_lookup()` registers it
   at startup instead. Import-safe everywhere; covered by two tests.
2. **`on_high_risk_alert` was added to `topics.yaml`.** The cost meter
   publishes it. Without the topic row the broker refuses the publish and the
   alert is silently dead — a regression test now pins this.

### Verification actually performed

```
$ pytest tests/foundation -q
62 passed
```

Plus: every module imports standalone; no Lux import path survives anywhere in
`brandme_foundation/` or `tests/foundation/` (CI enforces both).

The ported invariants were **mutation-checked**, not just run:

| Mutation | Caught? |
|---|---|
| Tenant key removed from the spend bucket | ✅ 5 failures |
| Ceiling-alert dedupe removed | ✅ 1 failure² |
| Lux topic name left in a broker fixture | ✅ 6 failures |
| Lux enum member left in a tenancy fixture | ✅ collection error |

² Not caught on the first attempt. `record_spend` only fires on the ceiling
*crossing*, so the `(day, owner_id)` dedupe set is an independent second guard
that the original test never reached. A test that exercises it directly was
added, and the mutation then failed as it should.

### CI

`.github/workflows/foundation.yml` — a hard gate. No step carries `|| echo`.
It runs the suite, proves standalone imports, and greps for leaked Lux import
paths. This does not fix `ci-cd.yml`'s swallowed `test-core` job (Audit
Finding 2), which is left as-is deliberately: repairing it will turn the build
genuinely red, and that should be a deliberate decision, not a side effect of
this port.

## Waves 2–4 — planned, not built

### Wave 2 — the auth and MCP boundary (Tier B, ~750 lines + tests)

- `services/api_gateway/auth.py` → dev-token/JWT/JWKS modes that validate
  loudly at boot and refuse dev tokens outside `APP_ENV=dev`.
- `services/api_gateway/rbac.py` + `web/sitemap.yaml` → persona→route guard
  from a single source of truth.
- `services/api_gateway/errors.py` → the `MCPError` → HTTP status map.
- `compass_mcp/_base.py` → the MCP server base enforcing tenant presence,
  capability match, PII tokenization, and per-tenant rate limits at the
  boundary. Brand.Me's `brandme_core/mcp/tools.py` (923 lines) is the natural
  adopter.
- Reinstates the two tests Wave 1 omitted for lack of these modules.

### Wave 3 — persistence and migrations (Tier C, pattern only)

- `services/runtime/migrate.py` (3,007 lines) — checksum ledger, advisory
  lock, statement timeouts, baseline verification. **This is the fix for Audit
  Finding 5.** Lux's is Postgres/Cloud SQL; Brand.Me is Spanner-first (753
  Spanner refs vs 32 Postgres), so the ledger mechanics port and the DDL
  execution layer is rewritten.
- `services/persistence/projection_outbox.py` (Tier A, 215 lines) — a
  transactional outbox with a dedicated DB role. Ports nearly as-is and is
  what the cube projector needs.
- `services/persistence/uow.py` (1,883 lines) — **do not port.** It is 290
  real-estate terms deep. Port the *pattern*: one connection, one transaction,
  repositories that never commit.

### Wave 4 — the isolation gate (the point of the whole exercise)

- `gates/tenant_isolation.py` + `tests/test_isolation.py` (886 lines) —
  provision two synthetic tenants, populate both, assert no path returns the
  other's data. **This is the fix for Audit Finding 4**, and it is the single
  highest-value item in this document.
- Depends on Waves 2 and 3 (it needs auth, the MCP boundary, and persistence
  to have something to assert against).
- Lux's `graph/client.py` has a `SpannerGraphClient` behind an in-memory
  reference implementation. Brand.Me is already Spanner-first, so this backend
  maps more directly here than the Postgres layer does — worth pulling
  alongside Wave 3.

## What this does not buy

Honest limits:

- **Nothing above touches Brand.Me's actual product.** The orchestrator still
  returns a fake `cardano_tx_*`; the cube state machine, Midnight burn proofs,
  and the ESG oracle are all still unbuilt. This port makes the platform under
  those services trustworthy — it does not build them.
- **Tier C is not a copy.** Roughly 6,000 of Lux's lines are structure-only
  reuse. Budget them as informed rewrites.
- **The Spanner/Postgres split is real.** Lux's persistence hardening is
  Postgres-shaped. Brand.Me's Spanner-first stack means Wave 3 carries the
  most adaptation risk of the four.
- **Lux's own suite was not run here** (see the audit's verification notes).
  Wave 1's 62 tests were run; Lux's 45,463 lines were read, not executed.

## Suggested order

1. **Fix `ci-cd.yml`** (Audit Finding 2). Nothing else is trustworthy until a
   red build can actually be red. Small, and unblocks everything.
2. **Wave 2** — auth and the MCP boundary. Highest value per line, and
   `brandme_core/mcp/` is ready to adopt it.
3. **Wave 3** — the migration runner first, the outbox second.
4. **Wave 4** — the isolation gate, once there is something to isolate.

Adopting Wave 1 costs nothing: `brandme_foundation/` is additive and no
existing service imports it yet.
