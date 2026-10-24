# GKE deploy-verification packet — first deploy `BRANDME_MODE=sandbox`

Prepared 2026-10-23 on base `744d593` (main `5174ec2` + PR #53 round-2
foundation work). Owner: foundation lane.

**Nothing has been deployed.** No GCP credential works from the environment
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
| D3 | Migration numbering. The consumer-domains lane branch (PR #52) adds `V003_wardrobe`, `V004_social`, `V005_rewards`. Once V006+ are applied to a real database, lower versions can never be applied there: the runner refuses out-of-order versions (`brandme-data/spanner/migrations/runner.py:195-202`) and refuses `--allow-out-of-order` in sandbox/production (`:294-295`). | Merge or renumber V003–V005 before the first `up` against Cloud Spanner. |
| D4 | How Secret Manager values reach Kubernetes Secrets. | GKE secret sync add-on (GKE ≥ 1.33), step C-15. |
| D5 | OIDC issuer and audience the gateway trusts (strict modes require https issuer + audience, `brandme-gateway/src/middleware/mode.ts:38-41`). | Google Identity Platform (spec `03-architecture-data-api.md` item 9). |
| D6 | Public exposure and domain. The legacy files disagree (`api.brandme.io` vs `console.brandme.com`). | No public ingress for the first sandbox deploy. |
| D7 | Who deploys the Midnight Preprod rights contract and owns the Blockfrost token. read-api and exports refuse to start without a 64-hex contract address. | Midnight-rights lane, with the address recorded in `values-sandbox.yaml`. |
| D8 | Cluster mode if one must be created. | Autopilot, Regular channel. |
| D9 | Retire the legacy deploy paths in section F (CLAUDE.md lists `agents/` as DO NOT DELETE). | Retire in one change that also updates CLAUDE.md. |

## A. What exists (verified)

| # | Fact | Evidence | How verified |
|---|---|---|---|
| A1 | CI pushes images to `gcr.io/lux-realestate-app/brandme-{gateway,core,agents,chain,console}` with tags `:main` and `:sha-<7>` on every push to `main`. Run 39902216424 (push, sha `5174ec2`) pushed core `sha256:a8c6a22e9e50…`, chain `sha256:69f9a96bf1b3…`, console `sha256:f6627c1f184a…`, agents `sha256:5b215c7a4d2e…`, gateway `sha256:adbf595add0e…`. | `.github/workflows/ci-cd.yml:219` (`PUBLISH_IMAGES`), `:241-251` (metadata tags), `:273-290` (JSON-key auth, push). Run log lines "The push refers to repository [gcr.io/lux-realestate-app/brandme-core]" / "main: digest: sha256:a8c6a22e…". | `gh run view 39902216424` (all build jobs `success`) and the saved run log. |
| A2 | At the audited baseline (`744d593`) the CI credential was a long-lived JSON key, `secrets.GCP_SA_KEY`, and no workflow had `id-token: write`. After this change set, image publishing still uses the key; the deploy job uses WIF (`id-token: write`) and is gated by `BM_DEPLOY_ENABLED`. | Baseline `ci-cd.yml:32-34`, `:277`, `:309`; now the `build-images` and `deploy` jobs in `ci-cd.yml`. | Read. Which service account backs the key, and its roles, is unknown (GitHub secrets API returns 403 here). |
| A3 | The `Deploy to GKE` job has never run: it only runs on `refs/tags/v*` and the repository has no tags. | `ci-cd.yml:296-300`. Run 39902216424 lists "Deploy to GKE" with conclusion `skipped`. | `git ls-remote --tags` → 0 tags; `gh run view`. |
| A4 | Container Registry stopped accepting writes on 2025-03-18, so successful 2026 pushes to `gcr.io/lux-realestate-app` imply Artifact Registry `gcr.io` repositories exist in that project. | Google transition guide (audit map). | **Inference**, not a live check: an anonymous registry probe returns the same 401 for this project and for a nonexistent one. |
| A5 | The repository is public (`visibility: public`); repository id `1083300600`, owner id `25632130` (used to pin WIF in C-16). | — | `gh api repos/brandmeonline/Brand-Me-Labs`. |
| A6 | **New:** chart `brandme-infra/helm/brandme` for gateway, chain, console, read-api, exports-api, exports-worker, events-worker and a migration hook Job. | `brandme-infra/helm/brandme/` | `scripts/validate-helm.sh` passes: helm 3.22.1 lint `--strict`; 42/42 resources valid with `kubeconform -strict` against Kubernetes 1.35.0 and 1.36.0 (CI values, ingress on, GKE CRDs included); 32/32 for the filled sandbox values; 18 negative rendering tests refuse as expected (as of 2026-10-24); env contract OK. A deliberate typo in a core field and in a FrontendConfig field were both rejected (kubeconform exit 1). |
| A7 | **New:** the core image's last stage is `runtime`, so CI's default build of `core` produces it: hash-verified install of `scripts/python/requirements.lock`, uid 10001, no `--reload`, no celery, no default process (bare run prints usage, exit 64). | `brandme-core/Dockerfile` (final stage). Compose does not build this Dockerfile (`docker-compose.yml:22-30` uses an inline Dockerfile). | Built from the repo root with `-f brandme-core/Dockerfile --build-arg NODE_VERSION=24.21.0`, no `--target` (as `ci-cd.yml:253-264`); `bash .github/scripts/smoke-image.sh core <image>` exits 0. See G for the one local build deviation. |
| A8 | The core image runs the chart's commands as uid 10001 with a read-only root, `/tmp` tmpfs, all capabilities dropped: `runner.py up` applied V001–V014 to a fresh emulator database, `read_api --check` printed `{"status":"ready","read_only":true}`, the server answered `GET /health` 200 and an unauthenticated private read 401. | `docker run --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges …` | Ran against the local Spanner emulator (development mode; strict modes refuse emulators). |
| A9 | The chart's rendered env satisfies each process's own strict-mode validator: `ReadConfig.from_env`, `ExportConfig.from_env` (API and worker), `WorkerConfig.from_env` + `PubSubPublisher` topic checks (reached the credential lookup), and the gateway's `loadConfig` + `checkGatewayMode` (no violations), and the chain config parser. | Python stage of `scripts/validate-helm.sh`; gateway/chain run locally with `tsx`. | Ran with fake, distinct 40-char tokens. |
| A10 | The gateway and console images (unchanged Dockerfiles) serve `/healthz` and `/` as uid 1000 with a read-only root (`/tmp`, and for the console `.next/cache`, as tmpfs). | — | Built locally and run with the chart's settings; existing `smoke-image.sh gateway` / `console` pass. The chain image was **not** built here. |
| A11 | GKE Regular channel: 1.35 is the current auto-upgrade target (since 2026-04-28); 1.36 is available and auto-upgrades from 2026-11. The chart is validated against both. | docs.cloud.google.com/kubernetes-engine/docs/release-schedule (page updated 2026-10-22). | Read 2026-10-23. |

## B. What is missing

| # | Gap | Blocks first deploy? | Where it is fixed |
|---|---|---|---|
| G1 | Cluster existence, mode, version, Workload Identity pool and dataplane are unconfirmed. | Yes | C-3 / C-6 (founder) |
| G2 | The current deploy job cannot succeed: it installs `./brandme-umbrella`, whose subcharts and `values/values-prod.yaml` do not exist (helm 3.22.1: "missing in charts/ directory…", "open values/values-prod.yaml: no such file"); it pins `global.image.tag=v1.2.3` while metadata-action pushes `1.2.3`/`1.2`/`sha-…` (`ci-cd.yml:246-251` vs `:329`); it rolls out `brandme-core` (celery beat) and `brandme-agents` (a CLI) (`:336-337`); JSON key, no environment, no concurrency. | Yes (job now gated off) | **Section E applied in this change set:** the deploy job uses the new chart, deploys by digest, runs under `environment: sandbox` with WIF, and runs only when a `v*` tag AND `vars.BM_DEPLOY_ENABLED == 'true'`. Until the founder sets that variable, a tag cannot start a half-configured deploy. |
| G3 | No repo artifact provisions the data plane the code needs: Spanner instance/database, three Pub/Sub topics (≥ 24 h retention), the export bucket with its exact policy, Secret Manager secrets, per-workload GSAs and IAM, WIF. | Yes | C-5…C-17 |
| G4 | Migration numbering (D3). | Yes (before the first `up`) | Founder decision, then lane merge |
| G5 | No Midnight Preprod contract address exists (`docs/build/evidence/midnight-integration-2026-10-22.md:53`). read-api and exports refuse to start without one; chain starts but reports the capability `unavailable`. | Yes for read-api/exports | D7, then `values-sandbox.yaml` |
| G6 | No OIDC issuer/audience; the gateway refuses strict modes without them (verified: "OIDC_ISSUER is required; OIDC_AUDIENCE is required"). | Yes for gateway | D5, then `values-sandbox.yaml` |
| G7 | The console bakes its API URLs at build time and CI passes none, so browsers would call `http://localhost:3000` (`brandme-console/lib/api.ts:11-14`; `ci-cd.yml:258`). `console.enabled: false` in `values-sandbox.yaml`. | No (console off) | Console build args (console owner) |
| G8 | **Fixed in this change set (gateway package):** the limiter exempts `/health`/`/healthz`, keys members by principal and addresses by `req.ip` with a configurable `TRUST_PROXY` (`brandme-gateway/src/middleware/rateLimiter.ts`, `src/config/index.ts:36-66`). The chart passes `gateway.trustProxy` and refuses `ingress.enabled` without it (`templates/validate.yaml`). The GKE value (2) is documented, not observed on a cluster. | No | Confirm `req.ip` on first ingress deploy |
| G9 | The gateway exits immediately on SIGTERM (`brandme-gateway/src/index.ts:98`). The chart adds a 5 s `preStop` sleep so endpoints are removed first; in-flight requests still drop at exit. | No | Gateway lane: drain on SIGTERM |
| G10 | Observed locally: with no ADC and no emulator, the gateway logs "listening" and then dies on an unhandled rejection from the Spanner client ("Could not load the default credentials"). With Workload Identity this should not occur, but a broken binding shows as a restart loop after the startup probe has briefly passed. | No | Gateway lane: fail before listening |
| G11 | **Fixed in this change set (gateway package):** strict modes refuse `SPANNER_EMULATOR_HOST`, `FIRESTORE_EMULATOR_HOST` and `PUBSUB_EMULATOR_HOST` (`brandme-gateway/src/middleware/mode.ts`). | No | — |
| G12 | The two workers have no health endpoint, so a hung worker is not detected. They exit non-zero on failed startup checks; the chart uses `minReadySeconds: 30` so a crash during startup blocks the rollout. | No | Core lane: heartbeat or health port |
| G13 | **Fixed in this change set (Python package):** `brandme_core/config.py` now carries audited inventories for read_api, privacy_exports, events_worker and gateway, and the stale chain entries are replaced (Midnight SANDBOX, Cardano UNCONFIGURED). chain/read-api/exports pass `preflight` in sandbox only (test networks); production stays refused. The chart still runs no `preflight` init container; adding one needs `ENVIRONMENT=BRANDME_MODE` and each service's network variable. | No | Optional init container after first deploy |
| G14 | No Pub/Sub subscriptions or consumers exist; the outbox README asks for subscriptions before publishing (`brandme_core/events/README.md:15-26`). Topic retention (≥ 24 h, required by `brandme_core/events/pubsub.py:94-103`) is the only replay window until consumers exist. | No | Consumer owners |
| G15 | The Firestore projection writer has no process entrypoint, so Firestore is not provisioned or deployed here. | No | Foundation lane, later |
| G16 | No secret-delivery mechanism is installed (D4). | Yes | C-15 |
| G17 | `automountServiceAccountToken: false` relies on the GKE metadata server issuing Workload Identity tokens without the pod's KSA token. **Inference**; the in-cluster `--check` commands in E prove or disprove it on first deploy (`podDefaults.automountServiceAccountToken` toggles it). | Maybe | First deploy |
| G18 | NetworkPolicy egress for the metadata server uses Google's documented addresses (169.254.169.252/32:987,988; Dataplane V2 169.254.169.254/32:80,8080) and DNS (kube-dns, 169.254.20.10, 169.254.169.254). Not exercised on a real dataplane. | Maybe | First deploy |
| G19 | Spanner custom role permissions (C-12) are derived from `roles/spanner.databaseUser` minus schema rights; not exercised live. | Maybe | First deploy (`--check` + logs) |
| G20 | The core image installs the whole foundation lock, including test tools (pytest, black, datamodel-code-generator). | No | Split a runtime-only lock |
| G21 | Base images are pinned by tag (`python:3.11.15-slim`, `node:24.21.0-bookworm-slim`), not digest; third-party actions are not SHA-pinned; no Dependabot/Renovate. | No | Foundation follow-up |
| G22 | **Fixed in this change set:** `.cache/` is in `.gitignore` and `.dockerignore`. | No | — |
| G23 | The consumer frontend has no Dockerfile and no image. | No | Frontend owner |
| G24 | `build-images` still publishes with the JSON key. The provisioning script now creates a separate push identity (`bm-sbx-fnd-pusher`, artifactregistry.writer only) in its own `github-push` pool (main and `v*` tags); switching `build-images` to it is a one-step change after the founder runs the script. | No | Founder runs the script, then foundation switches build-images |
| G25 | The export API cannot check that its token differs from the read API and chain tokens, because those are not in its pod. Distinctness depends on generating independent values (C-14). | No | C-14 |
| G26 | The gateway's write-side calls have no server among the deployed processes. `POST /challenges`, `/assets/{id}/transfers` and `/assets/{id}/reprint-quotes` go to `RIGHTS_SERVICE_URL` (`brandme-gateway/src/routes/v1/ownership.ts:44`, `assets.ts:55`, `assets.ts:71`), and `POST /deletion` goes to `PRIVACY_SERVICE_URL` (`routes/v1/privacy.ts:110`). The chart points both URLs at the read API (`templates/gateway.yaml`), which serves only GET routes (`brandme_core/read_api/app.py:95-117`). In sandbox those routes would get 404/405. | No (reads work) | midnight-rights / privacy lanes: name the write-side service |
| G27 | **Inference, not tested:** `@google-cloud/spanner` 9.0.0 (gateway, chain) may export client-side metrics to Cloud Monitoring by default. If it does, GSAs without `monitoring.timeSeries.create` will log export errors. Grant `roles/monitoring.metricWriter` to those GSAs, or turn the client metrics off. | No | First deploy logs |

## C. Exact founder / console actions (in order)

Run in Cloud Shell or a workstation as a project owner. Each step is marked
**[read-only check]** or **[creates resource]**. Never paste secret values into
commands, tickets or chat; the commands below pipe them.

```bash
# --- set once per shell ---
export PROJECT_ID=REPLACE_ME            # D1
export REGION=us-east1
export CLUSTER=brandme-cluster
export NS=brandme
export REPO=brandmeonline/Brand-Me-Labs
export REPO_ID=1083300600 OWNER_ID=25632130        # from gh api repos/$REPO (A5)
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
sa() { echo "$1@${PROJECT_ID}.iam.gserviceaccount.com"; }
```

**C-1 [read-only check] Who you are and what the project is.**
```bash
gcloud auth list
gcloud projects describe "$PROJECT_ID"
gcloud projects get-iam-policy "$PROJECT_ID" --flatten=bindings --format='table(bindings.role,bindings.members)'
```

**C-2 [read-only check] Which service account backs `GCP_SA_KEY` and what it can do.**
```bash
gcloud iam service-accounts list --project "$PROJECT_ID"
gcloud iam service-accounts keys list --iam-account=<SA_FROM_LIST> --managed-by=user
gcloud projects get-iam-policy "$PROJECT_ID" --flatten=bindings \
  --filter="bindings.members:serviceAccount:<SA_FROM_LIST>" --format='value(bindings.role)'
```

**C-3 [read-only check] Does the cluster exist, and how is it configured?**
```bash
gcloud container clusters list --project "$PROJECT_ID"
gcloud container clusters describe "$CLUSTER" --region "$REGION" --project "$PROJECT_ID" \
  --format='yaml(autopilot.enabled,releaseChannel.channel,currentMasterVersion,workloadIdentityConfig.workloadPool,networkConfig.datapathProvider,privateClusterConfig.enablePrivateNodes)'
```
Need: Workload Identity pool `$PROJECT_ID.svc.id.goog`, network policy
enforcement (Autopilot / Dataplane V2 always enforce), version ≥ 1.33 (chart
`kubeVersion` and secret sync).

**C-4 [read-only check] Registry and images.**
```bash
gcloud artifacts repositories list --project "$PROJECT_ID" --format='table(name,format,location)'
gcloud artifacts docker images list "gcr.io/$PROJECT_ID/brandme-core" --include-tags --limit 5
```

**C-5 [creates resource] Enable APIs.**
```bash
gcloud services enable container.googleapis.com artifactregistry.googleapis.com spanner.googleapis.com \
  pubsub.googleapis.com storage.googleapis.com secretmanager.googleapis.com iam.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com cloudresourcemanager.googleapis.com --project "$PROJECT_ID"
```

**C-6 [creates resource] Cluster — only if C-3 found none (D8).**
```bash
gcloud container clusters create-auto "$CLUSTER" --project "$PROJECT_ID" --region "$REGION" \
  --release-channel=regular --enable-secret-sync
# existing cluster instead:
gcloud container clusters update "$CLUSTER" --location "$REGION" --project "$PROJECT_ID" --enable-secret-sync
```
`--enable-secret-sync` is from docs.cloud.google.com/secret-manager/docs/sync-k8-secrets
(read 2026-10-23, GKE ≥ 1.33); it was not executed here. A Standard cluster
also needs `--workload-pool="$PROJECT_ID.svc.id.goog"` and network policy
enforcement. Private nodes need Cloud NAT for the chain's Blockfrost calls.

**C-7 [creates resource] Namespace with Pod Security "restricted".**
```bash
gcloud container clusters get-credentials "$CLUSTER" --region "$REGION" --project "$PROJECT_ID"
kubectl create namespace "$NS"
kubectl label namespace "$NS" pod-security.kubernetes.io/enforce=restricted pod-security.kubernetes.io/enforce-version=latest
```
Release name and namespace must both be `brandme`: the KSA names in C-13 are
`brandme-<component>`.

**C-8 [creates resource] Spanner (GoogleSQL).** Do **not** run migrations by
hand: the chart's hook Job does, after D3.
```bash
gcloud spanner instances create brandme-sandbox --project "$PROJECT_ID" --config=regional-us-east1 \
  --processing-units=100 --description="Brand.Me sandbox"
gcloud spanner databases create brandme-sandbox --instance=brandme-sandbox --project "$PROJECT_ID" \
  --database-dialect=GOOGLE_STANDARD_SQL
```

**C-9 [creates resource] Pub/Sub topics (names must start `brandme-sandbox-`, retention ≥ 24 h).**
```bash
for t in public member-private restricted; do
  gcloud pubsub topics create "brandme-sandbox-$t" --project "$PROJECT_ID" --message-retention-duration=1d
done
```

**C-10 [creates resource] Export bucket with the exact policy `PrivateStore.check` enforces** (`brandme_core/privacy_exports/storage.py:100-112`).
```bash
export SUFFIX=$(openssl rand -hex 3); export BUCKET="brandme-sandbox-exports-$SUFFIX"
gcloud storage buckets create "gs://$BUCKET" --project "$PROJECT_ID" --location="$REGION" \
  --uniform-bucket-level-access --public-access-prevention --soft-delete-duration=0
printf '%s\n' '{"lifecycle":{"rule":[{"action":{"type":"Delete"},"condition":{"age":1}}]}}' > /tmp/lc.json
gcloud storage buckets update "gs://$BUCKET" --lifecycle-file=/tmp/lc.json
gcloud storage buckets describe "gs://$BUCKET" --format=json   # [read-only check]: versioning off, no retention policy
```

**C-11 [creates resource] One Google service account per workload. No keys.**
```bash
for id in bm-sbx-fnd-deployer bm-sbx-fnd-migrator bm-sbx-fnd-gateway bm-sbx-fnd-outbox \
          bm-sbx-rts-chain bm-sbx-rts-read-api bm-sbx-rts-export-api bm-sbx-rts-export-wkr; do
  gcloud iam service-accounts create "$id" --project "$PROJECT_ID" --display-name="Brand.Me sandbox $id"
done
```

**C-12 [creates resource] Custom roles (least privilege).** First compare
against the predefined role **[read-only check]**:
`gcloud iam roles describe roles/spanner.databaseUser --format='value(includedPermissions)'`.
`roles/spanner.databaseUser` includes `spanner.databases.updateDdl`, so runtime
workloads get a data-only custom role instead.
```bash
gcloud iam roles create brandmeSpannerDataRW --project "$PROJECT_ID" --stage=GA \
  --title="Brand.Me Spanner data read/write (no DDL)" \
  --permissions=spanner.databases.beginOrRollbackReadWriteTransaction,spanner.databases.beginReadOnlyTransaction,spanner.databases.read,spanner.databases.select,spanner.databases.write,spanner.sessions.create,spanner.sessions.delete,spanner.sessions.get,spanner.sessions.list
gcloud iam roles create brandmeExportBucketRead --project "$PROJECT_ID" --stage=GA \
  --title="Brand.Me export bucket read" --permissions=storage.buckets.get,storage.objects.get
gcloud iam roles create brandmeExportBucketWrite --project "$PROJECT_ID" --stage=GA \
  --title="Brand.Me export bucket write" \
  --permissions=storage.buckets.get,storage.objects.get,storage.objects.create,storage.objects.delete
```

**C-13 [creates resource] Resource-level grants and Workload Identity bindings.**
```bash
DB=(--instance=brandme-sandbox --project "$PROJECT_ID")
RW="projects/$PROJECT_ID/roles/brandmeSpannerDataRW"
# Spanner, database level
gcloud spanner databases add-iam-policy-binding brandme-sandbox "${DB[@]}" --member="serviceAccount:$(sa bm-sbx-fnd-migrator)" --role=roles/spanner.databaseUser   # DDL + ledger writes; no drop/IAM
gcloud spanner databases add-iam-policy-binding brandme-sandbox "${DB[@]}" --member="serviceAccount:$(sa bm-sbx-rts-read-api)" --role=roles/spanner.databaseReader
for id in bm-sbx-fnd-gateway bm-sbx-fnd-outbox bm-sbx-rts-chain bm-sbx-rts-export-api bm-sbx-rts-export-wkr; do
  gcloud spanner databases add-iam-policy-binding brandme-sandbox "${DB[@]}" --member="serviceAccount:$(sa $id)" --role="$RW"
done
# Pub/Sub, topic level: publish + topics.get (the worker checks retention)
for t in public member-private restricted; do
  for role in roles/pubsub.publisher roles/pubsub.viewer; do
    gcloud pubsub topics add-iam-policy-binding "brandme-sandbox-$t" --project "$PROJECT_ID" \
      --member="serviceAccount:$(sa bm-sbx-fnd-outbox)" --role="$role"
  done
done
# Export bucket, bucket level: API reads, worker reads/creates/deletes (privacy_exports/README.md:75-80)
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$(sa bm-sbx-rts-export-api)" --role="projects/$PROJECT_ID/roles/brandmeExportBucketRead"
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$(sa bm-sbx-rts-export-wkr)" --role="projects/$PROJECT_ID/roles/brandmeExportBucketWrite"
# Workload Identity: KSA brandme/<name> may act as its GSA
while read -r ksa id; do
  gcloud iam service-accounts add-iam-policy-binding "$(sa $id)" --project "$PROJECT_ID" \
    --role=roles/iam.workloadIdentityUser --member="serviceAccount:$PROJECT_ID.svc.id.goog[$NS/$ksa]"
done <<'EOF'
brandme-gateway bm-sbx-fnd-gateway
brandme-chain bm-sbx-rts-chain
brandme-read-api bm-sbx-rts-read-api
brandme-exports-api bm-sbx-rts-export-api
brandme-exports-worker bm-sbx-rts-export-wkr
brandme-events-worker bm-sbx-fnd-outbox
brandme-migrations bm-sbx-fnd-migrator
EOF
```
The console KSA (`brandme-console`) gets no Google service account and no roles.

**C-14 [creates resource] Secret Manager.** Five secrets, IDs
`brandme-<mode>-<lane>-<purpose>`. The four service tokens are independent
random values (32–256 chars of `[A-Za-z0-9._~+/-]`, distinct by construction);
the Blockfrost Preprod project id comes from the provider (D7).
```bash
for id in rights-service-token privacy-service-token privacy-export-service-token chain-service-token; do
  gcloud secrets create "brandme-sandbox-rts-$id" --project "$PROJECT_ID" --replication-policy=automatic \
    --labels=lane=rts,mode=sandbox,rotation-days=90
  head -c 48 /dev/urandom | base64 | tr -d '=\n' | gcloud secrets versions add "brandme-sandbox-rts-$id" --project "$PROJECT_ID" --data-file=-
done
gcloud secrets create brandme-sandbox-rts-midnight-blockfrost-project-id --project "$PROJECT_ID" \
  --replication-policy=automatic --labels=lane=rts,mode=sandbox
read -rs BF && printf '%s' "$BF" | gcloud secrets versions add brandme-sandbox-rts-midnight-blockfrost-project-id --project "$PROJECT_ID" --data-file=- && unset BF
```

**C-15 [creates resource] Deliver secrets into the namespace (D4).** Recommended:
GKE secret sync (C-6 enabled it). One sync identity reads only these five secrets.
```bash
kubectl -n "$NS" create serviceaccount brandme-secret-sync
for id in rights-service-token privacy-service-token privacy-export-service-token chain-service-token midnight-blockfrost-project-id; do
  gcloud secrets add-iam-policy-binding "brandme-sandbox-rts-$id" --project "$PROJECT_ID" --role=roles/secretmanager.secretAccessor \
    --member="principal://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$PROJECT_ID.svc.id.goog/subject/ns/$NS/sa/brandme-secret-sync"
done
```
Then apply, with `PROJECT_ID` substituted (shape copied from the Google page
above; **not schema-validated here**, the CRDs exist only on a cluster with the add-on):
```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata: {name: brandme-sandbox-rts, namespace: brandme}
spec:
  provider: gke
  parameters:
    secrets: |
      - resourceName: "projects/PROJECT_ID/secrets/brandme-sandbox-rts-rights-service-token/versions/latest"
        path: "rights-service-token"
      - resourceName: "projects/PROJECT_ID/secrets/brandme-sandbox-rts-privacy-service-token/versions/latest"
        path: "privacy-service-token"
      - resourceName: "projects/PROJECT_ID/secrets/brandme-sandbox-rts-privacy-export-service-token/versions/latest"
        path: "privacy-export-service-token"
      - resourceName: "projects/PROJECT_ID/secrets/brandme-sandbox-rts-chain-service-token/versions/latest"
        path: "chain-service-token"
      - resourceName: "projects/PROJECT_ID/secrets/brandme-sandbox-rts-midnight-blockfrost-project-id/versions/latest"
        path: "midnight-blockfrost-project-id"
---
# One SecretSync per Kubernetes Secret; metadata.name becomes the Secret name.
# Repeat for the other four (sourcePath = the path above, targetKey: value).
apiVersion: secret-sync.gke.io/v1
kind: SecretSync
metadata: {name: brandme-sandbox-rts-chain-service-token, namespace: brandme}
spec:
  serviceAccountName: brandme-secret-sync
  secretProviderClassName: brandme-sandbox-rts
  secretObject:
    type: Opaque
    data:
      - sourcePath: "chain-service-token"
        targetKey: "value"
```
Fallback without the add-on (no rotation sync; value never touches disk):
`gcloud secrets versions access latest --secret=<id> --project "$PROJECT_ID" | kubectl -n "$NS" create secret generic <id> --from-file=value=/dev/stdin`.
External Secrets Operator is the other option; it is not installed anywhere.
**[read-only check]** `kubectl -n "$NS" get secrets` lists the five names (never `-o yaml`).

**C-16 [creates resource] Workload Identity Federation for the deploy job.** The
condition pins the repository **and** owner by immutable numeric id, the ref to
`v*` tags, and the GitHub Environment. `scripts/provision/gcp-dev-identities.sh --apply --github-repo-id N`
creates the same pool and provider (without the owner-id clause) plus a separate
`github-push` pool for the image pusher (`bm-sbx-fnd-pusher`, G24); run one or the other.
```bash
gcloud iam workload-identity-pools create github-deploy --project "$PROJECT_ID" --location=global --display-name="GitHub Actions deploy"
gcloud iam workload-identity-pools providers create-oidc brandme-deploy --project "$PROJECT_ID" --location=global \
  --workload-identity-pool=github-deploy --display-name="Brand-Me-Labs sandbox deploy" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref,attribute.environment=assertion.environment" \
  --attribute-condition="assertion.repository_id == '$REPO_ID' && assertion.repository_owner_id == '$OWNER_ID' && assertion.ref.startsWith('refs/tags/v') && assertion.environment == 'sandbox'"
gcloud iam service-accounts add-iam-policy-binding "$(sa bm-sbx-fnd-deployer)" --project "$PROJECT_ID" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-deploy/attribute.repository_id/$REPO_ID"
# Deployer: may fetch cluster credentials; Kubernetes rights only inside the namespace.
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$(sa bm-sbx-fnd-deployer)" --role=roles/container.clusterViewer
kubectl create rolebinding brandme-deployer -n "$NS" --clusterrole=admin --user="$(sa bm-sbx-fnd-deployer)"
```
The namespaced `admin` role covers what helm needs here (Deployments,
Services, ServiceAccounts, Jobs, NetworkPolicies, PDBs, release Secrets,
`pods/exec` for the checks). If ingress is enabled later, also grant the
deployer the `cloud.google.com` and `networking.gke.io` resources
(BackendConfig, ManagedCertificate, FrontendConfig) in the namespace.

**C-17 [creates resource] GitHub: environment, tag ruleset, repository variables.**
- Settings → Environments → New environment **`sandbox`**: required reviewer =
  the founder; "Deployment branches and tags" → selected → add tag rule `v*`.
  With a single maintainer leave "Prevent self-review" off, or the founder
  cannot approve their own tag.
- Settings → Rules → Rulesets → New **tag** ruleset "release tags", target
  `refs/tags/v*`, enforcement Active, rules: restrict creations, updates and
  deletions; bypass list: repository admins only.
- Repository variables (none of these is a secret):
```bash
gh variable set BM_GCP_PROJECT_ID   --repo "$REPO" --body "$PROJECT_ID"
gh variable set BM_GCP_REGION       --repo "$REPO" --body "$REGION"
gh variable set BM_GKE_CLUSTER      --repo "$REPO" --body "$CLUSTER"
gh variable set BM_GCP_WIF_PROVIDER --repo "$REPO" --body "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-deploy/providers/brandme-deploy"
gh variable set BM_GCP_DEPLOYER_SA  --repo "$REPO" --body "$(sa bm-sbx-fnd-deployer)"
gh variable set BM_DEPLOY_ENABLED   --repo "$REPO" --body false
```

**C-18 [read-only check, then creates resource if needed] Nodes can pull the images.**
```bash
gcloud container clusters describe "$CLUSTER" --region "$REGION" --project "$PROJECT_ID" --format='value(autopilot.enabled,nodeConfig.serviceAccount)'
gcloud artifacts repositories get-iam-policy gcr.io --location=<LOCATION_FROM_C-4> --project "$PROJECT_ID"
```
Grant `roles/artifactregistry.reader` on that repository to the node service
account only if it is missing, or if the images live in another project than
the cluster (D1).

**C-19 [creates resource] Optional public edge — not for the first deploy (D6, G8).**
`gcloud compute addresses create brandme-sandbox-edge --global --project "$PROJECT_ID"`, an
A record for the chosen host(s), then set `ingress.*` in `values-sandbox.yaml`.

**C-20 First deploy.** After the in-repo changes in D are merged:
`gh variable set BM_DEPLOY_ENABLED --repo "$REPO" --body true`, then push a
`v*` tag (for example `v0.1.0`) and approve the `sandbox` environment.

**C-21 [read-only check] After the deploy.**
```bash
kubectl -n "$NS" get deploy,pods,jobs
kubectl -n "$NS" logs job/brandme-migrations
kubectl label --dry-run=server --overwrite namespace "$NS" pod-security.kubernetes.io/enforce=restricted   # no warnings expected
kubectl -n "$NS" exec deploy/brandme-events-worker -- python -m brandme_core.events.worker --check
```

**C-22 [creates resource] Retire the JSON key** once both the deploy job and
image publishing use WIF (G24): `gcloud iam service-accounts keys delete <KEY_ID> --iam-account=<SA_FROM_C-2>`,
then delete the `GCP_SA_KEY` secret in GitHub.

## D. What changes in the repository after each cloud step

| After | Change in repo | Owner |
|---|---|---|
| D2 confirmed GKE | Nothing. If Cloud Run is chosen instead, keep the core `runtime` stage, Secret IDs, GSAs and WIF; replace the chart with Cloud Run service/job definitions. | Foundation |
| D1 / C-17 | Nothing for the deploy (it passes `gcp.projectId` from `vars.BM_GCP_PROJECT_ID`). If the image project changes too, change `GCP_PROJECT_ID` in `ci-cd.yml:37` (where `build-images` pushes). | ci-cd.yml owner |
| D3 | Renumber or merge V003–V005 before the first deploy. | Foundation + consumer-domains |
| C-8, C-9, C-11, C-14 | Nothing: `values-sandbox.yaml` already uses `brandme-sandbox` (instance and database), the three topic IDs, the `bm-sbx-*` GSAs and the `brandme-sandbox-rts-*` Secret names. | — |
| C-10 | Replace `REPLACE_ME_SUFFIX` in `privacyExports.bucket`. | Foundation |
| D5 | Fill `gateway.oidc.issuer` and `gateway.oidc.audience`. | Foundation |
| D6 | Fill `gateway.publicOrigins` (https). Later, for C-19: `ingress.enabled`, `staticIpName`, hosts and `gateway.trustProxy` (G8; the chart refuses ingress without it). | Foundation / gateway |
| D7 | Fill `midnight.contractAddress` (64 lowercase hex). | Midnight-rights |
| C-16, C-17 | Section E is applied. Set `BM_DEPLOY_ENABLED=true` only after every step in section C. | Founder |
| Console build args (G7) | `console.enabled: true` in `values-sandbox.yaml`; add `console` to the rollout loop in E. | Console owner |
| Done | `.cache/` is in `.gitignore` and `.dockerignore` (G22). | — |
| After the first green deploy | Update CLAUDE.md's service table with evidence (run URL, `kubectl` output); never before. | Parent |

While the committed `values-sandbox.yaml` contains any `REPLACE_ME`,
`scripts/validate-helm.sh` asserts that rendering it fails; once none is left
it asserts the committed file renders and validates. A separate negative test
keeps proving that any `REPLACE_ME` value is refused. (The deploy job passes
`gcp.projectId` from `vars.BM_GCP_PROJECT_ID`, so that placeholder may stay.)

## E. `ci-cd.yml` deploy patch (applied in this change set; gated off until `vars.BM_DEPLOY_ENABLED == 'true'`)

Two parts. The result was linted with actionlint 1.7.7 on a scratch copy: no
new findings (the only finding, SC2034 at the Firestore step, already exists
on the base file).

**E-1. `build-images` exposes the pushed digest per image.** Add under
`timeout-minutes: 40`:
```yaml
    # Matrix legs write distinct output names, so the job outputs combine.
    outputs:
      digest-gateway: ${{ steps.publish.outputs.digest-gateway }}
      digest-core: ${{ steps.publish.outputs.digest-core }}
      digest-chain: ${{ steps.publish.outputs.digest-chain }}
      digest-console: ${{ steps.publish.outputs.digest-console }}
```
and replace the `Publish verified images` step:
```yaml
      - name: Publish verified images
        id: publish
        if: env.PUBLISH_IMAGES == 'true'
        env:
          IMAGE_TAGS: ${{ steps.meta.outputs.tags }}
          SERVICE: ${{ matrix.service }}
        run: |
          set -euo pipefail
          digest=""
          while IFS= read -r tag; do
            out=$(docker push "$tag")
            printf '%s\n' "$out"
            pushed=$(printf '%s\n' "$out" | sed -nE 's/^.*: digest: (sha256:[a-f0-9]{64}) size: [0-9]+$/\1/p' | tail -n 1)
            [[ "$pushed" =~ ^sha256:[a-f0-9]{64}$ ]] || { echo "registry reported no digest for $tag" >&2; exit 1; }
            [ -z "$digest" ] || [ "$digest" = "$pushed" ] || { echo "tags of one build resolved to different digests" >&2; exit 1; }
            digest=$pushed
          done <<< "$IMAGE_TAGS"
          echo "digest-${SERVICE}=${digest}" >> "$GITHUB_OUTPUT"
```
The `sed` expression was tested against the real push line from run
39902216424 ("main: digest: sha256:a8c6a22e… size: 2766").

**E-2. Replace the whole `deploy` job** (`ci-cd.yml:296-339`):
```yaml
  deploy:
    name: Deploy to GKE (sandbox)
    runs-on: ubuntu-latest
    needs: [build-images]
    # A v* tag alone is not enough: the founder sets the repo variable
    # BM_DEPLOY_ENABLED=true only after every step in
    # docs/build/deploy/gke-verification-packet.md section C is done.
    if: startsWith(github.ref, 'refs/tags/v') && vars.BM_DEPLOY_ENABLED == 'true'
    environment: sandbox
    concurrency:
      group: deploy-sandbox
      cancel-in-progress: false
    timeout-minutes: 30
    # A job-level block replaces the workflow-level one: restate contents.
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4

      # Installs pinned, checksum-verified helm/kubeconform into .cache/tools
      # and runs the same offline gate as the 'Deploy manifests' workflow.
      - name: Validate chart offline
        run: bash scripts/validate-helm.sh

      - name: Render this exact release (fails on any unfilled REPLACE_ME)
        env:
          DIGEST_GATEWAY: ${{ needs.build-images.outputs.digest-gateway }}
          DIGEST_CORE: ${{ needs.build-images.outputs.digest-core }}
          DIGEST_CHAIN: ${{ needs.build-images.outputs.digest-chain }}
          DIGEST_CONSOLE: ${{ needs.build-images.outputs.digest-console }}
          BM_GCP_PROJECT_ID: ${{ vars.BM_GCP_PROJECT_ID }}
        run: |
          set -euo pipefail
          for d in "$DIGEST_GATEWAY" "$DIGEST_CORE" "$DIGEST_CHAIN" "$DIGEST_CONSOLE"; do
            [[ "$d" =~ ^sha256:[a-f0-9]{64}$ ]] || { echo "missing or malformed image digest from build-images" >&2; exit 1; }
          done
          {
            echo "--namespace=brandme"
            echo "--values=brandme-infra/helm/brandme/values-sandbox.yaml"
            echo "--set-string=gcp.projectId=${BM_GCP_PROJECT_ID}"
            echo "--set-string=images.registry=${REGISTRY}/${GCP_PROJECT_ID}"
            echo "--set-string=images.gateway.digest=${DIGEST_GATEWAY}"
            echo "--set-string=images.core.digest=${DIGEST_CORE}"
            echo "--set-string=images.chain.digest=${DIGEST_CHAIN}"
            echo "--set-string=images.console.digest=${DIGEST_CONSOLE}"
          } > "$RUNNER_TEMP/release-args"
          mapfile -t args < "$RUNNER_TEMP/release-args"
          .cache/tools/bin/helm template brandme brandme-infra/helm/brandme "${args[@]}" > "$RUNNER_TEMP/release.yaml"
          grep -c '^kind: Deployment$' "$RUNNER_TEMP/release.yaml"

      - name: Authenticate to Google Cloud (Workload Identity Federation, no key)
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ vars.BM_GCP_WIF_PROVIDER }}
          service_account: ${{ vars.BM_GCP_DEPLOYER_SA }}
          project_id: ${{ vars.BM_GCP_PROJECT_ID }}

      - name: Get GKE credentials
        uses: google-github-actions/get-gke-credentials@v2
        with:
          cluster_name: ${{ vars.BM_GKE_CLUSTER }}
          location: ${{ vars.BM_GCP_REGION }}
          project_id: ${{ vars.BM_GCP_PROJECT_ID }}

      # Migrations run first as the chart's pre-install/pre-upgrade hook Job
      # (runner.py up); helm stops before any workload changes if it fails.
      # The namespace is created by the founder (packet C-7), not here.
      - name: Migrate, then roll out by digest
        run: |
          set -euo pipefail
          mapfile -t args < "$RUNNER_TEMP/release-args"
          .cache/tools/bin/helm upgrade --install brandme brandme-infra/helm/brandme "${args[@]}" \
            --wait --wait-for-jobs --timeout 15m --history-max 10
          kubectl -n brandme logs job/brandme-migrations --tail=40

      - name: Verify rollout and in-cluster checks
        run: |
          set -euo pipefail
          for d in gateway chain read-api exports-api exports-worker events-worker; do
            kubectl -n brandme rollout status "deployment/brandme-$d" --timeout=5m
          done
          kubectl -n brandme exec deploy/brandme-read-api -- python -m brandme_core.read_api --check
          kubectl -n brandme exec deploy/brandme-exports-worker -- python -m brandme_core.privacy_exports --check
          kubectl -n brandme exec deploy/brandme-events-worker -- python -m brandme_core.events.worker --check

      - name: Diagnostics on failure (no secret values)
        if: failure()
        run: |
          kubectl -n brandme get deploy,pods,jobs -o wide || true
          kubectl -n brandme get events --sort-by=.lastTimestamp | tail -n 60 || true
          .cache/tools/bin/helm -n brandme history brandme --max 5 || true
```
Notes: the agents image is still built and published but no longer deployed
or rolled out (it is a CLI). The job name changes to "Deploy to GKE (sandbox)";
it is skipped on pull requests, so no required check should depend on it.

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

Not verified (needs the cluster or GCP): the cluster itself; Workload Identity
token issuance with `automountServiceAccountToken: false` (G17); NetworkPolicy
behaviour on the real dataplane (G18); the custom roles (G19); secret sync
(C-15 manifests are not schema-validated); the chain image under a read-only
root; any Preprod transaction or finality.
