# 01 — Product and experience

## 1. Product premise

The product promise is **Be More U**: understand your taste, shape how you express it, discover things that belong in your life, and involve the people whose judgment matters to you. Brand.Me should reward the work members contribute to this experience and preserve a useful history of the objects they choose.

The foundational loop is:

1. Express an intention or adjust a preference.
2. Receive a small, intelligible set of outfits or products.
3. See the items in a personal closet or on a chosen representation of yourself.
4. Ask friends for a decision or styling contribution.
5. Save, wear, purchase, share, repair, transfer, or commission an authorized reprint.
6. Receive relevant feedback and rewards. Decide what the system should learn.

The product must work for a person who buys nothing this month. Rediscovering an owned garment, assembling an outfit, helping a friend, and correcting an unwanted inference are successful outcomes.

### 1.1 Product roles

| Role | Primary job | Boundaries |
|---|---|---|
| Member | Express personal style; organize, discover, decide and own | Own profile and explicitly shared resources only |
| Friend/stylist | Give useful advice and assemble proposed outfits | Cannot purchase, edit identity, or publish for another member without a separate grant |
| Creator | Publish licensed digital/physical designs and styling collections | Must attest rights and fulfillment capability before selling |
| Brand/retailer | Supply catalog, product facts, verified claims and orders | Never receives a member's complete persona or private closet by default |
| Manufacturer/repairer/recycler | Accept a scoped job and issue physical-process evidence | Cannot self-award consumer reputation or alter original provenance |
| External agent | Execute a narrowly authorized task | Has explicit resource, purpose, time, action and spending limits |
| Operator | Handle support, disputes, provider setup and moderation | Audited, role-scoped access; no general plaintext access to private wallet state |

Launch the social/commerce service for adults as an explicit product default. The historic youth-market ideas do not authorize collecting children's data or enabling their autonomous purchases. Any younger-user version requires a separately designed experience.

### 1.2 Product language

Use **Me**, **My Closet**, **Style Me**, **Ask My Circle**, **My Data**, **History & Ownership**, **Rewards**, **Connections**, and **My Assistant**.

Show `Product Cube`, chain IDs, Compact, attestors, mandates, and proof formats inside advanced details or developer/operator surfaces. Consumer copy should say what the action means: “Prove this is yours without sharing your purchase price.”

Do not use “perfect” as a body judgment. The user determines the intended expression. Never score attractiveness, infer sensitive traits from a photograph, rank friends by appearance, or make body alteration the default.

## 2. Information architecture

The mobile primary navigation has five destinations: **Today**, **Closet**, **Style**, **Circle**, **Me**. A contextual capture button opens Add/Scan. Rewards, inbox, ownership and orders are reachable from Me and from their relevant objects. Desktop uses a left navigation rail and contextual right inspector.

| Route | Screen contract | Primary action | Essential alternate states |
|---|---|---|---|
| `/` | Short product introduction with a real explorable wardrobe preview | Explore my style | Reduced motion; no WebGL |
| `/start` | Progressive setup, resumable and skippable | Build my first look | Guest; interrupted; existing account |
| `/today` | One main personal recommendation plus timely circle requests and wardrobe reminders | See my look | Cold start; no new catalog; offline |
| `/me` | Personal identity overview, current context and edit entry | Shape my style | No inferred attributes |
| `/me/style` | Looking Glass sliders and explanation inspector | Apply changes | Locked values; conflict; reset |
| `/me/data` | Data sources, inferences, consent, export and deletion | Review what Brand.Me knows | Export pending; revoked integration |
| `/me/connections` | Provider/agent connections and granted scopes | Connect a service | Missing provider support; expired token |
| `/closet` | Spatial closet with equivalent grid/list | Add an item | Empty; degraded graphics; syncing |
| `/closet/settings` | Environment, light, layout, accessibility and sharing | Save my room | Theme download failed |
| `/closet/items/:itemId` | Member's item: outfits, status, care, purchase evidence | Style this | Wishlist; ordered; returned; transferred |
| `/add` | Photo, URL, catalog, receipt, QR/NFC and manual input | Add to my closet | Low confidence; duplicate; offline |
| `/style` | Intention entry and curated outfit composition | Create my look | Insufficient items; no AI provider |
| `/style/outfits/:outfitId` | Outfit canvas, item substitutions and explanations | Wear / save / ask | Missing variant; deleted item |
| `/discover` | Personal catalog with controlled filters and brand editorials | View product | Provider stale; region unavailable |
| `/products/:productId` | Catalog product, exact variants, sources and rights | Save / try / ask / shop | No 3D; no stock; missing price |
| `/try/:itemId` | Clearly separated 3D, room AR, live overlay and photo preview | Start selected mode | Camera denied; unsupported device |
| `/circle` | Pending decisions first, then outfits and people | Ask my circle | No friends; muted users |
| `/circle/decisions/new` | Five-minute decision composer | Send request | No eligible recipients; own request limit |
| `/circle/decisions/:decisionId` | Product/outfit, votes, countdown and comments | Yes / pass / suggest | Closed; blocked; unavailable product |
| `/people/:handle` | Public or shared profile and authorized closet collection | Follow / request friendship | Private; blocked; not found |
| `/collections/:collectionId` | Curated subset of items with separate visibility | Save collection | Revoked link; item privacy change |
| `/share/:shareId` | Sanitized, revocable shared snapshot | Open in Brand.Me | Expired; removed; anonymous viewer |
| `/rewards` | Points, earned badges, available benefits and transaction history | Use a benefit | Pending; reversed; unavailable sponsor |
| `/assistant` | Task workspace with constraints, proposals and run history | Ask for help | Disabled provider; approval needed |
| `/assistant/tasks/:taskId` | Deterministic task state, proposed action and receipts | Review proposal | Paused; expired; unknown purchase status |
| `/checkout/:checkoutId` | Trusted confirmation surface with exact totals | Confirm / continue at retailer | Price changed; step-up auth; expired |
| `/orders` | Per-merchant orders and fulfillment status | View order | Unverified receipt; refund pending |
| `/orders/:orderId` | Evidence, shipment, returns and ownership claim | Track / return / claim | Partial shipment; cancellation |
| `/ownership/:assetId` | Readable passport and entitled actions | Verify / transfer | Unclaimed; proof pending; disputed |
| `/ownership/:assetId/transfer` | Recipient, rights, private disclosure and approval | Prepare transfer | Recipient not enrolled; wallet rejected |
| `/ownership/:assetId/reprint` | Eligible design/license, manufacturer, material and quote | Request production | No license; no manufacturer; exhausted allowance |
| `/scan` | Physical product identification and evidence result | Scan tag | Plain barcode; copied tag; replay |
| `/inbox` | Transactional updates, decisions, requests and moderation notices | Open notification | No push permission; unread sync |
| `/settings` | Account, authentication, safety, accessibility and recovery | Save settings | Recovery incomplete |
| `/studio` | Creator product/collection publishing | Create a design | Rights review pending |
| `/studio/products/:id` | Media, variants, license, manufacturing and claims editor | Submit product | Asset QA failed; revision required |
| `/business` | Brand catalog health and consented aggregate intelligence | Review catalog | Low sample size; access denied |

Operator routes belong in `brandme-console`, not the member app: integrations, content moderation, reward disputes, claims, manufacturing jobs, connector health and deployment capabilities. Existing `/shop` redirects to `/discover`; `/stash` redirects to `/closet`. Preserve existing scan/proof URLs through explicit adapters.

## 3. Fast onboarding

### 3.1 Experience target

A first-time user should see a useful, editable look and a chosen closet in roughly 90 seconds, without a wallet. This is a design target to measure, not a performance claim. Avoid more than three mandatory decisions before the first reveal.

1. **Welcome:** “A wardrobe that feels like you.” Actions “Find my style” and “Explore first.” Explain in one sentence that preferences stay editable.
2. **Intention:** “What are you dressing for?” Choose Everyday, Work, Going out, An occasion, or enter an intention. Skip defaults to Everyday.
3. **Visual choice:** Show six distinct, licensed outfit compositions. Select up to three; “None of these” opens a neutral starting profile. Do not infer gender, ethnicity or body size from choices.
4. **Closet choice:** Preview three environments: Walnut Atelier, Limestone Gallery, and Garden Studio. A fourth control, Simple View, provides the same functionality in 2D. Choice is reversible and free.
5. **Reveal:** Display one outfit, three plain-language reasons, and three immediately adjustable style controls. “That feels like me” saves the seed; “Change it” keeps the user in control.
6. **First item:** Offer “Add something I own” with photo/manual/catalog paths. This is optional. Explain when a seed garment is a fictional demo object.
7. **Save account:** Offer email/OIDC/passkey-compatible authentication at the moment the user wants persistence or sharing. Do not require a seed phrase.
8. **Optional next step:** Ask a friend, organize a capsule, or connect a retailer. Offer one action chosen from the user's context.

Guest data stays in a local namespace with a visible “Saved on this device” status. Signing up atomically migrates the guest profile, closet theme, saved products and outfits. Migration is idempotent; signing in twice must not duplicate rewards or wardrobe items. Shared-device sign-out offers deletion of local personal data.

### 3.2 What onboarding must not request

No camera until a camera feature is selected. No contacts until the user chooses that import. No mailing address until checkout. No wallet until a blockchain action. No precise location for general shopping. No body photograph to get a style recommendation. No bundled consent for analytics resale, model training, public visibility or marketing.

### 3.3 Cold-start recommendation

Use explicit choices and a small licensed catalog first. The deterministic fallback scores category, occasion, budget and declared axes. It must work when no LLM key is configured. Explain this honestly as “Based on the styles you selected.” Seed recommendations do not receive fabricated purchase counts, friend endorsements, scarcity, or authenticity badges.

## 4. Looking Glass: user-controlled identity

### 4.1 Twelve initial axes

All axes use integer values 0–100, display steps of 1, keyboard steps of 5, and a default neutral 50 when unknown. Axes describe clothing preferences, not moral worth or psychological diagnosis.

| Key | Left / right labels | Example consequence |
|---|---|---|
| `temperature` | Warm / Cool | Palette relationships; does not infer skin tone |
| `sport_couture` | Sport / Couture | Technical casual pieces versus fashion-forward construction |
| `expression` | Understated / Expressive | Visual prominence and statement pieces |
| `fit_language` | Tailored / Relaxed | Silhouette preference, separate from body dimensions |
| `detail` | Minimal / Ornate | Surface/detail complexity |
| `novelty` | Timeless / Experimental | Familiar silhouettes versus unusual forms |
| `color` | Neutral / Colorful | Palette saturation and variety |
| `finish` | Matte / Lustrous | Surface finish |
| `structure` | Structured / Fluid | Garment shape and drape preference |
| `setting` | Urban / Outdoors | Contextual practicality |
| `exploration` | Familiar / Exploratory | How far discovery may range from established taste |
| `utility` | Functional / Decorative | Utility features and adornment |

Users may hide an axis, add a self-named preference tag, reject a suggested tag, or select “Do not infer this.” Custom axes become queryable only after mapping to an explicit ontology; arbitrary text must not be inserted into executable ranking expressions.

### 4.2 Separate four records

- **Declared preference:** deliberately supplied by the person.
- **Inferred preference:** model estimate with confidence, evidence categories, model version and timestamp.
- **Context override:** a temporary direction for a trip, event or period.
- **Effective preference:** the deterministic value actually used to rank a result.

Precedence: an active context override the user enabled, then a locked declared value, then an unlocked declared value blended only with permission, then an inference, then neutral. Unknown is distinct from neutral preference.

Default: explicit edits become locked until the user chooses “Let this adapt.” For adapting dimensions, use a bounded update no greater than 5 points per week and display the proposed change before applying the first one. This cap is a product default, not a scientific measure. A single accidental click never rewrites identity.

### 4.3 Interaction details

Dragging a slider updates the local preview immediately. After 300 ms idle, request a preview with a monotonically increasing revision; ignore stale responses. The preview must not write the profile. “Apply” commits all edits with an expected profile version. “Undo” returns to the prior saved snapshot. Keyboard input and numeric entry provide equivalent controls.

The right inspector contains:

1. “You chose 72.”
2. “Brand.Me inferred 61 from three saved looks.”
3. “Your choice is in control.”
4. Actions: lock, let adapt, inspect examples, exclude an example, clear this inference.

An inference deletion invalidates derived embeddings and recommendation caches through the event pipeline. It must not reappear from the same excluded observations at the next scheduled job. Record a suppression rule, not merely a deleted UI row.

### 4.4 Meaning of owning and editing backend stats

The member can change preference values, context, inferred labels, budget, sizes, brand affinities, excluded brands/materials, saved measurements, visibility, learning sources and inference permissions through supported APIs. Each edit is reflected in persisted backend state.

They can dispute, inspect and export factual records. They cannot directly award themselves points, alter another member's vote, forge an issuer signature, rewrite an order total, erase a counterparty's receipt, or change a chain-confirmed ownership event. Corrections to factual records are attributable amendments with provenance.

Provide a “What changes when I edit this?” explanation for each category. No SQL console or arbitrary JSON editing is required for ordinary users.

### 4.5 Recommendation explanation contract

Each recommendation has structured reasons tied to actual ranking inputs: “Uses your preferred relaxed silhouette,” “Pairs with two things in your closet,” “Within your $150 limit,” or “A sponsored placement.” Do not generate reasons after the fact that are unrelated to the score.

Show controls to prefer owned items, set a hard spend ceiling, increase exploration, exclude materials/brands, and disable use of social behavior. Sponsored placement is labeled and cannot silently override a hard constraint. A comparison preview shows how changing a preference affects results before saving.

## 5. Closet and garment intake

### 5.1 Closet categories

Use separate tabs for **Owned**, **Want**, **On the way**, **Digital**, and **Archive**. Item status and trust status are independent. A wishlist item can have verified product provenance without being owned. An owned item can be self-declared without brand verification.

Owned items support outfit membership, worn dates, care notes, clean/needs-care state, packing lists and repair history. These are private by default. Cost-per-wear may be calculated only when price and wear count are known; label estimates.

The 3D room must be useful at 1, 20 and 500 items. Render a limited visible capsule and virtualize the rest. Semantic organization persists independently of scene coordinates: rail, shelf, drawer, category, capsule, occasion and favorite. Changing room themes remaps semantic slots instead of scattering every object.

### 5.2 Add item paths

| Input | Required processing | Trust result |
|---|---|---|
| Photo | Validate, strip metadata, segment garment if selected, propose category/color | Self-added; visual interpretation requires confirmation |
| Catalog selection | Preserve provider/product/variant IDs and permitted media usage | Catalog match; not ownership |
| URL | Resolve through an approved provider or manual entry | Source link; never assume scraping rights |
| Receipt upload | Extract line items with confidence and user correction | Purchase evidence pending verification |
| QR/barcode | Parse identifier and resolve catalog/passport | Identification only unless cryptographic evidence is present |
| Secure NFC | Validate issuer/tag response and replay controls | Tag verification status; not automatically ownership |
| Manual | Name, category, status, optional image | Self-declared |
| Agent proposal | Show exact source, attributes and destination | User accepts before wardrobe mutation |

Every intake creates a review card with title, category, size/variant, closet destination and source. Uncertain fields are highlighted. The system must not silently choose a clothing size or invent a GTIN.

### 5.3 Deduplication and placement

Offer a duplicate suggestion based on provider variant, receipt line, tag serial, or user-confirmed visual similarity. A receipt line can contain multiple physical units, each with its own item identity. Never merge two unique physical serials simply because their photos match.

After confirmation, create the wardrobe item and placement in one transaction. Show an optimistic silhouette until acknowledged. Animate the item into the chosen rail/shelf only once per successful operation. On failure, the item returns to its source and an inline retry appears. A network retry reuses the operation ID and never awards points twice.

### 5.4 Styling and packing

An outfit is a versioned composition of item references plus styling notes, occasion, layer order and optional substitutes. A friend's contribution creates a proposal or fork, never an overwrite of the owner's outfit. Packing lists reference outfits and quantities; they support checked/packed/needs-care states. Travel locations and dates remain private unless deliberately shared.

## 6. Five-minute social decisions

### 6.1 Creator flow

Select a product or outfit; choose a question (“Does this work for me?”, “Which one?”, or custom); choose up to 12 recipients or a named circle; optionally set budget/context; preview the exact audience. Press **Ask my circle** to start a 300-second server-timed request.

If no friends exist, offer a share link or a private self-comparison. Do not create fake friend responses. External invite sharing uses the native share sheet and remains under the member's control.

The decision has `draft → open → closed`, with `cancelled` as a separate terminal state. The server fixes `opened_at` and `closes_at`. Device clocks only display the remaining interval. API votes arriving at or after the deadline are rejected with `decision_closed`.

### 6.2 Responder flow

Open notification or shared link; see product/outfit, the requester's stated intention and whatever style context they chose to disclose. Vote **Yes**, **Pass**, or **Try this instead**. A comment is optional. The response can be changed until expiry; only one qualifying participation award is possible.

Do not show other voters' choices before the person votes unless the requester deliberately selected an open discussion mode. This limits conformity pressure. “Pass” is as reward-eligible as “Yes.” Points must never incentivize an affirmative purchase.

### 6.3 Completion

At expiry, close once, reconcile votes, issue eligible points, notify the requester, and show a useful result: “4 yes, 2 pass, 1 alternative.” Zero votes yields “No replies this time” with save/extend-as-new-request options. A new request receives a new ID and cannot farm points from identical repeated polls.

The requester can say **Bought it**, **Saved it**, **Passed**, or **Still deciding**. Self-report is labeled. Verified provider orders may establish a separate attribution event, subject to consent. Do not call a vote a proven causal conversion.

### 6.4 Social safety and visibility

Blocking immediately excludes future notifications, shared collection access and search discovery between the parties. Existing content is evaluated under current permissions. Private friend lists and circle membership are not public. Report/mute/block are available from every member-generated post or comment.

Rate limits: default 5 new decisions/member/day; 3 concurrently open; 1 invitation per recipient per request; per-recipient notification quiet hours. These are configurable product defaults. Do not upload an address book merely to show who is already a member.

## 7. Rewards, badges and influence

### 7.1 Three separate concepts

- **Points:** nontransferable application credits, issued by deterministic rules.
- **Badges:** evidence of completed activities, optionally displayed.
- **Influence insights:** private or consented aggregate measurements of helpful participation, never a universal human-value score.

Points are not NIGHT, DUST, ADA, a financial investment, or proof of product authenticity. Optional future on-chain badge credentials require an independent opt-in; normal badges do not need minting.

### 7.2 Initial reward rules

| Event | Points | Eligibility and cap |
|---|---:|---|
| Complete first meaningful style setup | 100 once | Saved profile plus first saved look; no extra data disclosure requirement |
| Add a first owned item | 25 once | Confirmed persistent item; not per upload |
| Respond to a friend's decision | 10 | Unique eligible decision, before deadline; maximum 100/day |
| Helpful styling proposal accepted | 25 | Different member, unique outfit proposal; maximum 100/day |
| Catalog correction accepted | 50 | Reviewed evidence; maximum 250/week |
| Friend referral activates | 50 | New verified account plus meaningful use; no credit for contact upload |
| Optional research contribution | Campaign-defined | Clear purpose, fields, compensation and consent; separate from app access |
| Confirmed repair event | 50 | Evidence from an approved repair workflow; maximum 200/month |

Use integer amounts. Each rule has a version, qualifying event, effective dates, max count, actor/resource exclusions, fraud policy and reversal behavior. Reward settlement is idempotent. Returned orders cannot leave spend-based rewards permanently inflated. Do not issue points for wallet connections or uploading more private biometric data.

Use the [machine-readable reward defaults](contracts/reward-rules.json). Daily, ISO-week and calendar-month caps use UTC and the qualifying server event time; changing a profile timezone never resets a cap. Settle friend-response points after decision closure and eligibility reconciliation. A reversal remains a linked ledger entry. If the member already spent the affected points, track a disclosed recovery-due amount and offset future eligible credits under policy while keeping spendable points nonnegative; never turn app points into an undisclosed cash debt.

### 7.3 Badges

Initial badges: **First Reflection** (first saved persona), **Closet Curator** (10 organized owned items), **Trusted Eye** (20 valid friend responses across at least 5 decisions), **Style Collaborator** (5 accepted outfit proposals), **Care Keeper** (one verified repair), and **Material Story** (one verified product-history contribution).

Badge IDs, criteria and evidence versions are stable. Make criteria visible. Show earned date, eligible evidence and whether a badge was revoked. “Trusted Eye” describes participation, not identity verification. Do not equate badge count with purchasing power.

### 7.4 Redemption

The first redeemable benefits can be cosmetic room finishes, additional saved composition templates, or a funded partner benefit. Core data controls, accessibility, deletion and ordinary wardrobe access remain free. A benefit has inventory, eligibility, cost, expiry and fulfillment status.

Reserve points and benefit inventory atomically, then fulfill through a durable job. Failed fulfillment releases the reservation. Redemption history shows pending/fulfilled/refunded status. Do not display an unfunded gift card or a retailer discount that has not been contracted.

## 8. Sharing and personal presentation

Support outfit cards, a room vignette, a curated capsule and a decision link. Share generation requires an explicit preview showing image, caption, audience, expiry and visible product details. Hide prices, sizes, body measurements, purchase receipts, closet totals and chain addresses by default.

Room sharing renders only the selected collection and a sanitized camera view; it must not reveal the rest of a private closet through a loaded GLB, API payload or hidden scene object. Native share opens only after a user gesture. Social platform posting uses an approved connector if one exists; otherwise export an image or copy a link. Never claim an external post was published merely because a share sheet opened.

Revoking a link blocks future server access and invalidates controlled cached previews. Explain that an image already downloaded by another person cannot be recalled. Use a separate opaque share ID, not a user ID or ownership commitment.

## 9. Assistant experience

The assistant is a task workspace, not an unrestricted chat window with purchase powers. Example tasks:

- “Make three work outfits from what I own.”
- “Find a raincoat under $200 that works with this capsule.”
- “Ask my circle about these two options.”
- “Watch this exact size for a price drop.”
- “Prepare a repair request.”
- “Help me transfer this digital license.”

The task header shows objective, allowed sources, budget, deadline and permitted actions. The result separates retrieved facts from generated styling suggestions. Each proposed write has a preview; each purchase has the trusted confirmation flow in chapter 05.

Users can pause a task, revoke a source, inspect actions and undo reversible app changes. Pausing cannot promise to reverse a submitted retailer order. The assistant must explain the last known state and next supported action.

## 10. Ownership and circularity experience

The history screen starts with human questions: Who made it? What is known about it? What do I own? What can I do with it? What will another person receive?

Separate tabs: **Story**, **Evidence**, **My rights**, **Care & history**. Show a plain status for each claim: self-declared, issuer-attested, independently verified, expired, disputed or revoked. A chain transaction confirms a recorded event; it does not independently certify the physical claim.

Transfers clearly distinguish a physical item handoff, a digital wearable license and a manufacturing/reprint entitlement. A physical shipment and a digital transfer have separate completion states.

Reprint is offered only when a specific license and manufacturer support it. The experience includes design/version, size, materials, price, production lead time, allowed copies and what happens to the original. “Replace a worn item,” “Create an additional licensed copy,” and “Recycle material into a new item” are different workflows.

## 11. Creator and business experience

Creators upload designs and permitted media, define variants, attest rights, configure digital licenses and choose approved manufacturing capabilities. Drafts are not purchasable. Asset QA, product QA, license review and fulfillment readiness each have a visible state.

Brands can publish runway/editorial collections with licensing and attribution. Ingestion converts visual motifs into proposed product/style tags, which a human can review. A runway image is inspiration data, not automatically a catalog item or permission to reproduce a garment.

Business insights begin with catalog coverage, product engagement and aggregate demand by explicitly consented attributes. Suppress small cohorts; prevent repeated queries from reconstructing individuals; do not expose member-level persona sliders or body photos. Paid research campaigns are opt-in and explain the exchange in advance.

## 12. Product measurement

Measure first useful look, first meaningful closet save, first completed friend decision, accepted styling help, weekly use of owned items, preference corrections honored, useful recommendations saved, and successful provider handoffs. Track abandonment and error rates per capability mode.

Do not make gross merchandise value the only success measure. Also measure return reasons, unnecessary recommendation repetition, privacy revocation completion and whether a user can accomplish the core flow with 2D/reduced-motion modes.

The north-star candidate is **weekly members completing a self-expression loop**: creating or refining a look, involving their wardrobe or circle, and explicitly accepting a useful result. Validate this metric through research; do not treat it as proven.
