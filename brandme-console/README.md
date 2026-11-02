# brandme-console

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Next.js operator console (port **3002**). Status per `CLAUDE.md`: **PARTIAL**. It builds and runs, but its
operations screens (`/api/v1/ops/*` and the provider pages) call gateway routers that `main` does not mount
(`brandme-gateway/src/routes/v1/index.ts`), so every ops screen ends unconnected. `app/proof/[scanId]` and
`app/dashboard/scans` use `lib/api.ts`, a legacy bearer-token client that reads `auth_token` from `localStorage`;
it bypasses the gateway session model and is on the cleanup list.

## Run

The console is not in `docker-compose.yml`; it runs only under `docker-compose.dev.yml` (service `console`) or
natively:

```bash
pnpm --filter @brandme/console dev    # http://localhost:3002, expects the gateway on :3001
pnpm --filter @brandme/console build
pnpm --filter @brandme/console type-check
```

`pnpm --filter @brandme/console lint` has no ESLint configuration and prompts interactively; CI never runs it
(audit S2-OBS-007).

## Configuration

Variables the console reads (`process.env.*` in `app/` and `lib/`):

```bash
BRANDME_MODE=development
BRANDME_GATEWAY_URL=http://localhost:3001          # server-side calls
BRANDME_GATEWAY_INTERNAL_URL=http://gateway:3001   # inside compose
NEXT_PUBLIC_GATEWAY_URL=http://localhost:3001      # browser calls
NEXT_PUBLIC_KNOWLEDGE_SERVICE_URL=http://localhost:8003
NEXT_PUBLIC_COMPLIANCE_SERVICE_URL=http://localhost:8004
NEXT_PUBLIC_CHAIN_SERVICE_URL=http://localhost:3003
NEXT_PUBLIC_CARDANO_EXPLORER_URL=https://preprod.cardanoscan.io
```

Legacy template entries, read by nothing in the console today (kept because the credential manifest records them
as `legacy-unread`):

```bash
NEXTAUTH_URL=http://localhost:3002
NEXTAUTH_SECRET=your-nextauth-secret
```

## Where the rest is documented

Shell contract and console pages: `docs/build/status/opus-commerce-agents.md` (operator console rounds) and
`docs/build/status/astra-consumer-ui.md` (shell layout contract). Status table: `CLAUDE.md`.
