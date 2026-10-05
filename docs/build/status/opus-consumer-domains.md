# Lane brief: opus-consumer-domains

**Bench:** Opus 5.5 (Claude Code) · **Branch:** `bench/opus-consumer-domains-20261005`
**Base:** `docs/brandme-full-experience-2026-10-05` · **Spec:** `docs/design/brandme/` + `contracts/`
**Work packages:** W03-backend (first 90 seconds + Looking Glass), W04-backend (wardrobe/outfits), W05-backend (social/loyalty), W08-server (try-on jobs/consent/deletion)
**Position in merge order:** After `opus-foundation` merges. Independent of the other Opus lanes (disjoint files).

## What you are building
The consumer domain backends — the hardest reasoning in the build: persona precedence/suppression, the deterministic recommender, the idempotent reward ledger, server-timed five-minute decisions, wardrobe/outfit domain logic, and try-on server jobs. Read chapters 01, 03, 06 and the root `CLAUDE.md` first.

## You own exclusively (no other lane may touch these)
- `brandme_core/domains/{persona,wardrobe,social,rewards,media}/` — full domain logic
- `brandme-data/spanner/migrations/` — `V002_persona.sql`, `V003_wardrobe.sql`, `V004_social.sql`, `V005_rewards.sql` ONLY
- `brandme-gateway/src/routes/v1/{persona,wardrobe,outfits,social,decisions,rewards,media,tryon}.ts` — ship as unmounted router files; Lane 1 / parent mounts them at integration. Never touch `index.ts`, `middleware/`, or `types/`.
- `tests/test_{persona,wardrobe,social,rewards,media}*.py`, `tests/fixtures/{persona,wardrobe,social,rewards}/`
- `brandme-console/app/(ops)/{moderation,rewards-disputes}/**` — Lane 5 builds the console shell; you own these subtrees. If the shell imposes a layout contract, it will be published in `docs/build/status/astra-consumer-ui.md` — check it before building pages.

## Read-only for you
`packages/contracts` (generated clients), `packages/design-system`, `brandme_core/events/*`, gateway `middleware/` + `types/`, `docs/build/compatibility-lock.md` (submit your dependency pins via this status file instead of editing it).

## Forbidden
`packages/*` (any edits), `docs/design/brandme/**`, `contracts/**`, any `brandme-frontend/` files, other lanes' domains/routes/migrations.

## Exit evidence (from ch.06 §2, W03–W05, W08-server)
- Persona: 12 axes with declared/inferred/effective separation, locks, suppression, snapshots, reset; declared locked preference wins over inference; two devices editing one persona version → one accepted revision, other sees mergeable conflict; deleting evidence changes recommendations and prevents immediate reuse
- Deterministic recommender works with NO AI key; recommendations carry explanations reflecting actual scoring
- Reward ledger: 10 concurrent duplicate reward events → exactly one ledger cause and correct balance; two redemptions racing the same points → no negative balance; reversals, caps, idempotency keys all tested
- Decisions: server-computed `closes_at`; responses accepted only when server transaction time is strictly before deadline; one response per respondent/decision; zero-reply and expired states handled
- Wardrobe: product vs wardrobe entry vs attested instance separated; duplicate resolution; placement quaternions finite/normalized, positions asset-bounded
- Try-on server: consent/job/deletion interfaces; unsaved media expiry demonstrable (AR/camera UI is Lane 6 — you own the server side only)
- Migration V002→V005 run from empty; transaction retry does not duplicate outbox events

## Status protocol
Record status ONLY in this file. Propose deviations here (parent/Lane 1 compiles into `docs/build/deviations.md`). Publish your dependency pins here.

## Cross-lane contracts you must honor
- W10 deletion: expose a `deletion.py`/`privacy.py` registration in each domain package for Lane 4's export/deletion job framework (Lane 4 publishes the interface; you implement it).
- `brandme-cube/` belongs to Lane 4 — consume passport reads via its versioned, policy-filtered read API only.

## Global rules (all lanes)
Never edit another lane's owned files. Never edit `docs/design/brandme/**` or `contracts/**`. Fixtures stay in per-lane `tests/fixtures/<domain>/`. No `latest` tags — pin everything. Demo adapters carry visible simulation labels.
