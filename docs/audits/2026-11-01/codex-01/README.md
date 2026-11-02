# Brand-Me-Labs repository audit

**Brand.Me has substantial reusable product and platform work, but it is not yet one connected consumer product. The fastest path is to finish and verify its existing user journeys, not replace the stack.** The principal gaps are production browser sign-in, authenticated wardrobe storage, recommendation inputs, background consumers, commerce/assistant routing, and full-account privacy operations. Several useful additions remain on unmerged branches. Evidence and exact file references are in the linked reports and [consolidated findings](evidence/findings.json).

Auditor: **Codex, lead repository auditor**, with independent architecture, branch/history and security/infrastructure reviewers. Audit date: **2026-11-01**. Authorized target: **[brandmeonline/Brand-Me-Labs](https://github.com/brandmeonline/Brand-Me-Labs)** only. This is an audit and delivery proposal; no application remediation, commits, pushes, branch deletion, permission changes, deployment, shared migration, purchase, wallet signature or external message was performed. The original checkout was preserved.

**Status: INCOMPLETE against the full requested scope.** The static inventory, focused connectivity review, branch comparison, requirement-to-capability mapping, accessible GitHub evidence and artifact pack are delivered. Complete consequential-source/branch-unique review, requirement-specific implementation and acceptance verification, fresh isolated application/browser execution, full dependency/container/history analysis and authorized deployed-system verification remain unfinished. These limits are itemized below; sampled work is not described as exhaustive.

## Navigate the audit

| Report | What it answers |
|---|---|
| [Product and architecture](PRODUCT_ARCHITECTURE.md) | Intended product, 20 capabilities, 39 components, 150 inventoried requirements, useful/disconnected code, assets |
| [Requirement traceability](REQUIREMENTS_TRACEABILITY.md) | All 150 catalog requirements mapped to capability/source context; individual acceptance remains unassessed |
| [Branches and code preservation](BRANCHES_CODE.md) | Every available head, exact replacements, active lane integration, conditional retirement, recovery proposal |
| [Integrations and infrastructure](INTEGRATIONS_INFRASTRUCTURE.md) | 24 integrations; implementation, invocation, configuration, resources, permissions, network and business verification assessed separately |
| [User flows](USER_FLOWS.md) | 17 traced guest/member/operator journeys and exact missing boundaries |
| [Visual walkthrough](visuals/index.html) | Rendered diagrams, committed baselines, scoped CI screenshots and proposed sign-in wireframe |
| [CI journey provenance](CI_JOURNEY_EVIDENCE.md) | Six retrieved screenshots, ten development checks, precise mixed revisions and failed visual gate |
| [Security and reliability](SECURITY_RELIABILITY.md) | Threat boundaries, CI results, secret/advisory triage, release and operation risks |
| [Roadmap](ROADMAP.md) | 14 proposed work packages, dependency order, effort ranges, acceptance evidence and implementation prompts |
| [Evidence ledger](evidence/README.md) | Commands, inventories, coverage, reproduction and validation |
| [Checkpoint](AUDIT_STATE.md) | Baselines, completed phases, remaining scope and exact continuation |

## Four different baselines

| Surface | Pinned revision and observation |
|---|---|
| User's original local checkout | Clean `main`, **`0f5f58a9eecaca46b367c9bd96f89654343fa5fb`**, 370 commits behind remote main. No uncommitted/untracked first-party appendix was needed because status was clean. Preserved without fetching into it. |
| Remote canonical main | **`ed19dc151d103b108cf972e6d37971c55d5dcf60`**, detached in isolated audit clone. 1,340 tracked files. Main did not change during final recheck. |
| Important unmerged lanes | Consumer domains PR #66 **`babb3604ae2f33018edf0ad45270887d4b01945b`**; UI preview PR #63 **`0ff12fbdbce2a8b4ea1391a02ef3ea821ae6a420`**; rights PR #70 **`a05f2e03e58e55cc2b392b8abc7b19f59659f820`**. Exact final branch inventory/deltas are in the branch report. |
| Historical UI CI | UI PR merge **`d657103ee21674ef14d6182572a78d75d0241b29`** with separate backend **`dafd3b169da777ec3e3a7fc2c3f0cab573358e2b`**. Synthetic identity, HTTP and Spanner emulator. This is a composite, not current-main or production proof. |
| Deployed system | **Unknown SHA/digest and unknown operating state.** Exact-main CI published images, but deployment was skipped. Successful empty GitHub deployment/environment listings do not prove external infrastructure is absent. |

Sources: [pre-fetch local snapshot](evidence/local-baseline-before-fetch.txt), [baseline/recheck](evidence/baseline.json), [branches](evidence/branches.json), [CI runs](evidence/security-ci-runs.json), [CI visual provenance](evidence/ci-visual-provenance.json). Initial inventory contained 34 remote heads; a new head appeared during final recheck and was separately reviewed without invalidating unchanged main conclusions. No automatic cleanup followed.

## What was intended, and what actually exists

The dated product contracts describe a consumer style and identity experience: editable personal preferences, an owned wardrobe and spatial room, outfits and discovery, selected-friend decisions, participation rewards, controlled shopping/agent assistance, and optional digital rights. Guest exploration should work without demanding a wallet, camera or contacts. Wallets and provenance are supporting capabilities, not the entire product. Roles include guests, members, moderators/operators, providers and delegated agents. The [architecture report](PRODUCT_ARCHITECTURE.md) distinguishes current October requirements from older digital-passport/enterprise descriptions.

Remote main contains a substantial Next.js consumer UI and operations console, gateway authentication/authorization primitives, Python domain services, Spanner schemas, transactional events, selected rights export, chain reconciliation and compiled artifacts, provider/commerce authority checks and spatial assets. The local checkout predates much of this. These implementations differ in reachability and verification; their union is not an observed finished service. The [capability inventory](evidence/capabilities.json) preserves the five separate assessment dimensions.

**What a user can do is environment-dependent.** Source evidence supports device-only guest onboarding and spatial wardrobe behavior. Historical CI demonstrates development sign-in, explicit guest migration, persisted style edits, API-created wardrobe display, social decisions, reward settlement, notifications, blocking and sign-out for its exact composite revisions. The six screenshots are preserved with verified archive digest. No publicly deployed user journey was established, and this audit did not launch the app. Real browser sign-in on strict modes, the spatial Add UI feeding the server wardrobe, commerce and complete account deletion remain incomplete. [Journey traces and qualifications](USER_FLOWS.md), [CI execution evidence](CI_JOURNEY_EVIDENCE.md).

## Consequential gaps and useful work to keep

| Priority / finding | Consequence and disposition |
|---|---|
| **F-UX-003 — browser identity** | OIDC API verification exists, but the browser's production callback/session path does not. Keep the fail-closed guard; connect a real identity flow. |
| **F-ARCH-006 / 003 — wardrobe and recommendations** | Spatial UI uses guest IndexedDB; canonical persona composition supplies empty candidate/wardrobe sources. Retain UI/storage/domain code and connect it deliberately. |
| **F-ARCH-002 — background work** | Publisher code is not enough: consumer jobs/subscriptions need runtime composition for deadlines, rewards and lifecycle work. |
| **F-ARCH-001 / CAP-017 — dormant routes** | Commerce/provider/assistant and console ops surfaces have valuable code but no complete mounted execution path. Keys cannot repair this. |
| **F-ARCH-004 / F-UX-002 — privacy** | Current export covers selected rights, full deletion is unavailable, and “clear guest data” leaves spatial stores. State real scope and implement promised cleanup. |
| **F-BR-001 / 002 / 004 — branch integration** | Consumer and rights branches both use V016; rights commands still need routing/strict registration; credit redemption has no checkout caller. Preserve accumulated fixes before integration. |
| **F-SEC-003 / 004 — release identity** | No branch protection/rulesets observed; publishing uses a stored Google service-account key. Review/CI enforcement and scoped federation are concrete next controls. No compromise was observed. |
| **F-SEC-002 / 006 / 007 / 008 — operations and dependencies** | Static readiness, per-process rate limits and immediate gateway exit weaken deployment safety. Green CI coexists with open dependency alerts because the gate is narrower than all severities; alert reachability needs disposition. |

Retain contracts, transactional outbox/inbox deduplication, idempotent domain operations, strict guards, member-scoped authorization, media consent controls, tested UI foundations, hashed assets and rights reconciliation. Connect these through the canonical gateway/services. Consolidate stale repository maps and legacy infrastructure recipes only after confirming their consumers. Consider obsolete simulated routes and duplicate historical scaffolding for eventual archival; the audit does **not** justify blanket source deletion. [Component recommendations](PRODUCT_ARCHITECTURE.md), [security controls to retain](SECURITY_RELIABILITY.md).

## Branch decisions

The final **35 remote heads** yield **10 KEEP, 3 INTEGRATE, 2 PRESERVE THEN RETIRE, 2 UNKNOWN and 18 conditional DELETION CANDIDATES**. The original local main is separately KEEP. The final-arriving BR-036 / draft PR #71 contains a Stripe Connect plan only and is KEEP; its provider assertions were not independently verified and it adds no operating payment capability. Final PR metadata contains 70 PRs, including five open. The branch report gives exact refs/SHAs and both snapshots.

Integrate PR #66 consumer domains, then PR #63 UI against accepted contracts; coordinate migration numbers with PR #70 before its rights integration. Keep active bench/lane refs that workflows or assignment documents still consume. Preserve PR #29 foundation-transplant and historical design value before considering retirement. Several Codex branches appear ahead only because their equivalent changes were squash-merged: historical tree/patch comparisons and retained current paths support conditional retirement, not replaying old commits. No branch was deleted, and **no durable backup was created**. A retained ref or bundle plus tested recovery, external-consumer confirmation and fresh remote-tip verification are mandatory proposed prerequisites. [Exact preservation and cleanup plan](BRANCHES_CODE.md).

## Beyond API keys

The narrow topology needs browser server → gateway → consumer API → migrated Spanner, plus the actual workers/subscriptions for selected event effects. A real pilot also needs an identity tenant/client and callback URLs, authorized GCP project/resources, per-service IAM and workload federation, secret delivery, DNS/TLS/ingress, scoped storage where enabled, migrations, deployment health, alerts and backup restoration. Merchant, model, wallet and try-on features need additional entitlement/network/data/privacy work as well as their missing code connections. Provisioning code is not proof of applied resources; successful CI image publishing proves only the registry operation at that time. [Complete setup matrix and official sources](INTEGRATIONS_INFRASTRUCTURE.md).

## Readiness and validation

| Level | Verdict and gates |
|---|---|
| Isolated local demo | **Promising but not independently revalidated here.** Exact-main unit/emulator CI is substantial; historical composite browser CI works in its scope. Prove one canonical same-revision journey before calling the demo complete. |
| Integration-tested staging pilot | **Not established.** Requires real browser identity, authenticated UI storage, workers, selected resources/IAM and one full staged acceptance journey with accurate privacy scope. |
| Production | **Not established; launch-blocking gaps remain.** Add enforced release controls, dependency disposition, resilient deployment, restore/alert evidence and real authorized provider/network checks for every advertised external effect. |

Exact-main [CI run 41091237404](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/41091237404) reports **2,146 passed, 20 skipped, 17 expected failures** in Test Core. Foundation repeats that suite; it is not another 2,146 unique tests. Gateway reports 20 passing test files. Image publishing succeeded; deployment was skipped. PR #66's separate shell visual comparison failed because `consumer-1440x900-light.png` dimensions changed; successful live-domain checks do not erase that failure. [Sanitized CI summaries](evidence/security-ci-log-summaries.json), [CI visual evidence](CI_JOURNEY_EVIDENCE.md).

Auditor-owned non-executing checks parsed **330 Python files and 105 JSON files with no parse errors**, inventoried 1,340 tracked files and 154 assets, and verified all 84 entries in the curated asset manifest against their recorded size/hash. This does not verify imports, types, licensing, rendering, fit accuracy or application behavior. A redacted historical-secret scan processed an inventory of 3,253 blobs, including 231 skipped binary blobs; no usable live credential was confirmed, and credential validity was not tested. **78 open code-scanning alerts are triage inputs, not 78 confirmed vulnerabilities**; metadata severity conflicts and inapplicable prerequisites were found in selected checks. [Static evidence](evidence/static-checks.json), [assets](evidence/assets-architecture.json), [security/advisory scope](SECURITY_RELIABILITY.md).

The historical browser suite uses a custom development service composition with an in-process outbox-to-rewards consumer. It does not verify canonical service authentication, Pub/Sub ingress or scheduled jobs. Future acceptance must use both matching revisions **and the actual composed service/worker entrypoints**. [Harness boundary](CI_JOURNEY_EVIDENCE.md).

## Fastest credible next milestone and remaining scope

Start with WP-01 in the [roadmap](ROADMAP.md): same-revision disposable acceptance evidence. Then connect browser-created wardrobe items, real background completion and truthful account/cleanup state. Prove the wardrobe-and-friends loop with synthetic users before adding production identity and staged operational gates. This recovers current investment and keeps retailer/AI/chain prerequisites from obscuring the first complete product outcome.

| Unverified work | Exact prerequisite / next verification |
|---|---|
| Fresh application/build/browser/dynamic security tests | Approved disposable runtime with restricted filesystem/network and no production credentials. Docker CLI is installed but its selected engine was unavailable; a sufficient alternative sandbox was not established. Application startup was not attempted. |
| Full requirements/source/branch review | Continue the [coverage register](evidence/coverage.json): validate all 150 mapped requirements against their actual acceptance criteria, remaining consequential files and branch-specific changed lines. Capability/entrypoint mapping is not per-requirement implementation or acceptance completion. |
| Cloud deployment, IAM, database migration ledger, DNS/TLS, backups and alerts | Select the exact authorized project/environment/region and provide existing read-only metadata access. Resolve actual SHA/digests, applied schemas, identity scopes and restore evidence; do not supply raw secrets. |
| Current full dependency/container/history assurance | Complete lockfile/image SBOM/advisory matching and reachable-call-path triage; Dependabot metadata was inaccessible. Analyze excluded historical binary/generated artifacts in an appropriate isolated scanner. |
| Providers, wallet/network and external side effects | Select authorized sandbox accounts, entitlements, contract/network identifiers and explicit operation scope. Real purchases/signatures/customer messages remain outside this audit authorization. |
| Branch retirement and privacy decisions | Confirm external branch consumers, retained backup location/recovery, migration ownership, pilot data scope and retention commitments; permission changes or deletion require later authorization. |

The evidence pack is usable now. Its checkpoint states exactly how to resume without repeating completed investigation or combining incompatible revisions.
