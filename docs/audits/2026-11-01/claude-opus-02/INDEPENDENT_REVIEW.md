# Independent review of the first audit (codex-01)

**Auditor:** Claude (independent second auditor; session configured as Opus 5.5, served as Fable 5.1 for part of the session — see model note in `AUDIT_STATE.md`). **Role:** challenge the consequential conclusions of the first audit pack `brand-me-labs-audit-2026-11-01-codex-01` and fill its evidence gaps.
**Date:** 2026-11-01. **Target:** `brandmeonline/Brand-Me-Labs` only.
**Baseline:** remote `main` = `ed19dc151d103b108cf972e6d37971c55d5dcf60` (identical to the first audit's pin and to this session's checkout; main did not move during either audit). The first audit's original local checkout `0f5f58a9…` was not available here and was not re-examined.
**Repository drift since the first audit's final snapshot (14:43 UTC):** one new branch/PR (`claude/exciting-hypatia-wl48op`, PR #72) and one moved tip (`claude/amazing-goodall-ntrljq` 45e157f5 → 8360813e, PR #71, now code). Findings about those two are kept separate from findings about the original snapshot ([`evidence/branches-delta.json`](evidence/branches-delta.json)).

The first audit pack is **not** copied into this directory; it is referenced by its own file names (`README.md`, `BRANCHES_CODE.md`, `SECURITY_RELIABILITY.md`, `USER_FLOWS.md`, `INTEGRATIONS_INFRASTRUCTURE.md`, `ROADMAP.md`, `CI_JOURNEY_EVIDENCE.md`, `PRODUCT_ARCHITECTURE.md`, `evidence/*.json`). It was retained unchanged.

## 1. Verdict in one paragraph

The first audit's consequential conclusions survive independent re-derivation. Every cited line I re-read exists and says what the first audit says it says (43 of 52 spot-checks are straight confirmations; [`evidence/second-audit-spotchecks.md`](evidence/second-audit-spotchecks.md)). Its branch analysis is correct on every fact and was over-cautious on two refs. Its security findings are real but two severities are inflated for a single-admin repository. Its biggest gap was structural, not analytical: it executed nothing. This review ran the repository — install, builds, type-checks, 151 gateway tests, 90 chain tests, 1,422 Python tests without emulators (0 failures), an emulator-backed Python run (see §6), and a 52-screenshot frontend run — and found **no application failure** at `ed19dc1`. In the 2026-11-02 continuation it also reproduced CI's full Foundation gate on this host and hand-composed the worker processes no topology deploys; a friend-decision reward settled exactly once through them, which moves the roadmap's hardest package (WP-05) from "implement" to "wire and deploy". What it added are things a static pass cannot see: a CI gate whose green is not reproducible (`pnpm audit --prod` with no severity floor), a "one-click" deploy chain that sources a file that does not exist, a Helm default that leaves the consumer-domain API off, and a failure path in the legacy brain that reports success with fabricated chain hashes.

## 2. What this review did, and did not do

| Done | How | Where |
|---|---|---|
| Read all 11 first-audit reports and dumped its 67 JSON evidence files; link-checked the pack (0 broken relative links); inspected its visuals for labels and sensitive content | lead auditor | SC-23, SC-24 |
| Re-read every consequential first-audit citation at `ed19dc1` | lead auditor, `sed`/`rg` on the session checkout | SC-01…SC-16, SC-26…SC-31 |
| Independent GitHub metadata: branches + protection flags, open PRs, check runs, job logs, releases/tags, collaborators | GitHub MCP read-only | SC-15…SC-18, SC-30, SC-35 |
| Independent full-history git evidence for all 36 branches and 70 PR heads (ancestry, cherry, patch-id-of-squash vs branch, tree diffs, merge-tree pairs, consumers) | branch sub-agent on an isolated clone, no checkout, unanchored (did not read the first audit) | [`evidence/branches/`](evidence/branches/) |
| Independent static security review of gateway, Python services, chain, CI/CD, developer tooling, secrets, dependencies, AI surface, privacy | security sub-agent, unanchored | [`evidence/security/`](evidence/security/) |
| **Execution** in an isolated worktree: lifecycle inspection, `pnpm install --frozen-lockfile`, lint/type-check/build/tests for gateway, frontend, console, chain, packages; `pytest tests` (CI command); `pnpm check --no-provision`; frontend run without backend + Playwright capture at 1440×900 and 390×844 | runtime sub-agent | [`evidence/runtime/`](evidence/runtime/), [`visuals/screenshots/`](visuals/screenshots/) |
| Static journey wiring trace with exact break boundaries | runtime sub-agent | [`evidence/journeys/wiring-trace.md`](evidence/journeys/wiring-trace.md) |
| Configuration name matrix (216 names) and integration matrix (40 integrations) | integrations sub-agent, unanchored | [`evidence/integrations/`](evidence/integrations/) |
| **Emulator-backed Python suite** with native Spanner emulator + the repository's pinned Firestore/Pub/Sub/GCS emulators, Python 3.11 from the hashed lock, `BRANDME_REQUIRE_EMULATORS=1` | lead auditor | [`evidence/runtime/emulator-run.md`](evidence/runtime/emulator-run.md) |

Not done: no cloud/IdP/provider access (same as the first audit); no Docker daemon (CI-identical emulator images could not run; the native emulator 1.5.53 vs CI's 1.5.45 is a recorded deviation); no `docker compose up`; the composed chain was exercised at the API level (smoke 7/7; canonical gateway→`persona.app`→Spanner 16/16; hand-composed workers 18/18, see §6) but **not** through the browser UI, and the deadline-expiry closure path of `persona.jobs` was not exercised; no real-device/AR/accessibility testing; no gitleaks/trufflehog; no dynamic penetration testing; branch content of PRs #63/#66/#70 was not reviewed line by line (only their integration facts). Sub-agent coverage limits are listed in their own files (`notes.md`, `trust-boundaries.md`, `commands.md`, `infrastructure-inventory.md §9`).

## 3. Challenge table — the eight priorities

Format per the brief: *Original claim | Supporting evidence (first audit) | Independent evidence | Verdict | Reasoning | Consequence | Follow-up*. Full rows with IDs are in [`evidence/challenges.json`](evidence/challenges.json) (36 rows); verdict counts: 16 confirmed, 2 confirmed with severity contested, 12 extended (confirmed plus a material addition), 3 corrected, 2 superseded by repository change, 1 unresolved (owner decision), 0 rejected.

### 3.1 Branch deletion and preservation (priority 1)

| Original claim | First-audit evidence | Independent evidence | Verdict | Reasoning → consequence → follow-up |
|---|---|---|---|---|
| 18 DELETION CANDIDATES: 11 `codex/*`, `fix/property-test…`, 3 `mia/*`, 2 `triage/*`, `claude/ci-repair-workflows` | cherry, aggregate patch-id vs squash, merge-tree identity, added paths | patch-id(squash) == patch-id(merge-base..tip) **and** empty tree diff over touched paths for #28, #39, #42–#50, #65; all 0-ahead refs are ancestors; name-consumer grep clean (`branches/notes.md` checks A, F, H) | **Confirmed** | Stronger test than the first audit's; zero hunks missing from main. → 18 stand. → Fresh tip check + `--force-with-lease` + no mass delete remain mandatory; nothing was deleted. |
| BR-026 `docs/brandme-full-experience…`, BR-034 `w11/integration…` = UNKNOWN | "status files advertise as base"; "retention purpose not established" | both pure ancestors; no PR depends on them; no executable consumer; commits stay reachable from main after ref deletion | **Corrected → DELETION CANDIDATE (medium)** | A documentary citation of a commit does not need a live ref. → Second-audit tally **19**. |
| `bench/opus-*` ×4, `claude/opus-commerce-agents-setup…`, `claude/opus-foundation-w00…` = KEEP | lane names in orchestration docs | 0 unique commits; ancestors; `docs/build/orchestration/{ultra,oneshot}-plan-03-*.md:7-8` do name each as "Lane branch"; branch agent proposed DELETION_CANDIDATE | **Unresolved → UNKNOWN (owner decision)** | Nothing in git is at risk; whether AI-session orchestration still targets the names is not determinable from the repository. Per the brief, unresolved dependency concerns stay out of the deletion list. → Delete the moment the owner retires/repoints the round-03 plans. |
| `bench/astra-*` ×2 = KEEP (workflow push triggers) | `consumer-ui.yml:7`, `spatial-validation.yml:5` | SC-29 confirms both; agent found the same | **Confirmed** | Executable consumers; delete only after a reviewed workflow edit. |
| BR-007 (draft #29) and BR-013 = PRESERVE THEN RETIRE | 22 added paths absent; 23 design-audit paths unique | BR-007: 22/24 paths absent, blobs nowhere in main, **merge-tree onto main clean** (verified); BR-013: 4 commits (2026-06) never in any PR, 23 files' blobs absent | **Confirmed (BR-013 strengthened)** | Agent's INTEGRATE(low) for #29 rejected: a parallel foundation duplicates authority `brandme_core` already has. → Bundle + verified recovery of `eed67370` and `8b9bd4a7` before any retirement. |
| F-BR-001 V016 collision #66 × #70 (High delivery blocker) | both files; `runner.py:99`; registry test | SC-10, SC-33; `git merge-tree` of the two heads: **content conflicts** in `migrations/README.md` and `tests/foundation/test_migrations.py` (RESERVED `16:` differs) in addition to the duplicate version | **Extended** | Semantic and textual conflict. → Whichever lands second takes V017 and edits README/RESERVED. |
| F-BR-003 pipeline-state.md re-sync claim false | ancestry | SC-28: `97d54477` not an ancestor of #63's head; `75f0ff0` does not exist in the full clone | **Confirmed** | → Treat `pipeline-state.md` as unreliable until regenerated from exact SHAs. |
| BR-036 / PR #71 docs-only; KEEP | 230-line plan read at `45e157f5` | tip now `8360813e`: +1,369/−103 across 9 files incl. `stripe_connect.py`, `stripe_test.py`, `stripe_wire.py`, tests; commit: "Not yet run against Stripe test mode" | **Superseded (repo changed)** | Correct at snapshot; KEEP stands; it is now unverified payment code behind still-unmounted commerce routers. |
| 35 heads / 5 open PRs | final ref delta | 36 heads / 6 open PRs; #72 (`e033950b`) is a 2-file pnpm-override fix | **Superseded** | → BR-037 KEEP. |

Closed-unmerged PRs: #2, #13, #37, #55 — only #2 contains content not in main (two 2025 stub files whose paths were re-implemented independently); the first audit's "no valuable missing integration" holds. No tags, no submodules, no LFS, no `Revert` commits on main (agent checks I, J).

### 3.2 Critical/High security findings and missed boundaries (priority 2)

Neither audit found a Critical or High *vulnerability*. Both secret scans (the first audit's 3,253-blob regex pass; this review's tree + 400/562-commit shape scan and full-history file-name/`PRIVATE KEY` search) found only fixtures, placeholders and legacy default passwords. Neither is gitleaks-equivalent.

| Original claim | First-audit evidence | Independent evidence | Verdict | Reasoning → consequence |
|---|---|---|---|---|
| F-SEC-003 **High**: no branch protection/rulesets | 34×404 on protection; rulesets `[]` | SC-17: 36/36 `protected:false` (GitHub MCP); SC-35: **exactly one collaborator (admin)**; 234/400 recent main commits authored "Claude", 123 "Adamus", 15 "brandmeonline"; S2-SEC-007 no CODEOWNERS/Dependabot | **Confirmed; severity → Medium** | There is no second human writer to bypass review; protection would not bind the admin unless enforced for admins. The realistic path is an AI/automation session or leaked token pushing to `main`. Worth a ruleset (including admins) — but not a "privileged compromise path" today. |
| F-SEC-004 Medium: stored GCP SA JSON key for image publish | `ci-cd.yml:368` | SC-08; **SC-36: `GCP_PROJECT_ID: lux-realestate-app` hardcoded at `:43`**; repo's credential manifest marks the key for retirement; deploy job already uses WIF (`:461-466`) | **Extended** | Publish target project does not carry the product's name. → Highest-value CI change: WIF for publishing + owner confirms the intended project. |
| F-SEC-001 Medium: MCP argv key, `@latest`, hook forwards all env | `.mcp.json:8`, hook `:21` | SC-26; S2-SEC-004 | **Confirmed** | Developer-workstation supply chain; not a production path. |
| F-SEC-002 Medium: readiness without dependency checks | `health.ts:16`, `gateway.yaml:115`, `app.py:79` | SC-01; SC-40: readiness **and** liveness on `/healthz`; **`consumerDomains.enabled: false` by default** in Helm; SC-45: the only dependency-aware route (`/api/v1/system/health`) would 503 in-cluster because Helm never sets `BRAIN_SERVICE_URL` | **Extended** | Rollout success ≠ working consumer routes. |
| F-SEC-006 Medium(cond.) per-process limiter; F-SEC-007 Medium immediate exit | `rateLimiter.ts:56`; `index.ts:106` | SC-02/03; S2-SEC-017/009 rate both **Low**; SC-40: `preStop: sleep 5` partially mitigates 007 | **Confirmed; severity → Low** | Documented limitations in a two-replica chart. |
| F-SEC-005 Low Terraform undeclared var | `main.tf:192` | SC-12 | **Confirmed** | |
| F-SEC-008 Medium: CRITICAL-only Trivy gate; 78 alerts; Dependabot 403 | `ci-cd.yml:545`; triage of 19 | SC-09 confirms; **SC-32 finds the inverse problem in the Node path**: `pnpm audit --prod` at `ci-cd.yml:122` and `chain-tests.yml:181` has **no severity floor**, so new advisories fail the job on unrelated commits — observed 2026-11-01 on PR #71's docs-only commit (job 124879798452: "2 moderate \| 1 high"); PR #72 pins overrides to clear it | **Extended → new finding S2-OBS-002** | The first audit described "green with open alerts"; it missed "red without any code change". Main's 10-30 green `Test Frontend` is not reproducible today. → Any future "green CI" claim must carry its run date; merge #72 or set a floor + allowlist. |
| Missed boundaries | component rows mention stubs/governance; no findings | S2-SEC-002 governance approver from request body (boot-guard gated); **S2-SEC-003 brain returns `status: ok` with `stub_` hashes when the orchestrator call *fails* and discards the commit result** (SC-37); S2-SEC-005 duplicate, shadowed policy routes incl. an undefined function (SC-38); S2-SEC-014 bearer path JIT-creates a member for any (iss, sub) and copies scopes verbatim; S2-SEC-025 internal read/export APIs trust a client-chosen `X-Subject-Ref`; S2-SEC-015 Blockfrost token in URL query | **Extended** | All mode-gated or internal — none Critical/High — but S2-SEC-003 is a failure path that *reports success*; fix before any demo that displays chain hashes. |
| CI structure | no `pull_request_target`/`workflow_run` | SC-27 confirms; S2 `ci-cd-review.md`: least-privilege permissions, images smoke-tested before credentials, deploy gated by tag + `vars.BM_DEPLOY_ENABLED` + environment; 12/13 actions tag-pinned (Low) | **Confirmed** | |

### 3.3 Journey completeness / production-readiness claims (priority 3)

The first audit claimed no journey complete and no tier production-ready. Independently confirmed at every break boundary, now with runtime observations:

| Journey claim | Independent evidence | Verdict |
|---|---|---|
| J-002 / F-UX-003: no browser sign-in outside dev | `wiring-trace.md §2`: grep for authorize/callback/PKCE/code_verifier/nonce across gateway+frontend matches only comments and an unmounted zod field; `index.ts:89` 404s `/session/dev` in strict; screenshots `me-connections-after-signin-attempt-*` show `GET /api/v1/session → 503` without backend | **Confirmed** — launch-blocking for any real-user pilot |
| J-005/006 / F-ARCH-006: closet is browser-only | SC-41: wardrobe router **is** mounted (its header "UNMOUNTED" is stale); Today/Circle *read* `/wardrobe/items`; the only *writer* is the CI harness | **Confirmed** |
| J-004 / F-ARCH-003: recommendations rank an empty list | SC-05; `service.py:134,139` no-op sources; real sources injected only in tests | **Confirmed** |
| J-007/008 / F-ARCH-002: nothing closes decisions or settles rewards in any deployable topology | SC-11; `wiring-trace.md §5/§9`: compose 16 services / Helm 10 workloads, no jobs/ingress; `RewardsConsumer` wired only in `dev-domains.py:92-96`; **SC-46: the events worker and exports refuse to start in dev without emulator hosts compose never provides**; **SC-61: composed by hand (worker → Pub/Sub → ingress → jobs) the chain settles a reward exactly once** | **Confirmed, extended — and reclassified: a deployment-configuration gap, not a code gap** |
| J-009–011/017 / F-ARCH-001 / CAP-017: commerce, catalog, assistant, providers, delegations, `/ops` unmounted; no MCP transport | SC-04, SC-34; routers imported only by `commerce.test.ts`; domain excludes `/ops` (`app.py:13-14`); console ops → 404 | **Confirmed** |
| J-016 / F-UX-002: clear-guest leaves spatial stores; F-UX-001 `/me` static | SC-06/07; `wiring-trace.md §7`: 2 of 9 stores cleared | **Confirmed, quantified** |
| CI_JOURNEY_EVIDENCE qualifications (mixed revision, API-seeded item, in-process dispatcher) | SC-14/15/31 | **Confirmed** — the first audit's caveats are accurate and important |
| Readiness: local demo "promising, not revalidated" | §6 of this review | **Upgraded with evidence** — builds, lint, type-checks, every unit/emulator suite, the composed smoke (7/7) and the canonical gateway→consumer-domain→Spanner API path (16/16) pass at `ed19dc1`; only the browser UI and the uncomposed workers remain unexecuted here; staging/production verdicts unchanged |

### 3.4 "Works" / "needs only credentials" integration claims (priority 4)

The first audit never claimed an integration works. Independent inventory (40 integrations, 216 config names) reaches the same conclusion and sharpens it: 11 code paths are mounted, 15 are not, 4 are CLI-only, 3 test-only, 7 unobservable; 78 consumed names are declared nowhere, 25 declared names are consumed nowhere. Direct evidence that keys do not help: `deploy-brandme.sh:58-68` *requires* `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `BLOCKFROST_API_KEY` and no code reads any of them (SC-52). Verdict: **confirmed/extended** ([`evidence/integrations/notes.md`](evidence/integrations/notes.md)).

### 3.5 Dead-code recommendations vs dynamic consumers (priority 5)

| Recommendation | Independent evidence | Verdict |
|---|---|---|
| CMP-039 `brandme_gateway/` orphan → removal candidate | SC-20: `scripts/regression/run_all.sh:14` lists it as a regression module; S2-SEC-011: it holds a mock JWT parser accepting any 10+ char token | **Corrected (qualified)** — a script consumer exists; remove *with* `scripts/regression/modules/brandme_gateway.sh`; the folder is a security smell and should go |
| CMP-018 `persona/outbox_worker.py` removal after recheck | SC-21: only self/docs references; deletion explicitly assigned to the consumer-domains lane's follow-up to #66 | **Confirmed** — do not remove ahead of that PR |
| CLAUDE.md kill-list: keep `agents/` because `deploy-brandme.sh` consumes it | **SC-44: every `agents/*.sh` sources `agents/lib/common.sh`, which does not exist** | **Corrected** — the consumer is itself inoperable; archive both as a unit after owner confirmation |
| Legacy region YAML dormant (F-ARCH-007) | SC-13 | **Confirmed** |
| New candidates found | SC-47 `brandme_core/health.py` imports `redis`/`nats` absent from the hashed lock and has no importer; SC-48 eight Dockerfiles with out-of-context `COPY ../..` (CI builds only the five root-context images) | **Extended** |

### 3.6 Mismatches among requirements, screenshots, runtime, mocks and deployed revisions (priority 6)

- First-audit visuals are correctly labelled (OBSERVED CI / COMMITTED BASELINE / INTENDED / PROPOSED) and legible (SC-24). This review adds 52 **OBSERVED SCREENSHOTS — second audit local run** at `ed19dc1`, frontend-only, synthetic identity, each tagged with route, viewport, SHA, capture time and observed result ([`visuals/screenshots/manifest.json`](visuals/screenshots/manifest.json)). They show the honest "service not connected" states, the guest-only pages that work without any backend (`/`, `/start`, `/add`, `/closet`, `/style`, `/discover`, `/me`, `/settings`, `/scan`, `/governance`), a 404 and the failed sign-in attempt.
- Emulator pin drift: the composite live-domains job runs Spanner `1.5.28` while every other suite and the dev script pin `1.5.45` (SC-50).
- CLAUDE.md cites three things that do not exist at `ed19dc1`: `brandme-chain/src/services/midnight-client.ts`, `tools.py:799-923` (file is 454 lines), `docker-compose.yml:304` (file is 242 lines) (SC-39, SC-51); `docker-compose.dev.yml:168-184` console claim is stale (file is 36 lines). Extends F-ARCH-005.
- `wardrobe.ts:4` says "UNMOUNTED" for a router that is mounted (SC-41).

### 3.7 Omissions (priority 7)

Branches: #72 and the moved #71 tip (post-snapshot). Modules: `brandme_core/health.py`, the eight unbuildable Dockerfiles, console `lib/api.ts` localStorage-bearer bypass client (SC-49). Cloud prerequisites: the first audit's list stands; add the undeclared-but-required emulator hosts (SC-46), the `lux-realestate-app` project question (SC-36), and Helm's `consumerDomains` default (SC-40). Access limitations: identical to the first audit's except that this review had an isolated runtime and the first did not.

### 3.8 Roadmap sequencing and first-milestone achievability (priority 8)

**M0 is achievable and the first audit's package set is right; its order should change.** Main's own harness (`verify-live-domains.mjs`, SC-31) already asserts dev sign-in, guest migration, persona edit with account isolation, a server wardrobe item on Today, a 5-minute decision with pass/close, reward settlement, notifications, block and sign-out — i.e. most of M0 — with two substitutions (API-seeded item; in-process `OutboxDispatcher → RewardsConsumer` thread). Therefore:

1. **WP-01** is cheaper than described: repin `consumer-ui.yml:82` from `dafd3b16…` to the job's own checkout and the composite evidence becomes same-revision evidence. Also set an advisory floor or merge #72 first, or the job stays red for reasons unrelated to the change.
2. **WP-05** (compose jobs/ingress; set `consumerDomains.enabled: true`; add the Pub/Sub/GCS emulator services the worker requires — SC-46) carries the product value (decisions close, rewards settle) and is now known to be **wiring and manifests, not domain code**: the processes composed by hand with environment variables alone settled a reward exactly once (SC-61). Its effort estimate should drop accordingly. Sequence it **before finishing WP-04**.
3. **WP-04** (browser Add → server wardrobe) then **WP-06** (`/me` truth, full guest cleanup).
4. **WP-02/03** in parallel; **S2-SEC-003** (brain success-on-failure) belongs in WP-03's scope if the legacy scan demo is shown to anyone.

M1 remains blocked exactly where the first audit says (browser OIDC, privacy scope, resources/IAM, operations evidence). Effort ranges in `ROADMAP.md` are plausible; none was independently re-estimated.

## 4. New findings from this review (not in the first audit)

| ID | Severity (security / product) | Finding | Evidence |
|---|---|---|---|
| S2-OBS-002 | Low / **High (delivery)** | `pnpm audit --prod` gates with no severity floor; main's green is not reproducible after new advisories | SC-32, PR #71 job log, PR #72 |
| S2-OBS-003 | — / Medium | `deploy-brandme.sh` and `agents/*.sh` are inoperable (`agents/lib/common.sh` missing) | SC-44 |
| S2-OBS-004 | Low / Medium | Helm: `consumerDomains.enabled: false` default; `BRAIN_SERVICE_URL` unset so `/api/v1/system/health` would 503 in-cluster; readiness+liveness on an always-200 route | SC-40, SC-45 |
| S2-SEC-003 | Medium (mode-gated) | Brain reports `status: ok` + fabricated `stub_` hashes when the orchestrator call fails; commit result discarded | SC-37 |
| S2-SEC-005 | Low (latent) | Duplicate, shadowed policy route handlers; dead copy calls undefined `fetch_owner_and_consent` | SC-38 |
| S2-SEC-001 (detail) | Medium | Publishing project hardcoded as `lux-realestate-app` | SC-36 |
| S2-OBS-005 | — / Low | Events worker / privacy exports cannot start in the default compose stack (required emulator hosts undeclared) | SC-46 |
| S2-OBS-006 | — / Low | Emulator pin drift 1.5.28 vs 1.5.45; CLAUDE.md cites nonexistent code in three places | SC-50, SC-39, SC-51 |
| S2-OBS-007 | — / Info | Console `pnpm lint` has no ESLint config (interactive prompt); CI never runs it | runtime step 13 |

Full security list (26 findings: 4 Medium, 18 Low, 4 Info): [`evidence/security/findings-independent.json`](evidence/security/findings-independent.json).

## 5. False positives checked

- First-audit "no `pull_request_target`" — true (SC-27).
- First-audit "no tags/submodules/LFS" — true (agent check J; GitHub tags/releases empty).
- First-audit "CI run 41091237404 on `ed19dc1`, success" — true (SC-16).
- First-audit "shell job failed on dimensions changed" — verbatim in the log (SC-15).
- First-audit "19 review threads resolved on #66" — not re-verified (not consequential).
- First-audit F-SEC-003 "High" — the one rating I would call a false positive *as rated*: the fact is true, the threat model assumed is not present.

## 6. Runtime evidence (what the first audit could not provide)

**Without emulators** (CI command, Python 3.11.18 from the hashed lock): `1422 passed, 761 skipped, 0 failed, 0 xfailed`, `QUARANTINED: 0` — every skip is environmental (704 Spanner, 24 Firestore, 6 Spanner REST, 4 GCS, 3 Pub/Sub, 11 Stripe, 6 AP2, 3 Anthropic) and the suite reports them as *not run*, never as passes. Gateway `151 passed / 18 skipped` (4 emulator files). Chain `90/90`. Frontend `next build` 36 routes (shared JS 103 kB); console build 13 routes; packages tests pass; `pnpm check --no-provision` 12/12 with emulator suites explicitly `not_run`. One toolchain failure: console `pnpm lint` (no ESLint config; CI does not run it). Node 22.23.4 was used (pin 24.21.0; `engines` accepts it). Details: [`evidence/runtime/commands.md`](evidence/runtime/commands.md).

**With emulators** (native Spanner 1.5.53 + repository-pinned Firestore/Pub/Sub/GCS, Python 3.11.18 from the hashed lock, `BRANDME_REQUIRE_EMULATORS=1`): **`2146 passed, 20 skipped, 17 xfailed, 4 warnings in 1011.05s`, exit 0** — identical to CI's Test Core counts for the same commit, reproduced on an independent host. The 20 skips are all allowlisted credential/SDK skips (Stripe mock/live, AP2 SDK, Anthropic key); the 17 xfails are the documented legacy quarantine; the extra warning is an emulator `ABORTED` in a background thread of a deliberate two-agent contention test whose assertion passed. Zero emulator skips remained. Deviation: Spanner emulator 1.5.53 vs CI's 1.5.45 image. Details: [`evidence/runtime/emulator-run.md`](evidence/runtime/emulator-run.md).

**Continuation, 2026-11-02** (same baseline; all 36 remote tips and 6 open PRs re-fetched and unchanged): with the emulators up, the gateway suite ran **169/169 (20 files, 0 skipped)**, the Firestore-rules suite **6/6**, the repository's composed **`pnpm smoke` passed 7/7** (gateway → brain → Spanner health, dev session, `PATCH /me` with If-Match + CSRF, profile survives gateway + brain restart, outbox events validated and dispatched), and an audit-written API journey through the **canonical** consumer-domain composition — gateway signing ES256 principal assertions → `python -m brandme_core.domains.persona.app` → Spanner, using the repo's own dev key-pair script — passed **16/16** (persona read, idempotent wardrobe create, account isolation, CSRF/Origin refusals, sign-out, and `/recommendations` → 200 with **zero items**, i.e. F-ARCH-003 observed at runtime). The full Foundation gate (`pnpm check` with provisioning, `BRANDME_REQUIRE_EMULATORS=1`) then passed **12/12 steps** with pytest `2146 passed, 20 skipped, 17 xfailed` — CI's `foundation-check` reproduced in full. Finally, the three processes that no deployable topology composes (`events.worker`, `persona.ingress`, `persona.jobs`) were composed **by hand with environment variables only** around that API chain: a friend decision was created, answered and closed through the gateway; `events.worker --once` delivered 13 outbox events to the pinned Pub/Sub emulator; `persona.ingress --once` applied them (five further runs applied nothing — inbox dedupe held); bob's `friend_decision_response` settled to exactly **10 points**; notifications and the block were enforced — **18/18**. Two environment artefacts were isolated and are not application failures: this container's nested pnpm shim does not forward SIGTERM to `tsx` (smoke attempt 1 aborted at the restart step; passes with the real pnpm on `PATH`), and my first driver sourced the compose-style key file without expanding `\n` (fixed). Details and logs: [`evidence/runtime/emulator-run.md`](evidence/runtime/emulator-run.md).

Interpretation: at `ed19dc1` the repository **builds, its full Foundation gate passes, the composed smoke passes, the canonical gateway→consumer-domain→Spanner path works, and the decision→reward loop settles exactly once through the canonical worker processes when those are wired by hand**. That upgrades the first audit's "isolated local demo: promising but not revalidated" to **"demonstrated on an independent host for everything except the browser UI on top of the chain"**, and it reclassifies F-ARCH-002 / WP-05 from missing implementation to missing deployment configuration (no compose service, no Helm workload, no emulator services in compose). It does not change the staging or production verdicts.

## 7. Limits of this review

Same access limits as the first audit (no cloud, IdP, provider, device). No Docker daemon, so CI-identical images could not run. Sub-agents read the repository unanchored but their coverage is sampled where their files say so; I re-verified every claim I relied on for a verdict (SC rows) and did not re-verify the rest. Branch-content review of #63/#66/#70 was limited to integration facts. This review did not implement anything, create or delete refs, or commit.
