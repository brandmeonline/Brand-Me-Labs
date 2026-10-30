# Brand.Me — founder questions, 2026-10-23 (Mia, orchestrator)

Companion to `brandme-full-assessment-20261023.md` (per-lane grades + evidence). Answer any part with "defaults" to take all of Mia's recommendations in that part, or answer by number.

## What I think we're really building (Mia's read — correct me where it's wrong)

Brand.Me is not a shopping app. It's a **consumer-owned fashion identity layer**: a person's verified digital wardrobe (what they own, how it fits, what it means) plus their style persona (the Looking Glass), wrapped in a rights-and-privacy core (Midnight ownership proofs, My Data export/delete) that makes the identity *theirs* — portable, provable, deletable. On top of that identity sit two engines: **social decisions** (your circle helps you decide, fast, under your privacy rules) and **bounded commerce agents** (they research and prepare, but can only act inside authority you granted, at terms you approved). Brands/retailers plug in as providers; they never own the customer relationship. Why it exists: today your fashion identity is fragmented across retailer accounts that own it, monetize it, and can't be deleted. Brand.Me inverts that. Every build decision below is really a question about how literally we take that inversion before go-live.

## Part 1 — Product & user stories

1. **First customer.** Launch story = the style-conscious member with an overflowing closet and decision fatigue (Looking Glass + wardrobe + 5-minute decisions), not the crypto/ownership collector. *Default: yes — ownership is the trust layer, not the headline.*
2. **The 90-second win.** Onboarding must end with one real item in the closet + persona axes set (guest, idempotent migration), not a tour. *Default: keep the spec's 90-second onboarding as a hard go-live gate.*
3. **Guest vs account.** Guest milestone (spatial) ships as the public demo; accounts gate social/rewards/rights. *Default: yes.*
4. **The core loop.** Add item → outfit → ask circle → decide in 5 minutes → wear/reward. Everything else is supporting. *Default: freeze new surfaces that don't feed this loop until W11 acceptance passes.*
5. **Who sees what.** Shares are per-recipient, expiring, revocable (PD-09/10/11, ratified) — no audience-list documents, ever. *Default: ratified rules stand as the product's privacy promise; marketing copy must match them exactly.*
6. **Rewards purpose.** Rewards pay for identity-building actions (first item, meaningful setup, decisions), never for purchases alone. *Default: keep launch rule table as ruled (referral/research dropped, ids reserved).*

## Part 2 — Flows & interfaces

7. **Decision flow.** Server-timed 5-minute decisions with blind-until-response semantics are the signature interaction. *Default: keep 5 minutes; the closer is a real scheduled job at integration (not just a callable) before external release.*
8. **Shell/interface contract.** Enforce consumer-ui contract v1.1.0 (already ruled in substance by both lanes). *Default: enforce — each landing PR swaps its local header for the shared component; no further rulings needed.*
9. **Ops console.** Operators get moderation + reward-dispute pages under `moderation:admin`, aal2, no delegation, no self-review. *Default: keep — this is the trust-and-safety interface; do not soften for launch convenience.*
10. **Agent interface.** Agents act via MCP/AP2 with audience-bound tokens; an agent can prepare a purchase but never execute past approved terms (proven in #51 S14). *Default: this bound is a go-live criterion, not a feature — no launch with an unbound path.*
11. **Contracts ownership.** PD-09 endpoints fold into `packages/contracts` by the contracts/foundation lane (handoff from #52 rulings). *Default: foundation does it in the Q8/Q9 follow-on PR, not a new lane.*

## Part 3 — Third-party tools & frameworks (leverage vs build)

12. **Midnight/Blockfrost (C1).** Create the Blockfrost Midnight Preprod project + ≥3 funded seeds (tNIGHT/DUST). *Default: yes — highest-value unblock in the program; converts W09 from locally-proven to Preprod-proven and gates any Mainnet conversation.*
13. **Commerce secrets (C2).** Add `STRIPE_TEST_SECRET_KEY` (test mode) + `BRANDME_DEV_ANTHROPIC_API_KEY` as env secrets, manifest-logged. *Default: yes, dev/test scope only.*
14. **Try-on/photo (C3).** Google Cloud dev project with Virtual Try-On access for spatial; pose-model payloads stay out of distributable builds until redistribution terms clear. *Default: yes to dev access, hold on payloads.*
15. **Media storage (C4).** Dev GCS bucket (24h lifecycle) + dev service account so consumer-domains builds the GCS `MediaStore` (its ruled next build). *Default: yes, dev-only.*
16. **Retailers.** Nordstrom = Impact deep-link only; no guessed retailer APIs, no scraping — leverage affiliate frameworks until a retailer signs a real API agreement. *Default: keep.*
17. **Stack leverage.** Stay on the proven framework set — Next 15/React 19, Spanner (system of record), Firestore (projections), Pub/Sub outbox, Midnight (rights) — and resist swapping any of them before go-live. *Default: freeze.*

## Part 4 — Go-live

18. **Release gates (D2).** Internal preview now; external release requires real-device + screen-reader evidence, the pixel-comparison pass, and the full acceptance catalog on converged main. *Default: yes.*
19. **Q9 purge (B2) — launch-blocker.** Foundation purges delivered outbox rows after 7 days; privacy lane redacts a deleted subject's undelivered payloads. *Default: schedule immediately after the merge train; no external release with member payloads surviving deletion.*
20. **Q8 outbox catalog (B1) + Q10 contract (B3).** Foundation worker imports the lane catalog modules; commerce registers `commerce.order.observed@1`. *Default: yes to both, same follow-on PR as #19.*
21. **Device sessions (D1).** Your 45-min native session (iOS+Android) + 30-min measurement segment with one physical garment. *Default: schedule both; claims count only for devices actually tested.*
22. **Trust inventory (D3).** Retype `chain.midnight` = SANDBOX, `chain.cardano` = UNCONFIGURED (foundation edits its own mode-guard config). *Default: yes.*
23. **Mainnet criteria.** No Mainnet writes until: Preprod finality evidence captured, deletion/Q9 closed, privacy-counsel review of retention (tombstones + anonymized reports). *Default: adopt as written.*

## Part 5 — Build/ops decisions still open (from the assessment)

24. **A4 — V015 + S9.** Note the V015 commerce migration deviation (avoids V007 checksum drift) and adopt the S9 CI-gating fix (remove `|| echo` masking in ci-cd.yml, gate lane suites, add the 4 digest-pinned runtime deps). *Default: yes to both — auto-merge is only safe on gating CI.*
25. **A5 — PR #56 path.** Retarget consumer-ui to main after #52 lands (overriding its packet's keep-base default). *Default: yes.*
26. **A6 — PR #36 review target.** Review spatial now as the bounded guest milestone; authenticated launch stays separate and gated. *Default: yes.*
27. **Merge train (residual).** #53 ✅ merged 2026-10-23 (1f0d7387), #54 ✅ merged 2026-10-23 (0c3d7ea2), #52 held on a one-file conflict (ci-cd.yml) — lane triggered to resolve; Mia auto-merges on green+clean. #51 after #52 (V015 noted per Q24). *Default: proceed as sequenced.*
28. **Auto-run configuration.** Aggressive posture as you set it: Mia auto-merges green+clean (incl. main), notates every merge on the PR, writes assignments as files in `docs/build/orchestration/` + trigger comments, builders keep sessions open/listening. *Default: keep; daily digest at 09:00 EDT on change days only.*
