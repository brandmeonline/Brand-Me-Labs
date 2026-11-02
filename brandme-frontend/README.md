# brandme-frontend

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Next.js 15.5.28 consumer app (port **3000**; the spec targets 16.3, see `docs/build/deviations.md` D-009).
Status per `CLAUDE.md`: **PARTIAL**: the consumer shell and guest journeys shipped with PR #56; the wardrobe is
still guest-local and there is no browser OIDC sign-in (audit work packages WP-04 and WP-08).

Routes under `app/`: `add`, `assistant`, `circle`, `closet`, `discover`, `governance`, `inbox`, `me`, `orders`,
`products`, `rewards`, `scan`, `settings`, `shop`, `start`, `stash`, `style`, `today`, `try`, plus `api/` and
`dev/`. Spatial features (closets, fit ladder, passport claims) live in `features/spatial/`; visual baselines for
the shell job in `lib/testing/`.

## Run

Use pnpm only (`docs/build/workspace-governance.md` rule 5; `npm install` is refused by the workspace guard).

```bash
pnpm dev:demo                               # from the repo root: brain :8000, gateway :3001, consumer :3000
pnpm --filter brandme-frontend dev          # app alone
pnpm --filter brandme-frontend build        # production build with lint and type checks (CI: Test Frontend)
pnpm --filter brandme-frontend test:ui      # component tests
pnpm --filter brandme-frontend test:browser # browser checks (CI: consumer-ui.yml)
pnpm --filter brandme-frontend test:gateway # browser → gateway → domain → Spanner journey (CI: live-domains)
```

In containers the `consumer` service of `docker-compose.yml` runs `next dev -p 3000`.

## Configuration

`NEXT_PUBLIC_BRANDME_MODE` / `BRANDME_MODE` select demo or development behaviour. Browser calls reach the gateway
through the server-side proxy in `lib/server/gateway-proxy.ts`, which targets `BRANDME_GATEWAY_URL`
(`http://gateway:3001` in compose). `lib/api.ts` still defaults its base URL from `NEXT_PUBLIC_API_URL` (fallback
`http://localhost:8000`, the legacy brain) and is not the path the shipped journeys use. Test
harness variables (`BRANDME_CONSUMER_URL`, `BRANDME_CONSOLE_URL`, `BRANDME_EVIDENCE_DIR`, `BRANDME_VISUAL_CAPTURE_ONLY`,
`BRANDME_PYTHON`, `BRANDME_TEST_PACKAGE_JSON`) are set by the workflows. `BRANDME_VERTEX_ACCESS_TOKEN` (spatial
lane, GCP access token) is recorded in `docs/build/security/credential-manifest.yaml`.

## Where the rest is documented

`docs/build/status/astra-consumer-ui.md` (shell contract, journeys, evidence gates),
`docs/build/status/astra-spatial-ar.md` (spatial), `docs/design/brandme/01-product-experience.md` and
`02-visual-motion-spatial.md` (the contract), `.github/workflows/consumer-ui.yml` (checks).
