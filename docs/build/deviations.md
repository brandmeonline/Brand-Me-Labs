# Deviations

Format (ch.06 §1): requirement · reason · chosen replacement · product impact · evidence · founder approval needed?
Other lanes propose deviations in their own status files. The parent records accepted ones here at integration.

## D-001 V001 also contains platform tables (outbox, inbox, idempotency, audit)

- **Requirement:** lane brief, "`V001_identity.sql` ONLY (members/identity/sessions/consent)".
- **Reason:** every domain command needs the transactional outbox, inbox receipts and idempotency records in the same database before any V002+ migration runs. V002–V009 are reserved for other lanes, and the brief allows the foundation only V001.
- **Replacement:** V001 has two clearly separated sections: identity (Members, MemberSettings, MemberIdentities, Sessions, ConsentGrants) and platform (OutboxEvents, InboxReceipts, IdempotencyRecords, AuditEntries).
- **Impact:** none on product; other lanes can rely on these tables from V002 onward.
- **Evidence:** `tests/foundation/test_migrations.py`, `tests/foundation/test_outbox_emulator.py`.
- **Approval:** parent/integrator confirmation only.

## D-002 Cross-lane edits needed to deliver W00/W02 exit evidence

- **Requirement:** "never edit another lane's owned files". The brief lists `brandme-gateway/src/routes/v1/{index,me}.ts`, `middleware/`, `types/` as owned, but not `src/index.ts`, `src/config/index.ts`, `package.json` or a vitest config.
- **Reason:** mounting `/api/v1`, removing the shared-secret JWT requirement, making NATS optional, moving the gateway to port 3001 and adding dependencies all require these files.
- **Replacement (minimal edits):** `brandme-gateway/src/index.ts` (createApp + mount + optional NATS + mode guard), `src/config/index.ts` (BRANDME_MODE, OIDC, port 3001, no secret defaults), `package.json` (jose, @google-cloud/spanner, ajv, contracts, supertest), `vitest.config.ts` (test env). Also `brandme_core/spanner/pool.py`: an additive `database` property, without which 49 call sites fail (baseline F8).
- **Impact:** legacy `/scan` keeps its URL and `req.user` contract, now backed by real principals.
- **Approval:** parent review at merge.

## D-003 Generated JSON and evidence files force-added past `.gitignore`

- **Requirement:** commit generated contracts and evidence.
- **Reason:** root `.gitignore` ignores `*.json` (to stop GCP key files) and `build/` (which matches `docs/build/`). Both are outside this lane's ownership.
- **Replacement:** `git add -f` for `packages/contracts/generated/*.json`, `packages/contracts/src/foundation-schemas.json` and `docs/build/**`. **Proposed .gitignore change for the parent:** add `!docs/build/` and `!packages/**/*.json`. A fresh-clone `pnpm check` caught the missing `foundation-schemas.json`, which the ignore rule had hidden.
- **Impact:** without the negations, a lane that regenerates these files must remember `-f`. CI drift check catches a stale file.

## D-004 Design-system primitives not delivered by this lane

- **Requirement:** ch.06 W01 lists accessible primitives (Button … EvidenceLabel), the app shell, a component gallery and self-hosted fonts.
- **Reason:** the lane brief scopes `packages/design-system` to "tokens generated from `contracts/design-tokens.json`". The primitives need React 19 and the upgraded frontend toolchain, which the frontend lane owns.
- **Replacement:** tokens (CSS custom properties with dark, reduced-motion and data-attribute overrides; TS constants), a WCAG contrast utility, and contrast tests for 18 text pairings (all AA).
- **Impact:** W01 exit evidence for shell/viewports/keyboard is **not** produced here; it stays open for the consumer-ui lane.

## D-005 Browser OIDC code flow not implemented; dev identity simulation for local modes

- **Requirement:** ch.03 §1.9 Google Identity Platform OIDC with email link/social providers.
- **Reason:** no tenant or credentials exist (ch.06 §6 gate "Identity").
- **Replacement:** JWKS-verified bearer tokens (issuer, audience, asymmetric algorithms) map `(iss, sub)` to members. Server-side cookie sessions with CSRF are in place. A labelled dev identity provider (`POST /api/v1/session/dev`) works only in demo/development, returns 404 in sandbox/production, and is refused by the boot guard.
- **Impact:** real sign-up/sign-in needs the tenant plus the code-flow callback (adapter seam: `IDENTITY_PROVIDER=oidc`).
- **Approval:** owner action: provision the OIDC tenant/redirect domains.

## D-006 Round 4 (Q8): minimal edits to two lane-owned tests

- **Requirement:** "lane modules are imported, not edited" (oneshot plan 03, exclusive file ownership).
- **Reason:** two lane tests asserted the behaviour Q8 removes, that the foundation worker leaves a lane's contracts unclaimed until the lane's own process imports them. `tests/test_persona_lane_events.py` asserted the lane types stay `pending` after the foundation worker runs, then ran the lane's private `persona/outbox_worker.py`. `tests/test_commerce_events_catalog.py` asserted the worker refuses commerce types before the commerce import. Both turn red once the foundation worker loads every catalog. The alternative was quarantining them, which would hide a working test.
- **Replacement:** only those assertion blocks changed. The persona test now publishes through `python -m brandme_core.events.worker --once` and keeps every other assertion; the commerce test asserts the default allowlist already accepts commerce types and keeps its import-weight test byte for byte. No lane domain module was edited. `brandme_core/domains/persona/outbox_worker.py` is now unused; deleting it is the consumer-domains lane's step.
- **Approval:** owning lanes at review.

## D-007 Round 4 (Q9): the table owner redacts undelivered payloads, not the privacy lane

- **Requirement:** founder Q19: foundation purges delivered rows after 7 days and the privacy lane (midnight-rights) redacts a deleted subject's undelivered `member_private` payloads.
- **Reason:** the privacy orchestrator never knows table names (`brandme_core/domains/privacy/deletion.py:6-10`). Every table owner registers a handler, so redacting `OutboxEvents` inside privacy code would break that contract.
- **Replacement:** foundation registers `PlatformPrivacyHandler` (`brandme_core/events/erasure.py`) for `OutboxEvents` and `IdempotencyRecords`. It uses the orchestrator's existing non-transactional hook (`transactional = False` plus `delete_outside_txn`, `privacy.py:296-299`, `:444-455`). The joint proof runs the privacy lane's `request_deletion`/`run_deletion` with that handler (`tests/foundation/test_deletion_leaves_no_member_rows.py`).
- **Open for midnight-rights:** (a) acknowledge the split; (b) confirm `transactional`/`delete_outside_txn` as a stable extension of the published Protocol; (c) receipts drop `purge_derived` detail, so the broker-retention disclosure appears only in the category text.
- **Approval:** founder or privacy lane.

## D-008 Round 4: dependency fixes outside the foundation's listed files

- **Requirement:** foundation owns `scripts/python/requirements.in` and the lock. `brandme_core/requirements.txt` is the shared library's file. `brandme-core/`, `brandme-cube/` and `brandme-agents/agentic/requirements.txt` have no owning lane.
- **Reason:** the baselined CRITICALs could only be fixed there. anyio needs fastapi 0.134.0 and pydantic 2.7.4 in `brandme_core/requirements.txt`, because the lock includes that file with `-r`. The unused python-jose and sentence-transformers pins live in the legacy files.
- **Replacement:** fastapi 0.134.0 / pydantic 2.7.4 (full `tests/` suite unchanged, contracts no drift). Removal of python-jose ×2 and sentence-transformers (no imports), plus the agents smoke import list. The pinned-emulator fetchers (one was added by consumer-domains) share a retrying `_fetch.py`.
- **Approval:** parent review at merge.
