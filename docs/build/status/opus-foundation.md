# Lane brief: opus-foundation

**Bench:** Opus 5.5 (Claude Code) · **Branch:** `bench/opus-foundation-20261005`
**Base:** `docs/brandme-full-experience-2026-10-05` · **Spec:** `docs/design/brandme/` + `contracts/`
**Work packages:** W00 (audit, executable baseline, honest modes) + W01 contracts/workspace/tokens + W02 (persistence, auth, privacy boundaries)
**Position in merge order:** FIRST. All other lanes wait on this lane's merge.

## What you are building
The foundation every other lane stands on: an honest executable baseline, the shared contract packages, the design-token package, the persistence framework, auth/session middleware, the event outbox/inbox framework, mode configuration, and the required developer commands. Read `docs/design/brandme/06-delivery-verification.md` §1–§2 and the root `CLAUDE.md` before touching code.

## You own exclusively (no other lane may touch these)
- `docs/build/` — create `implementation-status.md`, `compatibility-lock.md`, `deviations.md` (these two files are parent/Lane-1-only; other lanes propose deviations via their own status files)
- `packages/` — all three: `contracts` (OpenAPI 3.1 + generated TS/Python types from `contracts/domain.schema.json` + ch.03), `design-system` (tokens generated from `contracts/design-tokens.json`), `provider-contracts` (interfaces only; Lane 3 extends after you merge)
- `pnpm-workspace.yaml`, root `package.json`
- `docker-compose*.yml`, `Makefile`, `.github/workflows/`
- `brandme-data/spanner/migrations/` — migration ledger + runner + `V001_identity.sql` ONLY (members/identity/sessions/consent). Reserve numbers V002–V009 for other lanes (see below); do not create them.
- `brandme_core/domains/` — framework files only: `__init__.py`, `base.py`, `events.py`, plus per-domain reservation READMEs for `persona, wardrobe, social, rewards, commerce, providers, rights, privacy, media` (READMEs only, no logic)
- `brandme_core/events/` (event envelope framework), `brandme_core/config.py` (mode definitions: `BRANDME_MODE` demo/development/sandbox/production)
- `brandme-gateway/src/routes/v1/` — `index.ts` mount file + `me.ts` ONLY. Other lanes ship unmounted router files; you (or the parent at integration) mount them.
- `brandme-gateway/src/middleware/`, `brandme-gateway/src/types/`
- `.env.example`, `tests/conftest.py` + `tests/fixtures/` (framework only), `scripts/` (implement the required pnpm commands from ch.06 §3 as scaffolds)

## Read-only for you
`docs/design/brandme/**`, `contracts/**` (the spec — never edit; deviations go in `docs/build/deviations.md`).

## Migration number reservations (do not use another lane's number)
V002 persona · V003 wardrobe · V004 social · V005 rewards · V006 providers · V007 commerce · V008 rights · V009 privacy

## Exit evidence (from ch.06 §2, W00–W02)
- Clean install/boot from a fresh checkout, documented; port map applied (consumer 3000, gateway 3001, console 3002, brain 8000, policy 8001, orchestrator 8002, cube 8007 — update compose/proxy/env together, no service infers another's port)
- Actual baseline test report (run existing tests, record failures honestly — old passing claims are not evidence)
- Mode-guard negative test: production boot fails closed when a required real adapter is missing; demo adapters carry visible simulation labels; all trust-path fixtures enumerated (fake chain hashes, fake proofs, constant ESG, fake commerce IDs, default reprint eligibility, auth shortcuts) and confined to demo adapters
- Migration runs from empty schema to V001; typed API clients generated from `domain.schema.json`; `compatibility-lock.md` pinned (exact Node/pnpm/Python/Next/React/TS/Three/R3F/Motion/model-viewer/MediaPipe/Midnight versions + check date); lockfiles committed — never "latest"

## Status protocol
- Record status ONLY in this file (`docs/build/status/opus-foundation.md`). Never edit `docs/build/implementation-status.md`.
- Other lanes will request design tokens and dependency pins via their status files — collect and publish them at integration.
- Note: the acceptance catalog has zero requirements staged at W01/W02 — define your exit evidence from ch.06 §2 prose and propose catalog additions in this file.

## Global rules (all lanes)
Never edit another lane's owned files. Never edit `docs/design/brandme/**` or `contracts/**`. Fixtures stay in per-lane `tests/fixtures/<domain>/`. No `latest` tags — pin everything. Demo adapters carry visible simulation labels. Production boot fails closed.

---

# Status log (opus-foundation lane)

**Last updated:** 2026-10-05 · **Working branch:** `claude/opus-foundation-w00-2hgiw5` (the session harness designates it; `bench/opus-foundation-20261005` points at the same base `e4f1342`) · **PR:** brandmeonline/Brand-Me-Labs#33 (draft, base `bench/opus-foundation-20261005`)
**Baseline reconciliation:** HEAD at start = spec baseline `0f5f58a` + docs-only `4511236`, `e4f1342`. No application code drifted from the audited baseline.

## Exit evidence (brief §"Exit evidence")

| Brief item | State | Evidence |
|---|---|---|
| Clean install/boot from a fresh checkout, documented; port map applied | **Done** for HTTP client → gateway → brain → Spanner. The consumer UI → gateway link is not done (consumer lane) | `docs/build/local-setup.md`, `docs/build/evidence/w00/fresh-checkout.md` (clone of `63df43f`, cold emulator: setup/smoke/check/build exit 0) |
| Actual baseline test report | **Done** | `docs/build/evidence/w00/baseline-test-report.md` (3 of 18 root tests pass at baseline; findings F1–F16 classified) |
| Mode-guard negative test (production fails closed); simulation labels; trust-path fixtures enumerated and confined | **Done** for enumeration, labels and refusal. **Not done:** physically moving fixtures into demo adapters. Each fabricating service is registered as a simulated adapter and refused in sandbox/production. Rewriting the fakes belongs to the owning lanes | `brandme_core/config.py`, `tests/foundation/test_mode_guard.py` (47), `brandme-gateway/src/middleware/mode.test.ts` (7), `docs/build/evidence/w00/trust-path-fixtures.md` |
| Migration empty → V001 | **Done**, plus baseline (legacy schema) → V001, rerun no-op, checksum drift / out-of-order / partial-failure refusal | `brandme-data/spanner/migrations/`, `tests/foundation/test_migrations.py` |
| Typed API clients generated from `domain.schema.json` | **Done**: OpenAPI 3.1 (73 operations, ch.03 inventory), TS types, openapi-fetch client, pydantic models, drift check in `pnpm check` and CI | `packages/contracts`, `tests/foundation/test_contract_models.py` |
| `compatibility-lock.md` pinned; lockfiles committed; never "latest" | **Done** | `docs/build/compatibility-lock.md`, `pnpm-lock.yaml` (pnpm 10.34.6), `scripts/python/requirements.lock` (hashed), `.nvmrc` |

## Acceptance catalog (W00 IDs; results in `docs/build/evidence/results.json`)

| ID | Result | Why |
|---|---|---|
| BM-BASE-001 | **blocked** | Gateway/domain/persistence boot verified from a fresh clone; the consumer app has no gateway client yet (consumer-ui lane) |
| BM-BASE-002 | **passed** | Strict modes refuse every simulated trust-path service, stub flags, the dev identity provider, shared-secret JWT and symmetric algorithms |
| BM-BASE-003 | **passed** | Baseline report + this status file |
| BM-BASE-004 | **passed** | All four apps + packages build from the frozen lockfile on Node 24.21.0 / pnpm 10.34.6. Frontend is still Next 14.0.4 (target 16.3.8 is the frontend lane's) |
| BM-BASE-005 | **failed** | `POST /scan` returns 500 without NATS; `/scan/:id` is a placeholder; `/shop`/`/stash` are not redirected (targets do not exist) |

All other 145 IDs are `not_run` (`pnpm evidence:report`).

## Stage W00 — done (except items above)
- `BRANDME_MODE` (demo/development/sandbox/production; required, no default) + `python -m brandme_core.config preflight --service X`. Compose runs it before every Python service.
- `ENABLE_STUB_MODE` default flipped to false. Stub flags are refused in strict modes.
- Compose rewritten (the old file did not parse) with the port map: consumer 3000, gateway 3001, console 3002, brain 8000, policy 8001, orchestrator 8002, knowledge 8003, compliance 8004, identity 8005, governance 8006, cube 8007. It is config-validated only; the container boot was not executed.

## Stage W01 — done for foundation scope
- Workspace: `brandme-gateway`, `brandme-chain`, `brandme-console`, `brandme-frontend`, `packages/*`. Pins Node 24.21.0, pnpm 10.34.6 (`engineStrict`), TS 5.9.3.
- `packages/contracts`, `packages/design-system` (tokens + dark + reduced motion; AA contrast for 18 pairs), `packages/provider-contracts` (interfaces + `assertAdapterAllowed`).
- **Not done here (D-004):** UI primitives, app shell, component gallery, fonts; W01 viewport/keyboard/320 px exit evidence. Owner: consumer-ui lane.

## Stage W02 — framework done; some ch.06 W02 items open
Done:
- Migration ledger/runner + V001 (identity + platform tables, D-001).
- `brandme_core.events`: envelope + closed-payload registry + forbidden-key filter, outbox writer, lease dispatcher with backoff/dead-letter, inbox dedupe.
- `brandme_core.domains`: Principal, deny-by-default `authorize` (block override, expiry, revocation; 404 for hidden), If-Match, canonical digest, `run_command`, `run_idempotent_command`, data-category registry. Reserved READMEs for persona … media.
- Emulator tests: a retried transaction commits exactly one outbox event; failed commands write nothing; at-least-once dispatch is applied once via the inbox; idempotent replay; key reuse returns 409; 5 concurrent duplicates apply once.
- Gateway identity boundary: server-side sessions (hashed secret + CSRF in Spanner), JWKS-verified OIDC bearer (iss/aud/asymmetric algs) mapped to members, `/api/v1` with problem+json and request-id/environment headers, `GET/PATCH /me` (If-Match, contract-validated), `/system/health`, labelled dev session (404 in strict modes). Cross-mode sessions are rejected. 10 emulator tests: restart + second-session persistence, CSRF/origin, 409/428, member isolation, token rejection cases.
- Commands: `pnpm setup:demo | dev:demo | dev | smoke | check | migrate | evidence:report`. `test:journeys`, `test:providers`, `test:midnight:*` and `assets:validate` exit 2 ("not implemented yet").
- CI: new `.github/workflows/foundation.yml` (emulator service; check + smoke + builds + production refusal). Existing workflows were moved to `.nvmrc`/`packageManager`.

Open (proposed for parent / later lanes):
- Firestore projection framework + security rules + revocation test (ch.06 W02 "projection revocation works"): **not started**.
- Media upload quarantine and provider connection records: **not started** (media/providers lanes per reservations).
- Export/deletion jobs: only the data-category registry exists. V009 privacy owns the job tables.
- Redacted-log middleware is partial: the gateway no longer logs raw user IDs in the new paths. Legacy `routes/scan.ts:67-72` still does.
- Backfill of the two legacy persona columns: persona lane (V002).
- Browser OIDC code flow (D-005): gated on the OIDC tenant.

## Cross-lane edits (flag for review; details in `docs/build/deviations.md` D-002)
`brandme_core/spanner/pool.py` (additive `database` property; fixes 49 call sites), `brandme-gateway/src/index.ts`, `src/config/index.ts`, `package.json`, `vitest.config.ts`.

## Proposed acceptance-catalog additions (W01/W02 have zero IDs)
- BM-FND-001 (W01, integration): `pnpm contracts:check` fails on any drift between `domain.schema.json`/`design-tokens.json` and generated artifacts. **Passing** (`pnpm check`).
- BM-FND-002 (W02, integration): a migration runs from empty and from the baseline schema; an edited applied migration is refused. **Passing**.
- BM-FND-003 (W02, integration): a retried command transaction commits exactly one outbox event; redelivery applies once via the inbox. **Passing**.
- BM-FND-004 (W02, security): `/api/v1` mutations without a session CSRF token or with a foreign Origin fail with 403; a stale If-Match gets 409. **Passing**.
- BM-FND-005 (W02, integration): a profile saved in one session survives a gateway+brain restart and is visible from a second session. **Passing** (gateway test + smoke).
- BM-FND-006 (W02, security): revoking a share removes shared Firestore projections. **Not run** (projection framework not built).

## Requests to other lanes
- **consumer-ui:** add a gateway client using `@brandme/contracts` (`createBrandmeClient`), import `@brandme/design-system/tokens.css`, implement the `/shop`→`/discover` and `/stash`→`/closet` redirects, and upgrade Next/React to the compatibility-lock targets.
- **All Python lanes:** wrap commands in `run_command`/`run_idempotent_command`; register events in `brandme_core.domains.events`; remove your service's `LEGACY_SIMULATED_ADAPTERS` entry only with replacement evidence.
- **Owner of `routes/scan.ts`:** return 503 problem+json when NATS is unconfigured; persist scan operations.
- **Parent:** apply the `.gitignore` negations in D-003.

## Resume instructions
1. `pnpm setup:demo && pnpm check && pnpm smoke` (needs Docker or a local Spanner emulator).
2. Read this file, `docs/build/deviations.md` and `docs/build/compatibility-lock.md`.
3. Next foundation items, if the parent keeps them in this lane: the Firestore projection framework + rules + revocation test (BM-FND-006), the redacted-log middleware for legacy routes, and export/deletion job scaffolding on top of `data_categories()`.
