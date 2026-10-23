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
- Verification is complete; publication and fetched-tree confirmation must be recorded below before expanding scope.
- Precise next owned milestone after this publication: shoe-shelf collision admission using existing authored bounds. Start with a shared availability helper consumed by guest add/move and destination UI; reject adjacent overlapping new placements, permit a sufficiently separated slot or Unplaced, preserve existing guest layouts and item identity, and test failed-write immutability/idempotency/concurrency. A read-only review found that logical shoe slots are 0.1375m apart while the authored sneaker pair is about 0.386m wide, so distinct slot IDs alone do not establish physical clearance. Do not apply a generic rail AABB migration or regenerate assets as part of that increment.
- Foundation/Next/domain integration, 200% zoom/manual screen-reader/physical-touch review, native AR/device evidence, pose models and photo-provider APIs remain open. Calibrated fit remains unavailable. Experience complete / integration verified / production approved remain **No**.
