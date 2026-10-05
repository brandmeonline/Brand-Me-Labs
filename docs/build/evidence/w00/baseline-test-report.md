# W00 baseline test report

**Executed:** 2026-10-05, branch `claude/opus-foundation-w00-2hgiw5` at `e4f1342`. That is spec baseline `0f5f58a` plus two docs-only commits (`4511236` spec package, `e4f1342` lane brief). No application code differs from the audited baseline.

**Environment:** Linux container. Node 22.22.0 / pnpm 8.15.0 for the baseline run (the repo's declared `packageManager`). Python 3.11.15 in a `uv` venv with `brandme_core/requirements.txt` pins. Cloud Spanner emulator `gcr.io/cloud-spanner-emulator/emulator:1.5.28` (docker). Cloud Firestore emulator 1.20.0 (`gcloud` component).

**Method:** I ran each existing suite as committed. A crash or timeout counts as a failure. The older documents' "these tests pass" claims (root `CLAUDE.md`, `README.md`, `FINAL_SUMMARY.md`) are not evidence and were not relied on. Raw outputs are in this directory.

## Summary

| Suite / check | Command | Result | Evidence |
|---|---|---|---|
| Spec package validator | `python docs/design/brandme/contracts/validate_spec.py` | **PASS** (docs only) | console |
| Legacy Spanner schema | per-statement apply of `brandme-data/spanner/schema.sql` to the emulator | **20 of 92 statements FAIL** | `legacy-schema-apply.txt` |
| `tests/test_consent_graph.py` | pytest vs emulator (schema as far as it applies) | **2 passed, 2 failed, 2 errors** | `pytest-test_consent_graph.txt` |
| `tests/test_provenance.py` | same | **0 passed, 1 failed, 5 errors** | `pytest-test_provenance.txt` |
| `tests/test_wardrobe.py` | pytest vs Firestore emulator | **1 passed, 5 failed** | `pytest-test_wardrobe.txt` |
| `brandme-cube/tests` | pytest | **1 passed (placeholder), 1 failed** | `pytest-tests.txt` |
| `scripts/regression/run_all.sh` | existing module harness | 10 modules "pass", **frontend FAILS** | `regression-report.md`, `regression-run_all.log` |
| `docker-compose.yml` | `docker compose config` | **does not parse** | `compose-config.txt` |
| Brain boot | `uvicorn main:app` vs emulator, `GET /health` | **503** before the pool fix below; 200 after | console |
| `pnpm install --frozen-lockfile` (pnpm 8) | root | **PASS** (frontend not in workspace, so not installed) | console |

Without a running emulator, the three root suites, which `CLAUDE.md` calls "actually pass", do not fail fast. `test_consent_graph.py` hangs until killed (no client timeout). The suites need `--timeout` (pytest-timeout) to report at all.

## Findings, classified

| # | Finding | Evidence | Classification |
|---|---|---|---|
| F1 | `schema.sql` uses PostgreSQL partial indexes (`CREATE INDEX … WHERE …`, 15 statements). Spanner GoogleSQL rejects them | `legacy-schema-apply.txt` | pre-existing defect |
| F2 | `Owns`, `Created`, `CubeFaces` are declared `INTERLEAVE IN PARENT` without the parent key prefix, so the tables are never created (plus 1 dependent index fails) | same | pre-existing defect |
| F3 | `CREATE PROPERTY GRAPH IntegritySpineGraph` fails to parse on emulator 1.5.28 | same | pre-existing; graph needs the base tables plus emulator support verification |
| F4 | Compose masked F1–F3 with `… ddl update … \|\| echo "Schema already applied"` | old `docker-compose.yml` | pre-existing; this lane's migration runner fails loudly instead |
| F5 | `FriendsWith.accepted_at` and `ConsentPolicies.revoked_at` lack `allow_commit_timestamp=true`, but the code writes commit timestamps | `pytest-test_consent_graph.txt` | pre-existing defect (schema vs code mismatch) |
| F6 | `brandme_core/firestore/wardrobe.py` puts `SERVER_TIMESTAMP` sentinels inside array values, which Firestore rejects | `pytest-test_wardrobe.txt` | pre-existing defect |
| F7 | `brandme-cube/tests/test_service.py` constructs `CubeService(db_pool=…)`, which the constructor no longer accepts; `test_api.py` is `test_placeholder()` | `pytest-tests.txt` | stale test (invalid test, not a regression) |
| F8 | `SpannerPoolManager` exposes `_database` but 49 call sites (brain, policy, cube, agents) use `pool.database`. Brain `/health` returned 503 and every query path raised `AttributeError` | brain log | **regression in shared lib**. Fixed in this lane with an additive read-only `database` property (`brandme_core/spanner/pool.py`); flagged as a cross-lane edit |
| F9 | `brandme_core.logging.StructuredLogger` has no `.warning`. `POST /intent/resolve` with an unknown tag returns 500 | brain log | pre-existing defect; **not fixed** (not this lane's file) |
| F10 | `docker-compose.yml` has duplicate keys (`spanner-emulator`, `spanner-init`, `depends_on`). A `postgres` service carries Spanner's ports | `compose-config.txt` | pre-existing; **fixed** (rewritten) |
| F11 | Python Dockerfiles `COPY ../../brandme_core` (outside build context) and `COPY requirements.txt` (missing at the compose context root). Agent Dockerfiles run `main:app`, but the code is in `src/main.py` | Dockerfiles | pre-existing; compose now uses a shared dev image with a hashed lock instead; Dockerfiles untouched |
| F12 | Regression harness "passes" for Python modules are `compileall` only. The gateway has 1 unit test. Chain "38 passed" runs against mocks with fallback flags forced on | `regression-run_all.log` | harness weakness; the passes are not behavior evidence |
| F13 | `brandme-frontend` is outside the pnpm workspace, so `tsc` fails on missing modules | `regression-run_all.log` | pre-existing; fixed in W01 by adding it to the workspace |
| F14 | Gateway `start()` exits if NATS is unreachable, so the gateway cannot boot without NATS | `brandme-gateway/src/index.ts` | pre-existing; addressed in W02 gateway work |
| F15 | Policy `canViewFace` calls undefined `fetch_owner_and_consent` (NameError for non-owners) | trust-path inventory | pre-existing defect |
| F16 | Cube calls nonexistent `compliance.verify_esg`; uses `request.state.get` | trust-path inventory | pre-existing defect |

## Reconciliation with the spec audit (07 §3) and root CLAUDE.md

- The spec audit's static findings hold at this HEAD. No code changed between `0f5f58a` and `e4f1342`.
- `CLAUDE.md` marks brain and policy **REAL**. At runtime both were broken by F8. Brain also hits F9 on the not-found path, and policy hits F15. The "REAL" label is not supported by execution.
- `CLAUDE.md` says the three root suites "actually pass". They do not: 3 of 18 tests pass, and only with emulators running.
- `CLAUDE.md` local-dev instruction `docker-compose up -d` cannot work (F10).
- Trust-path fabrications are enumerated in `trust-path-fixtures.md`. There are about 60 sites; several are unconditional.
