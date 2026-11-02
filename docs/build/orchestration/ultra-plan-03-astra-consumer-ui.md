# Ultra plan 03 — Astra Consumer-UI (design-implementation wave + ChatGPT reconciliation)

**Shape: ULTRA — deep multi-stage wave with a 21-question check-in.**
**Status: Prepared 2026-10-25 — founder approved push + trigger 2026-10-25.**
**Supersedes:** `ultra-plan-02-astra-consumer-ui.md` (round-02 draft, never triggered —
its step 1, the #56 re-sync + retarget, has since landed: #56 merged to main).
**Repo:** brandmeonline/Brand-Me-Labs · **Lane branch:** `bench/astra-consumer-ui-20261005` ·
**Vehicle PR:** #63 (draft, unstable, 19 commits, head `2f89dce5`)

## State at issue (verified 2026-10-25, main `2b5ae889`)

- #56 (consumer journeys, foundation integration, versioned shell contract) is ON MAIN
  (merge commit `b9f483be`) — the frontend is on main, the shell contract is published
  (1.1.1 via #65), and the visual-baseline gate was cleared by the founder's corrected
  baseline push. The re-sync/retarget question is closed.
- #63 (design preview: three rooms, private style card, optional heartbeat) is open, draft,
  unstable, with a failing `shell` check. Land it first; do not build the wave on top of
  a red PR.
- What is NOT in the build yet — and is the largest forward workload in the program — is
  the Oct 23 locked design surface: three rooms (Shops / Social / Closet), Home = Flow,
  the three Social horizons (Now / Flow / Editorial, with brand/designer feeds as a
  separate parallel stream), invite-only entry + waitlist-with-perks, the gesture model
  (quiet first, hold-the-cube radial), progressive mastery, haptic heartbeat, persona
  card, gallery-minimal luxury (runway-grade imagery, no prices in the social feed).
- External evidence gates still open: device sessions, screen-reader sessions,
  pixel-comparison rerun on a new head. Visual baselines are reviewed artifacts, never
  auto-approved.
- **Previous ChatGPT app designs — INPUT GAP, stated plainly.** No artifact identified as
  "previous ChatGPT app designs" was found in the repo spec docs, the workspace, or the
  recorded memory (ChatGPT's documented stewardship is the Lux repo, not Brand.Me). This
  plan therefore treats those designs as a NAMED INPUT the lane must obtain and reconcile
  (build step 1), not as material it can quote from memory. If the founder supplies the
  designs' location (file, link, or chat), the reconciliation step grounds itself in them
  exactly; until then it proceeds from the locked Oct 23 layer + the spec screen contracts
  and flags the gap at check-in.

## Mission

Build the locked experience surface on main against the dev gateway with live data, not
fixtures — and reconcile it against the previous ChatGPT app designs so nothing valuable
from that earlier design work is silently lost or silently contradicted.

## Shared chassis

Dev/test scope only; no production data. Secrets NEVER committed (GitHub secrets or
gitignored `.env` only). Every credential created gets a manifest entry in
`docs/build/status/astra-consumer-ui.md` (name, scope, where stored, date — never the
value). Least privilege by default. Anything needing prod scope gets a dev equivalent plus
a flag in the check-in questions. Check-in protocol: stop before any irreversible or
prod-scoped step; deliver evidence plus exactly 21 questions (7 direction / 7 integration
& security / 7 scope & sequencing) with recommended defaults. Until check-in, build on
defaults — do not stall.

## Build, in order

1. **ChatGPT-design reconciliation (do this FIRST, before new surface work).**
   Obtain the previous ChatGPT app designs (screens, flows, interaction notes — location
   per the founder flag below; if not supplied, record the gap and proceed from the locked
   layer + spec contracts). Diff them screen-by-screen against three authorities, in this
   precedence order: (a) the locked Oct 23 design decisions (rooms, Home = Flow, Now/Flow/
   Editorial, invite/waitlist, gesture model, gallery rules, disclosure default); (b) the
   spec screen contracts in `docs/design/brandme/02-visual-motion-spatial.md` (Today,
   Looking Glass, Closet compositions; warm-paper/ink/walnut/limestone art direction;
   Cormorant Garamond display + Manrope UI; 44px touch targets); (c) the currently merged
   UI on main. For every ChatGPT design element, record one of: ADOPT (carried into the
   wave, naming where), ADAPT (carried with a stated change + reason), or DISCARD (conflicts
   with a locked decision — name the decision it conflicts with). NO silent drops: every
   discard gets a reason in the reconciliation report. The report is exit evidence, not an
   aside.
2. **Land #63.** Fix the failing `shell` check, re-verify from a clean checkout, undraft
   → auto-merge on green + clean. #63's rooms preview + style card + heartbeat are the
   seed of the wave, not a side branch.
3. **Three rooms.** Shops / Social / Closet as separate, interconnected experiences;
   Home = Flow (newest from the member's houses through the persona lens, friend decision
   requests cutting in).
4. **Social horizons.** Now (timed decision requests, asker's "why," thumbs/comments,
   ~5-minute default window); Flow (living feed: freshness = position, excitement =
   size/depth); Editorial (hyper-curated brand/designer magazine layer; brand/designer
   feeds as a separate parallel stream alongside friends' social).
5. **Invite + waitlist.** Invite-only front door; members hold invites; non-members see
   the brand/runway shop window; waitlist with perks (early drop looks, engagement bumps,
   first invite to give away, concierge preview for the most engaged).
6. **Gesture model + progressive mastery.** Quiet first look, then one light gesture to
   share; hold-the-cube radial (share to friend / small group / purchase); simple actions
   at onboarding, advanced gestures unlocking as in-app upgrades. No button clutter.
7. **Persona card.** Living style-identity card (taste axes, badges, house standings,
   curated closet highlights), searchable/followable, recomposing as style evolves.
8. **Luxury gallery rules.** Runway-grade imagery only; no prices in the social feed —
   asserted by test; gallery, not marketplace. Curator voice user-controlled (off /
   one-line / story) and culture-aware; verbosity user-set.
9. **Haptics.** Haptic heartbeat on friend responses where the platform supports it,
   graceful degradation elsewhere.
10. **House pings.** Volume set by member signal preference + loyalty standing + active
    interests.
11. **Closet environments (starter path).** Starter variants now; luxe walk-ins and dream
    closets as earned upgrades. Mobile: friends see clean 2D scrolls; rich 3D is the
    owner's own closet view (spatial owns the 3D assets; this lane owns the shell they
    render in).
12. **Real gateway wiring.** Persona, wardrobe, social, rewards surfaces rendering live dev
    data — fixtures remain only as test doubles.
13. **Accessibility + visual gates.** A11y pass on shell primitives with CI checks;
    pixel-comparison rerun on the new head; baselines reviewed by a human, never
    auto-approved.
14. **Device/screen-reader sessions.** Founder sessions scheduled; evidence counts only for
    devices actually tested; external release stays gated on this evidence.

## Exclusive file ownership

- `brandme-frontend/`, the shell contract artifact (`@/components/console-contract`),
  visual baselines (`brandme-frontend/lib/testing/baselines/`), the lane status doc.
- Do NOT touch foundation files, domain/commerce/chain code, or spatial asset code.
  Backend lanes consume the contract; this lane publishes it. The reconciliation report lives
  in the lane status doc + `docs/build/orchestration/` as a durable record.

## Exit evidence (all required)

- [ ] ChatGPT reconciliation report delivered: every previous-design element marked
  ADOPT / ADAPT / DISCARD with reasons; zero silent drops (or the input gap stated plainly
  if the designs were not supplied).
- [ ] #63 merged to main (shell check fixed).
- [ ] Three rooms + Home = Flow live against the dev gateway with live data.
- [ ] Now / Flow / Editorial horizons live, including brand feeds as a parallel stream.
- [ ] Invite + waitlist flows live with the perks model.
- [ ] Gesture model + progressive mastery demonstrated (hold-cube radial working).
- [ ] Persona card live; gallery rules enforced (no prices in the social feed — asserted
  by test).
- [ ] A11y CI checks green; visual baselines human-reviewed.
- [ ] Device + screen-reader session evidence recorded (or scheduled with dates, stated
  plainly if not yet run).

## Check-in trigger

When the rooms + Now/Flow horizons are live against the dev gateway on main AND the
reconciliation report is delivered.

## Founder inputs this lane cannot self-serve

- **Previous ChatGPT app designs — location.** The single input this plan cannot
  self-serve: where those designs live (file, link, or chat thread). Without them, step 1
  records the gap and proceeds from the locked layer + spec contracts.
- Visual-baseline approval if routed to the founder (baselines are reviewed artifacts).
- Device + screen-reader session time.
- External-release gate decision (internal preview now; external only with device/
  screen-reader evidence).

## Check-in questions (21, with recommended defaults)

### Direction (7)

1. ChatGPT reconciliation: adopt what does not conflict with locked decisions, adapt the
   rest with stated reasons, discard conflicts with named reasons? **Default: yes, with a
   written report — no silent drops.**
2. If the ChatGPT designs are not supplied: proceed from the locked layer + spec contracts
   and flag the gap, rather than stalling the wave? **Default: yes, proceed + flag.**
3. Three rooms: Shops / Social / Closet as separate interconnected experiences?
   **Default: yes.**
4. Home = Flow: newest from houses through the persona lens, decision requests cutting in?
   **Default: yes.**
5. Social horizons: Now / Flow / Editorial, with brand feeds as a parallel stream?
   **Default: yes, all three + parallel brand stream.**
6. Access: invite-only front door + waitlist with perks? **Default: yes.**
7. Gesture model: quiet first, hold-cube radial, progressive mastery? **Default: yes.**

### Integration & security (7)

8. Spec contracts: spec 02 screen compositions (Today / Looking Glass / Closet) + art
   direction as the visual authority where ChatGPT designs are silent? **Default: yes.**
9. Gateway wiring: live dev data on all surfaces, fixtures as test doubles only?
   **Default: yes.**
10. Accessibility: a11y pass on shell primitives with CI checks? **Default: yes.**
11. Visual regression: pixel-comparison rerun on the new head; baselines human-reviewed,
    never auto-approved? **Default: yes.**
12. Haptics: haptic heartbeat where the platform supports it, graceful degradation
    elsewhere? **Default: yes.**
13. Curator voice: user-controlled verbosity (off / one-line / story), culture-aware?
    **Default: yes, user-set.**
14. House pings: volume by signal preference + standing + interests? **Default: yes.**

### Scope & sequencing (7)

15. Order: reconciliation → #63 → rooms → Now/Flow → invite/waitlist → gestures?
    **Default: yes.**
16. Device/screen-reader sessions: scheduled this round, evidence-gated before external
    release? **Default: yes.**
17. Closet environments: starter variants now, luxe walk-ins as earned upgrades?
    **Default: yes.**
18. Persona card: living card (taste axes, badges, standings, highlights)? **Default: yes.**
19. Check-in trigger: rooms + Now/Flow live on main + reconciliation report delivered?
    **Default: yes.**
20. W01 acceptance: visual gate + device evidence closed this round? **Default: yes.**
21. Next round: editorial polish + brand-feed depth after rooms? **Default: yes.**
