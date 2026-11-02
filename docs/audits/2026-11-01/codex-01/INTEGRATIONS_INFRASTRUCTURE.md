# Integrations and infrastructure

Baseline: `ed19dc151d103b108cf972e6d37971c55d5dcf60` (remote main), audited 2026-11-01. This report distinguishes source declarations from provisioned infrastructure. No cloud project was selected for authorized inspection; actual accounts, IAM, DNS/TLS, deployed resources and runtime configuration are **unknown** unless the CI evidence below says otherwise. No raw credentials were requested, read from unrelated stores or printed.

The shortest usable path is browser → gateway → consumer-domain API → Spanner, with the required domain workers and public browser authentication completed. Adding Stripe, AI, or blockchain keys cannot connect unmounted routers, create databases, run migrations, deploy missing workers, establish partner entitlements, or implement missing browser login. See [architecture](PRODUCT_ARCHITECTURE.md), [journeys](USER_FLOWS.md) and [roadmap](ROADMAP.md).

## Seven-axis service matrix

`D/U` means declarations/templates exist but runtime values are unknown. `U` means unverified, not absent. A CI emulator test does not establish cloud provisioning, permission, or network access. Full variable names, required locations/resources and acceptance checks are in [integrations.json](evidence/integrations.json).

| ID / integration | Implemented | Invoked | Config | Provisioned | Permission | Network | Meaningful operation |
|---|---|---|---|---|---|---|---|
| INT-001 OIDC and Spanner sessions | implemented verification; partial browser login | Bearer /api/v1 connected; browser creates only development session | D/U | unknown | unknown | unverified | unverified |
| INT-002 Cloud Spanner | implemented | gateway, domains, rights, export, outbox | D/U | unknown | unknown | unverified | CI emulator suite at pinned main (not cloud Spanner) |
| INT-003 Firestore projections and security rules | implemented | shared library/projection tests; direct browser consumers require separate proof | D/U | unknown | unknown | unverified | CI rules test step success; legacy 5 wardrobe tests xfailed |
| INT-004 GCS private media | implemented | consumer media routes mounted only with bucket | D/U | unknown | unknown | unverified | unverified |
| INT-005 GCS selected-category privacy export | implemented selected categories | gateway to export API + independent export worker | D/U | unknown | unknown | unverified | CI emulator coverage only |
| INT-006 Pub/Sub transactional outbox | implemented publisher | Helm events-worker; business consumers separately required | D/U | unknown | unknown | unverified | CI emulator suite and smoke only |
| INT-007 GKE Helm application hosting | implemented declarations | CI tag deploy gate; deployment skipped on pinned main | required repo variables absent | unknown | unknown | unverified | unverified |
| INT-008 Container registry image publishing | implemented | main CI builds/pushes five image families | GCP_SA_KEY metadata present | registry accepted CI push at run time; external inventory unknown | valid for CI push at run time; exact scope unknown | CI registry reachable at run time | Observed CI successful publish 2026-10-30 at pinned main |
| INT-009 GCP IAM/WIF/Secret Manager | implemented provisioning proposal | script not executed in audit; Helm secret references | D/U | unknown | unknown | unverified | unverified |
| INT-010 Midnight / Blockfrost | real adapter and compiled contracts | read-only chain service; reconciliation requires configured DB/contract | D/U | unknown | unknown | unverified | Committed local-network evidence exists; not re-executed by auditor |
| INT-011 Member wallet and proof server | implemented library; wallet production binding partial | member-controlled adapter; no server member signer | D/U | unknown | unknown | unverified | local-network committed evidence only |
| INT-012 Cardano anchoring | unavailable adapter | retired routes return 410 | D/U | unknown | unknown | unverified | unverified |
| INT-013 Stripe test payments | implemented test rail | dormant factory; gateway commerce routes not mounted (F-ARCH-001) | D/U | unknown | unknown | unverified | live test and stripe-mock checks skipped in main CI |
| INT-014 Nordstrom / Impact partner catalog | link validation implemented; Impact API not built | dormant commerce provider setup; external handoff only | D/U | unknown | unknown | unverified | unverified |
| INT-015 Anthropic assistant planner | implemented bounded model adapter | composition not wired to public gateway (F-ARCH-001) | D/U | unknown | unknown | unverified | live model test skipped in main CI |
| INT-016 Google Vertex virtual try-on experiment | implemented synthetic-only development route | opt-in development photo route; production disabled | D/U | unknown | unknown | unverified | not tested by auditor |
| INT-017 NATS legacy scan publisher | implemented publisher | /scan only when configured; no proof of business consumer | D/U | unknown | unknown | unverified | unverified |
| INT-018 Legacy PostgreSQL / Redis / Neo4j | SQL declaration; graph CLI/branding adapters; Redis health utility | not canonical consumer-domain persistence | D/U | unknown | unknown | unverified | unverified |
| INT-019 Observability: metrics, OTLP, Grafana/Loki | implemented utilities/configuration | legacy hooks; consumer-domain production alerting unverified | D/U | unknown | unknown | unverified | unverified |
| INT-020 Email / push notifications | in-app notifications implemented; external sender not found in reviewed canonical path | in-app routes; no verified email/push delivery | D/U | unknown | unknown | unverified | unverified |
| INT-021 Developer Magic MCP tool | config implemented | Claude SessionStart/MCP launch conditional | D/U | unknown | unknown | unverified | unverified |
| INT-022 AP2/UCP mandate contracts | schemas/verification library implemented | commerce executor path dormant; official SDK oracle skipped | D/U | unknown | unknown | unverified | AP2_SDK_PYTHON tests skipped in main CI |
| INT-023 Legacy branding LLM / GraphRAG embeddings | branding LangGraph/Anthropic library; GraphRAG constructor explicitly disabled | no service wiring found; graph CLI exists | D/U | unknown | unknown | unverified | unverified |
| INT-024 MediaPipe local pose runtime/model | hash-pinned development asset fetch script | spatial-validation prepares local runtime; browser/device audit in USER_FLOWS | D/U | unknown | unknown | unverified | not re-executed by auditor |

## Configuration and exact next actions

Only names are recorded below. Keys/tokens/seed/private assertion key are secrets. Project IDs, bucket/topic/contract IDs, issuer/audience/JWKS public keys, origins and mode/runtime selectors are identifiers/settings. Secret-reference fields name a secret resource, not the secret value. Host environment and provider secret values were not inspected.

### INT-001 — OIDC and Spanner sessions

Evidence: [brandme-gateway/src/middleware/session.ts:19](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/middleware/session.ts#L19). Version: jose from pnpm lock; OIDC Core 1.0.

Variables: `IDENTITY_PROVIDER`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URI`, `OIDC_ALGORITHMS`, `SESSION_TTL_HOURS`, `PUBLIC_ORIGINS`, `CORS_ORIGINS`. Location: gateway server; browser public origins.

Required: Selected issuer tenant, API audience, registered browser client/redirects, session tables.

Next action: Select issuer; implement code/PKCE callback + session exchange and recovery; register exact HTTPS origins; preserve revocation and CSRF. Keys alone cannot create the missing browser flow. Acceptance: Strict-mode browser sign-in, refresh, expiry/revocation, sign-out and cross-account denial; negative issuer/audience tests.

### INT-002 — Cloud Spanner

Evidence: [brandme-gateway/src/middleware/identity/store.ts:85](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/middleware/identity/store.ts#L85). Version: google-cloud-spanner Python 3.40.1; TS @google-cloud/spanner 9.0.0.

Variables: `SPANNER_PROJECT_ID`, `SPANNER_INSTANCE_ID`, `SPANNER_DATABASE_ID`, `SPANNER_EMULATOR_HOST`. Location: server/worker/migration; emulator only local.

Required: Environment-specific instance/database, Google SQL dialect schema/indexes, runtime data IAM, migration DDL IAM.

Next action: Choose project/region; provision DB; apply ordered migration ledger; grant per-service IAM; seed synthetic pilot data; verify schema and backup restore. Acceptance: Two accounts persist across process restart; tenant denial; migrations ledger/digests; restore into disposable DB.

### INT-003 — Firestore projections and security rules

Evidence: [brandme_core/firestore/client.py:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/firestore/client.py#L1). Version: google-cloud-firestore 2.14.0.

Variables: `FIRESTORE_PROJECT_ID`, `FIRESTORE_EMULATOR_HOST`. Location: server/projector; local emulator.

Required: Firestore database, security rules deploy, authenticated projection principal and indexes.

Next action: Verify whether direct realtime reads are in the selected milestone; provision/rules-test only if used. Existing legacy wardrobe path has known quarantined failure. Acceptance: Rules reject cross-member reads/writes and public private-data access; projection delivery verified.

### INT-004 — GCS private media

Evidence: [brandme_core/domains/media/gcs_store.py:325](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/media/gcs_store.py#L325). Version: Google Storage REST v1; ADC.

Variables: `BRANDME_MEDIA_BUCKET`, `STORAGE_EMULATOR_HOST`. Location: domains API + jobs worker.

Required: Private bucket, public access prevention, uniform IAM, no incompatible retention/versioning, CORS, service identity signing permissions.

Next action: Provision separate private media bucket matching bucket_findings; configure signed upload CORS and signer IAM; deploy media jobs/purge process (F-ARCH-002). Acceptance: Synthetic upload/finalize, wrong-owner denial, signature expiry, unsaved 24-hour purge and deletion retry.

### INT-005 — GCS selected-category privacy export

Evidence: [brandme_core/privacy_exports/config.py:9](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/privacy_exports/config.py#L9). Version: Google Storage/Spanner adapters.

Variables: `PRIVACY_EXPORT_SERVICE_URL`, `PRIVACY_EXPORT_SERVICE_TOKEN`, `EXPORT_BUCKET`, `EXPORT_NETWORK`, `EXPORT_CONTRACT_ADDRESS`, `EXPORT_STORAGE_EMULATOR_HOST`. Location: gateway/API/worker.

Required: Dedicated environment export bucket, per-service token, worker GSA, rights network/contract scope.

Next action: Provision private export bucket; deploy API and worker; apply schema; configure recent-auth assertions; document full-account export remains unsupported. Acceptance: Create, poll, download under recent auth, reject other user, verify digest and expire object.

### INT-006 — Pub/Sub transactional outbox

Evidence: [brandme_core/events/worker.py:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/events/worker.py#L1). Version: REST Pub/Sub; contract catalogs.

Variables: `OUTBOX_PUBSUB_TOPIC_PUBLIC`, `OUTBOX_PUBSUB_TOPIC_MEMBER_PRIVATE`, `OUTBOX_PUBSUB_TOPIC_RESTRICTED`, `OUTBOX_EVENT_TYPES`, `PUBSUB_EMULATOR_HOST`. Location: worker/subscriber; local emulator.

Required: Three private topics, >=24h topic retention, subscriptions before publish, retry/dead-letter policy, IAM publish/get and subscriber.

Next action: Create topics/subscriptions and service identities, deploy catalog-compatible consumers and domain ingress/jobs; do not treat delivered as business completion. Acceptance: Lost-ack duplicate delivered exactly once at business layer using event_id/inbox transaction; replay respects deletion freeze.

### INT-007 — GKE Helm application hosting

Evidence: [brandme-infra/helm/brandme/values.yaml:15](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-infra/helm/brandme/values.yaml#L15). Version: Helm chart; GKE Kubernetes target not observed.

Variables: `BM_DEPLOY_ENABLED`, `BM_GCP_PROJECT_ID`, `BM_GCP_REGION`, `BM_GKE_CLUSTER`, `BM_GCP_WIF_PROVIDER`, `BM_GCP_DEPLOYER_SA`. Location: CI / cluster / DNS.

Required: Authorized project, cluster, namespace, ingress controller, reserved IP, HTTPS DNS/cert, workload identities, network policy, secrets sync.

Next action: Complete verification packet, retain ingress disabled until OIDC/probes/tenant tests; add consumer frontend serving and workers needed for chosen milestone; validate F-SEC-002 before rollout. Acceptance: Immutable image digest → readiness → synthetic browser business journey; measured rollback and restore.

### INT-008 — Container registry image publishing

Evidence: [.github/workflows/ci-cd.yml:364](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.github/workflows/ci-cd.yml#L364). Version: google-github-actions/auth@v2.

Variables: `GCP_SA_KEY`, `GCP_PROJECT_ID`, `REGISTRY`. Location: CI only.

Required: Registry push identity and five images, registry access/retention.

Next action: Replace build key with narrowly scoped WIF pusher; reconcile hardcoded publishing project versus BM_GCP_PROJECT_ID; pin consumed digest. Acceptance: One authorized main push authenticates without stored JSON key and release references exact pushed digest.

### INT-009 — GCP IAM/WIF/Secret Manager

Evidence: [scripts/provision/gcp-dev-identities.sh:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/scripts/provision/gcp-dev-identities.sh#L1). Version: not independently checked.

Variables: `RIGHTS_SERVICE_TOKEN`, `PRIVACY_SERVICE_TOKEN`, `PRIVACY_EXPORT_SERVICE_TOKEN`, `CHAIN_SERVICE_TOKEN`, `CONSUMER_DOMAIN_ASSERTION_KEY`, `CONSUMER_DOMAIN_ASSERTION_KID`, `CONSUMER_DOMAIN_ASSERTION_JWKS`. Location: server/worker/CI; private keys server only.

Required: Per-process GSA/KSA, resource-scoped IAM, WIF issuer/ref/environment conditions, Secret Manager versions and sync.

Next action: After owner selects project, review plan output; grant minimal Spanner/Storage/PubSub permissions; provision independent service tokens and assertion key; test rotation by overlapping kid. Acceptance: Runtime impersonates only its own identity; unrelated resource access denied; no secret in rendered chart/log/browser.

### INT-010 — Midnight / Blockfrost

Evidence: [brandme-chain/src/midnight/capability.ts:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-chain/src/midnight/capability.ts#L1). Version: Midnight.js 4.1.1; ledger-v8 8.1.2; Compact runtime 0.16.0.

Variables: `MIDNIGHT_NETWORK`, `MIDNIGHT_CONTRACT_ADDRESS`, `MIDNIGHT_BLOCKFROST_PROJECT_ID`, `CHAIN_RECONCILIATION_ENABLED`, `CHAIN_SERVICE_TOKEN`. Location: chain server/worker; token secret.

Required: Correct-network Blockfrost project, RPC/indexer entitlement, test contract, finality oracle, persisted operations/projection.

Next action: Select authorized Preprod project; provision token in Secret Manager; verify artifacts and test contract; run authorized synthetic operation and reconcile finality. Mainnet writes remain unavailable. Acceptance: Actual Preprod transaction/contract/receipt matched by node finality and entitlement projection; duplicate/reorg recovery.

### INT-011 — Member wallet and proof server

Evidence: [brandme-chain/src/midnight/adapter.ts:204](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-chain/src/midnight/adapter.ts#L204). Version: dapp-connector-api 4.0.1; wallet-sdk 1.2.0.

Variables: `MN_PREPROD_SEEDS`, `MIDNIGHT_LOCAL_NODE_PORT`, `MIDNIGHT_LOCAL_INDEXER_PORT`, `APP__INFRA__SECRET`. Location: wallet/browser/test harness; seeds only authorized isolated tests.

Required: Compatible Lace/dApp connector, funded test wallet, locally controlled proof server, private state recovery.

Next action: Integrate wallet connection and clear signing confirmation; keep witnesses local; implement backup/recovery and verify correct network/address before proving. Acceptance: User sees exact operation and signs; no member seed reaches server; wrong network refused; restart recovers private state.

### INT-012 — Cardano anchoring

Evidence: [brandme-chain/src/cardano/anchor.ts:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-chain/src/cardano/anchor.ts#L1). Version: not applicable.

Variables: `BLOCKFROST_API_KEY`. Location: future adapter server; legacy variable unused by canonical path.

Required: Authorized Cardano RPC account, signer custody, network, submitter and reconciliation implementation.

Next action: Keep unavailable for first milestone; build and test real submitter only if explicit product requirement survives. Acceptance: Real testnet transaction finalized and verified; never fabricate transaction hash.

### INT-013 — Stripe test payments

Evidence: [brandme_core/domains/commerce/composition.py:90](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/commerce/composition.py#L90). Version: stripe 16.0.0; version pinned by stripe_test.py.

Variables: `BRANDME_COMMERCE_PAYMENTS`, `STRIPE_TEST_SECRET_KEY`, `STRIPE_TEST_WEBHOOK_SECRET`, `STRIPE_TEST_WEBHOOK_SECRET_PREVIOUS`, `BRANDME_STRIPE_EGRESS_PROXY`, `BRANDME_STRIPE_CA_BUNDLE`, `STRIPE_LOG`. Location: commerce server only; demo/development.

Required: Selected Stripe sandbox, restricted test key, signed webhook destination, test payment methods, durable commerce reconciliation.

Next action: Connect commerce application first; select test account; configure allowed test keys and separate webhook secret; preserve API version compatibility. No live payments authorized or supported. Acceptance: Sandbox authorize/capture/void/refund; duplicate webhook and lost-response recovery; test/live mismatch rejected.

### INT-014 — Nordstrom / Impact partner catalog

Evidence: [brandme_core/domains/providers/nordstrom.py:44](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/providers/nordstrom.py#L44). Version: no Impact wire client.

Variables: `NORDSTROM_IMPACT_ACCOUNT_REF`, `NORDSTROM_IMPACT_CREDENTIAL_SECRET`, `NORDSTROM_IMPACT_CAMPAIGN_REF`, `NORDSTROM_IMPACT_CATALOG_REF`. Location: operator config + server Secret Manager refs.

Required: Approved publisher account/catalog, account-specific API docs, imagery/caching/transformation/affiliate rights.

Next action: Obtain approval and usage rights; confirm approved-account endpoints, then implement adapter. A secret reference or link probe must not enable checkout. Acceptance: Read-only authenticated catalog test and permission review; checkout stays unsupported until separate contracted API.

### INT-015 — Anthropic assistant planner

Evidence: [brandme_core/orchestrator/model_planner.py:53](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/orchestrator/model_planner.py#L53). Version: anthropic 0.125.0; code API version 2023-06-01, model claude-opus-5-5.

Variables: `BRANDME_ASSISTANT_PLANNER`, `BRANDME_DEV_ANTHROPIC_API_KEY`, `BRANDME_ASSISTANT_MODEL`, `BRANDME_ASSISTANT_EFFORT`, `BRANDME_ASSISTANT_EGRESS_PROXY`, `BRANDME_ASSISTANT_CA_BUNDLE`, `BRANDME_LOG_REF_KEY`. Location: server only; demo/development.

Required: Authorized Claude account/model entitlement, approved data-use terms, spend controls.

Next action: Connect deterministic assistant first; verify current model/API entitlement and request schema before selecting model; preserve independent executor authorization; persist budgets before replicas. Acceptance: Adversarial tool data cannot add scopes/approval; cancellation stops new effects; per-user/day budget enforced across restart.

### INT-016 — Google Vertex virtual try-on experiment

Evidence: [brandme-frontend/features/spatial/server/photoService.ts:30](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/spatial/server/photoService.ts#L30). Version: virtual-try-on-001 REST predict.

Variables: `BRANDME_PHOTO_DEV_ENABLED`, `BRANDME_PHOTO_DEV_PROJECT`, `BRANDME_PHOTO_DEV_REGION`, `BRANDME_VERTEX_ACCESS_TOKEN`, `BRANDME_PHOTO_RETENTION_NOTICE`, `NEXT_PUBLIC_BRANDME_MODE`. Location: Next server only; public mode flag only in browser.

Required: Approved GCP project, Vertex AI model entitlement/region, short-lived token, retention disclosure.

Next action: Select dev project/terms explicitly; keep synthetic-only; do not confuse this separate experiment with approved consumer-domain production provider. Acceptance: Synthetic request reports accurate preview label; no real user image accepted; cancellation/retention limits disclosed.

### INT-017 — NATS legacy scan publisher

Evidence: [brandme-gateway/src/services/nats.ts:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/services/nats.ts#L1). Version: nats JS; compose 2.10.29-alpine.

Variables: `NATS_URL`, `NATS_MAX_RECONNECT_ATTEMPTS`. Location: gateway/local NATS.

Required: NATS server authentication, stream/subscription and consumer.

Next action: Retain only if legacy scan journey retained; otherwise consolidate behind canonical outbox. Acceptance: Synthetic event reaches named consumer with retry and broker-failure behavior.

### INT-018 — Legacy PostgreSQL / Redis / Neo4j

Evidence: [brandme-infra/terraform/main.tf:152](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-infra/terraform/main.tf#L152). Version: PostgreSQL 15 declaration; Neo4j/Redis runtime unknown.

Variables: `DB_PASSWORD`, `DATABASE_URL`, `REDIS_URL`, `NEO4J_PASSWORD`, `NEO4J_READONLY_PASSWORD`, `NEO4J_WRITER_PASSWORD`. Location: legacy scripts/CLI only.

Required: Only if separately retained: SQL/Redis/Neo4j instances and IAM/password delivery.

Next action: Do not provision for main consumer milestone. Reconcile each retained legacy module before archive/removal; Terraform has F-SEC-005. Acceptance: Named inbound consumer and reproducible business use before retaining service.

### INT-019 — Observability: metrics, OTLP, Grafana/Loki

Evidence: [brandme_core/telemetry.py:20](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/telemetry.py#L20). Version: OpenTelemetry 1.21.0; prometheus-client 0.19.0.

Variables: `OTEL_EXPORTER_OTLP_ENDPOINT`, `GRAFANA_PASSWORD`, `LOG_LEVEL`. Location: server/collector/operator.

Required: Collector endpoint, authenticated dashboard, log retention/redaction, alert destinations and incident ownership.

Next action: Instrument chosen live path; alert on outbox age/dead letters, purge failures, auth errors and readiness; set retention and test alert delivery without contacting customers. Acceptance: Fault injection produces one actionable alert and a runbook; traces exclude private content.

### INT-020 — Email / push notifications

Evidence: [brandme_core/domains/social/notifications.py:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/social/notifications.py#L1). Version: none.

Variables: `none`. Location: future worker.

Required: Chosen sender account, consent/preferences, delivery/webhook verification, unsubscribe/bounce handling.

Next action: Keep external notifications unavailable until provider and worker implemented; no messages sent in audit. Acceptance: Opt-in event delivers once; unsubscribe honored; failure tracked.

### INT-021 — Developer Magic MCP tool

Evidence: [.mcp.json:8](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.mcp.json#L8). Version: @21st-dev/magic@latest (unpinned).

Variables: `MAGIC_API_KEY`. Location: developer process only.

Required: Approved pinned third-party package and key storage.

Next action: Address F-SEC-001: pin audited version; pass minimum key via environment/private channel; allowlist exported variable names. Acceptance: Process argv contains no key; unapproved variables never forwarded.

### INT-022 — AP2/UCP mandate contracts

Evidence: [brandme_core/domains/commerce/ap2.py:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/commerce/ap2.py#L1). Version: schema snapshots in commerce/ap2_schemas.

Variables: `AP2_SDK_PYTHON`, `MCP_AS_ISSUER`, `MCP_AS_JWKS_URI`, `COMMERCE_DOMAIN_ASSERTION_KEY`, `COMMERCE_DOMAIN_ASSERTION_KID`. Location: commerce/server and isolated compatibility test.

Required: Approved protocol partner, signer/JWKS trust, supported SDK oracle version and account/network scope.

Next action: Run official SDK oracle in pinned isolated interpreter; mount authenticated commerce; obtain real partner acceptance before claiming interoperability. Acceptance: Signed mandate accepted by actual partner sandbox; replay/expiry/audience/amount denial; provider receipt reconciled.

### INT-023 — Legacy branding LLM / GraphRAG embeddings

Evidence: [brandme-agents/branding/src/graph_engine.py:62](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-agents/branding/src/graph_engine.py#L62). Version: branding requirements use ranges; agentic legacy pins documented by graph_rag.py.

Variables: `BRANDME_DEV_ANTHROPIC_API_KEY`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_DATABASE`, `NEO4J_PASSWORD`, `NEO4J_READONLY_USER`, `NEO4J_READONLY_PASSWORD`, `NEO4J_WRITER_USER`, `NEO4J_WRITER_PASSWORD`, `OPENAI_API_KEY`. Location: optional developer CLI/server library.

Required: If deliberately restored: compatible pinned LangChain client, Neo4j graph and RBAC, authorized Anthropic model; embeddings client implementation.

Next action: Keep dormant pending product decision; do not supply OPENAI_API_KEY to revive disabled GraphRAG. Reuse hardened canonical model transport rather than restoring ambient credential behavior. Acceptance: Chosen retained use case runs under isolated credentials, scoped graph queries and synthetic data; disabled GraphRAG remains fail-closed.

### INT-024 — MediaPipe local pose runtime/model

Evidence: [scripts/assets/prepare-vision.py:6](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/scripts/assets/prepare-vision.py#L6). Version: MediaPipe tasks-vision 0.10.35; pose landmarker lite float16 model 1.

Variables: `none`. Location: development build/browser; no runtime provider key.

Required: npm runtime archive and Google-hosted pose model; redistribution/provenance review before shipped model.

Next action: Retain pinned integrity validation and on-device processing; resolve model redistribution review before production packaging; verify disabled/permission-denied fallbacks on devices. Acceptance: No camera frame network upload; explicit camera permission/revocation; model integrity and licensing record; actual device performance captured.

## Existing deployment choices and minimum topology

Keep Spanner and the current gateway/domain API; recover the already-written domain workers before adding another stack. A first isolated demo needs only emulator-backed persistence plus signed gateway assertions and explicit simulated identity. For a staging pilot, select a dedicated project/database, OIDC issuer/client, gateway and frontend serving path, consumer API and its jobs/ingress consumers, and one deployment identity per process. Introduce GCS media, Pub/Sub business consumption, exports and Midnight only for journeys actually included in that pilot. Optional Stripe-test/Anthropic experiments stay outside production. No fresh cost estimate is justified until project region, replica count, Spanner capacity, media volume and traffic are selected; repository numbers are not current price quotes.

Dependency order: (1) name environment/project/region and required journey; (2) prepare resource/IAM plan and OIDC client; (3) create resources under separate authorization; (4) run migrations before writers, verify schema/digests and restore; (5) sync scoped secrets/public key configuration and deploy workers before emitting new event versions; (6) deploy immutable application images and configure DNS/TLS/origins; (7) run two-user end-to-end persistence, denial, retry and deletion checks; (8) test alerts, rollback, restore and credential rotation.

Helm is a concrete declaration, not proof of application: secretKeyRef does not create a Kubernetes Secret, a service-account annotation does not grant IAM, a topic name does not create a subscription, and an image push does not deploy. The current main CI did publish five image families; its sandbox deploy job was skipped. The branch/GitHub inventory reports no visible deployments/environments/releases, which does not prove no cloud resources exist.

Repository-scoped Actions metadata was inspected successfully: exactly one secret name, GCP_SA_KEY (created/updated 2026-10-09), and zero repository variables. Thus BM_DEPLOY_ENABLED and BM_GCP_* repository settings are confirmed absent in this snapshot; the tag deploy enable condition is unsatisfied in that scope. This does not inspect organization-level inherited configuration or runtime/cloud secrets. See [names-only configuration metadata](evidence/security-github-config-metadata.json).

## Official setup references checked 2026-11-01

- [OIDC](https://openid.net/specs/openid-connect-core-1_0.html) — Core 1.0 errata 2, 2023-12-15; issuer/audience verification and browser authorization flow.
- [Spanner/GKE](https://docs.cloud.google.com/spanner/docs/connect-gke-cluster?hl=en) — Workload identity and database IAM are separate from connection identifiers.
- [GKE identity](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-identity) — Enable workload federation, bind each runtime identity to resource permissions.
- [Pub/Sub](https://docs.cloud.google.com/pubsub/docs/create-topic) — Create topics, subscriptions and retention; publishing alone is not consumption.
- [GCS privacy](https://docs.cloud.google.com/storage/docs/public-access-prevention) — Public-access prevention for private storage.
- [Stripe keys](https://docs.stripe.com/keys) — Sandbox key selection and separate webhook signing secret.
- [Stripe events](https://docs.stripe.com/webhooks) — Register accessible HTTPS endpoint; authenticate received events.
- [Midnight networks](https://docs.midnight.network/relnotes/network) — Preprod uses Blockfrost token; retired October 2026 hostnames must not be reused.
- [Midnight deployment](https://docs.midnight.network/guides/deploy-and-operate) — Test network contract, wallet and local proof server; witness privacy boundary.
- [Anthropic](https://platform.claude.com/docs/en/api/overview) — API account/authentication and explicit rate/spend constraints.
- [OWASP](https://wstg.owasp.org/v4.2/) — WSTG v4.2 static review checklist; not a completed dynamic penetration test.
- [Vertex try-on](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/image/generate-virtual-try-on-images) — Select authorized project/model region and account permission before synthetic experiment.
- [Nordstrom publisher](https://www.nordstrom.com/browse/affiliate-program) — Official publisher application links to Impact; no checkout API entitlement implied.
- [Firestore rules](https://firebase.google.com/docs/firestore/security/get-started) — Deploy and test database access rules for authenticated client access.
- [GCS signed URLs](https://docs.cloud.google.com/storage/docs/access-control/signing-urls-with-helpers) — IAM signing and object permissions required for signed storage URLs.

Provider-specific next steps deliberately do not request raw credentials. For Nordstrom/Impact use the official program and approved-account documentation linked by the adapter; this audit did not verify a partner account or private endpoint specification. No quota/billing/license entitlement was assumed.
