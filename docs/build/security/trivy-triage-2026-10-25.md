# Trivy triage, 2026-10-25 (baseline renewal record)

Owner: foundation lane. Cadence: monthly. **Next triage: 2026-11-25.**

This record covers the dependency-vulnerability gate in `.github/workflows/ci-cd.yml`
(Security Scan job, step "Block on fixable CRITICAL vulnerabilities"). It was run on a clean
`git archive` export of `bf31c98`, which is `origin/main` `2b5ae88` (with PR #51 commerce, #56
consumer UI, #61 and #65 merged) plus the foundation round-4 commits. No dependency manifest
changed between `bf31c98` and the commit that adds this file.

## How it was run

The image is the same digest-pinned one that CI uses (Trivy 0.75.0). Trivy's vulnerability DB
was schema 2, updated 2026-10-24 19:09 UTC. The run used no ignorefile. Three runs:

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

Trivy found 17 language-specific files: 15 pip manifests, `scripts/python/requirements.lock`
(through `--file-patterns`) and `pnpm-lock.yaml`.

## Result

| Check | Result |
|---|---|
| Blocking gate, no ignorefile | **exit 0: 0 fixable CRITICAL** in all 17 targets |
| CRITICAL, fixed or not | **0** |
| HIGH (default scan, as in the SARIF report) | **21 findings in 6 packages** (below) |
| HIGH in pnpm dev dependencies (informational) | 9 more findings in 2 packages (below) |
| `.trivyignore.yaml` | still `vulnerabilities: []`; no entry added |

The npm and pip dependencies that arrived with PR #51 (stripe 16.0.0, anthropic 0.125.0 and the
commerce manifest) and PR #56 (consumer UI packages in `pnpm-lock.yaml`) add no CRITICAL. In
production dependencies they add no HIGH either: `pnpm-lock.yaml` scans clean without dev deps.

## Fixed since the 2026-10-23 baseline

The baseline was taken at `744d593` and held five entries, all fixable CRITICAL. All five are
fixed, and their entries are deleted.

| Finding | Package and manifest | Fix | Commit |
|---|---|---|---|
| CVE-2024-33663 | python-jose 3.3.0, `brandme-core/requirements.txt` | unused pin removed (no `jose` import in any `.py`) | `cfee5ee` |
| CVE-2024-33663 | python-jose 3.3.0, `brandme-cube/requirements.txt` | unused pin removed | `cfee5ee` |
| CVE-2026-68770 | sentence-transformers 2.3.1, `brandme-agents/agentic/requirements.txt` | unused pin removed | `cfee5ee` |
| GHSA-6q48-6c7w-9gw2 | certifi 2026.7.22, `scripts/python/requirements.lock` | refreshed to 2026.10.23 | `cfee5ee` |
| CVE-2026-63374 | anyio 3.7.1, `scripts/python/requirements.lock` | fastapi 0.104.1 → 0.115.14 (`brandme_core/requirements.txt:5`) lets the lock take anyio 4.15.1 (starlette 0.27.0 → 0.46.2); `requirements.in` adds an `anyio>=4.14.2` floor | `9877496` |

## HIGH backlog (not blocking today)

The plan in `docs/build/status/opus-foundation.md:226` makes HIGH blocking after November. Each
item below has one named owner. "Ships in" says where the package reaches a built image.
The lock is the deployed core runtime's dependency set: `brandme-core/Dockerfile:96-97`
installs it with `--require-hashes`.

| # | Manifest | Package (installed) | Findings | Fixed in | What the fix needs | Ships in | Owner |
|---|---|---|---|---|---|---|---|
| H1 | `scripts/python/requirements.lock` | starlette 0.46.2 | CVE-2025-62727, CVE-2026-48818, CVE-2026-54283 | 0.49.1, 1.1.0, 1.3.1 | fastapi 0.115.14 caps `starlette<0.47.0` (installed metadata). Clearing all three needs starlette ≥ 1.3.1, so fastapi ≥ 0.133.0, the first release without a starlette cap (PyPI `requires_dist`, checked 2026-10-25: 0.132.0 has `starlette<1.0.0`). That needs pydantic ≥ 2.7; the lock has 2.5.0 (`brandme_core/requirements.txt:11`). Recompile, then run the full `tests/` suite. Commerce re-verifies its FastAPI TestClient suites under the pydantic move. | core runtime image (read-api, exports, events worker, retention, migrations) | foundation (lock and `brandme_core/requirements.txt`); commerce-agents re-verifies |
| H2 | `scripts/python/requirements.lock` | protobuf 4.25.9 | CVE-2026-0994 | 5.29.6 | Held below 5 by google-cloud-spanner 3.40.1, google-cloud-firestore 2.14.0 and opentelemetry-proto 1.21.0 (each requires `protobuf<5`, installed metadata). All three must be upgraded together. | core runtime image | foundation |
| H3 | `scripts/python/requirements.lock` | datamodel-code-generator 0.34.0 | CVE-2026-54621, -54653, -54654, -54690, -54691, -55389, -55391, -55415 | 0.60.1 … 0.64.0 (0.64.0 clears all eight) | Regenerate `packages/contracts` with the new generator, then run `pnpm contracts:check` (drift). | core runtime image, as a dev tool (packet gap G20: the image installs the whole lock) | foundation |
| H4 | `scripts/python/requirements.lock` | black 26.10.0 | CVE-2026-114134 | 26.10.1 | Single-package lock refresh. | core runtime image, as a dev tool (G20) | foundation |
| H5 | `brandme-core/requirements.txt` | aiohttp 3.9.1 | CVE-2024-23334, CVE-2024-30251, CVE-2025-69223, CVE-2026-111064, CVE-2026-111066, CVE-2026-69244, GHSA-2g87-pp6c-29x5 | 3.9.2 … 3.14.4 (3.14.4 clears all seven) | Installed only by the legacy stage of `brandme-core/Dockerfile:23-24`, not the `runtime` stage CI builds. Bump to ≥ 3.14.4, or retire that stage together with the legacy deploy paths (packet section F). | legacy core stage only | foundation |
| H6 | `brandme-agents/agentic/requirements.txt` | langchain 0.1.0 | CVE-2026-45134 | 0.3.30 | GraphRAG is disabled and builds no client (`brandme-agents/agentic/graph_rag.py:19-31`). Remove the unused LangChain pins, or move to ≥ 0.3.30 with the client rules in that comment. | agents image (`brandme-agents/Dockerfile:75-80`), built and published by CI, never deployed | commerce-agents |

**pnpm dev dependencies (informational).** These come from run 3 only. They reach no image:
Trivy's default, which the gate and the report both use, suppresses them.

| # | Package (installed) | Findings | Fixed in | Path | Owner |
|---|---|---|---|---|---|
| N1 | vite 7.1.7 (two peer variations) | CVE-2026-112942, CVE-2026-39363, CVE-2026-39364, CVE-2026-53571 | 7.3.7 (already in the lock for `@vitest/mocker`) | `vite-node@3.2.4` ← `vitest@3.2.7` in `@brandme/gateway`, `@brandme/chain` and `@brandme/spatial-asset-tools` | foundation (`pnpm-lock.yaml` change); midnight-rights and astra-spatial-ar re-run their suites |
| N2 | undici 8.11.2 | CVE-2026-109869 | 8.12.2 | `testcontainers@12.2.0` ← `@midnight-ntwrk/testkit-js@4.1.1` ← `@brandme/chain` (devDependencies) | midnight-rights |

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
   with its commit.
