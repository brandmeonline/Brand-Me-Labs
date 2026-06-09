# Reference Anchors

Curated list of non-default design references for use in Phase B of the `design-audit` skill. Use the slug (left column) as `<anchor>` in the refiner prompt. Add new entries by category. Never invent an anchor at prompt time — add it here first.

## Industrial / Authoritative

| Slug | Source | Aesthetic in one line |
|---|---|---|
| `linear` | linear.app | Saturated dark, razor-sharp type, dense detail, single accent — the credibility default for technical products |
| `vercel` | vercel.com | Monochrome with vertical rhythm, restrained, geometric precision |
| `stripe` | stripe.com | Corporate-bright, masterful typography, optical alignment, payments-grade trust |
| `anthropic-console` | console.anthropic.com | Paper whites, slow motion, restrained chrome, reading-respect |
| `pitch` | pitch.com | Editorial product surface, strong type hierarchy, restrained color |

## Editorial / Magazine

| Slug | Source | Aesthetic |
|---|---|---|
| `are-na` | are.na | Text-first, no chrome, deliberate emptiness, content carries it all |
| `its-nice-that` | itsnicethat.com | Newspaper layouts on web, density-as-statement |
| `substack-reader` | substack.com (reader view) | Long-form respect, typographic hierarchy is everything |
| `nyt-article` | nytimes.com | Proven editorial primitives, body-led, restrained imagery |
| `read-css-zen-garden` | csszengarden.com | A reminder that semantic HTML + intentional CSS is the original distinctive |

## Personal / Handmade

| Slug | Source | Aesthetic |
|---|---|---|
| `family-co` | family.co | Wet-ink illustration, decorative serifs, organic shapes, human warmth |
| `maggie-appleton` | maggieappleton.com | Handmade SVG, color-block sections, illustrated metaphors |
| `nicky-case` | ncase.me | Bespoke micro-interactions, hand-drawn primitives, playful proofs |
| `rauno-me` | rauno.me | Extreme polish on tiny details, micro-interactions as content |

## Brutalist / Anti-design

| Slug | Source | Aesthetic |
|---|---|---|
| `bloomberg-bw` | bloomberg.com/businessweek (long-form) | Typographic violence, intentional ugly-on-purpose, headline-as-art |
| `cabel-sasser` | cabel.com | Neon, monospace, aggressive, web-as-fanzine |
| `arena-brutalist` | arena.computer | Console-mode density, monospace, network-as-UI |

## Material / Dimensional

| Slug | Source | Aesthetic |
|---|---|---|
| `apple-vision-marketing` | apple.com (visionpro pages) | Depth, glass, light, dimensional photography |
| `arc-browser` | arc.net | Mac-app dimensionality translated to web, big rounds, light play |
| `polycam` | poly.cam | 3D-first surface, real-time render in marketing |
| `spline` | spline.design | Native 3D primitives in product UI |

## Luxury / Restraint

| Slug | Source | Aesthetic |
|---|---|---|
| `aesop` | aesop.com | Single image, generous space, single accent, copy-led |
| `hermes` | hermes.com | Typography hierarchy carries everything, considered photography |
| `loewe` | loewe.com | Editorial e-commerce, no SaaS chrome, runway-as-product-grid |
| `the-row` | therow.com | Radical reduction, almost no UI, brand-as-restraint |
| `dover-street-market` | doverstreetmarket.com | Punk-luxe, intentional clash, art-direction-led |

## Provenance / Authentication-specific

| Slug | Source | Aesthetic |
|---|---|---|
| `vacheron-watch-archive` | vacheron-constantin.com (archive pages) | Heritage-document treatment, certificate aesthetic |
| `permanent-record-archive` | (curated archives like permanent.org) | Long-life document UI, generations-not-sessions framing |
| `cardano-explorer` | cardanoscan.io | What blockchain UI currently is — useful as a negative reference (avoid) |

---

## Suggested contrast triads for Brand.Me

The brand axis is **fashion-luxury × technical credibility × circular-economy soul**. Mix one anchor from each row below to ensure concept divergence:

| Credibility row | Luxury row | Soul row |
|---|---|---|
| `linear` | `aesop` | `family-co` |
| `vercel` | `hermes` | `maggie-appleton` |
| `anthropic-console` | `loewe` | `rauno-me` |
| `stripe` | `the-row` | `nicky-case` |

**Avoid combining**:
- Pure `cardano-explorer` (already the blockchain default — what every chain startup ships)
- Pure `stripe` + pure `linear` (over-rotates to corporate SaaS, loses garment side)
- Pure `bloomberg-bw` + pure `aesop` (clashes — pick one direction or design the clash deliberately)

**Category-specific overrides**:
- **Charts / data tiles** → bias to credibility row (Linear/Stripe), Aesop will mis-fit
- **Garment card / product detail** → bias to luxury row (Aesop/Loewe), Linear will mis-fit
- **Provenance certificate view** → consider `vacheron-watch-archive` as the anchor; this is exactly the heritage-document problem
- **Governance / escalation console** → bias to credibility + `arena-brutalist` for density
- **Onboarding / marketing pages** → all three rows are valid; widest concept divergence available

---

## Adding new anchors

When the user requests an anchor not in this list:

1. Confirm the URL or screenshot reference.
2. Pick the closest existing category (or create a new H2 if genuinely new).
3. Add a row: `slug | source | one-line aesthetic`.
4. Commit with the next concept commit — don't ship anchors-only commits.
