# Oneshot plan 03 — Opus Foundation (land round 4)

**Shape: ONESHOT — one PR, one landing, no 21-question check-in.** Exit evidence is the
deliverable; founder flags are a short list, not a question packet.
**Status: Prepared 2026-10-25 — founder approved push + trigger 2026-10-25.**
**Supersedes:** `ultra-plan-02-opus-foundation.md` (round-02 draft, never triggered — its Q11
item is now moot, its base state is stale).
**Repo:** brandmeonline/Brand-Me-Labs · **Lane branch:** `bench/opus-foundation-20261005` ·
**Vehicle PR:** #62 (draft, dirty, 5 commits, head `98774964`)

## State at issue (verified 2026-10-25, main `2b5ae889`)

- Main includes #51 (commerce round 2), #56 (consumer journeys + shell contract), #61
  (consumer-domains router mount), #65 (shell contract 1.1.1). Main fully green at last check.
- **Q11 RESOLVED BY EVENTS.** #51's own merged head locked `stripe==16.0.0` +
  `anthropic==0.125.0`, authorized by the founder's merge (effectively Option B, not a
  ruling). #62 must NOT re-add the pins — its Q11 item is trimmed to verifying the lock
  already carries them.
- #62's remaining scope: Q8 outbox catalogs, Q9 deletion purge, deploy checklist, trivy
  follow-through. It is dirty vs new main (after #51/#56/#61 landed) and needs a re-sync.
- **#61's foundation flags are now this lane's work** (they are foundation-owned files):
  one-line scope edit in `brandme-gateway/src/middleware/session.ts` (without it no member
  can reach a lane route); `consumer_domains` boot-guard service into the audited inventory
  (strict modes refuse it until added); Helm/compose run the domain service and carry its key.
- Still open from round 02: migration ordering (reserved V003–V005 below main's V006–V014;
  register #51's V015); `.trivyignore` baselines expire 2026-11-30; Firebase custom-token
  minting residual from round 2; deploy execution itself (packet exists, deploy unproven —
  execution rides the proposed release lane, still unapproved).

## Mission

Land round 4 in one push: a re-synced #62 carrying Q8 + Q9 + the #61 foundation flags,
with the migration registry clean — and nothing claimed as deployed until it runs.

## Shared chassis (oneshot version)

Dev/test scope only; no production data, no real funds. Secrets NEVER committed (GitHub
secrets or gitignored `.env` only). Every credential created gets a manifest entry in
`docs/build/status/opus-foundation.md` (name, scope, where stored, date — never the value).
Least privilege by default. No check-in protocol on a oneshot: the lane lands the PR and
reports exit evidence; anything needing prod scope stops and flags to the founder instead.

## Build, in order

1. **Re-sync #62 with main `2b5ae889`.** Resolve conflicts. Do not rebuild on the stale head.
2. **Trim Q11.** Verify the hashed lock already carries `stripe==16.0.0` +
   `anthropic==0.125.0` via #51's merge. If — and only if — the lock does NOT carry them,
   stop and flag to the founder; do not invent a second Q11 path.
3. **Fold in the #61 foundation flags.** Session scope edit; boot-guard inventory entry;
   Helm/compose domain service + key wiring. Verify a member session can reach a lane route
   on the dev gateway after the edit.
4. **Q8 outbox-catalog import.** Foundation worker imports the lane outbox catalog modules
   (consumer-domains + commerce); verify with a published-event round trip per lane. Both
   lanes then delete their private workers (their step, not this lane's edit).
5. **Q9 deletion purge (launch-blocker).** Purge delivered outbox rows after 7 days. Prove
   jointly with midnight's redaction: zero member payload rows survive account deletion,
   delivered + undelivered paths.
6. **Migration ordering.** Sequence reserved V003–V005 below main's V006–V014; register #51's
   V015. The registry check must pass on the head.
7. **Trivy renewal triage.** Named owner + plan before the 2026-11-30 expiry. No silent
   extensions.
8. **Re-verify from a clean checkout, undraft, land.** Aggressive posture: auto-merge on
   green + clean.

## Exclusive file ownership

- `.github/workflows/` (CI definitions), `scripts/python/requirements.in` +
  `requirements.lock`, `pnpm-workspace.yaml` + lockfile policy, `tests/foundation/`, Helm
  charts + deploy manifests, `docs/build/status/opus-foundation.md`.
- Do NOT touch lane-owned domain code, frontend code, or chain code. The Q8 import touches
  the foundation worker only; lane modules are imported, not edited.

## Exit evidence (all required)

- [ ] #62 merged to main (re-synced, Q11 trimmed, #61 flags in).
- [ ] Lock verified carrying stripe/anthropic pins (or a founder flag if absent — see step 2).
- [ ] Q8: published-event round trip per lane recorded in the status doc.
- [ ] Q9: joint deletion test green — zero member payload rows survive account deletion.
- [ ] Migration registry check green on the head (V003–V005 ordered, V015 registered).
- [ ] Member session reaches a lane route on the dev gateway (session scope edit proven).
- [ ] Trivy renewal triaged with a named owner before 2026-11-30.
- [ ] Zero deployment claims without a run (checklist only).

## Founder flags (short list — no question packet on a oneshot)

- Console actions for any deploy execution (WIF/cluster/Secret Manager) remain founder-only;
  the checklist from #58 + this round is the action list.
- Release lane proposal (executes deploys) still unapproved — deploy proof waits on it.
- `.trivyignore` renewal owner if not foundation.
- Firebase custom-token minting: carry to round 5 unless the founder directs it into this
  oneshot (it is the one item explicitly deferred).
