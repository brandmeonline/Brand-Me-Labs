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
2. **Spatial interaction/polish:** drag and touch long-press placement, physical collision/packing refinement for crowded slots, authored folded-display variants, saved custom camera views and orbit debounce, 450ms room transition, selected-item camera focus, source prefetch/pending slot representation, and 200% zoom/manual screen-reader/touch review. The current editor is an accessible visual composition using original garment posters; a composite 3D outfit preview remains future work.
3. **Asset finishing:** richer baked grounding/AO and entry-tier lighting, optional measured KTX2/geometry compression, neutral turntable still sets, rigged garments, and a general quarantined upload/optimization pipeline. Current fixtures use embedded original PNG PBR maps and gzip transport with portable uncompressed GLBs. Source is reproducible from the generator; a private source-archive ingestion service is not implemented here.
4. **Native AR:** actual supported iOS/Android/WebXR hardware tests and authoritative capability-registry activation; current disabled handoffs must not be switched on merely because desktop emulation passes.
5. **Live pose:** rights-reviewed locally hosted model/WASM files, approved pinned stable runtime, confidence/multiple-person/occlusion validation across bodies and lighting. Lifecycle scaffolding is tested; pose inference is not represented as verified.
6. **Photo processing:** approved provider/region/retention disclosure, real consent/job/spend/cancel/delete APIs and end-to-end generated output tests. Local media-store tests are not provider-deletion proof. Calibrated fit remains unavailable.

| Release dimension | Current assessment |
|---|---|
| Experience complete | **No** — working guest scaffold; integration and listed interactions remain |
| Integration verified | **No** — foundation/domain clients and physical AR/provider evidence absent |
| Production approved | **No** — no deployment or live capability activation performed |
