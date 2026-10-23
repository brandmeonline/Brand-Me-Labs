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

## Stage 4 — independent browser verification of the W01 shell (2026-10-05)

Independent run by Mia at the user's request against branch HEAD `472c404f3c34ff3eb59e23256abc77b36fb6da75` ("feat(ui): build consumer and operations shells from design tokens"). This supersedes the Stage 3 browser blocker: the lane's own environment could not launch a browser, so verification ran in a separate browser-capable runtime. No lane code files were touched; only this status file is updated, and only to record results.

### Environment (all validation-only, outside the repository)

- Node `v24.20.0`; `playwright@1.58.2`; `@axe-core/playwright@4.10.2`; Playwright Chromium (`chromium-1208`, headless)
- Clean checkout of `472c404` with per-app `npm install` (consumer: Next `14.0.4`/React `18.2.0`; console: Next `14.1.0`/React `18.2.0`); `node_modules` never committed, no manifest/workspace/lockfile edits
- Apps served with `next dev` (consumer `http://127.0.0.1:3000`, console `http://127.0.0.1:3002`); the committed read-only token bridge `docs/design/brandme/contracts/design-tokens.json` was present in the checkout
- Harness executed unmodified: `node brandme-frontend/lib/testing/verify-shell.mjs` with `BRANDME_TEST_PACKAGE_JSON`, `BRANDME_CONSUMER_URL`, `BRANDME_CONSOLE_URL`, `BRANDME_EVIDENCE_DIR` set per the Stage 3 instructions

### Result: 13 passed, 0 failed (process exit 0)

| # | Check | Result |
|---|---|---|
| 1–8 | Consumer + console at 320×844, 390×844, 768×1024, 1440×900: light and dark render, exactly one `main` and one `h1`, no framework error overlay, no horizontal overflow, axe clean (`wcag2a`, `wcag2aa`, `wcag21aa`), no page errors, dark mode flips `--bm-canvas` to `#161817` | `passed` |
| 9 | Consumer keyboard: skip link is first Tab stop and focuses `#main-content`; mobile menu dialog traps focus across 45 Tabs through Compact/Medium/Full-height snap buttons (each `aria-pressed` verified); Escape closes; focus returns to the `Open menu` trigger; menu `Settings` link routes to `/settings` with the expected heading | `passed` |
| 10 | Display preferences: dark theme + Reduce motion + Simple View survive reload; in-app reduction removes `.bm-route-content` animation; with in-app reduction off, OS `prefers-reduced-motion` still wins; no `canvas`/`video`; no mediapipe/three/model-viewer/external-font requests | `passed` |
| 11 | 200% reflow/text: `/today`, `/me`, `/settings` at 720×450 and `/settings` at 320×844 with `font-size: 200%` — no horizontal overflow | `passed` |
| 12 | Legacy redirects honest: `/shop` → `/discover` and `/stash` → `/closet`; `/discover` and `/me/data` entry screens state the catalog/privacy surface is "not connected" rather than implying readiness | `passed` |
| 13 | Console mobile menu at 320×844: `Open operations menu` dialog traps focus across 25 Tabs, Escape closes, focus returns to trigger | `passed` |

### Evidence

20 PNG screenshots written by the harness run (kept with the verification run, not committed): `consumer-{320x844,390x844,768x1024,1440x900}-{light,dark}.png`, `console-{320x844,390x844,768x1024,1440x900}-{light,dark}.png`, `consumer-large-text-{today,me,settings}.png`, `consumer-reduced-motion.png`. Spot-checked renders show the consumer editorial shell with labeled fictional 2D illustration and the console operations shell truthfully reporting unconnected access.

Visual observation (not a failure): in the 390×844 consumer full-page capture, the fixed bottom tab bar renders over body copy mid-capture. This is most likely a known full-page-screenshot artifact of `position: fixed` elements, not a real overlap — but the lane should confirm on a real device that content carries enough bottom padding to clear the tab bar.

### What this run does and does not establish

- Establishes: the committed shell renders and hydrates without errors in Chromium at all four required widths, light and dark; no 320px overflow; axe-clean; keyboard/focus behavior as authored; preference persistence; OS reduced-motion precedence; 200% text/reflow; honest unavailable states.
- Does NOT establish: production-build behavior (this run used `next dev`, not `next build`/`next start` — the lane's own optimized-build evidence stands separately); screen-reader behavior (`not_run`); real-device checks (`not_run`); human visual approval of the screenshots.
- W01 is NOT marked complete. Still missing: foundation integration (published `packages/design-system` token export/CSS entry, generated client names, supported Next/React tuple — this ran on the baseline 14.0.4/18.2.0 — `on-accent` pairings, persisted theme/motion contract, self-hosted font exports with licenses); screen-reader and device evidence; and all of W03/W05/W06/W07/W10 domain work, which remains `not_run` behind unavailable entry screens.

## Stage 5 — resumed inspection and remaining W01 controls (2026-10-23)

- Re-cloned the lane after transient workspace maintenance. Read this brief first, then the product/visual/delivery specification, root instructions and machine contracts. Lane HEAD remains `019204c3`; the independently verified shell is preserved, not rebuilt from scratch.
- Foundation bench is published at `67327e45`, but its packages are absent from this lane. The previous request to merge foundation and change app manifests/shared lockfile has not been approved; the repeated lane brief preserves the original ownership boundaries. No merge, dependency-manifest change, shared-package edit or backend change will be made in this stage. Integrator request: bring in foundation and authorize/install the supported framework tuple and workspace dependencies; then replace the temporary read-only specification token bridge.
- Unblocked work: complete app-local W01 accessible primitives and a development-only component gallery, exercise reusable controls in display settings, and harden the mobile shell against bottom-navigation growth. The existing 64px padding assumption does not track actual navigation height after text scaling; the screenshot observation is not itself proof of a real-device defect.
- Console contract v1 above remains published and unchanged. All new controls stay in this lane's `components/` and `lib/`, not `packages/design-system`. No domain capability or full W01 completion is claimed. New browser/device evidence starts `not_run`; Stage 4 passes apply only to its recorded commit.

## Stage 6 — app-local primitives and mobile clearance implemented (2026-10-23)

- Added `components/ui/` primitives: Button/ActionLink, labeled Input/Select/Switch, native range + numeric Slider, keyboard Tabs, Radix Dialog, Drawer reuse of the existing shell Sheet, Toast, Skeleton, EmptyState, ErrorState, StatusChip, Price and EvidenceLabel. No new runtime dependency. Display settings now exercise the shared Switch, with label and description separately associated.
- Slider distinguishes unknown (`null`) from an explicit neutral 50; pointer step is 1, arrow-key step 5, numeric entry is integer-only, and Clear restores unknown. These are draft controls, not persona persistence or a pass for BM-PER. Tabs use one tab stop, arrow/Home/End navigation and disabled-tab skipping. Dialog/Drawer use the existing focus-management dependency. Toasts do not auto-expire important actions or steal focus; Skeleton is static rather than an endless animation.
- Price formatting validates the wire-format decimal string and uses integer/string operations throughout, including values above JavaScript's safe-number limit. Currency exponent comes from runtime Intl metadata, unknown metadata fails closed as unavailable, and the ISO code remains visible. This is presentation, not a quote validator, provider verification or a checkout implementation.
- EvidenceLabel keeps photo display, approximate/product 3D, live overlay and generative preview distinct. Fit-estimate rendering requires method plus limitations; the gallery offers no fit-estimate capability. No generative example is labeled calibrated fit.
- `/dev/components` is a clearly labeled local fixture gallery with no domain writes. The production check caught streamed not-found HTML returning HTTP 200 with both an ordinary dynamic page and `force-static` under the root loading boundary. The gallery now uses a finite `dev/[example]` route with `dynamicParams=false` and no generated production paths, plus a page-level development guard. Development availability and production exclusion are tested separately; the result belongs in Stage 7, not an assumption about `notFound()`.
- Mobile shell now observes the actual bottom-navigation height, including safe area/text growth, and uses it for content and scroll clearance. Observer/listener cleanup and public-route transitions are covered by component tests. The original full-page screenshot is not reclassified as a proven device bug; the browser harness now checks final content/control geometry at 320/390/768px and 100%/200% text, with viewport-only bottom captures.
- React best-practices review: direct imports, generated stable control IDs, native controls where possible, no new provider/model/network calls, no global mutable account state, and no per-frame React updates. Review did not authorize a dependency upgrade or a shared-package edit.

## Stage 7 — shell hardening evidence and handoff (2026-10-23)

**W01 remains open. This is an additional shell/primitives increment, not completion of W03/W05/W06/W07/W10.** Console contract v1 is unchanged. All status changes for this work are confined to this file.

| Check | Result | Actual evidence / limits |
|---|---|---|
| Consumer and console optimized builds + TypeScript | `passed` | Consumer Next `14.0.4`, console Next `14.1.0`, React/React DOM `18.2.0`, Node `24.19.0`, TypeScript `5.3.3`, Tailwind `3.4.0`, Radix Dialog `1.0.5`. These are isolated validation installs, not a new supported workspace tuple. npm warns that both old Next versions have known security issues; release remains blocked on the upgrade. |
| Component behaviors, exact money, evidence labels | `passed` | `node --test brandme-frontend/lib/testing/verify-ui.mjs`: **13 passed, 0 failed**. JSDOM `26.1.0`, Testing Library React `16.1.0`, DOM `10.4.0`, user-event `14.6.1`; validation-only. Covers pending actions, associated labels/errors, keyboard switch/slider/tabs, dialog/drawer focus and Escape, null-vs-neutral, fractional/invalid money rejection, 18-digit amounts, 0/2/3 currency decimals, missing currency metadata, label fidelity, toast focus, and navigation observer lifecycle. **Simulated DOM, not browser/visual/device evidence.** An initial harness-only failure (`self` missing for Next Link) was fixed by supplying the browser global in the test environment; app code was not weakened. |
| Production HTTP shell regression | `passed` | `node brandme-frontend/lib/testing/verify-shell-http.mjs`: 14 consumer routes plus console root return 200 with single main/h1; both token themes delivered; GET/HEAD redirects remain 307; all 10 font deliveries succeed; console uses runtime `sandbox environment`; privacy entry remains honestly not connected. Ephemeral loopback servers stop in `finally`. No domain writes. |
| Development gallery / production exclusion | `passed` | Final `/dev/components` returns 200 under `next dev` with one main/h1 and fixture disclosure. Same source under `next build`/`next start` returns **HTTP 404** without gallery content. Two earlier page-config attempts returned streamed 200/not-found; the finite route manifest corrected this. Stale generated `.next/types` from the moved route initially failed a build; a clean generated-output rebuild passed. |
| Code quality and lane scope | `passed` | `git diff --check`, TS checks/builds, syntax checks for browser harnesses; no dependency manifests, lockfile, shared packages, backend files, protected spatial routes/features, design contracts or console domain pages changed. Existing consumer/console APIs and legacy pages remain untouched. No new runtime dependencies. |
| New browser screenshots, axe, 320px layout and large-text geometry | `not_run` on this increment | `verify-shell.mjs` now adds 18 bottom-of-viewport captures across 3 routes × 3 widths × 2 text sizes, actual nav-height/clearance checks, and last-control visibility. `verify-controls.mjs` adds gallery light/dark/axe/keyboard/reflow checks at 320/390/768/1440 widths. Authored and syntax-checked only. No fresh Chromium launch/escalation attempted after the earlier automatic policy denial. Stage 4 remains historical evidence for `472c404`, not an automatic pass for changed code. |
| Real device / screen reader / human visual review | `not_run` | Needed for current shell and new controls; JSDOM focus tests do not substitute for assistive-technology checks. |
| Onboarding, migration, persona API, social decisions, trusted checkout, My Data | `not_run` | Their actual integrations remain pending. Gallery sliders, prices and evidence labels are primitives, not those domain journeys. |

### Re-run commands and next assignment

With validation dependencies installed externally (or by the eventual approved workspace), run from the repository root:

```bash
BRANDME_TEST_PACKAGE_JSON=/absolute/path/to/validation/package.json \
node --test brandme-frontend/lib/testing/verify-ui.mjs

# After both app production builds:
node brandme-frontend/lib/testing/verify-shell-http.mjs

# Browser-capable approved runner; both production servers running:
BRANDME_TEST_PACKAGE_JSON=/absolute/path/to/validation/package.json \
BRANDME_CONSUMER_URL=http://127.0.0.1:3000 \
BRANDME_CONSOLE_URL=http://127.0.0.1:3002 \
BRANDME_EVIDENCE_DIR=/absolute/path/to/shell-evidence \
node brandme-frontend/lib/testing/verify-shell.mjs

# Separate development consumer server for the non-production gallery:
BRANDME_TEST_PACKAGE_JSON=/absolute/path/to/validation/package.json \
BRANDME_CONSUMER_URL=http://127.0.0.1:3000 \
BRANDME_EVIDENCE_DIR=/absolute/path/to/controls-evidence \
node brandme-frontend/lib/testing/verify-controls.mjs
```

Next integration assignment: consume foundation's published token CSS/client exports once its commits and approved manifest/toolchain changes are brought into this branch; keep package sources read-only. Then implement W03 against the mounted persona and guest-migration APIs, not a second local imitation of domain persistence. Before claiming W01, run the two browser suites in an approved runtime, inspect the actual viewport-bottom captures and gallery screenshots, fix findings, and add real-device/screen-reader evidence. Existing token/font/CSP and spatial-component interface requests above remain open unless satisfied by an integrated authoritative export.

## Stage 8 — published shell contract and consumer completion work (2026-10-23)

Founder handoff: `Consumer UI — Astra.md`. Starting HEAD `da2f430e`.
Scope includes W01 publication, first review-ready PR, journey UI, a11y/visual CI,
and same-origin gateway integration. Dev/test credentials are authorized; no
production credentials, customer data, real purchases or messages are needed.

### Console shell layout contract 1.1.0 — public code artifact

**Stable import:** `@/components/console-contract` in `brandme-console`.
Exports: `ConsolePageHeader`, `ConsolePageHeaderProps`,
`CONSOLE_SHELL_CONTRACT` (literal version `1.1.0`, landmark ID, CSS helpers,
reserved navigation paths and legacy exclusions). Source metadata lives in
`brandme-console/lib/console-contract.ts`; the live shell and navigation consume
it. The existing `@/components/console-page-header` import remains compatible.

```tsx
import { ConsolePageHeader, CONSOLE_SHELL_CONTRACT } from '@/components/console-contract'

export default function DomainPage() {
  // Authorize domain reads separately; the contract confers no permission.
  return <section data-shell-contract={CONSOLE_SHELL_CONTRACT.version}>
    <ConsolePageHeader eyebrow="Operations" title="Domain queue"
      description="Authorized records and their current state." />
    {/* Domain content; no nested main, global navigation, html or body. */}
  </section>
}
```

Contract invariants remain the eight v1 rules in Stage 1. In particular: shell
owns the skip link, navigation and single `main#console-content`; the page owns
its single h1, loading/error/denied/empty/stale states and server authorization.
Wide tables must use a labeled, keyboard-focusable `console-table-region`.
No server secrets, inferred role or operator record may enter shell props.
Dark/light tokens, keyboard dialog behavior and legacy pass-through are part
of the contract. Domain subtrees stay owned by their backend lanes.

**Changelog:**
- `1.0.0` (2026-10-05): prose contract and compatible header implementation.
- `1.1.0` (2026-10-23): first versioned public code entry point and exported props;
  shared metadata drives shell/nav; correct reward-dispute nav to
  `/rewards-disputes` (PD-19, the backend lane's actual owned route).

Semver: landmark/ownership or required-prop breaks require a major version;
additive exports/slots a minor; compatible fixes a patch. Record future changes
here and update the code version in the same commit. Local domain headers remain
valid under v1's optional-header rule until the founder's enforce/retire decision.
Recommendation: adopt this import when integrating each domain, retain existing
content and authorization, then retire duplicate header implementations.

**W01 contract publication: delivered. W01 release acceptance: still open** until
the supported framework/token integration and current browser checks pass;
real-device and screen-reader evidence must remain separately identified.

### Integration reconciliation

The latest consumer-domain work is on `claude/opus-consumer-domains-1csp2g`
(`dafd3b1`), ahead of its bench branch. Its persona, wardrobe, social and rewards
gateway routers explicitly ship **unmounted**. The current main and W11 gateway
do not mount them; foundation sessions also lack their full scopes. The frontend
must not report those data sources live merely because a router file exists.
Build against the published interfaces, use real session transport where mounted,
and retain explicit unconfigured/denied/error states. Backend mount and service
transport remain an integration dependency; no backend-owned source is edited.

### Credential manifest

No credential created at this checkpoint. Any later dev/test entry must record
name, scope, storage location and date, never its value. Never commit session
cookies, CSRF tokens, provider keys, test secrets or unredacted request logs.

## Stage 9 — foundation consumption and first live-client slice (2026-10-23)

- Published state before this checkpoint: `264b6a0`, PR [#56](https://github.com/brandmeonline/Brand-Me-Labs/pull/56), open and review-ready against the lane's specified base. Module Regression [39982719676](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/39982719676) passed on that exact SHA; the PR has not merged.
- Consume foundation commit `67327e45ed816bd76bc20ed1e2eb694009923530` as a merge parent. Backend, migrations and shared packages are inherited unchanged from that parent. Merge resolutions retain the registered consumer workspace, pnpm `10.34.6`, foundation Node `.nvmrc`, and current security overrides. Both UI apps adopt main's patched Next/eslint-config-next `15.5.28` and React `18.3.1`. This supersedes the older proposed framework tuple; no shared package or backend implementation was edited by this lane.
- Both shells load the generated design-system CSS; the consumer alias adapter reads its exported tokens instead of the spec JSON. Theme/motion attributes support the package and the existing shell contract. The generated API client handles `/me`; consumer-specific DTOs temporarily describe the newer, ungenerated domain fields. No generated source is modified.
- New same-origin `/api/v1/**` BFF permits explicit consumer roots only, forwards only the session cookie and approved headers, checks mutation origin/CSRF, rejects arbitrary upstreams/redirects/HTML/oversize payloads, refuses development sign-in in production, and never retries an uncertain write. The browser serializes CSRF refresh/writes, retains no access tokens, aborts obsolete reads and clears data/queued writes on account changes.
- `/start`: resumable device guest choices, six original fictional outfit illustrations, editable first three axes, optional learning, and server guest migration with a stable namespace/key. `/me/style`: all 12 declared/inferred/effective axes, locks, preview revisions, constraints, evidence suppression, inference reset, current-session snapshots/restore and context/adaptation controls. `/circle`: relationships, server-timed five-minute decisions, yes/pass/alternative response and close/result states. `/rewards`: service balances, badges/evidence, history, benefit confirmation and reservation state. `/me/connections`: real session status, explicitly simulated development sign-in, guest migration and sign-out. These are API clients, **not live-service acceptance evidence** yet.
- React review fixed snapshot-handle loss on profile refresh, cancellation of queued writes after account changes, and programmatic confirmation-dialog focus restoration.
- Local checks: **23/23 passed** (13 component behavior + 10 BFF security cases), frontend TypeScript passed, both optimized Next 15 builds passed. There is no local current browser pass: Chromium download did not produce a usable archive. Earlier browser evidence stays tied to its original commit.
- Added `Consumer UI` CI: exact dependency install, component/BFF tests, both optimized builds, pinned Chromium, shell/control keyboard/axe/reflow checks at 320/390/768/1440 widths and light/dark screenshot artifacts. Visual comparison uses pixelmatch and reviewed baseline files; its initial capture is explicitly `NOT_RUN` until the runner images are inspected and committed as baselines. A captured screenshot is not a visual-regression pass.
- Remaining: run CI on this checkpoint; inspect its screenshots; complete guest corruption/retry checks and ordinary-money budget entry; mount unchanged domain sources in an isolated emulator-only development composition; execute real session/persona/wardrobe/social/rewards journeys; finish discovery/assistant/checkout/My Data and remaining route coverage. Production integration, complete W03/W05/W06/W07/W10 acceptance and W01 visual release acceptance are **not claimed**.
- Credential manifest: no new credential has been created. The future emulator-only composition will generate a short-lived internal assertion key in runtime environment memory, never in source or artifacts.

### Stage 9 follow-up — current runner and development composition

- Foundation and Module Regression both passed on `4617097405027f40af1cd79049e93a479a5d32ac`. The first UI workflow definition failed before execution due to an unavailable expression context; the artifact path fix is that commit.
- Current Chromium shell execution: 13 checks passed, one failed (desktop button contrast during a theme transition). Removed foreground/background interpolation so the semantic pair changes together. Screenshot collection now uses a non-hidden directory; the prior upload step excluded the hidden directory. These fixes require the next run; no browser acceptance is claimed yet.
- Development composition lives only in owned `lib/testing/`: pinned unchanged domain source `dafd3b169da777ec3e3a7fc2c3f0cab573358e2b`, actual foundation IdentityStore/session middleware, real consumer routers/services, all migrations, and real outbox/inbox reward settlement against Spanner emulator `1.5.28`. It binds loopback only, refuses non-development/production contexts, authenticates internal requests with short-lived method/path-bound assertions and replay protection, and grants only explicit simulated first-party member scopes. This is a development integration, not a production mount or identity policy.
- The browser journey uses two isolated sessions and no intercepted requests: guest migration/replay, twelve axes/persistence/isolation, actual wardrobe intake rendered on Today, five-minute decision/Pass/close, settled rewards/no duplicate migration credits, block revocation, sign-out and axe checks. Authored and syntax/type-checked; execution pending CI.
- Credential manifest entry: `BRANDME_DEV_ASSERTION_KEY`; scope: local emulator-only internal principal assertions, one CI/dev process lifetime; storage: supervisor/child environment memory, randomly generated per launch; date: 2026-10-23. It is never logged, committed, retained in browser storage or included in artifacts. No production/provider credential created.
- At `57403ab`, Foundation and Module Regression passed. The live composition started successfully with the actual migrated emulator and gateway. Its browser sign-in was rejected by the BFF origin check because the explicit public origin was missing from the runner configuration; the next checkpoint sets that origin, preserving the CSRF check. Browser journey acceptance remains pending.
- Follow-up hardening: budget entry uses ordinary currency decimals with exact string conversion and validation; excluded-list typing preserves the draft; corrupt guest storage is rejected; interrupted guest migration retains the exact payload/key for retry and preserves newer local edits. Local component/security suite now **25/25 passed**, with frontend TypeScript passed. UI push/PR runs share a concurrency group to avoid duplicate browser runners.

### Stage 10 — discovery, inbox and browser corrections (2026-10-23)

- Published starting point `9c2bb10614c4409d74d2b31664ee115422e909da`; PR #56 remains open and unmerged. Foundation [39987733955](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/39987733955) and Module Regression [39987721106](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/39987721106) passed on that SHA. Consumer UI [39987733828](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/39987733828) passed all 14 shell checks; the controls gallery failed its modal focus assertion, and the live-domain job was still installing dependencies at this checkpoint. Visual comparison remains explicitly NOT_RUN.
- Display preferences now wait for initialization and compose rapid updates against the latest snapshot; a regression test verifies persistence through a fresh provider mount. Browser checks wait for the actual initialized state and modal autofocus before keyboard traversal. Diagnostic focus assertions retain the failing element. Both apps hide the development indicator in evidence captures; unavailable-service notices have readable spacing and grouping.
- Discover and product detail consume the current commerce interface at `3823ea5dd5b31a5abf68a44c94054ad0a4801f66`: authorized catalog observations, exact observed prices, freshness, provider/simulation disclosure, unavailable-provider states and variants. Provider text is rendered as text. Composite provider/product IDs are admitted only on the catalog detail route and URL-encoded. No fabricated product-to-wardrobe mapping or purchase action is exposed: the published detail response does not supply those capabilities. The BFF also explicitly rejects the nested commerce operator queue.
- Inbox consumes actual paginated notifications, permits explicit mark-as-read, and maps only known subject-reference types to local destinations. The real domain browser journey now covers this command and audits Inbox, with failure screenshots and completed-check diagnostics.
- Local component/security suite **27/27 passed**, and frontend TypeScript passed before this checkpoint. These are not a substitute for the pending Chromium/live-domain execution. No new credential was created. Production integration, reviewed visual baselines, assistant/checkout/My Data and the remaining route coverage are still open.
