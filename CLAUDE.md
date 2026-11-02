# CLAUDE.md — Honest Repo Map

> **Current product build contract (2026-10-05):** read
> [`docs/design/brandme/README.md`](./docs/design/brandme/README.md) and every linked
> chapter before implementing the full Brand.Me experience. Start with the
> [Claude kickoff prompt](./docs/design/brandme/CLAUDE_BUILD_PROMPT.md).
> The package restores editable identity, social shopping, loyalty, the spatial
> wardrobe, AR, authorized commerce and Midnight rights to one implementation plan.
> It is a specification, not a claim that these features already work.
>
> **Dated audit correction:** at baseline `0f5f58a`, commerce handlers do exist in
> `brandme_core/mcp/tools.py:410-444` (`_checkout_quote`, `_purchase_request`, `_purchase_execute`; the file is
> 454 lines) and the Midnight client is the real adapter in `brandme-chain/src/midnight/adapter.ts` (there is no
> `brandme-chain/src/services/` directory). Those two citations were re-verified 2026-11-02 at `ed19dc1`; the
> service table below was re-verified 2026-11-02 at `cc75f22`. The older “no references”/“type defs only” wording
> below and in the archived `PLAN.md` is stale. These handlers are not verified integrations.
> See the [code evidence and current sources](./docs/design/brandme/07-repository-audit-sources.md).
> Current AP2 and Midnight implementation details come from the new package's
> dated primary sources, with re-verification at build time. Preserve this file's
> honesty, security and review requirements; do not promote a stub based on a plan.

> Short, accurate map of what is **actually wired up** in this repo, vs. what
> is stubbed or aspirational. The older marketing-tone status documents
> (`FINAL_SUMMARY.md`, `CURRENT_STATUS.md`, the cube session reports) overstated
> readiness and were moved under `docs/archive/` on 2026-11-02; this file is the
> ground-truth reference. When any document conflicts with it, trust this.
>
> **Historical plan** (April 2026, end-to-end + ACP / AP2 / A2A; self-marked superseded):
> [`docs/archive/2026-04-plan/PLAN.md`](./docs/archive/2026-04-plan/PLAN.md). The current build
> contract is the design package linked above; the live program roll-up is
> [`docs/build/implementation-status.md`](./docs/build/implementation-status.md).
>
> Last verified: 2026-11-02 by code-level audit (`docs/audits/2026-11-01/`); rows carry their own
> dates where they were re-verified after the 2026-04-27 baseline.

## What this is

Brand.Me Labs is a microservice platform aimed at garment authentication and
a circular-economy lifecycle for physical assets. The intended end state is a
dual-blockchain (Cardano public, Midnight private) "Product Cube" with seven
visibility-gated facets, accessible by external agents through MCP tools.

Today, the consent/policy/provenance layer and the consumer-domain path are real
against emulators (see below); everything past the legacy orchestrator's response
is mocked.

## Per-service status

| Service | Port | Lang | Status | One-line evidence |
|---|---|---|---|---|
| `brandme-core/brain` | 8000 | Py | **REAL** | Real Spanner Asset lookup at `brandme-core/brain/main.py:62-74`; calls policy + orchestrator. |
| `brandme-core/policy` | 8001 | Py | **REAL** | Real consent graph queries via `brandme_core/spanner/consent_graph.py`; provenance verify endpoint live. |
| `brandme-core/orchestrator` | 8002 | Py | **STUB** | Returns hardcoded `f"cardano_tx_{transfer_id[:16]}"` at `brandme-core/orchestrator/main.py:92`; the docstring at `:89` says "In production, this would trigger Celery tasks for async processing." No Celery service in compose; behind `profiles: [legacy]` (`docker-compose.yml:112`). |
| `brandme-cube` | 8007 | Py | **STUB / UNVERIFIED** | Routes import; policy gates real; `brandme-cube/tests/test_api.py` holds only `test_placeholder()` and `tests/test_service.py` one mocked unit test. Startup untested (`docs/archive/2025-10-cube-integration/PRODUCT_CUBE_SUMMARY.md`). Behind `profiles: [legacy]`. |
| `brandme-governance` | 8006 | Py | **STUB** | Escalation listing plus a decision endpoint (`brandme-governance/governance_console/main.py:119`) that records an **unauthenticated** `reviewer_user_id` as the approver; it therefore refuses strict modes at import (`brandme_core/boot.py`, verified 2026-10-24). |
| `brandme-gateway` | 3001 | TS | **REAL** | helmet/CORS wired in `brandme-gateway/src/index.ts`; config-driven per-address and per-member rate limits with problem+json 429 (`brandme-gateway/src/middleware/rateLimiter.ts`, in-process only); OIDC/JWKS in strict modes (`middleware/mode.ts`). Default port `src/config/index.ts:73`. |
| `brandme-frontend` | 3000 | TS | **PARTIAL** | Next.js consumer shell with guest journeys (`brandme-frontend/app/`: add, closet, discover, me, scan, style, today, …; PR #56). Runs as the `consumer` service (`docker-compose.yml:218-228`) and via `pnpm dev:demo`. Wardrobe is guest-local and there is no browser OIDC sign-in (audit WP-04/WP-08; `docs/audits/2026-11-01/claude-opus-02/evidence/journeys/wiring-trace.md`). Re-verified 2026-11-02. |
| `brandme-console` | 3002 | TS | **PARTIAL** | Runs only under `docker-compose.dev.yml:23-36` (operator console on 3002); its `/api/v1/ops/*` and provider calls hit routers the gateway does not mount (`brandme-gateway/src/routes/v1/index.ts:131-149`), so every ops screen ends unconnected. Not in `docker-compose.yml`. |
| `brandme-chain` | 3001 | TS | **PARTIAL** | Verified 2026-10-23. Real Midnight adapter (`brandme-chain/src/midnight/adapter.ts:204`) over a compiled Compact contract (`brandme-chain/contracts/src/brandme_rights.compact`, 15 circuits), served under `/midnight` (`brandme-chain/src/index.ts:36,54`); the gateway calls it when configured (`brandme-gateway/src/services/rights.ts:70-72`). Real proofs observed on a local network only (`brandme-chain/evidence/`); Preprod writes not yet observed; no Mainnet writes. Fallback flags are rejected (`brandme-chain/src/config/index.ts:33-34`); Cardano anchoring is unavailable by default (`brandme-chain/src/cardano/anchor.ts:64`). Not in `docker-compose.yml`. |
| `brandme-agents/identity` | 8005 | Py | **PARTIAL** | Init real; `ZKProofManager` framework present; actual proofs use stubs / `allow_stub_fallback`. |
| `brandme-agents/knowledge` | 8003 | Py | **STUB** | Spanner pool init only; no visible endpoint impls. |
| `brandme-agents/compliance` | 8004 | Py | **STUB** | No `MIDNIGHT_ENABLED` variable exists in code or compose (the old `docker-compose.yml:304` citation is stale; the file is 242 lines); ESG scores fall back to a hash stub (`brandme-agents/compliance/src/lifecycle/esg_verifier.py:163-169`) with threshold `0.5`; no real oracle. |
| `brandme-agents/agentic` | — | Py | **CLI only** | Not a service — `brandme-agents/agentic/cli/main.py` is a CLI tool. |
| `brandme-agents/branding` | — | — | **NOT WIRED** | Not in `docker-compose.yml`. |
| `brandme_core/domains` (consumer-domains) | 8010 | Py | **REAL (local evidence)** | FastAPI app `brandme_core/domains/persona/app.py` behind the gateway's consumer routers (`brandme-gateway/src/routes/v1/index.ts:142-143`) with ES256 principal assertions; compose service `consumer-domains` (`docker-compose.yml:195-217`). Gateway→domain→Spanner journey 16/16 and the outbox→Pub/Sub→ingress→jobs chain 18/18 on emulators (audit SC-59, SC-61, 2026-11-02). Not deployed; Helm `consumerDomains.enabled: false` by default (S2-OBS-004). |
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

The consumer-domain path is separate from that legacy scan chain and was executed on
emulators on 2026-11-02 (`docs/audits/2026-11-01/claude-opus-02/evidence/runtime/emulator-run.md`):
HTTP client → `brandme-gateway` → `brandme_core/domains/persona/app.py` → Spanner, and
`brandme_core/events/worker.py` → Pub/Sub emulator → `persona/ingress.py` → `persona/jobs.py`
(a friend-decision reward settled exactly once). Still unexecuted: the browser UI on top of
it, deadline expiry via `jobs`, and Pub/Sub retry under fault.

## What delivers product value today

A small but real set:

- Spanner-backed consent graph with O(1) lookups (`brandme_core/spanner/consent_graph.py`).
- Provenance chain reads + integrity verification (`brandme-core/policy` endpoints).
- Region policy YAML loading (`brandme-core/policy/region_rules.py:39-42` →
  `brandme-core/policies/region/{default,eu-west1,us-east1}.yaml`).
- Hash-chained audit-log writes (compliance service).
- Token-bucket rate limiting wired into `brandme-gateway/`
  (`brandme-gateway/src/middleware/rateLimiter.ts`); the orphan copy in
  `brandme_gateway/` was removed on 2026-11-02.
- Tests: CI `test-core` runs **all of `tests/`** (`.github/workflows/ci-cd.yml`).
  Verified 2026-10-24: `tests/test_consent_graph.py`, `tests/test_provenance.py`
  and `tests/test_wardrobe.py` do **not** pass (no fixture applies the legacy
  schema; `brandme_core/firestore/wardrobe.py:280` puts `SERVER_TIMESTAMP` in an
  array). They are quarantined as strict xfail with an owner and a blocker in
  `tests/conftest.py` `QUARANTINE`; the summary prints the quarantined count.

## Known broken imports

None currently. The `rateLimiter.ts` that `brandme-gateway/src/index.ts:22`
imports has been moved into `brandme-gateway/src/middleware/`.

## Safe-to-delete kill-list

Verified by grepping all of `*.py / *.ts / *.tsx / *.yml / *.yaml / Makefile / *.sh`
for any reference.

Nothing in this repo is safe to delete blindly. Removed on 2026-11-02 after the audits (history
stays in git): `brandme_gateway/`, `brandme_core/health.py`, the inoperable deploy chain
(`agents/`, `deploy-brandme.sh`, `scripts/deploy.sh`, `scripts/db-init.sh`, `scripts/backup.sh`,
`scripts/test-infrastructure.sh`, `init.sql`), the previous platform's `infrastructure/` configs,
`brandme-infra/terraform` (invalid, Cloud SQL) and the non-functional umbrella chart, and the seven
out-of-context Dockerfiles CI never built. The Makefile's build targets now use the five root-context
Dockerfiles that `ci-cd.yml` builds.

| Folder | Verdict | Why |
|---|---|---|
| `brandme_gateway/` | **Removed 2026-11-02** | Held a stale copy of `rateLimiter.ts` and an alternate `auth.ts` whose mock JWT parser accepted any 10+ character token; nothing imported or ran it (the regression module named `brandme_gateway` tests `brandme-gateway/`). |
| `agents/` + `deploy-brandme.sh` + `scripts/deploy.sh` | **Removed 2026-11-02** | Every `agents/*.sh` sourced `agents/lib/common.sh`, which did not exist; the chain could not run and one agent wrote credentials to a plaintext file (audit S2-OBS-003; packet section F). The prepared cloud path is `docs/build/deploy/gke-verification-packet.md`. |
| `brandme-core/policies/region/` | **DO NOT DELETE** | Loaded at runtime by `brandme-core/policy/region_rules.py:39-42`. |

## Docs map (2026-11-02)

- `README.md`: purpose and start-here links only (rewritten 2026-11-02).
- `docs/README.md`: index of the live documentation.
- `docs/design/brandme/`: the frozen build contract (its validator runs in `pnpm check`).
- `docs/build/`: the live program record (status logs, evidence, runbooks, security, orchestration);
  `docs/build/implementation-status.md` is the roll-up the design package asks for.
- `docs/audits/2026-11-01/`: the two dated audit packs (`codex-01`, `claude-opus-02`) and their reconciliation.
- `docs/archive/`: superseded documents in dated sets, each listed with the document that replaced it.
  The v6/v7/v8/v9 labels, the 85–95% readiness figures, PostgreSQL/Celery/Neo4j, service ports
  8100–8103 and gateway port 3000 that appear there describe earlier platforms, not this tree.

## Local dev quick reference

```bash
pnpm setup:demo       # verified native path: runtimes, .venv, frozen install, emulator, migrations (docs/build/local-setup.md)
pnpm dev:demo         # brain :8000, gateway :3001, consumer :3000 (BRANDME_MODE=demo)
docker compose up -d  # default profile: Spanner emulator 9010/9020, Firestore 8080, spanner-migrate, brain :8000,
                      # policy :8001, gateway :3001, consumer-domains (:8010 in the gateway's network namespace), consumer :3000
# --profile legacy adds orchestrator :8002, knowledge :8003, compliance :8004, identity :8005, governance :8006, cube :8007
#   (stubs; their preflight refuses sandbox/production). console :3002 is only in docker-compose.dev.yml; brandme-chain is in neither.
# brandme_core/mcp/ is an executor library with no server transport (no mcp-server, midnight-stub or cardano-stub service exists).

pnpm check            # everything CI's foundation gate runs, incl. the full pytest suite
python -m pytest tests -q --timeout=300 -ra
# Known-broken tests are quarantined (tests/conftest.py QUARANTINE), never reported as passing.
```

Make targets: `make install`, `make lint`, `make format`, `make type-check`.

## When updating this file

- Verify by reading code, not by reading other docs.
- Cite file:line for every claim.
- If you flip a service from STUB → REAL, also remove its row from "What's
  stub". Don't let the table drift.
