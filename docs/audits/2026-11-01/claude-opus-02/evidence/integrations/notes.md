# Integrations / configuration evidence — top findings

Audit date 2026-11-01. HEAD `ed19dc151d103b108cf972e6d37971c55d5dcf60`. Static evidence only (grep + read);
nothing was executed, rendered or deployed. Companion files: `config-matrix.json` (216 entries: 113 consumed+declared,
78 consumed-undeclared, 25 declared-unconsumed; 34 classified `secret`), `integration-matrix.json` (40 integrations,
`S2-INT-001`…`S2-INT-040`: 11 mounted, 15 not-mounted, 4 cli-only, 3 test-only, 7 unknown/unobservable), `infrastructure-inventory.md`,
`commands.log`. Every claim below cites `path:line`; quotes are ≤120 chars. Variable **names** only, never values.

## 1. Consumed in code but declared nowhere (no `.env.example`, compose, Helm, workflow or script)

Grouped by the process that reads them. "Declared nowhere" was checked across `docker-compose*.yml`, every
`*.env.example`, `brandme-infra/**`, `infrastructure/**`, `.github/workflows/*.yml`, `Makefile`,
`deploy-brandme.sh`, `agents/*.sh`, `scripts/**` (tests excluded as declarations).

- **Gateway** (`brandme-gateway/src/config/index.ts`): `RATE_LIMIT_IP_MAX_REQUESTS` (`:168`), `RATE_LIMIT_MAX_KEYS` (`:169`).
  Operational knobs with defaults; harmless but invisible to operators.
- **Guard-only legacy flags** read to refuse boot: `ENABLE_STUB_MODE`, `MIDNIGHT_FALLBACK_MODE`, `CARDANO_FALLBACK_MODE`,
  `ZK_ALLOW_STUB_FALLBACK`, `ALLOW_STUB_FALLBACK` (`brandme_core/config.py:226-232`, `brandme-gateway/src/middleware/mode.ts:27`,
  `brandme-chain/src/config/index.ts:33-37`). No code path in the current tree enables a stub from them (grep of `brandme_core/zk`
  finds no reader), so they are inert except as a refusal trigger.
- **Foundation processes**: `STORAGE_EMULATOR_HOST` (`brandme_core/domains/media/gcs_store.py:334`), `EXPORT_STORAGE_EMULATOR_HOST`
  (`brandme_core/privacy_exports/config.py:27`), `PUBSUB_EMULATOR_HOST` (`brandme_core/events/worker.py:43-47`,
  `brandme_core/domains/persona/ingress.py:272-279`) are **required** in demo/development yet appear in no compose file; only
  tests set them. Consequence: the outbox worker, exports API/worker and persona ingress cannot be started from the committed
  compose stack in development (compose has no Pub/Sub or GCS emulator service; `docker-compose.yml:193-194` says so for media).
- **`LANE_PUBSUB_SUBSCRIPTION`** (`brandme_core/domains/persona/ingress.py:276`): the consumer-domains Pub/Sub subscriber has a
  `__main__` (`:282`) but no compose service, Helm workload, CI job or declared subscription name anywhere.
- **`BRANDME_TRYON_PROVIDER`** (`brandme_core/domains/media/providers.py:94`, `brandme_core/config.py:527`): only `simulated` is
  known; the chart omits it on purpose (`core-workloads.yaml:65`).
- **Assistant / commerce (dev-only, not mounted)**: `BRANDME_DEV_ANTHROPIC_API_KEY` (`model_planner.py:53`, `graph_engine.py:62`),
  `BRANDME_ASSISTANT_PLANNER|MODEL|EFFORT|EGRESS_PROXY|CA_BUNDLE` (`model_planner.py:54-58`), `BRANDME_COMMERCE_PAYMENTS`
  (`composition.py:38`), `STRIPE_TEST_SECRET_KEY`, `STRIPE_TEST_WEBHOOK_SECRET`, `STRIPE_TEST_WEBHOOK_SECRET_PREVIOUS`,
  `BRANDME_STRIPE_EGRESS_PROXY`, `BRANDME_STRIPE_CA_BUNDLE`, `STRIPE_LOG` (`stripe_test.py:54-55`, `composition.py:39-40`),
  `BRANDME_LOG_REF_KEY` (`brandme_core/mcp/refs.py:26`), `BRANDME_LOG_PSEUDONYM_KEY` (`brandme_core/logging.py:68`).
  Secret-shaped names are listed in `docs/build/security/credential-manifest.yaml` (checked by `scripts/check-credential-manifest.mjs`),
  so this is deliberate for secrets; the non-secret settings simply have no template.
- **Legacy Python services**: `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` (`brandme-core/orchestrator/celery_app.py:30-31`,
  defaults `redis://redis:6379/*` with no Redis anywhere); `ENABLE_STRICT_VALIDATION` (`brandme_core/config.py:69`);
  `SPANNER_MIN_SESSIONS`/`PING_INTERVAL`/`ACQUIRE_TIMEOUT`/`ENABLE_BACKPRESSURE` (`brandme_core/spanner/pool.py:265-269`);
  `HTTP_TIMEOUT` … `HTTP_POOL_MAXSIZE` (`brandme_core/config.py:50-54`); `ENABLE_MOLECULAR_DATA`, `AR_SYNC_ENABLED`,
  `AR_SYNC_LATENCY_TARGET_MS` (`brandme-cube/src/main.py:62-64`); `ZK_PROOF_ENABLED`, `ZK_PROOF_CACHE_TTL_MINUTES`
  (`brandme-agents/identity/src/main.py:30-31`); `BRAIN_URL` (`brandme-agents/agentic/orchestrator/agents.py:15`);
  `NEO4J_USERNAME`, `NEO4J_DATABASE`, `NEO4J_READONLY_*`, `NEO4J_WRITER_*` (`brandme-agents/branding/src/database.py:72-90`).
- **Frontend / console**: `NEXT_PUBLIC_BRANDME_MODE` (ten pages, e.g. `brandme-frontend/app/add/page.tsx:5`; also
  `features/spatial/server/photoService.ts:36`) — the browser-side mode gate is declared in no template, compose service or image
  (the consumer app has no Dockerfile at all); `NEXT_PUBLIC_API_URL` (`brandme-frontend/lib/api.ts:36`, dead code: no importer);
  `BRANDME_GATEWAY_INTERNAL_URL` (`brandme-console/app/(ops)/moderation/_lib/ops-gateway.ts:32`); `BRANDME_AR_DEVICE_TEST`;
  `BRANDME_PHOTO_DEV_ENABLED|PROJECT|REGION`, `BRANDME_VERTEX_ACCESS_TOKEN`, `BRANDME_PHOTO_RETENTION_NOTICE`
  (`photoService.ts:33-41`).
- **Chain tests/tooling**: `MN_PREPROD_SEEDS` (`brandme-chain/scripts/test-midnight-preprod.mjs:7`) — the manifest designates a
  GitHub Environment secret, but no workflow references it; `COMPACT_HOME`, `SKIP_ZK`, `PROOF_SERVER_CA_BUNDLE`.
- **CI variables used but never produced by the provisioning script**: `BM_GCP_DEPLOYER_SA`, `BM_GKE_CLUSTER`, `BM_GCP_REGION`
  (`ci-cd.yml:465,471,472`); `gcp-dev-identities.sh:465-468` prints only `BM_GCP_WIF_PROVIDER` and `BM_GCP_PUSH_WIF_PROVIDER`.

## 2. Declared but consumed by nothing

- **Whole legacy deploy surface** (`.env.deploy.example`, `deploy-brandme.sh`, `agents/*.sh`): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `BLOCKFROST_API_KEY` are *required* by `deploy-brandme.sh:61-68` and written into a Kubernetes Secret
  (`agents/service-agent.sh:54-61`) but **no application code reads any of them** — the planner reads
  `BRANDME_DEV_ANTHROPIC_API_KEY`, GraphRAG is disabled (`brandme-agents/agentic/graph_rag.py:30-31`), and the chain uses
  `MIDNIGHT_BLOCKFROST_PROJECT_ID`. Also unread: `CARDANO_NETWORK`, `CLUSTER_SIZE`, `ENABLE_MONITORING|LOGGING|BACKUPS`,
  `SCRAPE_FASHION_DATA`, `CONTAINER_REGISTRY`, `K8S_NAMESPACE`, `GATEWAY_CPU|MEMORY`, `AGENT_CPU|MEMORY`, `SSL_CERT_PATH`,
  `SSL_KEY_PATH`, `GRAFANA_PASSWORD`, `ENABLE_ANALYTICS_AGENT|REAL_BLOCKCHAIN|GRAPH_RAG|HUMAN_APPROVAL`
  (`.env.deploy.example:30-140`, `brandme-agents/agentic/.env.example:24-26`). The scripts themselves are inoperable:
  every agent sources `agents/lib/common.sh`, which does not exist (`agents/*-agent.sh:9`; `ls agents`).
- **Postgres**: `DATABASE_URL` (`brandme-core/.env.example:4`, `brandme-cube/.env.example:2`, `brandme-data/.env.example:7`,
  `infrastructure/helm/brandme/templates/cube-service.yaml:28-32`), `DATABASE_POOL_*` (`brandme-data/.env.example:10-12`),
  `init.sql`, `brandme-data/schemas`, `scripts/db-init.sh`, `scripts/backup.sh`, terraform Cloud SQL. No `asyncpg`/`sqlalchemy`
  import exists (grep). The legacy cube Helm template injects `DATABASE_URL` into a service that reads Spanner.
- **Redis**: `REDIS_URL` (`brandme-core/.env.example:7`, `brandme-cube/.env.example:5`), `REDIS_PASSWORD`
  (`infrastructure/redis/redis.conf:10`). Celery reads `CELERY_BROKER_URL`, not `REDIS_URL`.
- **OpenTelemetry**: `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME` (`brandme-core/.env.example:22-23`), `OTLP_ENDPOINT`,
  `ENABLE_TRACING` (`brandme-cube/.env.example:18-19`), `REGION` (`otel-collector-config.yml:68`). `TelemetrySetup.configure`
  has no callers (grep); `brandme-cube/src/main.py:203` says the telemetry import "always failed".
- **OAuth/NextAuth**: `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `JWT_SECRET` in `brandme-infra/helm/brandme-umbrella/values.yaml:75-89`
  and `scripts/regression/modules/brandme_gateway.sh:8`; the gateway ignores the OAuth names and **refuses** `JWT_SECRET`
  (`mode.ts:62`, `brandme-gateway/.env.example:10-11`). `next-auth@4.24.15` is a console dependency with zero imports (grep).
- **Workflow env never referenced**: `GKE_CLUSTER`, `GCP_REGION` (`.github/workflows/ci-cd.yml:44-45`); the deploy job uses `vars.BM_*`.
- `NEXT_PUBLIC_APP_NAME` / `NEXT_PUBLIC_APP_VERSION` (`brandme-console/next.config.js:20-21`): no component reads them.
- `SERVICE_NAME` in nine Dockerfile stages; no code reads it. `AGENT_LOG_LEVEL`, `AGENT_TIMEOUT` (`brandme-agents/agentic/.env.example:20-21`).
- `KNOWLEDGE_URL` is declared for cube (`brandme-cube/.env.example:12`) but cube does not read it; the agentic CLI does.

## 3. Inconsistent names / defaults for the same concept

| Concept | Names / defaults | Evidence |
|---|---|---|
| GCP project | `SPANNER_PROJECT_ID` (code), `FIRESTORE_PROJECT_ID`, `GCP_PROJECT_ID` (CI env, hardcoded `lux-realestate-app`), `BM_GCP_PROJECT_ID` (CI var), `gcp.projectId` (Helm) | `ci-cd.yml:43,438`; `brandme_core/config.py:40,47` |
| Spanner project default | `'test-project'` vs `'brandme-project'` | `brandme_core/config.py:40`, gateway `config/index.ts:94` vs `brandme_core/spanner/client.py:163`, `pool.py:262`, `brandme-agents/identity/src/main.py:92`, `brandme-core/policy/main.py:71` |
| Firestore project default | `'test-project'` / `'brandme-dev'` / `'brandme-project'` | `brandme_core/config.py:47`, `brandme_core/env.py:61`, `brandme_core/firestore/client.py:181` |
| Region | `DEFAULT_REGION` (gateway, `brandme-data/.env.example:18`) vs `REGION_DEFAULT` (Python services) vs `GCP_REGION`/`BM_GCP_REGION` (CI) vs `REGION` (otel) | `config/index.ts:163`; `brandme-core/brain/main.py:33`; `ci-cd.yml:44,472` |
| Service URLs | `*_SERVICE_URL` (brandme_core, gateway) vs `*_URL` (cube, agentic) | `brandme_core/config.py:57-64` vs `brandme-cube/src/main.py:99-114`, `agentic/orchestrator/agents.py:15-18` |
| Governance host default | `http://governance:8006` vs `http://governance_console:8006` | `brandme_core/config.py:63` vs `brandme_core/env.py:75` |
| Knowledge/compliance ports | compose 8003/8004; `tasks.py` defaults 8101/8102; console `NEXT_PUBLIC_*` 8101/8102; `brandme-agents/Dockerfile` 8100-8102; `brandme-core/.env.example:26,28` point knowledge→8001 and compliance→8002 (policy/orchestrator ports) | `brandme-core/orchestrator/tasks.py:200,380,519`; `brandme-console/lib/api.ts:12-13` |
| Policy URL default | `http://policy:8001` vs `http://localhost:8103` | `brandme_core/config.py:58` vs `brandme-agents/agentic/tools/policy_tools.py:17` |
| Chain URL default | gateway `http://localhost:3003` vs chain listens on 3001 | `brandme-gateway/src/config/index.ts:86`; `brandme-chain/src/config/index.ts:14`; documented at `.env.example:49-50` |
| Console gateway base | `BRANDME_GATEWAY_URL` (providers pages) vs `BRANDME_GATEWAY_INTERNAL_URL` (moderation pages) vs `NEXT_PUBLIC_GATEWAY_URL` (browser, default `http://localhost:3000` = consumer port) | `providers/_data/gateway.ts:53`; `moderation/_lib/ops-gateway.ts:32`; `lib/api.ts:11` |
| Neo4j user | `NEO4J_USER` vs `NEO4J_USERNAME` | `agentic/graph_db.py:314` vs `branding/src/database.py:72` |
| Mode | `BRANDME_MODE` (Python/gateway) vs `ENVIRONMENT` (chain's only source, default `development`) | `brandme-chain/src/config/index.ts:15,47`; `brandme_core/config.py:145-160` |
| Registry | `gcr.io/lux-realestate-app` (CI) vs `gcr.io/brandme` (Makefile) vs `gcr.io/brandme-prod` (umbrella, infrastructure chart) | `ci-cd.yml:43,46`; `Makefile:212`; `brandme-umbrella/values.yaml:9` |
| Cluster name | `brandme-cluster` (CI env), `brandme-cluster-${env}` (terraform), `vars.BM_GKE_CLUSTER` (deploy) | `ci-cd.yml:45,471`; `main.tf:78` |

## 4. Server-only secrets in browser code (`NEXT_PUBLIC_*`)

No `NEXT_PUBLIC_` name with a secret-shaped suffix was found in application code; the only hits for
`NEXT_PUBLIC_*_KEY|SECRET` are negative test fixtures in `scripts/check-credential-manifest.test.mjs:126,199-202`, and the
checker fails CI on any such name (`check-credential-manifest.mjs:9`). `BRANDME_VERTEX_ACCESS_TOKEN` is read only in
`features/spatial/server/photoService.ts:40` (server file; header `:1` forbids client import).

Two browser-exposure concerns remain:
- `brandme-console/lib/api.ts:32-35` reads a bearer `auth_token` from `localStorage` and sends it to `NEXT_PUBLIC_*` service URLs,
  including `NEXT_PUBLIC_CHAIN_SERVICE_URL` (`:14`), i.e. a browser-direct path to the chain service that bypasses the gateway's
  `CHAIN_SERVICE_TOKEN` boundary (`brandme-gateway/src/services/rights.ts:71`). The chain's `/midnight/operations` routes require the
  server token, so such calls would be refused (`brandme-chain/src/routes/operations.ts:34-36`), but the design is legacy.
- `NEXT_PUBLIC_*` console URLs are baked at build time and CI passes none (`brandme-infra/helm/brandme/templates/console.yaml:5-7`,
  `brandme-console/Dockerfile`), so a built console image carries `http://localhost:*` defaults; the chart therefore disables the
  console in sandbox (`values-sandbox.yaml:50-53`).

## 5. Hardcoded endpoints pointing at localhost / emulators / the wrong system in non-dev code paths

- **GKE gateway health calls localhost**: Helm sets no `BRAIN_SERVICE_URL` (`templates/gateway.yaml:51-110`) and brain is not in the
  chart, so `/api/v1/system/health` fetches `http://localhost:8000/health` (`config/index.ts:85`; `routes/v1/index.ts:73-78`) and
  answers 503 "degraded" in-cluster. Kubelet probes use `/healthz` (`gateway.yaml:111-124`), so pods stay Ready while the public
  health route fails.
- **Blockfrost token in URL**: the Midnight Blockfrost project token is appended as `?project_id=` to node/indexer/ws URLs
  (`brandme-chain/src/midnight/network.ts:40-45`). Redaction exists for tests (`test-midnight-preprod.mjs:13-15`, `redaction.ts`),
  but any unredacted error/log path in `@midnight-ntwrk/*` providers would carry the secret.
- **Legacy compliance stubs**: `http://midnight-devnet:9000` (`burn_proof.py:60`) and `http://cardano-node:3001` (`esg_verifier.py:71`)
  — no such hosts anywhere; on `ConnectError` both fall back to success-shaped stubs (`burn_proof.py:154-161`, `esg_verifier.py:163-169`).
  The boot guard refuses these services in sandbox/production (`brandme_core/config.py:288-297`), so exposure is dev-only.
- **Agentic tool posts to a route that does not exist**: `POST ${CHAIN_SERVICE_URL}/tx/cardano` (`blockchain_tools.py:34-35`);
  brandme-chain has no `/tx/cardano` route and returns 410 for the retired `/tx/*` routes (`brandme-chain/src/index.ts:57-63`).
- **Console defaults**: `http://localhost:3000` for the gateway (the consumer's port) and `:8101/:8102` legacy agent ports
  (`brandme-console/lib/api.ts:11-14`).
- **Frontend dead client**: `NEXT_PUBLIC_API_URL || 'http://localhost:8000'` (`brandme-frontend/lib/api.ts:36`) targets brain
  directly; no importer (grep), so inert.
- **Celery defaults** `redis://redis:6379/0|1` (`celery_app.py:30-31`) with no Redis service defined anywhere.
- **Prometheus/OTel configs** scrape or export to hosts that exist in no stack (`prometheus.yml:37-151`, `otel-collector-config.yml:78,89`).
- `brandme_core/env.py:66` defaults `CORS_ORIGINS` to `*` (`parse_cors_origins` returns `['*']`, `:155-157`) for legacy Python
  services; the gateway and chain default to explicit localhost origins and the chart requires https origins.
- **Emulator pins differ**: Spanner emulator `1.5.45` (compose, CI) vs `1.5.28` in `consumer-ui.yml:64`.

## 6. Integrations with code but no mount / entry point

- **Commerce domain + Stripe test rail** (`S2-INT-014/015`): full HTTP API class (`brandme_core/domains/commerce/http_api.py`),
  signature-verified Stripe webhooks (`stripe_test.py:586-600`) and a gateway router — but the router is marked UNMOUNTED
  (`brandme-gateway/src/routes/v1/commerce.ts:4`) and `routes/v1/index.ts:132-145` mounts only chain/rights/ownership/assets/me and
  the eight consumer-domain routers. No service runs the commerce domain. Webhook endpoint is therefore unreachable.
- **Assistant / Anthropic planner / MCP executor** (`S2-INT-017`, `S2-INT-037`): `compose_assistant` (`orchestrator/composition.py:47`)
  has no caller outside its package; `routes/v1/assistant.ts` is not imported by `routes/v1/index.ts`. No MCP server process exists
  despite CLAUDE.md naming an `mcp-server`.
- **Consumer-domains Pub/Sub ingress, jobs, outbox worker** (`persona/ingress.py:282`, `jobs.py:90`, `outbox_worker.py:23`): entry
  points with no compose/Helm/CI definition (`brandme-infra/helm/brandme/README.md:34-35` acknowledges jobs).
- **Celery orchestrator** (`celery_app.py`, `tasks.py`): no worker/beat process, no broker; compose runs `uvicorn worker:app`.
- **Branding engine (Neo4j + LangChain Anthropic)**: "Not wired into any service" (`graph_engine.py:60`).
- **Agentic GraphRAG (OpenAI/Anthropic via LangChain)**: disabled in code (`graph_rag.py:30-31`); CLI image is built by CI but only to
  prove it refuses production (`smoke-image.sh:17`).
- **OpenTelemetry** (`brandme_core/telemetry.py`): no caller configures it.
- **Firestore client / wardrobe** (`brandme_core/firestore/*`): used only by legacy-profile services; Firestore rules are tested, never deployed.
- **Gateway NATS publisher**: mounted but dormant unless `NATS_URL` is set; the current chart never sets it.

## 7. Integrations with config / infrastructure but no code

- PostgreSQL / Cloud SQL (`init.sql`, `brandme-data/schemas`, `scripts/db-init.sh`, `terraform/main.tf:152-193`, `infrastructure/helm` bitnami dependency, `DATABASE_URL` templates).
- Redis (`infrastructure/redis/redis.conf`, bitnami values, `REDIS_URL` templates) — only Celery's unused broker URL references Redis in code.
- Prometheus, Grafana, Loki, Tempo, Alertmanager, cAdvisor, node-exporter (`infrastructure/**`).
- Cardano Blockfrost key, `CARDANO_NETWORK`, wallet Secrets (`.env.deploy.example:27,30`; `brandme-umbrella/values.yaml:174-181`).
- Neo4j Enterprise deployment (`agents/database-agent.sh:66-76`) — code exists but only as a CLI/unwired engine.
- `istio`, `podSecurityPolicy`, `external-secrets` blocks in `infrastructure/helm/brandme/values.yaml:320-343` with no templates.
- GitHub Environment secret `MN_PREPROD_SEEDS` designated in the manifest with no consuming workflow.
- Nordstrom/Impact provider descriptor (`nordstrom.py`) — setup fields only, no client.

## 8. Other consequential observations

1. **Default credentials in source**: `NEO4J_PASSWORD` defaults to the literal `"password"` (`brandme-agents/agentic/graph_db.py:315`,
   `brandme-agents/branding/src/database.py:73`); `scripts/db-init.sh:27` and `scripts/backup.sh:23` default `DB_PASSWORD` to a
   well-known literal; `.env.example` templates embed `postgres:postgres` / `brandme:password` DSNs (`brandme-core/.env.example:4`,
   `brandme-cube/.env.example:2`). All legacy, none reachable from a current stack, but they remain in the tree.
2. **Legacy deploy writes credentials to disk**: `agents/database-agent.sh:124-134` and `agents/validation-agent.sh:71-97` write
   generated passwords in plaintext to `.deployment/*.env` and `credentials.txt`; `agents/service-agent.sh:54-61` puts API keys into
   one Kubernetes Secret `brandme-secrets`. The scripts cannot run (missing `agents/lib/`), but `deploy-brandme.sh` is still the
   repo's advertised "one-click" path and is protected by CLAUDE.md's kill-list.
3. **CI image push uses a long-lived service-account key** (`secrets.GCP_SA_KEY`, `ci-cd.yml:368`) while the deploy job already
   uses keyless WIF (`:461-466`); the manifest marks the key "retire" (`credential-manifest.yaml:241`). Which GSA backs it is unknown.
4. **`brandme_core/health.py` imports `redis.asyncio` and `nats.aio.client` at module import** (`:21-22`); neither package is in
   `scripts/python/requirements.lock` (grep of the lock finds no `redis==`/`nats-py==`). Any current-image process importing
   `brandme_core.health` would fail at import. Static inference only; not executed.
5. **Dockerfiles that cannot build**: `brandme-core/{brain,policy,orchestrator}/Dockerfile`, `brandme-agents/{identity,knowledge,compliance}/Dockerfile`,
   `brandme-governance/**/Dockerfile` use `COPY ../../brandme_core` (out of context). `Makefile:212-232`, `scripts/deploy.sh:103-125`
   and `agents/service-agent.sh:35-39` build gateway/chain/core/agents with per-service contexts although those Dockerfiles need
   the repository root (`brandme-gateway/Dockerfile:1`, `brandme-core/Dockerfile:84`).
6. **Two Helm charts named `brandme`** (`brandme-infra/helm/brandme`, `infrastructure/helm/brandme`) plus the umbrella; only the
   first renders. `Makefile deploy-*`, `scripts/deploy.sh` and `agents/service-agent.sh` all target the non-rendering ones.
7. **Firestore security rules** (`packages/firestore-rules`) are evaluated against the emulator in CI (`ci-cd.yml:192-201`) but no
   deploy step publishes them; no Firestore database is provisioned by any code.
8. **Pub/Sub topics, Spanner instance/database, buckets, Secret Manager secrets, the GKE cluster and WIF pools are all
   pre-requisites that no committed code creates** (`gcp-dev-identities.sh:12-15, 263-268`; `migrations-job.yaml:6-7`;
   `pubsub.py:95`). Their existence cannot be inferred from the repository.
9. **`BRANDME_LOG_PSEUDONYM_KEY` falls back to a random per-process salt** (`brandme_core/logging.py:122-126`), so cross-pod/
   cross-restart log pseudonyms are unstable until the (planned, undeclared) key is provisioned.
10. **Stale documentation**: CLAUDE.md `:55` cites `MIDNIGHT_ENABLED` at `docker-compose.yml:304` (file is 242 lines; name absent
    repo-wide); `Makefile:78-90` port map (gateway 3000, Postgres, "Agents 8001") matches no compose file.

## 9. Scope limits

Sampled rather than exhaustively read: `brandme_core/mcp/tools.py` (not read; classified from `brandme_core/config.py:308-321`),
`brandme_core/domains/commerce/http_api.py` (grep only), `brandme-chain/src/midnight/adapter.ts` (grep + lines 85-134),
`brandme-agents/identity/src/main.py` (lines 20-40 and grep), `scripts/validate-helm.sh` and `scripts/provision/gcp-dev-identities.sh`
(header + command grep), `scripts/check-credential-manifest.mjs` (lines 1-120), `docs/build/security/credential-manifest.yaml`
(lines 1-300 read, remainder condensed by grep). Directories not reviewed are listed in `infrastructure-inventory.md` §9.
GitHub secrets/variables, GCP resources, registry contents and cluster state were not and cannot be observed from the repository.
