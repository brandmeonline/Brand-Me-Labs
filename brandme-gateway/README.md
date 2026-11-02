# brandme-gateway

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Express/TypeScript edge gateway: server-side cookie sessions with CSRF, per-address and per-member rate limits,
and the `/api/v1` routers that front the Python services. Default port **3001** (`src/config/index.ts`). Status
per `CLAUDE.md`: **REAL** (169 vitest tests, run in CI by `ci-cd.yml` Test Gateway).

## What it serves

| Routes | Backend | Notes |
|---|---|---|
| `/api/v1/session/*`, `/me` | the gateway itself (Spanner sessions, CSRF, `If-Match` versions) | labelled dev identity simulation in demo/development only (`POST /api/v1/session/dev`); OIDC bearer verification when `IDENTITY_PROVIDER=oidc` |
| consumer routers: persona, wardrobe, outfits, social, decisions, rewards, media, try-on (`src/routes/v1/index.ts`) | `brandme_core/domains/persona/app.py` (consumer-domains service, port 8010) | forwarded with ES256 principal assertions signed by `CONSUMER_DOMAIN_ASSERTION_KEY`; unconfigured upstream → 503 per route |
| rights and My Data reads (`src/services/rights.ts`) | `brandme_core/read_api` and `brandme_core/privacy_exports` | each upstream has its own service token (32+ characters); privacy never falls back to the rights credential |
| Midnight operations (`src/services/rights.ts`) | `brandme-chain` `/midnight` API (`CHAIN_SERVICE_URL`, default `http://localhost:3003`, with `CHAIN_SERVICE_TOKEN`) | only when configured; `brandme-chain/INTEGRATION.md` |
| legacy `/scan` | `brandme-core/brain` (`BRAIN_SERVICE_URL`, default `http://localhost:8000`) | the legacy scan chain; see `CLAUDE.md` |

Commerce routers exist under `src/routes/v1/` but are not mounted (commerce-agents lane; `CLAUDE.md`).

## Configuration

Read by `loadConfig()` in `src/config/index.ts`; the schema is strict and the process refuses to boot on an
invalid combination.

- Mode and identity: `BRANDME_MODE` (`demo|development|sandbox|production`), `IDENTITY_PROVIDER` (`dev|oidc`),
  `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URI`, `OIDC_ALGORITHMS`, `SESSION_TTL_HOURS`.
- Upstreams: `BRAIN_SERVICE_URL`, `CHAIN_SERVICE_URL`, `RIGHTS_SERVICE_URL`, `PRIVACY_SERVICE_URL`,
  `PRIVACY_EXPORT_SERVICE_URL`, `CONSUMER_DOMAIN_SERVICE_URL`, and their credentials `RIGHTS_SERVICE_TOKEN`,
  `PRIVACY_SERVICE_TOKEN`, `PRIVACY_EXPORT_SERVICE_TOKEN`, `CHAIN_SERVICE_TOKEN`, `CONSUMER_DOMAIN_ASSERTION_KEY`,
  `CONSUMER_DOMAIN_ASSERTION_KID` (every secret-shaped name is listed in `docs/build/security/credential-manifest.yaml`).
- Storage and events: `SPANNER_PROJECT_ID`, `SPANNER_INSTANCE_ID`, `SPANNER_DATABASE_ID`; `NATS_URL` is optional.
- Edge: `PORT`, `CORS_ORIGINS`, `PUBLIC_ORIGINS`, `TRUST_PROXY` (hop count or IP/CIDR list, never bare `true`),
  `RATE_LIMIT_WINDOW_MS`, `RATE_LIMIT_MAX_REQUESTS`, `RATE_LIMIT_IP_MAX_REQUESTS`, `RATE_LIMIT_MAX_KEYS`,
  `DEFAULT_REGION`, `LOG_LEVEL`.

Strict modes (`sandbox`, `production`) refuse the legacy shared `JWT_SECRET` and the dev identity provider
(`docs/build/security/secrets-conventions.md`).

## Run

```bash
pnpm dev:demo                          # from the repo root: brain :8000, gateway :3001, consumer :3000
pnpm --filter @brandme/gateway dev     # gateway alone (needs the Spanner emulator and brain)
pnpm --filter @brandme/gateway test    # vitest (CI: ci-cd.yml Test Gateway, with the Spanner emulator)
pnpm --filter @brandme/gateway type-check
```

In containers the `gateway` service of `docker-compose.yml` runs the same `dev` script on port 3001; the
`consumer-domains` service shares its network namespace.

## Where the rest is documented

`CLAUDE.md` (status), `brandme_core/read_api/README.md` (rights and My Data backend),
`docs/build/status/opus-foundation.md` (sessions, CSRF, mode guard, rate limits),
`docs/build/status/opus-consumer-domains.md` (consumer routers), `brandme-chain/INTEGRATION.md` (Midnight).
