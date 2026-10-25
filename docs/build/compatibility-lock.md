# Compatibility lock

**Owner:** opus-foundation lane. **Baseline check date:** 2026-10-05. Next.js and test-tool security pins were rechecked on 2026-10-23; other historical registry notes below retain their baseline date. Versions come from the npm registry, nodejs.org, PyPI, and the gcr/Docker registries on that date. They are **pinned values, not "latest" policies**. Executable pins live in the lockfiles listed below; this file explains them.

Status legend: **installed+tested** = in a committed lockfile and exercised by `pnpm check` / `pnpm smoke` on the check date (`pnpm check` runs the whole `tests/` Python suite since 2026-10-23; before that it ran `tests/foundation` only). **target (not installed)** = resolved for the lane that will install it; not yet compatibility-tested here.

## Toolchain

| Component | Pin | Source / check | Status |
|---|---|---|---|
| Node.js | **24.21.0** (Active LTS "Krypton") | nodejs.org/dist/index.json; tarball SHA-256 `fd8e59d5…cb2d6` verified against SHASUMS256.txt | installed+tested (`.nvmrc`, `.node-version`, CI `node-version-file`) |
| pnpm | **10.34.6** | npm `pnpm` dist-tag `latest-10`. pnpm 12 exists; 10.x chosen for action/CI maturity and lockfile v9 | installed+tested (`packageManager`) |
| Python | **3.11.15** | matches existing service code (`python:3.11-slim` Dockerfiles) | installed+tested (`.venv`; compose `python:3.11.15-slim`) |
| TypeScript | **5.9.3** (single resolved version across the workspace) | openapi-typescript 7.13.0 peers `typescript ^5.x`; TS 6/7 not adopted | installed+tested |

**How the toolchain pins are enforced.** `packageManager` (`pnpm@10.34.6`) selects pnpm for corepack and for CI's `pnpm/action-setup`; CI installs Node from `.nvmrc`; and `checkRuntimes()` in `scripts/brandme.mjs` refuses `pnpm setup:demo` / `pnpm dev` unless Node is exactly `.nvmrc`, pnpm is exactly `packageManager` and Python is 3.11. `engines` is advisory only: `pnpm-workspace.yaml` sets `engineStrict: false`, and the ranges are wider than the pins (root `engines.node` is `>=20.0.0 <25`). `pnpm check` and `pnpm smoke` do not call `checkRuntimes()`.

Lockfiles: `pnpm-lock.yaml` (lockfile v9, pnpm 10.34.6, the whole workspace including `brandme-frontend` and `packages/*`); `scripts/python/requirements.lock` (uv-compiled, `--require-hashes`). The older per-package npm/yarn locks are not used. `.gitignore` excludes `package-lock.json`/`yarn.lock`.

## Application frameworks

| Component | Pin | Status / note |
|---|---|---|
| Next.js (frontend and console) | **15.5.28** (Maintenance LTS security release) | Installed together on 2026-10-23; retains the existing React 18.3.1 compatibility range. Both production builds are required by CI |
| Vitest / coverage / UI | **3.2.7** | Chain and gateway use matching test packages; critical UI-server advisory patched |
| Tinypool | **2.1.2** | Workspace override for worker-options pollution fixes; validated by chain/gateway/Spanner suites |
| PostCSS / minimatch v9 | **8.5.23 / 9.0.7** | Scoped overrides for source-map disclosure and pattern backtracking advisories |
| React / React DOM (target) | **19.3.0** | target. R3F 9.8.1 peers `react >=19 <19.4`; Next 16.3.8 peers `^19.0.0`. Current apps resolve 18.3.1 |
| Three.js | **0.186.1** | target (spatial lane) |
| @react-three/fiber | **9.8.1** (stable v9 line; not v10 alpha/canary) | target |
| Motion | **14.0.0** | target |
| @google/model-viewer | **4.3.1** | target |
| @mediapipe/tasks-vision | **1.0.1** (not the nightly) | target; models must be self-hosted and versioned |
| @tanstack/react-query | 5.104.1 | target (spec ch.03 frontend state default) |
| UUID (gateway) / Babel core | **11.1.1 / 7.29.6** | UUID retains CommonJS exports and bundled types; Babel override stays within v7 |
| Express (gateway/chain) | 4.22.3 | installed+tested |
| zod (gateway, chain, console) | **4.6.7** | Moved from 3.25.76 on 2026-10-24: GHSA-mrhx-c7xc-m3w5 (high, memory exhaustion on oversized input) has no 3.x fix. One semantic change touched code: `.default()` now takes the output type (`brandme-chain/src/config/index.ts:16`). Gateway 107/107, chain 90/90 + Spanner 26/26 |
| body-parser@1 / fast-uri@3 overrides | **1.20.9 / 3.1.9** | 2026-10-24 advisories (GHSA-27r3-jxmh-p828 high; four fast-uri moderate/low) in express 4.22.x and ajv 8.20 dependencies; `pnpm audit --prod` clean afterwards |

## Midnight tuple

The spec's dated tuple (ch.04 §1) is reproduced below with npm availability on 2026-10-05. The foundation lane does **not** install Midnight packages. The midnight-rights lane pins and tests the tuple as a group (W09).

| Component | Spec tuple | npm on check date | Note |
|---|---|---|---|
| Ledger | 8.1.2 | `@midnight-ntwrk/ledger-v8@8.1.2` exists (`@midnight-ntwrk/ledger` latest is 4.0.0, a different package line) | use the versioned package name |
| Compact runtime | 0.16.0 | 0.16.0 exists; `latest` is 0.20.0 | pin 0.16.0 unless the tuple is re-verified as a group |
| Compact JS | 2.5.1 | 2.5.1 exists; `latest` 2.5.3 | |
| Platform JS | 2.2.4 | 2.2.4 exists; `latest` 3.0.0 | |
| On-chain runtime | 3.0.0 | `@midnight-ntwrk/onchain-runtime-v3@3.0.0` exists | |
| Midnight.js | 4.1.1 | `@midnight-ntwrk/midnight-js-contracts@4.1.1` = latest | |
| testkit-js | 4.1.1 | `@midnight-ntwrk/midnight-js-testkit-js` **not found**; name to resolve from official docs | open item for W09 |
| Wallet SDK | 1.2.0 | `@midnight-ntwrk/wallet-sdk-facade@1.2.0` **not found** (latest 4.0.1) | package naming changed; resolve in W09 |
| DApp connector API | 4.0.1 | 4.0.1 = latest | |
| Compact compiler / dev tools / proof server / node / indexer | 0.31.1 / 0.5.1 / 8.1.0 / 1.0.400 / 4.3.302 (Preprod) | not npm packages | verify against official release notes in W09 |

## Infrastructure images and emulators

| Component | Pin | Status |
|---|---|---|
| Cloud Spanner emulator | `gcr.io/cloud-spanner-emulator/emulator:1.5.45` (changed from 1.5.28 on 2026-10-23 so the developer script matches every CI service container) | installed+tested (V001–V014 apply, full `tests/` suite, gateway emulator suites, smoke; CI `test-gateway`, `test-core`, chain `durable-store`; the new CI `foundation-check` job was verified only by a local replay before its first GitHub run) |
| Firestore emulator | gcloud component `cloud-firestore-emulator 1.20.0` (SDK 530.0.0); compose image `gcr.io/google.com/cloudsdktool/google-cloud-cli:587.0.0-emulators` | gcloud component used for the baseline wardrobe tests. The compose image tag was verified to exist but not run |
| NATS | `nats:2.10.29-alpine` (compose `events` profile) | verified tag exists; not run |
| Node image | `node:24.21.0-bookworm-slim` | verified tag exists; compose path not executed here |
| Python image | `python:3.11.15-slim` | verified tag exists; compose path not executed here |

## Libraries introduced by the foundation lane

| Library | Pin | Where |
|---|---|---|
| openapi-typescript / openapi-fetch | 7.13.0 / 0.17.0 | `packages/contracts` |
| ajv / ajv-formats | 8.20.0 / 3.0.1 | contracts tests, gateway validation |
| @google-cloud/spanner (Node) | 9.0.0 | gateway identity store |
| jose | 5.10.0 (dual CJS/ESM; 6.x is ESM-only and the gateway compiles to CommonJS) | gateway OIDC/JWKS |
| supertest | 7.3.1 | gateway tests |
| google-cloud-spanner (Python) | 3.40.1 (existing pin) | brandme_core |
| jsonschema | 4.26.0 (via spec requirement `>=4.23,<5`) | event/envelope validation |
| datamodel-code-generator | 0.34.0 | Python contract models |
| pytest-timeout | 2.3.1 | test hygiene (baseline suites hang without it) |
| jwcrypto / PyJWT[crypto] / rfc8785 / sd-jwt | 1.6.1 / 2.15.1 / 0.1.4 / 0.10.4 (see below) | commerce/providers/MCP lane runtime pins, added to `scripts/python/requirements.lock` |

### Commerce lane pins in the foundation venv (2026-10-23)

Listed directly in `scripts/python/requirements.in` (not `-r` of the lane file, so a lane edit cannot change the shared lock without a foundation recompile) and kept in step with `brandme_core/domains/commerce/requirements.txt`. Recompiled with `uv pip compile scripts/python/requirements.in --generate-hashes -p 3.11 -o scripts/python/requirements.lock` (uv 0.8.17), using the existing lock as preferences: the non-comment diff adds only these four entries, and their hashes equal the commerce lane's S9 addendum. Their dependencies (cryptography 50.0.2, typing-extensions 4.16.0, PyYAML 6.0.3) were already locked.

| Package | Pin | Consumer | Status |
|---|---|---|---|
| jwcrypto | **1.6.1** (newer than the AP2 SDK's 1.5.6; fixes CVE-2026-39373) | AP2 SD-JWT (`brandme_core/domains/commerce/ap2.py`, `service.py`) | installed+tested (`tests/` with CI env; `--require-hashes` venv imports) |
| PyJWT[crypto] | **2.15.1** | MCP token and executor assertions (`brandme_core/mcp/authz.py`), `providers/local_atelier.py` | installed+tested. CVE-2026-103001 (options-dict mutation) has no fixed release; the lane passes a fresh literal options dict on every decode |
| rfc8785 | **0.1.4** | RFC 8785 canonical JSON for quote hashes (`commerce/quote.py`, `service.py`) | installed+tested |
| sd-jwt | **0.10.4** (same pin as the official AP2 SDK) | AP2 SD-JWT | installed+tested |
| anthropic | **0.125.0** (Q11, 2026-10-25; last release on httpx<1, which the lock holds at 0.25.1) | dev model planner (PR #51, `brandme_core/orchestrator/anthropic_adapter.py`), imported lazily, only with `BRANDME_DEV_ANTHROPIC_API_KEY` in development/demo | locked; imports in the `--require-hashes` venv. Transitive additions: distro 1.9.0, docstring-parser 0.18.0, jiter 0.18.0 |
| stripe | **16.0.0** (Q11) | Stripe TEST mode only (PR #51, `providers/payments/stripe_test.py`), sync HTTP through `stripe.HTTPXClient` on the locked httpx | locked; imports. Recompiled with the existing lock as preferences: exactly the five packages the commerce lane's verified patch named, no other version change; `uv pip check` clean |

With the pins the commerce suites import, but on `main` 15 commerce tests still fail on JSON files that were never committed (the old blanket `*.json` ignore rule) and 3 modules fail at import; they are quarantined with owner and blocker in `tests/conftest.py` until PR #51 brings the files.

## Known compatibility issues (tested)

1. **@google-cloud/spanner 9.0.0 + emulator 1.5.28:** read/write transactions fail with `Unable to release unknown resource`. The emulator does not mark multiplexed sessions, and the client returns them to the session pool. Workaround, applied **only when `SPANNER_EMULATOR_HOST` is set**: `GOOGLE_CLOUD_SPANNER_MULTIPLEXED_SESSIONS=false` and `GOOGLE_CLOUD_SPANNER_MULTIPLEXED_SESSIONS_FOR_RW=false` (`brandme-gateway/src/middleware/identity/store.ts`). The gateway suites pass on 1.5.45 with the workaround still in place; whether 1.5.45 still needs it was not tested. This must be re-tested against a real instance before sandbox.
2. **Spanner emulator 1.5.28** rejects the legacy `CREATE PROPERTY GRAPH` statement and all PostgreSQL-style partial indexes in `brandme-data/spanner/schema.sql` (baseline report F1–F3). Not re-tested on 1.5.45. The legacy suites that need that schema (`tests/test_consent_graph.py`, `tests/test_provenance.py`) are quarantined in `tests/conftest.py`.
3. **pydantic models** generated from the spec cannot express JSON Schema `if/then`. Python services validate with `jsonschema` first (`packages/contracts/README.md`).
4. **pnpm 10** blocks dependency lifecycle scripts. The allowlist is in `pnpm-workspace.yaml` (`onlyBuiltDependencies`: esbuild, unrs-resolver, protobufjs, @parcel/watcher, sharp).
5. **Security audit:** production findings and all critical findings now block CI and image publishing. Lower-severity findings remain visible; see `dependency-audit-2026-10-23.md` for the remaining upstream issues and exact verification. This is not a claim that every transitive dependency is vulnerability-free.

## Additions 2026-10-23 (opus-foundation round 2)

| Component | Pin | Status |
|---|---|---|
| Cloud Firestore emulator | gcloud component `cloud-firestore-emulator` **1.22.0** (`google-cloud-sdk-cloud-firestore-emulator-20260717053915.tar.gz`, SHA-256 `e962450b…ca91ba` from rapid `components-2.json`), fetched by `scripts/python/fetch_firestore_emulator.py` | installed+tested (projection + rules suites; CI `test-core`) |
| firebase (JS, dev-only) | 13.1.0 | installed+tested (`@brandme/firestore-rules`) |
| @firebase/rules-unit-testing | 6.0.0 (peers `firebase ^13`) | installed+tested |
| @grpc/grpc-js override | `@grpc/grpc-js@1.9` → **1.14.6** in `pnpm-workspace.yaml` (firebase pins `~1.9`, affected by advisories fixed in ≥1.13.6) | rules suite passes; `pnpm audit` advisory set identical to `main` |
