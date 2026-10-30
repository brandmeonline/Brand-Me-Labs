# Pipeline state — continuous build loop

Seeded 2026-10-30 from the approved pipeline design (pipeline-design-20261029.md:
repo-based, Mia-monitored; daily updates; pause for founder review every 5 days).
This file is the loop's single source of truth. Mia updates it on every transition
and commits the update. Lanes read their next assignment from the queue below.

## Loop status
- Design: APPROVED by founder 2026-10-29. Check-in rule (option 3): lanes keep
  building on work independent of open questions; recommended defaults are NEVER
  treated as rulings. Open questions queue for the founder checkpoint.
- Main HEAD: 97d54477 (foundation PR #62 merged 2026-10-30 morning EDT;
  D-007 approved by the founder 2026-10-30).
- Main health: RED on one gate — Test Frontend (Next.js), "Reject production and
  critical dependency advisories". Flagged dependency identified by the
  consumer-domains lane on #66: GHSA-6pq8-jhm2-2vcw, moderate, qs <= 6.16.0 via
  brandme-chain > express > qs. Founder decision pending: re-run first, or
  dependency remediation if it persists. Post-#62-merge push-run checks not yet
  verified — re-check at the next hourly pass.
- Checkpoint: 5 days after this seed lands on main (seed day = day 1). The loop
  pauses for founder review at each checkpoint and resumes on the founder's go.
- Monitor cadence: Mia checks every hour — lane status files (finish?), PR/check
  state (review gate?), limit reports (refresh?).
- Review gate (per merge): CI green on the exact head SHA, mergeable clean, scope
  inside the lane's exclusive files, no secrets committed, credential manifest
  hygiene, plus Mia's evidence-vs-spec review. Green + clean + in-scope merges
  under the standing aggressive auto-merge posture, rationale comment first.
- Retry rule: one triage fix attempt per failed assignment (small, safe,
  high-confidence fixes only, as a [triage] PR to the bench branch). Still red
  after that, the lane parks and escalates with the failure + proposed fix.
  Other lanes continue.
- Token limits: each lane runs on a max-tier plan. On hitting a limit, the lane
  reports `limited until <refresh time>` in its status file; Mia parks it and
  resumes on refresh via hourly checks. Silence past the refresh window gets
  flagged; silence before it does not.
- Kill switch: a PAUSED file in docs/build/orchestration/, or any founder "stop"
  message, stops all triggers immediately.

## Per-lane status (verified 2026-10-30 morning EDT)
- **Foundation (Opus) — MERGED.** PR #62 merged (merge commit 97d54477).
  D-007 (Q9 redaction split: table owner redacts undelivered payloads, not the
  privacy lane) approved by the founder 2026-10-30. Q11 trimmed; #61 flags folded
  in; Q8 round trip 54 contracts. Next: ultra-plan-02 foundation draft (following
  queue). wip/fb2 token fold deferred to round 5 remains open.
- **Consumer-domains (Opus) — PR #66, draft, head b5e8ea4 (as of 2026-10-30 07:38
  watch).** Stage 19 status; session proved alive overnight. Item 9 (lane outbox
  worker deletion) UNBLOCKED by the #62 merge (Q8 import now on main); trigger
  comment posted 2026-10-30 morning. Lane undrafts for auto-merge once CI is
  green. Known: Test Frontend advisory failure on b5e8ea4 is the same qs advisory
  as main (not this PR's); one Test Core failure (logging redaction test) which
  the lane reports as not this PR's.
- **Commerce-agents (Opus) — no open PR.** Round-03 oneshot plan is on main via
  #67; needs a fresh branch to start. Money-path proof still gated on the two
  founder keys (STRIPE_TEST_SECRET_KEY, BRANDME_DEV_ANTHROPIC_API_KEY — names-only
  check 2026-10-30 morning: only GCP_SA_KEY present).
- **Midnight-rights (Opus) — no open PR.** Round-03 ultra plan is on main via #67;
  needs a fresh branch to start.
- **Consumer-ui (Astra) — PR #63, draft, visual-baseline gate.** No head change
  overnight; session-alive status still unproven (only status-check comments).
- **Spatial-ar (Astra) — PR #60, draft, head 2852b786.** Only red is the
  browser/pose check, lane-owned. No head change overnight; session-alive status
  still unproven.

## Queue order (from #67, on main)
1. Round-03 next plans (all six lanes) — foundation's item complete via #62;
   others in progress or queued.
2. Ultra-plan-02 drafts (six lane plans + new-lane proposal) — following queue.
   The ultra-plan-02 drafts live locally until activated; they are NOT yet in the
   repo. The new-lane pick itself remains genuinely open (two proposed sets,
   neither approved).

## Open founder gates (park, never stall the whole loop)
- Main Test Frontend audit: re-run vs remediation (qs GHSA-6pq8-jhm2-2vcw).
- Two founder keys (above) — gate the money-path proof only.
- New-lane pick; ChatGPT app designs location (consumer-ui reconciliation still
  starts with finding and diffing them).
- Founder check of Claude/Codex sessions: foundation and consumer-domains proved
  alive overnight; consumer-ui, spatial, commerce, and midnight have not yet
  demonstrated a live session in this window.
- Founder digest + lane check-in self-assessments — still owed by Mia, not claimed
  done here.
