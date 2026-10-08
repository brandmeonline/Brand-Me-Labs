# 06 — Build sequence, acceptance and launch evidence

Execute this as a complete product program initiated by one kickoff prompt. The stages below manage dependencies and preserve working software; they are not permission to stop after a passport demo. All consumer journeys remain in scope. External access gates are recorded precisely so they cannot be replaced with pretend integrations.

## 1. First execution and durable working record

Read root `CLAUDE.md`, applicable repository instructions, this entire package and the machine contracts before modifying application code. Reconcile against the current branch because the audited baseline may no longer be HEAD. Create an implementation branch. Preserve unrelated changes and the repository's review/merge rules.

Create `docs/build/implementation-status.md` with baseline SHA, active branch, stage, completed acceptance IDs, evidence locations, current blockers and exact next actions. Every stage updates it. A later model session must be able to resume by reading this file plus the specification, without reconstructing hidden conversation context.

Create `docs/build/compatibility-lock.md` with exact Node, pnpm, Python, Next, React, TypeScript, Three, R3F, Motion, model-viewer, MediaPipe and Midnight tuple versions. Include source/check date and integration test outcome. Commit actual lockfiles. Do not write “latest” as an executable dependency policy.

Create `docs/build/deviations.md`. A deviation states requirement, reason, chosen replacement, product impact, evidence and whether founder approval is needed. Resolve ordinary implementation details autonomously. Do not silently delete social shopping, editable identity, 3D environments, real data persistence or Midnight to simplify the build.

## 2. Work packages

### W00 — Audit, executable baseline and honest modes

Inspect dependency manifests, startup paths, schemas, migrations, authentication, stub flags and tests. Run the existing targeted tests and record failures honestly; the old documents' passing claims are not current execution evidence. Identify stale tests such as cube constructor/face-count expectations. Decide whether a failure is a real regression, pre-existing defect or invalid test before changing it.

Add explicit mode configuration and production boot guards. Enumerate all trust-path fixtures: fake chain hashes, fake proofs, constant ESG values, fake commerce IDs, default reprint eligibility and hardcoded authentication shortcuts. Keep fixtures only in dedicated demo adapters with visible labels. Do not remove a useful local mode to solve this problem.

Deliver an initial smoke command for gateway → brain → persistence, plus frontend boot. Resolve port collisions: proposed local ports are consumer 3000, gateway 3001, console 3002, brain 8000, policy 8001, orchestrator/worker-compatible entrypoint 8002 and cube 8007. Preserve other existing ports where possible and update compose/proxy/env together. No service should infer another service's port from a stale README.

Exit evidence: clean install/boot instructions from a fresh checkout; actual baseline test report; mode guard negative test; no fabricated production proof path.

### W01 — Workspace, contracts and design foundation

Add frontend/shared packages to the pnpm workspace. Upgrade the frontend toolchain in an isolated change, preserving routes through adapters. Build shared design tokens and accessible Button, Link, Dialog, Drawer, Tabs, Slider, Switch, Input, Select, Toast, Skeleton, EmptyState, ErrorState, StatusChip, Price and EvidenceLabel primitives.

Create the app shell, authenticated/guest layouts, typography, warm surfaces and responsive navigation. Add a development-only component gallery and visual fixtures. Use licensed self-hosted fonts, a consistent icon set and original badge SVGs. Include reduced-motion and dark-mode tokens. Do not import an entire UI template whose structure replaces the specified experience.

Generate typed API clients from OpenAPI and test schema drift in CI. The supplied JSON schema file defines core acceptance constraints; extend it into the complete API without weakening those constraints. Document snake_case wire fields and generated client conventions.

Exit evidence: shell at all three reference viewports, keyboard navigation, token consistency, no horizontal overflow at 320 px, and a successful supported build.

### W02 — Persistence, auth and privacy boundaries

Implement versioned Spanner migrations, domain repositories, identity mapping, session middleware, object-level policy and the transactional outbox/inbox. Create Firestore projections and rules, media upload quarantine, provider connection records, request correlation and redacted logs.

Backfill the existing two persona columns and asset/cube fields without inventing values. Resolve schema/code mismatches explicitly. Add export/deletion job scaffolding now so later domains register their data categories as they are introduced.

Exit evidence: a saved record survives service restart and a second browser session; unauthorized object reads/writes fail; transaction retry does not duplicate outbox events or effects; projection revocation works; migration runs from empty and baseline schemas.

### W03 — The first 90 seconds and Looking Glass

Build the full guest onboarding, optional sign-up/migration, intent selection, six visual choices, room choice and first personalized look. Use fictional licensed products with real assets and honest source labels. The deterministic recommender works with no AI key.

Build all 12 persona controls, declared/inferred/effective views, lock/unlock, learning toggle, source explanations, suppression, snapshots, reset, conflict handling and immediate recommendation preview. Persist every confirmed change through the domain API. A refresh must not revert to mock data.

Exit evidence: a new user reaches useful value without wallet/camera/contact access; guest migration is idempotent; another device sees the saved profile; a locked axis resists inference; deleting evidence changes recommendations and prevents immediate reuse.

### W04 — Wardrobe, outfits and real 3D assets

Implement wardrobe intake from manual entry/photo, product save, receipt draft and verified order events; collections; condition/care; duplicate resolution; outfits/proposals; packing lists. Separate product, wardrobe entry and attested instance.

Create or commission the three room assets and six initial garment assets defined in chapter 02, with original geometry/material work and asset-rights manifests. Procedural creation/export is acceptable if the result meets visual review; runtime primitive boxes are not the final garment library. Produce GLB LODs, permitted texture derivatives, thumbnails and explicit USDZ support where required. Record dimensions, pivots, collision bounds and fidelity. A room must look intentional from its actual camera, not only an external modeling viewport.

Implement selectable scene objects, named views, keyboard placement, semantic slot remapping, persistent layout, 2D equivalent, overflow handling and quality governor. Build and record the signature add-to-closet animation including success, retry, undo and reduced-motion paths. Virtualize a 500-item wardrobe while limiting rendered scene complexity.

Exit evidence: all three environments load with real assets; placement survives refresh/theme change; animation is tied to a real committed item; device loss/context loss yields usable 2D; 500-item organization remains functional.

### W05 — Social decisions, collaboration and loyalty

Build friendship request/accept/block, selected-audience sharing, five-minute server-timed decisions, yes/pass/alternative responses, deadline handling, zero-reply states, friend outfit proposals and sanitized share cards. The demo must use clearly fictional members and support multiple real test sessions.

Implement the reward ledger, rule versioning, daily/weekly caps, abuse exclusions, reversals, benefits reservations and six badge criteria. Add in-app notifications and optional external delivery adapters only with real provider setup. Build reporting/moderation and dispute visibility in the console.

Exit evidence: two independent sessions complete a decision and receive exactly the eligible reward once; parallel submissions cannot double-award; block/revoke removes access; pass and yes have equal reward eligibility; redemption failure returns the reservation; badge evidence is inspectable.

### W06 — Discovery and provider operations

Implement the provider registry, console setup forms, catalog normalization, source/freshness labels, affiliate disclosure, approved data-use manifest and ingestion jobs. Add deterministic local provider fixtures with full failure behavior, the Nordstrom/Impact publisher adapter shell against current official schemas, and verified handoff behavior.

If approved Nordstrom/Impact access is available, run the scoped read-only integration tests and record evidence. If unavailable, the setup checklist and link-only path must be complete, and the missing approval is an explicit integration gate. Do not block the entire wardrobe/social application on a retailer agreement.

Exit evidence: saved discovery products retain exact variant/source data; stale prices are labeled; unauthorized media transformations are rejected; cursor replay does not duplicate products; unavailable checkout yields the correct handoff.

### W07 — Assistant and bounded commerce

Implement task records, structured tool execution, research/prepare/buy modes, authenticated MCP access, delegation editor, trusted purchase approval, canonical quote hashes, budget reservations, durable submission and order reconciliation. Build ACP/AP2/UCP adapters only for verified supported versions and capabilities. Implement A2A for an actual approved integration need, otherwise leave it explicitly unconfigured with documented contract tests.

Migrate or disable misleading legacy tool aliases. Cover stock loss, price change, expiry, wrong principal, revoked delegation, duplicated calls, partial shipment, exchange/refund and timeout after provider acceptance. Connect real order observations to wardrobe states.

Exit evidence: an agent can research and prepare; cannot purchase without valid authority; cannot mutate approved material terms; cannot overspend through concurrency; an unknown outcome is reconciled without a duplicate purchase. Provider-specific sandbox evidence is separate from fixture behavior.

### W08 — AR and try-on

Implement the capability ladder: 3D inspection, room placement, supported live overlay, optional photo try-on, separately gated calibrated fit. Add model-viewer with actual GLB/USDZ assets and tested platform handoffs. Add MediaPipe worker lifecycle and camera permission/error/cleanup states. Integrate the selected approved photo provider behind consent, job and deletion interfaces.

Calibrated fit remains unavailable unless a real measurement/model pipeline validates it; do not relabel generative imagery as fit. Implement honest camera/AR fallback on unsupported devices. Where provider credentials are absent, show the complete explanation/setup state and retain other preview modes.

Exit evidence: actual supported device tests for each claimed AR mode, camera stops on exit, no unconsented frame uploads, previews carry fidelity labels, unsaved media expiry is demonstrable and saved media deletion works.

### W09 — Real Midnight rights and lifecycle

Replace the stub client and hash-based proof claims with the pinned real SDK/provider architecture. Build Compact contracts, constraint/property tests, private-state backup/recovery, wrong-network protection, operation tracking and real observation/finality handling. Implement claim-level passport evidence and field-level privacy.

Implement transferable entitlement and licensed reprint workflows, manufacturer capability registry, quota consumption, signed production evidence and child-instance lineage. Keep physical verification, rights and payment status separate. Add optional Cardano anchoring only through a verified adapter without delaying the primary Midnight path.

Exit evidence: actual local contract tests and Preprod issue/prove/transfer/consume transactions; replay/concurrency rejection; restored private state works; invalid proof leaves app state unchanged; no production stub fallback; clear managed-prover disclosure where applicable.

### W10 — Complete My Data, moderation and operational recovery

Complete export, deletion, provider disconnect, consent revocation, derived-data suppression, account switching, private-share invalidation and backup restore/tombstone tests. Add operator queues for ingestion failures, uncertain orders, stalled chain operations, reward disputes and manufacturing disputes.

Instrument budgets, queue age, provider health and product metrics without sensitive payloads. Document credential rotation, order reconciliation, wallet-state recovery, issuer revocation, incident response and migration rollback. Run a representative restore exercise.

Exit evidence: a member can inspect and change their backend preference data, export it and request deletion with a truthful receipt; old projections/caches no longer leak it; operations can resolve failures without editing database balances by hand.

### W11 — Integrated quality, release candidate and handoff

Run the entire acceptance catalog against the integrated application. Fix material visual and journey defects; do not substitute a set of disconnected screenshot routes. Verify startup from clean checkout with documented prerequisites. Capture the final consumer walkthrough, device evidence and completion matrix.

A reviewable release candidate includes implementation commits, schema migrations, licensed asset manifests, tests, setup scripts, operator runbooks and precise integration status. It does not automatically authorize production deployment, customer messaging, actual purchases or mainnet writes.

## 3. Required developer commands

The following commands are **deliverables to implement**, not commands claimed to exist at the audited baseline:

| Command | Required behavior |
|---|---|
| `pnpm setup:demo` | Validate runtimes, prepare emulators/fixtures/assets, create safe local config; idempotent |
| `pnpm dev:demo` | Start consumer, API/domain dependencies and deterministic providers; print usable local URLs |
| `pnpm dev` | Start configured development environment; fail clearly on missing required variables |
| `pnpm check` | Types, lint, schema/contract drift, documentation links and targeted unit/integration checks |
| `pnpm test:journeys` | Browser acceptance journeys with test isolation and retained failure traces |
| `pnpm test:providers` | Provider conformance fixtures; live suites opt-in and capability-scoped |
| `pnpm test:midnight:local` | Compile/test pinned contracts and adversarial state transitions locally |
| `pnpm test:midnight:preprod` | Authorized external network tests; no Mainnet fallback |
| `pnpm assets:validate` | Asset manifests, licenses, dimensions, compression, loadability and payload budgets |
| `pnpm evidence:report` | Assemble actual results and unmet gates without fabricating passes |

Commands may orchestrate Python/Docker tools, but prerequisites and failure messages must be explicit. If a required runtime is unavailable, report the exact missing component and continue all independent work. Never label an unexecuted test passed. Demo setup cannot download unlicensed commercial assets or require personal wallets/payment cards.

## 4. Verification design

Use tests for behavior and trust boundaries, not snapshots that merely mirror implementation. Each acceptance ID in `contracts/acceptance-catalog.json` must map to a test, inspected artifact, measured benchmark or explicit external evidence. Report `passed`, `failed`, `blocked`, `not_run` or `not_applicable` with reason. “Implemented” is not a test result.

### Test layers

- **Domain tests:** persona precedence/suppression, outfit versions, decision deadlines, reward caps/reversals, money arithmetic, grants, quote binding, rights state transitions.
- **Database integration:** migration from baseline, transaction conflicts, idempotency, outbox/inbox, ledger atomicity, projection versions and deletion propagation.
- **Provider conformance:** schema validity, pagination, signatures, authentication, timeout/unknown behavior and retained references. Use official fixtures/sandboxes where available.
- **Contract tests:** Compact constraints and adverse witnesses, commitment domains, transfer/reprint uniqueness, artifact/runtime compatibility, recovery and genuine network observations.
- **Browser journeys:** real API/persistence, two sessions, reloads, keyboard/touch, offline/slow network, expired grants, missing provider and denied camera.
- **Visual inspection:** reference viewports, all room themes, polished garment assets, contrast, focus, typography, motion and unclipped copy.
- **Security tests:** object authorization, token audience, CSRF, upload/import SSRF, malicious provider text, webhook replay, public DTO filtering, secrets/log redaction and revoked shared-cache access.

### High-value adversarial scenarios

| Scenario | Required observation |
|---|---|
| Two devices change one persona version | One accepted revision; the other sees a mergeable conflict |
| An inference worker races a manual axis lock | Declared locked preference wins |
| A decision response arrives at the deadline | Server time and one documented boundary determine eligibility |
| Ten duplicate reward events arrive concurrently | Exactly one ledger cause and correct balance |
| Two benefit redemptions spend the same points | At most available points are reserved; no negative available balance |
| A share is revoked while cached | Subsequent access loses protected fields and stale preview is invalidated |
| Agent reads a product description containing instructions | Text remains data; no credentials, scope changes or unauthorized tool call |
| Price changes after approval | New quote required; old approval rejected |
| Merchant accepts, request times out | Existing operation reconciles; no duplicate charge/order |
| Refund webhook arrives before delayed fulfillment event | Independent payment/fulfillment facts remain consistent |
| Wallet switches accounts during proving | Operation aborts/rebinds safely; private state is isolated |
| Transfer proof is replayed on a different network | Rejected before state mutation |
| Two reprint jobs consume the last allowance | One succeeds; the other fails without manufacture authorization |
| A manufacturer retries a completion callback | One child issuance/lineage update |
| Account deletion races a queued inference job | Job cannot recreate deleted profile data |
| Database is restored from an older backup | Tombstones reapply and external orders/chain state reconcile |

## 5. Performance and accessible quality

Measure performance on declared hardware/network conditions and publish bundle/asset sizes. Initial target: LCP ≤2.5 seconds, INP ≤200 ms and CLS ≤0.1 for ordinary member routes under the stated test profile. Treat these as goals requiring measurements; one Lighthouse score is not field evidence. The 3D route has separate first-usable-scene and frame-time budgets in chapter 02.

Lazy-load Three, MediaPipe, wallet/proving and heavy try-on code only on the relevant interaction/route. Do not preload all rooms or all garment LODs. Stream the closet shell and list first, warm the selected room, then load its visible capsule. Cache licensed immutable derivatives by content hash and keep authorization on protected retrieval.

Perform keyboard and screen-reader checks through onboarding, persona edit, placement, friend voting, checkout approval and data export. Automated accessibility scans are necessary but cannot assess whether a 3D wardrobe is understandable without vision. Reduced motion must remove camera flights and parallax while preserving clear state changes. Test at 200% zoom and large text. No task requires color alone, precise dragging, hover or an unlabelled icon.

## 6. Operational gates and owner prerequisites

| Gate | What the builder can complete | What requires an actual external asset/access decision |
|---|---|---|
| Identity | Full adapter, test identity, session flows | Production OIDC tenant/providers/domains |
| Nordstrom | Publisher/link adapter, ingestion contracts, setup UI | Approved program access and permitted catalog/media rights |
| Agent checkout | Policy, protocol adapters and failure/reconciliation fixtures | Supported merchant/processor accounts and sandbox credentials |
| Photo try-on | Consent/job/deletion flow, provider adapter | Enabled provider/model/region and processing terms |
| Midnight | Contracts, local tests, wallet integration and network adapter | Approved Preprod resources; separate Mainnet deployment/custody decision |
| Reprint | Rights policy, quota/job flow and manufacturer adapter | Rights-holder licenses, production files, approved manufacturer |
| Email/push | Templates, preferences, suppression and test sink | Verified delivery domain/provider and actual opt-in recipients |
| Production media | Asset pipeline and original demo set | Cleared commercial garment imagery/models and brand permissions |

Continue implementation around missing credentials using honest fixtures and disabled capability states. Ask for a prerequisite only when its concrete setup/test is ready and it is the actual remaining blocker. Do not repeatedly ask the founder to reconfirm already specified product decisions.

Before production, require appropriate security/contract review, provider approvals, measured infrastructure budgets, backup/recovery evidence, key/prover custody policy, privacy/retention disclosures, content rights, incident ownership and a launch checklist. These are concrete release gates for the requested purchase/identity/rights application, not a reason to leave the consumer build unfinished.

## 7. Completion report format

Deliver: commit/PR, startup command, local or authorized preview URL, exact implemented journeys, screenshots/video, measured performance, executed test results, provider capability matrix, Midnight network evidence, deviations, missing external prerequisites and next operator actions. Include separate columns for **experience complete**, **integration verified** and **production approved**.

Do not write “95% ready” or “fully production ready” without defined evidence. Do not count a stubbed endpoint, static screen or fixture transaction as the corresponding live capability. The founder should be able to open the app, change who it thinks they are, create a look, place an item in a chosen room, ask a friend, earn a justified reward and understand their garment's evidence before reading an engineering status report.
