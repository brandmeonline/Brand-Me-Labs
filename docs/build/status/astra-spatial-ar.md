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
