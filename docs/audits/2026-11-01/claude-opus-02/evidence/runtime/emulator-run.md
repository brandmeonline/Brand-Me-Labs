# Emulator-backed Python test run (second audit, lead auditor)

**Result: `2146 passed, 20 skipped, 17 xfailed, 4 warnings in 1011.05s (0:16:51)` — exit 0.**
This is identical to the counts CI reported for the same commit in run 41091237404 (Test Core: 2146 passed, 20 skipped, 17 xfailed) and reproduces them on an independent host with the CI-strict rule `BRANDME_REQUIRE_EMULATORS=1` (any non-allowlisted skip fails the run).

| Item | Value |
|---|---|
| Revision | `ed19dc151d103b108cf972e6d37971c55d5dcf60` (worktree `wt-main`, verified before the run) |
| Command (cwd = worktree) | `python -m pytest tests -q --timeout=300 -ra -p no:cacheprovider --continue-on-collection-errors` |
| Python | 3.11.18 venv built with `uv pip install --require-hashes -r scripts/python/requirements.lock` (CI: 3.11.x, same lock) |
| Spanner | **native** gcloud component `cloud-spanner-emulator 1.5.53` via `gateway_main -hostname 127.0.0.1 -grpc_port 9010 -http_port 9020` (CI: Docker image `gcr.io/cloud-spanner-emulator/emulator:1.5.45`) — **version deviation**, no Docker daemon available |
| Firestore | repository-pinned component fetched by `scripts/python/fetch_firestore_emulator.py` (SHA256-verified), `start --host=127.0.0.1 --port=8080` |
| Pub/Sub, GCS | repository-pinned binaries fetched by `fetch_pubsub_emulator.py` / `fetch_gcs_emulator.py` (SHA256-verified), exported as `PUBSUB_EMULATOR_BIN` / `GCS_EMULATOR_BIN`; the suites start them per test as in CI |
| Env | `SPANNER_EMULATOR_HOST=127.0.0.1:9010`, `SPANNER_EMULATOR_REST=http://127.0.0.1:9020`, `FIRESTORE_EMULATOR_HOST=127.0.0.1:8080`, `BRANDME_REQUIRE_EMULATORS=1`; no credentials of any kind |
| Started / finished (UTC) | 15:37:22 / 15:54:18 |
| Logs | `logs/emulator-run-strict1.txt` (startup), `logs/pytest-emulator-strict1-tail.txt` (quarantine/allowlist blocks, short summary, final line), `logs/pytest-emulator-strict1-warnings.txt` |

## Skips (20) — all allowlisted by `tests/conftest.py SKIP_ALLOWLIST`, reported as *not run*

| Reason | Count |
|---|---|
| `stripe-mock v0.206.0 not found (STRIPE_MOCK_BIN)` | 6 |
| `AP2_SDK_PYTHON not set: official SDK oracle not available` | 6 |
| `not_run: STRIPE_TEST_SECRET_KEY absent (live Stripe test mode)` | 5 |
| `not_run: the model run needs BRANDME_DEV_ANTHROPIC_API_KEY` | 3 |

Zero emulator-related skips remained (the 761 environmental skips of the no-emulator run all executed).

## Expected failures (17) — the documented quarantine, strict xfail with declared exception types

- 12 × `tests/test_consent_graph.py`, `tests/test_provenance.py` — `google.api_core.exceptions.NotFound`: no fixture creates the legacy `Users/Assets/Owns/ConsentPolicies/ProvenanceChain` schema (owner `unowned-legacy`; "founder decision: delete or fix").
- 5 × `tests/test_wardrobe.py` — `TypeError`: `WardrobeManager.add_cube` puts `firestore.SERVER_TIMESTAMP` inside an array (`brandme_core/firestore/wardrobe.py:280`).

The suite printed `QUARANTINED: 17 tests (owner: count unowned-legacy: 17)`. No XPASS, no FAILED, no ERROR.

## Warnings (4)

Three dependency deprecation/future warnings (google.api_core Python-version notice, Starlette/httpx test-client deprecations) and one `PytestUnhandledThreadExceptionWarning` in `tests/test_commerce_purchase.py::test_two_agents_cannot_overspend_shared_budget[spanner]`: a background thread's Spanner transaction received `StatusCode.ABORTED` from the emulator during the deliberate two-agent contention and the SDK's retry path raised in that thread; the test's assertion still passed. CI reported 4 warnings for the same job; whether it was the same warning was not verified (CI log bodies were not retrieved). Treat as a test-harness observation, not an application defect.

## What this does and does not establish

- Establishes: at `ed19dc1`, the full Python suite — including every Spanner-, Firestore-, Pub/Sub- and GCS-backed test — passes under the CI-strict skip rule on an independent host with the same lock. Combined with the no-emulator run (1,422 passed) and the Node suites in `commands.md`, the **isolated local demo** tier has direct execution evidence, not only CI metadata.
- Does not establish: a composed browser → gateway → consumer-domain → worker journey (not run here; see `wiring-trace.md`), anything about staging/production, real providers, or devices. The Spanner emulator version differs from CI's pin.
- Deviation log: the first attempt was stopped after ~3 minutes because a wrong `gateway_main` flag left the REST port down (6 REST tests would have become strict-mode failures); the relaunch above is the only run reported.

## Continuation 2026-11-02 — remaining emulator-backed suites

Same worktree (`ed19dc151d103b108cf972e6d37971c55d5dcf60`, re-verified), same emulators restarted (native Spanner 1.5.53 via `gateway_main`, gRPC 9010 + REST 9020; pinned Firestore on 8080), Node 22.23.4 (pin 24.21.0; `checkRuntimes()` is only enforced by `setup`/`dev`, not by `check`/`smoke`), pnpm 10.34.6.

| Suite | Command (cwd) | Result | Log |
|---|---|---|---|
| Gateway vitest, emulator reachable | `pnpm exec vitest run` (`brandme-gateway`), `SPANNER_EMULATOR_HOST=127.0.0.1:9010`, `SPANNER_EMULATOR_REST=http://127.0.0.1:9020`, `BRANDME_PYTHON=<venv 3.11>` | **Test Files 20 passed (20); Tests 169 passed (169)**, exit 0, 46 s — the 4 files/18 tests skipped in the no-emulator run (`me.test.ts` 12, `export-backend.test.ts` 2, `consumer-domains.test.ts` 2, `read-backend.test.ts` 2) now run and pass. Matches CI's "20 test files passed". | `logs/gateway-vitest-emulator.txt` |
| Firestore security rules | `pnpm --filter @brandme/firestore-rules test`, `FIRESTORE_EMULATOR_HOST=127.0.0.1:8080`, `BRANDME_REQUIRE_EMULATORS=1` | **6 tests, 6 pass, 0 fail, 0 skipped**, exit 0, 5 s (previously skipped: emulator unreachable). | `logs/firestore-rules-emulator.txt` |
| Composed smoke (`pnpm smoke` = `node scripts/brandme.mjs smoke`, the step CI runs in Foundation check) | cwd worktree; `BRANDME_PYTHON=<venv 3.11>`, `SPANNER_EMULATOR_HOST=127.0.0.1:9010`, `SPANNER_EMULATOR_REST=http://127.0.0.1:9020`; **attempt 2 with the real pnpm (`~/.local/share/pnpm/.tools/pnpm/10.34.6/bin`) first on `PATH`** | **PASSED 7/7**, exit 0, 14 s: spanner emulator (already running) → migrations to V001 → gateway → brain → Spanner health (`gateway.spanner ok 3200 ms`, `brain.health ok 37 ms`) → dev session (labelled simulation, `X-Brandme-Simulation`) → `PATCH /me` with If-Match + CSRF (etag "2") → **profile survives gateway + brain restart** → outbox events validated + dispatched (Python: `member.created,member.updated`). | `logs/pnpm-smoke-attempt2.txt`, `logs/pnpm-smoke-attempt2-report.json` |
| Composed smoke, attempt 1 (environment artefact) | same, but with this container's default `pnpm` (`/opt/node22/bin/pnpm` → `/opt/node-tools/node_modules/.bin/pnpm` shim → re-spawned `.tools/pnpm/10.34.6`) | steps 1–5 **passed**; aborted at "gateway stopped not ready after 20s": `startServices().stop()` sends SIGTERM only to its direct child (`scripts/brandme.mjs:186`), which here was the outer pnpm shim, so `tsx src/index.ts` kept port 3001. **Not an application failure**; CI's `pnpm/action-setup` installs the exact `packageManager` version, so no nested re-spawn occurs there. The harness's final `stop()` has the same limitation (lingering gateway killed by PID afterwards). | `logs/pnpm-smoke-attempt1.txt` |

The smoke run is the first evidence in either audit of a **composed** service chain (browser-facing gateway → legacy brain → Spanner, session cookie + CSRF, restart persistence, outbox dispatch) executed outside CI. It exercises the legacy brain path and the gateway identity/`/me` routes — not the consumer-domain service (`persona.app`), not Pub/Sub ingress, not the UI. The smoke writes `docs/build/evidence/w00/smoke-latest.json` in the worktree; that tracked file was restored after each run (`git checkout --`), copied to the logs directory first.

### Canonical consumer-domain composition (gateway → `persona.app` → Spanner), 2026-11-02

Neither audit had executed the **canonical** composition — docker-compose's default profile and the Helm `consumerDomains` workload (off by default) — as opposed to CI's `dev-domains.py` harness, which mounts routers directly behind an HMAC relay. This run did, at the API level (no browser):

- Key pair: `node scripts/dev/consumer-domain-keys.mjs` with `BRANDME_DEV_ASSERTION_DIR` pointing **outside** the repository (scratchpad); the script prints only the kid. Files were sourced into the two processes' environments; never printed.
- Service: `python -m brandme_core.config preflight --service consumer_domains` ("allowed in development; simulated adapters: 0"), `python -m brandme_core.domains.persona.app --check` (`{"status":"ready"}`), then the service on 127.0.0.1:8010 (`/health` → `{"status":"ok","media":"not_configured"}`). Env names: `ENVIRONMENT`, `BRANDME_MODE`, `SPANNER_EMULATOR_HOST`, `SPANNER_PROJECT_ID/INSTANCE_ID/DATABASE_ID`, `CONSUMER_DOMAIN_ASSERTION_ISSUER=brandme-gateway`, `CONSUMER_DOMAIN_ASSERTION_JWKS`, `PORT`.
- Gateway: `./node_modules/.bin/tsx src/index.ts` (direct, no pnpm shim) with `BRANDME_MODE=development`, `IDENTITY_PROVIDER=dev`, `CONSUMER_DOMAIN_SERVICE_URL=http://127.0.0.1:8010`, `CONSUMER_DOMAIN_ASSERTION_KEY/KID`, `PUBLIC_ORIGINS`/`CORS_ORIGINS`, Spanner settings. Database: `brandme-db` migrated V001–V015 by `runner.py up --create-database`.
- Driver: `logs/canonical-chain-journey.py` (stdlib only; synthetic identities `audit-alice`/`audit-bob`), orchestrated by `logs/canonical-chain.sh`.

| Step | Result |
|---|---|
| anonymous `GET /wardrobe/items` | 401 ✓ |
| `POST /session/dev` audit-alice | 201, `assurance simulated`, `X-Brandme-Simulation` ✓ |
| `GET /me` | 200, member matches ✓ |
| **`GET /me/persona` → gateway signs ES256 assertion → service verifies → Spanner** | 200, keys `profile, axes, constraints, context_overrides, adaptation_proposals, exists` ✓ |
| `POST /wardrobe/items` (manual, Idempotency-Key) | 201, `claim_level: self_reported` ✓ |
| same Idempotency-Key replayed | 201, same id (no duplicate) ✓ |
| `GET /wardrobe/items` | 200, exactly one item ✓ |
| **`GET /recommendations`** | 200 with **0 items** (`basis`, `exclusions_honored`, `profile_version` present) — **F-ARCH-003 confirmed at runtime** ✓ |
| `GET /rewards` | 200, account all zeros, version "0" ✓ |
| `POST /session/dev` audit-bob | 201, distinct member ✓ |
| bob `GET /wardrobe/items/<alice-item>` | 404 (isolation) ✓ |
| bob `GET /wardrobe/items` | 200, empty ✓ |
| command without `X-CSRF-Token` | 403 ✓ |
| command with foreign `Origin` | 403 ✓ |
| `DELETE /session` | 204 ✓ |
| `GET /me` after sign-out | 401 ✓ |

**16/16 passed** (run 2, 02:23:34–02:23:46 UTC). Run 1 failed 7 forwarded steps with HTTP 500 because my bash driver sourced compose-style `KEY="…\n…"` without expanding `\n` (compose's `env_file` does); the gateway's `importPKCS8` then failed. Driver defect, fixed with `printf '%b'`; recorded for honesty. Services were stopped by PID; ports 3001/8010 confirmed closed. Gateway log noise: a `MetadataLookupWarning` from the Spanner client's GCE metadata probe (no credentials present) — harmless with the emulator.

What this does and does not show: the canonical persona/wardrobe/rewards API path is **operational** at `ed19dc1` with the documented dev key pair and emulator; no browser UI, no social decision/reward settlement (needs the uncomposed jobs/ingress — F-ARCH-002 unchanged), no media (bucket unset → routes unmounted), simulated identity only.

### Full Foundation gate: `pnpm check` with provisioning, 2026-11-02

`node scripts/brandme.mjs check` (no `--no-provision`), `BRANDME_REQUIRE_EMULATORS=1`, real pnpm 10.34.6 first on `PATH`, `BRANDME_PYTHON=<venv 3.11>`, Spanner gRPC/REST reachable (native 1.5.53), Firestore reachable (pinned), `PUBSUB_EMULATOR_BIN`/`GCS_EMULATOR_BIN` pointing at the SHA256-verified pinned binaries (so the check downloaded nothing). 02:19:31–02:38:22 UTC, exit 0.

| Step | Result |
|---|---|
| workspace + toolchain governance | ✓ 1.5 s |
| spec package validator | ✓ |
| contract + token drift | ✓ 7.2 s |
| credential manifest | ✓ |
| guard self-tests | ✓ 7.9 s |
| packages type-check / tests (incl. Firestore rules, verified ran) | ✓ / ✓ |
| gateway lint / type-check / tests (emulator suites included) | ✓ / ✓ / ✓ 27.2 s |
| python tests (tests/) | ✓ 1070 s — **`2146 passed, 20 skipped, 17 xfailed, 4 warnings in 1068.13s`**, `QUARANTINED: 17`, allowlisted skips 6+5+3+6 |
| docs/build links | ✓ |

This is the repository's own Foundation gate, the job CI calls `foundation-check`, reproduced in full on an independent host with the same lock, the same pins for Firestore/Pub/Sub/GCS and the same strict skip rule. Only the Spanner emulator version (1.5.53 native vs 1.5.45 image) and Node (22.23.4 vs 24.21.0, not enforced by `check`) differ. Log: `logs/pnpm-check-full.txt`.

### Hand-composed workers: decision → outbox → Pub/Sub → ingress → reward, 2026-11-02

F-ARCH-002 (both audits) says no deployable topology composes the processes that close decisions and settle rewards. To establish whether that gap is missing *code* or missing *configuration*, the three canonical processes were composed by hand with environment variables only — no source changes — around the canonical API chain above:

- Pub/Sub: the repo-pinned emulator on 127.0.0.1:8085; three topics `brandme-development-{public,member-private,restricted}-<suffix>` and one subscription `brandme-development-consumer-lane-<suffix>` on the member-private topic, created through the emulator's REST API (the same shape `tests/test_persona_lane_events.py` uses).
- Processes: `python -m brandme_core.events.worker --check` / `--once`; `python -m brandme_core.domains.persona.ingress --once` (×6); `python -m brandme_core.domains.persona.jobs --once`. Env names: `ENVIRONMENT`, `BRANDME_MODE`, `SPANNER_*`, `PUBSUB_EMULATOR_HOST`, `OUTBOX_PUBSUB_TOPIC_PUBLIC/MEMBER_PRIVATE/RESTRICTED`, `LANE_PUBSUB_SUBSCRIPTION`.
- Driver: `logs/workers-chain-journey.py` orchestrated by `logs/workers-chain.sh` (synthetic identities `audit-alice-w`, `audit-bob-w`).

| Step | Result |
|---|---|
| two dev sessions; alice adds a wardrobe item | ✓ |
| alice invites bob (`POST /relationships` → `relationship_id`, 201); bob accepts (state `accepted`) | ✓ |
| alice creates a decision (`subject_type: wardrobe_item`, 1 recipient, 300 s, blind) → 201, state `open`; `closes_at − opened_at` = 300.0 s | ✓ |
| bob responds `pass`; alice closes early → `state: closed`, result `{yes 0, pass 1, alternative 0}` | ✓ |
| bob's rewards before any worker: `available 0` | ✓ |
| `events.worker --check` → `{"status":"ready","transport":"pubsub_emulator","event_contracts":54,"catalogs":{commerce-agents, consumer-domains, foundation: loaded}}` | ✓ |
| `events.worker --once` → `{"status":"dispatch","delivered":13,"failed":0,"dead":0,"stale":0}` | ✓ |
| `persona.ingress --once` ×6 → first run `{"processed":3,"not_subscribed":7,"status":"applied"}`, then `{"not_subscribed":1}`, then nothing — **re-runs applied nothing (inbox dedupe held)** | ✓ |
| `persona.jobs --once` → `{"decisions":{"closed":0,"skipped":0},"reservations":{"released":0},"fulfillment":"not_configured","media":"not_configured","status":"ran"}` | ✓ |
| **bob's reward after settlement: `available 10, lifetime_earned 10`** (= one `friend_decision_response` credit, not 6) | ✓ |
| alice's account readable: `available 25` (a rule credited the asker for something in the flow; which rule was not traced — recorded, not asserted) | ✓ |
| bob has 2 unread in-app notifications | ✓ |
| alice blocks bob → bob's `GET /decisions/<id>` → 404 | ✓ |

**18/18 passed**, 02:38:35–02:38:58 UTC; all processes stopped by PID, ports 3001/8010/8085 confirmed closed. `jobs --once` closed 0 decisions because alice had already closed early; the deadline-expiry path was not exercised (it would need a 300 s wait or clock control).

**Consequence:** the decision/reward loop that CI's `dev-domains.py` harness simulated with an in-process dispatcher works through the **canonical** publisher, broker, subscriber and scheduler processes with configuration alone. F-ARCH-002 stands as a *deployment* gap (no compose service, no Helm workload, no emulator services in compose — SC-46), not an implementation gap; WP-05 is wiring and manifests, not domain code. Not shown: the browser UI on top of this chain; deadline expiry via `jobs`; Pub/Sub retry/dead-letter under fault; production Pub/Sub.
