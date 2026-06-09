---
name: design-audit
description: Audit Brand.Me frontend surfaces for "default-ness" and generate non-standard design concepts using the 21st.dev Magic MCP. Use when the user asks to audit website designs, pull innovative concepts, push UI off shadcn/SaaS defaults, refresh component aesthetics with explicit reference anchors, or kick off a frontend redesign. Outputs a scored audit and a concept catalog to .claude/skills/design-audit/output/ so work can resume across sessions.
---

# Design Audit & Concept Generation

A reproducible, multi-session workflow that turns "audit our frontend and pull new concepts" into structured outputs on disk. Designed to be invoked from a fresh Claude Code session or from a sub-agent — the audit/concept artifacts persist across sessions so each run can pick up where the previous left off.

## When to use this skill

Trigger when the user asks any of:

- "Audit our website / app design"
- "Find innovative design concepts for X"
- "These components feel too default / too shadcn / too SaaS — push them"
- "Generate alternatives for `<component>` in the style of `<reference>`"
- Before kicking off a frontend redesign

Do **not** use this skill for:

- One-off "build me a new component" (use `mcp__magic__21st_magic_component_builder` directly)
- Bug fixes or styling tweaks within the current aesthetic
- Backend-only or infrastructure tasks

## Required tools

| Tool | Phase | Failure mode if missing |
|---|---|---|
| Read, Grep, Glob | A, B | hard requirement |
| Write | A, B, C | hard requirement |
| `mcp__magic__21st_magic_component_refiner` | B | stop after Phase A, report missing MCP |
| `mcp__magic__21st_magic_component_inspiration` | B | optional; reduces concept diversity if missing |
| `mcp__magic__logo_search` | C (optional) | optional |
| `ui-ux-pro-max` skill data at `.claude/skills/ui-ux-pro-max/data/*.csv` | A (grounding) | proceed without; mark report as ungrounded |

If `mcp__magic__*` tools are not loaded, run Phase A only and write a `NEEDS_MAGIC_MCP.md` note into the output dir. Do not fabricate concepts.

## Default scope (Brand.Me)

Unless the user overrides, audit these surfaces:

- `brandme-frontend/components/*.tsx` — currently FacetList, GarmentCard, Header, IntegrityBadge
- `brandme-frontend/app/**/page.tsx` — currently stash, governance, scan, shop, plus `layout.tsx`
- `brandme-console/components/**/*.tsx` if the service is present in `docker-compose.dev.yml`

Skip: `brandme-frontend/lib/*` (data), test files, stories.

Per `CLAUDE.md`, components currently contain placeholder UI (e.g. `<div>[Image]</div>` in `GarmentCard.tsx`). Treat low scores as "starting point not yet committed" rather than "needs to be ripped out" — the goal is to set direction before the placeholders harden.

## Workflow

### Phase A — Inventory & audit

1. Glob the default scope. Categorize each file into one of: **navigation**, **hero**, **card**, **form**, **dialog**, **list**, **dashboard tile**, **marketing block**, **page-shell**.

2. Read each file. Score against the **audit rubric** (below), 0–3 per axis:

   - Typography hierarchy
   - Density
   - Grid
   - Color temperature
   - Motion
   - Primitives used
   - Surface treatment

3. Write `output/audit-<YYYY-MM-DD>.md` containing:
   - One Markdown table: `file | category | type | density | grid | color | motion | primitives | surface | total | band`
   - Bands: **0–6 default**, **7–13 differentiated**, **14–21 distinctive**
   - A short prose section per component flagging the single most "default" axis — that's the lever to pull in Phase B
   - A "candidates for Phase B" list (anything scoring ≤6 or scoring 0 on three+ axes)

### Phase B — Concept generation

For each Phase A candidate:

1. Read the current component file.
2. From `references.md`, pick **three anchors that disagree with each other**. The Brand.Me default triad: **Linear** (authoritative) + **Aesop** (luxury restraint) + **Family.co** (handmade soul). Override if the component category demands it (e.g. a chart belongs in Linear/Stripe territory, not Aesop).
3. For each anchor, invoke `mcp__magic__21st_magic_component_refiner` with this prompt template:

   > Take this `<category>` component and propose a redesign in the style of **`<anchor>`**.
   >
   > Reject these defaults present in the current implementation: `<list the 0/1-scoring axes from the audit row>`.
   >
   > Brand context: Brand.Me is a garment-authentication platform on Cardano + Midnight blockchains. Aesthetic axis: **fashion-luxury × technical credibility × circular-economy soul**. Audience: brand operators and end consumers verifying garment provenance.
   >
   > Output format: Next.js 14 app-router component, TypeScript, Tailwind utility classes. No new dependencies unless essential — note them at the top if added.
   >
   > Constraints: must keep the public prop interface compatible with the current component (read the file). No lorem ipsum — wire to the same data shape.

4. (Optional) Call `mcp__magic__21st_magic_component_inspiration` with the category + anchor to surface 21st-library variants, attach the top result IDs to the rationale.
5. Write each concept to `output/concepts/<component-stem>/<anchor-slug>.tsx`.
6. Write `output/concepts/<component-stem>/<anchor-slug>.md` containing:
   - **Breaks**: which audit defaults this concept overturns
   - **Asserts**: the positive design claim it makes
   - **Brand fit risk**: where it might over-rotate (e.g. "Aesop direction risks reading as e-commerce, not platform")
   - **Migration notes**: prop deltas, new tokens, motion deps

### Phase C — Recommend

1. Score every concept against a brand-fit triad (0–3 each):
   - **Technical credibility** (does it read as a real platform, not a marketing site?)
   - **Luxury / garment authority** (does it respect the fashion side?)
   - **Distinctive memorability** (would a user remember a screenshot?)

2. Write `output/recommendations-<YYYY-MM-DD>.md` with the top 3 concepts overall:
   - File path to replace
   - Concept file to adopt
   - Brand-fit triad scores
   - Risk and mitigation
   - Suggested order of integration (which to ship first as a proof point)

3. **Stop.** Do not apply changes. Surface the recommendations.md path to the user and wait for explicit approval of which concept(s) to integrate.

### Phase D — Integration (only on user approval)

For each approved concept:

1. Read the target component again (in case it changed).
2. Diff the concept against current props. Adjust the concept so prop signature matches exactly.
3. Apply via Edit (preferred) or Write.
4. Start the dev server (`cd brandme-frontend && pnpm dev`) and verify the affected route renders without runtime errors. If a route can't be exercised headlessly, say so explicitly — don't claim verification.
5. Commit on the active branch with message: `Apply <anchor> design concept to <component>`.

## Audit rubric (full)

| Axis | 0 (default) | 1 | 2 | 3 (distinctive) |
|---|---|---|---|---|
| **Typography** | single sans, 16px body, default weights | varied weights, two faces | optical sizes or fluid type | editorial scale + display face + variable axes |
| **Density** | shadcn default padding | tightened intentionally | dashboard- or magazine-dense | spatial composition, deliberate emptiness |
| **Grid** | 12-col centered | asymmetric within grid | broken grid sections | bespoke grid, overlapping zones |
| **Color** | gray scale + 1 accent | warm/cool monochrome | restricted earth tones | hand-mixed OKLCH palette |
| **Motion** | none or default tw transition | hover spring | scroll-linked | gesture-aware / physics |
| **Primitives** | shadcn unmodified | shadcn restyled | handmade primitives | system-level redefinition |
| **Surface** | flat white card | glass / subtle gradient | textured / paper | dimensional / material |

Range 0–21. Bands: **0–6 default**, **7–13 differentiated**, **14–21 distinctive**.

## Reference anchors

Curated in `references.md` in this directory. The list is grouped by aesthetic so you can pick contrasting anchors in seconds. Always include at least one anchor that is *aesthetically incompatible* with the others — concept divergence is the point.

## Invocation patterns

### Direct (in current session)

User says any trigger phrase → invoke this skill → run Phase A → if magic MCP loaded, run B and C → stop and report.

### Sub-agent (recommended for full audits)

Keeps the main session's context window clean while a long audit runs:

```
Agent(
  description: "Audit Brand.Me frontend designs",
  subagent_type: "general-purpose",
  prompt: "Read /home/user/Brand-Me-Labs/.claude/skills/design-audit/SKILL.md and execute Phases A, B, and C on the default scope. Write all outputs to .claude/skills/design-audit/output/. Report only the path of the final recommendations-*.md file (under 100 words). Do not apply changes."
)
```

The sub-agent must have access to the `mcp__magic__*` tools. If those aren't loaded in its environment it will stop after Phase A.

### Loop / monitor (long horizons)

For ongoing design watch (new pages added, components edited), schedule with the `loop` skill:

```
/loop 24h /design-audit
```

The skill is idempotent on rerun — it writes new timestamped audits without overwriting prior ones.

## Resume semantics

Outputs are timestamped. To resume a partial run:

1. Read the most recent `output/audit-<date>.md`.
2. If `<date>` is within 7 days and the inventory still matches current files, skip Phase A.
3. For each Phase A candidate without a populated `output/concepts/<stem>/` directory, run Phase B.
4. Always rewrite `recommendations-<today>.md` at the end so the most recent ranking reflects all concepts on disk.

## Guardrails

- **Never apply concept code without user approval.** Phase C ends with a stop.
- **Never overwrite the user's frontend files in Phase B.** Concepts live in `output/concepts/`.
- **Never invent reference anchors.** Use only what `references.md` lists. If the user requests an anchor not in the list, add it to references.md first (with a one-line aesthetic descriptor) and commit the addition.
- **Don't fabricate scores.** If a file is too short to evaluate an axis, mark it `-` not a guess.
- **Don't pretend Magic ran when it didn't.** If the MCP tool returns an error or is unavailable, write the error to the concept rationale and skip.
