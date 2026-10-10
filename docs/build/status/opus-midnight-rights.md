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
- **Cause:** the test generator, not the contract.
  - An honest consume needs, in order: a reprintable issue, a grant with quota > 0 on it, then a consume by the current controller with `1 ≤ qty ≤ remaining` on a fresh job.
  - Uniform random commands lined up that way about 7–9 times per 150 sequences, so some seeds hit zero and tripped the non-vacuity guard.
  - `consumeReprintAllowance` is unchanged. The constraint suite, the callback-storm property and the local-network evidence already show it accepting and rejecting correctly.
- **Fix (test only):**
  - Each sequence now starts from an honest baseline: one reprintable entitlement held by `m0`, plus a quota-3 allowance.
  - Grants carry quota ≥ 1 three times out of four.
  - Consume gets a `'fit'` quantity that resolves to a value in `[1, remaining]`.
  - Adversarial values are kept: quota 0, quantities −1..5, and non-controller callers.
  - Runs went from 150 to 100 (more honest successes mean more real circuit work), with an explicit 180 s timeout per property.
- **Result:**
  - consume succeeds 76–87 times per run, with 104–139 rejections.
  - 5 consecutive local runs green.
  - Node 20: type-check passes; `pnpm -C brandme-chain test` is 58/58.
