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

---

# Lane status log

Working branch: `claude/midnight-rights-lifecycle-yhfyyu` (session-designated; same base commit `ede63f6` as `bench/opus-midnight-rights-20261005`).

## Stage 0 — Toolchain verification (2026-10-05)

### Midnight tuple — re-verified against the official support matrix

Source: <https://docs.midnight.network/relnotes/support-matrix>, page "Last Updated: October 5, 2026", fetched 2026-10-05. Matches ch.04's table exactly; no drift.

| Component | Matrix (Preprod) | Pinned here | How verified |
|---|---|---|---|
| Ledger | 8.1.2 | `@midnight-ntwrk/ledger-v8@8.1.2` | npm registry; compiler reports generated code targets `ledger-8.0.2` (compatible 8.x line) |
| Compact devtools | 0.5.1 | not installed — see note | installer fetches from GitHub; compiler pinned directly instead |
| Compact compiler/toolchain | 0.31.1 | `compactc 0.31.1` (language version 0.23.0) | GitHub release asset `compactc_v0.31.1_x86_64-unknown-linux-musl.zip`, sha256 `e291b4bab4d4e857707008f8b1c25c2b8e0c843f6c737d0ee6c0d9ac69a6bbfb` |
| Compact runtime | 0.16.0 | `@midnight-ntwrk/compact-runtime@0.16.0` | `compactc --runtime-version` → 0.16.0; generated code calls `checkRuntimeVersion('0.16.0')` |
| Compact JS | 2.5.1 | `@midnight-ntwrk/compact-js@2.5.1` | npm |
| Platform JS | 2.2.4 | `@midnight-ntwrk/platform-js@2.2.4` | npm |
| On-chain runtime | 3.0.0 | `@midnight-ntwrk/onchain-runtime-v3@3.0.0` | npm |
| Wallet SDK | 1.2.0 | `@midnight-ntwrk/wallet-sdk@1.2.0` | npm. **Note:** `@midnight-ntwrk/testkit-js@4.1.1` itself depends on `wallet-sdk@1.1.0`; the test harness therefore carries 1.1.0 transitively. Recorded, not hidden. |
| Midnight.js / testkit-js | 4.1.1 / 4.1.1 | all `@midnight-ntwrk/midnight-js-*@4.1.1`, `testkit-js@4.1.1` | npm |
| DApp connector API | 4.0.1 | `@midnight-ntwrk/dapp-connector-api@4.0.1` | npm |
| Proof server | 8.1.0 | `midnightntwrk/proof-server:8.1.0` | Docker Hub tag exists. `8.1.3` was pushed 2026-10-02 but is **not** in the matrix; not used. |
| Node | Preprod 1.0.400 | n/a (remote) | — |
| Indexer | Preprod 4.3.302 | n/a (remote) | — |

Newer packages exist (`compact-runtime 0.20.0`, `midnight-js 5.0.0-rc.*`, `proof-server 9.0.0-rc.*`). They are deliberately not used: the tuple is pinned as a set.

### Environment reachability (this build container)

| Resource | Result |
|---|---|
| npm `@midnight-ntwrk/*` | reachable |
| Docker Hub `midnightntwrk/*` | reachable (docker daemon must be started manually in this container) |
| GitHub release asset download | reachable; GitHub API/HTML pages return 403 (egress policy) — `fetch-compactc` (API-based) cannot run here, so the compiler is fetched by direct asset URL + sha256 check |
| `https://rpc.preprod.midnight.network`, `https://indexer.preprod.midnight.network/api/v4/graphql` | reachable (TLS OK) |
| Preprod faucet | reachable; funding requires a human-facing faucet flow — see blockers when reached |

### Next
Write and compile the Compact rights contract; artifact manifest with hashes.
