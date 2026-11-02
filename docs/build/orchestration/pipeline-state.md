# Pipeline state — continuous build loop

Seeded 2026-10-30 from the approved pipeline design (pipeline-design-20261029.md:
repo-based, Mia-monitored; daily updates; pause for founder review every 5 days).
This file is the loop's single source of truth. Mia updates it on every transition
and commits the update. Lanes read their next assignment from the queue below.

Refreshed 2026-10-30 ~11:15 EDT: main c902317 (#60 merged), #66 Stage 21
undrafted + green but held, #63 Codex contact.

## Loop status
- Design: APPROVED by founder 2026-10-29. Check-in rule (option 3): lanes keep
  building on work independent of open questions; recommended defaults are NEVER
  treated as rulings. Open questions queue for the founder checkpoint.
- Main HEAD: c902317 (foundation PR #62 merged 2026-10-30 morning EDT,
  D-007 approved by the founder 2026-10-30; spatial PR #60 merged by the
  founder 2026-10-30 10:18 EDT).
- Main health: FULLY GREEN on c902317 (verified 2026-10-30 ~11:14 EDT:
  13 success + 1 skipped on the merge push run, nothing failing). The Test
  Frontend advisory failure cleared after the #62 merge; the re-run vs
  remediation decision is closed by events. Mechanism not established (do not
  attribute to #62's qs override). Flagged advisory for the record:
  GHSA-6pq8-jhm2-2vcw, moderate, qs <= 6.16.0 via brandme-chain > express >
  qs (identified by the consumer-domains lane on #66).
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

## Ping-pong protocol (added 2026-10-30, founder direction)
Every trigger must be answered, and every answer must be acknowledged, so Mia
always knows where each lane is. Full definition: pipeline-design-20261029.md.
- PING (lane → Mia): PR comment + status-file update (timestamp, assignment,
  stage, head SHA, next step). Required on: trigger receipt (within 24h),
  stage completion, check-in PR opened, limit hit (with refresh time), blocker.
- PONG (Mia → lane): acknowledgment comment at the next hourly check after
  seeing a ping, confirming receipt + next instruction (continue / redirect /
  park). The pong is the proof Mia saw it.
- Per lane below: `last ping` and `last pong`, updated on every transition.
- Escalation: trigger with no receipt ping after 24h = flagged unresponsive
  (never silently assumed alive or dead). Ping with no pong by the next hourly
  check = Mia's overdue item, surfaced in the next update.

## Per-lane status (verified 2026-10-30 ~11:15 EDT)
- **Foundation (Opus) — MERGED.** PR #62 merged (merge commit 97d54477).
  D-007 (Q9 redaction split: table owner redacts undelivered payloads, not the
  privacy lane) approved by the founder 2026-10-30. Q11 trimmed; #61 flags folded
  in; Q8 round trip 54 contracts. Next: ultra-plan-02 foundation draft (following
  queue). wip/fb2 token fold deferred to round 5 remains open.
  Last ping: round-4 status (pre-merge). Last pong: #62 merge 2026-10-30.
- **Consumer-domains (Opus) — PR #66, head e40ea7cd, Stage 21, UNDRAFTED.**
  Session proved alive overnight and through the morning. Item 9 (lane outbox
  worker deletion) UNBLOCKED by the #62 merge (Q8 import now on main); trigger
  comment posted 2026-10-30 morning. Checks on e40ea7cd green at last check
  (21 success + 1 skipped), mergeable clean — but HELD, not merged, on two
  items: (1) Codex review still running on the head (triggered by
  draft-marked-ready); (2) foundation approval pending for two deviations
  recorded in the lane status file (c488c25 foundation-test-count edit;
  catalog pins consumer-domains 36 → 37 / total 54 → 55), both marked
  "Approval: Foundation, at review". Merge follows review completion +
  foundation approval (or founder decision).
  Last ping: Stage 21 status on #66; undrafted 2026-10-30. Last pong:
  hold notice 2026-10-30 (review + foundation approval pending).
- **Commerce-agents (Opus) — no open PR.** Round-03 oneshot plan is on main via
  #67; needs a fresh branch to start. Money-path proof still gated on the two
  founder keys (STRIPE_TEST_SECRET_KEY, BRANDME_DEV_ANTHROPIC_API_KEY — names-only
  check 2026-10-30 morning: only GCP_SA_KEY present).
  Last ping: none (no open PR). Last pong: round-03 plan on main via #67.
- **Midnight-rights (Opus) — no open PR.** Round-03 ultra plan is on main via #67;
  needs a fresh branch to start.
  Last ping: none (no open PR). Last pong: round-03 plan on main via #67.
- **Consumer-ui (Astra) — PR #63, draft, head 0ff12fb, visual-baseline gate.**
  Codex contact confirmed 2026-10-30: chatgpt-codex-connector bot re-synced the
  branch with main 97d54477 via merge commit 75f0ff0 and corrected the lane's
  claimed re-sync (docs-only). That reply counts as contact under ping-pong,
  not stage completion. Checks on 0ff12fb: 15 success + 1 skipped + shell
  failing; visual-baseline gate still open. Note: main has since advanced to
  c902317, so a further re-sync is needed before merge.
  Last ping: Codex re-sync reply 2026-10-30 (contact, not completion).
  Last pong: second kick-off trigger 2026-10-30 (comment 6524069655).
- **Spatial-ar (Astra) — MERGED.** PR #60 merged by the founder 2026-10-30
  10:18 EDT (merge commit c902317, head 3eddd28; 20 success + GKE skipped
  on the merged head, including Spatial browser and local pose passing, Codex
  zero findings, mergeable clean). Caveat: the merge lands code, not device
  proof — physical measurement session, native-device session, and
  live-provider run still NOT_RUN; pose evidence single-fixture.
  Last ping: merge (receipt obligation closed by the merge). Last pong:
  second kick-off trigger 2026-10-30 (comment 6524070094).

## Queue order (from #67, on main)
1. Round-03 next plans (all six lanes) — foundation's item complete via #62,
   spatial's item complete via #60; others in progress or queued.
2. Ultra-plan-02 drafts (six lane plans + new-lane proposal) — following queue.
   The ultra-plan-02 drafts live locally until activated; they are NOT yet in the
   repo. The new-lane pick itself remains genuinely open (two proposed sets,
   neither approved).

## Open founder gates (park, never stall the whole loop)
- Two founder keys (above) — gate the money-path proof only.
- New-lane pick; ChatGPT app designs location (consumer-ui reconciliation still
  starts with finding and diffing them).
- Founder check of Claude/Codex sessions: foundation and consumer-domains proved
  alive; spatial demonstrated via its merge; consumer-ui demonstrated contact
  via the Codex re-sync reply; commerce and midnight have not yet demonstrated
  a live session in this window.
- Founder digest + lane check-in self-assessments — still owed by Mia, not claimed
  done here.
