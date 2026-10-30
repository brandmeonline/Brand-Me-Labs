# Lane brief: opus-foundation

**Bench:** Opus 5.5 (Claude Code) · **Branch:** `bench/opus-foundation-20261005`
**Base:** `docs/brandme-full-experience-2026-10-05` · **Spec:** `docs/design/brandme/` + `contracts/`
**Work packages:** W00 (audit, executable baseline, honest modes) + W01 contracts/workspace/tokens + W02 (persistence, auth, privacy boundaries)
**Position in merge order:** FIRST. All other lanes wait on this lane's merge.

## What you are building
The foundation every other lane stands on: an honest executable baseline, the shared contract packages, the design-token package, the persistence framework, auth/session middleware, the event outbox/inbox framework, mode configuration, and the required developer commands. Read `docs/design/brandme/06-delivery-verification.md` §1–§2 and the root `CLAUDE.md` before touching code.

## You own exclusively (no other lane may touch these)
- `docs/build/` — create `implementation-status.md`, `compatibility-lock.md`, `deviations.md` (these two files are parent/Lane-1-only; other lanes propose deviations via their own status files)
- `packages/` — all three: `contracts` (OpenAPI 3.1 + generated TS/Python types from `contracts/domain.schema.json` + ch.03), `design-system` (tokens generated from `contracts/design-tokens.json`), `provider-contracts` (interfaces only; Lane 3 extends after you merge)
- `pnpm-workspace.yaml`, root `package.json`
- `docker-compose*.yml`, `Makefile`, `.github/workflows/`
- `brandme-data/spanner/migrations/` — migration ledger + runner + `V001_identity.sql` ONLY (members/identity/sessions/consent). Reserve numbers V002–V009 for other lanes (see below); do not create them.
- `brandme_core/domains/` — framework files only: `__init__.py`, `base.py`, `events.py`, plus per-domain reservation READMEs for `persona, wardrobe, social, rewards, commerce, providers, rights, privacy, media` (READMEs only, no logic)
- `brandme_core/events/` (event envelope framework), `brandme_core/config.py` (mode definitions: `BRANDME_MODE` demo/development/sandbox/production)
- `brandme-gateway/src/routes/v1/` — `index.ts` mount file + `me.ts` ONLY. Other lanes ship unmounted router files; you (or the parent at integration) mount them.
- `brandme-gateway/src/middleware/`, `brandme-gateway/src/types/`
- `.env.example`, `tests/conftest.py` + `tests/fixtures/` (framework only), `scripts/` (implement the required pnpm commands from ch.06 §3 as scaffolds)

## Read-only for you
`docs/design/brandme/**`, `contracts/**` (the spec — never edit; deviations go in `docs/build/deviations.md`).

## Migration number reservations (do not use another lane's number)
V002 persona · V003 wardrobe · V004 social · V005 rewards · V006 providers · V007 commerce · V008 rights · V009 privacy

## Exit evidence (from ch.06 §2, W00–W02)
- Clean install/boot from a fresh checkout, documented; port map applied (consumer 3000, gateway 3001, console 3002, brain 8000, policy 8001, orchestrator 8002, cube 8007 — update compose/proxy/env together, no service infers another's port)
- Actual baseline test report (run existing tests, record failures honestly — old passing claims are not evidence)
- Mode-guard negative test: production boot fails closed when a required real adapter is missing; demo adapters carry visible simulation labels; all trust-path fixtures enumerated (fake chain hashes, fake proofs, constant ESG, fake commerce IDs, default reprint eligibility, auth shortcuts) and confined to demo adapters
- Migration runs from empty schema to V001; typed API clients generated from `domain.schema.json`; `compatibility-lock.md` pinned (exact Node/pnpm/Python/Next/React/TS/Three/R3F/Motion/model-viewer/MediaPipe/Midnight versions + check date); lockfiles committed — never "latest"

## Status protocol
- Record status ONLY in this file (`docs/build/status/opus-foundation.md`). Never edit `docs/build/implementation-status.md`.
- Other lanes will request design tokens and dependency pins via their status files — collect and publish them at integration.
- Note: the acceptance catalog has zero requirements staged at W01/W02 — define your exit evidence from ch.06 §2 prose and propose catalog additions in this file.

## Global rules (all lanes)
Never edit another lane's owned files. Never edit `docs/design/brandme/**` or `contracts/**`. Fixtures stay in per-lane `tests/fixtures/<domain>/`. No `latest` tags — pin everything. Demo adapters carry visible simulation labels. Production boot fails closed.

---

# Status log (opus-foundation lane)

**Last updated:** 2026-10-05 · **Working branch:** `claude/opus-foundation-w00-2hgiw5` (the session harness designates it; `bench/opus-foundation-20261005` points at the same base `e4f1342`) · **PR:** brandmeonline/Brand-Me-Labs#33 (draft, base `bench/opus-foundation-20261005`)
**Baseline reconciliation:** HEAD at start = spec baseline `0f5f58a` + docs-only `4511236`, `e4f1342`. No application code drifted from the audited baseline.

## Exit evidence (brief §"Exit evidence")

| Brief item | State | Evidence |
|---|---|---|
| Clean install/boot from a fresh checkout, documented; port map applied | **Done** for HTTP client → gateway → brain → Spanner. The consumer UI → gateway link is not done (consumer lane) | `docs/build/local-setup.md`, `docs/build/evidence/w00/fresh-checkout.md` (clone of `63df43f`, cold emulator: setup/smoke/check/build exit 0) |
| Actual baseline test report | **Done** | `docs/build/evidence/w00/baseline-test-report.md` (3 of 18 root tests pass at baseline; findings F1–F16 classified) |
| Mode-guard negative test (production fails closed); simulation labels; trust-path fixtures enumerated and confined | **Done** for enumeration, labels and refusal. **Not done:** physically moving fixtures into demo adapters. Each fabricating service is registered as a simulated adapter and refused in sandbox/production. Rewriting the fakes belongs to the owning lanes | `brandme_core/config.py`, `tests/foundation/test_mode_guard.py` (47), `brandme-gateway/src/middleware/mode.test.ts` (7), `docs/build/evidence/w00/trust-path-fixtures.md` |
| Migration empty → V001 | **Done**, plus baseline (legacy schema) → V001, rerun no-op, checksum drift / out-of-order / partial-failure refusal | `brandme-data/spanner/migrations/`, `tests/foundation/test_migrations.py` |
| Typed API clients generated from `domain.schema.json` | **Done**: OpenAPI 3.1 (73 operations, ch.03 inventory), TS types, openapi-fetch client, pydantic models, drift check in `pnpm check`. *Correction 2026-10-24:* the drift check was not in `main`'s CI until round 3 (`foundation.yml` was dropped at `2eac4d7`); it now runs in the `Foundation check` job | `packages/contracts`, `tests/foundation/test_contract_models.py` |
| `compatibility-lock.md` pinned; lockfiles committed; never "latest" | **Done** | `docs/build/compatibility-lock.md`, `pnpm-lock.yaml` (pnpm 10.34.6), `scripts/python/requirements.lock` (hashed), `.nvmrc` |

## Acceptance catalog (W00 IDs; results in `docs/build/evidence/results.json`)

| ID | Result | Why |
|---|---|---|
| BM-BASE-001 | **blocked** | Gateway/domain/persistence boot verified from a fresh clone; the consumer app has no gateway client yet (consumer-ui lane) |
| BM-BASE-002 | **passed** (re-verified 2026-10-24) | Strict modes refuse every simulated trust-path service, stub flags, the dev identity provider, shared-secret JWT and symmetric algorithms. *Correction:* until round 3 only the compose preflight enforced this; a production-mode orchestrator started without compose served a fabricated `cardano_tx_` hash. Now enforced in-process (`brandme_core/boot.py`, `tests/foundation/test_boot_guard.py`) |
| BM-BASE-003 | **passed** | Baseline report + this status file |
| BM-BASE-004 | **passed** | All four apps + packages build from the frozen lockfile on Node 24.21.0 / pnpm 10.34.6. Frontend is still Next 14.0.4 (target 16.3.8 is the frontend lane's) |
| BM-BASE-005 | **failed** | Gateway half fixed 2026-10-24 (`POST /scan` 503 problem+json without NATS, `GET /scan/:id` 501). Still open: `/shop`/`/stash` are not redirected (frontend lane); `/scan` publishes outside the outbox |

All other 145 IDs are `not_run` (`pnpm evidence:report`).

## Stage W00 — done (except items above)
- `BRANDME_MODE` (demo/development/sandbox/production; required, no default) + `python -m brandme_core.config preflight --service X`. Compose runs it before every Python service.
- `ENABLE_STUB_MODE` default flipped to false. Stub flags are refused in strict modes.
- Compose rewritten (the old file did not parse) with the port map: consumer 3000, gateway 3001, console 3002, brain 8000, policy 8001, orchestrator 8002, knowledge 8003, compliance 8004, identity 8005, governance 8006, cube 8007. It is config-validated only; the container boot was not executed.

## Stage W01 — done for foundation scope
- Workspace: `brandme-gateway`, `brandme-chain`, `brandme-console`, `brandme-frontend`, `packages/*`. Pins Node 24.21.0, pnpm 10.34.6 (`engineStrict`), TS 5.9.3.
- `packages/contracts`, `packages/design-system` (tokens + dark + reduced motion; AA contrast for 18 pairs), `packages/provider-contracts` (interfaces + `assertAdapterAllowed`).
- **Not done here (D-004):** UI primitives, app shell, component gallery, fonts; W01 viewport/keyboard/320 px exit evidence. Owner: consumer-ui lane.

## Stage W02 — framework done; some ch.06 W02 items open
Done:
- Migration ledger/runner + V001 (identity + platform tables, D-001).
- `brandme_core.events`: envelope + closed-payload registry + forbidden-key filter, outbox writer, lease dispatcher with backoff/dead-letter, inbox dedupe.
- `brandme_core.domains`: Principal, deny-by-default `authorize` (block override, expiry, revocation; 404 for hidden), If-Match, canonical digest, `run_command`, `run_idempotent_command`, data-category registry. Reserved READMEs for persona … media.
- Emulator tests: a retried transaction commits exactly one outbox event; failed commands write nothing; at-least-once dispatch is applied once via the inbox; idempotent replay; key reuse returns 409; 5 concurrent duplicates apply once.
- Gateway identity boundary: server-side sessions (hashed secret + CSRF in Spanner), JWKS-verified OIDC bearer (iss/aud/asymmetric algs) mapped to members, `/api/v1` with problem+json and request-id/environment headers, `GET/PATCH /me` (If-Match, contract-validated), `/system/health`, labelled dev session (404 in strict modes). Cross-mode sessions are rejected. 10 emulator tests: restart + second-session persistence, CSRF/origin, 409/428, member isolation, token rejection cases.
- Commands: `pnpm setup:demo | dev:demo | dev | smoke | check | migrate | evidence:report`. `test:journeys`, `test:providers`, `test:midnight:*` and `assets:validate` exit 2 ("not implemented yet").
- CI: new `.github/workflows/foundation.yml` (emulator service; check + smoke + builds + production refusal). Existing workflows were moved to `.nvmrc`/`packageManager`. *Correction 2026-10-24:* `foundation.yml` never reached `main` (dropped at the W11 merge `2eac4d7`, "token lacks workflow scope"); round 3 restores the gate as the `Foundation check` job in `ci-cd.yml`.

Open (proposed for parent / later lanes):
- Firestore projection framework + security rules + revocation test (ch.06 W02 "projection revocation works"): done in round 2 (#53). Custom-token minting and a projection worker are still open.
- Media upload quarantine and provider connection records: **not started** (media/providers lanes per reservations).
- Export/deletion jobs: only the data-category registry exists. V009 privacy owns the job tables.
- Redacted-log middleware: done for the gateway (round 2) and Python (round 3, `brandme_core/logging.py`).
- Backfill of the two legacy persona columns: persona lane (V002).
- Browser OIDC code flow (D-005): gated on the OIDC tenant.

## CI state (PR #33, head `dc4b62b`)
- Green: Foundation `check` (check + smoke + builds + production refusal), Test Gateway, Test Chain, Test Core, regression, Security Scan.
- Red: **Trivy code scanning** (65 alerts). They appear now because the SARIF upload succeeds for the first time after moving to `upload-sarif@v3` + `security-events: write`. All of them are in manifests this PR does not change: python-jose/aiohttp pins, agentic ML pins, Dockerfiles, terraform, and Next 14.x (the base lockfile already had `next@14.2.33`). The critical/high npm alerts clear with the Next 16.3.8 / React 19.3.0 migration (frontend/console lanes). Reproduced locally with Trivy 0.69.1; owners proposed in the PR comment.
- Fixed in CI: an intermittent Spanner session leak in the gateway store (`runTransactionAsync` → explicit begin/commit/end with ABORTED retry; 0/8 failures after, 2/5 before).

## Cross-lane edits (flag for review; details in `docs/build/deviations.md` D-002)
`brandme_core/spanner/pool.py` (additive `database` property; fixes 49 call sites), `brandme-gateway/src/index.ts`, `src/config/index.ts`, `package.json`, `vitest.config.ts`.

## Proposed acceptance-catalog additions (W01/W02 have zero IDs)
- BM-FND-001 (W01, integration): `pnpm contracts:check` fails on any drift between `domain.schema.json`/`design-tokens.json` and generated artifacts. **Passing** (`pnpm check`).
- BM-FND-002 (W02, integration): a migration runs from empty and from the baseline schema; an edited applied migration is refused. **Passing**.
- BM-FND-003 (W02, integration): a retried command transaction commits exactly one outbox event; redelivery applies once via the inbox. **Passing**.
- BM-FND-004 (W02, security): `/api/v1` mutations without a session CSRF token or with a foreign Origin fail with 403; a stale If-Match gets 409. **Passing**.
- BM-FND-005 (W02, integration): a profile saved in one session survives a gateway+brain restart and is visible from a second session. **Passing** (gateway test + smoke).
- BM-FND-006 (W02, security): revoking a share removes shared Firestore projections. **Not run** (projection framework not built).

## Requests to other lanes
- **consumer-ui:** add a gateway client using `@brandme/contracts` (`createBrandmeClient`), import `@brandme/design-system/tokens.css`, implement the `/shop`→`/discover` and `/stash`→`/closet` redirects, and upgrade Next/React to the compatibility-lock targets.
- **All Python lanes:** wrap commands in `run_command`/`run_idempotent_command`; register events in `brandme_core.domains.events`; remove your service's `LEGACY_SIMULATED_ADAPTERS` entry only with replacement evidence.
- **Owner of `routes/scan.ts`:** return 503 problem+json when NATS is unconfigured; persist scan operations.
- **Parent:** apply the `.gitignore` negations in D-003.

## Resume instructions
1. `pnpm setup:demo && pnpm check && pnpm smoke` (needs Docker or a local Spanner emulator).
2. Read this file, `docs/build/deviations.md` and `docs/build/compatibility-lock.md`.
3. Next foundation items, if the parent keeps them in this lane: the Firestore projection framework + rules + revocation test (BM-FND-006), the redacted-log middleware for legacy routes, and export/deletion job scaffolding on top of `data_categories()`.

## Merge record (2026-10-05)

PR #33 merged into `bench/opus-foundation-20261005` at `25dff5c8` per founder approval (API merge of the draft required marking it ready-for-review first via GraphQL). The 8 working-branch commits (W00 honest baseline, W01 contracts/workspace/design tokens, W02 persistence/auth/privacy) are now on the bench branch. CI failures at merge time are systemic (fail on `main`, owned by PR #30), not lane-caused. Downstream lanes were notified via comments on PRs #32, #34, #35; the two Astra lanes (no open PRs) will see the merge via the bench watch digest. W00–W02 deliverables are complete *(correction 2026-10-24: overstated; see the open items above and the round-3 gap list)*; remaining foundation-adjacent work is the repo-wide CI repair (PR #30) and the Trivy dependency findings, both outside this lane's ownership.

## Round 2 (2026-10-23): remaining foundation items

**Branch:** `claude/opus-foundation-w00-2hgiw5`, restarted from `main` at `5174ec2`. PR #33 was merged, and the bench branch is in `main`.

| Item from "Resume instructions" | Outcome | Evidence |
|---|---|---|
| Firestore projection framework | **Done.** `brandme_core/events/projections.py`: field-allowlisted specs; private-field refusal for shared docs; monotonic `source_version`; revocation tombstones that block resurrection; `purge_member`; reducer registry | `tests/foundation/test_projections_emulator.py` (7) |
| Security rules | **Done.** `packages/firestore-rules/firestore.rules`: member-only private reads, audience-only `get` before expiry for shared docs, no listing, no client writes, tombstones closed | `packages/firestore-rules/test/rules.test.ts` (6). With an allow-all negative control, 5 of 6 fail |
| BM-FND-006: revoking a share removes shared projections | **Passing** on the emulator: server revoke → audience `get` denied; an older delayed upsert returns `revoked`; a superseded revoke does not delete a newer re-share | both suites above |
| Redacted logs for legacy routes | **Done** at the logger: `REDACT_PATHS` in `brandme-gateway/src/config/logger.ts` covers `scanner_user_id`, `garment_tag`, user/member IDs, email and CSRF/session headers (top-level and nested). `routes/scan.ts` itself is unchanged | `brandme-gateway/src/middleware/redaction.test.ts` (2). Without the logger change both fail |
| Export/deletion job scaffolding on `data_categories()` | **Already delivered by the midnight-rights lane** (V009, `brandme_core/domains/privacy/*`, `foundation_bridge.py` walks `data_categories()`). Not duplicated | `main` |

CI: the `test-core` job now fetches the pinned Firestore emulator 1.22.0 (SHA-256 verified), runs the projection tests with `BRANDME_REQUIRE_EMULATORS=1` (a missing emulator fails instead of skipping), and runs the rules suite, failing on any skip. `pnpm check` warns when Firestore is unreachable.

Dependency note: `firebase` (dev-only) pins `@grpc/grpc-js ~1.9`, which has a high and a low advisory. An override in `pnpm-workspace.yaml` moves it to the workspace's existing 1.14.6. The `pnpm audit` advisory set is identical to `main`; `--prod` and `--audit-level=critical` both pass.

Local verification on this branch (Spanner emulator 1.5.45, Firestore 1.22.0, Pub/Sub 0.8.37):
- CI's Python set: 281 passed, 0 skipped.
- Gateway: 62 passed, plus lint and type-check.
- Packages: 36 passed, 0 skipped.
- `pnpm check`: all green.
- Contract drift: none.

Still open:
- The gateway does not mint Firebase custom tokens (uid = member_id) yet, so clients cannot sign in to Firestore. The rules are ready for when it does.
- No domain reducers are registered yet. Owning lanes add them alongside their events.
- `routes/scan.ts` still returns 500 without NATS (BM-BASE-005, not this lane's file).

Codex review on PR #53 (2026-10-23). Six findings:
- **Fixed (five):**
  - Purged members can no longer be recreated by delayed events (member-wide marker).
  - Private-field checks now normalize names (`ownerId`, `walletAddress` and similar).
  - Shared views are stored per recipient, so the audience list is no longer readable.
  - Shared paths are restricted to the shape the rules serve.
  - Expiry timestamps must be timezone-aware.
- **Addressed by contract (one):** for version gaps, `Upsert` is documented and used as a full-snapshot replace, so a skipped version cannot leave a view partial.
- **Guard fixed:** the rules suite now fails rather than skipping when an emulator is required, and CI also rejects a zero pass count.

Evidence: projections 18 passed; rules 6 passed; CI Python set 292 passed, 0 skipped.

## Round 3 (2026-10-23/24): ultra plan — honest CI, workspace governance, GKE packet, secrets, W00–W02 gaps

**Branch:** `claude/opus-foundation-w00-2hgiw5`, rebuilt on `main` `48686d2` after #53 merged (`1f0d738`). **PR #58** (draft until this packet). Built as six isolated packages, each re-verified by an independent skeptic, then a six-lens adversarial review of the integrated diff with a skeptic per lens; every finding was reproduced before it was fixed.

### What was built

| Plan item | Outcome | Evidence |
|---|---|---|
| 1. Land #53 | **Merged** `1f0d738` (2026-10-23 18:06Z) | `main` |
| 1. Honest CI (commerce S9) | The `\|\| echo` masks S9 cited were already gone on `main` (#42). CI was still dishonest: hand-picked test list (15 of 21 root test files never ran), the foundation gate never reached `main`, Security Scan could not fail, a `tee` without pipefail hid the #53 rules step. Now: `test-core` runs **all of `tests/`**; known-broken tests are a strict-xfail **quarantine with owner + blocker** (`tests/conftest.py`), an unregistered xfail fails; under `BRANDME_REQUIRE_EMULATORS=1` any skip outside an owned allowlist fails; workflow-wide pipefail; **Foundation check** job (`pnpm check` + `pnpm smoke`) gates image publishing; blocking digest-pinned Trivy CRITICAL + repo-wide secret scans; the 4 S9 pins in the hashed lock (hashes byte-identical to S9) | Local, all emulators required: 606 passed, 3 allowlisted skips, 45 quarantined (before: 33 failed, 15 errors). CI on `0e66e46`: 19/19 success + deploy skipped |
| 2. Toolchain governance | `scripts/check-workspace.mjs`: fails on an unregistered `package.json` (which `pnpm --frozen-lockfile` does not catch), missing/orphan/stale lockfile importers, pnpm/Node pin drift, nested lockfiles, root `pnpm` field. Runs in the `Workspace guard` workflow (no branch filter), module-regression and `pnpm check`/`setup`. Process + the 2026-10-23 astra/PR #55 root-cause chain + merge-conflict resolutions in `docs/build/workspace-governance.md` | 34 self-tests; flags the historical failures (a37ec2b, 5acc8ee, PR #55 head) |
| 3. GKE deploy packet | `docs/build/deploy/gke-verification-packet.md`: what exists (A), what is missing (G1–G27), ordered founder actions with exact gcloud commands (C), deploy-job patch (E, **applied** but gated by `vars.BM_DEPLOY_ENABLED`). New chart `brandme-infra/helm/brandme`; core image `runtime` stage from the hashed lock. **Nothing is deployed; cluster existence in lux-realestate-app/us-east1 is unconfirmed** (gcloud 401 here) | `scripts/validate-helm.sh` (helm lint, kubeconform on K8s 1.35/1.36, 18 negative cases, env contract against the processes' own validators); `Deploy manifests` workflow; core + gateway images built and smoke-tested as CI builds them |
| 4. Secrets scaffolding | Naming conventions (`docs/build/security/secrets-conventions.md`), credential manifest (43 rows, names only) + checker in `pnpm check`, per-lane sandbox identities (`docs/build/security/lane-service-accounts.md`, `scripts/provision/gcp-dev-identities.sh`: dry run by default, refuses production and shared projects, deploy and image-push identities in separate WIF pools pinned to the repository id), rotation runbook stub (`docs/build/runbooks/credential-rotation.md`). Tracked legacy `.env.development/.staging/.production` deleted (read by nothing) | checker + 46 self-tests |
| 5. W00–W02 gaps | In-process boot guard for every legacy service, agents service, worker and the read/export APIs (BM-BASE-002 was recorded passed while a production orchestrator served a fake `cardano_tx_` hash); trust inventory refreshed (Midnight SANDBOX, Cardano UNCONFIGURED; foundation-era processes registered); Python log redaction; gateway rate limiter (config-driven, problem+json 429 + Retry-After, per-member + per-address, `TRUST_PROXY`, essential-access exemptions, bounded store), request-ID validation, `/scan` 503/501, 409 → `ETag`, strict mode refuses emulator hosts, missing/duplicate service tokens and plaintext JWKS/CORS | `tests/foundation/test_boot_guard.py`, `test_mode_guard.py`, `test_logging_redaction.py`; gateway 114/114 |
| Found on the way | New advisories turned `main` red (zod high, body-parser high, fast-uri): zod 4.6.7 (no 3.x fix) + two scoped overrides. `google.api_core` began warning on 2026-10-24 that Python 3.11 reaches EOL in a year; the core image smoke now compares stdout only | `pnpm audit --prod` clean |

Commits: `7810282` CI, `4408e15` workspace guard, `fc0e406` secrets, `9bc9a40` GKE, `295c241` boot guard, `6875ed9` gateway, `8a1cf46` wiring, `123a069` advisories, `0e66e46` smoke fix, `dda1f77` review fixes, plus this status commit.

### Credential manifest (founder authority, plan §FOUNDER AUTHORITY)

**Credentials created by this lane this round: none.** No GCP credential works from this environment (`gcloud` returns 401) and the GitHub secrets/variables/environments APIs return 403 through the proxy, so no service account, key, secret, variable or environment was created. Everything needed is scripted or listed for the founder:

| What | Where it will live | Created? | How |
|---|---|---|---|
| Per-lane sandbox service accounts (11, incl. `bm-sbx-fnd-deployer`, `bm-sbx-fnd-pusher`) | GCP sandbox project, no keys | no | `scripts/provision/gcp-dev-identities.sh --project P --github-repo-id 1083300600 --apply` |
| WIF pools `github-deploy`, `github-push` | GCP | no | same script |
| Secret Manager containers (empty) for the 4 service tokens + Blockfrost | GCP | no | same script; values via `gcloud secrets versions add` (runbook) |
| Repo variables `BM_GCP_*`, `BM_DEPLOY_ENABLED` | GitHub (not secrets) | no | packet C-17 |
| Every secret name code reads, incl. planned lane names (Stripe test, model keys, Vertex token) | `docs/build/security/credential-manifest.yaml` | names only | `node scripts/check-credential-manifest.mjs` |

### Still open after round 3
- Branch protection is unreadable here (403); `Foundation check` and `Workspace guard` are not yet required checks.
- `build-images` still publishes with `GCP_SA_KEY` until the pusher identity exists (packet G24).
- Five fixable CRITICALs are baselined in `.trivyignore.yaml` until 2026-11-30 (python-jose ×2 and sentence-transformers are unused pins; anyio and certifi need a fastapi upgrade).
- W02: `/me/consents`, `GET /capabilities`, Firebase custom tokens + projection worker, PD-07 principal transport, PD-12 scopes, media quarantine, outbox slow lane/re-drive, migration ordering.
- Merge impact on open lanes is documented: PR #51 must delete its quarantine entries and pin `anthropic`/`stripe` (strict xfail and skip→fail enforce it); PR #52 and both astra lanes resolve the conflicts listed in `docs/build/workspace-governance.md`.

## Check-in packet (2026-10-24) — stop point before any prod-scoped or irreversible step

**(a) Evidence:** the table and commits above. What runs end-to-end today: HTTP client → gateway → brain → Spanner → outbox → Pub/Sub emulator (`pnpm smoke`, passed 2026-10-24), plus every suite in `pnpm check` against the emulators. Nothing runs in a cloud project.

**(b) 21 questions, each with my recommended default.** Answer "defaults" to take all of them.

*Direction*
1. **Deploy target.** ADR-06 makes Cloud Run the initial target; you asked for GKE. Which first? — *Default: GKE sandbox as you asked, the chart and packet are ready; Cloud Run stays the fallback reusing the same image, identities and secrets.*
2. **GCP project.** Keep `lux-realestate-app` (shared, named for real estate) or create a dedicated `brandme-sandbox` project? — *Default: dedicated project; one project per mode.*
3. **First strict environment.** Deploy `BRANDME_MODE=sandbox` on Midnight Preprod only; production stays refused until a Mainnet adapter is authorized. — *Default: yes.*
4. **Framework tuple.** Apps are on Next 15.5.28 / React 18; the spec says Next 16.3 / React 19; the spatial lane tested React 19.1.1 / R3F 9.4.0. — *Default: record Next 15 as an interim deviation, then one foundation PR moves the workspace to React 19 using the spatial lane's tested tuple after #56 and #36 land.*
5. **Python 3.11 end of life (2027-10-24; Google libraries warn from today).** — *Default: one foundation PR to Python 3.12 in Q1 2027; nothing now.*
6. **Legacy services and tests** (brain/policy/orchestrator/cube/governance; the quarantined consent-graph/provenance/wardrobe suites). — *Default: keep them refused in strict modes; delete the unowned legacy tests on 2026-11-30 unless a lane claims them.*
7. **Legacy deploy paths** (`deploy-brandme.sh`, `agents/*.sh`, `scripts/deploy.sh`, Makefile deploy targets, `infrastructure/helm/brandme`, `brandme-infra/terraform`, the umbrella chart). All verified non-functional. — *Default: retire them in one PR that also updates CLAUDE.md's kill-list.*

*Integration & security*
8. **Required checks.** Make `Foundation check`, `Workspace guard`, `Test Core` and both Security Scans required on `main` (needs repo admin; I cannot read or set protection). — *Default: yes, after one green run on `main`.*
9. **Trivy baseline (expires 2026-11-30).** — *Default: foundation removes the three unused vulnerable pins and upgrades fastapi/anyio/certifi in November; HIGH severity becomes blocking after that.*
10. **Keyless image push.** After you run the provisioning script, switch `build-images` to `bm-sbx-fnd-pusher` and delete `GCP_SA_KEY`. — *Default: yes.*
11. **Secrets into pods.** GKE Secret Manager sync add-on, External Secrets, or CI-created Secrets? — *Default: the GKE secret sync add-on.*
12. **PD-07 principal transport.** Replace the static service tokens + `X-Subject-Ref` (any token holder can act as any member) with the audience-bound ES256 assertion the commerce lane built. — *Default: yes; foundation implements it right after #51 lands.*
13. **PD-12 scopes.** A session scope policy covering wardrobe/outfits/social/rewards (with `rewards:write`)/commerce, operator scopes behind role + aal2, `rights:*` gated by assurance. — *Default: yes.*
14. **OIDC for sandbox.** Google Identity Platform as issuer, the same tenant minting Firebase custom tokens for Firestore projections. — *Default: yes.*

*Scope & sequencing*
15. **Merge order.** — *Default: #58 first, then #52 (one `ci-cd.yml` conflict, keep both jobs), #51 (must drop its quarantine entries and lock `anthropic`/`stripe`), then #56 and #36.*
16. **Migration numbering.** Lane migrations V003–V005 sort below the applied V014, and the runner refuses out-of-order migrations in sandbox. — *Default: renumber unmerged lane migrations above the current maximum before the first cloud `runner.py up`; retire the fixed reservation table.*
17. **Commerce dependencies.** `anthropic` and `stripe` are not in the hashed lock. — *Default: foundation adds them to `requirements.in` in #51's merge, pinned and hashed.*
18. **Router mounting (W11).** — *Default: one foundation integration PR mounts the lane routers after #51 and #52 land.*
19. **Next foundation build (round 4).** — *Default order: PD-07 → PD-12 → `/me/consents` → `GET /capabilities` → Firebase custom tokens + projection worker.*
20. **Rate limits across replicas.** Buckets are per process. — *Default: one gateway replica in sandbox; a shared store (Memorystore) before production.*
21. **Unowned files.** `.gitignore`, `CLAUDE.md`, service Dockerfiles, `brandme-infra/`, `routes/scan.ts` have no owning lane. — *Default: foundation owns them, enforced with a CODEOWNERS file.*

**(c) Top three questions — what I build next under each answer**

- **Q1 (target).** *GKE:* run packet C-1…C-19 with you, set `BM_DEPLOY_ENABLED`, tag `v0.1.0`, verify rollout + in-cluster `--check`s, then add the gateway ingress. *Cloud Run:* write `deploy-cloudrun.yml` reusing the runtime image, WIF and Secret Manager names; services per process, migrations as a Cloud Run Job; the chart stays validated as the alternative. *Both:* GKE for the workers, Cloud Run for the gateway/console; a larger change I would sequence after the first GKE deploy.
- **Q16 (migrations).** *Renumber:* coordinate the consumer-domains lane to move V003–V005 above V015, drop the reservation table from the runner README, and add a guard that fails a new migration below the current maximum. *Reserved gaps:* teach the runner a signed reservation list that may apply late in sandbox with an audit row, plus tests for out-of-order safety. *Defer:* keep cloud databases ephemeral until all lanes merge (no persistent sandbox before then).
- **Q12 (PD-07).** *Yes:* port the ES256 domain-assertion signer into gateway middleware, a Python verifier in `brandme_core.domains`, migrate rights/privacy reads off `X-Subject-Ref`, forward `X-Request-Id` on every hop, add a `jti` replay store. *No (keep tokens):* make each token per-service and per-environment, add `<NAME>_NEXT` dual-accept for rotation, and document that a token holder can act as any member. *Defer:* nothing changes; the risk stays listed in the packet.

## Round 4 (2026-10-25 → 30): oneshot plan 03 — status: (d) done, pending merge

Assignment: `docs/build/orchestration/oneshot-plan-03-opus-foundation.md` (supersedes ultra plan 02). Vehicle: PR #62.
- **Restarts:** the session's container restarted several times between 2026-10-25 and 2026-10-30. Work was kept on local branches and pushed once verified.
- **Deployment:** nothing in this round deploys anything.
- **Credential manifest:** no credential was created, so it has no new entry. The new rows describe names that already exist.

### Exit evidence (plan 03)

| Exit item | State | Evidence |
|---|---|---|
| #62 merged (re-synced, Q11 trimmed, #61 flags in) | **ready for merge**; merging is the founder's/orchestrator's call | re-synced with main `22ff053`. CI green on `89ad5fa`: 21 checks pass, deploy skipped. `foundation-check` now runs the full pytest suite under `BRANDME_REQUIRE_EMULATORS=1`. |
| Lock carries stripe/anthropic | done | `stripe==16.0.0` and `anthropic==0.125.0` come from #51's merge. This branch adds no pin (`docs/build/compatibility-lock.md`, "resolved by #51's merge"). |
| Q8 round trip per lane | done | `tests/foundation/test_outbox_lane_catalogs.py` sends one envelope per registered contract through `write_events`, then `python -m brandme_core.events.worker --once`, then the Pub/Sub emulator. Each arrives exactly once on its privacy-class topic. Counts: **foundation 11, consumer-domains 36, commerce-agents 7 (54)**. `test_every_shipped_catalog_is_required` proves that a missing lane catalog refuses startup. |
| Q9 joint deletion test | done | `tests/foundation/test_deletion_leaves_no_member_rows.py` drives the privacy lane's `request_deletion`/`run_deletion` with the platform handler. **Zero** `OutboxEvents`/`IdempotencyRecords` rows name the member, on both the delivered and undelivered paths. Other members' rows survive with the member unlinked. Without the handler, at least 21 rows remain. Two adversarial reviews; every finding is fixed or documented (`brandme_core/events/README.md`, "Retention and erasure"). |
| Migration registry | done | V001–V015 are contiguous. `tests/foundation/test_migrations.py` guards contiguity and runs without the emulator. The README reservation row lists V001–V015. |
| Member session reaches a lane route | done | the scope edit was already on main (`brandme-gateway/src/middleware/session.ts:128-132`). The gateway `consumer-domains.test.ts` e2e passed: dev session → `/wardrobe/items` (201) and try-on routes → domain service → Spanner + GCS emulators. |
| Trivy triage, named owner | done | the blocking gate has **no baseline entries** (`.trivyignore.yaml` is empty). Fixed: python-jose ×2, sentence-transformers, certifi, anyio (fastapi 0.134.0 / starlette 1.3.1 / pydantic 2.7.4, which also clears starlette's HIGHs), and the qs advisory via a pnpm override. The HIGH backlog has owners and a next triage date of 2026-11-25 (`docs/build/security/trivy-triage-2026-10-25.md`). |
| Zero deployment claims | done | packet section C is an execution checklist. Every step is "not run". Each verify block fails loudly; the stubbed gcloud/kubectl/gh runs are in the opsfix commit message. |

Full CI-equivalent suite (Spanner, Firestore, Pub/Sub, GCS emulators, `BRANDME_REQUIRE_EMULATORS=1`): CI `Test Core` and `Foundation check`, both full `tests/` runs, pass on `89ad5fa`. Local run on `4c4307a` (same code as `89ad5fa` plus docs): LOCAL_COUNTS.

### What else landed

- **#61 flags:**
  - `consumer_domains` AuditedProcess.
  - Helm `consumerDomains` with 1 replica, because the jti replay cache is per process.
  - gateway `CONSUMER_DOMAIN_*` wiring.
  - a compose service whose dev key pair is generated outside the repo (`BRANDME_DEV_ASSERTION_DIR`).
- **Q9 runtime:** an hourly `events-retention` CronJob running as its own least-privilege GSA `fnd-retention`, and the `events_retention` AuditedProcess.
- **CI:**
  - `check()` provisions every emulator.
  - `foundation-check` runs the full suite.
  - the hand-picked `test-consumer-domains` job is gone. `test-core` stays until one run shows identical counts.
  - emulator downloads retry.
- **Docs:**
  - full credential rotation runbook.
  - deploy checklist covering the consumer-domains and retention identities.
- **Deviations:** D-006 (two minimal lane-test edits for Q8), D-007 (the Q9 redaction split), D-008 (dependency fixes outside the listed files).

### Founder flags (short list, per plan 03)

1. **Deploy execution** (WIF, cluster, Secret Manager) stays founder-only; packet section C is the action list. The release lane is still unapproved.
2. **F-identity (identity-table erasure).** Account deletion still leaves `Members`, `MemberSettings`, `MemberIdentities`, `ConsentGrants` and `Sessions`. Sessions keep working and `account_state` is never set to `deleted`. This is a launch-blocker of the same kind as Q9. *Proposed:* foundation adds a final identity step once the privacy lane rules on ordering.
3. **Firebase custom-token minting** is built and reviewed on local branch `wip/fb2` (bundle at `fb2.bundle` in the session scratchpad):
   - gateway full suite: 211 passed, rules suite "skipped 0".
   - plan 03 defers it to round 5, and this session may push only its designated branch.
   - *Decide:* fold it into #62 or a follow-up PR on this branch, or authorize a separate branch.
4. **Q9 trade-off:** a restore that carries only `DeletionTombstones` re-erases ambiguous platform tombstones, choosing privacy over a rare refused category request. Carrying `DeletionJobs` with the tombstones avoids it.
5. **`.trivyignore` owner:** foundation, monthly. No renewal is pending, because no entries remain.

### Lane follow-ups

- **consumer-domains:**
  - delete `brandme_core/domains/persona/outbox_worker.py` (unused since Q8);
  - fix the `persona/lane.py:13-15` docstring;
  - move the assertion jti cache to a shared store before running more than one domain replica.
- **midnight-rights:**
  - acknowledge D-007;
  - surface `purge_derived` detail in receipts;
  - supply a Preprod contract deploy procedure and the seed-rotation tooling.
- **commerce-agents:** `tests/test_commerce_payments_flow.py::test_payment_identifiers_never_reach_models_events_or_wires[simulated-spanner]` failed once under heavy local load and passed in 4 other runs. No traceback was captured.
