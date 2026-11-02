# Ultra plan 03 — Opus Consumer-Domains (design-alignment completion)

**Shape: ULTRA — deep multi-stage wave with a 21-question check-in.**
**Status: Prepared 2026-10-25 — founder approved push + trigger 2026-10-25.**
**Supersedes:** `ultra-plan-02-opus-consumer-domains.md` (round-02 draft, never triggered —
its step 1, the MediaService mount, has since landed as #61).
**Repo:** brandmeonline/Brand-Me-Labs · **Lane branch:** `bench/opus-consumer-domains-20261005` ·
**Vehicle PR:** #66 (draft, unstable, 4 commits, head `29913cb9`)

## State at issue (verified 2026-10-25, main `2b5ae889`)

- On main: #52 (persona V002, wardrobe V003, social V004, rewards V005, ops console
  backend), #59 (Q19 GCS media store), #61 (Ultra plan 02 item 1: lane routers mounted
  behind foundation auth, including the MediaService HTTP API). The mount this lane waited
  on is DONE — try-on end-to-end is unblocked.
- #66 is open and in flight: "Now, Flow, loyalty, surveys and credit, persona card,
  rooms, experiments" — Ultra plan 02 items 2–4 continuing. It is draft + unstable; the
  lane must say what is red and fix it before undrafting.
- Still open: dev-bucket run (Q14 — needs a GCP credential; emulator until then, do not
  block on it); lane outbox worker deletion (waits on foundation's Q8 import, landing in
  #62); share projector registration with foundation's framework; the five A/B experiment
  definitions (flag wiring; NO experiment runs without founder approval of definitions);
  small-group rooms; real-domain My Data registration; disclosure facets enforced at the
  API layer (locked stranger-scan default).
- PD-09 (extended), PD-10, PD-11 are founder-ratified. The locked design behavior (Oct 23)
  is not open for re-litigation: Now/Flow/loyalty/visibility mechanics are decided;
  questions below are implementation choices only.

## Mission

Turn the mounted domain spine into the locked experience: Now/Flow/loyalty mechanics live
on the dev gateway, experiments defined (not run), and the lane's remaining integration
debts closed.

## Shared chassis

Dev/test scope only; no production data. Secrets NEVER committed (GitHub secrets or
gitignored `.env` only). Every credential created gets a manifest entry in the lane status
doc (name, scope, where stored, date — never the value). Least privilege by default.
Anything needing prod scope gets a dev equivalent plus a flag in the check-in questions.
Check-in protocol: stop before any irreversible or prod-scoped step; deliver evidence plus
exactly 21 questions (7 direction / 7 integration & security / 7 scope & sequencing) with
recommended defaults. Until check-in, build on defaults — do not stall.

## Build, in order

1. **Land #66.** Fix what is red, re-verify from a clean checkout, undraft → auto-merge
   on green + clean. #66 carries the Now/Flow/loyalty/surveys/persona-card/rooms/
   experiments scope — do not let it sprawl past that list.
2. **Now-decision loop.** Timed decision requests to a chosen circle (default ~5-minute
   window, asker's stated "why," thumbs/comments), rewards for in-window responses,
   influence credit when a friend's verdict moves a purchase.
3. **Flow ranking.** Freshness sets position; excitement/engagement sets size/depth.
   Home = Flow: newest from the member's houses through the persona lens, friend decision
   requests cutting in.
4. **Loyalty standing.** Per-house standing computed from platform stats (e.g., top-5%
   buyer); houses see standing, never raw history — asserted by test. Standing drives
   house rewards (exclusive drops/events/gifts).
5. **Surveys/quizzes.** Daily-capped, feeding points; points convert to in-app purchase
   credit only (launch posture: not cashable).
6. **Persona card + closet visibility.** Living persona card (taste axes, badges, standings,
   curated highlights) recomposing on trigger events with nightly backfill; per-piece
   closet visibility, owner-curated, sliding-scale.
7. **Small-group rooms.** Intimate sends + collaboration rooms (e.g., bridesmaids' gown
   room) alongside fast circle verdicts — the second confirmed decision rhythm.
8. **Five A/B experiment definitions.** Closet memory (diary vs clean archive); curator
   verbosity default; the reveal (anticipation pause vs instant, adaptive to closeness);
   visitor-trace signals; decision-thread persistence. Definitions + flag wiring against
   foundation's primitive; NO experiment runs without founder approval of the definitions.
9. **Outbox worker deletion.** Delete the lane's private worker in the same PR that verifies
   foundation's Q8 import (lands in #62).
10. **Share projector.** Register the consumer reducer with foundation's projection framework
    (`share.revoked` and friends).
11. **Dev-bucket run.** Run against a real GCP dev bucket the day the founder credential
    lands; emulator until then — do not block the stage on it.
12. **Disclosure facets at the API layer.** Enforce the locked stranger-scan default
    (identity/house/maker/story only; price/ownership/logistics hidden unless the owner
    unfolds) with tests.

## Exclusive file ownership

- `brandme_core/domains/persona/`, `wardrobe/`, `social/`, `rewards/`, `media/` (including
  the W08 server + MediaService API), domain routers, social policy, the lane status doc.
- Do NOT touch foundation files (workflows, lock, worker), commerce code, frontend code, or
  chain code. The shell header swap is mechanical consumption of consumer-ui's published
  contract component, not a redesign.

## Exit evidence (all required)

- [ ] #66 merged to main.
- [ ] Now loop live on dev: timed windows, in-window rewards, influence credit on
  purchase-moving verdicts — with tests.
- [ ] Flow ranking live on dev with the specified semantics; Home = Flow demonstrated.
- [ ] Loyalty standing computed per house; houses receive standing only (verified by a test
  asserting raw history is never exposed).
- [ ] Surveys/quizzes daily-capped and feeding points; points→credit conversion in-app only.
- [ ] Persona card recomposing; per-piece visibility controls live.
- [ ] Small-group rooms live alongside fast verdicts.
- [ ] Five experiment definitions written + flag-wired; none running without founder approval.
- [ ] Lane outbox worker deleted post-Q8; share projector registered.
- [ ] Disclosure facets enforced at the API layer, tested.
- [ ] Dev-bucket run recorded (or emulator-only status stated plainly if the credential has
  not landed).

## Check-in trigger

When Now/Flow/loyalty are live against the dev gateway with #66 merged and experiments
defined.

## Founder inputs this lane cannot self-serve

- GCP credential for the dev-bucket run (dev bucket + service account).
- Approval of the five experiment definitions before any experiment runs.

## Check-in questions (21, with recommended defaults)

### Direction (7)

1. #66 scope: land as-is (Now/Flow/loyalty/surveys/persona-card/rooms/experiments), or
   split rooms/experiments to a follow-up? **Default: land as-is; split only if CI forces it.**
2. Now windows: ~5-minute default with asker-set variants? **Default: yes.**
3. Flow ranking: freshness = position, excitement = size/depth exactly as specified?
   **Default: yes, exactly as specified.**
4. Loyalty standing: compute per-house top-% from platform stats now? **Default: yes.**
5. Surveys/quizzes: daily caps feeding points, in-app credit only? **Default: yes.**
6. Persona card: live recompute on trigger events with nightly backfill? **Default: yes.**
7. Experiments: define all five this round, runs need separate approval? **Default: yes.**

### Integration & security (7)

8. Outbox worker: delete in the same PR that verifies the Q8 import? **Default: yes.**
9. Share projector: register the consumer reducer with foundation's framework? **Default: yes.**
10. Disclosure facets: enforce the locked stranger-scan default at the API layer?
    **Default: yes.**
11. Dev bucket: emulator now, real dev-bucket run the day the credential lands — or block?
    **Default: emulator now; do not block.**
12. My Data reads: Spanner reads per the Q20 deferral, or Firestore? **Default: Spanner reads.**
13. Points→credit: in-app purchase credit only, not cashable at launch? **Default: yes,
    enforced at the ledger.**
14. W08 retention: 24-hour try-on media retention stays? **Default: yes.**

### Scope & sequencing (7)

15. Order: #66 → Now/Flow polish → loyalty/surveys → experiments → outbox/share → bucket?
    **Default: yes.**
16. Small-group rooms: in scope this round alongside fast verdicts? **Default: yes.**
17. Try-on consent gating: unchanged? **Default: yes.**
18. Check-in trigger: Now/Flow/loyalty live on the dev gateway + #66 merged? **Default: yes.**
19. Stage label: this round is design-alignment completion, not spec completion (W03–W05
    already complete)? **Default: yes.**
20. Next round: editorial layer + brand/designer feeds after social mechanics? **Default: yes.**
21. Experiment runs: founder approves definitions first, runs approved separately per
    experiment? **Default: yes.**
