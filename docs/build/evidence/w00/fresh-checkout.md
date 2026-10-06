# Fresh-checkout boot evidence (BM-BASE-001)

**Run:** 2026-10-05. I ran `git clone` of commit `63df43f` into an empty directory. The Spanner emulator container was stopped and removed beforehand, so setup had to start it (cold path). The machine already had the pnpm store and the uv cache warm from earlier runs, so the wall-clock times below are not cold-network install times.

| Step | Command | Exit | Time | Log |
|---|---|---|---|---|
| Setup | `pnpm setup:demo` | 0 | 6.1 s | `fresh-checkout/setup.log` |
| Smoke | `pnpm smoke` | 0 | 13.8 s | `fresh-checkout/smoke.log`, `smoke-latest.json` |
| Checks | `pnpm check` | 0 | 27.9 s | `fresh-checkout/check.log` |
| Builds | `pnpm -r build` | 0 | — | `fresh-checkout/build.log` |

What setup did: created `.venv` from `scripts/python/requirements.lock`, validated Node 24.21.0 / pnpm 10.34.6 / Python 3.11, ran `pnpm install --frozen-lockfile`, wrote `.env.local` from `.env.example`, started `brandme-spanner` (emulator 1.5.28) through Docker, and applied V001 through the ledger.

What smoke proved: `GET /api/v1/system/health` on gateway :3001 returned ok for both checks, gateway → Spanner and gateway → brain :8000 → Spanner. A labelled dev session was created. `PATCH /me` with If-Match + CSRF succeeded. **Both gateway and brain were restarted** and the profile was still there at version 2. The outbox events (`member.created`, `member.updated`) written by the TypeScript gateway were validated and dispatched by the Python `OutboxDispatcher`.

An earlier run on the same day (before `63df43f`) failed `pnpm check` on a fresh clone. `packages/contracts/src/foundation-schemas.json` was hidden by the root `*.json` ignore rule; it is fixed and tracked now (deviation D-003).

## Not covered by this run

- **Consumer app → gateway:** the smoke client is a Node `fetch`, not the consumer UI. `brandme-frontend` (Next 14 placeholder) has no gateway client yet. BM-BASE-001 is therefore recorded as **blocked** on the consumer-ui lane, not passed.
- **Container path:** `docker compose up` was validated with `docker compose config` only.

## Frontend boot and legacy route probe (`pnpm dev:demo`, same day)

`pnpm dev:demo` started brain :8000, gateway :3001 and consumer :3000 and printed the URLs.

| Request | Status | Meaning |
|---|---|---|
| `GET :3000/` | 404 | the existing frontend has no root page |
| `GET :3000/shop`, `/stash`, `/scan` | 200 | old placeholder pages; **no** redirect to `/discover`, `/closet` (those routes do not exist yet) |
| `GET :3000/discover`, `/closet` | 404 | not built yet (W03/W04) |
| `GET :3001/api/v1/system/health` | 200 | |
| `POST :3001/scan` unauthenticated | 401 | legacy route now uses the real principal |
| `POST :3001/scan` with session + CSRF, no NATS | **500** | `routes/scan.ts` publishes to NATS unconditionally (not foundation-owned) |
| `GET :3001/scan/:id` with session | 200 `processing` | constant placeholder (trust-path inventory) |

BM-BASE-005 is recorded as **failed** with these owners: frontend lane (redirects) and whichever lane takes `routes/scan.ts`. Proposed fix for scan: persist a scan operation and return 503 problem+json when the event bus is unconfigured.
