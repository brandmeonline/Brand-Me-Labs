# Trivy triage, 2026-10-25 (baseline renewal record; re-run 2026-10-30)

Owner: foundation lane. Cadence: monthly. **Next triage: 2026-11-25.** The 2026-10-30 re-run
below refreshes this record for the current head; it does not move the cadence.

This record covers the dependency-vulnerability gate in `.github/workflows/ci-cd.yml`
(Security Scan job, step "Block on fixable CRITICAL vulnerabilities"). It was first run on a
clean `git archive` export of `bf31c98`, which is `origin/main` `2b5ae88` (with PR #51
commerce, #56 consumer UI, #61 and #65 merged) plus the foundation round-4 commits.

**Re-run 2026-10-30** on a clean `git archive` export of `375180b`: PR #62 (foundation round
4) re-synced with main `22ff053`. Since `bf31c98` the only dependency change is the
fastapi/starlette/pydantic move in `9bdb129`: `brandme_core/requirements.txt` pins fastapi
0.134.0 and pydantic 2.7.4 (`:5`, `:11`), and the lock has starlette 1.3.1
(`scripts/python/requirements.lock`, floor in `scripts/python/requirements.in`). Every other
manifest, `pnpm-lock.yaml` included, is byte-identical (`git diff --stat bf31c98 375180b` lists
only those two Python files among the scanned manifests).

## How it was run

The image is the same digest-pinned one that CI uses (Trivy 0.75.0). The run used no
ignorefile. Vulnerability DB: schema 2, updated 2026-10-24 19:09 UTC for the first run, and
2026-10-30 01:01 UTC for the re-run (the gate command downloaded it; runs 2 and 3 reused it with
`--skip-db-update`). Three runs:

```bash
set -euo pipefail
IMG=aquasec/trivy@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa
# (local runs add: --network host, the proxy variables, the proxy CA as SSL_CERT_FILE, a DB cache volume)
# 1. The blocking gate exactly as CI runs it, minus --ignorefile.
docker run --rm -v "$PWD:/src:ro" -w /src "$IMG" fs --scanners vuln --severity CRITICAL --ignore-unfixed \
  --exit-code 1 --no-progress --file-patterns 'pip:requirements\.lock$' .
# 2. HIGH and CRITICAL, fixed or not: the set the SARIF report shows.
docker run --rm -v "$PWD:/src:ro" -w /src "$IMG" fs --scanners vuln --severity HIGH,CRITICAL --no-progress \
  --format json --file-patterns 'pip:requirements\.lock$' . > trivy-high.json
# 3. Informational only: run 2 plus --include-dev-deps. Neither the gate nor the report reads pnpm dev deps.
```

Trivy found 17 language-specific files both times: 15 pip manifests,
`scripts/python/requirements.lock` (through `--file-patterns`) and `pnpm-lock.yaml`.

## Result

| Check | 2026-10-25, `bf31c98` (DB 2026-10-24) | 2026-10-30, `375180b` (DB 2026-10-30) |
|---|---|---|
| Blocking gate, no ignorefile | exit 0: 0 fixable CRITICAL in all 17 targets | **exit 0: 0 fixable CRITICAL in all 17 targets** |
| CRITICAL, fixed or not | 0 | **0** |
| HIGH (default scan, as in the SARIF report) | 21 findings in 6 packages | **18 findings in 5 packages** (H2–H6 below) |
| HIGH in pnpm dev dependencies (informational) | 9 more in 2 packages | **10 more in 2 packages** (N1, N2) |
| `.trivyignore.yaml` | `vulnerabilities: []` | **`vulnerabilities: []`**; no entry added |

The three fewer HIGH findings are starlette's (H1, now fixed). fastapi 0.134.0, starlette 1.3.1
and pydantic 2.7.4 report no HIGH or CRITICAL finding. The dev-dependency count moved from 9 to
10 with no change to `pnpm-lock.yaml`. The newer DB no longer reports CVE-2026-53571 for vite
7.1.7 (that removes 2 findings, one per peer variation). It reports three more for undici 8.11.2
(CVE-2026-109383, CVE-2026-109829, CVE-2026-87018), all fixed in 8.12.2 like the one already
listed.

## Fixed since the 2026-10-23 baseline

The baseline was taken at `744d593` and held five entries, all fixable CRITICAL. All five are
fixed and their entries deleted. The starlette HIGH findings followed.

| Finding | Package and manifest | Fix | Commit |
|---|---|---|---|
| CVE-2024-33663 | python-jose 3.3.0, `brandme-core/requirements.txt` | unused pin removed (no `jose` import in any `.py`) | `cfee5ee` |
| CVE-2024-33663 | python-jose 3.3.0, `brandme-cube/requirements.txt` | unused pin removed | `cfee5ee` |
| CVE-2026-68770 | sentence-transformers 2.3.1, `brandme-agents/agentic/requirements.txt` | unused pin removed | `cfee5ee` |
| GHSA-6q48-6c7w-9gw2 | certifi 2026.7.22, `scripts/python/requirements.lock` | refreshed to 2026.10.23 | `cfee5ee` |
| CVE-2026-63374 | anyio 3.7.1, `scripts/python/requirements.lock` | fastapi 0.104.1 → 0.115.14 (`brandme_core/requirements.txt:5`) lets the lock take anyio 4.15.1 (starlette 0.27.0 → 0.46.2); `requirements.in` adds an `anyio>=4.14.2` floor | `9877496` |
| H1: CVE-2025-62727, CVE-2026-48818, CVE-2026-54283 (HIGH) | starlette 0.46.2, `scripts/python/requirements.lock` | fastapi 0.115.14 → 0.134.0 and pydantic 2.5.0 → 2.7.4 (`brandme_core/requirements.txt:5`, `:11`) let the lock take starlette 1.3.1; `requirements.in` adds a `starlette>=1.3.1,<1.4` floor. The commit records the full `tests/` suite green on that lock, commerce's TestClient suites included | `9bdb129` |

## HIGH backlog (not blocking today)

The plan in `docs/build/status/opus-foundation.md:226` makes HIGH blocking after November. Each
item below has one named owner. "Ships in" says where the package reaches a built image.
The lock is the deployed core runtime's dependency set: `brandme-core/Dockerfile:96-97`
installs it with `--require-hashes`. Counts are from the 2026-10-30 re-run.

| # | Manifest | Package (installed) | Findings | Fixed in | What the fix needs | Ships in | Owner |
|---|---|---|---|---|---|---|---|
| H2 | `scripts/python/requirements.lock` | protobuf 4.25.9 | CVE-2026-0994 (1) | 5.29.6 | Held below 5 by google-cloud-spanner 3.40.1, google-cloud-firestore 2.14.0 and opentelemetry-proto 1.21.0 (each requires `protobuf<5`, installed metadata). All three must be upgraded together. | core runtime image | foundation |
| H3 | `scripts/python/requirements.lock` | datamodel-code-generator 0.34.0 | CVE-2026-54621, -54653, -54654, -54690, -54691, -55389, -55391, -55415 (8) | 0.60.1 … 0.64.0 (0.64.0 clears all eight) | Regenerate `packages/contracts` with the new generator, then run `pnpm contracts:check` (drift). | core runtime image, as a dev tool (packet gap G20: the image installs the whole lock) | foundation |
| H4 | `scripts/python/requirements.lock` | black 26.10.0 | CVE-2026-114134 (1) | 26.10.1 | Single-package lock refresh. | core runtime image, as a dev tool (G20) | foundation |
| H5 | `brandme-core/requirements.txt` | aiohttp 3.9.1 | CVE-2024-23334, CVE-2024-30251, CVE-2025-69223, CVE-2026-111064, CVE-2026-111066, CVE-2026-69244, GHSA-2g87-pp6c-29x5 (7) | 3.9.2 … 3.14.4 (3.14.4 clears all seven) | Installed only by the legacy stage of `brandme-core/Dockerfile:23-24`, not the `runtime` stage CI builds. Bump to ≥ 3.14.4, or retire that stage together with the legacy deploy paths (packet section F). | legacy core stage only | foundation |
| H6 | `brandme-agents/agentic/requirements.txt` | langchain 0.1.0 | CVE-2026-45134 (1) | 0.3.30 | GraphRAG is disabled and builds no client (`brandme-agents/agentic/graph_rag.py:19-31`). Remove the unused LangChain pins, or move to ≥ 0.3.30 with the client rules in that comment. | agents image (`brandme-agents/Dockerfile:75-80`), built and published by CI, never deployed | commerce-agents |

That is 1 + 8 + 1 + 7 + 1 = 18 findings: foundation owns 17 (H2–H5), commerce-agents 1 (H6).

**pnpm dev dependencies (informational).** These come from run 3 only. They reach no image:
Trivy's default, which the gate and the report both use, suppresses them.

| # | Package (installed) | Findings (2026-10-30) | Fixed in | Path | Owner |
|---|---|---|---|---|---|
| N1 | vite 7.1.7 (two peer variations, so each finding counts twice: 6) | CVE-2026-112942, CVE-2026-39363, CVE-2026-39364 | 7.3.7 clears all three (already in the lock for `@vitest/mocker`) | `vite-node@3.2.4` ← `vitest@3.2.7` in `@brandme/gateway`, `@brandme/chain` and `@brandme/spatial-asset-tools` | foundation (`pnpm-lock.yaml` change); midnight-rights and astra-spatial-ar re-run their suites |
| N2 | undici 8.11.2 (4) | CVE-2026-109383, CVE-2026-109829, CVE-2026-109869, CVE-2026-87018 | 8.12.2 clears all four | `testcontainers@12.2.0` ← `@midnight-ntwrk/testkit-js@4.1.1` ← `@brandme/chain` (devDependencies) | midnight-rights |

## Rules for the next triage (monthly; next 2026-11-25)

1. Run the three commands above on a clean export of `main`. Always run the gate without the
   ignorefile, so a baselined finding cannot hide a new one.
2. If a fixable CRITICAL in a foundation-owned pin (the lock, `brandme_core/requirements.txt`,
   `pnpm-lock.yaml`) appears, fix it in the same change. If it is in a lane's manifest, name that
   lane as owner here.
3. Add an ignore entry only when a fix cannot land before the gate must be green. The entry needs
   all four fields: `id`, `paths` (scoped to the one manifest), `expired_at` (at most one cadence
   ahead) and a `statement` that names the owner lane and the reason. Delete it in the PR that
   fixes it.
4. Write a new dated record next to this one. Move every item that was fixed into "Fixed since",
   with its commit. Record the DB date: a newer DB alone can add or drop findings (2026-10-30, N1
   and N2).
