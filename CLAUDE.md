# CLAUDE.md — Honest Repo Map

> Short, accurate map of what is **actually wired up** in this repo, vs. what
> is stubbed or aspirational. The marketing-tone status documents
> (`README.md`, `FINAL_SUMMARY.md`, `docs/status/CURRENT_STATUS.md`) overstate
> readiness; this file is the ground-truth reference. When they conflict,
> trust this.
>
> **Forward-looking plan** (end-to-end + ACP / AP2 / A2A): see [`PLAN.md`](./PLAN.md).
>
> Last verified: 2026-04-27 by code-level audit.

## What this is

Brand.Me Labs is a microservice platform aimed at garment authentication and
a circular-economy lifecycle for physical assets. The intended end state is a
dual-blockchain (Cardano public, Midnight private) "Product Cube" with seven
visibility-gated facets, accessible by external agents through MCP tools.

Today, only the consent/policy/provenance layer is real against emulators.
Everything past the orchestrator's response is mocked.

## Per-service status

| Service | Port | Lang | Status | One-line evidence |
|---|---|---|---|---|
| `brandme-core/brain` | 8000 | Py | **REAL** | Real Spanner Asset lookup at `brandme-core/brain/main.py:62-74`; calls policy + orchestrator. |
| `brandme-core/policy` | 8001 | Py | **REAL** | Real consent graph queries via `brandme_core/spanner/consent_graph.py`; provenance verify endpoint live. |
| `brandme-core/orchestrator` | 8002 | Py | **STUB** | Returns hardcoded `f"cardano_tx_{transfer_id[:16]}"` at `brandme-core/orchestrator/main.py:99`; comment at `:93-94` says "v6 simplified, in production this would trigger Celery." No Celery service in compose. |
| `brandme-cube` | 8007 | Py | **STUB / UNVERIFIED** | Routes import; policy gates real; **all tests are `test_placeholder()`** in `brandme-cube/tests/test_api.py`. `PRODUCT_CUBE_SUMMARY.md` explicitly states startup is untested. |
| `brandme-governance` | 8006 | Py | **STUB** | Only escalation listing implemented (`brandme-governance/governance_console/main.py:62-100`). No approve/deny endpoint. |
| `brandme-gateway` | 3000 | TS | **REAL** | helmet/CORS/rate-limit framework wired in `brandme-gateway/src/index.ts`; OAuth uses dev-client-id placeholders in compose. |
| `brandme-frontend` | — | TS | **NOT WIRED** | Components are placeholder UI (`<div>[Image]</div>` in `brandme-frontend/components/GarmentCard.tsx:21-22`); not in `docker-compose.yml`. |
| `brandme-console` | 3002 | TS | **NOT WIRED** | Service block commented out in `docker-compose.dev.yml:168-184`. |
| `brandme-chain` | — | TS | **NOT WIRED** | TX builder service commented out in `docker-compose.dev.yml:152-166`. Type defs only, no Cardano/Midnight client code. |
| `brandme-agents/identity` | 8005 | Py | **PARTIAL** | Init real; `ZKProofManager` framework present; actual proofs use stubs / `allow_stub_fallback`. |
| `brandme-agents/knowledge` | 8003 | Py | **STUB** | Spanner pool init only; no visible endpoint impls. |
| `brandme-agents/compliance` | 8004 | Py | **STUB** | `MIDNIGHT_ENABLED: "false"` in `docker-compose.yml:304`; ESG threshold hardcoded `0.5`; no real oracle. |
| `brandme-agents/agentic` | — | Py | **CLI only** | Not a service — `brandme-agents/agentic/cli/main.py` is a CLI tool. |
| `brandme-agents/branding` | — | — | **NOT WIRED** | Not in `docker-compose.yml`. |
| `brandme_core/*` (shared lib) | — | Py | **REAL** | `spanner/`, `firestore/`, `mcp/`, `zk/` — used by all working services. |

## What runs end-to-end today

The only real path:

```
client
  → brandme-gateway (broken — see below)
  → brandme-core/brain        (Spanner Asset lookup)
  → brandme-core/policy       (Spanner consent graph + provenance)
  → brandme-core/orchestrator (returns FAKE cardano_tx_* string)
```

Everything past the orchestrator response — Cardano anchoring, Midnight burn
proofs, ESG oracle verification, cube state machine transitions — is fake.

## What delivers product value today

A small but real set:

- Spanner-backed consent graph with O(1) lookups (`brandme_core/spanner/consent_graph.py`).
- Provenance chain reads + integrity verification (`brandme-core/policy` endpoints).
- Region policy YAML loading (`brandme-core/policy/region_rules.py:13` →
  `brandme-core/policies/{default,eu-west1,us-east1}.yaml`).
- Hash-chained audit-log writes (compliance service).
- JWT + token-bucket rate-limit middleware (in `brandme_gateway/`, not actually
  wired into `brandme-gateway/` — see below).
- Tests that actually pass: `tests/test_consent_graph.py`,
  `tests/test_provenance.py`, `tests/test_wardrobe.py`.

## Known broken imports

None currently. The `rateLimiter.ts` that `brandme-gateway/src/index.ts:22`
imports has been moved into `brandme-gateway/src/middleware/`.

## Safe-to-delete kill-list

Verified by grepping all of `*.py / *.ts / *.tsx / *.yml / *.yaml / Makefile / *.sh`
for any reference.

Nothing in this repo is currently safe to blindly delete.

| Folder | Verdict | Why |
|---|---|---|
| `brandme_gateway/` | **Now an orphan** | After moving `rateLimiter.ts` out, this folder holds only an unused alternate `auth.ts`. Safe to delete after confirming `brandme-gateway/src/middleware/auth.ts` (the imported one) is the canonical version. |
| `agents/` (shell scripts) | **DO NOT DELETE** | Used by `deploy-brandme.sh` (data-agent, database-agent, integration-agent, etc.). |
| `brandme-core/policies/` | **DO NOT DELETE** | Loaded at runtime by `brandme-core/policy/region_rules.py:13`. |

## Docs accuracy notes

- README claims **v9** "Agentic & Circular Economy"; `docs/status/CURRENT_STATUS.md`
  is titled **v8** "Global Integrity Spine". Trust v9.
- README and `FINAL_SUMMARY.md` claim "95% enterprise-ready". This is not
  defensible: orchestrator/cube/governance/chain/frontend/console all stub
  or not-wired. Treat as a marketing target, not a state description.
- `docs/next_steps/ROADMAP.md` was last updated 2025-01-27 — **16 months
  stale**. Lists then-future tasks that have either since shipped or been
  abandoned. Don't trust it.
- `PRODUCT_CUBE_SUMMARY.md` is the most honest internal doc and says cube
  startup is untested. Believe that one.

## Local dev quick reference

```bash
docker-compose up -d
# Spanner emulator: 9010 (gRPC), 9020 (REST)
# Firestore emulator: 8080
# Backend services: 8000–8007
# brandme-gateway, brandme-frontend, brandme-console, brandme-chain,
# mcp-server, midnight-stub, cardano-stub: NOT running by default

pytest tests/test_consent_graph.py tests/test_provenance.py tests/test_wardrobe.py -v
# These actually pass. Other suites are placeholders.
```

Make targets: `make install`, `make lint`, `make format`, `make type-check`.

## When updating this file

- Verify by reading code, not by reading other docs.
- Cite file:line for every claim.
- If you flip a service from STUB → REAL, also remove its row from "What's
  stub". Don't let the table drift.
