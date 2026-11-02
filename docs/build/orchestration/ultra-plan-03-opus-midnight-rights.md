# Ultra plan 03 — Opus Midnight-Rights (finality + anchor record)

**Shape: ULTRA — deep multi-stage wave with a 21-question check-in.**
**Status: Prepared 2026-10-25 — founder approved push + trigger 2026-10-25.**
**Supersedes:** `ultra-plan-02-opus-midnight-rights.md` (round-02 draft, never triggered —
base state updated: main is now `2b5ae889`, and the Q9 joint test now pairs with #62).
**Repo:** brandmeonline/Brand-Me-Labs · **Lane branch:** `bench/opus-midnight-rights-20261005`
(head `44aaceab`, STALE — see build step 1) · **No open midnight PR.**

## State at issue (verified 2026-10-25, main `2b5ae889`)

- On main: #54 (Midnight tuple re-pin: proof-server 8.1.3 + node 1.0.400, 7/7 local network
  verification), #43/#44/#45/#47/#48/#50 (rights routes, Spanner chain ops, projection
  worker, durable outbox, deletion freezes, rights exports with authenticated GCS downloads).
- Still open from PR #43's NOT-complete list: authenticated application command backends,
  durable operation store + reconciler hardening, remaining event producers, real-domain My
  Data registration.
- Still unproven, the program's largest unproven chain claim: **Preprod finality evidence**
  — no faucet-funded transaction observed to finality. `test:midnight:preprod` needs a
  Blockfrost Preprod project token + ≥3 funded seeds (tNIGHT/DUST); hosted endpoints were
  retired 2026-10-09, so the path is Blockfrost-only.
- Q9 deletion purge is a launch-blocker: foundation purges delivered rows (in #62); this
  lane redacts a deleted subject's undelivered `member_private` payloads. Joint deletion
  proof required.
- Locked design scope: **RFID anchor record** — scan event → cube resolution →
  disclosure-filtered response. Split (evening audit): midnight owns the anchor record,
  spatial owns the scan experience. Plus the locked disclosure default (strangers see
  identity/house/maker/story; price/ownership/logistics hidden unless the owner unfolds)
  and the full lifecycle audit (designer intent → cutter instructions → production →
  taxes → ownership → resale → deletion).
- The evening audit's deliberate-investment recommendation stands: **formal verification of
  disclosure/rights contracts** — this lane lays the groundwork (invariants as code tests);
  independent verification itself rides the proposed verification lane (still unapproved).

## Mission

Convert "proven locally" into "proven on Preprod," close the PR #43 remainder, and make
the disclosure default mechanically enforceable — with the formal-verification groundwork
that lets an independent lane check it.

## Shared chassis

Preprod/testnet ONLY — no Mainnet writes, no real funds, no production data. Secrets and
wallet seeds NEVER committed (GitHub secrets or gitignored `.env` only; seed phrases never
in any doc or log). Every credential gets a manifest entry in the lane status doc (name,
scope, where stored, date — never the value or seed). Least privilege by default. Anything
Mainnet-scoped gets a Preprod equivalent plus a flag in the check-in questions. Check-in
protocol: stop before any irreversible or prod-scoped step; deliver evidence plus exactly
21 questions (7 direction / 7 integration & security / 7 scope & sequencing) with
recommended defaults. Until check-in, build on defaults — do not stall.

## Build, in order

1. **Fresh branch off main `2b5ae889`.** The bench head is stale; do not build on
   `44aaceab`. New PR targeting main.
2. **Authenticated command backends.** Remaining commands behind principal/scope/CSRF/
   recent-auth, exercised end-to-end.
3. **Durable operation store + reconciler hardening.** Lease/clock edge cases,
   interrupted-broadcast recovery, read-only reconciler proof — on top of #44/#45.
4. **Remaining event producers into the durable outbox (#47).** Real-domain My Data
   registration live in dev form.
5. **Q9 redaction.** Redact a deleted subject's undelivered `member_private` payloads;
   prove jointly with foundation's #62 purge (zero member payload rows survive account
   deletion, delivered + undelivered paths).
6. **RFID anchor record.** Anchor record schema + scan-event ingestion + cube resolution +
   disclosure-filtered response enforcing the locked default. Scan UX itself is spatial's;
   this lane owns the record and the filter. Sequence note: the record schema can land
   before spatial's scan UX completes — do not wait on #60.
7. **Disclosure-default enforcement at the contract layer.** No facet crosses a disclosure
   boundary; ownership transfer preserves lineage; deletion actually deletes — as code
   invariants with tests, ready for independent verification.
8. **Preprod finality run.** The day founder-provisioned credentials land: submit real
   Preprod transactions from the faucet-funded wallet, capture finality, record tx IDs +
   finality timestamps in the status doc. Evidence standard: independently verifiable
   hashes/timestamps — screenshots are not evidence.
9. **Local re-verification.** Re-run the 7/7 local network verification on the final head;
   confirm no hosted-endpoint dependency remains anywhere (Blockfrost-only path).
10. **Privacy suite green throughout.** Deletion guards, incomplete-restore blocking,
    selected-rights exports.

## Exclusive file ownership

- Chain/Midnight modules, rights routes, privacy guards, durable op store/reconciler,
  anchor-record schema + disclosure filter, the lane status doc.
- Do NOT touch foundation files (workflows, lock, worker, mode-guard policy — the
  trust-inventory retype is foundation's edit; coordinate, don't self-apply),
  consumer-domains code, commerce code, or frontend code. Verification *specs* for the
  disclosure invariants live with the proposed verification lane; this lane owns the
  contract code + its own tests.

## Exit evidence (all required)

- [ ] New PR off main; authenticated command backends live behind auth, exercised
  end-to-end.
- [ ] Op store/reconciler hardening with edge-case tests green.
- [ ] Remaining producers wired into the outbox; My Data registration live in dev form.
- [ ] Q9 redaction test green (undelivered path); joint deletion proof with foundation's
  purge.
- [ ] Anchor record + disclosure-filtered scan response demonstrated on dev (stranger facets
  only, unless owner unfolds).
- [ ] Disclosure invariants as code tests (facet boundaries, lineage on transfer, deletion).
- [ ] Preprod finality evidence recorded (tx IDs + finality timestamps) — or, if credentials
  have not landed, a plain statement that finality is the single outstanding item (see
  check-in trigger).
- [ ] 7/7 local verification re-run on the final head; Blockfrost-only audit clean.
- [ ] Privacy suite green throughout.

## Check-in trigger

When authenticated commands + producers + redaction are complete. Finality evidence is
attached if credentials landed; if not, it is named as the single outstanding item rather
than blocking the packet — the lane must not stall the rest of the round waiting on
credentials.

## Founder inputs this lane cannot self-serve

- Blockfrost Midnight Preprod project token + ≥3 funded seeds (tNIGHT/DUST via faucet) —
  the highest-value credential unblock in the program.
- Mainnet go/no-go criteria approval (criteria defined by this lane; the decision itself is
  founder's, later).
- Trust-inventory retype execution (foundation's edit, coordinated).

## Check-in questions (21, with recommended defaults)

### Direction (7)

1. Preprod credentials: founder provisions Blockfrost + seeds, or lane self-serves via
   faucet? **Default: founder provisions; lane runs the day they land, local prep now.**
2. Mainnet criteria: define go/no-go criteria this round (not a Mainnet decision)?
   **Default: yes.**
3. RFID split: midnight owns the anchor record, spatial owns scan UX — confirm?
   **Default: yes.**
4. Formal verification scope: disclosure invariants first, or full rights contracts?
   **Default: disclosure invariants first.**
5. Trust-inventory retype: foundation makes the edit (it owns mode-guard policy)?
   **Default: yes — coordinate, don't self-apply.**
6. Wallet fostering: manifest + rotation plan for Preprod seeds, seeds never recorded?
   **Default: yes.**
7. Deletion: midnight owns redaction of undelivered `member_private` payloads (foundation
   owns purge)? **Default: yes.**

### Integration & security (7)

8. Authenticated commands: principal/scope/CSRF/recent-auth on all remaining commands?
   **Default: yes.**
9. Op store: lease/clock edge cases + interrupted-broadcast recovery hardened? **Default: yes.**
10. Remaining producers: wired into the outbox this round? **Default: yes.**
11. My Data registration: live in dev form? **Default: yes.**
12. Finality evidence: tx IDs + finality timestamps in the status doc, independently
    verifiable (no screenshots)? **Default: yes.**
13. Disclosure default: enforced at the contract layer (stranger facets only unless owner
    unfolds)? **Default: yes.**
14. Blockfrost-only: audit confirms no hosted-endpoint dependency remains? **Default: yes.**

### Scope & sequencing (7)

15. Order: auth commands → op store → producers → redaction → anchor → finality run?
    **Default: yes; finality run when credentials land (may be last).**
16. Branch: fresh branch off main `2b5ae889` (bench stale), PR targeting main? **Default: yes.**
17. Local network: re-run 7/7 verification on the final head? **Default: yes.**
18. Check-in trigger: auth + producers + redaction complete, finality attached if landed
    else named as the single outstanding item? **Default: yes.**
19. Privacy suite: deletion guards + incomplete-restore blocking green throughout?
    **Default: yes.**
20. Exports: selected-rights exports + authenticated GCS downloads — extend or harden only?
    **Default: harden only, no new scope.**
21. Next round: Mainnet-readiness round after finality, gated on founder go/no-go?
    **Default: yes.**
