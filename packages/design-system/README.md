# @brandme/design-system

Tokens generated from `docs/design/brandme/contracts/design-tokens.json` (read-only spec input).

- `generated/tokens.css`: CSS custom properties (`--bm-color-*`, type, spacing, radius, layout, z-index, motion). Dark values apply under `prefers-color-scheme: dark` or `[data-theme="dark"]`. Reduced motion applies under `prefers-reduced-motion` or `[data-motion="reduced"]`; `[data-motion="full"]` opts out. One reduced-motion source serves DOM and scene code.
- `generated/tokens.ts`: the same contract as typed constants (`tokens`, `easing`, `closetAddSegmentsMs`, `sceneCamera`, `qualityTiers`).
- `src/contrast.ts`: WCAG contrast ratio.

`pnpm contracts:generate` regenerates; `pnpm contracts:check` fails on drift. Tests assert byte-equality with the contract and WCAG AA for 18 text pairings in both schemes. All pass on 2026-10-05.

Not in this package yet: accessible primitives, app shell, component gallery and self-hosted Cormorant Garamond / Manrope with licenses (see `docs/build/deviations.md` D-004).
