# Brand.Me — Be More U

## Complete product and implementation specification

**Specification date:** 2026-10-05

**Repository baseline:** `brandmeonline/Brand-Me-Labs@0f5f58a9eecaca46b367c9bd96f89654343fa5fb`

**Status:** Implementation contract and design proposal authorized by the founder's October 5 brief. This is not a claim that the described application already exists.

**Intended implementer:** Claude Code with Opus 5.5, or an equivalently capable repository agent.

Brand.Me helps a person define and express themselves through fashion, make decisions with people they trust, and receive value for their participation. A living wardrobe connects aspirations, possessions, outfits, social relationships, commerce, and the continuing history of a garment. Midnight supplies privacy-preserving ownership and rights workflows. It does not replace the consumer experience.

This specification restores the personality engine and social shopping vision to the repository's trust infrastructure. The target is an actual, beautiful application with persistent behavior, not a set of decorative screens or synthetic blockchain receipts.

## Reading order

Read every document before implementation. Keep the contracts open while coding.

| Document | Purpose |
|---|---|
| [01 Product and experience](01-product-experience.md) | Product invariants, onboarding, every principal screen, persona controls, social decisions, points, badges, creator and brand journeys |
| [02 Visual, motion, 3D and AR](02-visual-motion-spatial.md) | Visual system, responsive layouts, exact animation timelines, closet scene geometry, asset pipeline, device behavior and try-on |
| [03 Architecture, data and APIs](03-architecture-data-api.md) | Repository migration, deployment topology, domain ownership, persistence, event delivery, contracts and API behavior |
| [04 Midnight, ownership and lifecycle](04-midnight-ownership-lifecycle.md) | Real proof boundaries, private state, contracts, custody, transfer, provenance, licensed reprint and physical verification |
| [05 Commerce, agents and connectors](05-commerce-agents-connectors.md) | Nordstrom/Impact, Shopify/UCP, ACP, AP2, MCP, agent authorities, payments, ingestion and owner setup |
| [06 Delivery and verification](06-delivery-verification.md) | Ordered implementation work packages, tests, performance budgets, rollout and completion evidence |
| [07 Repository evidence and research](07-repository-audit-sources.md) | What was inspected, code findings, historical reconciliation, dated primary sources and architecture decisions |
| [Claude build prompt](CLAUDE_BUILD_PROMPT.md) | The single kickoff instruction to execute this package |
| [Machine-readable contracts](contracts/README.md) | Design tokens, domain schemas, fixture scenario and acceptance catalog |

## How to interpret requirements

- **MUST** is an acceptance requirement. **SHOULD** allows an explained, tested deviation. **MAY** is optional.
- Product behavior in this package supersedes the narrow trust-first product sequencing in the older `PLAN.md`. It does not supersede repository security instructions, actual provider contracts, or verified code facts.
- An external dependency is **not** complete because its adapter returns a plausible response. Completion requires the appropriate sandbox or production evidence.
- Defaults below are explicit implementation choices. They can be changed through a recorded architecture decision without silently removing the founder's product requirements.
- Build in one sustained execution initiated by the prompt, using small verifiable stages and resumable checkpoints. No document can guarantee that a model will produce a production system in one unreviewed response.
- No initial wallet, body scan, contact import, purchase, or public post is required to experience value.
- No actual money movement, mainnet deployment, retailer agreement, or customer messaging is authorized by this documentation change. The build creates those capabilities and their operator controls.

## Non-negotiable product contract

1. The person controls their declared and inferred style profile. They can inspect, correct, lock, reset, export, and remove it.
2. Social shopping is a first-class product: five-minute purchase decisions, friend styling, shared outfits, closets with permissions, and useful participation rewards.
3. The closet is spatial and functional. The user chooses its environment, places garments, switches to an accessible list, and keeps changes across devices.
4. A saved product, an ordered product, a physically owned item, a verified item, a digital license, and a right to reprint are distinct things.
5. Provenance, ownership proofs, material certifications, reward balances, and receipts have named authorities. Editing a preference does not grant the ability to falsify these records.
6. The user sees why something was recommended and can make an immediate, persistent change.
7. Commerce connects to authorized providers. It uses exact variants, fresh quotes, bounded approvals, and real order reconciliation.
8. Private information stays out of public blockchain state, social previews, analytics exports, and model prompts unless the user expressly discloses the minimum required data.
9. Garment visualization communicates its fidelity. A photograph displayed in 3D, a generative preview, a body overlay, and a physically calibrated fit simulation receive different labels.
10. A complete build includes the ordinary states: empty, slow, offline, denied, expired, revoked, duplicated, returned, lost-device, and disputed.

## Build modes

| Mode | Purpose | Permitted evidence |
|---|---|---|
| `demo` | Beautiful, deterministic exploration with fictional products and people | Persistent local/emulator app behavior; all simulated providers visibly labeled |
| `development` | Real domain logic against emulators and deterministic adapters | Database and browser test evidence; never represented as live retail or chain activity |
| `sandbox` | Authorized partner sandboxes plus Midnight local/Preprod and Cardano Preprod | Actual provider receipts and network observations, labeled by environment |
| `production` | Approved providers, operational controls and audited rights contracts | Real orders and network evidence; no stub fallback anywhere in the trust path |

The consumer UI must remain useful when a provider is unavailable. It must not pretend that the unavailable capability succeeded. A capability registry, not scattered booleans or cosmetic badges, decides what is offered.

## Release interpretation

**Experience complete** means the entire consumer loop works with durable state and honest adapters. **Integration verified** means a named provider/network passed its required tests. **Production approved** additionally requires the operating, contractual, security, and asset-rights gates described here. These are separate dimensions and must appear separately in the completion report.

## Ownership of this specification

The founder's current request and the reviewed Brand.Me history supply the product intent. Engineering choices, numerical UX targets, reward values, retention defaults, and acceptance thresholds in this package are proposed defaults for an executable build. They are not historical claims, merchant promises, measured performance, or financial forecasts.
