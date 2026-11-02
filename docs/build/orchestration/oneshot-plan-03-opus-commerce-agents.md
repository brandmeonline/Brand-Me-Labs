# Oneshot plan 03 — Opus Commerce-Agents (land round 3 + money-path proof)

**Shape: ONESHOT — one PR + one proof run, no 21-question check-in.** Exit evidence is
the deliverable; founder flags are a short list, not a question packet.
**Status: Prepared 2026-10-25 — founder approved push + trigger 2026-10-25.**
**Supersedes:** `ultra-plan-02-opus-commerce-agents.md` (round-02 draft, never triggered —
#51 has since merged, so its Q11-unblock step is moot).
**Repo:** brandmeonline/Brand-Me-Labs · **Lane branch:** `bench/opus-commerce-agents-20261005` ·
**Vehicle PR:** #64 (draft, unstable, 8 commits, head `8c1126f8`)

## State at issue (verified 2026-10-25, main `2b5ae889`)

- #51 (round 2: foundation adoption, payments/fulfillment seam, Stripe test-mode processor,
  dev model planner, console ops pages) is ON MAIN (merge commit `7c4c1cd2`). Q11 is
  resolved by events via #51's own head — no rebase onto pins is needed anymore.
- #64 (round 3: audit closure, autonomy boundaries, partner tiers, shell swap) advanced
  from 3 to 8 commits and flipped clean → unstable. The lane must say what turned it
  unstable and fix that first; do not undraft over a red check.
- The program's money-path proof is STILL UNPROVEN: one end-to-end purchase in Stripe test
  mode, agent-assisted inside a user-set cap, fully audited. This oneshot exists to produce
  it — it is the single most persuasive demo artifact in the program.
- Founder keys (`STRIPE_TEST_SECRET_KEY`, `BRANDME_DEV_ANTHROPIC_API_KEY`) remain
  unfostered. Interim direction stands: run the proof on lane-created demo/test keys under
  the fostering rules; swap to founder-fostered keys mechanically when they land, without
  code changes. Do not block the proof on the founder keys.
- Round-02 claimed-but-unproven items, carried: provider `setup.update`/`verify`
  (`_not_built`); assistant runtime MCP `_dispatch` bypass of the audit record; Stripe
  test-mode adapter `not_run`; model planner `not_run`. #64's "audit closure" title claims
  progress — the exit evidence below verifies it instead of trusting it.

## Mission

Land #64 and record the money-path proof: simulator → real test flow, one purchase
end-to-end, cap-respecting agent assistance, fully audited, with test-mode transaction
evidence in the status doc.

## Shared chassis (oneshot version)

Stripe test mode ONLY — no live charges, no production data, no real funds. Secrets NEVER
committed (GitHub secrets or gitignored `.env` only). Every credential created gets a
manifest entry in the lane status doc (name, scope, where stored, date — never the value).
Least privilege by default. No check-in protocol on a oneshot: the lane lands the PR,
records the proof, and reports exit evidence; anything needing prod scope stops and flags
to the founder instead.

## Build, in order

1. **Stabilize #64.** Name and fix whatever turned it unstable (it was clean at 3 commits).
   Full suite green on the head is the undraft precondition — no exceptions.
2. **Audit-path proof (blocking for any real transaction).** Every assistant runtime tool
   call goes through the audited path — no `_dispatch` bypass. Add a test proving every
   tool call writes an audit record. Do not run the money proof before this is green.
3. **Provider setup/verify.** Finish `provider.setup.update` / `provider.verify` (the
   `_not_built` items); save/test working from the console page.
4. **Money-path proof run.** Simulator → real test flow, one purchase end-to-end: provider
   setup, cart, grant-scoped cart, cap-respecting agent assistance, test-mode charge,
   idempotent return path, fulfillment seam. Demo keys now (manifest-logged); swap to
   founder keys mechanically when fostered. Record test-mode transaction IDs in the status
   doc (test-mode IDs only, never live).
5. **Model planner on the dev key.** Agent runs against real model APIs with the dev key;
   runs logged under foundation log/redaction rules.
6. **Autonomy boundaries live.** User-set boundaries per brand / wishlist / price cap;
   concierge-prepares default; autonomous action only inside boundaries. Prove with a test
   where an over-cap action is refused or held for approval. Log every autonomy decision
   (feeds the open agent-autonomy research question; the research itself is a founder
   commission, not lane scope).
7. **Tier enforcement mechanics.** Quota/customization/analytics/member-connection
   enforcement against a pricing-table interface — placeholder tiers until the founder
   prices them. Do not invent prices.
8. **Shell header swap.** Replace the local console header with consumer-ui's published
   contract component (one-change seam already exists; the enforce ruling stands).
9. **Simulator fidelity close-out.** S13 exchange fidelity vs BM-COM-011, with a fidelity
   checklist in the packet.
10. **Outbox registration.** Register commerce events with foundation's Q8 catalog import.
11. **Undraft and land.** Aggressive posture: auto-merge on green + clean.

## Exclusive file ownership

- `brandme_core/domains/commerce/`, provider adapters, simulator exchange, ops console
  pages, agent runtime + planner, the lane status doc.
- Do NOT touch foundation files (workflows, lock, worker), consumer-domains code, frontend
  code, or chain code.

## Exit evidence (all required)

- [ ] #64 merged to main (stabilized, adversarial review closed).
- [ ] Audit-path test green: zero tool calls bypass the audit record.
- [ ] Provider setup save/test working from the console page.
- [ ] Proof run recorded: one simulator → test-mode purchase end-to-end, with test-mode
  transaction evidence in the status doc.
- [ ] Model planner run on the dev key, logged per redaction rules.
- [ ] Over-cap refusal/hold test green; autonomy decisions logged.
- [ ] Tier enforcement mechanics behind a pricing-table interface; placeholder tiers clearly
  marked, no invented prices.
- [ ] Shell header swapped to the published contract component.
- [ ] S13 fidelity checklist + commerce events registered with the Q8 catalog.

## Founder flags (short list — no question packet on a oneshot)

- Key fostering (`STRIPE_TEST_SECRET_KEY`, `BRANDME_DEV_ANTHROPIC_API_KEY`) — proof runs on
  demo keys meanwhile; the swap is mechanical.
- B2B tier pricing/quotas — mechanics are built; prices are a founder decision.
- Agent-autonomy market research — commission or defer (founder decision; lane only logs).
