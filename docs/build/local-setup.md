# Local setup from a fresh checkout

Verified 2026-10-05 from a fresh `git clone` in two cases: emulator already running, and a cold start where setup launched the emulator. Evidence: `docs/build/evidence/w00/fresh-checkout.md`.

## Prerequisites

| Need | Version | Notes |
|---|---|---|
| Node | 24.21.0 (`.nvmrc`) | `nvm use` / `fnm use` |
| pnpm | 10.34.6 | `corepack enable` (uses `packageManager`) |
| Python | 3.11 + `uv` (preferred) or `python3.11 -m venv` | setup builds `.venv` from `scripts/python/requirements.lock` (hashed) |
| Spanner emulator | 1.5.28 | started automatically through Docker; or `gcloud emulators spanner start` |

## Commands

```bash
pnpm setup:demo   # runtimes, .venv, frozen install, .env.local, emulator, migrations (idempotent)
pnpm dev:demo     # brain :8000, gateway :3001, consumer :3000 (BRANDME_MODE=demo)
pnpm dev          # same with BRANDME_MODE=development
pnpm smoke        # gateway → brain → Spanner, session, PATCH /me, restart persistence, outbox dispatch
pnpm check        # spec validator, contract/token drift, type checks, unit + emulator tests, doc links
```

Sign-in locally uses the **labelled dev identity simulation**: `POST /api/v1/session/dev {"test_identity":"you"}` returns an HTTP-only cookie and a CSRF token. It does not exist in sandbox/production.

`test:journeys`, `test:providers`, `test:midnight:*` and `assets:validate` currently **exit 2 with "not implemented yet"**. They belong to W03–W09 and are never reported as passing.

## Containers

`docker compose up` (default profile: emulators, migrate, brain, policy, gateway, consumer) validates with `docker compose config`. The full container boot was **not executed** in the verification environment; the native `pnpm dev:demo` path is the verified one. `--profile legacy` adds the stub-heavy services; in sandbox/production their preflight refuses to start them.
