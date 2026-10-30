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


## Stage 1 — Compact contract + local constraint/property tests (2026-10-05)

**Done**
- `brandme-chain/contracts/src/brandme_rights.compact`: issuer registry, transferable entitlements, licensed reproduction. 15 circuits. Design, field placement, linkability and prover-exposure statement are in `brandme-chain/contracts/DESIGN.md`.
- Compiled with pinned `compactc 0.31.1`. Proving keys are **deterministic** (two independent full compiles produced byte-identical output, including all `.prover` files). Committed: TS binding, zkir, verifier keys, `contracts/artifact-manifest.json` with sha256 for every artifact, prover keys included. Prover keys are not committed (2.8–5.2 MB each); `pnpm compact:compile` regenerates them and `pnpm compact:verify` checks them against the manifest.
- `pnpm test:midnight:local` (`brandme-chain/scripts/test-midnight-local.sh`) fetches compactc by sha256, compiles, fails if the manifest drifts, verifies artifacts, then runs the suites.
- Suites in `tests/contracts/` run the **real compiled circuits** through compact-runtime 0.16.0 / onchain-runtime-v3 3.0.0 in a test-only simulator (`brandme-chain/tests/support/simulator.ts`):
  - `constraints.test.ts`: 28 cases covering every precondition in ch.04 §4. Each rejection asserts that public and private state are byte-identical afterwards.
  - `property.test.ts`: 150 random interleavings (≤60 honest and adversarial commands) with invariant checks after every step, plus 200 duplicate-callback storms showing reprint quota is consumed exactly once and there is one child per attested unit. A non-vacuity guard fails the run if any stateful circuit never succeeds or never rejects.
- Result: **30/30 passing** (≈70 s).

**Not yet proven:** these tests execute circuit logic without generating proofs. Proof generation and verification against the pinned proof server and a live ledger come in Stage 3 (local network, then Preprod).

**Shared-file touches (heads-up for opus-foundation):**
- Root `package.json`: added `pnpm.overrides` pinning `@midnight-ntwrk/{ledger-v8 8.1.2, onchain-runtime-v3 3.0.0, compact-runtime 0.16.0, compact-js 2.5.1, platform-js 2.2.4}`. Without these, `midnight-js-protocol@4.1.1` (exact `ledger-v8 8.1.0`) and `compact-js` (`^8.0.3`) resolve to two ledger WASM instances. The matrix says ledger 8.1.2, so the override enforces that.
- Root `pnpm-lock.yaml` regenerated by `pnpm install`.
- `brandme-chain` is now ESM (`"type": "module"`, NodeNext) and needs Node ≥ 22. `.github/workflows/chain-tests.yml` still pins Node 18 and `MIDNIGHT_FALLBACK_MODE`. That workflow sits outside my directories, so I'm proposing the change here rather than making it: Node 22 + `pnpm test:midnight:local` (SKIP_ZK=1 for PR CI).


## Stage 2 — Real adapter replaces the stub (2026-10-05)

**Removed:**
- `src/services/midnight-client.ts`: the stub with `encrypted_` strings, invented hashes, a constant proof and a hardcoded confirmed block.
- `blockchain.ts`: simulated Midnight/Cardano fallbacks and a "cross-chain root" made by hashing two tx ids.
- `/tx/verify-root`: returned a hardcoded `is_consistent: true`.
- The test suites that asserted those fakes.

`/tx/anchor-scan` and `/tx/verify-root` now return **410 Gone**. `MIDNIGHT_FALLBACK_MODE=true` / `CARDANO_FALLBACK_MODE=true` now abort startup.

**Added (`brandme-chain/src/midnight/`):**
- `adapter.ts` wires the official provider boundaries:
  - indexer public-data provider
  - `NodeZkConfigProvider` over manifest-verified artifacts (startup refuses mismatched proving material)
  - `httpClientProofProvider` restricted to a **loopback** proof server. Wallet proving is supported. Managed/remote proving needs a consent record and is never chosen automatically.
  - level private-state provider
  - the connected wallet
- Operation execution:
  - an operation is persisted before any wallet interaction
  - network, contract, digest and expiry checks run before proving
  - the wallet/session is re-checked at `balanceTx`, the last point before submission; an account switch or lock aborts with nothing submitted
  - `Submitted` only after a real tx id; observation via the indexer
  - `Finalized` only when the node's GRANDPA finalized head (`chain_getFinalizedHead`) has reached the block and `chain_getBlockHash(height)` matches
  - a timeout after submission moves to `Reconciling` and never resubmits
- `operations.ts`: the ch.04 §5 state machine with guarded transitions, a request digest, idempotency keys, compare-and-set updates, and conflict blocking per subject.
- `private-state.ts`:
  - account-scoped, encrypted at rest (official level provider; password complexity enforced)
  - lock/unlock/account-changed
  - backup envelope bound to network + contract + account; restore refuses a mismatch before writing
- `network.ts`: endpoints from the official network page; Mainnet via Blockfrost with the token kept server-side; `assertWritable('mainnet')` always throws (no override exists).
- `capability.ts` + `GET /midnight/capability` report `available | read_only | unavailable` with reasons, the network badge, the tuple, artifact verification and witness exposure per proving mode.

**Tests (`brandme-chain/tests/midnight/`, 25 cases):**
- adapter: happy path to Finalized, cross-network replay rejected with the simulator state byte-identical, tampered digest, wrong wallet network, account switch during proving, invalid witness, chain FailEntirely, timeout → Reconciling, conflicts, idempotency, Mainnet refusal, non-loopback prover refusal
- private state: encrypted at rest, account isolation, lock, backup → clean-profile restore → **restored secret proves control on the real circuit**, wrong network/contract/account/password refused
- trust path: static guards against test-code imports and stub/simulate/fallback tokens in `src/midnight`

**`pnpm test:midnight:local`: 55/55 passing**, including a fresh compile and an unchanged manifest (2m31s).

**Deviation (proposed):** a Spanner-backed `OperationStore` is not written yet. Until it exists, `capability` reports writes as disabled outside development (`read_only`), so the in-memory store is never used for sandbox or production writes.

## Stage 3 — W10 My Data framework, rights domain, V008/V009 (2026-10-05)

**Migrations** (`brandme-data/spanner/migrations/`), GoogleSQL, applied to Spanner emulator 1.5.45:
- `V008_rights.sql`: ChainOperations, RightsIssuers, RightsEntitlements, TransferIntents, LicenseGrants, ManufacturerCapabilities, ReprintJobs, ManufacturerCallbacks (inbox), PassportClaims, with query-specific indexes.
- `V009_privacy.sql`: ExportJobs, DeletionJobs, DeletionSteps (interleaved), DeletionTombstones, ProcessingFreezes, RestoreRuns.
- The emulator caught one bug in my own DDL: `DeletionJobs.state` was too narrow for `completed_with_exceptions`. Fixed.
- V008/V009 assume the opus-foundation lane's migration ledger and V001–V007. No foreign keys to foundation tables, so they apply standalone.

**Published registration interface — for consumer-domains and commerce-agents lanes:**
`brandme_core/domains/privacy/deletion.py`. Implement `DomainPrivacyHandler` (`categories`, `export`, `delete(txn)`, `purge_derived`, `reapply_tombstone`) and call `register_domain(handler)`. Every writer of personal or derived data must call `assert_processing_allowed(txn, subject_ref, category, basis_time)` inside its own read/write transaction. The registry rejects:
- undeclared categories
- wrong domain prefixes
- `RETAIN_LEGAL` without a stated basis

A worked example implementation lives in `tests/fixtures/privacy/persona_fixture.py` (test-only stand-in; the real persona domain belongs to another lane).

**Orchestrator** (`brandme_core/domains/privacy/privacy.py`, `MyDataService`):
- Inventory.
- Export: re-auth required, consistent snapshot, versioned JSON, sha256 receipt. Refuses secret-shaped keys (seed/mnemonic/private_key/…). Points to the separate Midnight private-state backup.
- Deletion:
  - the job and the processing freeze commit in one transaction
  - per-category steps run inside a txn, plus a tombstone
  - projection/cache purge happens after commit
  - the receipt is truthful: `deleted` / `not_erasable` (public ledger) / `retained` with its basis / `exception`, plus the backup-expiry date
- Restore: `reapply_tombstones_after_restore` plus `assert_serving`, which refuses to serve while a restore is unreconciled.

**Rights domain** (`brandme_core/domains/rights/`):
- `projection.py` projects only Finalized evidence, is idempotent per tx, monotonic in epoch, never reactivates a revoked entitlement, and drops the old member link when control moves.
- `reprint.py`:
  - ch.04 §7 state machine
  - `rights_consumed` only from a Finalized chain operation
  - manufacturer callbacks are exactly-once through a (manufacturer, callback_id) inbox written in the same txn as the effect
  - units advance in order and never past the quantity
  - no automatic quota restore
- `passport.py`: versioned claim-level read API (`brandme.passport.claims/v1`), one statement per claim with assurance, source, environment, network/test-network flag, expiry/revocation, "what this means", and server-side visibility filtering.
- `privacy_handler.py` registers the rights categories. Control links are erased, transfers deleted, reprint jobs retained with the member reference removed, chain commitments reported as not erasable.

**Tests** (`tests/test_privacy.py`, `tests/test_rights.py`): **16/16 passing on the Spanner emulator**:
- export receipt and secret-content guard
- deletion propagates to projections/caches (old reads no longer leak)
- truthful receipt with exceptions
- tombstones reapply after restore from an older backup, and serving is blocked until they are
- account deletion vs. a queued inference job, both commit orders refused/removed
- stale-basis category jobs blocked while fresh ones are allowed
- duplicate manufacturer callbacks applied exactly once
- finalized-only projection
- passport visibility filtering

**Stated limit:** the emulator allows one read/write transaction at a time, so a truly overlapping deletion/inference interleaving can't be reproduced there. Correctness in that case rests on Spanner's serializable isolation: the guard reads the freeze row inside the writer's transaction. Re-run on an authorized disposable Cloud Spanner database before production.

**Run:** start the emulator (`docker run -p 9010:9010 gcr.io/cloud-spanner-emulator/emulator:1.5.45`), then `pytest tests/test_privacy.py tests/test_rights.py` (google-cloud-spanner 3.40.1 as pinned in `brandme_core/requirements.txt`).

## Stage 4 — Live network evidence, Cardano boundary, cube filtering (2026-10-05)

### Local Midnight network — real proofs, real node, real finality

`pnpm test:midnight:network` against `scripts/local-network.sh`:
- node `midnight-node:1.0.300` (`CFG_PRESET=dev`)
- indexer `indexer-standalone:4.3.5`
- `proof-server:8.1.0`

All images are pinned by digest in `brandme-chain/tests/network/compose.yml`. **7/7 passing, run twice** (8m21s and 9m55s). Evidence: `brandme-chain/evidence/undeployed-2026-10-05T18-51-38-369Z.json`, contract `8332bb9a…2280`, source sha256 `919577bf…fa49` (= manifest).

| Exit criterion | Observed |
|---|---|
| Deploy with verified artifacts | Deploy, plus 7 verifier-key insertions, all `SucceedEntirely`; `findDeployedContract` verified all 15 on-chain keys against the manifest |
| issue → prove → transfer → consume | registerIssuer, registerManufacturer, issueEntitlement, proveControl, offerTransfer ×2, acceptTransfer, grantReprintAllowance, consumeReprintAllowance, attestManufacture: each **Finalized** (≈22–24 s each, mostly proving); `finalizedHeadHeight` ≥ block height via `chain_getFinalizedHead` |
| Replay rejected before state mutation | Same (challenge, audience): local execution fails `challenge already used`, nothing submitted. Identical tx bytes resubmitted: node rejects `1013: Transaction Already Imported`. `usedChallenges` size unchanged |
| Concurrent acceptance | Two offers at one epoch, both accepts submitted concurrently: exactly one Finalized, the other rejected at submission (SDK surfaced only a generic "Transaction submission error"; no node RPC reason captured). Epoch advanced exactly once |
| Cross-network replay | Persisted op for another network: `WrongNetworkError` before proving, nothing submitted, op unchanged |
| Invalid proof leaves state unchanged | Wrong holder secret fails `not controller` during local circuit execution. **No proof can be produced**, nothing is submitted, and the entitlement is byte-identical on chain afterwards. A tampered proof was not tested on the node |
| Account switch during proving | Proved, then account changed, then the `balanceTx` guard aborted (`session_changed`); zero transactions submitted |
| Reprint exactly once | Duplicate consume for the same job: `job already consumed`. Duplicate attest unit 0: `units must be attested in order`. Over-quota rejected; remaining quota exactly 1; one child entitlement only |
| Private-state backup/restore | Export, then a clean in-memory profile restores it, then `proveControl` with the restored secret is **Finalized on chain** |
| Old owner loses control | Old owner's proveControl fails `not controller`; new owner's is Finalized |

**Finding (blocker resolved):** a 15-key deploy is rejected by the node (`1010: Transaction would exhaust the block limits`; 8 keys = 21 KB accepted). The deploy is now two-phase. The maintenance authority this creates is a governance power, recorded in `contracts/DESIGN.md` as a production gate.

### Preprod

- **Read path verified (2026-10-05):** `rpc.preprod.midnight.network` reports `system_version` `1.0.400-c338b9ac` (matches the matrix); `chain_getFinalizedHead` works; indexer v4 head (2851273) equals the node's finalized head.
- **BLOCKED — needs a human:** the Preprod faucet (`faucet.preprod.midnight.network/api/drips`) returns `400 Missing X-Captcha-Token header`; the documented Nethermind faucet is a captcha web UI. I did not attempt to bypass it.
  - **Operator action:** create 3 Preprod wallets, fund them via <https://midnight-tmnight-preprod.nethermind.dev/>, then run `bash scripts/local-network.sh up` (proof server only is needed) and `MN_PREPROD_SEEDS=s1,s2,s3 pnpm test:midnight:preprod`. The same 7-test scenario runs unchanged and writes `evidence/preprod-*.json`.
  - Until then, **Preprod integration is NOT verified**.

### Cardano (last, optional)

- Removed `cardano-tx-builder.ts` (it returned `simulated_cardano_*`), `cardano-wallet.ts`, and the Cardano/bip39/cbor dependencies.
- Added `src/cardano/anchor.ts`: a domain-separated Merkle batch over approved non-personal commitments (32-byte hex only, single network per batch) with an independent status.
- The only submitter is `UnavailableCardanoAnchor`, which reports **unavailable** (no Blockfrost Preprod credentials, no integration test). The Midnight path never calls it.

### brandme-cube

`src/passport_filter.py` is now applied in `get_cube`/`get_face` after the face-level policy ALLOW:
- nested owner references and valuation fields are stripped for non-owners;
- fabricated chain refs (`cardano_tx_*`, `simulated_*`, `encrypted_*`) are never displayed as evidence.

Tests: `tests/test_rights_cube_filter.py` (2/2). Cube startup itself remains untested (pre-existing state, per root CLAUDE.md).

### Service/runtime

- `brandme-chain` builds to `dist/` with artifacts and scripts.
- The Dockerfile uses Node 22 and regenerates and verifies prover keys at image build.
- The stale `BLOCKCHAIN_INTEGRATION.md` and `TESTING.md`, which described the stub as working, are replaced by an accurate `README.md`.

## Exit-evidence summary (as of this stage)

| Criterion | Experience complete | Integration verified | Production approved |
|---|---|---|---|
| `pnpm test:midnight:local` (compile + constraint/property/adversarial) | yes | **yes** (55/55 + 3 cardano) | no (no external contract review) |
| issue/prove/transfer/consume observed | yes | **local network: yes; Preprod: BLOCKED (faucet captcha)** | no |
| Replay / cross-network / concurrency | yes | local network: yes | no |
| Invalid proof / account switch | yes | local network: yes (invalid witness cannot produce a proof; tampered-proof submission not tested) | no |
| Reprint exactly-once | yes | local network + emulator: yes | no |
| Private-state backup → clean restore | yes | local network: yes | no |
| My Data export/deletion/tombstones/inference race | yes (backend) | Spanner emulator: yes (true overlap not reproducible on emulator) | no |
| No stub fallback in trust path | yes | static guard test + code removal | — |
| No Mainnet writes | yes | enforced, no override | — |

## Open items / proposals

1. **Preprod run**: needs funded seeds (above).
2. **Spanner `OperationStore` for brandme-chain** (TS): the V008 `ChainOperations` table exists. Until a store is written, chain writes stay disabled outside development (capability `read_only`).
3. **Maintenance authority custody**: move to governance multi-party or rotate away before valuable issuance.
4. **CI (not my file):** `.github/workflows/chain-tests.yml` pins Node 18 and sets the removed `*_FALLBACK_MODE=true`, which now aborts startup. Proposal: Node 22, `SKIP_ZK=1 pnpm test:midnight:local`; run the Python suites with the Spanner emulator service.
5. **Console ops pages** (`brandme-console/app/(ops)/{chain,rights,manufacturing,privacy}`): not started. The Lane 5 shell layout contract (`docs/build/status/astra-consumer-ui.md`) does not exist on this branch yet.
6. Python HTTP service endpoints behind the gateway's `upstream.rights` / `upstream.privacy` are not yet exposed (the domain logic is done; the FastAPI wiring depends on the foundation lane's service layout).
7. An external Compact/protocol review of commitments and witness handling is required before production.

## Stage 5 — Reconciliation with merged opus-foundation (2026-10-05)

opus-foundation PR #33 merged into `bench/opus-foundation-20261005`, not into this lane's base (`bench/opus-midnight-rights-20261005` is still `ede63f6`). Preview of integrating the foundation branch (`git merge-tree`):

- **Conflicts:** only root `package.json` and `pnpm-lock.yaml`. Resolution at integration:
  - keep foundation's scripts, engines and `packageManager pnpm@10.34.6`
  - point its placeholder `test:midnight:local` / `test:midnight:preprod` scripts at `pnpm --filter @brandme/chain test:midnight:local|preprod`
  - carry over this lane's `pnpm.overrides` (single ledger-v8 / onchain-runtime instance)
  - regenerate the lockfile with pnpm 10.34.6
- **No table collisions** between foundation V001 (15 tables/indexes) and V008/V009. The reserved numbers match the migration runner's reservation table. V008/V009 apply standalone and will run under `runner.py`'s checksum ledger.
- **Two data-category registries.** Foundation shipped `brandme_core.domains.register_data_category` (callbacks `export(db, member)` / `delete(db, member)`) and its privacy README points domain lanes at it. This lane had published `DomainPrivacyHandler`. Resolution: `brandme_core/domains/privacy/foundation_bridge.py` registers foundation categories with the My Data orchestrator, so either path gets inventory, export, deletion receipt, tombstone and re-delete after restore.
  - Foundation-style deletes run in their own transactions; the processing freeze already covers the gap.
  - Domains that need single-transaction deletion implement `DomainPrivacyHandler` directly.
  - Test: `test_foundation_registered_categories_are_driven_by_my_data`.
  - Privacy/rights/cube suites now **19/19** on the emulator.
- **Still to reconcile at integration (needs the foundation code on this base):**
  - route My Data commands through `run_idempotent_command` + `authorize`
  - register `privacy.deletion.requested/completed` and `chain.operation.observed` with the foundation event registry
  - mount the v1 routers behind foundation's session/OIDC middleware
  - add the API shapes to `packages/contracts`

## Stage 6 — CI fixes (2026-10-05)

- **Correction:** the root `.gitignore` ignores `*.json`. Until `62cde97`, `brandme-chain/contracts/toolchain.json`, `contracts/artifact-manifest.json`, `compiler/contract-info.json` and `evidence/undeployed-2026-10-05T18-51-38-369Z.json` existed only in the working tree. Earlier stages cite them; they are now tracked via `brandme-chain/.gitignore` negations.
- `9211286`: the indexer provider now gets an explicit `ws` WebSocket, because Node 20 (the regression workflow's runtime) has no global one. A clean clone passes type-check and 58/58 tests on Node 20 and Node 22.
- `9f242b9`: ported #30's fixes for pnpm setup, gateway test env, and SARIF permissions/v3. Trigger scoping was not ported.
- Remaining expected red: `regression` → `brandme_frontend` is missing from `pnpm-workspace.yaml`. This is pre-existing, documented in #30, and outside this lane.

## Stage 7 — property-test non-vacuity flake (#38, 2026-10-10)

- **Symptom on `main` (99fc2fa):** `tests/contracts/property.test.ts` sometimes failed with `consumeReprintAllowance never succeeded`.
- **Cause:** the test generator, not the contract. `consumeReprintAllowance` is unchanged.
  - An honest consume needs, in order: a reprintable issue, a grant with quota > 0 on it, then a consume by the current controller with `1 ≤ qty ≤ remaining` on a fresh job.
  - Uniform random commands lined up that way about 7–9 times per 150 sequences.
- **#39 (merged as `49623e4`)** made the guard deterministic. `seedCircuitCoverage()` puts one success and one rejection per guarded circuit into the tally before the random runs.
  - Side effect: the guard no longer measures whether the random stream itself reaches the honest reprint path.
- **#40 (this lane)** keeps #39's preamble and raises random-stream coverage of the honest path:
  - each sequence starts with a reprintable entitlement held by `m0` plus a quota-3 allowance;
  - grants carry quota ≥ 1 three times out of four;
  - consume gets a `'fit'` quantity that resolves to a value in `[1, remaining]`;
  - adversarial values are kept: quota 0, quantities −1..5, non-controller callers;
  - 100 runs instead of 150, with an explicit 180 s timeout per property.
- **Result:** in the random stream, consume succeeds about 70–90 times per run (68–81 in three post-merge runs), up from about 8.

## Stage 8 — re-verification on integrated `main` (2026-10-10)

`main` at `6044818`, which includes the W11 lane integration (`3f366f0`), #39 and #40. Every run below was in this container:

- `pnpm test:midnight:local`: the compactc 0.31.1 recompile reproduces the committed artifacts (manifest unchanged); 58/58.
- `pnpm test:midnight:network` on the local network (node 1.0.300, indexer 4.3.5, proof server 8.1.0): **7/7** in 9m43s.
  - Evidence: `brandme-chain/evidence/undeployed-2026-10-10T21-15-56-331Z.json`.
  - Contract `2eca9ad1…3082`; source sha256 `919577bf…fa49`, which matches the manifest.
- Spanner emulator 1.5.45: `tests/test_privacy.py`, `tests/test_rights.py` and `tests/test_rights_cube_filter.py` pass 19/19.
  - Importing `brandme_core.domains` now requires `jsonschema` (through foundation `events`). Only `brandme_core/domains/commerce/requirements.txt` declares it.
- Gateway with the emulator: 34/34, including foundation's identity suite, which applies V001–V009 through the migration runner.
- CI on `6044818`: Module Regression is green. `ci-cd.yml` is red on "Build Docker Images (agents)" because of the `brandme-agents` dependencies, which are outside this lane.

Still open:
- **Preprod:** issue/prove/transfer/consume has not been observed. It needs funded Preprod wallets.
- **Trust inventory:** `brandme_core/config.py:300,304` still registers `chain.midnight` and `chain.cardano` as simulated via the removed `src/services/*` files.
  - Accurate entries would be Midnight SANDBOX via `src/midnight/adapter.ts` (no Mainnet) and Cardano UNCONFIGURED (`UnavailableCardanoAnchor`).
  - `CLAUDE.md:13,52` is stale in the same way.
  - Both await a decision.
- **Integration:**
  - the v1 routes are not mounted;
  - `privacy.deletion.*` and `chain.operation.observed` are not registered with the foundation event registry;
  - no other domain registers with My Data (persona has a `deletion.py` that is not registered).
- **CI:** no Python tests run. Module Regression only compiles Python, and `ci-cd.yml:118` swallows pytest failures.

## Stage 9 — `chain-tests.yml` repaired (2026-10-10)

- **Before:** "Chain Service Tests" had never passed. Every job died in `actions/setup-node` because its cache path, `brandme-chain/pnpm-lock.yaml`, no longer exists. Behind that failure the workflow also:
  - pinned pnpm 8 and Node 18;
  - ran `pnpm lint`, but no ESLint config exists;
  - set the removed `*_FALLBACK_MODE` flags;
  - had a Cardano testnet job for a `tests/integration` suite that does not exist.
- **After:** the toolchain comes from the repo root, as in `module-regression.yml`: Node from `.nvmrc`, pnpm from `packageManager`, and the workspace lockfile.
  - **Unit Tests:** type-check, then `pnpm test:midnight:local` (fetch compactc, recompile, check the manifest and artifacts, run the 58 tests). This is the first CI job that runs the compile and manifest check.
  - **Build Test:** only the setup changed.
  - **Security Scan:** a blocking Trivy secret scan of the committed `brandme-chain/` files (image pinned by digest), then the informational `pnpm audit`. It replaces `trufflehog@main`, which never ran.
  - **Removed:** the lint step, the Cardano testnet job, the fallback env and the Codecov upload.
  - **Triggers:** now also cover `tests/contracts/**`, the root `package.json`, `pnpm-lock.yaml`, `.nvmrc` and the workflow file itself, on PRs as well as pushes.
- **Verified locally** (Node 24.21.0, pnpm 10.34.6):
  - a fresh frozen install;
  - type-check;
  - the lane gate: 58/58 with the manifest unchanged, in 174 s;
  - the build;
  - the Trivy secret scan: exit 0 on a clean export of `brandme-chain/`, exit 1 on a planted GitHub token.
  - `pnpm audit` reports 81 advisories across the workspace. That step stays informational.
- **CI on `659d0a2`:** all three jobs are green on a GitHub runner.
  - Unit Tests: compactc downloaded and sha256-verified, the 15 circuits recompiled in about 56 s, and `artifact manifest OK` passed the `git diff --exit-code` guard. Proving keys built on the runner therefore reproduce the committed manifest. Then 58/58.
  - Build Test: green.
  - Security Scan: the digest-pinned Trivy reported no secrets; `pnpm audit` stays informational.

## Stage 10 — tuple re-verification on `main` (2026-10-23)

`main` at `5174ec2`. Between Stage 9 and this stage, the repo owner merged #42–#50, which changed lane-owned files (`brandme-chain/`, `brandme_core/domains/{rights,privacy}/`, `tests/test_{rights,privacy}*.py`). Those PRs are not recorded in earlier stages. They are listed here by title, with the suites below as evidence of current behavior:
- #42: build and verify all Docker images before publishing
- #43: secure rights routes, wire domain events, and update Preprod
- #44: persist operations and reconcile authenticated transaction evidence
- #45: reconcile durable operations and project finalized entitlements
- #46: patch production dependencies and gate image publishing on audits
- #47: deliver durable outbox events through a fenced Pub/Sub worker
- #48: preserve deletion freezes and resume incomplete restores safely
- #49: add authenticated rights and partial My Data backend
- #50: add durable selected rights exports and authenticated downloads

### Midnight tuple, re-verified 2026-10-23

Sources, both fetched 2026-10-23:
- the [support matrix](https://docs.midnight.network/relnotes/support-matrix), which no longer shows a "Last Updated" date;
- [Networks and environments](https://docs.midnight.network/guides/networks-and-environments).

| Component | Matrix (all networks unless noted) | Pinned here | Change |
|---|---|---|---|
| Ledger | ledger 8 ("Preview, Preprod, and Mainnet run ledger 8"); no package version listed | `@midnight-ntwrk/ledger-v8@8.1.2` | none. npm has 8.1.3 (2026-10-02); not adopted without a matrix requirement |
| Compact toolchain | 0.31.1 | `compactc 0.31.1` | none |
| Compact runtime | 0.16.0 | 0.16.0 | none |
| Compact JS | 2.5.1 | 2.5.1 | none |
| Platform JS | 2.2.4 | 2.2.4 | none |
| On-chain runtime | 3.0.0 | 3.0.0 | none |
| Wallet SDK | 1.2.0 | 1.2.0 | none |
| Midnight.js / testkit-js | 4.1.1 | 4.1.1 | none |
| DApp connector API | 4.0.1 | 4.0.1 | none |
| **Proof server** | **8.1.3** | **`proof-server:8.1.3@sha256:0f4ab071…115c`** | **was 8.1.0** |
| **Node** | **1.0.400** (Preview now too) | local network **`midnight-node:1.0.400@sha256:915b117f…040f`** | **local was 1.0.300**, the previous Preview version |
| Indexer | Preview 4.3.5; Preprod/Mainnet 4.3.302 ("no public tag, release, or image yet") | local 4.3.5 | none |

Image digests come from the Docker Hub tag API. The same API returns the digests already pinned for 8.1.0 and 1.0.300, which confirms the method.

**Do not bump to ledger 9.** The matrix says compactc 0.34.0/0.35.0 and compact-runtime 0.19.0/0.20.0 "target ledger 9", "don't work with the versions in this matrix", and "Ledger 8 can't read the initial contract state of these contracts, so you can't deploy them to these networks." npm `latest` for `compact-runtime` is 0.20.0, so a routine dependency update would break deployment.

### Providers
- **Preprod.** The Midnight-hosted `rpc.preprod` and `indexer.preprod.midnight.network` endpoints were retired at 22:00 UTC on 2026-10-09; the indexer now answers HTTP 410.
  - Preprod is Blockfrost-only and every request needs a project token. #43 moved `network.ts` to `preprodEndpoints(projectId)`.
  - Stage 4's Preprod read-path check used the retired endpoints.
- **Faucets** (Nethermind; 5,000 tNIGHT per request, rate-limited):
  - Preview: `midnight-tmnight-preview.nethermind.dev`
  - Preprod: `midnight-tmnight-preprod.nethermind.dev`
  - Mainnet has none.

### Verified in this container
- **On `main` before the pin change:**
  - install and type-check pass;
  - `pnpm test:midnight:local`: manifest unchanged, 10 files / 90 tests (179 s).
- **After the pin change:** type-check passes; unit suites 90/90.
- **Durable operation store:** `pnpm --filter @brandme/chain test:spanner` on Spanner emulator 1.5.45: 3 files / 26 tests.
- **Python lane suites:** `tests/test_privacy*.py` and `tests/test_rights*.py`, with dependencies from `scripts/python/requirements.lock`: 99/99.
- **Network verification with the new pins.** Both images were pulled by the pinned digests, so Docker verified their content.
  - **Isolation run** (node 1.0.400 with the previous proof server 8.1.0): 7/7 in 551 s. Its evidence file was not kept, because its tuple label read 8.1.3 from `toolchain.json`.
  - **Final run** through `scripts/local-network.sh`: **7/7 in 556 s**. The running services reported node `1.0.400-87c0fbdb` and proof server `8.1.3`, with indexer 4.3.5.
    - Evidence: `brandme-chain/evidence/undeployed-2026-10-23T12-13-38-231Z.json`. Its tuple labels now come from `toolchain.json` and `package.json`, and its source sha256 matches the manifest.
    - One behaviour differs from the 2026-10-10 evidence. The losing concurrent acceptance is recorded as `Reconciling` ("broadcast pending; do not resubmit") instead of `Failed`, following the reconciliation added in #44/#45. Exactly one acceptance still finalizes.
- **CI on `240a967`:** all 17 checks green or skipped, including the lane gate, the durable operation store, the Python suites and all five Docker image builds.

### Still open
- **Preprod writes.** Still not observed. `pnpm test:midnight:preprod` refuses to start without `MIDNIGHT_BLOCKFROST_PROJECT_ID` (a Blockfrost Midnight Preprod token) and `MN_PREPROD_SEEDS` (three or more distinct funded test seeds with tNIGHT and DUST). Neither is set in this environment.
- **Trust inventory.** `brandme_core/config.py:300,304` still registers `chain.midnight`/`chain.cardano` as simulated via the removed `src/services/*` files.
  - `tests/foundation/test_mode_guard.py` requires strict modes to refuse `chain`, so dropping or retyping those entries changes foundation's boot policy. That is foundation's call.
  - Proposal: cite the current implementations instead. The Midnight adapter is SANDBOX-grade until Preprod writes and external review exist; Cardano is UNCONFIGURED (`UnavailableCardanoAnchor`).
- **Resolved on `main` since Stage 8:**
  - lane routes mounted (`brandme-gateway/src/routes/v1/index.ts:119-123`);
  - lane events registered (`brandme_core/domains/events.py:62-88`);
  - lane Python suites run in CI against an emulator (`.github/workflows/ci-cd.yml:154`).
- **`CLAUDE.md`.** The `brandme-chain` row is corrected in this stage, with file:line evidence.

## Stage 11 — round-03 ultra plan received and reviewed (2026-10-30)

- **Assignment:** `docs/build/orchestration/ultra-plan-03-opus-midnight-rights.md`, on `main` since `718d031` (2026-10-25).
- **Receipt:** 2026-10-30 16:47 UTC.
- **Branch:** `claude/midnight-rights-lifecycle-yhfyyu`, fresh off `main` `ed19dc1`. The plan's base (`2b5ae889`) and the bench head (`44aaceab`) are both stale; the bench branch is fully contained in `main`.
- **Next step:** the D-007 items, then the authenticated command backends.

### Plan review against `main` `ed19dc1`
What changed after the plan was written on 2026-10-25:

1. **Build step 5 (Q9 redaction) is superseded by D-007**, which the founder approved on 2026-10-30 (`docs/build/deviations.md:52`).
   - Foundation's `PlatformPrivacyHandler` (`brandme_core/events/erasure.py:170`) redacts `OutboxEvents` and `IdempotencyRecords` as their table owner.
   - The joint proof is `tests/foundation/test_deletion_leaves_no_member_rows.py`.
   - This lane's part:
     - (a) acknowledge the split;
     - (b) declare `transactional`/`delete_outside_txn` in the published Protocol. Today the orchestrator reaches them only through `getattr` (`brandme_core/domains/privacy/privacy.py:298-299, 444-452`), not through `DomainPrivacyHandler` in `deletion.py`;
     - (c) surface `purge_derived` detail in receipts.
2. **The trust-inventory retype is done** by foundation (`brandme_core/config.py:406-421`).
   - `chain.midnight` cites `RightsAdapter`, scoped by `MIDNIGHT_NETWORK`, with the no-Preprod-evidence note.
   - `chain.cardano` is UNCONFIGURED.
   - This resolves founder input 3 and check-in question 5.
3. **Items for this lane that the plan doesn't list.**
   - Foundation's follow-ups (`docs/build/status/opus-foundation.md`, "Lane follow-ups"):
     - `purge_derived` in receipts (same as 1c);
     - a Preprod contract deploy procedure;
     - seed-rotation tooling.
   - Founder flag **F-identity**: account deletion leaves `Members`, `MemberSettings`, `MemberIdentities`, `ConsentGrants` and `Sessions`. Foundation adds a final identity step once this lane rules on ordering.
   - The **Q9 restore trade-off**: whether to carry `DeletionJobs` with `DeletionTombstones`.
4. **Real-domain My Data registration mostly exists already.** Persona, wardrobe, social, rewards, media and commerce register handlers (`brandme_core/domains/*/deletion.py`, `brandme_core/domains/commerce/privacy_handler.py`). What step 4 still needs is composition: one My Data service with every handler, in dev form.
5. **The command routes are mounted but have no backend.**
   - The routes: `POST /assets/:id/transfers`, `POST /assets/:id/reprint-quotes`, `POST /ownership/challenges` and `POST /ownership/submissions` exist behind scopes.
   - `/me` reports `rights.transfer` as `unconfigured`/`lane_not_integrated` (`brandme-gateway/src/routes/v1/me.ts:41`).
   - `brandme-chain/INTEGRATION.md` ("Still required") lists the missing command construction and member wallet/session flow.
6. **Migrations.** The registry runs V001–V015 with a contiguity guard. The anchor record takes V016, and its row goes into `RESERVED` (`tests/foundation/test_migrations.py:23`) and the migrations README in the same change. That test file is foundation's, so this needs a coordination note.
7. **The disclosure default is assigned twice:** this plan's step 7 (contract layer) and consumer-domains' item 12 (API layer).
   - No anchor-record or disclosure-default spec exists under `docs/design/`; the locked default appears only in the round-03 plans.
   - Default: one shared facet-class definition, owned here and consumed by consumer-domains (check-in question).
8. **Spatial's scan UX has merged (#60).** It consumes this lane's `brandme.passport.claims/v1` (`docs/build/status/astra-spatial-ar.md:429`), so the anchor record has to keep that contract.
9. **Preprod.** The credentials are still absent here (names-only check). Finality remains the outstanding item.

### Order (defaults applied, building per the check-in rule)
1. D-007 items.
2. Authenticated command backends.
3. Hardening of the operation store and reconciler.
4. Event producers and My Data composition (dev form).
5. Anchor record (V016), disclosure filter and invariants.
6. Preprod prep (deploy procedure, seed rotation, credential manifest), then finality once credentials land.
7. Final-head 7/7 local verification and Blockfrost-only audit, then the check-in packet.

### Credential manifest
No values or seeds are ever recorded here.

| Name | Scope | Where stored | Provisioned |
|---|---|---|---|
| `MIDNIGHT_BLOCKFROST_PROJECT_ID` | Blockfrost Midnight Preprod project token (prefix `nightpreprod`) | environment secret, set by the founder | not yet |
| `MN_PREPROD_SEEDS` | three or more Preprod test-wallet seeds holding tNIGHT and DUST; never Mainnet | environment secret, set by the founder | not yet |

## Stage 12 — D-007 accepted; Protocol extension, receipt notes and identity ordering (2026-10-30)

- **Assignment:** round-03 plan build step 5, as replaced by D-007 (`docs/build/deviations.md:52-58`), plus foundation's open founder flags F-identity and the Q9 restore trade-off (`docs/build/status/opus-foundation.md:291,296`).
- **Base:** Stage 11 head `c55c010`.
- **Next step:** authenticated command backends (build step 2).

### D-007 (the table owner redacts undelivered payloads)
- **(a) Acknowledged.** Foundation's `PlatformPrivacyHandler` (`brandme_core/events/erasure.py:170`) owns `OutboxEvents` and `IdempotencyRecords`. The privacy orchestrator still never names a table.
- **(b) Declared as a stable extension.**
  - `NonTransactionalPrivacyHandler` (`brandme_core/domains/privacy/deletion.py:146`) and contract item 7 (`deletion.py:34-43`) publish `transactional = False` plus `delete_outside_txn`. The orchestrator calls it before the transaction that records the step and tombstone, and again for every tombstone on restore, so it must be idempotent. It never calls `delete` or `reapply_tombstone` for these handlers.
  - Not added to `DomainPrivacyHandler` itself: that Protocol is `runtime_checkable` and used in `isinstance` checks, so new required members would reject every existing handler.
  - Registration refuses the flag without a callable method, and a non-boolean flag (`runs_outside_transaction`, `deletion.py:158`; called from `register`). Both orchestrator call sites use the helper (`privacy.py:305,457`), replacing raw `getattr`.
- **(c) Receipts keep handler notes.**
  - Per-category `records_detail` and `derived_detail` (`privacy.py:393`). The platform handler's broker-retention note (`BROKER_COPIES`, `erasure.py:72`) now reaches the receipt instead of only the category text.
  - Contract item 8 (`deletion.py:44-47`): `exception` and `detail` must be short plain-language sentences, never identifiers, URLs, keys, provider error text or other members' data.
  - Known limit: a resumed run rereads saved steps, and the single `DeletionSteps.detail` column keeps only the exception when a handler set both. No current handler finishes with both.
  - The read API still relays only status and counts (`brandme_core/read_api/reads.py:201-202`), and the generated `DeletionOutcomeRead` has no field for notes. Member-visible notes need a contract field; that's a check-in question.

### F-identity: ordering ruling (default, built)
- **Ruling:** identity erasure runs **last**. It starts only after every other category of the job has finished both its record and derived steps.
  - Other handlers keep any identity mapping they need while they run.
  - A member whose deletion is pending (commerce settling, rights broadcasts awaiting reconciliation) can still sign in and read the pending receipt.
  - Restore re-applies identity tombstones last.
- **Built:** contract item 9 (`deletion.py:48-53`) and `runs_last` (`deletion.py:168`).
  - A handler sets `final = True`. The orchestrator sorts final categories last (`privacy.py:292`) and holds them pending, with `records_detail` "waits until every other category is finished" (`privacy.py:298-300`). Restore sorts their tombstones last (`privacy.py:453`).
  - Foundation's identity step can register as a final handler. This lane writes no identity code.
- **Still foundation's to decide:** what happens at acceptance (`account_state`, revoking sessions) and how the member gets the receipt once their identity is gone.

### Q9 restore trade-off: ruling (default, documented)
- **Carry `DeletionJobs`, `DeletionSteps` and the deletion rows of `ProcessingFreezes` with `DeletionTombstones`** (`brandme_core/domains/privacy/README.md:68-74`).
- **Finding:** the trade-off is wider than a refused category request.
  - The permanent account barrier in `assert_processing_allowed` reads `DeletionJobs` (`deletion.py:258-264`) and the `*` freeze (`deletion.py:248-254`).
  - A tombstone-only restore therefore re-applies the erasures and serves, but a guarded writer with a fresh basis time can then write a deleted account's data again.
- **Not enforced in code.** Foundation's `test_restore_without_the_job_ledger_reerases_and_serves` (`tests/foundation/test_outbox_retention.py:519-545`) asserts that a tombstone-only restore serves. A guard that refuses would change foundation's test, so it's a coordination question, not a self-applied edit.

### Verified (Spanner emulator 1.5.45, venv from `scripts/python/requirements.lock`)
- **New tests** (`tests/test_privacy.py:185-326`):
  - registry validation, including foundation's platform handler and bridge satisfying the extension;
  - deletion and restore wholly outside the transaction;
  - a final handler waiting for a pending category and running last on restore;
  - the receipt carrying `BROKER_COPIES` from the real platform handler.
- **Lane and joint suites:** 285 passed across 14 files, including the joint proof `tests/foundation/test_deletion_leaves_no_member_rows.py`, `tests/foundation/test_outbox_retention.py`, the lane privacy/rights suites, `tests/test_read_api.py` and every consumer and commerce privacy suite.
  - That run predates the F-identity edit.
  - After it, `test_privacy.py`, `test_privacy_recovery.py` and `test_rights.py` passed again (67 passed).
- **Full `tests/` on this stage's code:** 2107 passed, 67 skipped, 12 xfailed (the quarantined legacy suites).
  - One failure, `tests/foundation/test_migrations.py::test_only_reserved_numbers_are_used`, came from the next stage's uncommitted V016 file, which was in the working tree during the run. With that file moved aside the migrations suite passes (7 passed).
- **CI:** the Stage 11 head's checks are green on PR #70 (Foundation check, Test Core, chain, gateway, security).

## Stage 13 — authenticated rights command backend (2026-10-30)

- **Assignment:** round-03 build step 2, "Remaining commands behind principal/scope/CSRF/recent-auth, exercised end-to-end."
- **Base:** Stage 12 head `cd6224d`.
- **Next step:** the client-proven operation journal (wallet flow), then build step 3 (operation store and reconciler hardening).

### What was missing
- The gateway relayed `POST /assets/:id/transfers`, `POST /assets/:id/reprint-quotes` and `POST /ownership/challenges` to the read API.
- The read API is read-only by design (`brandme_core/read_api/README.md:3-5,48-49`), so every command reached no backend.

### Built
- **Command process `brandme_core/rights_commands`.** A private FastAPI process with its own credential `RIGHTS_COMMAND_SERVICE_TOKEN`.
  - The service refuses a token equal to any of the four other rights-lane service credentials (`config.py:37-38`).
  - It re-checks scope and recent authentication from the gateway's principal headers (`app.py:74`; window `app.py:31`).
  - It verifies the V001–V016 ledger and the columns it uses (`app.py:104`).
  - It never relays or logs database errors.
- **Domain commands (`brandme_core/domains/rights/commands.py`).**
  - `create_transfer` (`:146`):
    - authorizes against the member's single active, transferable entitlement on the configured network and contract (`_controlled`, `:105`);
    - an open intent holds the entitlement;
    - the intent fixes the `offerTransfer` arguments (nonce, terms digest, expiry in seconds);
    - stores only the invite's SHA-256 digest;
    - emits `ownership.transfer.requested` in the same transaction as the row and the idempotency record.
  - `accept_transfer` (`:193`):
    - binds the recipient's locally computed commitment; a wrong invite and a missing intent are both 404;
    - refuses the sender, expired intents and stale epochs;
    - a frozen sender reads as `invalid_transition`, so the sender's restriction isn't disclosed (`:236`).
  - `transfer_status` (`:255`): the sender's view carries the exact proving arguments once a recipient is bound.
  - `reprint_quote` (`:301`): read-only; never reserves quota; price is `null`/`unavailable`.
  - `authorize_challenge` (`:376`): stateless. `proveControl` records the challenge key on chain, which enforces single use.
  - Every command checks the restore barrier (`assert_serving`, `:99`) and the privacy processing guard in its own transaction.
- **V016 `rights_transfer_invites`.** Adds `contract_address`, `invite_digest`, `offer_nonce`, `terms_digest` and `recipient_subject_ref` to `TransferIntents`, plus sender/recipient indexes.
  - Registered in the migrations README and in `RESERVED` (`tests/foundation/test_migrations.py:26`). The README requires a new migration to add its `RESERVED` row in the same change; the owner's #45, #47 and #50 did the same.
- **Privacy for the new recipient link.**
  - The rights handler exports received offers with a `role`.
  - Erasing a recipient cancels an unproven offer and clears the commitment (`brandme_core/domains/rights/privacy_handler.py:92`).
  - The deployed export service includes received offers in the same contract-valid record shape (`brandme_core/privacy_exports/service.py:270`) and checks for the V016 column at startup (`:43`).
- **Gateway.**
  - Transfers, reprint quotes and challenges go to the command upstream (`brandme-gateway/src/services/rights.ts:108`).
  - Only rights scopes and `auth_time` are forwarded (`commandHeaders`, `brandme-gateway/src/routes/v1/chain.ts:96`).
  - Transfer creation now requires recent authentication (`assets.ts:57`). Before this stage it did not.
  - The invite must be 43–128 base64url characters, at least 256 bits (`assets.ts:28`); before, it was 8 characters minimum.
  - A closed allowlist of command refusals is relayed as Problems with gateway-owned text (`COMMAND_REFUSALS`, `services/rights.ts:16`). Any other body is still discarded.
  - New `GET /transfers/:id` and `POST /transfers/:id/accept` (`brandme-gateway/src/routes/v1/transfers.ts`) are **unmounted**, because the mount file is foundation's.
- **Credential.** Manifest row `RIGHTS_COMMAND_SERVICE_TOKEN` (`docs/build/security/credential-manifest.yaml:140`), templates at the end of both rights blocks, and symmetric `distinct_from` on the four other rights-lane token rows.
  - My config insertions shifted ten other rows' gateway-config line citations; those were corrected.
  - The guard reports 0 errors and the same 15 warnings as before.

### Not done here (stated plainly)
- **Strict modes refuse the process.** It has no entry in the trust-path inventory (`brandme_core/config.py`, foundation's mode-guard policy), so `guard("rights_commands")` refuses sandbox and production. Foundation needs to add the entry.
- **The `/transfers` router is unmounted.** Foundation needs to add one `router.use('/transfers', ...)` line.
- **Public contract shapes.** `packages/contracts` still lists `createTransfer`, `acceptTransfer` and `createReprintQuote` with empty bodies, so the shapes need foundation's catalog entries.
- **The operation journal for client-side proving is not built.** The wallet's `offerTransfer`/`acceptTransfer`/`proveControl` still need journaling before broadcast (`brandme-chain/INTEGRATION.md`, updated "Still required").
- **`/me` still reports `rights.transfer` as `lane_not_integrated`** (`brandme-gateway/src/routes/v1/me.ts:41`, foundation's file).

### Verified
- `tests/test_rights_commands.py`: 11 passed. Covers config, boundary, idempotent offer, binding and proving arguments, expiry and stale epoch, freezes and restore, the frozen sender, recipient erasure, quotes and challenges.
- `tests/test_rights.py`: passed (22 with the command suite).
- **End to end.** `brandme-gateway/src/routes/v1/commands-backend.test.ts` runs signed OIDC through the mounted gateway into the real Python process on the emulator: 3 passed.
  - It covers recent authentication, scope, the idempotent replay, the relayed `transfer_in_progress` Problem, a stranger's 404, challenge and quote.
  - It also checks the cookie CSRF refusal before any upstream call.
  - Logs carry no token, member id or invite.
- **Gateway:** lint and type-check clean; full suite 174 passed (21 files).
- **Chain durable store on V016:** 26 passed. A first run failed only because local `node_modules` predated main's zod 4 bump; re-synced from the frozen lock.
- **Other gates:** credential manifest 0 errors, contracts no drift, workspace guard clean, docs/build links clean.
- **Foundation, export and read-API suites with these changes:** 485 passed, 23 skipped, 0 failed.
  - Covers `tests/foundation/` (including the `RESERVED` row), `tests/test_privacy_exports.py`, `tests/test_read_api.py` and the command suite.
  - The full `tests/` run was still in progress at commit; its count is recorded in Stage 15.

## Stage 14 — event producers and My Data composition in dev form (2026-10-30)

- **Assignment:** round-03 build step 4, "Remaining event producers into the durable outbox (#47); real-domain My Data registration live in dev form."
- **Base:** Stage 13 head `d58e3c8`.
- **Next step:** the check-in packet. With this stage, commands, producers and redaction are done, which is the check-in trigger.

### Producers
At 2026-10-22, four registered lane events had no producer (`docs/build/evidence/midnight-integration-2026-10-22.md:35`). Now:

| Event | Producer | Status |
|---|---|---|
| `chain.operation.observed` | chain durable store (`brandme-chain/src/midnight/spanner-store.ts`) | already on `main` |
| `ownership.transfer.requested` | `create_transfer`, in the transfer intent's transaction (Stage 13) | built |
| `reprint.attested` | chain reconciler, in the atomic projection commit (`brandme-chain/src/midnight/reconciliation-queue.ts:127,143`) | built here |
| `license.issued` | none | **not produced; check-in question** |

- **`reprint.attested`.**
  - Emitted once, when a finalized `attestManufacture` first projects its manufactured child entitlement.
  - The unit is linked to the app's reprint job by the consumption nullifier it attests, never by the operation owner. A unit outside the app workflow is projected but emits nothing.
  - It commits with the projection and its completion marker, so it can't be emitted twice.
  - It doesn't touch `ReprintJobs.units_attested`, which counts manufacturer callbacks. On-chain attestation stays a separate fact.
- **`license.issued` is left unproduced on purpose.**
  - The spec makes a `LicenseGrant` the rights holder's record, backed by the verified contract (`docs/design/brandme/03-architecture-data-api.md:154`).
  - Its permissions and territory are not on chain; `grantReprintAllowance` carries only a policy digest.
  - Producing the row from chain facts would invent them, for example reading an unknown territory as unrestricted.
  - It needs an issuer-authenticated license command, and no issuer principal exists yet (governance is a stub).

### My Data composition in dev form
- `compose_registry` / `compose_my_data` (`brandme_core/domains/privacy/composition.py:25,41`) put every real handler in one registry:
  - the five consumer domains;
  - commerce;
  - rights;
  - foundation's platform handler.
- Demo and development only. Not deployable until deletion has one serialized executor per subject and foundation registers the final identity step (contract item 9).

### Verified
- `tests/test_my_data_composition.py`: 2 passed.
  - The composed registry covers all eight domains (commerce, media, persona, platform, rewards, rights, social, wardrobe), and strict modes are refused.
  - One account deletion finishes every category with nothing pending.
  - It clears the member's control link, deletes their sent intent, and cancels and unlinks an intent offered to them.
- `brandme-chain` reconciliation suite: 11 passed, including the new attestation test.
  - That suite's teardown validates every emitted outbox row against the Python event registry (`brandme-chain/tests/support/store-database.py:21-34`), so the new `reprint.attested` payload is checked across languages.
- `brandme-chain` type-check clean.

## Stage 15 — check-in packet (2026-10-30)

- **Trigger met:** authenticated commands (Stage 13), producers (Stage 14) and redaction (D-007, Stage 12) are complete.
- **Single outstanding item: Preprod finality.** `MIDNIGHT_BLOCKFROST_PROJECT_ID` and `MN_PREPROD_SEEDS` are still absent (names-only check). The day they land, the lane runs `pnpm test:midnight:preprod` and records tx IDs, block heights and hashes, and finality timestamps here. Screenshots are not evidence.
- **Head:** this packet sits on Stage 14 `6a4a11a`, branch `claude/midnight-rights-lifecycle-yhfyyu` (PR #70).

### Exit evidence against the plan
- [x] **New PR off `main`, authenticated command backends behind auth, exercised end to end.** Signed OIDC → mounted gateway → real Python process → Spanner, for transfer creation, reprint quotes and ownership challenges, including recent auth, scope, idempotent replay, relayed refusals and the cookie CSRF refusal (Stage 13).
  - **Caveat:** accept and status ship unmounted (foundation's mount file), and strict modes refuse the process until its trust-path entry exists.
- [ ] **Op store/reconciler hardening.** Not started this round (question 17).
- [~] **Producers and My Data.**
  - Done: `ownership.transfer.requested` and `reprint.attested` are produced, and My Data is composed in dev form across all eight domains.
  - Open: `license.issued` is deliberately unproduced (question 15).
- [x] **Q9 redaction (undelivered path) and the joint deletion proof are green.** Foundation's handler runs through this lane's orchestrator (D-007, Stage 12).
- [ ] **Anchor record and disclosure-filtered scan response.** Not started (questions 18–19).
- [ ] **Preprod finality.** Blocked on credentials; this is the single outstanding item.
- [ ] **7/7 local re-run and Blockfrost-only audit on the final head.** Deferred to the final head (question 17).
- [x] **Privacy suite green throughout.**
  - Stage 12: full `tests/` 2107 passed.
  - Stage 13: full `tests/` 2118 passed, 67 skipped, 12 xfailed, 0 failed. Collected before the frozen-sender test and Stage 14's tests, which passed separately (11 command and 2 composition tests).
  - Each stage's joint proof and privacy suites pass.

### Questions (21, with recommended defaults)
Several of the plan's questions are settled: the trust-inventory retype has landed, D-007 replaced the redaction question, and commands and producers are built. Their slots carry the decisions this round surfaced.

**Direction (7)**
1. **Preprod credentials.** Does the founder provision both secrets in the GitHub `sandbox` environment (`docs/build/security/credential-manifest.yaml:206-246`)? **Default: yes; the lane runs the day they land.**
2. **Mainnet criteria.** Should the lane define the go/no-go criteria next stage (not a Mainnet decision)? **Default: yes.**
3. **RFID split.** Midnight owns the anchor record and spatial owns the scan UX; confirm? **Default: yes.**
4. **Verification scope.** Disclosure invariants first, then the rights contracts? **Default: disclosure invariants first.**
5. **F-identity ordering.**
   - Identity erasure runs last (`final = True`, contract item 9). Sessions survive until that step so a pending receipt stays readable. Foundation registers the identity handler and decides what happens at acceptance (`account_state`, session revocation) and how the receipt reaches a member whose identity is gone.
   - **Default: yes, as built.**
6. **Wallet custody.** Test seeds go only in the environment secret, the manifest holds names only, and rotation means funding new wallets and sweeping the old ones (never editing in place)? **Default: yes.**
7. **Transfer invite design.**
   - The sender's app generates a ≥256-bit invite, the server stores only its digest, and the recipient binds their wallet's commitment (V016).
   - The alternative is recipient-issued receive codes, which need a new table.
   - **Default: sender-generated, as built.**

**Integration & security (7)**

8. **Command principal transport.**
   - Today: a service credential plus principal headers, with scope and `auth_time` re-checked by the backend.
   - Alternative: a signed short-lived assertion with its own audience, as the consumer domains use.
   - **Default: keep the service credential now; move to a signed assertion when foundation generalizes its signer.**
9. **Trust-path entry for `rights_commands`** (foundation's edit). **Default: a sandbox-grade entry citing `brandme_core/domains/rights/commands.py`, with no Mainnet mode.**
10. **Mount `/transfers`** (foundation's mount file, one line). **Default: mount now.**
11. **Public contract shapes** for `createTransfer`, `acceptTransfer`, `createReprintQuote` and a transfer read (foundation's `packages/contracts`). **Default: foundation adds them; the lane supplies the request/response shapes from `commands.py`.**
12. **Receipt notes (D-007c).** Expose `records_detail`/`derived_detail` through `DeletionOutcomeRead`? Contract item 8 now governs that text. **Default: add one optional plain-language field.**
13. **Q9 restore guard.**
   - Refuse to serve when a tombstone's deletion job is missing, because a tombstone-only restore loses the account barrier.
   - This changes foundation's `test_restore_without_the_job_ledger_reerases_and_serves`.
   - **Default: yes; foundation updates its test.**
14. **Finality evidence format.** Tx IDs, block heights and hashes, and finality timestamps, independently verifiable through Blockfrost, no screenshots? **Default: yes.**

**Scope & sequencing (7)**

15. **`license.issued`.**
    - Producing it needs an issuer-authenticated license command, because permissions and territory are the rights holder's (spec 03 `LicenseGrant`) and are not on chain.
    - No issuer principal exists yet.
    - **Default: keep it unproduced until issuer authority exists; never infer it from chain facts.**
16. **Client-proven operation journal.** Build the wallet flow's journal next, so `offerTransfer`/`acceptTransfer`/`proveControl` are journaled before broadcast? **Default: yes, next stage.**
17. **Order of the rest:** op-store hardening → client journal → anchor record → disclosure invariants → Preprod prep → final 7/7 and Blockfrost audit → finality when credentials land. **Default: yes.**
18. **Disclosure default owner.** One shared facet-class definition, owned by this lane and consumed by consumer-domains item 12? **Default: yes.**
19. **Anchor migration.** V017 (V016 is now transfer invites), with its `RESERVED` row in the same change, as the migrations README requires. **Default: yes.**
20. **Exports.** Harden only? Received offers are now included in the same contract-valid shape. **Default: harden only.**
21. **Next round.** A Mainnet-readiness round after Preprod finality, gated on the founder's go/no-go? **Default: yes.**
