# 07 — Repository evidence, historical reconciliation and sources

## 1. Scope and limits of this review

This specification was prepared on 2026-10-05 against `brandmeonline/Brand-Me-Labs` commit `0f5f58a9eecaca46b367c9bd96f89654343fa5fb` (2026-04-26, “Add MCP commerce mandate and cart tool handlers (#28)”). The repository was cloned and inspected, including root instructions, application manifests, frontend components, domain/data code, chain clients, MCP handlers, schemas, infrastructure and relevant tests. No application test suite or live provider/chain transaction was executed as part of writing this specification. Implementation status below is static code evidence, not a new runtime certification.

The separate `brandmeonline/Brand-Me-Codex` repository was also inspected. It is a minimal alternate developer-testing repository. Labs contains the substantial service implementation and is the destination for this package.

The product synthesis also draws on the founder's current instructions and the previously reviewed Brand.Me archive: early personality-engine concepts, self-adjustable identity controls, social purchasing decisions, points, brand participation, wardrobe organization and later trust/ownership work. This public repository package records product requirements and engineering decisions. It does not reproduce private source documents, personal information, private folder links or commercial credentials.

No applicable `AGENTS.md` was found in the inspected repositories at this baseline. Root `CLAUDE.md` and the repository's review workflow remain relevant. The repository-local UI/UX Pro Max skill was read and its design-system/Next.js guidance consulted. Its generic suggestions were adapted to the founder's tactile fashion and social experience rather than treated as a replacement brief.

## 2. What the archive changes about the product

| Topic | What the underlying product history emphasizes | Consequence for this build |
|---|---|---|
| Personality | A persistent engine combining explicit choices and behavioral signals; “who I am” and “who I want to be” | Editable declarations, visible inference, meaningful recommendations and user-controlled learning are central |
| Social experience | Trusted friends help one another choose and style in the moment | Five-minute decisions, outfit proposals, selected audiences and useful responses are first-class journeys |
| Loyalty | Members contribute feedback, referrals, corrections and research value | Versioned rewards, badges and benefits recognize contribution with auditable evidence |
| Wardrobe | Owned and wanted items, outfits, care and travel context | A practical persistent closet with a spatial expression, not only an asset explorer |
| Brand relationship | Personal relevance, discovery, emotional experience and participation | Authorized editorial/catalog ingestion, creator attribution and explicitly permissioned research |
| Physical/digital continuity | Apparel connects discovery, purchase, identity and continuing product history | Provenance, ownership transfer, care and licensed reprint support the consumer loop |
| Data economics | Older market-research ideas coexist with a desire for personal agency | The founder's current instruction resolves the tension in favor of inspectable, editable, exportable user data and explicit consent |

The central difference from a narrow passport/resale implementation is the order of value: a member comes to express themselves and interact with people; trust infrastructure makes the resulting objects and relationships more durable. This does not remove blockchain. It gives the blockchain an actual experience to support.

“Perfect you” is implemented as self-directed expression. It is not a body-ranking score, a diagnosis, or a system that dictates a single ideal identity. This interpretation follows the founder's request for editable backend preferences and the historical self-tuning persona controls.

## 3. Code findings at the audited baseline

Paths below are repository-relative and refer to the baseline, not guaranteed future line locations.

| Finding | Evidence | Implementation consequence |
|---|---|---|
| Consumer frontend is a small placeholder surface | `brandme-frontend/package.json`, `app`, `components/GarmentCard.tsx`, `lib/demoData.ts`; garment card renders an image placeholder | Build real product routes, media, persistence and states; do not treat current screens as finished UX |
| Frontend uses older dependency stack and is outside root workspace | Next 14.0.4/React 18.2 in frontend manifest; workspace lists gateway, chain and console | Add canonical frontend to workspace and perform controlled compatible upgrade |
| Console is a separate existing application | `brandme-console` manifest/app | Preserve operator/member boundary |
| Brain contains an actual Spanner lookup and service calls | `brandme-core/brain/main.py` | Reuse service structure; verify it at runtime rather than rewrite blindly |
| Policy/consent/provenance code is substantive | `brandme-core/policy`, `brandme_core/spanner/consent_graph.py` | Extend and test policy as a shared boundary |
| Orchestrator transfer response fabricates chain success | `brandme-core/orchestrator/main.py`, transfer handler, fake `cardano_tx_` construction around line 99 | Replace with durable operation state and actual chain observations |
| Midnight client is a full mock implementation | `brandme-chain/src/services/midnight-client.ts`: example endpoint, synthetic encryption/proof/transaction/confirmation behavior | Real SDK/provider integration is required; fake adapter isolated to demo |
| Real Cardano builder code is commented out | `brandme-chain/src/services/cardano-tx-builder.ts`, approximately lines 77–155 | No claim of working Cardano settlement until actual integration evidence |
| Python ownership proof implementation is not a real ZK proof system | `brandme_core/zk/proof_of_ownership.py` hash/JSON logic and stub configuration | Use actual cryptographic contract/proof verification for trust claims |
| MCP commerce handlers now exist, contrary to older plan text | `brandme_core/mcp/tools.py`: manifest additions, handler map, handlers around lines 799–923 | Audit current handlers; do not repeat “no ACP/AP2 code exists” |
| Those commerce handlers return synthetic IDs/statuses | Same MCP file: intent/cart/payment mandate UUIDs; checkout completion without merchant/payment execution | Preserve only useful interface concepts; replace or version/deprecate misleading protocol names |
| MCP principal binding requires attention | Executor uses supplied `user_id` parameter around line 586 | Bind to verified authenticated principal/delegation; never trust tool arguments as identity |
| Cube service contains actual Spanner access and policy filtering | `brandme-cube/src/service.py`, database lookup and molecular/lineage paths | Do not describe it as a PostgreSQL-only service; verify initialization and field filtering |
| Cube is seven logical facets | `brandme-cube/src/models.py` includes molecular data with six earlier facets | Preserve all seven facets independent of six-sided visual metaphor |
| Cube tests are insufficient/stale | `brandme-cube/tests/test_api.py` placeholder; service test assumptions differ from constructor/facet count | Replace with behavior tests; do not infer completeness from filenames |
| Ownership/reprint defaults risk overstating rights | `brandme_core/firestore/wardrobe.py` includes default reprint eligibility; cube top-level owner fields need filtered DTO | Derive capabilities from verified rights; protect top-level and nested identity fields |
| Gateway auth is incomplete for target remote-agent model | `brandme-gateway/src/middleware/auth.ts`: shared-secret JWT verification, limited checks and raw user logging | Implement proper issuer/audience/algorithm/key/session controls and redaction |
| Scan polling returns a placeholder processing state | `brandme-gateway/src/routes/scan.ts`, GET status handler | Persist scan operation and return real state |
| Spanner and legacy SQL coexist | `brandme-data/spanner/schema.sql`, `brandme-data/schemas/*.sql` | Establish GoogleSQL migration authority; do not mix dialects |
| Schema/code drift needs migration verification | Ownership current/active column references and ZK cache device field references differ across schema/code | Reconcile actual columns and queries under executable integration tests |
| Existing idempotency helper is useful but insufficiently scoped for target commerce | `brandme_core/spanner/idempotent.py` and `MutationLog` | Canonical request digests, principal/environment scoping and remote reconciliation required |
| Alternate gateway files remain | `brandme_gateway` and `brandme-gateway` | Recheck imports/references before deleting; older safe-delete prose is not enough |
| Documentation overstates readiness in places | Root README/status summaries versus executable paths and root `CLAUDE.md` cautions | Use an evidence matrix instead of percentage-ready claims |

The old root `CLAUDE.md` is valuable because it warns about stubs, but some details are stale: chain client code exists as stubs, commerce handler references exist, and the orphan directory description needs rechecking. The new package does not promote any of those implementations to production readiness.

## 4. Decision record

| ID | Decision | Rationale and tradeoff |
|---|---|---|
| ADR-01 | Consumer identity/social/closet loop is the organizing product | Restores founder intent; increases UI/domain scope beyond a trust demo |
| ADR-02 | Labs is canonical implementation repository | Contains existing services and data investment |
| ADR-03 | Existing frontend upgraded in place, admin console separate | Avoids disconnected prototypes and mixed permissions |
| ADR-04 | Spanner authoritative, Firestore projection | Reuses code and gives explicit consistency; requires disciplined migrations and cost monitoring |
| ADR-05 | Modular domain services before additional microservices | Reduces operational overhead while retaining trust boundaries |
| ADR-06 | Cloud Run plus durable task/event adapters as initial cloud target | Fits stateless APIs; prover/stateful needs stay separate; existing GKE remains an option |
| ADR-07 | Deterministic persona ranking plus optional model assistance | Fast, explainable and usable without AI credentials; sophisticated recommendations can evolve |
| ADR-08 | React 19/R3F v9 stable and progressive 3D | Compatible visual stack; must resolve exact current packages and test devices |
| ADR-09 | Separate 3D, room AR, live overlay, generated try-on and fit | Makes capability and fidelity honest instead of one misleading AR promise |
| ADR-10 | Midnight is the required private rights network | Matches current brief; Cardano public anchors remain optional and independently evidenced |
| ADR-11 | Local/user-controlled proving default where supported | Protects witness privacy; mobile completion may need compatible wallet/companion |
| ADR-12 | Product, instance, wardrobe record and license are distinct | Prevents catalog saves becoming fabricated ownership or reprint rights |
| ADR-13 | Current provider contracts determine checkout capability | Nordstrom publisher access and merchant checkout are different permissions |
| ADR-14 | Human-present purchase approval first; bounded autonomous mode gated | Delivers agent assistance while preventing free-form model authority over funds |
| ADR-15 | AP2 adapter follows current v0.2 schemas | Avoids implementing stale three-mandate design as current compatibility |
| ADR-16 | No on-chain personal profile/body/social plaintext | Preserves editability and limits irreversible disclosure |
| ADR-17 | Points are auditable application rewards | Supports loyalty without forcing a speculative token or wallet |
| ADR-18 | Realism comes from quality assets and measured motion | A cube placeholder is insufficient for the requested fashion experience |

An implementation may propose a better choice with evidence, but it must preserve the product invariants and record the migration impact. “The agent preferred another stack” is not sufficient justification for abandoning functioning repository code.

## 5. Primary-source catalog

All sources below were consulted on 2026-10-05. They establish external capabilities or standards; most numeric UX, reward, performance and retention values in the specification are original proposed defaults. Reverify versioned services, authentication, provider contracts and network endpoints at implementation time. Source pages do not grant access or media rights.

### S01 — Midnight release overview

[Official release overview](https://docs.midnight.network/relnotes/overview). Establishes the current release families and ledger context. The application must pin the supported tuple rather than repeat the older repo claim that the SDK is unavailable.

### S02 — Midnight compatibility matrix

[Official compatibility matrix](https://docs.midnight.network/relnotes/support-matrix). Source for the dated version table in chapter 04. Version compatibility must be verified as a group; these numbers are not permanent “latest” labels.

### S03 — Midnight environments and endpoints

[Official network endpoints](https://docs.midnight.network/relnotes/network). Source for the Mainnet provider transition and network-specific endpoints. Provider authentication and access must be configured independently.

### S04 — Midnight deployment and provider boundaries

[Deploy and operate](https://docs.midnight.network/guides/deploy-and-operate). Informs the six provider boundaries, private-state handling and prover trust discussion. The recovery, user experience and authorization requirements in this package are Brand.Me implementation requirements.

### S05 — Midnight network/environment selection

[Networks and environments](https://docs.midnight.network/guides/networks-and-environments). Network-aware wallet/provider configuration. Never treat test-network observations as Mainnet evidence.

### S06 — Midnight.js API

[Midnight.js reference](https://docs.midnight.network/api-reference/midnight-js). Verify actual provider and client APIs before implementation; no pseudocode in this package replaces compiling against the selected SDK.

### S07 — Claude Opus 5.5

[Official Opus 5.5 documentation](https://platform.claude.com/docs/en/models/opus-5-5/whats-new-opus-5-5). The requested model is documented with model ID `claude-opus-5-5`. Actual account/tool availability still applies. The kickoff prompt is model-compatible prose, not a guarantee of a one-response production application.

### S08 — React Three Fiber

[Official introduction](https://r3f.docs.pmnd.rs/getting-started/introduction). Stable v9 pairs with React 19. Do not select the v10 alpha documentation path by accident.

### S09 — glTF and texture portability

[Khronos glTF](https://www.khronos.org/gltf/), [KTX](https://www.khronos.org/ktx/), and [KHR_texture_basisu](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Khronos/KHR_texture_basisu/README.md). Standards basis for portable runtime assets and compressed textures; actual loader and device support must be tested.

### S10 — R3F performance

[Scaling performance](https://r3f.docs.pmnd.rs/advanced/scaling-performance). Supports demand rendering, reuse and scene optimization. Brand.Me's specific payload/frame budgets are proposed acceptance targets, not measurements from this source.

### S11 — model-viewer AR

[Official AR examples](https://modelviewer.dev/examples/augmentedreality/). Documents WebXR, Scene Viewer and Quick Look paths and their differing capabilities. Brand.Me must test its own assets and native handoffs.

### S12 — MediaPipe Pose Landmarker

[Official web guide](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/web_js). Basis for browser landmark processing. Landmarks alone do not provide validated apparel fit or calibrated body measurements.

### S13 — Google photo try-on

[Official virtual try-on guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/generate-virtual-try-on-images). Documents the `virtual-try-on-001` candidate integration. Verify account, region, model availability, image requirements and processing terms. Generated imagery is a visual preview.

### S14 — Nordstrom official affiliate program

[Nordstrom program page](https://www.nordstrom.com/browse/affiliate-program). Official publisher route points to Impact; creator participation is a separate route. This review did not verify a public unrestricted Nordstrom checkout API.

### S15 — Impact partner integration

[Partner API reference](https://integrations.impact.com/partner-api-reference) and [official catalog guidance](https://help.impact.com/brand/what-would-you-like-to-learn-about/platform-features/product-catalogs/add-product-catalogs-as-a-brand). Use current approved-account documentation for exact endpoints and permissions. A general partner API does not prove a specific merchant has enabled a catalog for Brand.Me.

### S16 — Shopify agent commerce/UCP

[Carts and checkout](https://shopify.dev/docs/agents/carts-and-checkout), [profiles](https://shopify.dev/docs/agents/profiles), and [authentication](https://shopify.dev/docs/agents/get-started/authentication). Establishes current supported agent commerce surfaces and capability/authentication discovery.

### S17 — Agentic Commerce Protocol

[Architecture](https://www.agenticcommerce.dev/docs/concepts/architecture), [checkout reference](https://www.agenticcommerce.dev/docs/reference/checkout), and [payments](https://www.agenticcommerce.dev/docs/reference/payments). Use exact supported protocol schemas and merchant/payment integration, not success-shaped local handlers.

### S18 — AP2 v0.2

[Official specification](https://ap2-protocol.org/ap2/specification/). Source for current Checkout/Payment mandate structure and trusted-surface requirements. Follow the exact version and conformance guidance; older Intent/Cart/Payment documentation in this repo is historical.

### S19 — A2A

[Official specification](https://a2a-protocol.org/latest/specification/). Pin the selected stable version and verify discovery/task/authentication details against it. The old plan's endpoint/version claims are not independently guaranteed by this package.

### S20 — MCP authorization

[2026-07-28 authorization specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization). Basis for remote protected-resource access and audience-bound authorization. Application-level policy still decides which objects/actions a client may access.

### S21 — GS1 Digital Link

[GS1 overview](https://www.gs1.org/standards/gs1-digital-link) and [URI syntax 1.7.0](https://ref.gs1.org/standards/digital-link/uri-syntax/1.7.0/). Identifier/resolution interoperability is separate from proof of ownership or a reproduction license.

### S22 — EU Digital Product Passport context

[Regulation (EU) 2024/1781](https://eur-lex.europa.eu/eli/reg/2024/1781/oj/eng) and [European Commission DPP FAQ](https://single-market-economy.ec.europa.eu/single-market/digital-product-passport/explore-our-faqs_en). Product-specific applicable obligations require current assessment. This specification makes no blanket fashion deadline or compliance certification claim.

### S23 — Motion accessibility

[Motion's React accessibility guide](https://motion.dev/docs/react-accessibility). Supports respecting reduced-motion preferences. The exact Brand.Me animation choreography is an original design requirement.

### S24 — Next.js rendering boundaries

[Server and Client Components](https://nextjs.org/docs/app/getting-started/server-and-client-components). Supports server-rendered initial pages and focused interactive client islands. Resolve the latest supported patched release at build time.

### S25 — Spanner transactions

[Official transactions overview](https://docs.cloud.google.com/spanner/docs/transactions). Basis for transactional domain/outbox writes and retry-aware callbacks. Cross-provider effects still require application idempotency/reconciliation.

### S26 — Firestore rules

[Official security-rules conditions](https://firebase.google.com/docs/firestore/security/rules-conditions). Use rules for client access and separate IAM/application authorization for server access. Brand.Me projection field minimization is an additional requirement.

### S27 — NXP secure tags

[NTAG 424 DNA official product documentation](https://www.nxp.com/products/rfid-nfc/nfc-hf/ntag-for-tags-and-labels/ntag-424-dna-424-dna-tagtamper-advanced-security-and-privacy-for-trusted-iot-applications:NTAG424DNA). Source for the candidate secure-tag family. Exact provisioning, cryptographic verification and tamper assumptions require implementation against the relevant manufacturer documentation and issuer process.

## 6. What remains a design decision or external gate

The chosen visual system, persona axes beyond the two legacy fields, reward values, room dimensions, interaction timings, ranking weights, SLOs, retention defaults and initial operating topology are specific proposals made to turn the vision into an executable brief. They have not been usability-tested or measured in this repository.

Nordstrom program approval, commercial media/derivative rights, merchant checkout access, processor credentials, manufacturer contracts, reproduction licenses, identity-provider setup and production cloud resources are not established by a source URL. The implementation must expose their setup and capability status. Mainnet availability likewise does not certify Brand.Me's contracts, custody or deployment.

This package's validation checks documentation structure, machine contracts and consistency. It does not certify the future application's security, visual quality, protocol conformance, manufacturing feasibility or production readiness. Those require the concrete evidence described in chapter 06.
