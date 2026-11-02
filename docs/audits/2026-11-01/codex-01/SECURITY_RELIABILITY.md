# Security and reliability

Baseline `ed19dc151d103b108cf972e6d37971c55d5dcf60`; audit date 2026-11-01; auditor: Codex security/infrastructure reviewer. Static trust-boundary review and GitHub CI evidence, not a live penetration test. Repository code was not executed: Docker engine/adequate disposable isolation was unavailable.

## Threat model and controls to retain

Assets: account/profile/persona data, social relationships, wardrobe/media, privacy jobs, purchase authority and money records, wallet private state, contract entitlements, cloud credentials and release integrity. Actors: anonymous browser, authenticated member, delegated external agent, operator, provider/webhook sender, compromised dependency or repository writer. Main boundaries are browser→gateway identity, gateway→domain assertion/token, domain→Spanner/GCS/PubSub, wallet→proof/indexer/node, and CI→registry/cluster. The primary credible risks are cross-member access, stale/replayed authority, fake trust claims, private media retention, duplicated external effects, and credential-bearing developer/CI execution.

| Boundary | Reviewed evidence / retained control | Residual gap |
|---|---|---|
| Gateway identity/session | [brandme-gateway/src/middleware/session.ts](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/middleware/session.ts#L77) verifies issuer/audience/asymmetric algorithm; server session + CSRF token + Origin checks; [brandme-gateway/src/middleware/mode.ts](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/middleware/mode.ts#L47) refuses simulated identity/emulators in strict mode. | Strict browser login/callback/session exchange absent; bearer tokens do not supply the current browser path. Dynamic expiry/revocation tests not run here. |
| Consumer tenant boundary | [brandme_core/domains/persona/assertion.py](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/persona/assertion.py#L63) verifies ES256 issuer/audience, <=60s lifetime, environment and jti; scoped domain queries include member IDs. | Replay cache is process-local; chart limits consumer service to one replica. Distributed/restart replay handling needs review before scale. No cross-tenant exploit demonstrated. |
| Rights/export service | [brandme_core/read_api/app.py](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/read_api/app.py#L66) requires distinct service token and subject; [brandme_core/privacy_exports/app.py](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/privacy_exports/app.py#L25) gates export download by subject and recent-auth evidence. | Shared bearer-service trust boundary depends on private network/IAM and gateway correctness; full-account export/deletion remains a separate integration task. |
| Media | [brandme_core/domains/media/service.py](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/media/service.py#L84) enforces member-owned queries, consent and expiry; [brandme_core/domains/media/gcs_store.py](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/media/gcs_store.py#L325) checks private deletable bucket in strict modes. | Worker deployment must actually purge objects. Cloud bucket policy, signer IAM and user-photo lifecycle unverified. |
| Import/redirect SSRF | [brandme_core/domains/providers/url_guard.py](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/providers/url_guard.py#L45) rejects internal addresses and checks redirect hops; checkout redirect hosts allowlisted. | Code explicitly describes DNS re-resolution race; enforcing egress proxy/allowlist not observed. This is an unexploited hypothesis on dormant provider paths. |
| Agent/AI | [brandme_core/orchestrator/runtime.py](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/orchestrator/runtime.py#L61) fixed tool allowlists/scopes, approval stop, budgets/cancel; [brandme_core/orchestrator/model_planner.py](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/orchestrator/model_planner.py#L60) withholds purchase.execute from model. [brandme_core/orchestrator/anthropic_adapter.py](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/orchestrator/anthropic_adapter.py#L1) pins egress and strips ambient headers. | Assistant route composition dormant. Default cost ledger is in memory; a distributed/live launch needs durable budgets. No prompt injection test executed here. |
| Money/commerce | [brandme_core/domains/providers/merchant.py](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/providers/merchant.py#L1) has integer-money, idempotency/reconciliation and authorization-before-capture design; test rail refuses live keys/modes. | Provider and gateway routes unmounted, partner entitlement absent from evidence, external tests skipped. No real payment performed. |
| Wallet/privacy | [brandme-chain/src/index.ts](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-chain/src/index.ts#L34) read-only reconciliation; [brandme-chain/src/routes/midnight.ts](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-chain/src/routes/midnight.ts#L4) keeps signer with member; old fake transaction routes 410. | Public-network operation and private-state recovery unverified. Proof server sees witnesses; keep local/member-controlled. |
| Legacy service authority | [brandme_core/config.py](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/config.py#L273) inventories payload-ID auth shortcuts/fake outputs and refuses strict boot. | Development services must stay isolated; do not publish them or mistake guard-protected stubs for production services. |

OWASP WSTG v4.2 was used for identity, authorization, sessions, input validation, configuration, transport and business-logic review. Input schemas/parameterized queries and headers were sampled at the named boundaries; there was no exhaustive dynamic SQLi/XSS/CSRF/SSRF/upload fuzzing. CORS, webhook authenticity, replay and rate-control implementations were read, with the wiring limitations stated above. No legal or compliance certification is made.

## Findings

Severity concerns realistic security/operational impact; product importance and delivery order are separate. High means a credible privileged compromise/release-control path under stated prerequisites, not an observed breach. Medium means important containment/availability/correctness controls need work. Findings are static/metadata-confirmed; consequences requiring exploitation are explicitly conditional.

### F-SEC-001 — Developer MCP starts a mutable package and puts its API key in argv

**Medium (conditional) · supply chain / credential handling · high static/metadata evidence; no exploit execution**. Tool launch executes third-party code with developer process access and exposes key to local process inspection. No compromise/exposure observed.

Evidence: [.mcp.json:8](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.mcp.json#L8); [.claude/hooks/session-start.sh:21](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.claude/hooks/session-start.sh#L21)

Preconditions: Developer enables the repository MCP tool with MAGIC_API_KEY; package or local process-inspection boundary is compromised. Expected: Reviewed pinned executable; minimum credentials delivered privately. Observed: npx -y uses @latest; key is passed as command argument. SessionStart forwards every local env assignment to session environment.

Impact: Developer token and any unnecessarily forwarded environment may become accessible to unreviewed package or local observers. Validation: source/metadata review only; no repository execution.

Fix: Pin reviewed immutable package version/integrity; use supported environment/private key delivery; allowlist env names and validate shell identifier. Do not execute hook during audit. Dependencies: Approved developer tool/package and secret channel. Effort: 0.5–1.5 engineering days. Acceptance: Inspect spawned argv with synthetic key; no value present. Unexpected env key rejected. Reviewed package resolved identically.

### F-SEC-002 — Readiness marks gateway and consumer-domain processes healthy without database checks

**Medium · reliability · high static/metadata evidence; no exploit execution**. A broken schema/IAM/database can receive traffic and appear deployed successfully.

Evidence: [brandme-gateway/src/routes/health.ts:16](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/routes/health.ts#L16); [brandme-infra/helm/brandme/templates/gateway.yaml:115](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-infra/helm/brandme/templates/gateway.yaml#L115); [brandme_core/domains/persona/app.py:79](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/persona/app.py#L79)

Preconditions: Deploy chart with inaccessible Spanner or unapplied consumer schema. Expected: Readiness verifies required dependencies/schema; liveness remains process-only. Observed: Gateway /healthz always 200; Helm uses it for readiness. Consumer /health returns static ok and __check only config.

Impact: Rollout success and HTTP 200 can coexist with failure of sign-in/profile/domain operations. Validation: source/metadata review only; no repository execution.

Fix: Add bounded dependency/schema readiness; wire probe separately; use selected business synthetic check in deploy. Avoid restarting processes solely for downstream outage. Dependencies: Spanner and selected domain schema; F-ARCH-002 workers. Effort: 1–2 days. Acceptance: Block DB or omit required migration: readiness false, liveness true; restore makes readiness recover.

### F-SEC-003 — No branch protection or rulesets observed on current repository branches

**High · release governance · high static/metadata evidence; no exploit execution**. A repository writer can bypass review/CI on source that main CI publishes using cloud credentials.

Evidence: [.github/workflows/ci-cd.yml:310](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.github/workflows/ci-cd.yml#L310); [evidence/history-github-protection.json:metadata](evidence/history-github-protection.json); [evidence/history-github-rulesets.json:metadata](evidence/history-github-rulesets.json)

Preconditions: A repository write-capable identity makes an unsafe direct push; configured controls do not require approval/checks. Expected: Default/release refs require trusted review, required checks, and controlled changes to workflow/deployment files. Observed: Paginated GitHub snapshot: 34 branches protected=false; explicit protection endpoints return Branch not protected; rulesets listing succeeds empty.

Impact: Accidental or compromised direct source/workflow change may reach image publishing without enforced review. Validation: source/metadata review only; no repository execution.

Fix: Propose default/release rulesets and CODEOWNERS for CI/IAM/contracts; require actual check names after validating scope. Protect release tags and environment approvals as appropriate. No permission change authorized in audit. Dependencies: Owner approval; branch/CI inventory. Effort: 0.5–1 day after decision. Acceptance: Unauthorized direct push and failing-check merge denied; authorized reviewed change succeeds. Recheck metadata.

### F-SEC-004 — Image publishing still depends on a long-lived Google service-account key

**Medium · CI identity · high static/metadata evidence; no exploit execution**. A static cloud credential persists when deployment already supports short-lived identity. Key scope and age are unknown.

Evidence: [.github/workflows/ci-cd.yml:368](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.github/workflows/ci-cd.yml#L368); [scripts/provision/gcp-dev-identities.sh:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/scripts/provision/gcp-dev-identities.sh#L1)

Preconditions: Main/tag publish job is authorized and has GCP_SA_KEY available. Expected: Scoped federated pusher identity limited to this repository/ref and registry. Observed: build-images authenticates via credentials_json; deploy separately uses WIF. Pinned-main publish jobs succeeded.

Impact: Key theft has a potentially longer useful lifetime and unknown IAM blast radius. Validation: source/metadata review only; no repository execution.

Fix: Switch publishing to separate WIF pusher and restrictive subject/repository/ref conditions; verify one authorized push, then separately authorize revocation/secret removal. Dependencies: Selected publishing project; IAM review; credentials owner. Effort: 1–2 days. Acceptance: No stored JSON key required; unauthorized PR/ref cannot obtain pusher credentials; immutable digest published.

### F-SEC-005 — Historical Terraform is not a valid canonical provisioning plan

**Low (noncanonical path) · infrastructure drift · high static/metadata evidence; no exploit execution**. Applying the old recipe fails and does not supply the canonical data services.

Evidence: [brandme-infra/terraform/main.tf:192](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-infra/terraform/main.tf#L192)

Preconditions: An operator uses brandme-infra/terraform as full-system provisioning. Expected: Valid declared variables and resources matching current runtime. Observed: var.db_password referenced but only project_id/region/environment variables declared; plan describes Cloud SQL while canonical runtime needs Spanner/PubSub/exports/media resources.

Impact: Wasted provisioning effort and misleading setup expectations. No apply was attempted. Validation: source/metadata review only; no repository execution.

Fix: Mark historical recipe explicitly and reconcile to chosen topology; preserve any still-used infrastructure before retirement. Validate a new plan in isolated provider context. Dependencies: Cloud project/region decision and resource inventory. Effort: 1–3 days depending retained legacy resources. Acceptance: terraform validate passes for retained plan; plan contains required resources and no unexpected legacy SQL.

### F-SEC-006 — Gateway budgets multiply across replicas and reset on restart

**Medium (conditional) · abuse controls · high static/metadata evidence; no exploit execution**. Per-process limiter is weaker than a shared account/IP budget in a replicated deployment.

Evidence: [brandme-gateway/src/middleware/rateLimiter.ts:56](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/middleware/rateLimiter.ts#L56); [brandme-infra/helm/brandme/values.yaml:102](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-infra/helm/brandme/values.yaml#L102)

Preconditions: More than one gateway process serves the caller, or pods restart. Expected: Documented per-member/address limit holds across routing/restarts. Observed: Limiter uses process Map; chart gateway replicas defaults to 2. Code acknowledges N-times budget.

Impact: Requests spread across replicas can exceed intended quota; additional downstream protection remains required. Validation: source/metadata review only; no repository execution.

Fix: Use shared atomic rate limiting or enforce fixed limit at trusted edge; preserve export exemptions and proxy IP verification. Dependencies: Chosen edge/shared store, trusted-proxy verification. Effort: 1–3 days. Acceptance: Round-robin requests across two pods hit one shared budget; spoofed forwarded IP cannot reset identity.

### F-SEC-007 — Gateway exits immediately on termination

**Medium · reliability · high static/metadata evidence; no exploit execution**. A rolling update can terminate accepted in-flight writes/responses without drain.

Evidence: [brandme-gateway/src/index.ts:106](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/index.ts#L106)

Preconditions: SIGTERM during request/DB activity. Expected: Stop accepting, drain in-flight work, close clients within grace deadline. Observed: Server handle is not retained for close; SIGTERM/SIGINT call process.exit(0).

Impact: Client sees ambiguous outcome; retries depend on idempotency and can worsen interruptions. Validation: source/metadata review only; no repository execution.

Fix: Retain HTTP server; drain requests then close Spanner/NATS; bounded timeout with truthful exit status. Dependencies: Request timeout/idempotency contracts. Effort: 0.5–1.5 days. Acceptance: Send synthetic slow request, terminate, verify drain/retry outcome and no accepted mutation lost; no live provider effect.

## CI evidence at pinned main

[Build, Test, and Deploy run 41091237404](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/41091237404) ran on `ed19dc151d103b108cf972e6d37971c55d5dcf60`, push event, 2026-10-30. The audit retrieved job metadata and selected test-summary lines from logs, sanitized before saving; raw logs were not retained.

| Check | Observed result and meaning |
|---|---|
| Test Core | **2146 passed, 20 skipped, 17 xfailed**, 4 warnings, 755.87s. These are CI counts, not tests rerun in the audit. |
| Foundation check | Same **2146 passed, 20 skipped, 17 xfailed**, 3 warnings; `pnpm smoke` step successful. |
| Gateway | 20 test files passed; lint/type-check/test job success. |
| Frontend | Locked install, production/critical advisory step and build/lint/type checks success. Does not prove browser backend journey. |
| Chain | Type-check and committed artifact verification success; this job is not a Preprod transaction test. |
| Security | Trivy current-tree fixable-CRITICAL gate and repo-wide secret gate success. All-severity SARIF report uploaded. No historical-secret scan implied by this workflow. |
| Images | Five service image build/runtime-smoke/publish legs success. This is actual CI registry interaction; registry permissions/retention remain unknown. |
| Deploy | Sandbox deploy job skipped. No deployed SHA established. |

Known quarantines are explicitly listed in [tests/conftest.py](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/tests/conftest.py#L58): 12 legacy consent/provenance tests lack the legacy schema fixture; 5 legacy wardrobe tests hit SERVER_TIMESTAMP-in-array behavior. Allowed skips include AP2 SDK oracle, Stripe live-test/mock prerequisites and live model, listed at [tests/conftest.py](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/tests/conftest.py#L98). Do not translate green CI into those checks passing. Root `test:journeys` and `test:providers` still call `not-yet`; targeted suites are separate.

The Consumer UI live-domain workflow assembles current UI with a separately checked-out domain commit `dafd3b169da777ec3e3a7fc2c3f0cab573358e2b` ([.github/workflows/consumer-ui.yml](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.github/workflows/consumer-ui.yml#L80)). That is a mixed-revision integration test, not end-to-end verification of the full pinned-main tree.

Evidence: [run metadata](evidence/security-ci-runs.json), [all 12 job/step records](evidence/security-ci-jobs.json), [sanitized summary lines](evidence/security-ci-log-summaries.json), and [history CI inventory](evidence/history-github-branch-ci.json).

[Repository Actions configuration metadata](evidence/security-github-config-metadata.json) was read without values: one secret name (GCP_SA_KEY, created/updated 2026-10-09) and zero repository variables. Required repository deploy-enable/project settings are absent in this scope; inherited organization configuration was not inspected.

The remote historical UI evidence now has an explicit [CI storyboard](visuals/ci-storyboard.png) and [result manifest](evidence/ci-live-results.json): artifact `12998005788`, run `41098774318`, live-domains job `124211331191`; UI merge commit `d657103ee21674ef14d6182572a78d75d0241b29` with domain commit `dafd3b169da777ec3e3a7fc2c3f0cab573358e2b`. These screenshots are historical composite-revision CI evidence, not new audit execution, pinned-main end-to-end evidence, or a production observation.

## Secrets, dependencies and execution safety

An auditor-authored read-only regex scan traversed 7,542 reachable Git objects, including 3,253 blobs (94,200,935 bytes); 231 binary blobs were skipped. It checked current and accessible-history text for common GitHub/AWS/Google/Stripe/private-key/named-credential patterns, emitting only path/line/blob ID and candidate fingerprints. It found 54 candidates, predominantly test fixtures, placeholder/example assignments and PEM header markers. No usable live secret was confirmed; candidates were not tested against providers. This is not a full entropy/gitleaks-equivalent scan, cannot prove no secret exposure, and excludes inaccessible Git objects, host secret stores, historical binary contents, downloaded build artifacts and full CI log bodies. See [redacted candidates](evidence/security-secret-candidates.json).

Current examples were examined only as committed templates. No unrelated `.env`, SSH store or production credentials were loaded. The names-only extractor includes constants as well as environment names and is explicitly a discovery index, not a claim that all 1,206 names are runtime configuration: [config reference index](evidence/security-config-names.json).

Before execution decisions, review covered package scripts, [pnpm-workspace.yaml](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/pnpm-workspace.yaml#L13) lifecycle allowlist, Docker stages/entrypoints, Claude hook, compiler/emulator download scripts by static references, CI install/build commands and mode guards. The final core image uses the hashed Python lock and refuses a default process; earlier Docker stages are historical and have different commands. No package install, lifecycle hook, repository test, build, application, migration, provider call or cloud provisioning ran in this audit.

No current advisory database scan was run locally. A final read-only GitHub alert review and upstream advisory checks for all 19 HIGH/Critical-metadata combinations found affected dependency pins and a gate/triage limitation (F-SEC-008 below). Comments claiming CVE fixes were not accepted as independent evidence. Workflow actions commonly use mutable version tags; no pull_request_target/workflow_run privileged checkout path was found in the reviewed workflows. Branch controls and build credential risks remain F-SEC-003/004.

## F-SEC-008 - Dependency alerts require reachability triage despite green CI

**Medium pending reachability triage; confirmed gate limitation, not confirmed application exploitation.** A complete visible open-alert listing on 2026-11-01 contains 78 Trivy alerts. Raw GitHub rule metadata labels 18 High and 1 Critical; these are **not validated vulnerability counts**. The [current gate](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/.github/workflows/ci-cd.yml#L545) blocks only fixable CRITICAL findings. [Alert metadata](evidence/security-github-advisory-metadata.json), [initial details](evidence/security-advisory-detail.json), [expanded details](evidence/security-advisory-detail-expanded.json) and [primary-source triage](evidence/security-advisory-triage.json) preserve the distinction. Dependabot alert access returned HTTP403, so its state is unknown.

| Alert / locked dependency | Current primary-source assessment | Reachability in this repository |
|---|---|---|
| [508](https://github.com/brandmeonline/Brand-Me-Labs/security/code-scanning/508), protobuf 4.25.9, CVE-2026-0994 | Published affected version; nested Any parsing bypasses a recursion limit. [Upstream fix discussion](https://github.com/protocolbuffers/protobuf/pull/25239), [reviewed version range](https://github.com/advisories/GHSA-7gcm-g887-7qv7). | Runtime lock contains package. No direct `json_format.ParseDict` call found in sampled canonical code; attacker-controlled input path unverified. |
| [505](https://github.com/brandmeonline/Brand-Me-Labs/security/code-scanning/505), datamodel-code-generator 0.34.0, CVE-2026-55415 | Within upstream affected range; malicious schema extensions can inject Python into generated imports. [Maintainer advisory](https://github.com/datamodel-code-generator/datamodel-code-generator/security/advisories/GHSA-5578-w22f-pfx9). | Generator is invoked on repository schemas by `packages/contracts/scripts/generate.mjs:158`; external untrusted schema intake not found. Maintainer advisory says patched version None while reviewed DB/Trivy lists 0.64.0; verify the exact fix before selecting an upgrade. |
| [496](https://github.com/brandmeonline/Brand-Me-Labs/security/code-scanning/496), Black 26.10.0, CVE-2026-114134 | Upstream requires Black's GitHub Action with `use_pyproject: true`; patched 26.10.1. [Maintainer advisory](https://github.com/psf/black/security/advisories/GHSA-cg8m-r9f2-5wm2). | Neither `psf/black` nor `use_pyproject` occurs in reviewed workflows; this specific exploit prerequisite is absent. |
| [43](https://github.com/brandmeonline/Brand-Me-Labs/security/code-scanning/43), legacy aiohttp 3.9.1, CVE-2026-34520 | Current instance and maintainer classify **Low**, conflicting with rule metadata Critical. [Maintainer advisory](https://github.com/aio-libs/aiohttp/security/advisories/GHSA-63hf-3vf5-4wqf). | Legacy manifest, absent from default core image hashed lock. Do not report a confirmed critical exposure. |
| [474](https://github.com/brandmeonline/Brand-Me-Labs/security/code-scanning/474), legacy aiohttp 3.9.1, GHSA-2g87-pp6c-29x5 | Maintainer says **Moderate**; scanner says High; patched 3.14.4. [Maintainer advisory](https://github.com/aio-libs/aiohttp/security/advisories/GHSA-2g87-pp6c-29x5). | Legacy affected pin; no aiohttp call found in sampled legacy core Python; actual deployed use unknown. |

The final prerequisite review covers **all 19 distinct package/advisory combinations** with High/Critical rule metadata: eight `datamodel-code-generator`, eight `aiohttp`, one each `protobuf`, Black and `langchain`. The table above highlights five; the [19-record triage](evidence/security-advisory-triage.json) contains the rest, current source links, version ranges and unresolved prerequisites. This is a static applicability review, not proof that all 19 are exploitable.

The expanded review materially distinguishes two packaging cases. The generator's JSON Schema invocation is real, and the same lock also installs it into the [default core image](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-core/Dockerfile#L96). Current schema inputs contain no risky external references or extension fields; the reviewed invocation has no `--url`, GraphQL or `--extra-template-data` option. Seven additional upstream advisories cover SSRF, local-file references and generated-code injection; upgrading alone must also establish an explicit trusted-reference policy. No malicious schema or exploit was executed.

`langchain==0.1.0` is installed by the [default agents stage](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-agents/Dockerfile#L75), and agents belongs to the CI image matrix. Its [public-prompt advisory](https://github.com/langchain-ai/langsmith-sdk/security/advisories/GHSA-3644-q5cj-c5c7) requires pulling and trusting an external Hub prompt; repository source searches found no `pull_prompt`, `pullPrompt` or `hub.pull` call. The affected package can ship, but this specific vulnerable use was not established. By comparison, the eight aiohttp alerts concern a legacy manifest absent from the default core lock, with no first-party aiohttp call located. Further severity drift exists: upstream classifies CVE-2026-111066 Moderate, CVE-2026-111064 Low and CVE-2026-34516 Low despite higher scanner metadata; the first also has a patched/affected boundary inconsistency documented in the evidence.

Unreviewed remainder: 59 visible Low/Medium-metadata alerts have not each received upstream/reachability triage. No complete current container OS/package SBOM or exact deployed-image scan was performed. Text searches cannot exclude indirect/transitive consumers; Dependabot, deployed image digests and cloud runtime state remain unavailable.
Recommended PR: separate runtime/build/legacy dependency inventories; review compatibility and fixed versions; regenerate the hashed lock/contracts; run isolated regression and a current lock/image scan; gate high runtime findings or record narrow, owned, expiring exceptions. Effort: 1-3 days for triage/lock work, assuming compatible updates. Acceptance: exact-image scan plus no unreviewed high runtime finding, fixed negative fixtures and passing substantive regression. No package install or exploit was run in this audit.

## Reliability, privacy and readiness limits

Retain transactional outbox+inbox deduplication, lease fencing, network/contract-scoped chain projections, selected-category exports, processing-freeze/tombstone hooks, and strict-mode guards. Their successful source or emulator checks do not replace deployed workers, schema rollout, retry/dead-letter consumers, storage policies and restoration evidence. Broker acknowledgement means Pub/Sub accepted an event, not that rewards/media/deletion applied it.

Data path: member profile/persona/social/wardrobe and consent enter Spanner; upload media goes to a private bucket through signed targets; jobs transfer media only after consent to an approved provider; outputs require expiry/purge worker; events carry privacy-classed payloads and internal references; selected rights exports go to a dedicated bucket. Provider retention and chain-public commitments are separate from local tombstones. No production backup retention, successful restore, alert route, RPO/RTO, incident owner, real consent capture or full-account deletion completion was observable. UI guest-clear privacy gap is tracked separately as F-UX-002. The production browser-login gap is F-UX-003.

Readiness: **isolated local demo** has substantial CI emulator evidence but was not observed on this host; **integration-tested staging pilot** remains blocked by full-current-tree browser auth/routing, required workers/resources/IAM and acceptance tests; **production** is not established. Release governance, graceful shutdown, dependency-aware readiness, backups/restores, alerts and explicit external-provider verification are required before a production verdict.

Remaining scope: execute isolated runtime/dynamic authorization tests, full lockfile/current-advisory scan, cloud project-specific read-only resource/IAM/DNS/backup metadata, actual deployment SHA/digest, protected release-flow trial, provider sandbox operations and restore/drain tests. Resolve by supplying an approved isolated runtime plus selecting the exact authorized cloud project/environment and appropriate read-only metadata access. Do not send raw credentials.
