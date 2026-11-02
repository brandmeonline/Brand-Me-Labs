# Runtime verification — commands and results

- SHA: `ed19dc151d103b108cf972e6d37971c55d5dcf60` · audit date 2026-11-01 · second (independent) audit run
- `$WT` = `/tmp/claude-0/-home-user-Brand-Me-Labs/1bf61dcf-0f4d-53ea-917a-a94fd3490bcc/scratchpad/wt-main` (git worktree of the audit clone; `git rev-parse HEAD` verified before any command)
- `$VENV` = `/tmp/claude-0/-home-user-Brand-Me-Labs/1bf61dcf-0f4d-53ea-917a-a94fd3490bcc/scratchpad/venv` (Python 3.11.18, built from `scripts/python/requirements.lock` with `uv 0.11.32`, 90 packages)
- Tool versions: node v22.23.4 (pin 24.21.0, within `engines`), pnpm 10.34.6 (exact pin), python 3.11.18, uv 0.11.32, pytest 7.4.3, fastapi 0.134.0, vitest (gateway/chain pinned in lockfile), Next.js 15.5.28, Playwright 1.63.0 (audit tooling, pre-installed; `playwright install` not run), docker CLI 29.9.2 **without daemon**, java 21.0.12.1.
- Every step ran through `logs/steps.tsv`'s runner, which records cwd, command, exit code, UTC start/end and duration. Full logs: `logs/<step>.txt` (sanitized; longer than 200 lines → head 60 + tail 140).
- All times are wall-clock on a shared container; steps ran partly in parallel.

## Steps

| # | Step | cwd | Command | Exit | Duration | Counts / observation | Classification | Log |
|---|---|---|---|---|---|---|---|---|
| 1 | Worktree | — | `git worktree add $WT ed19dc15…` then `git -C $WT rev-parse HEAD` | 0 | <1s | HEAD = `ed19dc151d103b108cf972e6d37971c55d5dcf60` | setup | — |
| 2 | Python venv | `$WT` | `uv venv -p 3.11 $VENV && uv pip sync --python $VENV/bin/python scripts/python/requirements.lock` | 0 | 4s | 90 packages (uv cache hit) | pass | `logs/py-venv.txt` |
| 3 | Install | `$WT` | `pnpm install --frozen-lockfile` (no `--ignore-scripts`: repo has no lifecycle hooks; see lifecycle-inspection.md) | 0 | 18s | resolved 1198, added 1198; allowlisted postinstalls ran: protobufjs, esbuild×2, unrs-resolver; 5 others ignored by pnpm policy | pass | `logs/pnpm-install.txt` |
| 4 | Gateway lint | `$WT/brandme-gateway` | `pnpm lint` (`eslint src --ext .ts`) | 0 | 4s | no findings | pass | `logs/gateway-lint.txt` |
| 5 | Gateway type-check | `$WT/brandme-gateway` | `pnpm type-check` (`tsc --noEmit`) | 0 | 6s | no errors | pass | `logs/gateway-typecheck.txt` |
| 6 | Gateway tests | `$WT/brandme-gateway` | `pnpm exec vitest run` | 0 | 26s | **Test Files 16 passed, 4 skipped (20); Tests 151 passed, 18 skipped (169)**; skipped files `me.test.ts` (12), `export-backend.test.ts` (2), `consumer-domains.test.ts` (2), `read-backend.test.ts` (2) are `describe.skipIf(!up)` on the Spanner emulator at `localhost:9010` | pass; 18 **not run** (emulator absent) | `logs/gateway-vitest.txt` |
| 7 | Gateway build | `$WT/brandme-gateway` | `pnpm build` (`tsc`) | 0 | 7s | `dist` 912K, 40 JS files | pass | `logs/gateway-build.txt` |
| 8 | Python suite (CI test-core command) | `$WT` | `$VENV/bin/python -m pytest tests -q --timeout=300 -ra -p no:cacheprovider` | 0 | 73s | **`1422 passed, 761 skipped, 3 warnings in 70.94s`**; 0 failed, 0 errors, 0 xfailed; summary block: `QUARANTINED: 0 tests`; `ALLOWLISTED SKIPS: AP2_SDK_PYTHON 6, STRIPE_TEST_SECRET_KEY absent 5, model (Anthropic key) 3, stripe-mock 6`. Skip reasons (all environmental): Spanner emulator 704 (405+153+118+15+12+1), Firestore emulator 24, Spanner REST 6, GCS emulator 4, Pub/Sub emulator 3, Stripe 11, AP2 SDK 6, Anthropic key 3 | pass; 761 **not run** (emulators/credentials absent) | `logs/pytest-tests.txt` |
| 9 | Frontend build | `$WT/brandme-frontend` | `pnpm build` (`next build`, includes lint + type validation) | 0 | 67s | "Compiled successfully in 32.4s"; 36 routes; shared First Load JS 103 kB; largest route `/add` 45.4 kB (160 kB first load); `.next` 301M, `.next/static` 3.1M | pass | `logs/frontend-build.txt` |
| 10 | Frontend unit tests | `$WT/brandme-frontend` | `pnpm test:ui` (`node --test lib/testing/verify-ui.mjs ../brandme-console/lib/testing/verify-shell-adapters.mjs`) | 0 | 4s | tests 22, pass 22, fail 0 | pass | `logs/frontend-test-ui.txt` |
| 11 | Frontend gateway-proxy tests | `$WT/brandme-frontend` | `pnpm test:gateway` (`node --test lib/testing/verify-gateway.mjs`) | 0 | 2s | tests 13, pass 13, fail 0 | pass | `logs/frontend-test-gateway.txt` |
| 12 | Console type-check | `$WT/brandme-console` | `pnpm type-check` | 0 | 8s | no errors | pass | `logs/console-typecheck.txt` |
| 13 | Console lint | `$WT/brandme-console` | `pnpm lint` (`next lint`) | **1** | 2s | Stopped at interactive prompt "How would you like to configure ESLint?" — no `.eslintrc*`/`eslint.config.*` in `brandme-console` (only `eslint`/`eslint-config-next` devDependencies). CI never runs console lint (`consumer-ui.yml:37` builds only). | **toolchain/setup failure**, not an application failure | `logs/console-lint.txt` |
| 14 | Console build | `$WT/brandme-console` | `pnpm build` (`next build`) | 0 | 55s | "Compiled successfully in 12.2s"; 13 routes; shared First Load JS 102 kB | pass | `logs/console-build.txt` |
| 15 | Chain type-check | `$WT/brandme-chain` | `pnpm type-check` | 0 | 7s | no errors | pass | `logs/chain-typecheck.txt` |
| 16 | Chain artifact verify | `$WT/brandme-chain` | `pnpm compact:verify` | 0 | 2s | "artifact manifest OK (compactc 0.31.1, 1 contract(s))" (checks committed artifacts; does not fetch compactc) | pass | `logs/chain-compact-verify.txt` |
| 17 | Chain tests | `$WT/brandme-chain` | `pnpm test` (`vitest run`) | 0 | 109s | **Test Files 10 passed (10); Tests 90 passed (90)**; local/offline adapter, projection, reconciliation and contract-constraint suites; no network suites (`test:midnight:*` not run) | pass | `logs/chain-vitest.txt` |
| 18 | Packages type-check | `$WT` | `pnpm --filter './packages/*' type-check` | 0 | 5s | 4 packages, no errors | pass | `logs/packages-typecheck.txt` |
| 19 | Packages tests | `$WT` | `pnpm --filter './packages/*' test` | 0 | 2s | design-system 20/20, contracts 5/5, provider-contracts 17/17; firestore-rules: suite **skipped** ("Firestore emulator not reachable (FIRESTORE_EMULATOR_HOST)") | pass; rules suite **not run** | `logs/packages-test.txt` |
| 20 | Foundation gate | `$WT` | `BRANDME_PYTHON=$VENV/bin/python pnpm check --no-provision` (`--no-provision` so no emulator binaries are downloaded) | 0 | 100s | 12/12 steps ✓ (workspace governance, spec validator, contract+token drift, credential manifest, guard self-tests, packages type-check/tests, gateway lint/type-check/tests, python tests `1422 passed, 761 skipped`, docs links). Probes: Spanner ✗, Spanner REST ✗, Firestore ✗, Pub/Sub bin ✗, GCS bin ✗, Java ✓ → emulator suites reported `not_run`, never passed | pass with emulator suites **not run** | `logs/pnpm-check-no-provision.txt` |
| 21 | Frontend runtime (guest, no backend) | `$WT/brandme-frontend` | `BRANDME_MODE=development NEXT_PUBLIC_BRANDME_MODE=development pnpm exec next dev -p 3100 --hostname 127.0.0.1` (no `BRANDME_GATEWAY_URL`) | started, then stopped | ~6 min | `GET /` → 200; `GET /api/v1/me` → 503 `{"code":"gateway_unconfigured","title":"Account services are not connected."}` | runs without backend | `logs/frontend-dev-server.txt` |
| 22 | Screenshots | audit scratchpad (`pw/capture.cjs`, outside the worktree) | `node capture.cjs http://127.0.0.1:3100 <visuals/screenshots> ed19dc15…` (Playwright 1.63.0, headless chromium-1243) | 0 | ~4 min | 52 PNGs + `manifest.json` with 54 entries: 24 routes × 2 viewports (1440×900, 390×844), 2 action states × 2 viewports, 1 BFF probe × 2. Unknown route → 404. Every gateway-backed page observed `503` on `/api/v1/*` | captured | `logs/playwright-capture.txt` |

## Not run, and why

| Check | Reason |
|---|---|
| Spanner-emulator suites (pytest 704 skips, gateway 18 skips, `pnpm smoke`, `make test-core` equivalent beyond step 8) | Spanner emulator is a Docker image (`gcr.io/cloud-spanner-emulator/emulator:1.5.45`); the Docker daemon is not available (`/var/run/docker.sock` missing). |
| Firestore / Pub/Sub / GCS emulator suites (pytest 31 skips, firestore-rules suite) | Would require downloading Google emulator binaries via `scripts/python/fetch_*_emulator.py`; deliberately not provisioned (`--no-provision`) to keep the audit free of non-registry downloads. |
| Stripe / AP2 SDK / Anthropic-model tests (20 pytest skips) | Need `STRIPE_TEST_SECRET_KEY`, `STRIPE_MOCK_BIN`, `AP2_SDK_PYTHON`, `BRANDME_DEV_ANTHROPIC_API_KEY`; no credentials used by policy. Reported by the suite as `ALLOWLISTED SKIPS`, never as passes. |
| `pnpm --filter brandme-frontend test:browser`, `verify-domain-views.mjs`, `verify-visual.mjs` | Need both dev servers plus the repo-pinned Playwright 1.58.2 browser (`playwright install` prohibited). The audit's own Playwright capture (step 22) substitutes an independent observation. |
| `brandme-chain` `test:midnight:local` / `test:midnight:preprod` / `compact:fetch` | Require a local Midnight network / Preprod access / compiler download. |
| Docker Compose stack (`docker compose up`), Helm deploys | No Docker daemon; no cluster; out of scope. |
| `make install`/`make lint-core`/`make type-check-core` | Reference paths (`brandme-core/requirements.txt`, `src/`) not exercised; Makefile targets are stale relative to the tree. |

## Toolchain deviations recorded

- node v22.23.4 instead of the pinned 24.21.0 (`.nvmrc`); `engines` accepts it and every build/test passed, but `scripts/brandme.mjs setup/dev` would refuse it (`checkRuntimes()` line 100).
- `pnpm check` was run with `--no-provision` (emulator binaries not fetched). CI runs it with full provisioning plus a Spanner service container and `BRANDME_REQUIRE_EMULATORS=1`.
- The frontend runtime for screenshots used `next dev` (not `next start`) so that `NODE_ENV!=='production'` exposes the development sign-in form on `/me/connections`; the production build (step 9) was verified separately.
