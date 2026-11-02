# Implementation status (program roll-up)

The design package asks for this file (`docs/design/brandme/06-delivery-verification.md` §1, `CLAUDE_BUILD_PROMPT.md`).
It rolls up what the lane status files, the acceptance ledger and the audits already record; it never replaces them.
Lanes keep writing `docs/build/status/<lane>.md`; this file is refreshed when `main` changes in a way that moves a
row below. Last refresh: **2026-11-02** (close of the 2026-11 repository cleanup).

## Baseline

| Surface | Value |
|---|---|
| `main` at refresh | `652b77a4363faae3e75cb95c841564475c68d412` (2026-11-02, the merge of PR #84; this refresh lands on top of it). Preserved as the ref `baseline/2026-11-02-cleanup`, a branch until the owner converts it to a tag (hand-off below) |
| Audited revision | `ed19dc151d103b108cf972e6d37971c55d5dcf60`; two independent audits in `docs/audits/2026-11-01/` |
| Deployed revision | none; nothing has been deployed (`docs/build/deploy/gke-verification-packet.md`) |
| Toolchain | `docs/build/compatibility-lock.md` (Node 24.21.0, pnpm 10.34.6, Python 3.11, Spanner emulator 1.5.45 in every workflow since #82, Next 15.5.28 per D-009) |
| Migrations on `main` | V001–V017 contiguous (`brandme-data/spanner/migrations/`; registry `tests/foundation/test_migrations.py` `RESERVED`); next free number **V018** |
| Gates on every PR | `.github/workflows/ci-cd.yml`: Foundation check (`pnpm check` + `pnpm smoke`), Test Core (all of `tests/` with emulators), gateway, chain, frontend, security scan, five image builds with packaged-runtime smoke; path-filtered: `consumer-ui.yml` (shell, live-domains at the same SHA), `spatial-validation.yml`, `chain-tests.yml`, `module-regression.yml`, `workspace-guard.yml`, `deploy-validate.yml` |
| Rules | `CONTRIBUTING.md`; `.github/PULL_REQUEST_TEMPLATE.md`; protection rulesets specified in `docs/build/security/branch-protection.md` (owner-applied; nothing is active until applied) |

## The 2026-11 cleanup (what landed on `main`, in order)

| PR | Merge | What |
|---|---|---|
| #72, #74, #75 | `eee71172`, `d81f955e`, `cc75f225` | Audit fixes: `pnpm audit` severity floor; hex-digest false positive in the providers redaction (S2-OBS-008); its recurrence on `main` recorded |
| #73 | — | Second audit pack (`docs/audits/2026-11-01/claude-opus-02/`) |
| #76 | `5d88a9da` | Documentation consolidation: dated archive sets, honest READMEs, this file, `CLAUDE.md` corrections, first audit pack (`codex-01`) committed |
| #77 | `7730834a` | Dead code and the inoperable deploy chain removed; workflow triggers off retired `bench/*` refs; `.gitignore` without the blanket `*.json` rule |
| #79 | `6a53b272` | PR #63 integrated (consumer UI three rooms, private style card, heartbeat; 74 visual baselines refreshed under a stated review); #63 closed |
| #78 | `30e70aba` | PR #66 integrated (consumer-domains Ultra plan 02 items 2–8 and 10; V016 `consumer_design`) plus three Codex-found fixes with tests (hidden style axis leaves the cached card at once; malformed multi-select survey answers refuse instead of 500; catalog titles over 200 characters no longer fail the order observation); #66 closed |
| #80 | `d31c1dcd` | `CONTRIBUTING.md`, PR template, branch-protection spec (two Codex corrections applied: image checks required, tag creation not locked out); `.env.deploy.example` and the nonexistent `develop` triggers removed |
| #82 | `eb0b60ce` | `consumer-ui.yml` `live-domains` runs the domain sources of the job's own checkout at the same SHA as the UI (audit WP-01); the dev composition's drifted `OutboxDispatcher` call fixed; ten browser journeys pass in CI |
| #81 | `9b19ca19` | PR #70 integrated (midnight-rights round 03) with the migration renumbered to V017 plus three Codex-found fixes with tests (consumed reprint quota stays charged after failure or cancellation; every grant evaluated, not only the newest; `reprint.attested` emitted even when a later operation projected the child first); #70 closed |
| #84 | `652b77a4` | Kernel retry wrapper re-runs the emulator's one-writer `ABORTED` (the `test_concurrent_replays_one_response_one_close` failure on run 41523044806); `node_modules` symlinks ignored |
| this PR | — | This refresh; `CLAUDE.md` rows for the integrated lanes and the rights command process; archive-ref wording |

Preserved then retired: `archive/lux-foundation-lift-2026-08-31` (PR #29, closed) and `archive/design-audit-skill-2026-06-11`.
Parked by owner decision: PR #71 (Stripe Connect brands flow; test-mode run pending). Still open and not part of the
cleanup: PR #83 (consumer-domains Ultra plan 03 items 12 and 9 with its check-in packet, opened 2026-11-02 on the
lane branch, which therefore stays).

Owner hand-off (the session's token was refused on tag creation and branch deletion): run the retirement script
delivered with the cleanup report (two archive tags, the baseline tag, then the deletions it re-verifies as
ancestors of `main`), apply the rulesets, confirm the publish project (D-5) and move image publishing to workload
identity.

## Lanes

| Lane | Status log | State at refresh |
|---|---|---|
| Foundation (opus-foundation) | `status/opus-foundation.md` | Round 4 merged (PR #62). Owns the gates, migrations ledger, outbox worker, privacy framework. Owes the five midnight-rights round-03 items (blockers below) and the `events/README.md:62` sentence PR #83 flags |
| Consumer domains (opus-consumer-domains) | `status/opus-consumer-domains.md` | Ultra plan 02 items 2–8 and 10 on `main` via #78; Ultra plan 03 items 12 and 9 open as PR #83 with the lane's check-in packet (21 questions) |
| Consumer UI (astra-consumer-ui) | `status/astra-consumer-ui.md` | PR #56 (shell, guest journeys) and #63 (three rooms, style card, heartbeat; via #79) on `main`. Same-SHA `live-domains` evidence: ten browser → gateway → domain → Spanner journeys pass in CI (#82, run 41524104825) |
| Spatial AR (astra-spatial-ar) | `status/astra-spatial-ar.md` | PRs #60 and #69 merged (guest fit ladder, passport transport); round-03 continuation, check-in trigger not yet met |
| Commerce agents (opus-commerce-agents) | `status/opus-commerce-agents.md` | Rounds 1–3 merged (#35, #51, #64); commerce routers unmounted; Stripe Connect brands flow parked as PR #71 (owner decision) |
| Midnight rights (opus-midnight-rights) | `status/opus-midnight-rights.md` | Round 03 on `main` via #81 (authenticated rights command backend `brandme_core.rights_commands`, producers, My Data composition; V017). Open: the five foundation items of its Stage 15 packet; Preprod finality blocked on a Blockfrost token and funded seeds |

## Acceptance evidence

`docs/build/evidence/results.json` (read by `pnpm evidence:report`) records 5 of the 150 catalog IDs: BM-BASE-002,
-003 and -004 passed; BM-BASE-001 blocked (the consumer app had no gateway client when recorded); BM-BASE-005 failed.
The other 145 IDs have no recorded result and must not be described as passing.

Execution evidence outside the ledger (2026-11-02): every cleanup PR above merged with the full gate green on its
head, and every `main` push gate that has completed is green (`ci-cd.yml` runs are the record). The first same-SHA
M0 artifact exists: `consumer-ui.yml` `live-domains` on `b5b2e4a` (run 41524104825, ten journeys, `live-results.json`
and six captures in the run's artifact). The second audit's emulator runs
(`docs/audits/2026-11-01/claude-opus-02/evidence/runtime/`): `pnpm check` 12/12 with pytest `2146 passed, 20 skipped,
17 xfailed`; `pnpm smoke` 7/7; gateway 169/169; chain 90/90; Firestore rules 6/6; gateway → `persona.app` → Spanner
journey 16/16; worker chain 18/18 with a reward settled exactly once. Test Core on `main`-equivalent content at the
close: 2194 passed, 20 skipped, 17 xfailed (run 41523044806, before the #84 fix of its one failure).

## Blockers (owner or credential gated)

| Blocker | Where it is recorded |
|---|---|
| Branch and tag protection not yet applied; archive and baseline refs are unprotected branches | `docs/build/security/branch-protection.md`; owner hand-off above |
| Browser OIDC sign-in (tenant, redirect domains); development identity simulation only | D-005; audit WP-08 |
| Member-aware wardrobe repository and guest migration in the browser: re-verify against #66/#78 (audit WP-04 predates them; the same-SHA journeys cover guest migration and wardrobe intake through the gateway) | audit WP-04; `status/astra-consumer-ui.md` |
| Helm `consumerDomains.enabled: false` and unset `BRAIN_SERVICE_URL`; readiness on an always-200 route | audit S2-OBS-004; packet |
| Image publishing uses a service-account key and a hardcoded project (`lux-realestate-app`) that the owner has not confirmed | audit F-SEC-004 / S2-SEC-001, dispute D-5; packet C-checklist |
| Midnight rights round 03, five foundation items: trust-path entry for `rights_commands` (`brandme_core/config.py` audited-process inventory), `/transfers` mount, contract shapes, `/me` capability `rights.transfer`, Q9 restore guard. Until then accept/status ship unmounted and strict modes refuse the process | `status/opus-midnight-rights.md` Stage 15 (Q9–Q13) and Stage 16 |
| Midnight Preprod finality: Blockfrost token and funded seeds | `status/opus-midnight-rights.md` |
| Stripe Connect: no run against Stripe test mode | PR #71 (parked) |
| Visual gate: full-page capture height in `verify-visual.mjs` comparisons is not deterministic (`consumer-1440x900-light.png` "dimensions changed" on docs-only PR #76 and on #66's `babb360`, PR #83 Q11) | `status/astra-consumer-ui.md` integration note; fix belongs in the capture step |

## Exact next action

1. Owner: apply the rulesets in `docs/build/security/branch-protection.md`, run the ref retirement hand-off (tags,
   then branch deletions), confirm the publish project (D-5) and move image publishing to workload identity.
2. Foundation: land the five midnight-rights round-03 items with the lane's defaults in one PR, then re-run the
   rights end-to-end against the mounted gateway; answer PR #83's foundation flags.
3. Consumer UI: make the full-page capture height deterministic in `verify-shell.mjs` (wait for a stable
   `scrollHeight`, reduced motion) so the `shell` gate stops failing on unrelated PRs.
4. Then the round-03 plans in `docs/build/orchestration/` resume on the clean baseline, one change per PR.
