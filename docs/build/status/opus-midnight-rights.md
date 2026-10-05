# Lane brief: opus-midnight-rights

**Bench:** Opus 5.5 (Claude Code) · **Branch:** `bench/opus-midnight-rights-20261005`
**Base:** `docs/brandme-full-experience-2026-10-05` · **Spec:** `docs/design/brandme/` + `contracts/`
**Work packages:** W09 (real Midnight rights + lifecycle), W10 (My Data, moderation, operational recovery)
**Position in merge order:** After `opus-foundation` merges. Independent of the other Opus lanes (disjoint files).

## What you are building
The trust core: real Midnight contract integration replacing the stub client, claim-level passports, transferable entitlements, licensed reprint workflows, private-state backup/recovery, and the cross-domain export/deletion framework. Read chapters 04, 03, 06 and the root `CLAUDE.md` first. Resolve the current supported Midnight tuple and Mainnet provider configuration from official docs at build time — ch.04's table is dated 2026-10-05; re-verify and record actual pinned versions here.

## You own exclusively (no other lane may touch these)
- `brandme-chain/` — ENTIRE directory: real Midnight adapter (replacing `midnight-client.ts` stub), `contracts/` Compact sources, compiled artifacts + artifact manifest, `test:midnight:local`
- `brandme_core/domains/{rights,privacy}/` — full domain logic
- `brandme_core/zk/` — extend as needed
- `brandme-cube/` — migrate passport facet reads to policy-filtered access (migrate, don't fork; Lane 2 consumes via your versioned read API only)
- `brandme-data/spanner/migrations/` — `V008_rights.sql`, `V009_privacy.sql` ONLY
- `brandme-gateway/src/routes/v1/{rights,chain,ownership,assets,privacy}.ts` — unmounted router files; never touch `index.ts`, `middleware/`, `types/`
- `tests/contracts/` — Compact constraint/property/adversarial tests; `tests/test_{rights,privacy}*.py`
- `brandme-console/app/(ops)/{chain,rights,manufacturing,privacy}/**` — check Lane 5's shell layout contract in `docs/build/status/astra-consumer-ui.md` before building pages

## Read-only for you
`packages/contracts` (generated clients), gateway shared files, `docs/build/*`.

## Forbidden
`packages/*` (any edits), `docs/design/brandme/**`, `contracts/**`, any `brandme-frontend/` files, other lanes' domains/routes/migrations.

## Cardano rule
Optional Cardano anchoring comes LAST through a verified adapter and must NEVER delay the primary Midnight path (ch.04 §8).

## Exit evidence (from ch.06 §2, W09–W10)
- `pnpm test:midnight:local` green: Compact compile + constraint/property tests + adversarial state transitions; compiler/runtime tuple + artifact hashes recorded
- Preprod observed transactions: issue → prove → transfer → consume; replay/concurrency rejected; replay of a transfer proof on a different network rejected BEFORE state mutation
- Invalid proof leaves app state unchanged; wallet account-switch during proving aborts/rebinds safely with isolated private state
- Private-state backup → clean-profile restore works; wrong-network protection active; managed-prover usage clearly disclosed where applicable
- NO production stub fallback anywhere in the trust path; no Mainnet writes
- Reprint: quota consumed exactly once under duplicate manufacturer callbacks; one child issuance per completion; license/manufacturer authorization enforced by the real contract
- My Data: export produces truthful receipt; deletion propagates — old projections/caches no longer leak; tombstones reapply after restore from older backup; account deletion racing a queued inference job cannot recreate deleted profile data
- Deletion framework: publish the `deletion.py`/`privacy.py` registration interface that Lanes 2–3 implement per domain; verify at integration

## Status protocol
Record status ONLY in this file. Propose deviations here. Publish dependency pins here (Midnight tuple, Compact compiler, provider versions).

## Global rules (all lanes)
Never edit another lane's owned files. Never edit `docs/design/brandme/**` or `contracts/**`. Fixtures stay in per-lane `tests/fixtures/<domain>/`. No `latest` tags — pin everything. Private information stays out of public chain state, logs, and model prompts.
