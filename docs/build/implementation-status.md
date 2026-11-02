# Implementation status (program roll-up)

The design package asks for this file (`docs/design/brandme/06-delivery-verification.md` §1, `CLAUDE_BUILD_PROMPT.md`).
It rolls up what the lane status files, the acceptance ledger and the audits already record; it never replaces them.
Lanes keep writing `docs/build/status/<lane>.md`; this file is refreshed when `main` changes in a way that moves a
row below. Last refresh: **2026-11-02** (documentation consolidation).

## Baseline

| Surface | Value |
|---|---|
| `main` at refresh | `cc75f2259e4f046cd41194287a8686a001e51e7b` (2026-11-02, before the cleanup PRs) |
| Audited revision | `ed19dc151d103b108cf972e6d37971c55d5dcf60`; two independent audits in `docs/audits/2026-11-01/` |
| Deployed revision | none; nothing has been deployed (`docs/build/deploy/gke-verification-packet.md`) |
| Toolchain | `docs/build/compatibility-lock.md` (Node 24.21.0, pnpm 10.34.6, Python 3.11, Spanner emulator 1.5.45, Next 15.5.28 per D-009) |
| Gates on every PR | `.github/workflows/ci-cd.yml`: Foundation check (`pnpm check` + `pnpm smoke`), Test Core (all of `tests/` with emulators), gateway, chain, frontend, security scan; `consumer-ui.yml`, `spatial-validation.yml`, `module-regression.yml`, `workspace-guard.yml` |

## Lanes

| Lane | Status log | State at refresh |
|---|---|---|
| Foundation (opus-foundation) | `status/opus-foundation.md` | Round 4 merged (PR #62). Owns the gates, migrations ledger, outbox worker, privacy framework |
| Consumer domains (opus-consumer-domains) | `status/opus-consumer-domains.md` | Ultra plan 02 items 2–8 and 10 open as PR #66 (green, five Codex rounds fixed); V016 reserved |
| Consumer UI (astra-consumer-ui) | `status/astra-consumer-ui.md` | PR #56 merged (shell, guest journeys); PR #63 (three rooms, style card, heartbeat) draft behind a visual-baseline review |
| Spatial AR (astra-spatial-ar) | `status/astra-spatial-ar.md` | PRs #60 and #69 merged (guest fit ladder, passport transport); round-03 continuation, check-in trigger not yet met |
| Commerce agents (opus-commerce-agents) | `status/opus-commerce-agents.md` | Rounds 1–3 merged (#35, #51, #64); commerce routers unmounted; Stripe Connect brands flow parked as PR #71 (test-mode run pending) |
| Midnight rights (opus-midnight-rights) | `status/opus-midnight-rights.md` | Round 03 open as PR #70 (authenticated rights commands, producers); needs V017 and five foundation items; Preprod finality blocked on a Blockfrost token and funded seeds |

## Acceptance evidence

`docs/build/evidence/results.json` (read by `pnpm evidence:report`) records 5 of the 150 catalog IDs: BM-BASE-002,
-003 and -004 passed; BM-BASE-001 blocked (the consumer app had no gateway client when recorded); BM-BASE-005 failed.
The other 145 IDs have no recorded result and must not be described as passing.

Execution evidence outside the ledger (2026-11-02, second audit, `docs/audits/2026-11-01/claude-opus-02/evidence/runtime/`):
full `pnpm check` 12/12 with pytest `2146 passed, 20 skipped, 17 xfailed`; `pnpm smoke` 7/7; gateway 169/169; chain
90/90; Firestore rules 6/6; gateway → `persona.app` → Spanner API journey 16/16; hand-composed worker chain
(`events.worker` → Pub/Sub → `persona.ingress` → `persona.jobs`) 18/18 with a reward settled exactly once.

## Blockers (owner or credential gated)

| Blocker | Where it is recorded |
|---|---|
| Browser OIDC sign-in (tenant, redirect domains); dev identity simulation only | D-005; audit WP-08 |
| Wardrobe is guest-local; no member-aware server repository or guest migration | audit WP-04 |
| Helm `consumerDomains.enabled: false` and unset `BRAIN_SERVICE_URL`; readiness on an always-200 route | audit S2-OBS-004; packet |
| Image publishing uses a service-account key and a hardcoded project (`lux-realestate-app`) that the owner has not confirmed | audit F-SEC-004 / S2-SEC-001, dispute D-5; packet C-checklist |
| Midnight Preprod finality: Blockfrost token and funded seeds | PR #70; `status/opus-midnight-rights.md` |
| Stripe Connect: no run against Stripe test mode | PR #71 (parked) |
| Migration numbering: V016 reserved by both #66 and #70 | `brandme-data/spanner/migrations/README.md`; cleanup plan allocates V017 to #70 |
| `pnpm audit --prod` gate has no severity floor | audit S2-OBS-002 (immediate fix merged as PR #72) |

## Exact next action

Finish the 2026-11 cleanup in order: documentation consolidation (this PR), dead-code and workflow-trigger removal,
branch retirement with preservation tags, then integrate #66, #70 (renumbered to V017) and #63. After that, one
same-revision `consumer-ui.yml` live-domains run with `BRANDME_DOMAIN_REFERENCE` repinned to the job's own checkout
and the emulator pin aligned converts the composite evidence into the first same-SHA M0 acceptance artifact
(audit RECONCILIATION §5).
