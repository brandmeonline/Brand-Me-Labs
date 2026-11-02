# Infrastructure inventory — what the repository declares vs. what is applied

Audit date 2026-11-01. HEAD `ed19dc151d103b108cf972e6d37971c55d5dcf60` (= remote main).
Method: static read of `docker-compose*.yml`, `brandme-infra/**`, `infrastructure/**`, every
`Dockerfile`, `deploy-brandme.sh`, `agents/*.sh`, `scripts/*.sh`, `scripts/brandme.mjs`,
`.github/workflows/*.yml`, `.github/scripts/smoke-image.sh`, `init.sql`, `brandme-data/`.
Verification level: **static-only**. Nothing here was rendered with `helm`, applied with
`kubectl`/`terraform`, or started with `docker compose`. "Applied" state for every row is
**unknown** from inside the repository; the repository's own documentation says the chart has
never been deployed (`brandme-infra/README.md:7-11`, `brandme-infra/helm/brandme/Chart.yaml:3-5`).

Legend: **declared** = present as code/config in the repository; **applied** = observed on a live
system (never observable here). Line references are `path:line`.

---

## 1. Local stack — `docker-compose.yml` (242 lines) and `docker-compose.dev.yml`

Compose project name `brandme` (`docker-compose.yml:29`). Port map comment at `:3-10`.
Profiles: default = emulators + migrate + brain + policy + gateway + consumer-domains + consumer;
`--profile legacy` adds orchestrator/knowledge/compliance/identity/governance/cube; `--profile events`
adds NATS (`:24-27`).

| Compose service | Image / build | Ports | Command / healthcheck | Profile | Notes |
|---|---|---|---|---|---|
| `spanner-emulator` | `gcr.io/cloud-spanner-emulator/emulator:1.5.45` (`:75`) | 9010 gRPC, 9020 REST (`:77-78`) | image default; no healthcheck | default | Same tag as CI service containers (`ci-cd.yml:60,137,218`); `consumer-ui.yml:64` pins the older `1.5.28`. |
| `firestore-emulator` | `gcr.io/google.com/cloudsdktool/google-cloud-cli:587.0.0-emulators` (`:82`) | 8080 | `gcloud emulators firestore start --host-port=0.0.0.0:8080` (`:83`); no healthcheck | default | |
| `spanner-migrate` | inline Dockerfile `python:3.11.15-slim` + `scripts/python/requirements.lock` (`:34-38`), image tag `brandme/python-dev:foundation` (`:39`) | — | `python brandme-data/spanner/migrations/runner.py up --create-database --wait 60` (`:96`) | default | One-shot migrations job; every Python service `depends_on` it with `service_completed_successfully` (`:61-63`). Creates instance/database only against the emulator (`runner.py:131-133` per `migrations-job.yaml:6-7`). |
| `brain` | same python image, bind mount `./:/app:ro` (`:41`) | 8000 | `python -m brandme_core.config preflight --service brain && exec uvicorn main:app ...` (`:101`); no healthcheck | default | |
| `policy` | same | 8001 | preflight + uvicorn (`:107`) | default | |
| `orchestrator` | same | 8002 | preflight + `uvicorn worker:app` (`:114`) | legacy | Not Celery; the Celery app (`brandme-core/orchestrator/celery_app.py`) has no compose service and no broker (no Redis service exists). |
| `knowledge` | same | 8003 | (`:121`) | legacy | |
| `compliance` | same | 8004 | (`:128`) | legacy | |
| `identity` | same | 8005 | (`:135`) | legacy | |
| `governance` | same | 8006 | (`:142`) | legacy | |
| `cube` | same | 8007 | `uvicorn src.main:app` (`:149`) | legacy | |
| `node-install` | `node:24.21.0-bookworm-slim` (`:66`) | — | `corepack enable && pnpm install --frozen-lockfile` into named volume `node_modules` (`:155`, `:238`) | default | |
| `gateway` | node image, bind `./:/app` | 3001 (`:181`) | `pnpm --filter @brandme/gateway dev` (`:159`); no healthcheck | default | env at `:160-176`; optional `env_file` for the consumer-domain signing key from `${BRANDME_DEV_ASSERTION_DIR:-$HOME/.config/brandme/dev-keys}/consumer-domains-gateway.env` (`:178-180`, `required: false`). |
| `consumer-domains` | python image, `network_mode: "service:gateway"` (`:200`) | 8010 inside the gateway's namespace, not published (`:9`, `:204`) | refuses to start without `CONSUMER_DOMAIN_ASSERTION_JWKS` (`:211`), then preflight + `python -m brandme_core.domains.persona.app` | default | `env_file` public JWKS (`:208-210`). No `BRANDME_MEDIA_BUCKET` (`:193-194`): media/try-on stay unmounted. |
| `consumer` | node image | 3000 (`:223`) | `pnpm --filter brandme-frontend exec next dev -p 3000` (`:220`) | default | env `BRANDME_GATEWAY_URL: http://gateway:3001` (`:222`). |
| `nats` | `nats:2.10.29-alpine` (`:231`) | 4222, 8222 (`:234`) | `-js -sd /data` | events | Gateway only connects when `NATS_URL` is set (`:174` passes `${NATS_URL:-}`; `brandme-gateway/src/index.ts:89-94`). |
| `console` (dev override) | `node:24.21.0-bookworm-slim` (`docker-compose.dev.yml:24`) | 3002 (`:32`) | `pnpm --filter @brandme/console exec next dev -p 3002` (`:29`) | dev override only | env `BRANDME_GATEWAY_URL: http://gateway:3001` (`:31`). |

Not in compose at all: `brandme-chain`, read API, privacy exports API/worker, outbox events worker,
events retention, consumer-domains Pub/Sub ingress (`brandme_core/domains/persona/ingress.py`),
consumer-domains jobs (`persona/jobs.py`), Redis, Postgres, Neo4j, OpenTelemetry collector,
Prometheus, Loki, Grafana. The `Makefile:78-90` `dev-up` target runs
`docker-compose -f docker-compose.dev.yml up -d` **alone** (without the base file) and prints a port
map (Gateway 3000, Core 8000, Agents 8001, PostgreSQL 5432, NATS 4222) that matches neither compose
file; `docker-compose.dev.yml` is an override and is not self-sufficient (it references the
`node_modules` volume and `brandme_net` network declared only in the base file).

CLAUDE.md `:55` cites `MIDNIGHT_ENABLED: "false"` at `docker-compose.yml:304`; the file has 242
lines and no `MIDNIGHT_ENABLED` anywhere in the repository (grep). Stale claim.

Volumes/networks: named volume `node_modules` (`:237-238`); bridge network `brandme_net` (`:240-242`).
No persistent volumes for the emulators (data is lost on `down`).

## 2. Dockerfiles (14 found)

| Dockerfile | Base | Build context assumed | Exposed port / healthcheck | Default CMD | Used by |
|---|---|---|---|---|---|
| `brandme-gateway/Dockerfile` | `node:${NODE_VERSION}-bookworm-slim` (ARG default 24.21.0, `:2-3`), pnpm 10.34.6 (`:5`) | repo root (`:1`, `COPY . .`) | 3001; `fetch http://127.0.0.1:$PORT/healthz` (`:20-21`) | `node dist/index.js` (`:22`) | `ci-cd.yml:347-348` (context `.`, file `./brandme-gateway/Dockerfile`); Helm `gateway.yaml:46`. **`Makefile:212` and `scripts/deploy.sh:104,119` build with context `./brandme-gateway`, which contradicts `:1` (workspace paths) — would fail or build the wrong tree.** |
| `brandme-chain/Dockerfile` | node 24.21.0 (`:8-9`) | repo root (`:13`) | 3001; `/health` (`:27-28`) | `node dist/src/index.js` (`:29`) | `ci-cd.yml` matrix `chain`; Helm `chain.yaml:46`. Build stage runs `pnpm compact:verify && pnpm compact:compile && pnpm compact:verify && pnpm build` (`:16`). `Makefile:228`/`deploy.sh` use context `./brandme-chain` (same contradiction). |
| `brandme-console/Dockerfile` | node 24.21.0 (`:1-2`) | repo root (`:6`) | 3002; no HEALTHCHECK (smoke-image.sh:124-134 curls `/`) | `node brandme-console/server.js` (standalone) (`:17`) | `ci-cd.yml` matrix `console`; Helm `console.yaml:46`. `NEXT_PUBLIC_*` not passed as build args: the browser bundle keeps `lib/api.ts` localhost defaults (`console.yaml:5-7`). |
| `brandme-core/Dockerfile` | multi-stage; stages `base`/`brain`/`policy`/`orchestrator`/`orchestrator-beat` on `python:3.11-slim` (`:8`), final `runtime` stage `python:3.11.15-slim` (`:89`) | repo root (`:23,27,31,96-102`) | base: `${PORT:-8000}/health` (`:38-39`); runtime: none | runtime: prints usage, exit 64 (`:107`); legacy stages run `uvicorn ... --reload` (`:53,61,69`) | `ci-cd.yml` matrix `core` builds the **last** stage (`runtime`) because no `--target` (`:80-83`); Helm core workloads (`_core.tpl:58`). Legacy stages install `brandme-core/requirements.txt` (unpinned-by-hash, `:23-24`) and run `--reload` (CLAUDE.md/boot.py warn against it). |
| `brandme-core/brain/Dockerfile`, `policy/Dockerfile`, `orchestrator/Dockerfile` | `python:3.11-slim` | service dir, but `COPY ../../brandme_core` (`brain/Dockerfile:10`) | none | uvicorn | Referenced by `Makefile:216-218`. **`COPY ../../...` escapes the build context and cannot work with Docker's classic builder; these Dockerfiles are not buildable as written.** |
| `brandme-agents/Dockerfile` | multi-stage `python:3.11-slim`; stages identity/knowledge/compliance (ports 8100/8101/8102, `:49,57,65`) and `agentic` (`:70-83`; installs `torch==2.14.1` from `download.pytorch.org`, `:80`) | repo root | `${PORT:-8100}/health` | `uvicorn src.main:app` (`:42`); agentic: `python -m agentic.cli.main --help` | `ci-cd.yml` matrix `agents` (builds last stage = `agentic`); `smoke-image.sh:14-17`. Not in Helm. Ports 8100-8102 conflict with compose/CLAUDE.md map (8005/8003/8004). |
| `brandme-agents/{identity,knowledge,compliance}/Dockerfile` | `python:3.11-slim` | service dir with `COPY ../../brandme_core` (`identity/Dockerfile:10`) | none | uvicorn on 8005/8003/8004 | `Makefile:222-224`. Same out-of-context COPY problem. |
| `brandme-governance/Dockerfile` | `python:3.11-slim` | `brandme-governance/` but `COPY ../brandme_core` (`:24`) | `${PORT:-8006}/health` | `uvicorn ... --reload` | nowhere in CI/compose/Helm. Out-of-context COPY. |
| `brandme-governance/governance_console/Dockerfile` | `python:3.11-slim` | `COPY ../../brandme_core` (`:10`) | none | uvicorn 8006 | nowhere. |
| `brandme-cube/Dockerfile` | `python:3.11-slim` | repo root (`:14,17,21`) | 8007 `/health` (`:30`) | `uvicorn src.main:app` (`:36`) | `infrastructure/helm/brandme/templates/cube-service.yaml` (legacy chart) image `gcr.io/brandme/cube:latest`; `Makefile` does not build it. Installs `postgresql-client` (`:7`) although the service reads Spanner. |

No Dockerfile exists for: `brandme-frontend` (consumer app; compose runs `next dev` from the node
image), `brandme_core` read API / exports / workers as separate images (they share the core
`runtime` stage), `brandme-agents/branding`, `brandme_gateway/` (orphan folder).

## 3. CI/CD — `.github/workflows/`

| Workflow | Trigger | What it declares |
|---|---|---|
| `ci-cd.yml` ("Build, Test, and Deploy") | push `main`/`develop`/`v*` tags; PR to main/develop (`:17-26`) | Jobs: `test-gateway` (Spanner emulator service, `:58-62`), `test-frontend`, `test-core` (Spanner + pinned Firestore/Pub/Sub/GCS emulators, `:135-201`), `foundation-check` (`pnpm check` + `pnpm smoke`, `:212-266`), `test-chain`, `security-scan` (Trivy `0.75.0` by digest, `:544,553`; SARIF upload), `build-images` (matrix gateway/core/agents/chain/console; builds from repo root; `smoke-image.sh` verifies; pushes to `gcr.io/lux-realestate-app/brandme-<svc>` only on push to main or `v*` tag via `secrets.GCP_SA_KEY` JSON key, `:364-391`), `deploy` ("Deploy to GKE (sandbox)", `:397-524`): runs only on a `v*` tag **and** repo variable `BM_DEPLOY_ENABLED == 'true'` (`:404`); GitHub Environment `sandbox`; validates chart offline (`validate-helm.sh`), renders `values-sandbox.yaml` with digests from build-images, authenticates with **Workload Identity Federation** (`vars.BM_GCP_WIF_PROVIDER`, `vars.BM_GCP_DEPLOYER_SA`, `:461-466`), gets GKE credentials (`vars.BM_GKE_CLUSTER`, `vars.BM_GCP_REGION`, `vars.BM_GCP_PROJECT_ID`, `:468-473`), `helm upgrade --install brandme brandme-infra/helm/brandme --namespace brandme --wait --wait-for-jobs` (`:482-483`), rollout checks and in-cluster `--check` commands (`:486-497`), one retention Job run (`:502-517`). Workflow-level env `GCP_PROJECT_ID: lux-realestate-app`, `GCP_REGION: us-east1`, `GKE_CLUSTER: brandme-cluster`, `REGISTRY: gcr.io` (`:42-46`); `GCP_REGION` and `GKE_CLUSTER` are never referenced again in the file (declared-unused; deploy uses `vars.BM_*`). |
| `chain-tests.yml` | push/PR on chain paths; `workflow_dispatch` | unit (compactc fetch + compile + vitest), durable-store (Spanner emulator, `BRANDME_MODE: development`, `:82-106`), build-test, security-scan (Trivy secret scan of `brandme-chain/`, `pnpm audit`). No cloud credentials. |
| `consumer-ui.yml` | PR on frontend/console/packages; push to `bench/astra-consumer-ui-20261005` | Playwright shell tests; `live-domains` job starts a dev gateway from a pinned second checkout (`ref: dafd3b16...`, `:79-83`) against Spanner emulator `1.5.28` (`:64`). |
| `deploy-validate.yml` ("Deploy manifests") | push main / PR on `brandme-infra/**`, `brandme_core/**`, lock | `bash scripts/validate-helm.sh` with `BRANDME_PYTHON: python` (`:65-69`). Offline only (`:3-8`). |
| `module-regression.yml` | push/PR main/develop; dispatch | `scripts/regression/run_all.sh` over 11 modules (`run_all.sh:8-20`); `brandme_gateway.sh:8` injects legacy `OAUTH_CLIENT_ID`/`OAUTH_CLIENT_SECRET`/`JWT_SECRET` test values that the gateway ignores/refuses. |
| `spatial-validation.yml` | PR main on spatial paths; push to `bench/astra-spatial-ar-20261005` | asset validation, Playwright with local MediaPipe inference (`scripts/assets/prepare-vision.py` downloads the pose model from `storage.googleapis.com`, `prepare-vision.py:18`). |
| `workspace-guard.yml` | every PR; push main | `scripts/check-workspace.mjs --with-pnpm`. |

GitHub identity: one repository **secret** name (`GCP_SA_KEY`, `ci-cd.yml:368`, long-lived JSON key for
image push — the credential manifest marks it "retire", `credential-manifest.yaml:226-241`); six repository
**variables** (`BM_DEPLOY_ENABLED`, `BM_GCP_PROJECT_ID`, `BM_GCP_WIF_PROVIDER`, `BM_GCP_DEPLOYER_SA`,
`BM_GKE_CLUSTER`, `BM_GCP_REGION`). Whether any of these exist in GitHub is **unknown** (not observable).
`scripts/provision/gcp-dev-identities.sh:465-468` also prints `BM_GCP_PUSH_WIF_PROVIDER` for a separate
image-push pool, which no workflow consumes.

## 4. Current Helm chart — `brandme-infra/helm/brandme/` (declared; **never deployed** per its own README)

Chart `brandme` 0.1.0, `kubeVersion >=1.33.0-0` (`Chart.yaml:10-12`). Validated offline by
`scripts/validate-helm.sh` (helm 3.22.1 + kubeconform 0.8.0 pinned by SHA-256, Kubernetes 1.35/1.36
schemas, negative render tests `:251-283`). Render-time guards: `mode` must be sandbox|production
(`_helpers.tpl:60-66`); any `REPLACE_ME` fails (`validate.yaml:5-7`); images need a `sha256:` digest or an
immutable tag, `latest` refused (`_helpers.tpl:76-99`); Midnight `mainnet` refused (`_helpers.tpl:126-132`);
production with chain/read-api/exports enabled refused (`validate.yaml:9-11`).

Workloads (`README.md:15-26`, templates):

| Component | Kind | Image | Command | Port / probes | KSA → GSA (sandbox values) | Env (names) |
|---|---|---|---|---|---|---|
| gateway | Deployment ×2 | `images.gateway` | `node dist/index.js` (`gateway.yaml:46`) | 3001; startup/readiness/liveness `GET /healthz` (`:111-124`) | `brandme-gateway` → `bm-sbx-fnd-gateway` (`values-sandbox.yaml:38`) | BRANDME_MODE, ENVIRONMENT, PORT, LOG_LEVEL, DEFAULT_REGION, IDENTITY_PROVIDER=oidc, OIDC_ISSUER, OIDC_AUDIENCE, [OIDC_JWKS_URI], [OIDC_ALGORITHMS], PUBLIC_ORIGINS, CORS_ORIGINS, [TRUST_PROXY], SPANNER_*; conditional CHAIN_SERVICE_URL + CHAIN_SERVICE_TOKEN(secretKeyRef), RIGHTS_SERVICE_URL, PRIVACY_SERVICE_URL, RIGHTS_SERVICE_TOKEN, PRIVACY_SERVICE_TOKEN, PRIVACY_EXPORT_SERVICE_URL, PRIVACY_EXPORT_SERVICE_TOKEN, CONSUMER_DOMAIN_SERVICE_URL, CONSUMER_DOMAIN_ASSERTION_KID, CONSUMER_DOMAIN_ASSERTION_KEY(secretKeyRef) (`gateway.yaml:51-110`). **`BRAIN_SERVICE_URL` is not set**, so `/api/v1/system/health` calls the code default `http://localhost:8000/health` (`config/index.ts:85`, `routes/v1/index.ts:73-78`) and will report `degraded`/503 in-cluster; kubelet probes use `/healthz` so pods still pass. |
| chain | Deployment ×1 | `images.chain` | `node dist/src/index.js` | 3001; `GET /health` | `brandme-chain` → `bm-sbx-rts-chain` | BRANDME_MODE, ENVIRONMENT, PORT, LOG_LEVEL, CHAIN_RECONCILIATION_ENABLED, MIDNIGHT_NETWORK, [MIDNIGHT_CONTRACT_ADDRESS], SPANNER_*, CHAIN_SERVICE_TOKEN(secret), MIDNIGHT_BLOCKFROST_PROJECT_ID(secret, preprod only) (`chain.yaml:51-72`) |
| console | Deployment ×2 (disabled in `values-sandbox.yaml:52-53`) | `images.console` | `node brandme-console/server.js` | 3002; `GET /` | `brandme-console`, no GSA (`serviceaccounts.yaml:37-45`) | BRANDME_MODE, ENVIRONMENT, PORT, HOSTNAME, NEXT_TELEMETRY_DISABLED (`console.yaml:51-61`). No `BRANDME_GATEWAY_URL`/`BRANDME_GATEWAY_INTERNAL_URL`: the console's server-side gateway calls would answer "not connected". |
| read-api | Deployment ×2 | `images.core` | `python -m brandme_core.read_api` | 8000; startup/readiness `GET /health`, liveness TCP (`_core.tpl:77-91`) | `brandme-read-api` → `bm-sbx-rts-read-api` | mode env, SPANNER_*, PORT, READ_API_NETWORK, READ_API_CONTRACT_ADDRESS, RIGHTS_SERVICE_TOKEN, PRIVACY_SERVICE_TOKEN (`core-workloads.yaml:17-27`) |
| exports-api | Deployment ×2 | core | `python -m brandme_core.privacy_exports` | 8000 | → `bm-sbx-rts-export-api` | + EXPORT_NETWORK, EXPORT_CONTRACT_ADDRESS, EXPORT_BUCKET, PRIVACY_EXPORT_SERVICE_TOKEN (`:29-40`) |
| exports-worker | Deployment ×1, no probes, `minReadySeconds: 30` (`_core.tpl:31-35`) | core | `python -m brandme_core.privacy_exports --worker` | — | → `bm-sbx-rts-export-wkr` | same export env (`:41-45`) |
| events-worker | Deployment ×1 | core | `python -m brandme_core.events.worker` | — | → `bm-sbx-fnd-outbox` | OUTBOX_PUBSUB_TOPIC_PUBLIC/_MEMBER_PRIVATE/_RESTRICTED as `projects/<p>/topics/<t>`, [OUTBOX_EVENT_TYPES] (`:47-61`) |
| consumer-domains | Deployment ×1 (on in sandbox values) | core | `python -m brandme_core.domains.persona.app` | 8010; `GET /health` | KSA `brandme-consumer-domains-api` → `bm-sbx-dom-api` | PORT, CONSUMER_DOMAIN_ASSERTION_ISSUER, CONSUMER_DOMAIN_ASSERTION_JWKS (compact JSON of public keys), [BRANDME_MEDIA_BUCKET] (`:62-78`) |
| events-retention | CronJob `17 * * * *` UTC, `concurrencyPolicy: Forbid` (`:86-100`) | core | `python -m brandme_core.events.retention --once` | — | → `bm-sbx-fnd-retention` | mode env + SPANNER_* |
| migrations | Job, `helm.sh/hook: pre-install,pre-upgrade`, `backoffLimit: 0` (`migrations-job.yaml:50-67`) | core | `python brandme-data/spanner/migrations/runner.py up` | — | hook ServiceAccount → `bm-sbx-fnd-migrator` | mode env + SPANNER_* |

Also declared: ServiceAccounts per workload with `iam.gke.io/gcp-service-account` annotations
(`serviceaccounts.yaml`); PodDisruptionBudgets `maxUnavailable: 1` (`pdb.yaml`); default-deny
NetworkPolicy plus per-workload allows (gateway → chain/read-api/exports-api/consumer-domains; DNS;
GKE metadata server 169.254.169.252/254; HTTPS egress 0.0.0.0/0 except RFC1918/CGNAT/link-local;
load-balancer ranges only when ingress is on) (`networkpolicy.yaml`, `values.yaml:272-308`); optional GKE
Ingress with `BackendConfig`, `ManagedCertificate`, `FrontendConfig` HTTPS redirect, global static IP
(`ingress.yaml`), **disabled by default** (`values.yaml:312-313`, `values-sandbox.yaml:105-106`).
Secrets: never rendered; only `secretKeyRef` to Kubernetes Secrets named in `secretRefs`
(`values.yaml:65-88`), expected to be synced from Google Secret Manager by an add-on/ESO that the chart
does **not** install (`values.yaml:8-11`). Hardening: non-root UIDs 1000/10001, `RuntimeDefault` seccomp,
read-only root FS with `emptyDir /tmp`, all capabilities dropped (`_helpers.tpl:221-235`).

Not in this chart: brain, policy, orchestrator, knowledge, compliance, identity, governance, cube
(refuse strict modes; `README.md:37-40`); the consumer frontend; the persona Pub/Sub ingress and jobs
processes (`README.md:34-35`: "not in the chart yet"); any Spanner instance/database, Pub/Sub topic,
bucket, Secret Manager secret, IAM binding, or the cluster itself (founder/gcloud actions,
`README.md:5-7`).

Sandbox values that are placeholders (`values-sandbox.yaml`): `gcp.projectId` (`:16`),
`midnight.contractAddress` (`:27`), OIDC issuer/audience (`:41-42`), public origin (`:45`), export bucket
suffix (`:66`), consumer-domain kid and public JWK (`:77-80`). Rendering fails while any remains.

## 5. GCP provisioning scripts (declared; dry-run by default)

`scripts/provision/gcp-dev-identities.sh` (475 lines): **prints** gcloud commands unless `--apply`
(`:8-9`). With `--apply` it first requires the Spanner database, three outbox topics, the export bucket
and the Artifact Registry repo to already exist (`:263-268`); it never creates the data plane or the
cluster (`:12-15`). It declares: API enablement (iam, iamcredentials, sts, secretmanager, spanner,
pubsub, storage, artifactregistry, container, cloudresourcemanager; `:271-273`); custom roles
`brandmeSpannerDataReadWrite`, `brandmeOutboxPublisher`, `brandmeExportObjectReader`,
`brandmeExportObjectWriter` (`:291-294`); per-lane GSAs `bm-sbx-*` with `roles/iam.workloadIdentityUser`
bindings for KSA members (`:319-324`); Spanner database IAM (`fnd-migrator` databaseUser,
`rts-read-api` databaseReader, others custom RW; `:328-337`); topic publisher bindings (`:342`); export
bucket reader/writer (`:347-349`); empty Secret Manager containers with accessor bindings
(`:369-375`); Artifact Registry writer for `fnd-pusher`, `container.clusterViewer` for `fnd-deployer`
(`:388-391`); Workload Identity Federation pools/providers for GitHub (`github-deploy`, `github-push`;
`:424-439`) with `attribute.repository_id` conditions; optional projector/Firestore and media-bucket
grants (`:448-460`). Applied state: **unknown**.

## 6. Legacy / non-functional infrastructure still in the tree

| Path | What it declares | Status per repository evidence |
|---|---|---|
| `brandme-infra/helm/brandme-umbrella/` | Umbrella chart depending on `file://../charts/brandme-{gateway,core,agents,chain,console}` (`Chart.yaml:10-34`); values with `gcr.io/brandme-prod` registry and `latest` tag (`values.yaml:9-11`), Cloud SQL proxy DB at 127.0.0.1:5432 (`:21`), NATS `nats://nats:4222` (`:31`), gateway on port 3000 with `OAUTH_CLIENT_ID`/`OAUTH_CLIENT_SECRET`/`JWT_SECRET` from Secrets `oauth-secrets`/`jwt-secret` (`:73-89`), chain wallet keys from Secret `wallet-secrets` (`:174-181`), console ingress `console.brandme.com` with cert-manager (`:208-221`). | **Non-functional**: subcharts directory does not exist (`LEGACY.md:10-13`); `values-prod.yaml` does not exist (`LEGACY.md:14-16`). Still targeted by `Makefile:260-282` (`deploy-dev`/`deploy-prod` with `values-dev.yaml`/`values-prod.yaml`) and `agents/service-agent.sh:117-123`. |
| `brandme-infra/terraform/main.tf` | GCS backend bucket `brandme-terraform-state` (`:16-19`); VPC + subnet with pods/services ranges (`:51-71`); GKE cluster `brandme-cluster-${env}` with Workload Identity pool (`:77-111`), node pool `e2-standard-4` ×3 autoscaling 3-10 (`:113-146`); Cloud SQL PostgreSQL 15 `brandme-postgres-${env}` with private IP + `require_ssl` (`:152-182`); database `brandme`, user `brandme` with `var.db_password` (`:184-193`); bucket `brandme-passport-blobs-${env}` (`:199-229`); single GSA `brandme-workload-${env}` with `roles/cloudsql.client` and `storage.objectAdmin` (`:235-250`). | **Fails `terraform validate`**: `var.db_password` used at `:192` but never declared (`brandme-infra/README.md:25`). Provisions Cloud SQL (unused by current code) and none of Spanner/Pub/Sub/Secret Manager. `agents/infrastructure-agent.sh:31-39` writes a `terraform.tfvars` with variables (`cluster_name`, `node_count`, `machine_type`, `db_tier`, `enable_autoscaling`) that `main.tf` does not declare, and reads outputs (`cluster_name`, `db_private_ip`, `bucket_name`, `:53-55`) that `main.tf` does not define (it defines `gke_cluster_name`, `cloudsql_connection_name`, `gcs_bucket_name`). |
| `infrastructure/helm/brandme/` | Second chart named `brandme` with Bitnami postgresql/redis, prometheus, grafana dependencies (`Chart.yaml:17-33`); values for gateway (`gcr.io/brandme/gateway:latest`, LoadBalancer port 80 → 3000, nginx ingress `api.brandme.io` with cert-manager, `:16-63`), brain/policy/identity(8100)/knowledge(8101)/compliance(8102)/cube/chain/orchestrator worker+beat, postgresql 100Gi, redis, NATS JetStream, prometheus, grafana, istio off, external-secrets `gcpSecretsManager` project `brandme-prod` (`:338-343`). Only one template: `templates/cube-service.yaml` (Deployment + Service for cube with `DATABASE_URL` from Secret `brandme-secrets`, probes `/health/live`, `/health/ready`). | Only the cube template exists; every other values block has no template. The `brandme.fullname`/`brandme.labels` helpers it includes are not defined in this chart (no `_helpers.tpl`), so even the cube template cannot render. Used by `scripts/deploy.sh:158-164`. |
| `infrastructure/kubernetes/namespace.yaml` | Namespaces `brandme`, `brandme-staging`, `observability`. | Not referenced by any workflow or script. |
| `infrastructure/otel-collector/otel-collector-config.yml` | OTLP gRPC 4317 / HTTP 4318 receivers; exporters to Prometheus 8889, Loki `http://loki:3100`, Tempo `tempo:4317` (insecure), file `/data/otel-traces.json`; `${env:ENVIRONMENT}`, `${env:REGION}`. | No compose/Helm service runs a collector; no application sets an OTLP endpoint (`TelemetrySetup.configure` has no callers). Orphan. |
| `infrastructure/prometheus/prometheus.yml`, `rules/alerts.yml` | Scrape targets `gateway:3000`, `brain:8000`, `policy:8001`, `identity:8100`, `knowledge:8101`, `compliance:8102`, `chain:3001`, `postgres-exporter`, `redis-exporter`, `nats:7777`, `celery-exporter`, `node-exporter`, `cadvisor`, `otel-collector`; alerts on `brandme_*`, `pg_*`, `celery_*`, `redis_*` metrics. | No Prometheus service anywhere; target names/ports do not match the current compose map (gateway is 3001; identity/knowledge/compliance are 8005/8003/8004). Orphan. |
| `infrastructure/loki/loki-config.yml`, `infrastructure/redis/redis.conf` | Loki filesystem single-binary; Redis with `requirepass ${REDIS_PASSWORD}` (`redis.conf:10`) and renamed FLUSHDB/FLUSHALL/CONFIG. | No service mounts either file. `REDIS_PASSWORD` is declared nowhere else. Orphan. |
| `init.sql` (root) | PostgreSQL tables `scan_event`, `chain_anchor`, `audit_log`, `cubes`, `cube_face_access_log` with JSONB/GIN indexes and an `updated_at` trigger; `GRANT ALL ... TO postgres` (`:112`). | No compose service, script, Dockerfile or workflow references `init.sql` (grep). Current services use Spanner migrations (`brandme-data/spanner/migrations/V001..V015`). Orphan. |
| `brandme-data/schemas/*.sql`, `seeds/*.sql`, `scripts/db-init.sh`, `scripts/backup.sh`, `scripts/test-infrastructure.sh` | Postgres schema/seed application via `psql` to `DB_HOST:5432` (`db-init.sh:23-27`), `pg_dump` backups with optional `BACKUP_BUCKET` upload left as a TODO (`backup.sh:65-71`), infra smoke tests against Postgres/Redis/NATS/Prometheus/Grafana/Loki/OTel and `localhost:3000` gateway (`test-infrastructure.sh:46-108`). | Postgres is not part of any current stack definition. `Makefile:104-123` calls `brandme-data/manage.py`, which does not exist (`ls brandme-data`). Legacy. |
| `scripts/deploy.sh` | Builds `brandme/*:latest` images with per-service contexts (`:103-125`), `alembic upgrade head` if `brandme-data/alembic.ini` exists (it does not), `docker-compose up` for development, `helm upgrade --install brandme ./infrastructure/helm/brandme` for staging/production (`:158-164`), health checks on `localhost:3000` (`:176`). Registry push is a TODO (`:225-229`). | Legacy; points at the non-rendering `infrastructure/helm` chart and wrong gateway port. |
| `deploy-brandme.sh` + `agents/*.sh` | "One-click" GKE deployment: `source .env.deploy`, requires `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `BLOCKFROST_API_KEY`, `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_CREDENTIALS_PATH` (`deploy-brandme.sh:61-68`); `gcloud auth activate-service-account --key-file` (`infrastructure-agent.sh:15`); terraform apply (`:41-50`); Cloud SQL database/user creation with a generated password and `cloud_sql_proxy` (`database-agent.sh:21-51`); Neo4j Enterprise via `helm.neo4j.com` with `acceptLicenseAgreement=yes` (`:66-76`); NATS via `nats-io` chart; Bitnami Redis with `auth.enabled=false` (`:113-115`); writes plaintext credentials to `.deployment/database.env` (`:124-134`) and `.deployment/credentials.txt` (`validation-agent.sh:71-97`); builds each service with context `cd $service && docker build .` and pushes `gcr.io/$GCP_PROJECT_ID/<service>:latest` (`service-agent.sh:32-43`); `kubectl create secret generic brandme-secrets` from literals including API keys (`:54-61`); deploys the non-functional umbrella chart with a generated `values-prod.yaml` (`:72-123`); NATS streams `SCAN_EVENTS`/`POLICY_EVENTS` (`integration-agent.sh:22-36`). | Every step sources `agents/lib/common.sh` and `agents/lib/show-access-info.sh` (`deploy-brandme.sh:220`, `agents/*-agent.sh:9`), and `agents/lib/` **does not exist** (`ls agents`). The scripts cannot run as committed. CLAUDE.md's kill-list says `agents/` is "DO NOT DELETE" because `deploy-brandme.sh` uses it; both are inoperable. |
| `Makefile` | `build-*`/`push-*` to `gcr.io/brandme/*` (`:212-254`; a third registry/project distinct from `lux-realestate-app` and `brandme-prod`); `deploy-dev`/`deploy-prod` to the umbrella chart with non-existent values files (`:260-282`); `infra-*` terraform targets (`:310-332`); `install-core` expects `brandme-core/requirements-dev.txt` (does not exist, `:60`); `lint-core` expects `brandme-core/src/` (does not exist). | Partially legacy. `test`, `test-core`, `test-gateway`, `test-chain` targets are current. |

## 7. Code services with no deployment definition (declared in code only)

| Process | Entry point | Deployment definition found |
|---|---|---|
| Consumer-domains Pub/Sub ingress (lane subscriber) | `brandme_core/domains/persona/ingress.py:282` (`LANE_PUBSUB_SUBSCRIPTION`) | none (not in compose, Helm, or CI) |
| Consumer-domains scheduled jobs (try-on/media purge/fulfillment) | `brandme_core/domains/persona/jobs.py:90` | none (`helm/brandme/README.md:34-35` says "not in the chart yet") |
| Consumer-domains outbox worker | `brandme_core/domains/persona/outbox_worker.py:23` | none |
| Commerce domain HTTP API | `brandme_core/domains/commerce/http_api.py` (class-based; no `__main__`) | none; the gateway router that would front it is marked UNMOUNTED (`brandme-gateway/src/routes/v1/commerce.ts:4`) |
| MCP tool executor | `brandme_core/mcp/tools.py`, `authz.py` | no server entry point (no FastMCP/stdio/HTTP mount found); CLAUDE.md lists "mcp-server" among services not running — none is defined anywhere |
| Celery orchestrator worker/beat | `brandme-core/orchestrator/celery_app.py`, `tasks.py` | Dockerfile stage `orchestrator-beat` only; no broker service; not in compose/Helm |
| Agentic CLI | `brandme-agents/agentic/cli/main.py` | image stage `agentic` built by CI (`ci-cd.yml` matrix `agents` = last stage); CLI only, not a service |
| Branding engine | `brandme-agents/branding/src/graph_engine.py` ("Not wired into any service", `:60`) | none |
| Governance console | `brandme-governance/governance_console/main.py` | compose `legacy` profile only; Dockerfiles not buildable (out-of-context COPY) |

## 8. Services referenced by deployment definitions with no code or no Dockerfile

- `infrastructure/helm/brandme/values.yaml` images `gcr.io/brandme/core`, `gcr.io/brandme/agents` and ports 8100-8102, orchestrator `worker`/`beat` blocks: no templates exist for them (section 6).
- `brandme-infra/helm/brandme-umbrella/Chart.yaml` subcharts `brandme-gateway`, `brandme-core`, `brandme-agents`, `brandme-chain`, `brandme-console`: directories absent.
- `infrastructure/prometheus/prometheus.yml` exporters `postgres-exporter`, `redis-exporter`, `celery-exporter`, `node-exporter`, `cadvisor`, `alertmanager`; `otel-collector` exporters `loki`, `tempo`: no definitions anywhere.
- `agents/service-agent.sh:15-21` lists `brandme-core` and `brandme-agents` as services with a Dockerfile at `cd $service && docker build .`; both Dockerfiles require the repository root as context (`brandme-core/Dockerfile:23,27`, `brandme-agents/Dockerfile:21,25`).
- `brandme-infra/helm/brandme/values.yaml:60-63` `images.console` is built by CI, but the console is disabled in sandbox values and, when enabled, receives no gateway URL.

## 9. Directories not reviewed line-by-line

`brandme-frontend/public/**`, `brandme-frontend/features/**` (other than `spatial/server/photoService.ts`),
`brandme-console/app/**` pages other than those cited, `brandme-chain/contracts/managed/**` (compiler
output), `packages/**/generated/**`, `docs/**` other than `docs/build/security/credential-manifest.yaml`
(read for cross-check only; `docs/audits/**` was not read as instructed), `scripts/assets/**` beyond the
files cited, `tests/**` (read only for env-name discovery), `brandme_core/zk/**`, `brandme_core/spanner/**`
beyond `client.py`/`pool.py` lines cited, `brandme_core/firestore/**` beyond `client.py`.
