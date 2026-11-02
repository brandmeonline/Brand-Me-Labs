# Ultra plan 03 — Astra Spatial-AR (land Stage 18 + fit evidence)

**Shape: ULTRA — deep multi-stage wave with a 21-question check-in.**
**Status: Prepared 2026-10-25 — founder approved push + trigger 2026-10-25.**
**Supersedes:** `ultra-plan-02-astra-spatial-ar.md` (round-02 draft, never triggered —
its "new PR targeting main" step has since happened as #60; base state updated).
**Repo:** brandmeonline/Brand-Me-Labs · **Lane branch:** `bench/astra-spatial-ar-20261005` ·
**Vehicle PR:** #60 (draft, dirty, 15 commits, head `2852b786`)

## State at issue (verified 2026-10-25, main `2b5ae889`)

- #36 (original closet assets, outfit editor, gated AR journey) merged into the SPEC branch,
  not main. #60 is this lane's first PR targeting main: "guest fit ladder, Pod model and
  scan boundaries." It is draft + dirty vs new main, with one failing check: "Spatial
  browser and local pose." Land it first; do not build the wave on top of a red, dirty PR.
- Built so far: spatial asset pipeline (rooms/garments, GLB/USDZ + manifests + rights),
  OutfitEditor v1, saved views, capsule tray, placement, keyboard-accessibility milestone,
  local pose + gated dev preview flows (same-origin MediaPipe pose inference, synthetic-only
  photo adapter, measurement preparation, native-device session protocol).
- Pose evidence today is single-fixture only: 33 landmarks on a synthetic fixture, 87.5 ms
  median inference (container CPU), 23.64 px mean error on 8 coarse annotations; the 15–30 Hz
  device target is explicitly NOT established (the lane states this itself — credit).
- Locked design this lane must now serve (fit ladder): (1) tailor questions + per-house
  size learning + inference for everyone, day one; (2) photogrammetry with honest
  confidence, then depth/IR geometry on capable phones; (3) **the Pod** — physical
  3D-mapping installations at flagships/pop-ups, brands pay to host, pod captures
  calibrate the cheaper tiers; pods are a phase-two headline but the data model is
  designed now. Every measurement carries provenance; brands get fit outcomes, never raw
  body data.
- Also locked: closet environments as earned upgrades (starter → luxe walk-ins, wooden,
  IKEA-style dream closets); mobile friends see clean 2D scrolls, rich 3D is the owner's
  own closet; scan-a-garment experience (RFID/photo → cube → disclosure-filtered facets)
  with the split: spatial owns scan UX, midnight owns the anchor record.
- CI surface warning: the bench's evidence has been thin (single regression check-run).
  This round thickens it — a one-check-run PR is not evidence.

## Mission

Land Stage 18 on main, then replace synthetic-only demos with measured evidence: real dev
integrations, calibrated-fit numbers against known garments, the Pod data model, and the
scan experience — all honestly gated.

## Shared chassis

Dev/test scope only; no production data, no user photos beyond the lane's own test assets.
Secrets NEVER committed (GitHub secrets or gitignored `.env` only). Every credential
created gets a manifest entry in `docs/build/status/astra-spatial-ar.md` (name, scope,
where stored, date — never the value). Least privilege by default. Anything needing prod
scope gets a dev equivalent plus a flag in the check-in questions. Check-in protocol: stop
before any irreversible or prod-scoped step; deliver evidence plus exactly 21 questions
(7 direction / 7 integration & security / 7 scope & sequencing) with recommended
defaults. Until check-in, build on defaults — do not stall.

## Build, in order

1. **Land #60.** Re-sync with main `2b5ae889`, resolve conflicts, fix the failing
   "Spatial browser and local pose" check, re-verify from a clean checkout, undraft →
   auto-merge on green + clean. #60's guest fit ladder + Pod model + scan boundaries are
   the foundation of this round, not a side branch.
2. **Pose-model dev integration.** Real provider wired on the dev tier if terms allow,
   else a documented local model — exercised end-to-end in the try-on flow with
   accuracy/latency evidence recorded. Pose payloads stay excluded from source until
   redistribution terms clear.
3. **Photo-provider dev integration.** Upload → processing → closet asset on the
   provider's dev tier, test assets only.
4. **Calibrated-fit evidence.** Measured error against known garments, reported as
   numbers with method + fixture counts — not adjectives. The ladder's credibility is a
   measurement claim; claims need receipts.
5. **Fit ladder, tier 1 + 2.** Tailor-question flow + per-house size learning +
   inference; photogrammetry with honest confidence labels ("our best reading"); depth/IR
   path stubbed for capable phones with capability detection.
6. **Pod data model (design now).** Capture schema, calibration fields linking pod captures
   to cheaper tiers, provenance fields on every measurement. No physical pod build this
   round — the model is the deliverable.
7. **Scan UX.** Photo/RFID scan → cube resolution (midnight's anchor record) →
   disclosure-filtered facets (locked default: identity/house/maker/story to strangers;
   price/ownership/logistics only on owner unfold). This lane owns the experience;
   midnight owns the record and filter. Sequence note: scan UX can demo against midnight's
   anchor schema as it lands — coordinate, don't block on midnight's full round.
8. **Closet environments (3D assets).** Starter variants as 3D assets; luxe walk-ins as
   earned-upgrade assets. Shell rendering stays consumer-ui's; this lane owns the assets.
9. **Native AR device protocol.** Device-test protocol + build/device checklist so a
   founder device session is a single sitting, not a discovery exercise.
10. **CI surface thickening.** Add module checks beyond the single regression run so the
    next PR's evidence is not one check-run deep.

## Exclusive file ownership

- Spatial assets (rooms/garments, GLB/USDZ + manifests), OutfitEditor, pose/try-on flows,
  fit pipeline + Pod data model, scan UX, the lane status doc.
- Do NOT touch foundation files, domain/commerce/chain code, or frontend shell code. Scan
  resolution consumes midnight's anchor record; it does not reimplement it. Closet rendering
  shell belongs to consumer-ui.

## Exit evidence (all required)

- [ ] #60 merged to main (re-synced, browser check fixed).
- [ ] Pose-model dev integration wired end-to-end with accuracy/latency numbers.
- [ ] Photo-provider dev integration wired end-to-end, test assets only.
- [ ] Calibrated-fit evidence: measured error vs known garments, method + fixture counts
  stated.
- [ ] Fit ladder tiers 1–2 live with honest confidence labels; depth/IR capability
  detection stubbed.
- [ ] Pod data model documented (capture schema, calibration linkage, provenance fields).
- [ ] Scan UX demonstrated against the anchor record with disclosure-filtered facets.
- [ ] Starter closet-environment assets delivered; upgrade path defined.
- [ ] Native device protocol + checklist ready for a founder session.
- [ ] CI surface thicker than one check-run on the new PR.

## Check-in trigger

When #60 is on main, dev integrations are wired, fit-evidence numbers are recorded, and
the Pod data model is documented.

## Founder inputs this lane cannot self-serve

- Google Cloud dev project with Virtual Try-On access + short-lived least-privilege token
  (dev tier; no production tier implied).
- Pose-model redistribution review clearance (payloads excluded from source until terms clear).
- Native device session (45 min) + measurement session (30 min, 18 readings, one physical
  garment) — evidence counts only for devices actually tested.
- Foundation client/token contract for authenticated integration (gates the authenticated
  round, not this one).

## Check-in questions (21, with recommended defaults)

### Direction (7)

1. #60 path: re-sync + fix + land as the round's foundation, or split scan boundaries
   out? **Default: land as-is once green.**
2. Review target: guest milestone for review, authenticated integration as a separate
   gated round? **Default: yes — guest milestone.**
3. Pose model: real provider dev tier if terms allow, else documented local model?
   **Default: real dev tier if terms allow.**
4. Photo provider: dev-tier upload → processing → closet asset? **Default: yes, test
   assets only.**
5. Pod data model: design now for phase-two pods (captures calibrate cheaper tiers)?
   **Default: yes.**
6. Closet environments: starter variants now, luxe walk-ins as earned upgrades?
   **Default: yes.**
7. Scan UX: spatial owns the experience, midnight owns the anchor record — confirm?
   **Default: yes.**

### Integration & security (7)

8. Body data: brands get fit outcomes, never raw body data — architectural rule?
   **Default: yes, enforced.**
9. Measurement provenance: every measurement carries tier + source? **Default: yes.**
10. Pose payloads: excluded from source until redistribution terms clear? **Default: yes.**
11. Native AR: device-test protocol + checklist ready before any founder session?
    **Default: yes.**
12. Authenticated storage: gated on the foundation client/token contract — do not build
    around it? **Default: yes.**
13. Test assets: no user photos beyond the lane's own test assets? **Default: yes.**
14. Views: mobile friends see clean 2D scrolls, rich 3D is the owner's own closet?
    **Default: yes.**

### Scope & sequencing (7)

15. Order: #60 → dev integrations → fit evidence → Pod model → scan UX (Pod model
    parallel)? **Default: yes.**
16. Fit evidence standard: measured error vs known garments, numbers not adjectives?
    **Default: yes.**
17. Device sessions: 45-min native + 30-min measurement with the founder? **Default:
    schedule; evidence only for devices tested.**
18. PR path: #60 targets main (already does) — no spec-branch detour? **Default: yes.**
19. Check-in trigger: #60 on main + dev integrations wired + fit numbers + Pod model
    documented? **Default: yes.**
20. Device rate: report the measured rate honestly; 15–30 Hz target stays open until the
    device session? **Default: yes.**
21. Next round: native AR + authenticated integration after the token contract?
    **Default: yes.**
