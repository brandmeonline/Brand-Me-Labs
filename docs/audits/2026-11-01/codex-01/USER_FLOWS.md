# User flows and visual evidence

The consumer UI on remote main is substantial, but its persistence and service connections are uneven. Guest onboarding saves a local draft; the spatial wardrobe is an IndexedDB demo; persona, social and rewards have mounted gateway/domain paths that require a separately running stack. Production browser sign-in, spatial account storage, commerce mounting and full account deletion remain incomplete.

This audit did **not** execute the application. Docker's selected engine was unavailable; the WSL probe found Python/unshare but no Node or sandbox helper, and an adequate isolated runtime was not established. No existing host application environment or production credentials were reused. Static parsing is not a runtime test. The [runtime preflight](evidence/runtime-preflight.txt) and [static checks](evidence/static-checks.json) record the exact distinction.

Baseline for every row below: `ed19dc151d103b108cf972e6d37971c55d5dcf60`. Original local checkout `0f5f58a9eecaca46b367c9bd96f89654343fa5fb` is older and must not be described as containing these new flows. Deployment remains unknown.

## Walkthrough

- [Browsable visual walkthrough](visuals/index.html)
- [Intended user flow](visuals/intended-flow.png) and [diagram source](visuals/intended-flow.mmd)
- [Implemented system and disconnected paths](visuals/implemented-system.png)
- [Observed CI development storyboard](visuals/ci-storyboard.png) and [exact provenance/checks](CI_JOURNEY_EVIDENCE.md)
- [Committed UI baseline storyboard](visuals/storyboard.png)
- [Proposed sign-in and recovery surface](visuals/proposed-sign-in.png)
- [Image provenance manifest](visuals/screenshot-manifest.json)

**No image in this pack was captured by a fresh audit run.** Six OBSERVED SCREENSHOTS were retrieved from a successful October 30 CI development job, verified against the published artifact digest, and inspected. They use UI merge `d657103ee21674ef14d6182572a78d75d0241b29` and backend `dafd3b169da777ec3e3a7fc2c3f0cab573358e2b`; they do not verify the current main tree or a deployed service. The [CI evidence note](CI_JOURNEY_EVIDENCE.md) distinguishes verified checks from API-seeded setup and custom development service/event composition. It does not establish canonical worker deployment.

 Original UI baseline images were read from the pinned Git tree and inspected for content. Catalog and My Data baselines were produced by a repository harness that intercepts HTTP with explicit test doubles. Their storage revision is known; original capture time and actual running application SHA are not independently known. The storyboard labels them as committed baselines. It cannot establish successful current transitions or deployed behavior.

## Journeys

Each journey below separates the intended effect from source-observed behavior. All complete trace fields, actor/preconditions, checks, blockers and evidence are also available in [journeys.json](evidence/journeys.json).

### J-001 — Explore → four-step editable style onboarding → first useful direction without wallet/camera/contact import

**Actor:** Guest; modern browser with local storage.

**Current code:** /start implements intent, fictional look selection, room choice, three adjustable axes and save. Landing CTA leads to /today; onboarding is a separate route.

**Trace:** Home /today link → /start Onboarding → localStorage guest draft → fictional 2D study → optional account migration.

**Persistence/effect:** Device localStorage only until explicit migration; no retailer or chain effect.

**Alternatives and checks:** Skip/back exist; storage errors keep in-tab state with warning. Reload and unknown preferences traced, not exercised.

**Blockers:** No additional static blocker identified for the narrow device-only path; execution unverified.

Evidence: [brandme-frontend/app/page.tsx:25](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/app/page.tsx#L25); [brandme-frontend/features/persona/onboarding.tsx:44](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/persona/onboarding.tsx#L44).

### J-002 — Provider login/recovery → secure browser session → reauthentication for sensitive changes

**Actor:** New or returning real member in sandbox/production.

**Current code:** Browser account page offers only fictional development sign-in. Strict build displays sign-in unavailable. Gateway verifies bearer tokens but has no production browser session creation/callback in its mounted routes.

**Trace:** /me/connections → Connections → /session/dev only; strict mode refuses it. Browser proxy forwards bm_session, not bearer Authorization; command() requires /session..

**Persistence/effect:** No complete browser production account journey demonstrated. OIDC bearer validation is a separate API capability.

**Alternatives and checks:** Missing/expired sessions yield errors. Password recovery and callback UI confirmed absent from inspected app route inventory; external IdP recovery remains unverified.

**Blockers:** F-UX-003.

Evidence: [brandme-frontend/app/me/connections/page.tsx:4](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/app/me/connections/page.tsx#L4); [brandme-frontend/features/privacy/connections.tsx:13](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/privacy/connections.tsx#L13); [brandme-gateway/src/routes/v1/index.ts:85](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/routes/v1/index.ts#L85); [brandme-gateway/src/middleware/session.ts:66](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/middleware/session.ts#L66); [brandme-frontend/lib/server/gateway-proxy.ts:100](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/lib/server/gateway-proxy.ts#L100).

### J-003 — Sign in → migrate guest choices once → refresh/relogin with durable saved persona

**Actor:** Synthetic development member; gateway, migrated Spanner and consumer API configured.

**Current code:** Development session route resolves member and creates session. Guest migration preserves request and key before sending; only clears local draft after response.

**Trace:** Connections → command(/session/dev) → gateway IdentityStore → Spanner session → command(/me/guest-migration) → signed domain client → GuestMigrationService.

**Persistence/effect:** Server persistence code exists; dev identity is explicitly simulated, not verified real identity.

**Alternatives and checks:** Stable idempotency key on timeout; account-change guard and no automatic write retries. Consumer CI uses separately pinned domain source, so it is not an all-main test.

**Blockers:** Runtime assembly and emulator unavailable for audit execution.

Evidence: [brandme-frontend/features/persona/onboarding.tsx:24](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/persona/onboarding.tsx#L24); [brandme-gateway/src/routes/v1/index.ts:94](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/routes/v1/index.ts#L94); [brandme-gateway/src/services/domains.ts:37](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/services/domains.ts#L37); [brandme_core/domains/persona/app.py:70](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/persona/app.py#L70).

### J-004 — Inspect/edit/lock/reset style axes → preview recommendations → save with conflict handling

**Actor:** Signed-in member; consumer domain API available.

**Current code:** Looking Glass uses server persona and If-Match updates. Recommendation service exists but production composition supplies no catalog/wardrobe candidates, so connected ranking output is missing.

**Trace:** /me/style → LookingGlass → same-origin proxy → personaRouter → signed principal → PersonaService → Spanner → visible saved revision.

**Persistence/effect:** Persona updates persist server-side if assembled; preview is not a retail transaction.

**Alternatives and checks:** Version conflicts require reload; preview requests carry revision; reset controls present. /me still falsely says guest (F-UX-001).

**Blockers:** F-ARCH-003.

Evidence: [brandme-frontend/features/persona/looking-glass.tsx:15](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/persona/looking-glass.tsx#L15); [brandme-frontend/features/persona/looking-glass.tsx:70](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/persona/looking-glass.tsx#L70); [brandme_core/domains/persona/api.py:40](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/persona/api.py#L40); [brandme_core/domains/persona/app.py:69](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/persona/app.py#L69).

### J-005 — Place owned/wanted pieces in chosen room → accessible list → persist across devices

**Actor:** Guest/demo; IndexedDB and optional WebGL.

**Current code:** Guest closet has transactional IndexedDB, placement conflicts and cross-tab notifications. Sandbox/production route is explicitly blocked. No authenticated repository is injected.

**Trace:** /closet → SpatialModeGate → ClosetPage/useCloset → createGuestClosetRepository → IndexedDB → room/list.

**Persistence/effect:** Persists on this browser/device; does not prove ownership or cross-device sync.

**Alternatives and checks:** Storage failure, optimistic-version conflict, duplicate operation and subscribe cleanup reviewed; WebGL/device recovery not run.

**Blockers:** F-ARCH-006.

Evidence: [brandme-frontend/app/closet/page.tsx:5](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/app/closet/page.tsx#L5); [brandme-frontend/features/closet/SpatialModeGate.tsx:12](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/closet/SpatialModeGate.tsx#L12); [brandme-frontend/features/closet/useCloset.ts:10](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/closet/useCloset.ts#L10); [brandme-frontend/features/closet/repository.ts:265](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/closet/repository.ts#L265).

### J-006 — Add self-reported item → see it in Today and spatial closet → update/archive consistently

**Actor:** Member or guest adding a garment.

**Current code:** Mounted server wardrobe intake and separate guest AddItem/closet stores both exist. UI spatial IDs and IndexedDB state are not connected to the server wardrobe returned by Today.

**Trace:** Guest /add → guest repository; separate API POST /wardrobe/items → wardrobeRouter → WardrobeService/Spanner → TodayData GET /wardrobe/items.

**Persistence/effect:** Two distinct persistence systems, with self-reported vs fictional claim labels.

**Alternatives and checks:** Intake validation and claim labels traced; no fresh browser/API cross-device test. A test seeding via API is not the Add-item UI journey.

**Blockers:** F-ARCH-006.

Evidence: [brandme-frontend/features/closet/AddItemPage.tsx:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/closet/AddItemPage.tsx#L1); [brandme-frontend/features/closet/repository.ts:145](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/closet/repository.ts#L145); [brandme_core/domains/wardrobe/api.py:48](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/wardrobe/api.py#L48); [brandme-frontend/features/persona/today.tsx:10](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/persona/today.tsx#L10).

### J-007 — Ask selected friends for five minutes → yes/pass/alternative → server closes → access revocation

**Actor:** Two signed-in members; accepted relationship and server wardrobe item

**Current code:** Consumer UI, gateway mounts and social service handlers exist. Uses member references for requests; server-backed wardrobe is prerequisite. Deadline and access are periodically refreshed.

**Trace:** /circle → /relationships; /circle/decisions/new → /decisions → signed principal → DecisionService/Spanner → visible server state

**Persistence/effect:** Server records and internal notifications; page explicitly sends no external notifications.

**Alternatives and checks:** Blind-until-response, no-replies, close early, block/revocation and server deadline paths traced; no participant notification delivery observed.

**Blockers:** End-to-end deployment unverified; guest items do not seed server wardrobe; F-ARCH-002: consumer scheduler/ingress composition missing; UI refresh is not durable deadline closure or reward settlement.

Evidence: [brandme-frontend/features/social/circle.tsx:32](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/social/circle.tsx#L32); [brandme-frontend/features/social/circle.tsx:48](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/social/circle.tsx#L48); [brandme_core/domains/social/api.py:83](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/social/api.py#L83); [brandme-gateway/src/routes/v1/index.ts:143](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/routes/v1/index.ts#L143).

### J-008 — Earn auditable participation rewards → reserve benefit → fulfill or reverse

**Actor:** Signed-in member with reward events and available benefit

**Current code:** Rewards summary and reservation UI call mounted domain endpoints. UI distinguishes reserved from fulfilled. Earning/scheduler/provider fulfillment are separate operational dependencies.

**Trace:** /rewards → /rewards,/benefits → review dialog → idempotent reservation command → RewardsService/BenefitService → Spanner → status

**Persistence/effect:** Points/reservations code; no evidence of partner fulfillment or real monetary value.

**Alternatives and checks:** Reservation unknown-outcome retains key; mocked browser harness tests repeat and focus recovery; not executed here.

**Blockers:** Worker and fulfillment deployment unverified; F-ARCH-002: consumer scheduler/ingress composition missing; UI refresh is not durable deadline closure or reward settlement.

Evidence: [brandme-frontend/features/rewards/rewards.tsx:44](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/rewards/rewards.tsx#L44); [brandme_core/domains/rewards/api.py:35](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/domains/rewards/api.py#L35); [brandme-gateway/src/routes/v1/index.ts:143](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/routes/v1/index.ts#L143).

### J-009 — Discover → live catalog variants → save/try/quote

**Actor:** Member searching an authorized provider.

**Current code:** Discover sends /catalog/search and renders explicit provider observations. Catalog/provider routers are not mounted in main; ProductDetail has no save/try/checkout action.

**Trace:** /discover → /api/v1/catalog/search → proxy → gateway catch-all 404; standalone router/adapters are unreachable from this mount.

**Persistence/effect:** Visible test catalog screenshots are HTTP test doubles, not live retailer results.

**Alternatives and checks:** UI handles provider unavailable and untrusted text; search success baselines are mocked.

**Blockers:** F-ARCH-001.

Evidence: [brandme-frontend/features/commerce/catalog.tsx:55](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/commerce/catalog.tsx#L55); [brandme-frontend/features/commerce/catalog.tsx:179](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/commerce/catalog.tsx#L179); [brandme-gateway/src/routes/v1/index.ts:131](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/routes/v1/index.ts#L131).

### J-010 — Quote → trusted approval → authorized order → reconcile/cancel/refund

**Actor:** Member approves exact variant and bounded spend.

**Current code:** /orders is an unavailable-state page; commerce domain and provider safety code exist but the public router/application composition is disconnected.

**Trace:** /orders → AvailabilityState; proposed path would use commerce gateway → domain → provider → webhook/reconcile → order view.

**Persistence/effect:** No actual purchase, payment or refund performed or verified.

**Alternatives and checks:** Idempotency/approval logic reviewed by security reviewer; sandbox provider receipts and timeout reconciliation remain unverified.

**Blockers:** F-ARCH-001.

Evidence: [brandme-frontend/app/orders/page.tsx:4](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/app/orders/page.tsx#L4); [brandme-gateway/src/routes/v1/commerce.ts:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/routes/v1/commerce.ts#L1).

### J-011 — Ask assistant → review plan/grant → execute within scope → cancel/revoke

**Actor:** Member grants bounded assistant permission.

**Current code:** /assistant is an unavailable-state page; standalone assistant/delegation router work is not mounted.

**Trace:** /assistant → AvailabilityState; no reachable consumer task creation journey on main.

**Persistence/effect:** No agent authority or external action created in audit.

**Alternatives and checks:** Tool permission, injection and cancellation analysis belongs to security evidence; no autonomous task was launched.

**Blockers:** F-ARCH-001.

Evidence: [brandme-frontend/app/assistant/page.tsx:4](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/app/assistant/page.tsx#L4); [brandme-gateway/src/routes/v1/assistant.ts:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/routes/v1/assistant.ts#L1); [brandme-gateway/src/routes/v1/index.ts:131](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/routes/v1/index.ts#L131).

### J-012 — Inspect all personal data → export selected categories with integrity verification

**Actor:** Member with recent authentication; rights read/export services configured.

**Current code:** UI honestly shows partial rights inventory. Export job/service supports selected rights categories, hash verification and account-change discard; not a full account export.

**Trace:** /me/data → gateway privacy routes → read_api rights catalog; export command → privacy_exports service/worker/store → verified JSON download.

**Persistence/effect:** Server job and private artifact code exists; resource/worker/access configuration not observed.

**Alternatives and checks:** Hash mismatch, account switch and partial scope handled; browser screenshots come from mocked harness, not exported private data.

**Blockers:** F-ARCH-004; F-UX-003.

Evidence: [brandme-frontend/features/privacy/my-data.tsx:80](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/privacy/my-data.tsx#L80); [brandme-frontend/lib/client/gateway.ts:36](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/lib/client/gateway.ts#L36); [brandme_core/read_api/reads.py:180](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/read_api/reads.py#L180); [brandme_core/privacy_exports/service.py:71](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/privacy_exports/service.py#L71).

### J-013 — Freeze processing → delete permitted data → show retained exceptions and receipt

**Actor:** Member requesting correction/removal.

**Current code:** Main My Data cannot initiate deletion and read service returns commands unavailable; it can display an existing deletion receipt. Full consumer/privacy handlers are not composed into this entry point.

**Trace:** /me/data → inventory says deletion unavailable; /me/data/deletion/[id] → read-only receipt.

**Persistence/effect:** No erasure requested; public ledger exceptions and full account completion not verified.

**Alternatives and checks:** Retained/exception states displayed. Proposed new branch composition must be integrated and tested, not counted as main behavior.

**Blockers:** F-ARCH-004.

Evidence: [brandme-frontend/features/privacy/my-data.tsx:211](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/privacy/my-data.tsx#L211); [brandme_core/read_api/app.py:122](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/read_api/app.py#L122); [brandme_core/read_api/reads.py:180](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/read_api/reads.py#L180).

### J-014 — Preview garment with honest fidelity → deny/revoke camera → discard media

**Actor:** Guest with camera permission or optional photo provider.

**Current code:** Spatial preview, overlay and photo-service code exists; guest storage and explicit consent are used. Fit/provenance labels are distinct. No audit camera/device/provider execution.

**Trace:** /try/[itemId] → TryPage → model/overlay/photo branch → cameraSession or photo route → optional provider → local preview-media/closet link.

**Persistence/effect:** Local camera/IndexedDB and optional external photo transmission when configured and consented; not proof of fit or ownership.

**Alternatives and checks:** Permission denial/revocation, reduced motion and cleanup have source/test paths; physically calibrated fit and real mobile AR remain untested.

**Blockers:** Authenticated spatial connection missing; provider and devices unverified.

Evidence: [brandme-frontend/features/spatial/TryPage.tsx:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/spatial/TryPage.tsx#L1); [brandme-frontend/features/spatial/PhotoPreview.tsx:118](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/spatial/PhotoPreview.tsx#L118); [brandme-frontend/features/spatial/photoMedia.ts:3](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/spatial/photoMedia.ts#L3); [brandme-frontend/features/spatial/previewMedia.ts:10](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/spatial/previewMedia.ts#L10).

### J-015 — Authenticate authority → real chain submission → reconcile/projection → visible proof/failure

**Actor:** Member/operator requesting digital ownership/lifecycle action

**Current code:** Gateway mounts rights reads/exports and chain reconciliation. The chain server is read-only; ownership challenge creation reaches a read-service mutation boundary returning 503. Client-owned wallet proof/submission is not a mounted server signer. Legacy scan/governance screens remain simulations.

**Trace:** Gateway /rights reads and /chain reconciliation → configured read/chain service → Spanner projections when configured. Ownership challenge POST → read API mutation boundary → 503. Member wallet submission is a separate unverified connection.

**Persistence/effect:** No wallet signature or chain write was performed; deployed version/contract and network remain unknown.

**Alternatives and checks:** Idempotency/reconciliation/reorg/recovery reviewed statically by security reviewer; full failure recovery not executed.

**Blockers:** F-BR-002: rights command service/route guard incomplete on PR #70; main mutation endpoint unavailable; F-UX-003: production browser identity incomplete; Cloud/network/contract/worker deployment unobserved.

Evidence: [brandme-gateway/src/routes/v1/index.ts:131](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/routes/v1/index.ts#L131); [brandme-frontend/components/shell/app-shell.tsx:215](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/components/shell/app-shell.tsx#L215); [brandme-chain/src/midnight/adapter.ts:1](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-chain/src/midnight/adapter.ts#L1); [brandme-chain/src/index.ts:35](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-chain/src/index.ts#L35); [brandme-gateway/src/routes/v1/ownership.ts:36](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/routes/v1/ownership.ts#L36); [brandme_core/read_api/app.py:122](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme_core/read_api/app.py#L122).

### J-016 — Sign out → revoke session → clear opted-in guest data

**Actor:** Signed-in development member on shared browser.

**Current code:** Server session revocation exists, and UI invalidates account resources. Clear guest data checkbox only removes two onboarding localStorage keys; closet, outfits and saved preview-media IndexedDB remain.

**Trace:** Connections signout → DELETE /session → IdentityStore.revokeSession → clearGuest → accountChanged → UI refresh.

**Persistence/effect:** Session invalidation code + partial device cleanup; privacy expectation gap for retained guest photos/items.

**Alternatives and checks:** Logout failure does not clear state; shared-browser cleanup and re-login not executed in audit.

**Blockers:** F-UX-002.

Evidence: [brandme-frontend/features/privacy/connections.tsx:19](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/privacy/connections.tsx#L19); [brandme-frontend/features/persona/onboarding.tsx:37](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/persona/onboarding.tsx#L37); [brandme-gateway/src/routes/v1/index.ts:120](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/routes/v1/index.ts#L120); [brandme-frontend/features/spatial/previewMedia.ts:10](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/features/spatial/previewMedia.ts#L10).

### J-017 — Review moderation/reward disputes or provider status → authorized correction → audit record and visible result

**Actor:** Authorized moderator/provider operator with separately configured console identity

**Current code:** Console surfaces and gateway clients exist. Moderation requests /api/v1/ops, which main gateway does not mount; no working operator correction path established. Provider administration uses a separate bearer-only client.

**Trace:** Console moderation/reward pages → opsFetch (cookie or bearer; BRANDME_GATEWAY_INTERNAL_URL) → /api/v1/ops → absent gateway mount. Provider console → bearer-only client (BRANDME_GATEWAY_URL) → provider/commerce route not mounted.

**Persistence/effect:** No operator write or external provider operation was executed. Real audit trail/role enforcement cannot be established through an unreachable path.

**Alternatives and checks:** Missing/expired operator token, non-admin access, duplicate correction and audit-log failure require runtime role/tenant tests after mounting.

**Blockers:** CAP-017: ops domain/router composition absent; F-ARCH-001: provider/commerce routes unmounted.

Evidence: [brandme-console/app/(ops)/moderation/_lib/ops-gateway.ts:31](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-console/app/(ops)/moderation/_lib/ops-gateway.ts#L31); [brandme-console/app/(ops)/providers/_data/gateway.ts:51](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-console/app/(ops)/providers/_data/gateway.ts#L51); [brandme-gateway/src/routes/v1/index.ts:131](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-gateway/src/routes/v1/index.ts#L131).

## Accessibility and device coverage

Static evidence includes a skip link, landmark labels, focus on route changes, keyboard-capable Radix sheets, online/offline messaging, named sliders, resource error/retry states, theme/contrast controls, reduced-motion preference handling and an accessible simple-view option. See [app shell](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/components/shell/app-shell.tsx#L68), [preferences](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/lib/client/experience-preferences.tsx), and [UI test harness](https://github.com/brandmeonline/Brand-Me-Labs/blob/ed19dc151d103b108cf972e6d37971c55d5dcf60/brandme-frontend/lib/testing/verify-domain-views.mjs).

The harness declares desktop/mobile, light/dark, axe and overflow checks, but this audit did not run keyboard navigation, screen-reader testing, mobile Safari, camera permissions, WebXR/Quick Look, hardware fit calibration, reconnection or contrast measurements. Reviewed screenshots provide visual examples only. No accessibility conformance or real-device performance claim is made.

## Test evidence boundaries

`verify-domain-views.mjs` uses intercepted HTTP test doubles. `verify-live-domains.mjs` is designed to exercise real development HTTP and Spanner, but `.github/workflows/consumer-ui.yml` checks out domain source at `dafd3b169da777ec3e3a7fc2c3f0cab573358e2b` separately from the UI revision. Its successful result, if present, applies to that combination. It also creates the server wardrobe item through its HTTP helper, so it does not prove the UI's guest Add-item path persists to the server. Current check results and failed browser lanes belong in [SECURITY_RELIABILITY.md](SECURITY_RELIABILITY.md), tied to their tested SHAs.

The smallest useful next milestone is two synthetic members completing onboarding, persisted persona/wardrobe, a five-minute friend decision and returning use through one canonical stack. Reuse existing logic; connect the spatial repository and recommendation sources. Provider payments and chain writes are separate later acceptance gates.
