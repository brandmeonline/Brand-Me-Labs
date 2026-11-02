# CI/CD review — per workflow file (S2, 2026-11-01)

Scope: every file under `.github/` at HEAD `ed19dc15`: 7 workflows + `scripts/smoke-image.sh`. No `pull_request_target`, no `workflow_run`, no `continue-on-error` anywhere (grep). No `CODEOWNERS`, no `dependabot.yml` (directory listing). **Branch protection, required reviews, tag protection and the `sandbox` environment's protection rules are GitHub settings that are not represented in the repository and could not be assessed from code.**

Secrets referenced by name (whole `.github/`): `secrets.GCP_SA_KEY` (1). Repository variables: `vars.BM_DEPLOY_ENABLED`, `vars.BM_GCP_DEPLOYER_SA`, `vars.BM_GCP_PROJECT_ID` (3), `vars.BM_GCP_REGION`, `vars.BM_GCP_WIF_PROVIDER`, `vars.BM_GKE_CLUSTER`.

Action pinning (all workflows): 12 distinct actions by **major tag** (`actions/checkout@v4` ×20, `pnpm/action-setup@v4` ×15, `actions/setup-node@v4` ×15, `actions/setup-python@v5` ×9, `actions/upload-artifact@v4` ×3, `google-github-actions/auth@v2` ×2, `google-github-actions/get-gke-credentials@v2`, `github/codeql-action/upload-sarif@v3`, `docker/setup-buildx-action@v3`, `docker/metadata-action@v5`, `docker/build-push-action@v5`, `actions/cache@v4`); **1 by SHA** (`aquasecurity/trivy-action@ed142fd0…` `# v0.36.0`). Finding S2-SEC-006.

Untrusted-context interpolation in `run:` blocks: none. The only `github.head_ref` use is in a `concurrency.group` key (`consumer-ui.yml:14`), which is not shell-interpolated. Image tags from `docker/metadata-action` are passed through `env:` before use in shell (`ci-cd.yml:358-361, 377-390`).

---

## `.github/workflows/ci-cd.yml` — "Build, Test, and Deploy"

- **Triggers** (`:17-26`): `push` to `main`, `develop`, tags `v*`; `pull_request` to `main`, `develop`. Comment explains why feature branches are excluded from `push`.
- **Permissions** (`:32-34`): top-level `contents: read`, `security-events: write` (needed by `upload-sarif`). Deploy job overrides to `contents: read`, `id-token: write` (`:411-413`). No job has `packages`, `actions` or `pull-requests` write.
- **Defaults** (`:38-40`): `shell: bash` (→ `-eo pipefail`).
- **Env** (`:42-46`): `GCP_PROJECT_ID: lux-realestate-app` (public identifier; a project name unrelated to Brand.Me), `REGISTRY: gcr.io`.
- **Jobs:**
  - `test-gateway` (`:54-104`): Spanner emulator service `1.5.45`; `pip install --require-hashes -r scripts/python/requirements.lock`; `pnpm install --frozen-lockfile`; lint, type-check, vitest. `BRANDME_REQUIRE_EMULATORS=1`.
  - `test-frontend` (`:106-125`): `pnpm audit --prod` and `pnpm audit --audit-level=critical` as **blocking** steps; Next build.
  - `test-core` (`:131-201`): hashed lock; pinned Firestore emulator fetched by a SHA-256-verifying script (`scripts/python/fetch_firestore_emulator.py:16`); Pub/Sub + GCS emulator binaries fetched (also SHA-verified per the helper scripts); `pytest tests -q --timeout=300 -ra --continue-on-collection-errors`; Firestore rules suite must report `skipped 0`, `fail 0`, `pass >0` (`:198-201`).
  - `foundation-check` (`:212-266`): `pnpm check` (the documented local gate) then `pnpm smoke`.
  - `test-chain` (`:268-291`): type-check + `pnpm compact:verify` (committed Compact artifacts vs manifest).
  - `security-scan` (`:530-575`): **blocking** Trivy `fs --scanners vuln --severity CRITICAL --ignore-unfixed` with `.trivyignore.yaml` (currently empty baseline, `:26`) and `--file-patterns 'pip:requirements\.lock$'`; **blocking** repo-wide secret scan with `trivy-secret.yaml` that disables the test/example/markdown/vendor allow-rules; non-blocking SARIF report via SHA-pinned `trivy-action` uploaded to code scanning. Trivy image digest-pinned (`:544, 553`).
  - `build-images` (`:298-391`): `needs` all test jobs + security-scan; matrix gateway/core/agents/chain/console; builds with `push: false, load: true`, **runs `.github/scripts/smoke-image.sh` against the built image before any credential is introduced** (`:357-361`); then, only when `PUBLISH_IMAGES` (push to `main` or `v*` tag, `:310`), authenticates with **`google-github-actions/auth@v2` + `credentials_json: ${{ secrets.GCP_SA_KEY }}`** (`:364-368`) — a long-lived SA JSON key (Finding S2-SEC-001) — and pushes every tag, verifying a single digest per build (`:380-391`). Build cache `type=gha` scoped per service (`:354-355`). GitHub's cache isolation lets a run restore only caches created on its own branch or on the default branch, so caches seeded by PR or `develop` runs cannot be restored by a `main` publishing run (the reverse direction is allowed). Cache-poisoning of published images is therefore not reachable from untrusted PRs; treated as Info.
  - `deploy` (`:397-524`): gated by `startsWith(github.ref,'refs/tags/v') && vars.BM_DEPLOY_ENABLED == 'true'` and `environment: sandbox` (`:404-405`); offline Helm validation (`scripts/validate-helm.sh`, pinned helm `v3.22.1` / kubeconform `v0.8.0` with checksum verification, `validate-helm.sh:57-93`); renders the release from the **build job's digests** and fails on malformed digests or `REPLACE_ME` (`:432-459`); authenticates with **Workload Identity Federation (no key)** (`:461-466`); `helm upgrade --install … --wait --wait-for-jobs --timeout 15m` with migrations as a pre-upgrade hook (`:478-484`); **verifies health**: `kubectl rollout status` per Deployment, in-cluster `--check` of read-api/exports/events workers, and one retention CronJob run that must reach `Complete` (`:486-517`); failure diagnostics avoid secret values (`:519-524`).
- **Assessment:** least-privilege token, test-before-credential ordering, digest-propagated deploy and WIF for deploy are strong. Residual issues: the legacy static key for registry push (S2-SEC-001), tag-pinned actions (S2-SEC-006), hardcoded shared project id. `--continue-on-collection-errors` in pytest keeps running after import errors (still non-zero exit); noted, not a security issue.

## `.github/workflows/deploy-validate.yml` — "Deploy manifests"

- **Triggers** (`:14-32`): `push` to `main` and `pull_request`, both path-filtered to `brandme-infra/**`, `scripts/validate-helm.sh`, `brandme_core/**`, contracts, lock, itself.
- **Permissions** (`:34-35`): `contents: read`. `concurrency` cancel-in-progress per ref.
- **Steps:** hashed lock install; `actions/cache@v4` for `.cache/tools` keyed on the validator script hash (`:59-63`, archives re-verified against pinned SHA-256 on every run per comment and `validate-helm.sh:81-93`); `bash scripts/validate-helm.sh`.
- **No cloud credentials, nothing deployed.** Assessment: sound.

## `.github/workflows/chain-tests.yml` — "Chain Service Tests"

- **Triggers** (`:9-34`): path-filtered `push` (main, develop) and `pull_request` (main, develop); `workflow_dispatch`.
- **Permissions** (`:36-37`): `contents: read`.
- **Jobs:** `unit-tests` (type-check + `pnpm test:midnight:local`, which fetches the pinned `compactc` by release URL with `sha256sum -c` (`brandme-chain/scripts/fetch-compactc.sh:12-19`), recompiles, fails on manifest drift); `durable-store` (Spanner emulator `1.5.45`, hashed Python lock, `test:spanner`); `build-test` (`pnpm compact:verify` before build, dist check).
- **Assessment:** sound; no secrets; artifacts verified.

## `.github/workflows/consumer-ui.yml` — "Consumer UI"

- **Triggers** (`:3-8`): `pull_request` path-filtered; `push` only to `bench/astra-consumer-ui-20261005`; `workflow_dispatch`.
- **Permissions** (`:10-11`): `contents: read`.
- **Jobs:** `shell` (UI tests, production builds, Playwright chromium, dev servers on 127.0.0.1, visual baselines, artifact upload 14 days); `live-domains` (Spanner emulator **`1.5.28`** — drift vs `1.5.45` elsewhere; a **second `actions/checkout@v4` of a pinned same-repo commit `dafd3b16…` into `domain-reference` with `persist-credentials: false`** (`:79-83`) — fixed ref, not attacker-controlled; symlinks gateway `node_modules` into it (`:96`); starts a dev gateway and runs browser→gateway→domain→Spanner journeys).
- **Assessment:** no secrets; pinned reference checkout is safe because the ref is a literal SHA. Emulator version drift is Info.

## `.github/workflows/module-regression.yml` — "Module Regression"

- **Triggers** (`:9-17`): `push`/`pull_request` to `main`, `develop`; `workflow_dispatch`. **Permissions:** `contents: read`.
- **Steps:** `node scripts/check-workspace.mjs` before install; `pnpm install --frozen-lockfile`; `bash scripts/regression/run_all.sh` (runs `scripts/regression/modules/*.sh`, including a `brandme_gateway` module that names the orphan folder, `run_all.sh:14`; S2-SEC-011).
- **Assessment:** no secrets; informational.

## `.github/workflows/spatial-validation.yml` — "Spatial validation"

- **Triggers** (`:3-23`): `push` to `bench/astra-spatial-ar-20261005`; path-filtered `pull_request` to `main`; `workflow_dispatch`. **Permissions:** `contents: read`.
- **Steps:** asset rights/integrity validation; `python scripts/assets/prepare-vision.py` ("hash-pinned local inference"); Playwright; artifact upload 7 days with an explicit note that trace archives are kept local (`:89-91`).
- **Assessment:** no secrets; sound.

## `.github/workflows/workspace-guard.yml` — "Workspace guard"

- **Triggers** (`:13-21`): `pull_request` with **no branch filter** (intentional, comment `:14-16`); `push` to `main`. **Permissions:** `contents: read`.
- **Steps:** `node scripts/check-workspace.mjs --with-pnpm` (lockfile-only frozen check), guard self-tests.
- **Assessment:** no secrets; sound.

## `.github/scripts/smoke-image.sh`

Runs each freshly built image **without provider credentials** (`:2`). Gateway: requires `dist/index.js` and the contracts OpenAPI (`:8`). Chain: verifies committed artifacts and runtime imports (`:11-12`). Agents: imports; `BRANDME_MODE=production` CLI invocation must raise `TrustPathViolation` (`:17`). Core: non-root uid `10001` (`:21`); default command prints usage and exits 64 (`:22-26`); `pip check`; every `--help`; packaged migrations include V013/V014 (`:34`); **sandbox `--check` for five modules must exit 2 with `{"status":"startup_refused"}` and no traceback** (`:39-45`); boot-guard test that a configured sandbox consumer-domains passes while `BRANDME_TRYON_PROVIDER=simulated` is refused (`:48-63`); read API / export API / consumer-domain routers refuse unauthenticated calls and never leak provider errors (`:67-106`). Console: sharp codecs and a standalone HTTP response (`:110-134`).

**Assessment:** this script is the strongest CI control in the repo — it exercises the fail-closed behaviour of the shipped images. It does not run with any secret.

---

## What could not be determined from code
- Branch protection on `main`/`develop`, required status checks, required reviewers, signed-commit or linear-history rules.
- Tag protection for `v*` (a deploy trigger), and who can create tags.
- `sandbox` environment protection rules (required reviewers, wait timers) and whether `vars.BM_DEPLOY_ENABLED` is currently `true`.
- Which service account and IAM roles back `GCP_SA_KEY`; the credential manifest itself states this is unverified.
- Whether Dependabot/secret-scanning/push-protection are enabled at the repository/org level (no config files; GitHub-side settings).
