# Lane brief: astra-spatial-ar

**Bench:** Astra (Codex) · **Branch:** `bench/astra-spatial-ar-20261005`
**Base:** `docs/brandme-full-experience-2026-10-05` · **Spec:** `docs/design/brandme/` + `contracts/`
**Work packages:** W04-UI/assets (wardrobe spatial UI + real 3D assets), W08-UI (AR + try-on)
**Position in merge order:** After `opus-foundation` merges (needs `packages/design-system` tokens + generated API clients). Independent of Lane 5 (disjoint routes/features).

## What you are building
The spatial heart of the product: three real 3D closet environments, the garment asset library, the signature add-to-closet animation, and the honest AR/try-on capability ladder. Read chapters 02, 01, 06 and the root `CLAUDE.md` first. Chapter 02's geometry, animation timelines, and scene budgets are implementation requirements.

## You own exclusively (no other lane may touch these)
- `brandme-frontend/features/{spatial,closet}/`
- `brandme-frontend/app/{closet,try,add,style}/**`
- `brandme-frontend/public/demo/` — CREATE the real room/garment GLBs (+USDZ where required), thumbnails, manifests, and rights records. These are files you must create per `contracts/demo-scenario.json` — they are not supplied. Procedural creation/export is acceptable if it passes visual review; runtime primitive boxes are NOT the final garment library.
- Asset pipeline scripts + `pnpm assets:validate` implementation (manifests, licenses, dimensions, compression, loadability, payload budgets)
- `tests/e2e/spatial*.{spec.ts,py}`

## Read-only for you (import, never modify)
`brandme-frontend/app/layout.tsx`, `brandme-frontend/app/globals.css`, `brandme-frontend/{lib,components}/` (Lane 5), `packages/design-system`, `packages/contracts` (generated clients).

## Forbidden
Other `features/*`, any `brandme_core/`, `brandme-data/`, `brandme-chain/`, `brandme-gateway/` files. `docs/design/brandme/**`, `contracts/**`.

## Exit evidence (from ch.06 §2, W04-UI + W08-UI)
- All three room environments (Walnut Atelier, Limestone Gallery, Garden Studio) load with real assets and look intentional from their actual cameras — not just a modeling viewport; dimensions, pivots, collision bounds, and fidelity recorded
- Signature add-to-closet animation (ch.02 timeline) tied to a REAL committed item, with success/retry/undo paths and a reduced-motion equivalent
- Placement survives refresh and theme change; semantic slot remapping; keyboard placement; named views; accessible 2D equivalent (Simple View) with full functionality
- 500-item wardrobe virtualized with bounded rendered scene complexity; overflow handling
- Capability ladder, each honestly gated: 3D inspection → room placement → supported live overlay → photo try-on → (calibrated fit REMAINS UNAVAILABLE unless a real measurement pipeline validates it — never relabel generative imagery)
- model-viewer with actual GLB/USDZ assets and tested platform handoffs; MediaPipe worker lifecycle with camera permission/error/cleanup states; camera stops on exit; no unconsented frame uploads; unsaved media expiry demonstrable; saved media deletion works
- Honest fallback on unsupported devices / no-WebGL: usable 2D, complete explanation states where provider credentials are absent
- Every preview carries its fidelity label; device-loss/context-loss yields usable 2D

## Cross-lane note
Build the visual outfit editor as an embeddable component that Lane 5 (`features/outfits`) imports read-only. Confirm the component interface via status files.

## Status protocol
Record status ONLY in this file. Propose deviations here. Publish the outfit-editor component interface here early.

## Global rules (all lanes)
Never edit another lane's owned files. Never edit `docs/design/brandme/**` or `contracts/**`. No `latest` tags — pin everything. Asset rights manifests required for every shipped asset.

## Execution — 2026-10-05

### Stage 1 — inspection and interface (completed)
- Baseline: `00c9cfc`; isolated worktree on `bench/astra-spatial-ar-20261005`.
- Read this brief first, then the design package and fixture/token contracts. No `AGENTS.md` found. Existing frontend is Next 14 / React 18 and outside the workspace; `packages/design-system` and `packages/contracts` do not exist on this branch.
- Lane boundaries are unchanged. Only root asset-command script entries are proposed outside the owned feature/routes/assets/tests paths, under the explicit asset-pipeline assignment.
- Asset reconciliation: create all six fixture products (overshirt, trousers, dress, jacket, sneaker, bag), plus the chapter-02 tee and knit layer, plus a P0 image-only item. Procedural originals are P1 / **Approximate 3D**, not the fixture's aspirational P2 target. No body binding or calibrated-fit claim.
- Foundation integration request: React 19 + R3F 9, Three, model-viewer and Motion must join the foundation-owned frontend dependency tuple. This lane carries an isolated pinned feature/tool manifest for reproducible asset and component checks; it does not edit the frontend/workspace manifests or root layout/styles.
- Persistence boundary: a scoped `ClosetRepository` adapter with explicit local-guest demo implementation until the generated domain client is available. Local guest commits are durable on this browser only; no backend/cross-device claims or reward writes. Production must inject the real adapter.

### Consumer lane import contract — v1
Import named `OutfitEditor` and its types from `@/features/spatial/OutfitEditor` (client component). It owns no route, navigation, data fetching, social action, or global style.

```ts
type OutfitEditorItem = {
  id: string; title: string; category: string;
  posterUrl: string; fidelity: 'P0' | 'P1' | 'P2' | 'P3' | 'P4';
};
type OutfitComposition = {
  itemIds: string[]; title: string; occasion: string; notes: string;
};
type OutfitEditorProps = {
  items: readonly OutfitEditorItem[];
  value: OutfitComposition;
  onChange: (next: OutfitComposition) => void;
  onSave?: (next: OutfitComposition) => Promise<void>;
  readOnly?: boolean;
  reducedMotion?: boolean;
};
```

`onSave` resolves only after the host's authoritative save; rejections remain visible and retryable. The host owns version/conflict policy, outfits, circle sharing and persisted IDs. Missing/deleted item references remain visible for deliberate removal. Every preview carries the fidelity label. DOM/keyboard editing is complete without WebGL.

### Current external evidence gates
No real iOS/Android device is connected. Quick Look / Scene Viewer / WebXR handoff evidence cannot be claimed from desktop simulation. Live overlay remains gated until local model files and a supported worker/device pass checks. Photo processing remains unconfigured without an approved provider, consent/retention contract and backend. Calibrated fit remains unavailable.

### Stage 2 — original asset pipeline (implemented; structural check passed)
- `scripts/assets/generate.mjs` creates original lofted garment geometry, modeled garment details, furniture/rooms, original embedded PBR microtextures, portable GLBs, gzip sidecars, explicit USDZs, manifests and rights records. No runtime box garment library or third-party commercial visual assets.
- All three required rooms, all six contract products, the additional tee/knit, and P0 image-only fallback exist. `scripts/assets/review.mjs` loads each GLB through Three in Chromium and renders transparent garment posters and rooms from the specified actual camera. Native USDZ microtextures are omitted and declared; base colors/geometry remain.
- `node scripts/assets/validate.mjs`: **passed** — 36 exact contract paths, 12 manifests; glTF structural validation, hashes/sizes, local-only references, dimensions/bounds, license records, gzip round trips, USDZ storage/alignment, and estimated scene/payload limits.
- First camera inspection completed for Walnut Atelier and overshirt; remaining room/mobile visual review is underway. Structural checks do not equal native AR or physical-device performance evidence.
- Reproduce tool installation with `pnpm --dir scripts/assets install --ignore-workspace --ignore-scripts`; use direct `node scripts/assets/...` commands to avoid pnpm 11 automatically reconciling the foundation-owned workspace. Root command aliases include `assets:generate`, `assets:review`, `assets:validate`. Foundation root lockfile/workspace remain unchanged.

### Stage 3 — component and guest behavior scaffold (implemented; verification underway)
- Added owned routes `/closet`, `/closet/settings`, `/closet/items/[itemId]`, `/add`, `/style`, `/style/outfits/[outfitId]`, `/try/[itemId]` without editing layout, globals, lib, components, design contracts, backend or other features.
- React 19/R3F 9 lazy scene island, original asset loading/disposal, named views, entry/standard/desktop bounds, demand rendering, quality downgrade, context-loss fallback; virtualized DOM wardrobe; item inspector and keyboard placement; deterministic theme remapping and Unplaced tray.
- Guest IndexedDB transaction adapter serializes optimistic version checks and idempotency across tabs, with item+placement creation and actual inverse Undo. Explicit guest/device-only label; no reward or ownership assertions. Shared authenticated adapter is still an integration gate.
- Embeddable `OutfitEditor` matches v1 above; host controls persistence and proposals. Own style route has separately labeled device-only guest persistence.
- Model-viewer loads actual assets lazily. Native AR stays gated for missing device evidence; local camera/worker lifecycle is implemented with pose model gate; provider-less photo try-on explains consent/retention/setup without an upload surface; calibrated fit disabled.
- Targeted TypeScript check: **passed** using the pinned lane tuple. This is not the integrated Next build. `scripts/assets/dev.mjs` is a development-only component verification harness importing the real feature code, not another shipped application.
- Agent-browser 0.38.2 daemon failed to start twice with no diagnostic output; using the installed Playwright Chromium runner for the same visual and behavioral checks. The final executed browser results are recorded below.


### Stage 4 — verified scaffold and handoff (2026-10-05)

**Delivery level:** spatial/asset scaffold with working local guest journeys. This is not a claim that the entire W04/W08 exit gate or integrated application is complete.

#### Executed evidence

| Check | Result | Evidence / boundary |
|---|---|---|
| Asset validation | **passed** | `scripts/assets/evidence/asset-validation.json`: 36 required paths, 12 manifests; actual glTF loads, USDZ package checks, rights, hashes and budgets |
| Pinned component type check | **passed** | `node scripts/assets/node_modules/typescript/bin/tsc -p scripts/assets/tsconfig.json`; integrated Next build is blocked on foundation |
| Browser scenarios | **17 passed** | `scripts/assets/evidence/browser-results.json`; isolated real component harness, Chromium software WebGL, not a live API or physical-device test |
| Three room cameras | **passed, agent visual review** | `public/demo/rooms/*/poster.webp` and `scripts/assets/evidence/runs/*/`: Walnut, Limestone, Garden, actual specified perspective camera |
| Responsive component views | **passed** | 320/390/768/1440 px screenshots; no document overflow. This does not verify the other lane's shell or screen-reader research |
| Add / failure / retry / Undo / reduced motion | **passed for local guest** | Creation is an IndexedDB transaction before motion; expected-version inverse removes the actual record; `scripts/assets/evidence/signature-placement.webm` |
| Placement / theme / reload | **passed for local guest** | Keyboard move and revision persist; absent semantic destinations go to Unplaced, with item identity retained |
| 500-item wardrobe | **passed** | Bounded DOM rows and rendered capsule, End-key access to item 500, search and inspector |
| WebGL unavailable / context loss | **passed** | 2D controls continue to move real guest records; room-loading poster avoids a blank initial mobile frame |
| model-viewer | **passed for 3D load; native blocked** | Actual GLB loads, explicit USDZ and fixed-scale handoff attributes. Native launch stays disabled without device evidence |
| Camera lifecycle | **passed with controlled test streams / worker double** | Late permission result is stopped; active stream/worker stop on backgrounding. No pose accuracy or real camera/device claim |
| Preview privacy | **passed locally** | No provider uploads exposed without configuration; 24h unsaved media purge and saved-media deletion tested in private guest media store |
| Calibrated fit | **correctly unavailable** | No measurement/material pipeline; no relabeling of approximate or generated imagery |

Observed staged-room rendering: Walnut **29,168 triangles / 32 draw calls**, Limestone **20,132 / 31**, Garden **16,176 / 23** (`scripts/assets/camera-measurements.json`). Low garment GLBs are **104,856–265,428 bytes**. Conservative room + twelve worst-case compressed garment payloads are **812,028–870,615 bytes**. These are artifact/renderer measurements, not real-device frame-time, thermal or network performance results.

The first run exposed a real context-loss listener bug when replacing rooms; fixed by preserving the canvas and removing the listener on unmount. The remaining two failing assertions used ambiguous select-option/label selectors; corrected without weakening their intended outcomes. Final suite is green. A dependency peer mismatch was also resolved: model-viewer 4.2.0 and Three 0.182.0 now form a compatible pinned pair.

#### Exact tool tuple and reproduction

- Node `24.19.0`; asset-tool pnpm `11.25.0` in its isolated manifest/lock; root currently declares pnpm `8.15.0` (foundation-owned).
- React / React DOM `19.1.1`, R3F `9.4.0`, Three / Three types `0.182.0`, Motion `12.23.24`, model-viewer `4.2.0`, MediaPipe `0.10.22-rc.20250304` (scaffold only; model/device gate stays closed), TypeScript `5.9.3`, Vite `7.1.7`, Playwright `1.56.1`, Chromium `141.0.7390.37`, gltf-validator `2.0.0-dev.3.10`.
- Compatibility checked against package metadata and the official R3F installation, model-viewer AR, and MediaPipe worker documentation on 2026-10-05. Foundation should own the eventual consolidated supported tuple.

```bash
pnpm --dir scripts/assets install --ignore-workspace --ignore-scripts
node scripts/assets/prepare-checks.mjs
node scripts/assets/node_modules/@playwright/test/cli.js install chromium
node scripts/assets/node_modules/typescript/bin/tsc -p scripts/assets/tsconfig.json
node scripts/assets/validate.mjs
node scripts/assets/node_modules/@playwright/test/cli.js test -c scripts/assets/playwright.config.mjs
node scripts/assets/dev.mjs
# Component harness: http://127.0.0.1:4178/closet
# Optional regeneration: node scripts/assets/generate.mjs && node scripts/assets/review.mjs
```

`pnpm assets:validate` was verified through the root's declared manager using `npx --yes pnpm@8.15.0 assets:validate`. The environment's globally installed pnpm 11 tries to reconcile the older root workspace first and stops on unrelated ignored build scripts. No build approvals were bypassed, and its incidental root lock/workspace edits were restored. Root asset command entries are the only shared package edits. The temporary frontend `node_modules` link is generated/ignored and must be removed before foundation installs the real frontend workspace dependencies.

#### Confirmed consumer interface additions

- `OutfitEditor` v1 above is implemented at the stated path. The consumer owns `onSave` authority, version conflicts, proposals and sharing. Its `reducedMotion` prop accepts the shell's canonical preference; OS reduction also wins in the spatial scene through `useMotionPreference`.
- `RoomViewport` from `@/features/spatial/RoomViewport` is a lazy scene wrapper with `{ room, items, selectedId?, onSelect, onFallback, namedView, reducedMotion, simpleView }`; types are exported from `features/spatial/types.ts`. It requires neither navigation nor global CSS. Every item remains available through a host-provided DOM list.
- Live/sandbox route modes refuse the guest adapter via `SpatialModeGate` until a real wardrobe repository is injected. `NEXT_PUBLIC_BRANDME_MODE=production` or `sandbox` displays the explicit connection gate. No fixture fallback is presented as live data.

#### Remaining work — do not mark these complete

1. **Foundation integration:** supported Next/React migration, design-system exports, shared preference hook, generated API clients, authenticated wardrobe/outfit repositories, account migration/export/deletion integration, cross-device persistence and integrated build. Consume these read-only when supplied; keep the explicit demo boundary.
2. **Spatial interaction/polish, updated after Stage 11:** physical collision/packing refinement beyond the six nonoverlapping grounded folded destinations, direct manipulation inside the 3D canvas (DOM image drag and touch entry are implemented), and 200% zoom/manual screen-reader/physical-touch review. Stage 11 hardens keyboard placement and focus with native-selector and pending-save coverage; it does not close the manual accessibility gate. Six authored folded-display variants are implemented and verified. The current editor is an accessible visual composition using original garment posters; a composite 3D outfit preview remains future work. Stage 6 implements saved cameras, orbit debounce, room/selection motion, prefetch/pending destinations, search dimming and the multi-select capsule tray.
3. **Asset finishing:** richer baked grounding/AO and entry-tier lighting, optional measured KTX2/geometry compression, neutral turntable still sets, rigged garments, and a general quarantined upload/optimization pipeline. Current fixtures use embedded original PNG PBR maps and gzip transport with portable uncompressed GLBs. Source is reproducible from the generator; a private source-archive ingestion service is not implemented here.
4. **Native AR:** actual supported iOS/Android/WebXR hardware tests and authoritative capability-registry activation; current disabled handoffs must not be switched on merely because desktop emulation passes.
5. **Live pose:** rights-reviewed locally hosted model/WASM files, approved pinned stable runtime, confidence/multiple-person/occlusion validation across bodies and lighting. Lifecycle scaffolding is tested; pose inference is not represented as verified.
6. **Photo processing:** approved provider/region/retention disclosure, real consent/job/spend/cancel/delete APIs and end-to-end generated output tests. Local media-store tests are not provider-deletion proof. Calibrated fit remains unavailable.

| Release dimension | Current assessment |
|---|---|
| Experience complete | **No** — working guest scaffold; integration and listed interactions remain |
| Integration verified | **No** — foundation/domain clients and physical AR/provider evidence absent |
| Production approved | **No** — no deployment or live capability activation performed |

### Stage 5 — publication checkpoint (2026-10-07)

- Published implementation commit `7bea00e682499cddfc4b9bbc839e73643c46257c` to `bench/astra-spatial-ar-20261005`. No merge, PR, deployment, or live capability activation was performed.
- Terminal push had no configured GitHub credentials. The connected GitHub integration published the reviewed Git blobs after recovering an interrupted upload; every returned blob hash was checked. Remote tree `dc588413725622d29bb67adb689a95d668a92160` exactly matches the tested local implementation commit `9bfb2c2`.
- Fetched the remote commit and verified zero file differences before aligning the local branch. The 17 browser scenarios and asset/type evidence above were executed on 2026-10-05; publication recovery did not change implementation code or claim new device coverage.
- The scaffold is available for cross-lane integration. All remaining work and the three **No** release assessments above remain in effect.

### Stage 6 — continued implementation (2026-10-08)

- Draft PR **#36**: https://github.com/brandmeonline/Brand-Me-Labs/pull/36, targeting the specified design-contract base. GitHub's completed mergeability calculation reports no merge conflict.
- Read the current foundation bench (`67327e4`) and consumer-domain status read-only. Foundation packages exist on the foundation bench, not this PR base; frontend remains Next 14/React 18 there. Do not copy or modify other lanes' work. The integration gates above remain open.
- Continuing the owned interactions: visible pending destination and asset prefetch, room transition, reduced-motion-safe camera control and local camera persistence, then focused browser regression coverage. PR remains draft throughout.


Implemented in this continuation:
- Prefetch the selected original low-LOD asset; show a destination placeholder throughout an outstanding add command; lock the reviewed inputs while saving. The real committed response still starts the 900ms signature and its ten-second inverse Undo. Flight coordinates now use the exact fixed room-camera projection rather than an approximate screen offset. Intake cameras remain fixed during this interaction.
- Preserve the canvas while fading the old room out for 225ms, replacing the environment and fading in for 225ms. Reduced motion swaps directly. Interrupted/reversed transitions restore visibility.
- Restrained 220ms selected-item camera focus, interrupted by orbit input. Named views remain usable under reduced motion and switch immediately. Orbit position is device-local with a one-second idle debounce; up to eight named views per room can be saved, restored and removed. Storage denial never blocks normal camera controls.
- Drag an item image from the DOM wardrobe onto an eligible, unoccupied named destination to commit placement. Touch pointer hold enters placement after 350ms; movement before the threshold cancels the hold and leaves scrolling alone. Keyboard move/save/cancel remains available. Physical-device touch review is still open.
- Search dims nonmatching scene garments instead of erasing room context; a selected item is prioritized within the bounded rendered capsule. Per-instance material clones preserve shared source materials and are disposed on release. Image-only items now render as labeled photo-display representations as well as remaining available through DOM rows.
- Multi-select items across filters and save their actual IDs into a device-local capsule in the same revision/idempotency transaction adapter. Capsule membership survives refresh; removing a capsule preserves items and their statuses. This does not create entitlements or ownership claims.

Consumer interface compatibility: `OutfitEditor` v1 is unchanged. `RoomViewport` adds optional `interactiveCamera`, `cameraRequest`, `onCameraPose`, `matchingIds` and `pendingPlacement`; existing consumers need no changes. Shared layout, global CSS, lib/components, backend, contracts and design documents remain unmodified.

### Stage 7 — verification and PR update (2026-10-08)

| Check | Result | Scope |
|---|---|---|
| Full browser regression | **28 passed, 0 failed/skipped/flaky** | `scripts/assets/evidence/browser-results.json`, 108.9 seconds, pinned Chromium 141; eleven new interaction scenarios plus the original seventeen |
| Final visual/capsule recheck | **5 passed** | Rechecked three real room cameras, 320/390/768 reflow and capsule persistence after correcting an oversized checkbox and unsupported plus glyph; 44px label hit targets retained |
| Isolated TypeScript | **passed** | Real owned components/routes; not an integrated Next build |
| Asset validation | **passed** | 36 contract paths and 12 manifests remain valid; no original binary asset changes |
| Placement video | **refreshed** | `scripts/assets/evidence/signature-placement.webm`, committed add, projected destination, settled state and actual inverse Undo |

The expanded suite caught a transition assertion that missed the short fade interval; it now records mutation order and elapsed time. A capsule dropdown lookup included option text; its exact accessible combobox name now drives the check. A rapid room reversal is tested to prevent a permanently hidden scene. No failed assertions were removed to declare the suite green.

Browser tooling required restoring the missing pinned Chromium cache in this resumed environment (the first run could not launch a browser). Here it was installed under `/workspace/scratch/83a30b4e4bb6/playwright-browsers`; prefix local commands with `PLAYWRIGHT_BROWSERS_PATH` pointing to that directory if using this cache. The normal install/reproduction commands above remain valid for a standard checkout.

PR **#36** remains draft. No other lane's files were changed, no PR was merged, and no deployment occurred. Foundation integration, physical-device AR/touch/performance, pose-model validation, photo-provider integration and the remaining explicitly listed polish are still open. Calibrated fit remains unavailable. The full W04/W08 lane and production readiness are **not** marked complete.

### Stage 8 — publication recovery and folded displays (2026-10-23)

- Re-read the lane brief, design requirements and fixture paths. Fresh checkout of the named branch at `7ccc0b4`; draft PR #36 is open against the specified docs base. Shared layout/styles, other lanes and contracts remain read-only.
- Workspace maintenance removed the unpublished local folded-display increment. The earlier 30-test result described in chat was local-only; its Git blob upload stopped before the branch update. It is **not** evidence for the published PR. Reconstructing the owned source and generating fresh artifacts/tests instead of claiming that interrupted publication succeeded.
- Existing scaffold and OutfitEditor v1 remain intact. Restoring six original folded variants, explicit grounded shelf destinations and safe migration of legacy local coordinates. Native AR/pose/photo/fit gates remain unchanged. New verification and publication evidence follows in this file.

Restored implementation:
- Six original folded cloth variants have layered curved surfaces, garment-specific collars/hems/ribs/creases and grounded pivots; no box garment library. They retain P1 / Approximate 3D and separate display revisions. Original hanging inspection/low-LOD GLBs and native USDZs are unchanged.
- Folded shelves now use three columns on each of two real surfaces. Added Limestone's missing shelf pair and versioned room manifests as `original-shelves-v2`. Slots retain their semantic IDs. Asset checks cover nonoverlapping bounds, and camera review raycasts against exported furniture at every destination.
- Scene loading/budget accounting and selected-asset prefetch use folded variants only on folded shelves. Guest read transactions migrate legacy shelf coordinates once, preserve item/capsule identity and increment versions; stale writes conflict. Full authenticated integration remains outside this local adapter.
- Added actual asset-load/refresh/theme coverage for six occupied shelves in all rooms, plus migration/idempotency/conflict coverage. OutfitEditor v1 is unchanged.
- Fresh pinned dependency install and type check pass. The Chromium download initially failed (bad archive/cache lock); installing the same pinned headless Chromium 141 in `/tmp/brandme-playwright-20261023` succeeded. Use `PLAYWRIGHT_BROWSERS_PATH` with that cache for this session. No dependency upgrades, lockfile changes or approval bypasses.

### Stage 9 — fresh verification and timing correction (2026-10-23)

- Fresh first regression run: 28 passed, 2 failed. The pending-save test queried storage after its fixed 1400ms delay elapsed; it now uses a development-harness release event, still executing the real guest transaction after the pending assertions. No production mocking or assertion removal.
- The second failure exposed a real transition issue under software-renderer load: both room timers could expire before React committed, skipping the fade-in phase. Each 225ms interval now starts after its phase commits. Reduced motion and reversal cancellation remain intact. Re-running the full suite before publication.
- Fresh structural asset validation passes: 36 required paths, 12 manifests, folded GLBs 377,572–711,640 bytes and 3,744–7,224 triangles. All 18 shelf destinations have raycast support from the actual exported furniture within 2mm; three room camera renders and six folded posters were visually inspected.
- Second run: 29 passed, 1 failed. Trace confirmed the 900ms flight was visible, but a subsequent attribute lookup began after it unmounted. The animation test now captures visibility and the committed item ID together through a preinstalled DOM observer, then retains the real storage and inverse Undo assertions. No production timing or timeout was extended.
- Final full run: **30 passed, 0 failed/skipped/flaky**, 221.0 seconds, pinned Chromium 141 on 2026-10-23. Fresh browser report and screenshots replace the prior run evidence. Isolated TypeScript and asset validation pass. Actual committed add/Undo, reduced motion, refresh/theme migration, 500-item virtualization, no-WebGL/context loss and local camera/media privacy checks are covered in the real-component guest harness, not an integrated Next/API build or physical-device AR test. The existing placement video remains the separately dated Stage 7 recording.
- React quality review kept lazy scene loading, demand rendering and effect cleanup intact; selected folded prefetch and transitions have explicit dependencies. OutfitEditor v1 and all native/provider/calibrated-fit gates are unchanged. Experience complete / integration verified / production approved remain **No**.

### Interruption-safe continuation protocol (2026-10-23)

- User reports repeated streaming interruptions. Publish small tested increments to the existing draft PR #36 before expanding scope; record the last verified remote commit and unfinished step here. A local commit or uploaded Git blob alone is not a published checkpoint.
- At resumption, read this file first, check the actual branch/PR head and local worktree, and continue the outstanding step rather than rebuilding completed work. Reuse verified content-addressed blobs safely, with bounded upload batches and an expected-head lease on the branch update. Never force-push or infer publication from chat progress.

### Stage 10 — published checkpoint (2026-10-23)

- Implementation **published and fetched back** as `5200b12740d38873eb71b05918315b676aa3fb2b` on `bench/astra-spatial-ar-20261005`. Tree `d0e28ad10f8f0cf13be9a19aadb8d61baa9bd1ed` exactly matches tested local commit `e11ecd20060c84fef406b0fe9fd019dd4fe8d089`; the fetched comparison has zero file differences. All 68 changed blobs were SHA-verified before the non-forced update from `7ccc0b4`.
- **PR #36 verified open and draft**, head `5200b12740d38873eb71b05918315b676aa3fb2b`, base `docs/brandme-full-experience-2026-10-05`; GitHub reports mergeable. Its description now includes folded displays, migration, sequential transition correction, fresh 30-test evidence and the remaining gates. This receipt is a documentation-only follow-up.
- No implementation upload remains outstanding. Resume future development from this published checkpoint, not from earlier interrupted uploads. Next owned work is broader collision/packing and manual accessibility/direct-canvas polish; foundation/domain integration and native-device/provider evidence remain explicit external gates. No merge, deployment or live capability activation occurred.

### Stage 11 — keyboard placement accessibility (2026-10-23)

- Resumed from verified remote head `6899d88202617808443bf7f72257643503c7c0e8`; PR #36 is open, draft and mergeable. Fresh isolated checkout matched that head and was clean. Completed assets and prior publication were reused without regeneration.
- Bounded milestone: stop placement shortcuts from intercepting native selectors, provide an explicitly focused keyboard navigator, restore focus after cancel/save, and keep pending-save announcements truthful. OutfitEditor v1 and external capability gates remain unchanged.
- Implemented a named, described keyboard navigator with explicit Arrow/Enter shortcuts. Native destination/slot selectors retain their own keyboard behavior. Move item focuses the navigator; cancel/success return focus only if it still belongs to the placement panel. A user who moves focus to Search during saving keeps it there. Selected destination tiles now expose their pressed state and existing selected styling.
- Submitted moves keep focusable Save/Cancel controls with truthful disabled/pending semantics. Escape cannot claim to cancel an outstanding transaction. A synchronous guard prevents duplicate submissions and selection reentry. A rejected move leaves the editor usable for correction and retry; no repository or stored-data schema changed.
- Six new tests inspect actual guest IndexedDB state and operation receipts. The first focused run passed five; its occupied-slot test accidentally selected displayed label 6 instead of stored value 6 (displayed slot 7). The trace showed a valid empty-slot move. The test now selects the explicit value and verifies it before submitting; no production behavior or failure assertion was weakened.
- Final full regression: **36 passed, 0 failed/skipped/flaky**, 342.9 seconds, pinned Chromium 141. This includes all 30 previous scenarios plus the six new keyboard/focus scenarios. Isolated TypeScript and asset validation pass (36 required paths, 12 manifests). This is real-component/local-guest evidence, not integrated Next/API or physical-device approval.
- Evidence: `scripts/assets/evidence/keyboard-placement-results.json` and `scripts/assets/evidence/keyboard-placement-390.png`. Existing Stage 9 reports/screenshots and all shipped assets remain unchanged. Automated reflow checks pass at 320/390/768px; the new 390px placement panel was visually inspected. No 200% zoom or manual screen-reader pass is claimed.
- Reproduce with the existing pinned install/prepare commands above, then `node scripts/assets/node_modules/@playwright/test/cli.js test -c scripts/assets/playwright.config.mjs`. This run used an equivalent temporary reporter/output override to retain the previous evidence, and `PLAYWRIGHT_BROWSERS_PATH=/tmp/brandme-spatial-playwright-20261023` for the pinned headless Chromium cache. The local server required loopback execution permission; no app/dependency settings or package locks changed. React quality review and independent diff review found no blocking issue in this bounded change.
- Verification and publication are complete; the fetched-tree confirmation is recorded in Stage 12 below.
- Precise next owned milestone after this publication: shoe-shelf collision admission using existing authored bounds. Start with a shared availability helper consumed by guest add/move and destination UI; reject adjacent overlapping new placements, permit a sufficiently separated slot or Unplaced, preserve existing guest layouts and item identity, and test failed-write immutability/idempotency/concurrency. A read-only review found that logical shoe slots are 0.1375m apart while the authored sneaker pair is about 0.386m wide, so distinct slot IDs alone do not establish physical clearance. Do not apply a generic rail AABB migration or regenerate assets as part of that increment.
- Foundation/Next/domain integration, 200% zoom/manual screen-reader/physical-touch review, native AR/device evidence, pose models and photo-provider APIs remain open. Calibrated fit remains unavailable. Experience complete / integration verified / production approved remain **No**.

### Stage 12 — keyboard milestone publication receipt (2026-10-23)

- Implementation **published and fetched back** as `cbdc30a716b744dbd61738717b9bc1d64321128c`, advancing the branch from `6899d88202617808443bf7f72257643503c7c0e8` with a non-forced expected-head check. Tree `ba747868a7731a5582955ff87be2cc2f2301c1f4` exactly matches tested local commit `86d3344b0dec7c6f18fd3fc4e6d6259352c32ba5`; fetched comparison has zero file differences.
- Verified PR **#36 open, draft and mergeable**, with implementation head `cbdc30a716b744dbd61738717b9bc1d64321128c` and the unchanged design-contract base. The PR description now includes the keyboard milestone, 36-test evidence and remaining gates. The local branch/worktree matched the fetched implementation and was clean before this documentation-only receipt.
- Terminal Git had no push credentials. The connected GitHub integration published the eight changed files using the existing base tree, and verified the screenshot blob and complete tree hashes. No completed asset was regenerated or re-uploaded. A PR-triggered workflow query returned no runs for this implementation SHA; no CI or integrated-application pass is claimed.
- **No implementation upload remains outstanding.** On resumption, inspect the actual branch head and read the precise shoe-shelf collision milestone in Stage 11 before changing code. Preserve any concurrent work and use small tested commits. OutfitEditor v1 and all external capability gates remain intact. No merge, deployment or live capability activation occurred.


### Stage 13 — workspace and CI toolchain repair (2026-10-23)

- User-directed toolchain repair supersedes feature work for this increment. Started from clean local/remote head `5acc8ee40c79b3b4be52357846eed513cbeb6d63`; PR #36 remains open and draft. The actual push-triggered Module Regression run [39961921035](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/39961921035) failed. Stage 12's PR-event-only query did not inspect these push runs.
- Applied PR #55's exact workflow change: remove `with: version: 8` under `pnpm/action-setup@v4`. Root `packageManager` is now the single pin. Mirrored consumer commit `da2f430e99c45d559a032414da20444ba6297d22`: pnpm `10.34.6`, Node engine `>=20.0.0 <25`; preserved all root asset scripts. `pnpm-workspace.yaml` exactly matches foundation `744d593be75bf892171631ccdb18785d7f0c6e27`, including the frontend/package registration, build allowlist and overrides. Regenerated the root v9 lockfile using pnpm install; all five workspace importers match their manifests.
- Removed the ignored frontend-to-asset-tools dependency symlink before the real workspace installation. This exposed an additional manifest omission: the existing spatial imports were never declared by the frontend. Its manifest now carries the already tested React/DOM `19.1.1`, R3F `9.4.0`, Three/types `0.182.0`, model-viewer `4.2.0`, Motion `12.23.24`, MediaPipe `0.10.22-rc.20250304`, and React types `19.1.16`/`19.1.9`. Next/eslint-config-next use foundation's `15.5.28`; Lucide `0.469.0` declares React 19 compatibility. These are manifest changes; application source and the isolated asset-tool tuple are unchanged.
- The mixed React 18 console/React 19 frontend workspace exposed R3F's undeclared React type peer. A root pnpm package extension adds optional `@types/react: ^19.0.0` only to `@react-three/fiber@9.4.0`. Its JSX augmentation now resolves the frontend's actual React 19 types. No compiler configuration, type shim, exclusion, source edit or regression assertion was needed; the console retains its own React 18 dependencies.
- Local validation on Node `24.19.0` / pnpm `10.34.6`: **frozen install passed**, **full frontend `tsc --noEmit` passed**, and **Module Regression passed all 11 modules, 0 failed** with `CI=true REGRESSION_TIMEOUT=900 bash scripts/regression/run_all.sh` (2026-10-23 14:49:37–14:49:53 UTC). Gateway: 1 test passed; chain: 38 passed and 7 existing testnet integration tests skipped. A separate nonincremental frontend compile also passed. `git diff --check` and independent manifest/lock/scope review passed.
- Reproduce with the root-pinned manager: `pnpm install --frozen-lockfile`, `pnpm -C brandme-frontend exec tsc --noEmit`, then `CI=true REGRESSION_TIMEOUT=900 bash scripts/regression/run_all.sh`. The explicit CI environment prevents local Vitest watch mode, matching GitHub Actions. The original workflow and all module scripts/tests remain otherwise unchanged.
- Precise next step: publish this tested toolchain commit with an expected-head check, fetch and compare its tree, then require the push-triggered Module Regression run for that exact remote SHA to finish successfully. Record the remote SHA/run receipt here before any feature work. No completed assets were regenerated or re-uploaded; Stage 11's 36-browser-test evidence remains separately dated.
- This repair declares the frontend dependency tuple and verifies compilation; integrated Next/API/domain behavior, authenticated persistence, physical AR/touch, pose-model and photo-provider approval remain open. Calibrated fit stays unavailable. OutfitEditor v1 and all lane logic are unchanged. After the CI receipt, the next owned feature remains the shoe-shelf collision milestone specified in Stage 11. No merge or deployment is requested.


### Stage 14 — toolchain publication and CI receipt (2026-10-23)

- Toolchain implementation **published and fetched back** as `e576558d1b1113514d67ed5b439a4f2289427dbd`, advancing the branch from `5acc8ee40c79b3b4be52357846eed513cbeb6d63` with a non-forced expected-head check. Tree `52408bdd743133bb494d075467b0061ddcb8dcaf` exactly matches locally tested commit `6d733acb60a1e4272a98d62f90fcdb9ed6b52791`; the fetched comparison has zero differences and the worktree was clean.
- **GitHub Actions Module Regression succeeded end-to-end on that exact implementation SHA:** [run 39973210496](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/39973210496), push event, job `regression` / `120481011847`, final workflow and job conclusion `success`. Setup pnpm, frozen JS install, Python setup, the complete module regression suite and cleanup all passed. This is the existing repository module suite; it is not an integrated product-flow, Next production-build or physical-device AR approval.
- PR **#36 remains open, draft and mergeable**, against `docs/brandme-full-experience-2026-10-05`. The five toolchain files plus this lane status are the entire repair. No implementation upload remains outstanding, and no lane logic, test, compiler configuration, asset or other-lane manifest changed. This receipt is a documentation-only follow-up; its own push-triggered regression must also be checked at the latest branch head before reporting completion.
- Precise next owned feature remains **shoe-shelf collision admission** described in Stage 11: shared availability checks for add/move/destination UI using existing authored bounds, preservation of existing layouts, rejection of overlapping new placements, separated-slot or Unplaced alternatives, and transaction/idempotency/concurrency tests. Do not regenerate completed assets or resume the already completed toolchain repair.
- Foundation/API/domain integration and native-device/provider gates remain explicit and open. Calibrated fit remains unavailable; OutfitEditor v1 is preserved. No PR was merged and no deployment occurred.

### Stage 15 — founder ultra-plan execution (2026-10-23, in progress)

- Resumed the attached founder brief at verified remote `a78433d66e8c41963abd1f62f810f920ecdc6ee1`, using an isolated worktree. PR #36 remains draft. Existing assets and the completed CI repair are preserved.
- Ordered scope: reviewable guest asset/editor/try-on milestone; actual local pose inference; dev photo-provider job flow; measurement/calibration preparation; native device-session protocol. No production activation, user photos, merge, or deployment.
- Implementing authored-bound shoe-shelf admission in repository and destination UI first. Existing layouts are preserved. New checks will cover failed-write immutability, retries, idempotency and concurrent reservations.
- Pose default: same-origin, pinned MediaPipe 0.10.35 runtime with version-1 lite model; an original AI-generated synthetic adult is the only person-image fixture. Runtime/model payloads are reproducibly downloaded for dev, hash checked, and excluded from source until model redistribution terms are confirmed. No real-device or population accuracy claim.
- Credential manifest: none created yet. Local inference needs no credential. Photo-provider credentials, if acquired, will be dev-only and server-only; values never belong in this file.
- This checkpoint is not completion evidence. Tests, provider access and device measurements remain pending; final receipts will supersede it.

### Stage 16 — implemented development boundary and review findings (2026-10-23)

- Shoe-shelf admission now uses the original authored bounds, placement quaternion/scale and 1 cm horizontal clearance. The repository's atomic add/move and destination UI share the same check. Existing layouts are not rewritten. Separated destinations and Unplaced remain usable; failed writes, inverse Undo, replay and concurrent reservations are exercised. This is not general packing or shelf-edge validation.
- Local pose inference is real: a same-origin classic worker runs pinned MediaPipe `0.10.35` with `pose_landmarker_lite/float16/1` on CPU. Runtime archive SHA-512 and model SHA-256 are checked by `scripts/assets/prepare-vision.py`. All six downloaded payloads remain gitignored. Four original GLBs were exported as transparent front overlays with hanger meshes removed; original room/garment binaries were not regenerated. Only upper-body garments are supported. There is no arm occlusion, rigging, body measurement, calibrated size or fit claim.
- Camera startup is explicit; backgrounding, exit, late permission resolution, stream ending and worker errors stop tracks. Tracking has a frame timeout and hides the overlay on absent, ambiguous or low-confidence landmarks. The test uses a synthetic canvas video stream through the actual camera/worker UI, then verifies track shutdown. Frames and landmarks are not uploaded.
- The local-only photo adapter targets Google's `virtual-try-on-001:predict` API. It requires a dev project, server token, region and retention disclosure before exposing upload controls. It accepts only the SHA-matching synthetic fixture and four original garment overlays. Explicit consent, same-origin mutations, HttpOnly owner session, bounded input/output, no redirects, single image per call, a persistent 10-attempt/day budget and operation-id replay protection precede external submission. Budget reservations survive process restart; timeouts are unknown outcomes with no automatic retry/refund. Inputs are not persisted; outputs are memory-only for 24 hours or process lifetime. Saving is browser-local. Deletion removes linked guest closet references before the saved media; provider-side erasure is never promised. Lost status polling releases the busy UI without submitting another job.
- **Photo evidence is conformance evidence using an injected provider double. No live Google generation, account access, regional availability, actual retention agreement, price or quota has been verified.** No Google Cloud connector, CLI credentials or configured project/token was available in this session. The adapter remains disabled. This is the precise remaining external integration gate, not a completed live provider demo.
- Measurement preparation accepts three independent readings for height, chest, waist, hip, shoulder width and inseam in centimeters; rejects nonfinite/out-of-range inputs or spread over 2 cm; exports only on user action and clears on exit. Median values and a minimum 1 cm uncertainty are preparation heuristics, not validated error estimates. A separate versioned garment comparison propagates uncertainty without returning a fit verdict. Synthetic test arithmetic: chest 100 cm ±1 cm and garment 108 cm ±0.5 cm gives an ease interval [6.5, 9.5] cm. **There is no physical fit-accuracy evidence yet.** Calibrated fit stays unavailable.
- Native AR has a dedicated development device-session route, disabled unless the explicit development mode and server flag are set. It records device/build/asset context and operator-entered outcome with `approval: false`. Normal room placement remains unverified and disabled. A device-test launch does not promote capability state.
- The first full new regression passed 45/46. Context-loss handling was attached after renderer startup; the failing test caught the missing recovery window. Recovery now listens in the host's capture phase before the asynchronous renderer initializes. No assertion was removed. Integrated Next compilation then exposed the legacy object-or-Promise params declaration in three owned dynamic routes; they now use Next 15's Promise contract. Further build/test results and the publication receipt follow below.

#### Credential manifest — values deliberately excluded

| Name | Scope | Storage | Created / status (UTC) |
|---|---|---|---|
| Local MediaPipe inference | On-device development | No credential | 2026-10-23: none required |
| `BRANDME_VERTEX_ACCESS_TOKEN` | Intended short-lived token for a dedicated dev project only | Server process environment or gitignored `brandme-frontend/.env.local`; never `NEXT_PUBLIC_*` | 2026-10-23: **not created / unavailable** |
| `BRANDME_PHOTO_DEV_PROJECT`, `BRANDME_PHOTO_DEV_REGION` | Dev project and explicit allowed region | Same server-only local configuration | 2026-10-23: unconfigured; default region `us-central1` is not an availability assertion |
| `BRANDME_PHOTO_RETENTION_NOTICE` | Actual provider/account retention disclosure | Server-only local configuration, displayed before consent | 2026-10-23: unconfigured; do not invent terms |

No new secret was created, committed, logged, or sent to a browser. Once dev access exists, record credential name/scope/storage/creation date here, test revocation, and rotate it after the session. Do not raise the attempt limit or enable production automatically.

#### Reproduce the development evidence

Use the root-pinned Node 20–24 / pnpm `10.34.6` environment, `pnpm install --frozen-lockfile`, and the existing isolated asset-tool install described above. Do not regenerate the completed assets.

```bash
python scripts/assets/prepare-vision.py
node scripts/assets/validate.mjs
node scripts/assets/node_modules/typescript/bin/tsc -p scripts/assets/tsconfig.json
node scripts/assets/node_modules/@playwright/test/cli.js install chromium
SPATIAL_EVIDENCE_FILE=scripts/assets/evidence/ultra-browser-results.json node scripts/assets/node_modules/@playwright/test/cli.js test -c scripts/assets/playwright.config.mjs
pnpm -C brandme-frontend exec next build
CI=true REGRESSION_TIMEOUT=900 bash scripts/regression/run_all.sh
```

The full browser suite requires the explicit model preparation step; ordinary module CI does not download or execute the model. Tests cover the actual guest components in Vite. Next build/API smoke results are separately identified, not substituted for an authenticated foundation/domain journey. The `SPATIAL_RUN_DIR` override can keep transient traces outside the worktree.

To exercise a real photo dev request after access is supplied, configure the four server variables above and `BRANDME_PHOTO_DEV_ENABLED=1`, restart a **loopback-only** development server, open `/try/overshirt`, select Photo try-on, download/reselect the supplied synthetic PNG, inspect the disclosure, consent and submit once. Record model/region, request UTC, end-to-end latency, completion/error, actual output dimensions and whether browser save → closet reference → refresh → deletion works. Never include token values or real-person images in the evidence. Confirm that denial, timeout, duplicate operation and budget exhaustion do not send an extra request. The counter lives in gitignored `scripts/assets/.photo-dev/`; do not delete it to bypass the daily cap. This adapter is single-process local development, not a hosted upload service.

Sources used for the pinned integrations: [MediaPipe Pose Landmarker web documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/web_js), [versioned model source](https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task), and [Google Virtual Try-On request documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/generate-virtual-try-on-images). The runtime package declares Apache-2.0; model redistribution terms still need confirmation before shipping downloaded payloads. Original demo asset rights and synthetic-input provenance are committed separately.

#### One-sitting native-device protocol

Prepare before the founder arrives: install pinned dependencies and model files, validate assets, record `git rev-parse HEAD`, and arrange a development host with a certificate already trusted by both devices. The installed Next 15 CLI supports the following flags; certificate files are local secrets and must not be committed:

```bash
NEXT_PUBLIC_BRANDME_MODE=development BRANDME_AR_DEVICE_TEST=1 \
  pnpm -C brandme-frontend exec next dev --hostname 0.0.0.0 --port 3000 \
  --experimental-https --experimental-https-key /absolute/private/dev-key.pem \
  --experimental-https-cert /absolute/private/dev-cert.pem
```

Keep the server on a trusted private test network, with photo-provider variables absent. Confirm each phone opens `https://<dev-host>:3000/try/device-test` without a certificate warning and reports a secure context. An untrusted self-signed certificate is not a completed setup. No production build enables this route's test controls.

Bring one AR-capable iPhone/iPad with Safari and one ARCore-capable Android with Chrome/Google Play Services for AR, charged, plus a helper, tape measure, known 1 m reference and a clear well-lit floor. Record exact hardware, OS/browser versions, selected native viewer and commit. Reserve approximately 45 minutes for the native checks; measurements are a separate approximately 30-minute segment if done in the same sitting.

| Session step | Observable result / evidence |
|---|---|
| Open normal `/try/overshirt`, inspect and rotate | GLB loads, approximate fidelity is visible, normal native capability remains unverified |
| Open device-test route, enter device details, begin | Original model loads; supported devices expose the explicitly labeled test launch |
| iOS Quick Look and Android Scene Viewer/WebXR | Record which viewer actually opened; place on floor; capture cold-start and first-placement times; repeat three times |
| Cancel, return, background, deny permission | Original item/revision context remains available; no accidental closet mutation; camera indicator stops after exit; usable image/3D fallback on denial |
| Unsupported device / offline model fetch | Clear failure or disabled state, with usable return path; no infinite spinner or implied success |
| Compare to the 1 m reference | Record observed dimensions and relative error; retain approximate scale regardless of one successful placement |
| Export and finish | Download the evidence JSON, attach an operator recording and timing sheet, stop the dev server and remove the test flag |

A pass requires the exact device/viewer/build's three successful launches and returns, denied/unsupported recovery, no context loss or unwanted camera persistence, plus review of the recording. Evidence alone does not enable public AR: an explicit reviewed capability mapping is a later change. Native timing, accuracy and camera-release claims remain **unmeasured** until this session occurs.

#### Measurement and fit evidence needed from that session

Collect 18 independent centimeter readings (three each: barefoot height, chest, natural waist, fullest hip, shoulder landmark width, and a documented inseam method), releasing/repositioning the tape each time. Use a helper and record method, instrument resolution, date and repeat spread. Keep personal values in the private export; do not put them in this repository. For one physically available upper-body garment, record exact maker/model/size/revision, three flat chest/waist/hem and shoulder/length measurements, seam allowances/method, material composition/stretch, and any licensed pattern or supplier size specification. A trouser inseam is a garment proxy and must not be mislabeled as body ground truth.

Next compare repeated body and garment measurements with uncertainty, then collect consented observed comfort/mobility/ease outcomes (standing, seated, arm raise) and repeat measurements by a second operator if available. Report absolute measurement error against that reference and agreement with physical outcomes. A single founder session cannot establish population-level fit accuracy; no size recommendation, drape simulation or P4 designation is unlocked by repeatability alone.

#### Founder check-in — 21 questions with working defaults

Direction (1–7):

1. Should the next review target be the guest closet and honest development preview milestone? **Default:** yes; keep authenticated/domain rollout as a separate foundation integration.
2. Should live overlay remain an approximate visual aid while fit is unavailable? **Default:** yes; preserve the visible fidelity labels and no size recommendation.
3. Which garment scope should lead? **Default:** the four original upper-body garments; broaden only after pose/device evidence.
4. Should shoe-shelf admission remain bounded while broader packing is designed? **Default:** yes; preserve existing layouts and use Unplaced for overflow.
5. Should local inference remain the first pose strategy? **Default:** yes; avoid frame uploads and benchmark CPU/device limits before a cloud alternative.
6. What should a generated image become in the closet? **Default:** a deletable P0 Want reference, without ownership, authenticity or fit claims.
7. What quality target should drive the next pose iteration? **Default:** target stable 15–30 Hz on named devices with explicit loss recovery; do not claim that target from this CPU fixture run.

Integration and security (8–14):

8. Which dev provider access should be connected next? **Default:** an existing dedicated Google Cloud dev project with Virtual Try-On access and a short-lived, least-privilege server token; if unavailable, keep the adapter disabled while selecting an accessible dev equivalent.
9. Which provider production tier should be used? **Default:** none yet; decide only after the real dev run, terms, regional availability, actual pricing and budget review.
10. Should photo testing remain restricted to the synthetic fixture? **Default:** yes; no real user photos or production records in this lane.
11. What is the initial spending limit? **Default:** retain ten attempts per UTC day, one output per call and no automatic retry; set an account-level dev budget once pricing is verified.
12. Where should provider credentials live and when should they rotate? **Default:** server environment/gitignored local configuration for this dev session, short lifetime and rotation afterward; record metadata only in the manifest.
13. What retention and deletion promises should the UI make? **Default:** only the actual account/provider terms plus the tested app-local deletion behavior; never imply provider deletion from cancellation.
14. Should pose payloads be included in distributable builds now? **Default:** no; retain hash-pinned local downloads until model terms and the intended distribution are reviewed.

Scope and sequencing (15–21):

15. Can we run the prepared native session on both iOS and Android? **Default:** one 45-minute sitting with the devices, trusted HTTPS, helper and known-size reference listed above; if only one is available, approve evidence only for that exact tested path.
16. Can the founder supply the 18 readings and one physical garment described above? **Default:** add a separate 30-minute measurement segment, keep values private, and leave calibrated fit disabled until physical outcomes validate the method.
17. Should the final browser suite run after every capability change? **Default:** yes; preserve all previous scenarios and add coverage for new failures rather than replace the baseline.
18. What comes next if provider access is delayed? **Default:** publish the tested development boundary and continue device/accessibility work; do not label the provider integration live.
19. When should this lane join authenticated storage and the product shell? **Default:** after foundation's client/token contract lands; retain guest adapter isolation until an end-to-end authenticated test passes.
20. Which manual accessibility checks should follow? **Default:** 200% zoom, VoiceOver/NVDA, keyboard-only flow and physical touch on the two test devices.
21. What should happen after code-review readiness? **Default:** request review with external gates explicit; no automatic merge, deployment or public AR/photo/fit activation.

Priority decisions and next steps under plausible answers:

| Priority question | Answer | Next action |
|---|---|---|
| 1 — review target | Guest development milestone | Review the bounded PR with measured local evidence and external gates listed |
| 1 — review target | Authenticated launch required | Keep public release gated; join foundation's real repository/API and test identity, refresh and cross-device persistence before launch |
| 1 — review target | Narrower asset/editor release | Separate the tested development integrations into a follow-up review while preserving their work |
| 8 — dev provider | Google dev access supplied | Configure server-only access, record credential metadata, run one synthetic request and measure the actual end-to-end result |
| 8 — dev provider | A different accessible dev provider | Verify its official schema/terms, implement a provider-specific adapter and repeat the same consent/cap/idempotency/deletion tests before a live test |
| 8 — dev provider | No dev access yet | Keep the upload surface disabled; retain conformance evidence and continue native/accessibility work |
| 15 — device session | Both platforms available | Run the prepared matrix in one sitting and collect independent results per device/viewer |
| 15 — device session | Only one platform available | Validate only that exact device/path; retain the other platform's unverified gate |
| 15 — device session | No hardware available | Keep native activation gated, retain the protocol/build and continue browser validation without fabricating device results |

### Stage 17 — final browser evidence and build closure (2026-10-23)

- Final full browser run after the Next authority correction: **47 passed, zero failed/skipped/flaky**, 315.5 seconds, pinned Chromium 141. All 36 earlier cases are retained alongside collision admission, real local pose inference, photo service/UI/restart handling and measurement/device gates. Report: `scripts/assets/evidence/ultra-browser-results.json`. A focused 5/5 recheck had already verified context-loss recovery and photo operations after the fixes.
- The actual local model produced 33 landmarks on the synthetic fixture and zero poses on a blank frame. Warm inference across 11 timed samples: **87.5 ms median / 189.8 ms p95** on this container's CPU. Eight coarse landmark annotations gave 23.64 px mean error and 8/8 within a 64.512 px tolerance (15% of the approximate torso length); annotation uncertainty is 20 px. This is a reproducible single-fixture alignment check, not population accuracy, native-camera accuracy, physical measurement or fit evidence. The 15–30 Hz device target is **not met or established** by this run. Raw samples/landmarks and limits are in `pose-inference.json`; the actual overlay screenshot is `pose-preview.png` and was visually inspected.
- Asset validation passes all 36 required paths / 12 original manifests, four additional original PNG overlays, the synthetic fixture's hash/provenance/coarse annotations, and all six locally downloaded pose payloads. `ultra-asset-validation.json` records the distinction. The downloaded runtime/model remain excluded from the source tree. Isolated owned-component TypeScript and `git diff --check` pass.
- A fresh root frozen install reproduces the integrated build's remaining React type-resolution conflict: Next's own declarations resolve the workspace-hoisted React/DOM 18 types, while this frontend uses React/DOM 19. The existing toolchain repair is extended with optional React/DOM 19 type peers scoped only to `next@15.5.28`, matching the already-used R3F peer technique. No runtime version, compiler setting, assertion or console React 18 dependency is changed. The three owned dynamic routes also use Next 15's Promise params contract. Final frozen install, Next build and module regression results are recorded after verification; no success is inferred from a compiling bundle alone.
- Earlier local verification attempts with temporary dependency links failed from missing sibling-module dependencies and, separately, a concurrent build replacing generated `.next` types. A genuine five-importer frozen install replaced the root/frontend links; final build and module checks are run sequentially. The transient dependency setup failure is not represented as a product regression or hidden as a passed run.
- Integrated verification now passes: root frozen install; the complete Next 15.5.28 production build (bundle, type validity, static generation and traces); all **11 Module Regression modules**; and a real built-server Chromium/API smoke with zero browser errors. The smoke hydrates `/closet` and `/try/overshirt`, confirms photo capabilities disabled and POST 503 with no chooser, confirms live camera remains disabled in production, and confirms `/try/device-test` cannot begin a native test. The smoke exposed Next's normalized internal request hostname; the service now validates the actual loopback HTTP Host before comparing Origin, with external-host rejection and normalized-host replay coverage. No credentials were present or provider calls made. The successful full browser repeat after that correction supersedes the earlier 269.1-second run.
- This is a code-review milestone for the guest closet and bounded development integrations. The remaining external gates are a real Google dev request, model redistribution review, the prepared native-device/measurement session, authenticated domain integration and manual accessibility checks. Calibrated fit and public native/photo activation remain unavailable. Exact publication SHA and CI links are maintained on [PR #36](https://github.com/brandmeonline/Brand-Me-Labs/pull/36); re-query its head and push-triggered checks on resumption. No merge or deployment is part of this checkpoint.

### Stage 18 — Spatial-AR round 2 implementation (2026-10-24 Pacific)

The founder explicitly activated the attached Ultra plan 02 and requested work on `bench/astra-spatial-ar-20261005`. Implementation therefore continues from `ceb6ed6f` on that existing branch, overriding the draft's proposed fresh branch. The new review target is `main`. At kickoff, #51 remained draft against main and #56 remained conflicted against the spec branch; this change does not merge or rewrite those lanes. Main integration must be reconciled before merge readiness. No deployment, provider account, production data or credential has been created.

#### Implemented in this increment

- **Tier 1:** `/try/overshirt` → **Find your fit** exposes tailor questions and device-local, explicitly saved fit notes. Inference is scoped to house, category, size system and preferred silhouette; a corrected note replaces the same garment rather than inflating evidence. Ties, discomfort, restricted movement and tailoring needs do not produce a size starting point. Suggestions remain self-reported and non-calibrated, with no numerical confidence claim. Read, write, deletion, corrupt storage and cross-tab privacy boundaries have explicit behavior.
- **Tier 2 boundary:** photogrammetry remains **unavailable**, because no reconstruction engine, approved multiview capture or physical validation is connected. The permission-free WebXR feature probe distinguishes missing/insecure/unsupported/unknown paths but never promotes immersive AR support or an exposed API into proven depth/IR capture. It requests neither camera frames nor an AR session. This does not satisfy the brief's live photogrammetry exit criterion.
- **Pod model:** `measurementProvenance.ts` and `podCapture.ts` define strict runtime-validated capture, consent, retention and per-measurement provenance. Each measurement carries tier, source/reference, method/revision, capture UTC, units, uncertainty and body-versus-garment-proxy identity. Pod captures bind measurements to a subject, capture, station, hardware/software and device-calibration reference. Raw geometry is memory-only in this proposed model; measurement retention is bounded to 30 days and the consent expiry. Authoritative consent receipt validation, persistent storage and deletion workers are integration requirements, not implemented services.
- **Calibration linkage:** a separate cross-tier-calibration consent purpose is required. Paired measurements must concern the same body subject/dimension within the allowed time window. A link records both measurement references and target method, Pod-minus-cheaper correction and the sum of uncertainty bounds. Expired/revoked captures, synthetic/physical mixing and garment-proxy-to-body comparisons fail closed. One pair never implies population accuracy or enables calibrated fit. Brands have a narrow fit-outcome projection that rejects attached measurements, subject/capture identifiers and raw body data.
- **Fit evidence evaluator:** `fitEvidence.ts` reports fixture/garment/dimension counts, signed bias, MAE, RMSE, maximum error and separately reported reference uncertainty. `node scripts/assets/fit-evidence.mjs` exercises six invented dimensional comparisons across three fictional garments. Its numbers verify arithmetic only; `physicalBenchmark.status` is `NOT_RUN`, physical garment/measurement counts are zero, and calibrated fit remains false. No physical accuracy claim is made.
- **Scan experience:** `/add` → **Scan a garment** → `/add/scan` accepts a host-injected tag/photo resolver and consumes the existing Midnight-owned `brandme.passport.claims/v1` response shape. The shipped page is explicitly unconfigured. No actual resolver exists on this branch or the inspected main. Tests inject a clearly labeled fixture connector; only the supplied original garment photo is available. Public presentation is identity/house/maker/story; private facets require a separate server-authorized owner unfold. Browser controls confer no ownership. Requests cancel on changes/exit, late responses are ignored, and expiry/revocation closes private disclosures. Midnight still owns resolution, authorization, policy and agreed facet mappings.
- **Environment assets:** two original starter rooms, `starter_wooden` (Oak Starter) and `starter_modular` (Modular Studio), include GLB + gzip, rendered WebP, bounds, cameras, semantic placement slots, content hashes and individual rights records. Six folded slots are ray-checked against shelf surfaces. `environment-progression.json` is a presentation handoff from starters to the existing three walk-ins; reward entitlements remain authoritative domain decisions. Existing shell/catalog/reward behavior is unchanged. Friends' shared 2D views remain consumer-UI-owned.
- **CI:** a dedicated `spatial-validation.yml` adds separate asset/type and browser/local-pose jobs, using frozen isolated lane dependencies. Browser CI prepares hash-pinned model payloads locally and never uploads them. The Windows model-preparation path bug was fixed by serializing manifest paths with POSIX separators.

#### External gates and remaining acceptance work

| Brief exit | State after this increment |
|---|---|
| New PR targeting main | Draft publication and CI recorded below; main integration sequencing remains open |
| Local pose end-to-end | Existing real local model retained; current rerun evidence recorded below; no physical-device rate claim |
| Real photo-provider dev call | **NOT_RUN**: no configured dev project/token/region/retention notice. Existing synthetic-only provider adapter retained |
| Measured error against physical known garments | **NOT_RUN**: founder garment/measurement session required; arithmetic fixtures are not physical evidence |
| Fit ladder tiers 1–2 live | Tier 1 implemented for local guest; Tier 2 reconstruction/capture remains unavailable; depth/IR probe is a stub boundary only |
| Pod capture/provenance/calibration model | Implemented and documented above; physical Pod and backend services out of scope |
| Scan against real anchor resolver | Experience and claims contract checks implemented; authoritative resolver/producer mapping remains missing |
| Starter environments / earned upgrades | Assets and progression handoff implemented; consumer shell and rewards integration pending |
| Native-device session protocol | Stage 16 protocol retained; **NOT_RUN** on physical devices |
| Broader CI surface | Two new spatial jobs added; actual run conclusions recorded below |

The check-in trigger (real dev integrations wired + physical fit numbers + Pod model) has **not** been reached. The brief's 21 recommended defaults remain the working direction; there is no new approval or physical-evidence assertion. The credential manifest in Stage 16 is unchanged: no credential exists or was created for this increment. Pose payload redistribution remains excluded pending review.

#### Verification and publication

- Published implementation `fe3b761` and CI runner correction `8604f37` on the requested branch. [PR #60](https://github.com/brandmeonline/Brand-Me-Labs/pull/60) targets **main** and remains **draft / non-mergeable**. At publication, main has 147 commits outside this branch; the PR necessarily includes the earlier Spatial-AR baseline. No foundation/domain merge, force push or deployment was performed.
- Final local browser run: **80 passed, zero failed/skipped/flaky**, 493.6 seconds, Windows / Chromium 141. An additional **11/11** fit rerun verifies the final storage guard: a queued save cannot recreate a note deleted/reset by another tab. The initial 78-case attempt had four form-selector/claim-markup failures; accessible select labels and semantic `dl`/`dt`/`dd` claim fields were corrected without weakening assertions. The final runs supersede those attempts. Per-case outcomes and report hashes are in `scripts/assets/evidence/round2-summary.json`.
- Integrated Next 15.5.28 production build, component TypeScript and frozen dependency installs pass. The built-server Chromium/API smoke saves, reloads, reviews and deletes a synthetic guest fit note, observes zero fit uploads/browser errors, confirms scan is unconfigured, and checks disabled photo capabilities plus POST 503. Only synthetic fixture data is used. Fit/scan layout checks at 320/390/768/1440 px found no horizontal overflow; manual screen-reader/touch verification remains pending.
- Asset validation passes **36 required paths / 14 manifests**. Both committed starter rooms load and render from their declared cameras; all six shelf slots per room have support gaps below 0.000001 m. Wood: 4,260 triangles / 6 draw calls / 27,461 gzip bytes; modular: 4,464 / 6 / 29,370. Their staged software-WebGL scenes use 43,888 / 44,092 triangles and 33 draw calls. These are asset/render checks, not physical-device performance measurements. The rendered posters were visually inspected.
- Real local pose inference still produces 33 landmarks on the original synthetic fixture and zero poses on a blank frame. The final Windows run records **128.7 ms median / 189.4 ms p95**; coarse annotation mean error is 23.64 px, with 8/8 points inside 64.512 px and annotation uncertainty 20 px. Concurrent local verification affects timing. This single synthetic fixture provides no physical fit, population accuracy or 15–30 Hz device claim. Updated raw samples remain in `pose-inference.json`; no downloaded model payload is committed.
- GitHub checks for **`8604f3716f0fc203d5125634b02d4eaa6b7ea99e`** pass: [Spatial validation](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/40151251053), including both asset/type and **80/80 browser/local-pose** jobs (browser suite 3.9 minutes), and [Module Regression](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/40151251074), all **11 module groups**. Seven Cardano testnet tests are skipped; no live network test is claimed. The first spatial workflow failed during browser setup because rolling `ubuntu-latest` selected Ubuntu 26.04, unsupported by pinned Playwright 1.56.1; pinning these two jobs to supported Ubuntu 24.04 resolved it. The final evidence-only commit does not change tested application or workflow code.
- Reproduce the spatial suite after the frozen lane install with `python scripts/assets/prepare-vision.py`, `node scripts/assets/node_modules/@playwright/test/cli.js install chromium`, and `node scripts/assets/node_modules/@playwright/test/cli.js test -c scripts/assets/playwright.config.mjs`; set `SPATIAL_EVIDENCE_FILE=test-results/spatial-browser.json` and `SPATIAL_RUN_DIR=test-results/spatial-runs` to keep historical artifacts intact. `node scripts/assets/starter-environments.mjs --check` validates committed starter renders without rewriting assets. The built local preview uses `node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3005` from `brandme-frontend`, then `/try/overshirt` → **Find your fit** or `/add/scan`.

### Stage 19 — reported Shop/Stash image repair (2026-10-24 Pacific)

The founder reported missing images in the live `/shop` preview. The legacy shared `GarmentCard` ignored `imageUrl` and rendered literal `[Image]`, while all nine discovery/stash records referenced absent placeholder JPGs. This requested repair now renders accessible, lazy-loaded garment images, derives matching titles/posters from the existing original asset catalog, and supplies per-item `/try/{slug}` links. Shop and Stash fixtures are explicitly labeled demo rather than presenting fictional verification/material claims. No live inventory or ownership integration is implied.

Frontend `tsc --noEmit` and diff whitespace checks pass. In the actual in-app browser, all six Shop and all three Stash images decode with nonzero natural dimensions; the Shop render was visually inspected. The local server at port 3005 now runs `next dev` for immediate preview updates. This small follow-up was checked directly; the earlier 80-case/CI results above remain evidence for their named commit rather than being relabeled as a run of this follow-up.

### Stage 20 — round-03 continuation (2026-10-30)

- Resumed the founder-triggered Ultra plan 03 with parallel CI and integration review. Fetched main `97d54477f7667dade1a4fd7220c0b2694cffb604` (#62 merged); PR #68 remains pending and is not a prerequisite. Work runs in a fresh isolated worktree of the designated lane branch. Merge `3fe809f` preserves main's `/shop` → `/discover` and `/stash` → `/closet` redirects, removing the obsolete duplicate pages; foundation/domain changes are taken from main without editing their implementation.
- Diagnosed the red browser check at `2852b786`: [run 40155571278](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/40155571278/job/121056139035) passed **79/80** cases, including both real local-pose cases. The failing fit-history test reloaded before confirming the asynchronous origin-lock save. Assertions now wait for the corrected size and second committed note before navigation, and for completed reset before checking storage. Post-reload, privacy and deletion assertions remain intact. Current rerun results follow below; earlier results are not relabeled.
- Spatial CI now follows main's registered ten-package workspace, root frozen lockfile, `.nvmrc` and root pnpm pin. Removed the obsolete isolated install/symlink steps and added browser report/failure artifacts, excluding model payloads. The workspace guard passes with its five pre-existing manifest warnings. No dependency pin or foundation file was changed.
- Credential manifest: **none created**; no provider-specific environment variables are present in this task. Local pose preparation downloads only the existing hash-pinned development runtime/model; payloads remain ignored and redistribution remains gated.
- Remaining external evidence is still **NOT_RUN**: Google development-provider request, known physical garment measurements, and physical native-device session. Tier 2 reconstruction remains unavailable. Current main has a passport claims read API, but scan still needs tag/photo-to-asset resolution, agreed facet mapping, and public-versus-owner-unfold integration; the page remains explicitly unconfigured.
- Usage at kickoff: account allows ordinary usage, weekly window **0% used**; next reported reset **2026-11-05 17:04:21 UTC (09:04:21 America/Los_Angeles)**. No secondary window was reported. No reset credit consumed; no rate-limit block observed.
- Merge gate: land #60 only after all checks on the final candidate pass and GitHub reports it clean. [PR #60](https://github.com/brandmeonline/Brand-Me-Labs/pull/60) is the authoritative live merge/check state. The round-03 check-in trigger has not been reached; no physical fit, device-rate or live-provider claim is made.
- Independent review reproduced an empty-history reset race: a first save already queued behind a reset could restore a note because both before/after history values were absent. Resets now rotate a separate nonpersonal generation marker under the existing origin lock; queued saves compare it, and other tabs clear drafts on its storage event. The history key is still removed. Marker-write/deletion failures report an error instead of claiming success. Four focused regression cases cover the empty-reset race, repeated resets, corrupt/unreadable state, storage failures and real cross-tab locking; component TypeScript, independent review and all **15 focused fit cases** pass.
- The original reload race passes **5/5** consecutive focused runs. Asset checks pass **36 required paths / 14 manifests**, and both starter rooms pass actual camera/render/shelf checks. A fresh Windows checkout exposed CRLF conversion changing hashed starter rights JSON; the owned demo directory now pins JSON to LF without changing asset bytes or weakening hashes. The Windows `--with-pnpm` guard launcher cannot spawn the `.cmd` shim (`ENOENT`); the static guard and explicit root frozen install pass, and Linux CI runs the full guard. A concurrent-build local harness startup timed out before executing tests; it is not counted as a test pass.

#### Current implementation evidence — `d3cc93e235f0fbec227ba494c95fd26d72de7bed`

- **84/84 browser cases pass**, zero failed/skipped/flaky, 314.0 seconds, Node 24.21.0 / pinned Chromium 141 on Windows. This includes both real local-model tests, camera cleanup/no uploads, fit deletion/reset races, Pod provenance, scan disclosure boundaries and room/placement/accessibility scenarios. `scripts/assets/evidence/round3-summary.json` lists the cases, report hashes and precise boundaries; historical round-2 evidence is preserved.
- Full Next 15.5.28 production build passes (27 generated pages). The built app passes guest save → reload → review → delete, reset marker, main's Shop/Stash redirects, unconfigured scan and disabled photo API (POST 503), with **zero browser errors / fit uploads / provider calls**. Fit and scan layouts have no document overflow at **320/390/768/1440 px**. The actual integrated shell and fit screen were visually inspected; `round3-built-fit.png` records that view. Physical-device and manual assistive-technology work remain separate.
- Pose inference reports **33 landmarks**, blank-frame rejection, **100.1 ms median / 133.9 ms p95** across 11 warm samples. Coarse alignment: **23.64 px** mean error, **8/8** annotated points within **64.512 px**, annotation uncertainty **20 px**. See `round3-pose-inference.json` and visually reviewed `round3-pose-preview.png`. This is one synthetic fixture on a desktop CPU, not physical body measurements, population accuracy, fit or a 15–30 Hz native-device claim.
- Exact implementation CI: [Spatial PR run](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/41066518819), [Spatial push run](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/41066510462), [Build/Test](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/41066518792), [Consumer UI](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/41066518658), [Module Regression](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/41066518660), [Workspace guard](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/41066518867). The final evidence-only commit preserves this application/test/workflow code; its own GitHub checks must also finish before merging. Superseded checks from this task were cancelled to free runner slots; cancellations are not reported as passes.

#### Next executable gates

1. Merge #60 on green + clean, then use the documented local pose model while redistribution clearance remains pending.
2. For a real photo-provider run, supply an approved Google Cloud **development** project/region, Virtual Try-On access and a short-lived credential through the documented server-only environment. No credential value belongs in this file or a PR. Existing fixture conformance does not satisfy the live-provider exit.
3. Run the prepared **30-minute / 18-reading physical measurement session** and **45-minute native-device session**; record only actual devices/garments and keep calibrated fit unavailable. Current physical garment count and tested native-device count remain **zero**.
4. Tier 2 reconstruction, authenticated storage, and scan resolver/public-owner mappings remain explicit integration work. The Pod model, Tier 1 flow, starter assets, native-session protocol and thicker CI are implemented. Continue on the plan's defaults; the 21-question completion check-in is due only when its stated trigger is met.

### Stage 21 — passport transport and private evidence intake (2026-10-30)

- **#60 landed:** merged to main as `c902317df3da58b9f20916811052111dfdf23569` after final head `3eddd286` had **20 successful checks and one expected deployment skip**, clean and ready. Both final spatial runs passed **84/84** cases. The subsequent main [Build/Test run](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/41070741028), [Module Regression](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/41070740854), and [Workspace guard](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/41070740880) also passed; all five main container builds succeeded, and GKE deployment was skipped. This continuation starts from that merged main, with parallel implementation and independent review.
- **Passport HTTP reader:** `passportClaimsReader.ts` consumes the existing generated claims schema and same-origin passport GET endpoint. Public requests omit credentials on every page; only an explicit owner read includes same-origin credentials, and every page must retain the requested viewer/asset/environment/network. Bounded pagination and streamed JSON reject incomplete, oversized, cyclic, duplicate or downgraded responses; cancellation, a whole-read deadline and redirect rejection are enforced. No tag/photo resolver or new facet mapping is invented, and the shipped scan page remains unconfigured. Composition and host session obligations are documented alongside the reader.
- **Private garment intake:** `scripts/assets/fit-evidence-private.mjs` evaluates supplied physical-garment circumference records through the existing evaluator. Explicit input/output paths must be outside Git worktrees, with link/traversal checks and exclusive output creation. Reports contain aggregate metrics and hashed protocol/source references, without individual readings, garment identifiers or paths; console output contains only status/report hash. Reports remain private, `INPUTS_RECORDED_UNVERIFIED`, and `calibratedFitAvailable: false`. The operator guide distinguishes chest/waist/hip circumferences from flat widths and the separate 18 body readings, requires an independently documented estimate method, and explains Windows ACL and filesystem-race limits. This is intake preparation, not a physical session or an estimation engine.
- **Evidence isolation and CI:** pose tests now write inference JSON and preview images to their own test output directory, preserving historical committed evidence. The existing artifact allowlist includes only the synthetic pose JSON in addition to its previous safe report/image/video paths; trace archives and model payloads remain excluded. Spatial CI now also runs the private-intake functional tests.
- **Focused checks:** the passport reader passes **11/11** tests, including actual browser requests with an HTTP-only session cookie (omitted on public pages, included only on explicit owner pages), redirects and cancellation. Component TypeScript passes. Private intake passes **7/7** Node 24.21.0 functional test groups with no skips, including actual Windows junctions/hard links, duplicate JSON keys, malformed UTF-8, bounded input, no-overwrite and competing writers. Tests use invented temporary records solely to exercise code; they provide no physical evidence. Integrated continuation results are recorded below when complete.

#### Cloud discovery and remaining evidence gates

The founder selected eastern US and instructed this lane to use repository configuration. `.github/workflows/ci-cd.yml` identifies the existing shared project **`lux-realestate-app`**, region **`us-east1`**. The region is also listed for Virtual Try-On in [Google's location matrix](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations). Read-only Cloud SDK checks on this date confirmed the project exists, but Vertex AI is **not enabled** and no spatial development service account is present. The repo's `GCP_SA_KEY` is an image-publishing credential, not a configured photo-provider credential; the shared credential manifest still marks `BRANDME_VERTEX_ACCESS_TOKEN` as planned. `brandme-dev` is an emulator namespace and `brandme-prod` is an example, so neither is treated as discovered dev access.

The ignored local `brandme-frontend/.env.local` now records the discovered project and chosen region with `BRANDME_PHOTO_DEV_ENABLED=0`; it contains no token or invented retention notice. No photo-provider credential, API enablement, IAM binding or cloud resource was created, and no live image request was made. Credential manifest: **none created**. Live photo completion still needs scoped development access, Vertex enablement and the actual account retention disclosure; the image-publishing secret is not repurposed.

Physical garment measurements and native-device sessions remain **NOT_RUN**, with **zero physical garments and zero tested native devices** in this lane's evidence. The new intake cannot make those claims true by accepting a file. Tier 2 still lacks a reconstruction engine, approved calibrated multiview input, scale/quality checks and physical validation; existing 2D pose overlays and renderer statistics do not supply them. The scan still requires Midnight's authoritative tag/photo-to-asset resolver, a dev record, and agreed producer facet mappings. The round-03 completion check-in trigger remains unmet.

Usage at this continuation's check: **11% weekly used**, ordinary usage available; next reported reset **2026-11-05 17:04:21 UTC (09:04:21 America/Los_Angeles)**. No secondary window was reported and no reset credit was consumed.
