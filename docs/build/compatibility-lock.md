# Compatibility lock

**Owner:** opus-foundation lane. **Check date:** 2026-10-05. Versions come from the npm registry, nodejs.org, PyPI, and the gcr/Docker registries on that date. They are **pinned values, not "latest" policies**. Executable pins live in the lockfiles listed below; this file explains them.

Status legend: **installed+tested** = in a committed lockfile and exercised by `pnpm check` / `pnpm smoke` on the check date. **target (not installed)** = resolved for the lane that will install it; not yet compatibility-tested here.

## Toolchain

| Component | Pin | Source / check | Status |
|---|---|---|---|
| Node.js | **24.21.0** (Active LTS "Krypton") | nodejs.org/dist/index.json; tarball SHA-256 `fd8e59d5…cb2d6` verified against SHASUMS256.txt | installed+tested (`.nvmrc`, `.node-version`, `engines`, CI `node-version-file`) |
| pnpm | **10.34.6** | npm `pnpm` dist-tag `latest-10`. pnpm 12 exists; 10.x chosen for action/CI maturity and lockfile v9 | installed+tested (`packageManager`, `engines`, `engineStrict`) |
| Python | **3.11.15** | matches existing service code (`python:3.11-slim` Dockerfiles) | installed+tested (`.venv`; compose `python:3.11.15-slim`) |
| TypeScript | **5.9.3** (single resolved version across the workspace) | openapi-typescript 7.13.0 peers `typescript ^5.x`; TS 6/7 not adopted | installed+tested |

Lockfiles: `pnpm-lock.yaml` (lockfile v9, pnpm 10.34.6, the whole workspace including `brandme-frontend` and `packages/*`); `scripts/python/requirements.lock` (uv-compiled, `--require-hashes`). The older per-package npm/yarn locks are not used. `.gitignore` excludes `package-lock.json`/`yarn.lock`.

## Application frameworks

| Component | Pin | Status / note |
|---|---|---|
| Next.js (consumer target) | **16.3.8** (stable; `engines.node >=20.9.0`) | **target (not installed)**. `brandme-frontend` still resolves **14.0.4** (npm marks it deprecated). The upgrade is the frontend lane's isolated W01 change |
| Next.js (console, current) | 14.2.35 (from `^14.1.0`) | installed; builds on Node 24 |
| React / React DOM (target) | **19.3.0** | target. R3F 9.8.1 peers `react >=19 <19.4`; Next 16.3.8 peers `^19.0.0`. Current apps resolve 18.3.1 |
| Three.js | **0.186.1** | target (spatial lane) |
| @react-three/fiber | **9.8.1** (stable v9 line; not v10 alpha/canary) | target |
| Motion | **14.0.0** | target |
| @google/model-viewer | **4.3.1** | target |
| @mediapipe/tasks-vision | **1.0.1** (not the nightly) | target; models must be self-hosted and versioned |
| @tanstack/react-query | 5.104.1 | target (spec ch.03 frontend state default) |
| Express (gateway/chain) | 4.22.3 | installed+tested |

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
| Cloud Spanner emulator | `gcr.io/cloud-spanner-emulator/emulator:1.5.28` | installed+tested (V001 apply, emulator test suites, smoke, CI service) |
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

## Known compatibility issues (tested)

1. **@google-cloud/spanner 9.0.0 + emulator 1.5.28:** read/write transactions fail with `Unable to release unknown resource`. The emulator does not mark multiplexed sessions, and the client returns them to the session pool. Workaround, applied **only when `SPANNER_EMULATOR_HOST` is set**: `GOOGLE_CLOUD_SPANNER_MULTIPLEXED_SESSIONS=false` and `GOOGLE_CLOUD_SPANNER_MULTIPLEXED_SESSIONS_FOR_RW=false` (`brandme-gateway/src/middleware/identity/store.ts`). This must be re-tested against a real instance before sandbox.
2. **Spanner emulator 1.5.28** rejects the legacy `CREATE PROPERTY GRAPH` statement and all PostgreSQL-style partial indexes in `brandme-data/spanner/schema.sql` (baseline report F1–F3).
3. **pydantic models** generated from the spec cannot express JSON Schema `if/then`. Python services validate with `jsonschema` first (`packages/contracts/README.md`).
4. **pnpm 10** blocks dependency lifecycle scripts. The allowlist is in `pnpm-workspace.yaml` (`onlyBuiltDependencies`: esbuild, unrs-resolver, protobufjs, @parcel/watcher, sharp).
5. **Next 14.0.4** (frontend) builds on Node 24 but is deprecated upstream. The frontend lane must upgrade to the target row above.
