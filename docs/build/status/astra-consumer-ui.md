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

## Stage 2 — W01 shell implementation (2026-10-05)

- Consumer: editorial introduction and Today example, Me directory, functional display settings, primary/mobile navigation, desktop inspector, accessible Radix dialog, skip link, focus transfer, offline notice, loading/error/not-found states. `/shop` → `/discover`; `/stash` → `/closet`. Spatial destinations are links only; this branch does not supply their pages.
- Added explicit unavailable entry screens for later consumer stages. They are **not completed domain features** and do not create profiles, votes, points, purchases, connections, exports or deletion receipts. Full lane exit remains pending those integrations.
- Tokens are generated at render from the untouched specification JSON; no duplicated palette. Manrope 400/500/600/700 and Cormorant Garamond 500 Latin WOFF2 files are self-hosted under owned `lib/fonts/`, with both upstream OFL licenses (Fontsource packages `5.2.6`). Original inline SVG is labeled a fictional 2D style illustration, never a calibrated fit preview or actual spatial wardrobe.
- Theme (automatic/light/dark), reduced motion, stronger contrast and Simple View preferences use a versioned, device-local presentation record. OS reduced motion always wins; other lanes can consume `useExperiencePreferences()`. Simple View is a requested preference; spatial behavior is not verified in this branch.
- Console root implements contract v1 and no domain API reads. Root overview truthfully reports unconnected access; no fabricated operator role/provider verification. Legacy console API/helpers exist but are hidden by global `lib/` ignore rules; they are preserved unchanged, as are legacy `/proof/**` and `/dashboard/**` pages.
- Baseline type checks passed for both apps. Browser/build checks next. Validation dependencies are installed outside the repository; no manifest, workspace or lockfile edits. Baseline Next 14.0.4 is obsolete and must be replaced by foundation's supported tuple before release; successful baseline rendering will not satisfy the supported-toolchain gate.
- New source files under ignored `lib/` paths must be explicitly staged. Generated build output, temporary tooling and local `node_modules` symlinks are never committed.

## Stage 3 — shell build and HTTP verification / visual gate blocked (2026-10-05)

**Current disposition: shell implementation delivered for integration; W01 exit is NOT complete. Full consumer lane is NOT complete.** The user asked to begin with the shell; subsequent work remains W03/W05/W06/W07/W10 as specified above.

### Executed evidence

| Check | Result | Evidence / scope |
|---|---|---|
| Consumer TypeScript and optimized Next build | `passed` | `next build`: all 21 build entries generated; `/`, `/today`, `/me`, `/settings` and honest unavailable entry screens compile. Baseline tuple below, not the required supported upgrade. |
| Console TypeScript and optimized Next build | `passed` | Root shell and existing dashboard/proof routes compile. Root uses `force-dynamic` so runtime environment and future sessions are not frozen into build-time HTML. |
| HTTP render smoke | `passed` | Production-mode servers: 14 consumer entry routes + console `/` returned 200, exactly one main and one h1, and both light/dark token sets in delivered HTML. This proves server rendering, not hydration or visual quality. |
| Font delivery | `passed` | All five self-hosted WOFF2 assets returned 200 with nonempty payload in each app. Both OFL licenses are checked in. Fonts total about 88 KiB on disk. |
| Legacy redirects | `passed` | GET and HEAD `/shop` → `/discover`, `/stash` → `/closet`, HTTP 307. Initial page-based redirects returned 200 with streamed redirect markup; replaced with explicit route handlers and rechecked. `/closet` is still supplied by the spatial lane. |
| Runtime console mode | `passed` | Built without a mode, then served with `BRANDME_MODE=sandbox`: HTTP HTML displayed `sandbox environment`. No capability verification implied. |
| Static text-token contrast | `passed` | All 24 ink/muted/accent/forest/amber/error on canvas/surface combinations across light/dark are at least 4.5:1. Does not substitute for rendered contrast testing. |
| Legacy consumer fixture disclosure | `passed` | `/scan` HTTP output contains the new explicit legacy simulation notice. Existing scan/governance implementation remains unverified. |
| Whitespace, harness syntax, lane boundaries | `passed` | `git diff --check`; `node --check brandme-frontend/lib/testing/verify-shell.mjs`; no changes to protected spatial routes/features, design/contracts/packages, backend trees, manifests/workspace/lockfile, or legacy console pages/API helpers. |
| 390×844 / 768×1024 / 1440×900 + 320px overflow | `blocked` | No browser screenshots obtained; cannot assert no overflow or visual approval. |
| Keyboard, focus restoration, sheet sizes, dark/reduced motion, 200% zoom/text | `blocked` | Implemented and harness authored; browser execution unavailable. Actual device/screen-reader checks remain `not_run`. |

Consumer validation uses Node `24.19.0`, Next `14.0.4`, React/React DOM `18.2.0`, TypeScript `5.3.3`, Tailwind `3.4.0`, Radix Dialog `1.0.5`, Lucide `0.294.0`. An initial console build used that consumer tuple; it was replaced by a separate successful install/build using the console's own declared minima: Next/eslint-config-next `14.1.0`, React/React DOM `18.2.0`, TypeScript `5.3.3`, Tailwind `3.4.0`, Radix Dialog `1.0.5`, Lucide `0.309.0`. No claim of clean-checkout reproducibility or supported release readiness. Dependency upgrades/lockfile changes remain with foundation.

Browser blocker: agent-browser `0.38.2` failed to start its daemon. Direct Playwright/Chromium then identified the concrete sandbox restriction: `socket() failed: Operation not permitted`. Automatic approval policy rejected the requested browser escalation (`sandbox_approval: false`). That execution restriction was not bypassed. Builds and HTTP/static checks were completed as a safer alternative. No screenshots or browser pass results are fabricated.

### Browser gate ready to execute

`brandme-frontend/lib/testing/verify-shell.mjs` checks both shells at four widths in light/dark, axe accessibility, landmarks, keyboard skip, modal focus containment/Escape, the three mobile panel heights, persistent display settings, OS reduced-motion precedence, large text/reflow, fonts/heavy-dependency behavior, and legacy redirects. It writes screenshots only when actually run. Syntax checked; browser cases **not executed** here.

In a browser-capable environment with the apps running and validation-only `playwright@1.58.2` / `@axe-core/playwright@4.10.2` installed (exact versions, no repository manifest changes from this lane):

```bash
BRANDME_TEST_PACKAGE_JSON=/absolute/path/to/validation/package.json \
BRANDME_CONSUMER_URL=http://127.0.0.1:3000 \
BRANDME_CONSOLE_URL=http://127.0.0.1:3002 \
BRANDME_EVIDENCE_DIR=/absolute/path/to/shell-evidence \
node brandme-frontend/lib/testing/verify-shell.mjs
```

With dependencies installed by the foundation workspace, launch in separate terminals with `pnpm --dir brandme-frontend exec next dev -p 3000` and `pnpm --dir brandme-console exec next dev -p 3002`. The workspace/install gate is still blocked on foundation; these commands are not a fresh-checkout setup claim.

### Acceptance / next integration order

1. Foundation: provide supported pinned workspace/toolchain, `packages/design-system` token/font exports, generated API clients, and server session/guest migration interfaces. Replace the temporary specification-token/font bridge; do not edit the protected package from this lane. Provide CSP nonce handling for the small pre-paint preference script when the app CSP is introduced.
2. Browser-capable runner: execute the harness and inspect/fix every screenshot. `BM-VIS-001`, `BM-VIS-002`, `BM-VIS-012`, shell portions of `BM-OPS-002` and `BM-OPS-009` remain `blocked`; no whole criterion is marked passed from a static check. Large-text reflow in the harness is an equivalent viewport test, not evidence of actual browser zoom or a real-device accessibility review.
3. Spatial lane: use the shell-owned provider (import hook from `lib/client/experience-preferences`) and publish the preview/editor API. It returns conservative reduced motion until the OS preference is known. CSS also respects OS reduction. Three mobile sheet heights are 40/70/full usable viewport; keyboard buttons are an equivalent to dragging. No spatial rendering is included in this shell stage.
4. W03: implement real onboarding/guest migration and all 12 Looking Glass axes through generated domain clients. All `BM-ONB-*` and `BM-PER-*` remain `not_run`; current `/start` and `/me/style` pages are explicit unavailable states.
5. W05/W06/W07/W10: wire actual social deadlines/audiences/rewards, discovery, deterministic approvals/orders, and My Data controls. All related domain acceptance IDs remain `not_run`. Do not count these shell entry screens as those features.

Consumer shell shared pieces live in `components/shell/`; editorial SVG in `components/editorial/`; preferences/tokens/fonts and browser harness in owned `lib/`. Console shell helpers live in `components/` and `lib/{shell,navigation}.ts`. The console shell contract published earlier remains v1. No operational domain subtree has been created or modified.
