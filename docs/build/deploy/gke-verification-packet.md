# GKE deploy-verification packet — first deploy `BRANDME_MODE=sandbox`

Prepared 2026-10-23 on base `744d593` (main `5174ec2` + PR #53 round-2
foundation work). Revised 2026-10-25 on `bf31c98` (main `2b5ae88` with PRs #51,
#56, #61 and #65, plus foundation round 4). Section C is now an execution
checklist with a verify and an undo command for each step, and the `ci-cd.yml`
line references are refreshed. Owner: foundation lane.

**Nothing has been deployed, and no step in section C has been run.** No GCP credential works from the environment
that produced this packet (`gcloud auth list` → "No credentialed accounts"),
so the existence of a GKE cluster in `lux-realestate-app` / `us-east1` is
**UNCONFIRMED**. The deliverable is this packet plus manifests that are
validated offline. Every cloud step below is a founder action.

## 0. Read first: GKE versus ADR-06

The design contract makes **Cloud Run, not GKE, the initial cloud target**:
ADR-06 "Cloud Run plus durable task/event adapters as initial cloud target …
existing GKE remains an option" (`docs/design/brandme/07-repository-audit-sources.md:70`),
and "Preserve existing GKE manifests as an alternative operational deployment,
not the default prerequisite" (`docs/design/brandme/03-architecture-data-api.md:14`).
GKE is prepared here because the founder asked for it. Confirm the choice
(decision D2) before spending on a cluster. Most of this work carries over to
Cloud Run: the core `runtime` image stage and its explicit commands, the env
contract per process, the Secret Manager IDs, the per-workload Google service
accounts and least-privilege roles, Workload Identity Federation for CI, and the
deploy-by-digest pattern. The Helm chart, NetworkPolicies and PDBs do not.

A sandbox deploy is not a production release: "It does not automatically
authorize production deployment, customer messaging, actual purchases or
mainnet writes" (`docs/design/brandme/06-delivery-verification.md:115`).

### Founder decisions this packet needs

| ID | Decision | Recommended default |
|---|---|---|
| D1 | GCP project: keep `lux-realestate-app` (set deliberately in `9e6699b`, 2026-10-09, "ci: use lux-realestate-app GCP project for Docker push") or create a dedicated `brandme-sandbox` project. Every ID below depends on it. | Dedicated project per mode; if not, keep `lux-realestate-app` and accept the shared blast radius knowingly. |
| D2 | GKE now, or Cloud Run per ADR-06. | Confirm GKE explicitly in writing, or switch to Cloud Run and reuse sections C-5…C-17. |
| D3 | **Resolved (2026-10-25).** `main` packages V001–V015 with no gap (V003–V005 merged with the consumer-domains lane, V015 with PR #51). On an empty Cloud Spanner database the runner applies them in order. The runner still refuses out-of-order versions (`brandme-data/spanner/migrations/runner.py:195-202`) and `--allow-out-of-order` in sandbox/production (`:294-295`), so `tests/foundation/test_migrations.py::test_packaged_versions_are_contiguous_and_reserved_once` now fails any gap. | Nothing to decide. New migrations take V016 onward (`brandme-data/spanner/migrations/README.md`). |
| D4 | How Secret Manager values reach Kubernetes Secrets. | GKE secret sync add-on (GKE ≥ 1.33), step C-15. |
| D5 | OIDC issuer and audience the gateway trusts (strict modes require an https issuer and an audience, `brandme-gateway/src/middleware/mode.ts:53-56`). | Google Identity Platform (spec `03-architecture-data-api.md` item 9); values in C-11. |
| D6 | Public exposure and domain. The legacy files disagree (`api.brandme.io` vs `console.brandme.com`). An https origin for `gateway.publicOrigins` is needed even without ingress (`mode.ts:64`). | No public ingress for the first sandbox deploy; name the origin the app will use. |
| D7 | Who deploys the Midnight Preprod rights contract and owns the Blockfrost token. read-api and exports refuse to start without a 64-hex contract address. No deploy command for it exists in the repository (C-12). | Midnight-rights lane, with the address recorded in `values-sandbox.yaml`. |
| D8 | Cluster mode if one must be created. | Autopilot, Regular channel. |
| D9 | Retire the legacy deploy paths in section F (CLAUDE.md lists `agents/` as DO NOT DELETE). | Retire in one change that also updates CLAUDE.md. |

## A. What exists (verified)

| # | Fact | Evidence | How verified |
|---|---|---|---|
| A1 | CI pushes images to `gcr.io/lux-realestate-app/brandme-{gateway,core,agents,chain,console}` with tags `:main` and `:sha-<7>` on every push to `main`. Run 39902216424 (push, sha `5174ec2`) pushed core `sha256:a8c6a22e9e50…`, chain `sha256:69f9a96bf1b3…`, console `sha256:f6627c1f184a…`, agents `sha256:5b215c7a4d2e…`, gateway `sha256:adbf595add0e…`. | `.github/workflows/ci-cd.yml:310` (`PUBLISH_IMAGES`), `:332-342` (metadata tags), `:364-391` (JSON-key auth, push). Line numbers are on this head. Run log lines "The push refers to repository [gcr.io/lux-realestate-app/brandme-core]" / "main: digest: sha256:a8c6a22e…". | `gh run view 39902216424` (all build jobs `success`) and the saved run log. |
| A2 | At the audited baseline (`744d593`) the CI credential was a long-lived JSON key, `secrets.GCP_SA_KEY`, and no workflow had `id-token: write`. Since round 2, image publishing still uses the key, while the deploy job uses WIF (`id-token: write`) and is gated by `BM_DEPLOY_ENABLED`. | Baseline `ci-cd.yml:32-34`, `:277`, `:309` (at `744d593`). On this head: `build-images` `:298-391`, `deploy` `:397-518`. | Read. Which service account backs the key, and its roles, is unknown (GitHub secrets API returns 403 here). |
| A3 | The `Deploy to GKE` job has never run: it only runs on `refs/tags/v*` and the repository has no tags. | Gate at `ci-cd.yml:404`. Run 39902216424 lists "Deploy to GKE" with conclusion `skipped`. | `git ls-remote --tags` → 0 tags; `gh run view`. |
| A4 | Container Registry stopped accepting writes on 2025-03-18, so successful 2026 pushes to `gcr.io/lux-realestate-app` imply Artifact Registry `gcr.io` repositories exist in that project. | Google transition guide (audit map). | **Inference**, not a live check: an anonymous registry probe returns the same 401 for this project and for a nonexistent one. |
| A5 | The repository is public (`visibility: public`); repository id `1083300600`, owner id `25632130` (used to pin WIF in C-16). | — | `gh api repos/brandmeonline/Brand-Me-Labs`. |
| A6 | **New:** chart `brandme-infra/helm/brandme` for gateway, chain, console, read-api, exports-api, exports-worker, events-worker and a migration hook Job. | `brandme-infra/helm/brandme/` | `scripts/validate-helm.sh` passes: helm 3.22.1 lint `--strict`; 42/42 resources valid with `kubeconform -strict` against Kubernetes 1.35.0 and 1.36.0 (CI values, ingress on, GKE CRDs included); 32/32 for the filled sandbox values; 18 negative rendering tests refuse as expected (as of 2026-10-24); env contract OK. A deliberate typo in a core field and in a FrontendConfig field were both rejected (kubeconform exit 1). |
| A7 | **New:** the core image's last stage is `runtime`, so CI's default build of `core` produces it: hash-verified install of `scripts/python/requirements.lock`, uid 10001, no `--reload`, no celery, no default process (bare run prints usage, exit 64). | `brandme-core/Dockerfile` (final stage). Compose does not build this Dockerfile (`docker-compose.yml:22-30` uses an inline Dockerfile). | Built from the repo root with `-f brandme-core/Dockerfile --build-arg NODE_VERSION=24.21.0`, no `--target` (as `ci-cd.yml:344-355`); `bash .github/scripts/smoke-image.sh core <image>` exits 0. See G for the one local build deviation. |
| A8 | The core image runs the chart's commands as uid 10001 with a read-only root, `/tmp` tmpfs, all capabilities dropped: `runner.py up` applied V001–V014 to a fresh emulator database, `read_api --check` printed `{"status":"ready","read_only":true}`, the server answered `GET /health` 200 and an unauthenticated private read 401. | `docker run --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges …` | Ran against the local Spanner emulator (development mode; strict modes refuse emulators). |
| A9 | The chart's rendered env satisfies each process's own strict-mode validator: `ReadConfig.from_env`, `ExportConfig.from_env` (API and worker), `WorkerConfig.from_env` + `PubSubPublisher` topic checks (reached the credential lookup), and the gateway's `loadConfig` + `checkGatewayMode` (no violations), and the chain config parser. | Python stage of `scripts/validate-helm.sh`; gateway/chain run locally with `tsx`. | Ran with fake, distinct 40-char tokens. |
| A10 | The gateway and console images (unchanged Dockerfiles) serve `/healthz` and `/` as uid 1000 with a read-only root (`/tmp`, and for the console `.next/cache`, as tmpfs). | — | Built locally and run with the chart's settings; existing `smoke-image.sh gateway` / `console` pass. The chain image was **not** built here. |
| A11 | GKE Regular channel: 1.35 is the current auto-upgrade target (since 2026-04-28); 1.36 is available and auto-upgrades from 2026-11. The chart is validated against both. | docs.cloud.google.com/kubernetes-engine/docs/release-schedule (page updated 2026-10-22). | Read 2026-10-23. |

## B. What is missing

| # | Gap | Blocks first deploy? | Where it is fixed |
|---|---|---|---|
| G1 | Cluster existence, mode, version, Workload Identity pool and dataplane are unconfirmed. | Yes | C-3 / C-6 (founder) |
| G2 | The current deploy job cannot succeed: it installs `./brandme-umbrella`, whose subcharts and `values/values-prod.yaml` do not exist (helm 3.22.1: "missing in charts/ directory…", "open values/values-prod.yaml: no such file"); it pins `global.image.tag=v1.2.3` while metadata-action pushes `1.2.3`/`1.2`/`sha-…` (`ci-cd.yml:246-251` vs `:329` at `744d593`); it rolls out `brandme-core` (celery beat) and `brandme-agents` (a CLI) (`:336-337` at `744d593`); JSON key, no environment, no concurrency. | Yes (job now gated off) | **Section E applied in this change set:** the deploy job uses the new chart, deploys by digest, runs under `environment: sandbox` with WIF, and runs only when a `v*` tag AND `vars.BM_DEPLOY_ENABLED == 'true'`. Until the founder sets that variable, a tag cannot start a half-configured deploy. |
| G3 | No repo artifact provisions the data plane the code needs: Spanner instance/database, three Pub/Sub topics (≥ 24 h retention), the export bucket with its exact policy, Secret Manager secrets, per-workload GSAs and IAM, WIF. | Yes | C-5…C-17 |
| G4 | **Resolved:** migration numbering (D3). V001–V015 are contiguous on `main`; a test guards it. | No | — |
| G5 | No Midnight Preprod contract address exists (`docs/build/evidence/midnight-integration-2026-10-22.md:53`). read-api and exports refuse to start without one; chain starts but reports the capability `unavailable`. | Yes for read-api/exports | D7, then `values-sandbox.yaml` |
| G6 | No OIDC issuer/audience; the gateway refuses strict modes without them (verified: "OIDC_ISSUER is required; OIDC_AUDIENCE is required"). | Yes for gateway | D5, then `values-sandbox.yaml` |
| G7 | The console bakes its API URLs at build time and CI passes none, so browsers would call `http://localhost:3000` (`brandme-console/lib/api.ts:11-14`; `ci-cd.yml:349` passes only `NODE_VERSION`). `console.enabled: false` in `values-sandbox.yaml`. | No (console off) | Console build args (console owner) |
| G8 | **Fixed in this change set (gateway package):** the limiter exempts `/health`/`/healthz`, keys members by principal and addresses by `req.ip` with a configurable `TRUST_PROXY` (`brandme-gateway/src/middleware/rateLimiter.ts`, `src/config/index.ts:36-66`). The chart passes `gateway.trustProxy` and refuses `ingress.enabled` without it (`templates/validate.yaml`). The GKE value (2) is documented, not observed on a cluster. | No | Confirm `req.ip` on first ingress deploy |
| G9 | The gateway exits immediately on SIGTERM (`brandme-gateway/src/index.ts:98`). The chart adds a 5 s `preStop` sleep so endpoints are removed first; in-flight requests still drop at exit. | No | Gateway lane: drain on SIGTERM |
| G10 | Observed locally: with no ADC and no emulator, the gateway logs "listening" and then dies on an unhandled rejection from the Spanner client ("Could not load the default credentials"). With Workload Identity this should not occur, but a broken binding shows as a restart loop after the startup probe has briefly passed. | No | Gateway lane: fail before listening |
| G11 | **Fixed in this change set (gateway package):** strict modes refuse `SPANNER_EMULATOR_HOST`, `FIRESTORE_EMULATOR_HOST` and `PUBSUB_EMULATOR_HOST` (`brandme-gateway/src/middleware/mode.ts`). | No | — |
| G12 | The two workers have no health endpoint, so a hung worker is not detected. They exit non-zero on failed startup checks; the chart uses `minReadySeconds: 30` so a crash during startup blocks the rollout. | No | Core lane: heartbeat or health port |
| G13 | **Fixed in this change set (Python package):** `brandme_core/config.py` now carries audited inventories for read_api, privacy_exports, events_worker and gateway, and the stale chain entries are replaced (Midnight SANDBOX, Cardano UNCONFIGURED). chain/read-api/exports pass `preflight` in sandbox only (test networks); production stays refused. The chart still runs no `preflight` init container; adding one needs `ENVIRONMENT=BRANDME_MODE` and each service's network variable. | No | Optional init container after first deploy |
| G14 | No Pub/Sub subscriptions or consumers exist; the outbox README asks for subscriptions before publishing (`brandme_core/events/README.md:15-26`). Topic retention (≥ 24 h, required by `brandme_core/events/pubsub.py:94-103`) is the only replay window until consumers exist. | No | Consumer owners |
| G15 | The Firestore projection writer has no process entrypoint, so Firestore is not provisioned or deployed here. | No | Foundation lane, later |
| G16 | No secret-delivery mechanism is installed (D4). | Yes | C-15 |
| G17 | `automountServiceAccountToken: false` relies on the GKE metadata server issuing Workload Identity tokens without the pod's KSA token. **Inference**; the in-cluster `--check` commands (C-21) prove or disprove it on first deploy (`podDefaults.automountServiceAccountToken` toggles it). | Maybe | First deploy |
| G18 | NetworkPolicy egress for the metadata server uses Google's documented addresses (169.254.169.252/32:987,988; Dataplane V2 169.254.169.254/32:80,8080) and DNS (kube-dns, 169.254.20.10, 169.254.169.254). Not exercised on a real dataplane. | Maybe | First deploy |
| G19 | Spanner custom role permissions (`brandmeSpannerDataReadWrite`, created by the script in C-13) are derived from `roles/spanner.databaseUser` minus schema rights; not exercised live. | Maybe | First deploy (`--check`, the retention pass and logs) |
| G20 | The core image installs the whole foundation lock, including test tools (pytest, black, datamodel-code-generator). | No | Split a runtime-only lock |
| G21 | Base images are pinned by tag (`python:3.11.15-slim`, `node:24.21.0-bookworm-slim`), not digest; third-party actions are not SHA-pinned; no Dependabot/Renovate. | No | Foundation follow-up |
| G22 | **Fixed in this change set:** `.cache/` is in `.gitignore` and `.dockerignore`. | No | — |
| G23 | The consumer frontend has no Dockerfile and no image. | No | Frontend owner |
| G24 | `build-images` still publishes with the JSON key. The provisioning script now creates a separate push identity (`bm-sbx-fnd-pusher`, artifactregistry.writer only) in its own `github-push` pool (main and `v*` tags); switching `build-images` to it is a one-step change after the founder runs the script. | No | Founder runs the script, then foundation switches build-images |
| G25 | The export API cannot check that its token differs from the read API and chain tokens, because those are not in its pod. Distinctness depends on generating independent values (C-14). | No | C-14 |
| G26 | The gateway's write-side calls have no server among the deployed processes. `POST /challenges`, `/assets/{id}/transfers` and `/assets/{id}/reprint-quotes` go to `RIGHTS_SERVICE_URL` (`brandme-gateway/src/routes/v1/ownership.ts:44`, `assets.ts:55`, `assets.ts:71`), and `POST /deletion` goes to `PRIVACY_SERVICE_URL` (`routes/v1/privacy.ts:110`). The chart points both URLs at the read API (`templates/gateway.yaml`), which serves only GET routes (`brandme_core/read_api/app.py:95-117`). In sandbox those routes would get 404/405. | No (reads work) | midnight-rights / privacy lanes: name the write-side service |
| G27 | **Inference, not tested:** `@google-cloud/spanner` 9.0.0 (gateway, chain) may export client-side metrics to Cloud Monitoring by default. If it does, GSAs without `monitoring.timeSeries.create` will log export errors. Grant `roles/monitoring.metricWriter` to those GSAs, or turn the client metrics off. | No | First deploy logs |

## C. Founder execution checklist (in order)

**Every step below is `not run`.** Nothing in this section has been executed against GCP,
GitHub settings or a cluster from this repository. Run the steps in Cloud Shell or on a
workstation, as a project owner, in one shell. Each step is marked **[read-only check]** or
**[creates resource]**. Each step has a **Verify** command, which must succeed before the
next step, and an **Undo** command. Never paste a secret value into a command, a ticket or a
chat: the commands pipe values, and the checks compare digests without printing them. Record
each step's verify output, redacted to its status line, in the deploy evidence.

### C-0 [decision gate] Write the answers down before any step that creates a resource

| ID | Decision | Needed by | Answer (fill in) |
|---|---|---|---|
| D1 | Project: a dedicated sandbox project, or `lux-realestate-app` with its shared blast radius | every step | |
| D2 | GKE (this packet) or Cloud Run per ADR-06 | C-6 onward | |
| D5 | OIDC issuer and audience the gateway trusts | C-11, C-19 | |
| D6 | The https origin for `gateway.publicOrigins`. It is required even with no ingress, because the strict gateway refuses non-https origins (`brandme-gateway/src/middleware/mode.ts:64`) | C-19 | |
| D7 | Who deploys the Preprod rights contract (recommended: midnight-rights) and owns the Blockfrost account | C-12, C-14 | |

D3 is **resolved**. `main` packages V001–V015 contiguously, and
`tests/foundation/test_migrations.py::test_packaged_versions_are_contiguous_and_reserved_once`
keeps it that way. A first `runner.py up` on an empty Cloud Spanner database applies them in
order. D4 (secret sync add-on), D8 (Autopilot, Regular channel) and D9 (legacy retirement) keep
the defaults in section 0. If any row above is empty, stop.

### Preamble: save as `~/brandme-sandbox-deploy/env.sh`

The file holds no secret. Every later block starts with `set -euo pipefail` and sources it.
Run each block as its own script (`bash step.sh`), or paste it into a fresh `bash --norc`
sub-shell, so that a failing command ends that step and not your login shell. Steps pass
values to later steps through files in `$WORK` (the bucket name, for example). For a new
project (D1 = dedicated), run C-1's new-project block first, because the `PROJECT_NUMBER`
lookup below needs the project to exist.

```bash
set -euo pipefail
export PROJECT_ID=REPLACE_ME            # D1
export REGION=us-east1 CLUSTER=brandme-cluster NS=brandme MODE=sandbox
export REPO=brandmeonline/Brand-Me-Labs REPO_ID=1083300600   # gh api repos/$REPO --jq .id (A5)
export WORK="$HOME/brandme-sandbox-deploy"   # operator files (bucket name, pins, public JWK); never secrets
[[ "$PROJECT_ID" != REPLACE_ME* && "$PROJECT_ID" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || { echo "PROJECT_ID is unset or REPLACE_ME (D1)" >&2; exit 1; }
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
[[ "$PROJECT_NUMBER" =~ ^[0-9]+$ ]] || { echo "PROJECT_NUMBER lookup failed for $PROJECT_ID" >&2; exit 1; }
export PROJECT_NUMBER
mkdir -p "$WORK"; chmod 700 "$WORK"
sa() { echo "$1@${PROJECT_ID}.iam.gserviceaccount.com"; }
```

Create the directory before saving the file into it: `mkdir -p -m 700 ~/brandme-sandbox-deploy`.

**C-1 [read-only check] Who you are and what the project is.**
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
gcloud auth list --filter=status:ACTIVE --format='value(account)'
gcloud projects describe "$PROJECT_ID" --format='value(projectId,projectNumber,lifecycleState)'
gcloud projects get-iam-policy "$PROJECT_ID" --flatten=bindings --format='table(bindings.role,bindings.members)'
```
New project branch (D1 = dedicated) **[creates resource]**:
```bash
set -euo pipefail
PROJECT_ID=REPLACE_ME     # the same value as in env.sh
[[ "$PROJECT_ID" != REPLACE_ME* ]] || { echo "set PROJECT_ID" >&2; exit 1; }
gcloud projects create "$PROJECT_ID" --name="Brand.Me sandbox"            # optionally --folder / --organization
gcloud billing accounts list --filter=open=true --format='value(name,displayName)'
BILLING=REPLACE_ME_BILLING_ACCOUNT; [[ "$BILLING" != REPLACE_ME* ]]
gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING"
gcloud resource-manager org-policies enable-enforce iam.disableServiceAccountKeyCreation --project "$PROJECT_ID"
```
From here on, `env.sh` resolves `PROJECT_NUMBER`. **Verify:**
`gcloud billing projects describe "$PROJECT_ID" --format='value(billingEnabled)'` prints `True`.
**Undo:** `gcloud projects delete "$PROJECT_ID"`. The project stays recoverable for 30 days.

**C-2 [read-only check] Which service account backs `GCP_SA_KEY`, and what can it do.**
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
gcloud iam service-accounts list --project "$PROJECT_ID" --format='value(email)'
SA=REPLACE_ME_SA_FROM_LIST; [[ "$SA" != REPLACE_ME* ]]
gcloud iam service-accounts keys list --iam-account="$SA" --managed-by=user --format='table(name.basename(),validAfterTime,disabled)'
gcloud projects get-iam-policy "$PROJECT_ID" --flatten=bindings --filter="bindings.members:serviceAccount:$SA" --format='value(bindings.role)'
printf '%s\n' "$SA" > "$WORK/gcp-sa-key-account.txt"
```

**C-3 [read-only check] Does the cluster exist, and how is it configured?**
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
gcloud container clusters list --project "$PROJECT_ID"
gcloud container clusters describe "$CLUSTER" --region "$REGION" --project "$PROJECT_ID" \
  --format='yaml(autopilot.enabled,releaseChannel.channel,currentMasterVersion,workloadIdentityConfig.workloadPool,networkConfig.datapathProvider,privateClusterConfig.enablePrivateNodes,secretManagerConfig)'
```
Need: Workload Identity pool `$PROJECT_ID.svc.id.goog`; network policy enforcement
(Autopilot and Dataplane V2 always enforce); version ≥ 1.33 (the chart's `kubeVersion`, and
the secret sync add-on). If the cluster does not exist, C-6 creates it.

**C-4 [read-only check] Registry and images.**
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
gcloud artifacts repositories list --project "$PROJECT_ID" --format='table(name,format,location)'
gcloud artifacts docker images list "gcr.io/$PROJECT_ID/brandme-core" --include-tags --limit 5
```

**C-5 [creates resource] Enable APIs** (identitytoolkit is for D5, C-11).
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
apis="container.googleapis.com artifactregistry.googleapis.com spanner.googleapis.com pubsub.googleapis.com
  storage.googleapis.com secretmanager.googleapis.com iam.googleapis.com iamcredentials.googleapis.com
  sts.googleapis.com cloudresourcemanager.googleapis.com identitytoolkit.googleapis.com"
# shellcheck disable=SC2086
gcloud services enable $apis --project "$PROJECT_ID"
enabled=$(gcloud services list --enabled --project "$PROJECT_ID" --format='value(config.name)')
for a in $apis; do grep -qx "$a" <<<"$enabled" || { echo "not enabled: $a" >&2; exit 1; }; done; echo "all APIs enabled"
```
**Undo:** `gcloud services disable <api> --project "$PROJECT_ID"`. Only do this in a dedicated
project; in a shared one, other workloads may depend on the API.

**C-6 [creates resource] Cluster, only if C-3 found none (D8).**
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
gcloud container clusters create-auto "$CLUSTER" --project "$PROJECT_ID" --region "$REGION" \
  --release-channel=regular --enable-secret-sync
# existing cluster instead:
#   gcloud container clusters update "$CLUSTER" --location "$REGION" --project "$PROJECT_ID" --enable-secret-sync
gcloud container clusters get-credentials "$CLUSTER" --region "$REGION" --project "$PROJECT_ID"
```
**Verify:** run the C-3 describe again. It must show `autopilot.enabled: true`, the
Workload Identity pool and secret sync enabled.
**Undo:** `gcloud container clusters delete "$CLUSTER" --region "$REGION" --project "$PROJECT_ID"`.
The `--enable-secret-sync` flag is from docs.cloud.google.com/secret-manager/docs/sync-k8-secrets
(read 2026-10-23, GKE ≥ 1.33). A Standard cluster also needs `--workload-pool="$PROJECT_ID.svc.id.goog"`
and network policy enforcement. Private nodes need Cloud NAT for the chain's Blockfrost calls.

**C-7 [creates resource] Namespace with Pod Security "restricted".**
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
kubectl create namespace "$NS"
kubectl label namespace "$NS" pod-security.kubernetes.io/enforce=restricted pod-security.kubernetes.io/enforce-version=latest
kubectl get namespace "$NS" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}{"\n"}'   # restricted
```
**Undo:** `kubectl delete namespace "$NS"`. This deletes everything in it. The release name and
the namespace must both be `brandme`, because the KSA names are `brandme-<component>`.

**C-8 [creates resource] Spanner (GoogleSQL).** Do **not** run migrations by hand: the chart's
hook Job runs `runner.py up` at C-20.
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
gcloud spanner instances create brandme-sandbox --project "$PROJECT_ID" --config=regional-us-east1 \
  --processing-units=100 --description="Brand.Me sandbox"
gcloud spanner databases create brandme-sandbox --instance=brandme-sandbox --project "$PROJECT_ID" \
  --database-dialect=GOOGLE_STANDARD_SQL
gcloud spanner databases describe brandme-sandbox --instance=brandme-sandbox --project "$PROJECT_ID" \
  --format='value(state,databaseDialect)'                           # READY  GOOGLE_STANDARD_SQL
```
**Undo:** `gcloud spanner databases delete brandme-sandbox --instance=brandme-sandbox --project "$PROJECT_ID"`,
then `gcloud spanner instances delete brandme-sandbox --project "$PROJECT_ID"`. Both are irreversible.

**C-9 [creates resource] Pub/Sub topics.** Names must start with `brandme-sandbox-`, and
retention must be ≥ 24 h (`brandme_core/events/pubsub.py:94-103`).
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
for t in public member-private restricted; do
  gcloud pubsub topics create "brandme-sandbox-$t" --project "$PROJECT_ID" --message-retention-duration=1d
  gcloud pubsub topics describe "brandme-sandbox-$t" --project "$PROJECT_ID" --format=json \
    | jq -e '(.messageRetentionDuration | rtrimstr("s") | tonumber) >= 86400' >/dev/null && echo "brandme-sandbox-$t retention ok"
done
```
**Undo:** `gcloud pubsub topics delete brandme-sandbox-{public,member-private,restricted} --project "$PROJECT_ID"`.

**C-10 [creates resource] Export bucket with the exact policy `PrivateStore.check` enforces** (`brandme_core/privacy_exports/storage.py:100-112`).
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
BUCKET="brandme-sandbox-exports-$(openssl rand -hex 3)"; printf '%s\n' "$BUCKET" > "$WORK/bucket.txt"
gcloud storage buckets create "gs://$BUCKET" --project "$PROJECT_ID" --location="$REGION" \
  --uniform-bucket-level-access --public-access-prevention --soft-delete-duration=0
printf '%s\n' '{"lifecycle":{"rule":[{"action":{"type":"Delete"},"condition":{"age":1}}]}}' > "$WORK/lifecycle.json"
gcloud storage buckets update "gs://$BUCKET" --lifecycle-file="$WORK/lifecycle.json"
# Verify: the JSON API fields storage.py:100-112 reads, with the same rules.
gcloud storage buckets describe "gs://$BUCKET" --project "$PROJECT_ID" --raw --format=json | jq -e --arg b "$BUCKET" '
  .name == $b
  and .iamConfiguration.publicAccessPrevention == "enforced"
  and .iamConfiguration.uniformBucketLevelAccess.enabled == true
  and ((.versioning.enabled // false) == false)
  and ((.softDeletePolicy.retentionDurationSeconds // "") | tostring) == "0"
  and .retentionPolicy == null and ((.defaultEventBasedHold // false) == false)
  and ((.objectRetention.mode // "") != "Enabled")
  and any(.lifecycle.rule[]?; . == {"action":{"type":"Delete"},"condition":{"age":1}})' >/dev/null \
  && echo "gs://$BUCKET matches PrivateStore.check"
```
**Undo:** `gcloud storage rm --recursive "gs://$(cat "$WORK/bucket.txt")"`. That deletes the
bucket and its objects. The bucket name goes into the values PR (C-19).

**C-11 [creates resource] OIDC issuer for the gateway (D5).** The recommended default is Google
Identity Platform (spec `03-architecture-data-api.md` item 9). Enabling Identity Platform the
first time is a console step: Identity Platform → Enable, then add a sign-in provider. The
values below are the ones Google documents for Identity Platform ID tokens. They were **not
verified here**.
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
ISSUER="https://securetoken.google.com/$PROJECT_ID"
AUDIENCE="$PROJECT_ID"
JWKS="https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
curl -fsS "$JWKS" | jq -e '.keys | length > 0' >/dev/null && echo "JWKS reachable"
printf 'issuer=%s\naudience=%s\njwksUri=%s\n' "$ISSUER" "$AUDIENCE" "$JWKS" > "$WORK/oidc.txt"
```
The values PR (C-19) needs all three. `gateway.oidc.jwksUri` must be set, because the gateway
otherwise derives `<issuer>/.well-known/jwks.json` (`brandme-gateway/src/middleware/session.ts:71`),
which this issuer does not serve. ID tokens are RS256, which the default `OIDC_ALGORITHMS`
allows (`src/config/index.ts:81`). **Undo:** disable the provider in the console. A different
D5 answer replaces this step, keeping the same three outputs.

**C-12 [external; owner midnight-rights] Preprod rights contract address (D7).** read-api and
exports refuse to start without a 64-hex contract address (`values-sandbox.yaml:27`). **No
command in this repository deploys the contract.** `brandme-chain/package.json` has only
`test:midnight:local`, `test:midnight:network`, `test:midnight:preprod` and
`midnight:local-network`. The midnight-rights lane deploys `brandme_rights` to Preprod with its
own tooling and hands over the address. The founder records it:
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
ADDR=REPLACE_ME_64_HEX; [[ "$ADDR" =~ ^[0-9a-f]{64}$ ]] || { echo "not 64 lowercase hex" >&2; exit 1; }
printf '%s\n' "$ADDR" > "$WORK/preprod-contract-address.txt"
```
**Verify after C-20:** the chain capability (C-21) is not `unavailable`. **Undo:** none
(on-chain). A new address replaces it through the values PR.

**C-13 [creates resource] Service accounts, custom roles, resource grants, Workload Identity
and the two GitHub WIF pools: one path, the script.** `scripts/provision/gcp-dev-identities.sh`
is the only maintained path, so do not mix it with hand-written grants. It creates one keyless
GSA per workload and the least-privilege custom roles (`brandmeSpannerDataReadWrite` includes
`beginPartitionedDmlTransaction`, which the retention job needs). It grants on the resources
only and binds each KSA `brandme/brandme-<component>` to its GSA. It also creates the
`github-deploy` pool and the separate `github-push` pool for the image pusher (G24). The
deploy pool's condition pins the immutable repository id, the repository name, `v*` tags and
the Environment `sandbox` (`scripts/provision/gcp-dev-identities.sh:412-414`); the push
pool's condition pins `main` and `v*` tags (`:416`). First, a dry run, which executes nothing:
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
BUCKET=$(cat "$WORK/bucket.txt")
flags=(--project "$PROJECT_ID" --export-bucket "$BUCKET" --github-repo-id "$REPO_ID")
# D1 = lux-realestate-app also needs: flags+=(--i-understand-shared-project)
bash scripts/provision/gcp-dev-identities.sh "${flags[@]}" > "$WORK/identities-plan.txt"
# The two KSAs added this round must be in the plan with their fixed GSAs; stop if either is missing.
grep -F "serviceAccount:$PROJECT_ID.svc.id.goog[$NS/brandme-events-retention]" "$WORK/identities-plan.txt" | grep -q "bm-sbx-fnd-retention@" \
  || { echo "plan lacks bm-sbx-fnd-retention -> brandme-events-retention: update the checkout" >&2; exit 1; }
grep -F "serviceAccount:$PROJECT_ID.svc.id.goog[$NS/brandme-consumer-domains-api]" "$WORK/identities-plan.txt" | grep -q "bm-sbx-dom-api@" \
  || { echo "plan lacks bm-sbx-dom-api -> brandme-consumer-domains-api" >&2; exit 1; }
```
Read `$WORK/identities-plan.txt`, then apply it. The script asks you to type the project id.
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
BUCKET=$(cat "$WORK/bucket.txt")
bash scripts/provision/gcp-dev-identities.sh --project "$PROJECT_ID" --export-bucket "$BUCKET" --github-repo-id "$REPO_ID" --apply
```
The fixed identities that other lanes rely on:

| KSA (`brandme/…`) | GSA | Grants (from the script) |
|---|---|---|
| `brandme-events-retention` (hourly CronJob) | `bm-sbx-fnd-retention` | `brandmeSpannerDataReadWrite` on database `brandme-sandbox` only; **no Pub/Sub** |
| `brandme-consumer-domains-api` | `bm-sbx-dom-api` (`gcp-dev-identities.sh:309`) | `brandmeSpannerDataReadWrite` on the database; media bucket only with `--dom-media-bucket` (MediaService is unmounted, so leave it out) |
| `brandme-gateway`, `-chain`, `-read-api`, `-exports-api`, `-exports-worker`, `-events-worker`, `-migrations` | `bm-sbx-fnd-gateway`, `bm-sbx-rts-chain`, `bm-sbx-rts-read-api`, `bm-sbx-rts-export-api`, `bm-sbx-rts-export-wkr`, `bm-sbx-fnd-outbox`, `bm-sbx-fnd-migrator` | as in `lane-service-accounts.md` |

**Verify** (Workload Identity for the two new KSAs, and retention's least privilege):
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
for pair in "bm-sbx-fnd-retention brandme-events-retention" "bm-sbx-dom-api brandme-consumer-domains-api"; do
  read -r gsa ksa <<<"$pair"
  gcloud iam service-accounts get-iam-policy "$(sa "$gsa")" --project "$PROJECT_ID" --format=json | jq -e --arg m "serviceAccount:$PROJECT_ID.svc.id.goog[$NS/$ksa]" \
    '[.bindings[] | select(.role == "roles/iam.workloadIdentityUser") | .members[]] | index($m) != null' >/dev/null && echo "$ksa -> $gsa bound"
done
gcloud spanner databases get-iam-policy brandme-sandbox --instance=brandme-sandbox --project "$PROJECT_ID" --format=json \
  | jq -e --arg m "serviceAccount:$(sa bm-sbx-fnd-retention)" '[.bindings[] | select(.members | index($m)) | .role] == ["projects/'"$PROJECT_ID"'/roles/brandmeSpannerDataReadWrite"]' >/dev/null \
  && echo "retention: Spanner data read/write on brandme-sandbox only"
for t in public member-private restricted; do
  pol=$(gcloud pubsub topics get-iam-policy "brandme-sandbox-$t" --project "$PROJECT_ID" --format=json)
  if grep -q "bm-sbx-fnd-retention@" <<<"$pol"; then echo "retention has a grant on $t" >&2; exit 1; fi
done; echo "retention: no Pub/Sub grant"
gcloud iam workload-identity-pools providers describe brandme-deploy --workload-identity-pool=github-deploy --location=global --project "$PROJECT_ID" --format='value(attributeCondition)'
```
**Undo:** `gcloud iam service-accounts delete "$(sa <id>)" --project "$PROJECT_ID"` for each
GSA; `gcloud iam roles delete <role> --project "$PROJECT_ID"` for each custom role;
`gcloud iam workload-identity-pools delete github-deploy --location=global --project "$PROJECT_ID"`;
and the same for `github-push`.

**C-14 [creates resource] Secret Manager: six secrets.** IDs are `brandme-<mode>-<lane>-<purpose>`.
The four service tokens are independent random values, all from one generator (the same one
as the rotation runbook, 5.1). The Blockfrost Preprod project id comes from the provider (D7).
The domain assertion key is a fresh P-256 key; only its public half leaves the machine.
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
for id in rights-service-token privacy-service-token privacy-export-service-token chain-service-token; do
  gcloud secrets create "brandme-sandbox-rts-$id" --project "$PROJECT_ID" --replication-policy=automatic \
    --labels=lane=rts,mode=sandbox,rotation-days=90
  python3 -c 'import secrets; print(secrets.token_urlsafe(48), end="")' \
    | gcloud secrets versions add "brandme-sandbox-rts-$id" --project "$PROJECT_ID" --data-file=-
done
gcloud secrets create brandme-sandbox-rts-midnight-blockfrost-project-id --project "$PROJECT_ID" \
  --replication-policy=automatic --labels=lane=rts,mode=sandbox
read -rs BF; [[ "$BF" =~ ^nightpreprod[A-Za-z0-9_-]{8,}$ ]] || { unset BF; echo "not a Preprod project id" >&2; exit 1; }
printf '%s' "$BF" | gcloud secrets versions add brandme-sandbox-rts-midnight-blockfrost-project-id --project "$PROJECT_ID" --data-file=-; unset BF
gcloud secrets create brandme-sandbox-dom-domain-assertion-key --project "$PROJECT_ID" \
  --replication-policy=automatic --labels=lane=dom,mode=sandbox,rotation-days=180
KID="dom-sandbox-$(date -u +%Y%m%d%H%M)"; printf '%s\n' "$KID" > "$WORK/domain-assertion-kid.txt"
umask 077; tmp=$(mktemp -d); trap 'shred -u "$tmp"/key.pem 2>/dev/null; rm -rf "$tmp"' EXIT
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$tmp/key.pem"
gcloud secrets versions add brandme-sandbox-dom-domain-assertion-key --project "$PROJECT_ID" --data-file="$tmp/key.pem"
node -e 'const c=require("crypto"),f=require("fs");const j=c.createPublicKey(f.readFileSync(process.argv[1])).export({format:"jwk"});
  if(j.d)process.exit(3);process.stdout.write(JSON.stringify({keys:[{...j,kid:process.argv[2],alg:"ES256",use:"sig"}]}))' \
  "$tmp/key.pem" "$KID" > "$WORK/domain-assertion-jwks.json"      # public keys only; goes into the values PR
```
**Verify** (names, one enabled version each, and the tokens pairwise distinct; no value printed):
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
gcloud secrets list --project "$PROJECT_ID" --filter='labels.mode=sandbox' --format='value(name.basename())' | sort
for s in $(gcloud secrets list --project "$PROJECT_ID" --filter='labels.mode=sandbox' --format='value(name.basename())'); do
  n=$(gcloud secrets versions list "$s" --project "$PROJECT_ID" --filter=state:ENABLED --format='value(name)' | wc -l)
  [ "$n" -eq 1 ] && echo "$s: 1 enabled version" || { echo "$s: $n enabled versions" >&2; exit 1; }
done
dups=$(for id in rights-service-token privacy-service-token privacy-export-service-token chain-service-token; do
  gcloud secrets versions access 1 --secret "brandme-sandbox-rts-$id" --project "$PROJECT_ID" | sha256sum | cut -d' ' -f1
done | sort | uniq -d | wc -l)
[ "$dups" -eq 0 ] && echo "four service tokens pairwise distinct" || { echo "token values repeat" >&2; exit 1; }
```
**Undo:** `gcloud secrets delete <id> --project "$PROJECT_ID"` for each of the six. Rotation
of all six is in [credential-rotation.md](../runbooks/credential-rotation.md).

**C-15 [creates resource] Deliver the six secrets into the namespace (D4: GKE secret sync).**
One sync identity reads only these six secrets. Pods never read Secret Manager.
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
ids="brandme-sandbox-rts-rights-service-token brandme-sandbox-rts-privacy-service-token
  brandme-sandbox-rts-privacy-export-service-token brandme-sandbox-rts-chain-service-token
  brandme-sandbox-rts-midnight-blockfrost-project-id brandme-sandbox-dom-domain-assertion-key"
kubectl -n "$NS" create serviceaccount brandme-secret-sync
for id in $ids; do
  gcloud secrets add-iam-policy-binding "$id" --project "$PROJECT_ID" --role=roles/secretmanager.secretAccessor \
    --member="principal://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$PROJECT_ID.svc.id.goog/subject/ns/$NS/sa/brandme-secret-sync"
done
# Explicit versions, never versions/latest: a new version is inert until its pin changes (runbook section 4).
{
  printf 'apiVersion: secrets-store.csi.x-k8s.io/v1\nkind: SecretProviderClass\nmetadata: {name: brandme-sandbox-rts, namespace: %s}\n' "$NS"
  printf 'spec:\n  provider: gke\n  parameters:\n    secrets: |\n'
  for id in $ids; do
    printf '      - resourceName: "projects/%s/secrets/%s/versions/1"\n        path: "%s"\n' "$PROJECT_ID" "$id" "$id"
  done
  for id in $ids; do   # one SecretSync per Kubernetes Secret; metadata.name becomes the Secret name, key "value"
    printf -- '---\napiVersion: secret-sync.gke.io/v1\nkind: SecretSync\nmetadata: {name: %s, namespace: %s}\n' "$id" "$NS"
    printf 'spec:\n  serviceAccountName: brandme-secret-sync\n  secretProviderClassName: brandme-sandbox-rts\n'
    printf '  secretObject:\n    type: Opaque\n    data:\n      - sourcePath: "%s"\n        targetKey: "value"\n' "$id"
  done
} > "$WORK/secret-sync.yaml"
kubectl apply -f "$WORK/secret-sync.yaml"
```
The rendered file holds six SecretSyncs, written out in full in `$WORK/secret-sync.yaml`, plus
one SecretProviderClass. It names resources only, never values. Its shape was copied from the
Google page cited at C-6 and was **not schema-validated here**: the CRDs exist only on a
cluster with the add-on. The chart already references the first five Secret names
(`values-sandbox.yaml:29-34`). The consumer-domains lane's chart change must reference
`brandme-sandbox-dom-domain-assertion-key` (key `value`) for the gateway's
`CONSUMER_DOMAIN_ASSERTION_KEY`.

**Verify (key presence, without printing values):** each Kubernetes Secret exists, has a
non-empty `value`, and matches version 1 in Secret Manager.
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
ids="brandme-sandbox-rts-rights-service-token brandme-sandbox-rts-privacy-service-token
  brandme-sandbox-rts-privacy-export-service-token brandme-sandbox-rts-chain-service-token
  brandme-sandbox-rts-midnight-blockfrost-project-id brandme-sandbox-dom-domain-assertion-key"
for id in $ids; do
  for _ in $(seq 1 30); do kubectl -n "$NS" get secret "$id" >/dev/null 2>&1 && break; sleep 10; done
  bytes=$(kubectl -n "$NS" get secret "$id" -o jsonpath='{.data.value}' | base64 -d | wc -c)
  [ "$(kubectl -n "$NS" get secret "$id" -o jsonpath='{.data.value}' | base64 -d | sha256sum)" = \
    "$(gcloud secrets versions access 1 --secret "$id" --project "$PROJECT_ID" | sha256sum)" ] \
    && echo "$id: present, $bytes bytes, matches version 1" || { echo "$id: missing or differs" >&2; exit 1; }
done
```
**Undo:** `kubectl delete -f "$WORK/secret-sync.yaml"` and
`kubectl -n "$NS" delete serviceaccount brandme-secret-sync`. Then remove the six IAM bindings
with `gcloud secrets remove-iam-policy-binding`, using the same member and role. The fallback
without the add-on gives no rotation sync, and the value never touches disk:
`gcloud secrets versions access 1 --secret=<id> --project "$PROJECT_ID" | kubectl -n "$NS" create secret generic <id> --from-file=value=/dev/stdin`.

**C-16 [creates resource] Deployer rights inside the namespace only.** C-13 created the deployer
GSA, its `container.clusterViewer` grant and the `github-deploy` pool. Kubernetes rights are
namespaced:
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
kubectl create rolebinding brandme-deployer -n "$NS" --clusterrole=admin --user="$(sa bm-sbx-fnd-deployer)"
kubectl auth can-i create deployments -n "$NS" --as="$(sa bm-sbx-fnd-deployer)"      # yes
kubectl auth can-i create jobs -n "$NS" --as="$(sa bm-sbx-fnd-deployer)"             # yes (retention pass)
kubectl auth can-i create deployments -n default --as="$(sa bm-sbx-fnd-deployer)" || true   # no
```
**Undo:** `kubectl -n "$NS" delete rolebinding brandme-deployer`. The namespaced `admin` role
covers what helm and the deploy job need: Deployments, Services, ServiceAccounts, Jobs,
CronJobs, NetworkPolicies, PDBs, release Secrets, `pods/exec` for the checks, and
`kubectl create job --from=cronjob` for the retention pass. If ingress is enabled later, also
grant the `cloud.google.com` and `networking.gke.io` resources (BackendConfig,
ManagedCertificate, FrontendConfig).

**C-17 [creates resource] GitHub: environment, tag ruleset, repository variables.**
- Settings → Environments → New environment **`sandbox`**: required reviewer = the founder;
  "Deployment branches and tags" → selected → add tag rule `v*`. With a single maintainer, leave
  "Prevent self-review" off, or the founder cannot approve their own tag.
- Settings → Rules → Rulesets → New **tag** ruleset "release tags", target `refs/tags/v*`,
  enforcement Active, rules: restrict creations, updates and deletions; bypass list:
  repository admins only.
- Repository variables (none of these is a secret):
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
gh variable set BM_GCP_PROJECT_ID   --repo "$REPO" --body "$PROJECT_ID"
gh variable set BM_GCP_REGION       --repo "$REPO" --body "$REGION"
gh variable set BM_GKE_CLUSTER      --repo "$REPO" --body "$CLUSTER"
gh variable set BM_GCP_WIF_PROVIDER --repo "$REPO" --body "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-deploy/providers/brandme-deploy"
gh variable set BM_GCP_DEPLOYER_SA  --repo "$REPO" --body "$(sa bm-sbx-fnd-deployer)"
gh variable set BM_DEPLOY_ENABLED   --repo "$REPO" --body false
gh variable list --repo "$REPO"
gh api "repos/$REPO/environments/sandbox" --jq '.name, (.protection_rules | map(.type) | join(","))'
```
**Undo:** `gh variable delete <NAME> --repo "$REPO"`; delete the environment and the ruleset in
Settings.

**C-18 [read-only check, then creates resource if needed] Nodes can pull the images.**
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
gcloud container clusters describe "$CLUSTER" --region "$REGION" --project "$PROJECT_ID" \
  --format='value(autopilot.enabled,autoscaling.autoprovisioningNodePoolDefaults.serviceAccount)'
LOCATION=REPLACE_ME_LOCATION_FROM_C4; [[ "$LOCATION" != REPLACE_ME* ]]
gcloud artifacts repositories get-iam-policy gcr.io --location="$LOCATION" --project "$PROJECT_ID"
```
Autopilot nodes use the cluster's `autoscaling.autoprovisioningNodePoolDefaults.serviceAccount`.
Standard clusters use each node pool's `nodeConfig.serviceAccount`. If the field is empty, the
nodes use the Compute Engine default account, `$PROJECT_NUMBER-compute@developer.gserviceaccount.com`.
Grant `roles/artifactregistry.reader` on the repository to that account only if it is missing,
or if the images live in another project than the cluster (D1).

**C-19 [repository change] The values PR.** It must merge before the tag. While any
`REPLACE_ME` remains in `brandme-infra/helm/brandme/values-sandbox.yaml`, the deploy job's
render fails by design (`templates/validate.yaml`). `scripts/validate-helm.sh` asserts that
too.

| Line on this head | Key | Value from |
|---|---|---|
| `:16` | `gcp.projectId` | may stay: the deploy job passes `--set-string gcp.projectId=${{ vars.BM_GCP_PROJECT_ID }}` (`ci-cd.yml:447`) |
| `:27` | `midnight.contractAddress` | `$WORK/preprod-contract-address.txt` (C-12) |
| `:40-41` | `gateway.oidc.issuer`, `gateway.oidc.audience` | `$WORK/oidc.txt` (C-11) |
| new | `gateway.oidc.jwksUri` | `$WORK/oidc.txt` (C-11) |
| `:44` | `gateway.publicOrigins` | D6 (https), even with ingress off |
| `:65` | `privacyExports.bucket` | `$WORK/bucket.txt` (C-10) |
| `:77-78` | `eventsRetention.gcpServiceAccount` | `bm-sbx-fnd-retention`. This head still says `bm-sbx-fnd-outbox`, which has Pub/Sub grants the job does not need |
| consumer-domains keys | domain service on, its GSA `bm-sbx-dom-api`, gateway `CONSUMER_DOMAIN_ASSERTION_KID` = `$WORK/domain-assertion-kid.txt`, domain service `CONSUMER_DOMAIN_ASSERTION_JWKS` = `$WORK/domain-assertion-jwks.json` (public) | key names as the consumer-domains lane's chart change defines them |
| `:80-83` | the comment that calls D3 a blocker | delete: D3 is resolved (C-0) |

**Verify** on the PR branch:
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
! grep -vE '^[[:space:]]*#' brandme-infra/helm/brandme/values-sandbox.yaml | grep -q REPLACE_ME
BRANDME_PYTHON="$(command -v python3)" bash scripts/validate-helm.sh   # renders the committed sandbox values once none is left
```
**Undo:** revert the PR.

**C-20 [creates resource] First deploy.**

This step deploys real infrastructure, so start with a backup point (rollback R-1). On the
empty database it records the known-empty state; take one before every later tag that adds a
migration.
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
TAG=v0.1.0
gcloud spanner backups create "pre-${TAG//./-}" --instance=brandme-sandbox --database=brandme-sandbox \
  --retention-period=7d --project "$PROJECT_ID"
gcloud spanner backups describe "pre-${TAG//./-}" --instance=brandme-sandbox --project "$PROJECT_ID" --format='value(state)'   # READY
```
Next, tag the commit whose `main` run is green, with the values PR merged:
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
TAG=v0.1.0
git fetch origin main --tags && git switch --detach origin/main
sha=$(git rev-parse HEAD)
[ "$(gh run list --repo "$REPO" --workflow ci-cd.yml --commit "$sha" --json conclusion --jq 'map(select(.conclusion=="success")) | length')" -ge 1 ] \
  || { echo "no green ci-cd.yml run for $sha" >&2; exit 1; }
gh variable set BM_DEPLOY_ENABLED --repo "$REPO" --body true
git tag -s "$TAG" -m "sandbox $TAG" "$sha"      # -a instead of -s if no signing key is configured
git push origin "$TAG"
sleep 15; run=$(gh run list --repo "$REPO" --workflow ci-cd.yml --commit "$sha" --event push --limit 1 --json databaseId --jq '.[0].databaseId')
echo "approve the 'sandbox' environment on: https://github.com/$REPO/actions/runs/$run"
gh run watch "$run" --repo "$REPO" --exit-status
```
The run pauses at the `deploy` job until the founder approves the `sandbox` environment, on
the run page or under Settings → Environments. The job then runs these steps in order:
- validate the chart offline;
- render the exact release by digest;
- authenticate with WIF;
- `helm upgrade --install --wait --wait-for-jobs`, with migrations first as the pre-install hook;
- rollout status and the three `--check` commands;
- one retention pass from `cronjob/brandme-events-retention`. A failed pass fails the deploy
  (`ci-cd.yml:496-511`).

**Undo:** `gh variable set BM_DEPLOY_ENABLED --repo "$REPO" --body false` stops further tags,
then roll back (R-3). Deleting the tag needs the ruleset bypass: `git push origin ":refs/tags/$TAG"`.

**C-21 [read-only check] After the deploy.**
```bash
set -euo pipefail
. ~/brandme-sandbox-deploy/env.sh
kubectl -n "$NS" get deploy,pods,jobs,cronjobs
kubectl -n "$NS" logs job/brandme-migrations --tail=60          # hook Job, kept until the next release
for d in gateway chain read-api exports-api exports-worker events-worker; do
  kubectl -n "$NS" rollout status "deploy/brandme-$d" --timeout=2m
done
kubectl -n "$NS" exec deploy/brandme-read-api -- python -m brandme_core.read_api --check
kubectl -n "$NS" exec deploy/brandme-exports-api -- python -m brandme_core.privacy_exports --check
kubectl -n "$NS" exec deploy/brandme-exports-worker -- python -m brandme_core.privacy_exports --check
kubectl -n "$NS" exec deploy/brandme-events-worker -- python -m brandme_core.events.worker --check
kubectl label --dry-run=server --overwrite namespace "$NS" pod-security.kubernetes.io/enforce=restricted   # no warnings
# Gateway health and chain capability over port-forwards (nothing is exposed publicly).
kubectl -n "$NS" port-forward deploy/brandme-gateway 18081:3001 >/dev/null 2>&1 & pf1=$!
kubectl -n "$NS" port-forward deploy/brandme-chain 18082:3001 >/dev/null 2>&1 & pf2=$!
trap 'kill "$pf1" "$pf2" 2>/dev/null' EXIT; sleep 3
curl -fsS -o /dev/null -w 'gateway /healthz %{http_code}\n' http://127.0.0.1:18081/healthz
curl -fsS http://127.0.0.1:18082/midnight/capability | jq -c '{status, network}'      # expect network "preprod", status not "unavailable"
curl -fsS http://127.0.0.1:18081/api/v1/chain/capability | jq -c '{status, badge}'    # the same view through the gateway
# One more retention pass, as the operator.
job="brandme-events-retention-manual-$(date -u +%Y%m%d%H%M)"
kubectl -n "$NS" create job "$job" --from=cronjob/brandme-events-retention
kubectl -n "$NS" wait --for=condition=complete "job/$job" --timeout=10m
kubectl -n "$NS" logs "job/$job" --tail=20
```
`/api/v1/system/health` is not a cluster check: it also calls the legacy brain service, which
the chart does not deploy, so it reports `degraded` (`brandme-gateway/src/routes/v1/index.ts:67-81`).
Once the consumer-domains chart change is deployed, also run
`kubectl -n "$NS" rollout status deploy/brandme-consumer-domains-api --timeout=2m`.

**C-22 [creates resource] Retire the JSON key.** Do this once image publishing also uses WIF
(G24). The full sequence is in [credential-rotation.md](../runbooks/credential-rotation.md) 5.5:
disable the key, wait for a green publishing run, delete the key, then delete the `GCP_SA_KEY`
secret.

**C-23 [creates resource] Optional public edge: not for the first deploy (D6, G8).** Run
`gcloud compute addresses create brandme-sandbox-edge --global --project "$PROJECT_ID"`, add an
A record for the chosen host(s), then set `ingress.*` and `gateway.trustProxy` in
`values-sandbox.yaml`. The chart refuses ingress without `trustProxy`.

### Rollback and teardown

- **R-1 Backups before migrations.** Spanner migrations are forward-only. The runner has `up`,
  `status`, `verify` and `repair` (`brandme-data/spanner/migrations/runner.py:282-288`), but no
  down. So take the C-20 backup before every release that adds a migration. To restore,
  create a new database from the backup:
  `gcloud spanner databases restore --source-backup=pre-<tag> --source-instance=brandme-sandbox --destination-instance=brandme-sandbox --destination-database=brandme-sandbox-r1 --project "$PROJECT_ID"`.
  Then point `spanner.databaseId` at it in a values PR. A restore cannot overwrite the live
  database.
- **R-2 A bad migration** is fixed forward with the next number (V016 onward, registry in
  `brandme-data/spanner/migrations/README.md`), or by R-1. A failed DDL batch leaves an
  `applying` row; inspect it, then run `runner.py repair --version N`. Never edit an applied
  file: the checksum ledger refuses that.
- **R-3 Application rollback:** `helm -n brandme history brandme`, then
  `helm -n brandme rollback brandme <REVISION> --wait --timeout 10m`. Rollback runs no
  pre-upgrade hook, so the schema stays at the newer version. The older images must accept it:
  each service asserts its supported range at startup and refuses otherwise. If they refuse,
  use R-1.
- **R-4 Teardown, in this order:**
  1. `helm -n brandme uninstall brandme`.
  2. `kubectl -n brandme delete job/brandme-migrations serviceaccount/brandme-migrations networkpolicy/brandme-migrations-egress --ignore-not-found`.
     These are hook resources, which `helm uninstall` keeps (`templates/migrations-job.yaml:10-11`).
  3. Delete the retention Jobs from `C-20`/`C-21`.
  4. Run the C-15 undo, then `kubectl delete namespace brandme`.
  5. Then, in reverse order of creation, run the undo of C-14, C-13, C-10, C-9 and C-8,
     including `gcloud spanner backups delete pre-<tag> --instance=brandme-sandbox`.
  6. Finally C-6, if the cluster was created for this deploy, and C-17's variables.

  Verify each undo with the describe command of the matching step: it must report "not found".

### Cost note

These are what keeps billing while the sandbox exists. Prices were not checked here; use
cloud.google.com/spanner/pricing and cloud.google.com/kubernetes-engine/pricing.

- **Spanner** `regional-us-east1`, 100 processing units. It bills per processing-unit hour from
  C-8 until C-8's undo, even when idle, plus storage and backups. This is likely the largest
  fixed cost.
- **GKE Autopilot** bills a cluster management fee plus the pods' resource requests. With the
  chart defaults and the console off, the six always-on Deployments request about 2.1 vCPU and
  2.5 GiB in total. Gateway, read-api and exports-api run 2 replicas each at 250m and 256Mi;
  chain runs 1 at 250m and 512Mi; exports-worker runs 1 at 250m and 256Mi; events-worker runs 1
  at 100m and 256Mi (`helm template` of the chart, 2026-10-25). The hourly retention Job adds
  100m and 256Mi while it runs.
- **Small usage-based costs:** Pub/Sub retention (1 day on three topics), Secret Manager (six
  secrets, their versions and access operations), Artifact Registry storage, and Cloud NAT if
  private nodes are used.

## D. What changes in the repository after each cloud step

| After | Change in repo | Owner |
|---|---|---|
| D2 confirmed GKE | Nothing. If Cloud Run is chosen instead, keep the core `runtime` stage, Secret IDs, GSAs and WIF, and replace the chart with Cloud Run service and job definitions. | Foundation |
| D1 / C-17 | Nothing for the deploy: it passes `gcp.projectId` from `vars.BM_GCP_PROJECT_ID` (`ci-cd.yml:447`). If the image project changes too, change `GCP_PROJECT_ID` at `ci-cd.yml:43`, where `build-images` pushes. | ci-cd.yml owner |
| D3 | Nothing: resolved (C-0). | — |
| C-8, C-9, C-14 | Nothing. `values-sandbox.yaml` already uses `brandme-sandbox` (instance and database), the three topic IDs and the five `brandme-sandbox-rts-*` Secret names (`:29-34`). | — |
| C-10, C-11, C-12, D6 | The values PR (C-19): bucket, OIDC issuer/audience/JWKS URI, contract address, https public origin. | Foundation (values), midnight-rights (address) |
| C-13 | The values PR (C-19) sets `eventsRetention.gcpServiceAccount: bm-sbx-fnd-retention`; this head still has `bm-sbx-fnd-outbox` (`values-sandbox.yaml:77-78`). The script must list `fnd-retention` (`brandme-events-retention`); it lists `dom-api` (`brandme-consumer-domains-api`) at `scripts/provision/gcp-dev-identities.sh:309`. | Foundation |
| C-14, C-15 (domain key) | The consumer-domains chart change references Secret `brandme-sandbox-dom-domain-assertion-key` and carries the kid and the public JWKS from C-14. | Consumer-domains |
| C-16, C-17 | Nothing; section E is applied. Set `BM_DEPLOY_ENABLED=true` only at C-20. | Founder |
| Console build args (G7) | `console.enabled: true` in `values-sandbox.yaml`, and add `console` to the rollout loop at `ci-cd.yml:486-488`. | Console owner |
| G24 | Switch `build-images` auth (`ci-cd.yml:364-368`) to `vars.BM_GCP_PUSH_WIF_PROVIDER` / `vars.BM_GCP_PUSHER_SA`, then C-22. | Foundation |
| After the first green deploy | Update CLAUDE.md's service table with evidence (the run URL, `kubectl` output); never before. | Parent |

While the committed `values-sandbox.yaml` contains any `REPLACE_ME`,
`scripts/validate-helm.sh` asserts that rendering it fails. Once none is left, it
asserts that the committed file renders and validates. A separate negative test keeps
proving that any `REPLACE_ME` value is refused. The deploy job passes
`gcp.projectId` from `vars.BM_GCP_PROJECT_ID`, so that placeholder may stay.

## E. `ci-cd.yml` deploy path (applied; gated off until `vars.BM_DEPLOY_ENABLED == 'true'`)

These are the jobs as they stand on this head. They are not copied here, so they cannot
drift. Read the file.

- **`build-images`** (`ci-cd.yml:298-391`). It needs `test-gateway`, `test-core`,
  `foundation-check`, `test-chain`, `test-frontend` and `security-scan` (`:301`). The
  consumer-domains subset job is gone, because `foundation-check` now runs the full `pnpm check`,
  pytest included. Each matrix leg builds, runs `.github/scripts/smoke-image.sh`, and only
  then authenticates and pushes. It writes `digest-<service>` outputs (`:304-308`), parsed
  from the registry's push line (`:374-391`). That `sed` expression was tested against the
  real push line from run 39902216424 ("main: digest: sha256:a8c6a22e… size: 2766").
- **`deploy`** (`ci-cd.yml:397-518`) runs only for a `v*` tag **and**
  `vars.BM_DEPLOY_ENABLED == 'true'` (`:404`), under `environment: sandbox`, with no
  cancel-in-progress and a 40-minute timeout. Its steps, in order:
  1. Validate the chart offline (`:429-430`).
  2. Render the exact release by digest. Rendering fails on any `REPLACE_ME`, and on a
     missing or malformed digest (`:432-456`).
  3. Authenticate with WIF (`:458-463`).
  4. Get GKE credentials.
  5. `helm upgrade --install … --wait --wait-for-jobs`, with the migrations hook first
     (`:475-481`).
  6. Rollout status and the three `--check` commands (`:483-491`).
  7. **New this round:** one retention pass, `kubectl create job --from=cronjob/brandme-events-retention`.
     It polls the Job's `Complete`/`Failed` condition for at most 10 minutes. Anything but
     `Complete` fails the deploy (`:493-511`).
  8. Diagnostics on failure, with no secret values (`:513-518`).

The agents image is still built and published, but it is not deployed: it is a CLI. The
deploy job is skipped on pull requests, so no required check should depend on it.

## F. Legacy deploy paths — all non-functional; recommend retirement

None of these can deploy the current system. Do not delete them in this
change: CLAUDE.md's kill-list marks `agents/` "DO NOT DELETE" because
`deploy-brandme.sh` uses it. Retire them together, with a CLAUDE.md update (D9).

| Path | Why it cannot work | Evidence |
|---|---|---|
| `deploy-brandme.sh` + `agents/*.sh` | They source files that do not exist; read Terraform outputs that do not exist; expect a cluster name Terraform does not create; assume Postgres/Neo4j/Redis/NATS. | `agents/*.sh:9` source `agents/lib/common.sh` and `deploy-brandme.sh:220` sources `agents/lib/show-access-info.sh`; `ls agents` has no `lib/`. `agents/infrastructure-agent.sh:53-55` reads `cluster_name`, `db_private_ip`, `bucket_name`; `brandme-infra/terraform/main.tf:256-280` defines `gke_cluster_name`, `gke_cluster_endpoint`, `cloudsql_connection_name`, `gcs_bucket_name`, `workload_identity_sa`. `infrastructure-agent.sh:34` expects `brandme-cluster`; `main.tf:78` names it `brandme-cluster-${var.environment}`. |
| `scripts/deploy.sh` | Builds `brandme/*:latest` from service-dir contexts the Dockerfiles cannot use, never pushes, and installs a chart that fails lint. | `scripts/deploy.sh:104-123` (build), `:227-229` (push left as TODO), `:158-161` (`./infrastructure/helm/brandme`). |
| `Makefile` build/push/deploy targets | Wrong contexts and image names (`gcr.io/brandme/*:latest`); `deploy-dev`/`deploy-prod` install `./brandme-umbrella` with values files that do not exist. | `Makefile:221-263`, `:269-291`. |
| `infrastructure/helm/brandme` | `helm lint` (3.22.1) fails: `no template "brandme.fullname"` in `templates/cube-service.yaml:5`; `:latest` images (`values.yaml:21,71,94,116`); the pinned Bitnami tags no longer exist on Docker Hub (audit map). | Ran `helm lint infrastructure/helm/brandme`. |
| `brandme-infra/terraform` | `terraform validate` (1.9.8) fails: undeclared `var.db_password` (`main.tf:192`; only `project_id`, `region`, `environment` are declared at `:31-45`). It provisions Cloud SQL, which current code does not use, and none of Spanner, Pub/Sub, Secret Manager, the export bucket or per-workload identities. | Ran `terraform init -backend=false && terraform validate` on a scratch copy. |
| `brandme-infra/helm/brandme-umbrella` | Subcharts and `values/values-prod.yaml` missing; `helm lint` still exits 0. Marked with `LEGACY.md`. | Ran `helm template` and `helm lint` (3.22.1). |

## G. How this packet was verified, and what was not

Ran (all local, no cloud credentials):

- `BRANDME_PYTHON=.venv/bin/python bash scripts/validate-helm.sh` (repo-root venv built from the lock) → exit 0 (lint, 4 renders × kubeconform, hardening assertions, 18 negative tests, env contract). A tampered cached helm archive failed the checksum gate and was deleted.
- Core image: built from the repo root with `-f brandme-core/Dockerfile --build-arg NODE_VERSION=24.21.0` and no `--target`, then `bash .github/scripts/smoke-image.sh core <image>` → exit 0. **Local deviation:** this sandbox re-terminates TLS, so the build used a scratch copy of the Dockerfile whose only change is a BuildKit secret mount of the proxy CA on the `pip install` line (`PIP_CERT`); secret mounts leave nothing in the image. Docker Hub returned 429, so `python:3.11.15-slim` came from `mirror.gcr.io` (same index digest `sha256:90744cff…`). The legacy stages were not built.
- Core image against the local Spanner emulator as the chart runs it (A8).
- Gateway and console images built the same way (CA mount on the `corepack`/`pnpm` build-stage lines only) and run read-only as uid 1000 (A10); existing gateway/console smoke checks pass.
- Gateway `loadConfig` + `checkGatewayMode` and the chain config parser on the chart's rendered env via `tsx` (A9).
- actionlint 1.7.7 on `.github/workflows/deploy-validate.yml` and on a scratch `ci-cd.yml` with the E patch.

Revision 2026-10-25 (on `bf31c98` plus this change; all offline, no cloud call):

- **Section C blocks.** Every bash block in section C was extracted. Each was checked to
  start with `set -euo pipefail`, parsed with `bash -n`, and run through shellcheck 0.10.0
  at `-S warning`, excluding SC1090, SC1091, SC2034 and SC2154: the blocks source the shared
  `env.sh`. All 28 blocks pass. The rotation runbook's 20 blocks pass the same checks. None was executed against GCP, GitHub or a cluster.
- **C-13 plan assertions.** They were run against `scripts/provision/gcp-dev-identities.sh`'s
  dry run, without `--apply` and with a placeholder project, so no `gcloud` command ran. The
  `dom-api` → `brandme-consumer-domains-api` assertion passes. The `fnd-retention` →
  `brandme-events-retention` assertion **fails on `bf31c98`**, because the script there has
  no `fnd-retention` identity yet. The step stops, as designed, until the change that adds
  it is merged.
- **C-15 rendering.** The rendering loop was run with a placeholder project and parsed as
  YAML: one SecretProviderClass with six `versions/1` pins, and six SecretSyncs whose names
  equal their source paths. On the same output, the rotation runbook's `pinned`/`pin`
  helpers read and rewrite exactly one entry.
- **Chart render.** `helm template` with `ci/test-values.yaml` gives the per-Deployment
  `secretKeyRef` consumers (rotation runbook 5.1) and the resource requests (cost note).
- **ci-cd.yml lint.** actionlint 1.7.7 with shellcheck 0.10.0 on this head's
  `ci-cd.yml` reports no findings, the same as the base file.
- **C-11 JWKS.** The JWKS URL answered with four RS256 keys (curl, 2026-10-25). The
  issuer/audience convention itself was not verified.
- **C-10 flag.** `gcloud storage buckets describe --help` lists `--raw`. It was not run
  against a bucket.

Not verified (needs the cluster or GCP): every step in section C; the cluster itself; Workload Identity
token issuance with `automountServiceAccountToken: false` (G17); NetworkPolicy
behaviour on the real dataplane (G18); the custom roles (G19); secret sync
(the C-15 manifests are not schema-validated, and their refresh after a pin
change is not observed); the chain image under a read-only root; any Preprod
transaction or finality; the deploy job's retention pass (`ci-cd.yml:496-511`)
on a real cluster.
