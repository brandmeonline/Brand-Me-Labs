# Lane brief: astra-consumer-ui

**Bench:** Astra (Codex) · **Branch:** `bench/astra-consumer-ui-20261005`
**Base:** `docs/brandme-full-experience-2026-10-05` · **Spec:** `docs/design/brandme/` + `contracts/`
**Work packages:** W01-shell/UI, W03-UI (onboarding + Looking Glass), W05-UI (social/loyalty), W06-UI (discovery), W07-UI (assistant/checkout), W10-UI (my data)
**Position in merge order:** After `opus-foundation` merges (needs `packages/design-system` tokens + generated API clients). Independent of Lane 6 (disjoint routes/features).

## What you are building
The consumer frontend — 40+ routes, the app shell, Looking Glass persona controls, social decision flows, the trusted checkout surface, discovery, and My Data screens. Read chapters 01, 02, 06 and the root `CLAUDE.md` first. Use the design tokens and screen/scene choreography as implementation requirements.

## You own exclusively (no other lane may touch these)
- `brandme-frontend/app/` — ALL routes EXCEPT `closet/**`, `try/**`, `add/**`, `style/**` (those are Lane 6)
- `brandme-frontend/app/layout.tsx`, `brandme-frontend/app/globals.css`
- `brandme-frontend/{lib,components}/`, `brandme-frontend/tailwind.config.js`
- `brandme-frontend/features/{persona,outfits,social,rewards,commerce,ownership,privacy}/`
- `brandme-console/` shell: `app/layout.tsx`, `app/page.tsx`, shared `components/`, `lib/` — PLUS publish your layout contract for domain pages in this status file BEFORE backend lanes build their `app/(ops)/**` subtrees

## Read-only for you (import, never modify)
`packages/design-system` (consume tokens; token gaps → request in this status file, never direct edits), `packages/contracts` (generated clients), `brandme-frontend/features/{spatial,closet}/` (Lane 6 — may import, never modify).

## Forbidden
Any `brandme_core/`, `brandme-data/`, `brandme-chain/`, or `brandme-gateway/` files. `docs/design/brandme/**`, `contracts/**`.

## Exit evidence (from ch.06 §2, UI portions)
- Shell renders at 390×844, 768×1024, 1440×900, plus 320px with no horizontal overflow; keyboard navigation throughout; reduced-motion removes camera flights/parallax while preserving state changes; dark-mode tokens verified; 200% zoom + large text usable
- Onboarding: useful first reveal in ~90 seconds, no wallet/camera/contacts required; guest migration idempotent (sign in twice → no duplicated rewards/wardrobe)
- Looking Glass: all 12 axes inspectable/editable, declared/inferred/effective separation, locks, evidence suppression, snapshots, reset; changes persist via the domain API (a refresh never reverts to mock data); recommendation explanations reflect actual scoring
- Social: five-minute server-timed decision composer with countdown; yes/pass/alternative responses; friend outfit proposals; sanitized share cards; blocks/revokes remove access
- Checkout: trusted confirmation surface with exact totals (deterministic panel — never model prose); price-changed and expired states handled
- My Data: inspection/edit/export/delete flows; consent revocation; derived-data suppression
- Visual QA: fix visible issues in screenshots before calling complete; fidelity labels on every preview type (photo-in-3D vs generative vs body overlay vs calibrated fit — never label generative imagery as calibrated fit)

## Cross-lane note
The visual outfit editor straddles Lane 5 (`features/outfits` — lists, proposals) and Lane 6 (3D composition). Rule: Lane 6 builds it as an embeddable component; you import it read-only. Confirm the component interface with Lane 6 via status files.

## Status protocol
Record status ONLY in this file. Propose deviations here. Publish your console shell layout contract here early.

## Global rules (all lanes)
Never edit another lane's owned files. Never edit `docs/design/brandme/**` or `contracts/**`. No `latest` tags — pin everything. Demo fixtures carry visible simulation labels. Never label generative imagery as calibrated fit.

---

## Stage 1 — inspected baseline / console contract published (2026-10-05)

- Branch: `bench/astra-consumer-ui-20261005`; starting commit `813051a`.
- Read this brief first, root `CLAUDE.md`, product/visual/delivery chapters and machine contracts. The checkout has Next 14 / React 18 placeholder apps, no consumer root page, no `packages/design-system`, no `packages/contracts`, and no spatial feature modules. The foundation workspace/toolchain migration is not present. No domain/backend files will be changed here.
- Immediate stage: W01 consumer and console shells. W03/W05/W06/W07/W10 remain pending their actual domain/client integrations; shell screenshots cannot pass those acceptance gates.

### Console shell layout contract v1 — available for backend lanes now

1. Root `brandme-console/app/layout.tsx` imports the shell CSS and renders `ConsoleShell` from `@/components/console-shell`. It owns the app-level skip link, navigation, environment notice, responsive rail and exactly one `<main id="console-content" tabIndex={-1}>` for new operator pages.
2. Add domain pages under `app/(ops)/<route>/page.tsx`. The route group is transparent: `app/(ops)/providers/page.tsx` serves `/providers`. Do not add another global rail, `<html>`, `<body>`, or `<main>`. Domain-owned layouts may nest sections inside the existing main.
3. Page interface: ordinary Server Component returning a fragment/section. Optional `ConsolePageHeader` import from `@/components/console-page-header`: `{ eyebrow?: string; title: string; description?: string; actions?: ReactNode }`. It renders the page's single `<h1>`. Each page owns its loading, error, empty, denied, stale and actual action states.
4. Reserved navigation paths: `/providers`, `/ingestion`, `/commerce/operations`, `/chain/operations`, `/rights/issuers`, `/manufacturing/jobs`, `/moderation`, `/rewards/disputes`, `/capabilities`. Provider children live at `/providers/[id]/{setup,health}`. This lane creates none of those domain pages. Domain lanes can use any child path without changing the shell.
5. The shell is presentation only, **not an authorization boundary**. Backend lanes must authorize every server read/mutation and protect their `(ops)` layouts/pages using the foundation identity adapter. No operator data is fetched by the shell, no fake role is injected, and navigation visibility grants no authority. Root overview reports access/capabilities as unverified until integration.
6. Preserve `/proof/[scanId]` and `/dashboard/**`: the shell passes these legacy surfaces through without wrapping them in a second main/nav. Their existing behavior is not represented as verified by this work.
7. New operator styling uses `--bm-*` semantic properties (canvas, surface, ink, muted, line, accent, forest, amber, error), matching the read-only design contract in both themes. `console-page-header`, `console-section`, `console-grid`, `console-notice`, `console-table-region` are shell-owned helpers; pages can also use existing Tailwind primitives. Wrap wide domain tables in a labeled `console-table-region` with keyboard focus; never let them expand the document. Main content is min-width:0 and fluid. Mobile navigation uses a focus-managed dialog; Escape restores trigger focus.
8. Shared styling is in `components/console-shell.css`, imported by root layout. Do not modify shell files from backend lanes. Record requested contract changes in the requesting lane's status file.

### Foundation requests / temporary deviations

- Publish the `packages/design-system` token export/CSS entry point and generated client names, plus the exact supported Next/React workspace tuple. Until that lands, the shell's isolated token adapter reads `docs/design/brandme/contracts/design-tokens.json` **read-only**. This is a temporary bridge, not a second token authority. No palette values may be silently invented.
- Need semantic `on-accent` pairings for dark/light themes, persisted theme/motion preference contract, and self-hosted font asset exports with licenses. Until provided, use ink/canvas contrast pairing and licensed app-local fonts or the contract's declared fallbacks. Any local font files stay in this lane's owned `lib/`.
- Keep dependency manifests/workspace/lockfile untouched: those belong to foundation. Validate against the baseline when possible and rerun after the supported tuple arrives.
- Spatial lane: please publish the embeddable outfit/closet preview interface and canonical reduced-motion input. Shell will export `useExperiencePreferences()` with `reducedMotion: boolean` and `simpleView: boolean`; user/OS reduction wins. No spatial/closet route or feature file is changed by this lane.

### Evidence at this stage

Inspection only. Shell build, screenshots, keyboard, motion, dark mode and zoom: `not_run`. Full onboarding migration, persona persistence, decision deadline, checkout and privacy flows: `not_run` / waiting for domain integration. No production or provider verification claimed.
