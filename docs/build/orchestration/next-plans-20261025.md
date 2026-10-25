# Next plans — round 03 (2026-10-25)

**Prepared 2026-10-25 — founder approved push + trigger 2026-10-25.**
**Base state verified:** main `2b5ae889` (includes #51, #56, #61, #65). Open PRs: #29
(dormant audit), #60, #62, #63, #64, #66.

## Why round 03, and what it supersedes

The round-02 drafts (`ultra-plan-02-*.md`, prepared 2026-10-24 evening, never triggered)
are now stale: they assume main `d5b993f2`, #51 draft, #56 on the spec branch, and Q11
pending. Since then #51, #56, #61, #65 merged; Q11 resolved by events (#51's own head
locked the pins, authorized by the founder's merge); #62, #63, #64, #66 opened. Round 03
is grounded in the new state. Round-02 drafts are retained for history, not for use.

## Shape rule used

- **ULTRA** = deep multi-stage wave + 21-question check-in (7 direction / 7 integration &
  security / 7 scope & sequencing) + check-in trigger. For lanes with multi-stage new scope.
- **ONESHOT** = one PR (+ its proof run) + exit evidence + a short founder-flags list.
  No question packet. For lanes whose next work is essentially "land the open round PR
  and prove it."

## Per-lane verdict

| Lane | Shape | File | Vehicle | One-line mission |
|---|---|---|---|---|
| Opus foundation | ONESHOT | `oneshot-plan-03-opus-foundation.md` | #62 (draft, dirty) | Land round 4: re-sync, trim Q11, fold #61 flags, Q8 + Q9 |
| Opus consumer-domains | ULTRA | `ultra-plan-03-opus-consumer-domains.md` | #66 (draft, unstable) | Design-alignment completion: Now/Flow/loyalty + experiments defined |
| Opus commerce-agents | ONESHOT | `oneshot-plan-03-opus-commerce-agents.md` | #64 (draft, unstable) | Land round 3 + the money-path proof |
| Opus midnight-rights | ULTRA | `ultra-plan-03-opus-midnight-rights.md` | fresh branch off main | Finality + anchor record + disclosure enforcement |
| Astra consumer-ui | ULTRA | `ultra-plan-03-astra-consumer-ui.md` | #63 (draft, unstable) | Design-implementation wave + ChatGPT reconciliation |
| Astra spatial-ar | ULTRA | `ultra-plan-03-astra-spatial-ar.md` | #60 (draft, dirty) | Land Stage 18 + fit evidence + Pod model + scan UX |

## Cross-lane sequencing

1. #62 (foundation) + #64 (commerce) are independent — either can land first on
   green + clean. Foundation-first still holds as a principle, not a blocker here.
2. #60 (spatial) before #63's rooms work if their room manifests collide.
3. Midnight's anchor record schema can land before spatial's scan UX completes.
4. Consumer-domains' outbox worker deletion pairs with #62's Q8 import; Q9's joint
   deletion proof pairs foundation purge + midnight redaction.
5. Endgame after these land: W11 integration (contracts/OpenAPI/migrations reconciled,
   acceptance catalog run, integrated journeys, device/visual checks).

## New lanes — still unapproved, not re-planned here

The round-02 new-lanes proposal (`ultra-plan-02-new-lanes.md`: Release & Deployment,
Verification & Assurance) remains unapproved, and a second proposed pair exists in the
Brand.Me APIs Space (Discovery & Brand Feeds; Trust, Verification & Live Platform). That
discrepancy awaits the founder's choice. No new-lane plans were created in round 03;
the round-02 proposal stands as the reference until the founder picks a pair.

## Founder inputs still owed (program-wide)

- Previous ChatGPT app designs — location (see the consumer-ui plan's step 1; the input
  gap is stated plainly there, not papered over).
- GCP credential for the consumer-domains dev-bucket run.
- Blockfrost Preprod token + funded seeds — the highest-value credential unblock
  (midnight finality).
- Founder key fostering (`STRIPE_TEST_SECRET_KEY`, `BRANDME_DEV_ANTHROPIC_API_KEY`) —
  commerce proof runs on demo keys meanwhile.
- B2B tier pricing; agent-autonomy research commission-or-defer; device/screen-reader
  session time; console actions (WIF/cluster/Secret Manager) for any deploy execution.
- Dormant #29: close-or-revive (not a lane plan).

## Orchestrator notes

- All six plans keep the standing chassis: dev/test scope only, secrets never committed,
  every credential manifest-logged (name/scope/location/date, never values).
- Mia runs point as before: tracks via watch/triage, self-assesses every ultra check-in
  packet (evidence vs GitHub, spec-coverage grade, manifest hygiene audit,
  question-quality grade), digests recommended answers for the founder.
- Triggering: per the direct-trigger convention, these plans go into the repo under
  `docs/build/orchestration/` + trigger comments on the PRs when the founder approves.
  Round 03 triggered 2026-10-25 per founder approval (branch mia/next-plans-20261025 + trigger comments on each lane PR).
