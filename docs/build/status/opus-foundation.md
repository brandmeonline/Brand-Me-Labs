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
