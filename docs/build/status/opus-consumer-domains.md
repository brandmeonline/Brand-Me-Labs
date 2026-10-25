# Lane brief: opus-consumer-domains

**Bench:** Opus 5.5 (Claude Code) · **Branch:** `bench/opus-consumer-domains-20261005`
**Base:** `docs/brandme-full-experience-2026-10-05` · **Spec:** `docs/design/brandme/` + `contracts/`
**Work packages:** W03-backend (first 90 seconds + Looking Glass), W04-backend (wardrobe/outfits), W05-backend (social/loyalty), W08-server (try-on jobs/consent/deletion)
**Position in merge order:** After `opus-foundation` merges. Independent of the other Opus lanes (disjoint files).

## What you are building
The consumer domain backends — the hardest reasoning in the build: persona precedence/suppression, the deterministic recommender, the idempotent reward ledger, server-timed five-minute decisions, wardrobe/outfit domain logic, and try-on server jobs. Read chapters 01, 03, 06 and the root `CLAUDE.md` first.

## You own exclusively (no other lane may touch these)
- `brandme_core/domains/{persona,wardrobe,social,rewards,media}/` — full domain logic
- `brandme-data/spanner/migrations/` — `V002_persona.sql`, `V003_wardrobe.sql`, `V004_social.sql`, `V005_rewards.sql` ONLY
- `brandme-gateway/src/routes/v1/{persona,wardrobe,outfits,social,decisions,rewards,media,tryon}.ts` — ship as unmounted router files; Lane 1 / parent mounts them at integration. Never touch `index.ts`, `middleware/`, or `types/`.
- `tests/test_{persona,wardrobe,social,rewards,media}*.py`, `tests/fixtures/{persona,wardrobe,social,rewards}/`
- `brandme-console/app/(ops)/{moderation,rewards-disputes}/**` — Lane 5 builds the console shell; you own these subtrees. If the shell imposes a layout contract, it will be published in `docs/build/status/astra-consumer-ui.md` — check it before building pages.

## Read-only for you
`packages/contracts` (generated clients), `packages/design-system`, `brandme_core/events/*`, gateway `middleware/` + `types/`, `docs/build/compatibility-lock.md` (submit your dependency pins via this status file instead of editing it).

## Forbidden
`packages/*` (any edits), `docs/design/brandme/**`, `contracts/**`, any `brandme-frontend/` files, other lanes' domains/routes/migrations.

## Exit evidence (from ch.06 §2, W03–W05, W08-server)
- Persona: 12 axes with declared/inferred/effective separation, locks, suppression, snapshots, reset; declared locked preference wins over inference; two devices editing one persona version → one accepted revision, other sees mergeable conflict; deleting evidence changes recommendations and prevents immediate reuse
- Deterministic recommender works with NO AI key; recommendations carry explanations reflecting actual scoring
- Reward ledger: 10 concurrent duplicate reward events → exactly one ledger cause and correct balance; two redemptions racing the same points → no negative balance; reversals, caps, idempotency keys all tested
- Decisions: server-computed `closes_at`; responses accepted only when server transaction time is strictly before deadline; one response per respondent/decision; zero-reply and expired states handled
- Wardrobe: product vs wardrobe entry vs attested instance separated; duplicate resolution; placement quaternions finite/normalized, positions asset-bounded
- Try-on server: consent/job/deletion interfaces; unsaved media expiry demonstrable (AR/camera UI is Lane 6 — you own the server side only)
- Migration V002→V005 run from empty; transaction retry does not duplicate outbox events

## Status protocol
Record status ONLY in this file. Propose deviations here (parent/Lane 1 compiles into `docs/build/deviations.md`). Publish your dependency pins here.

## Cross-lane contracts you must honor
- W10 deletion: expose a `deletion.py`/`privacy.py` registration in each domain package for Lane 4's export/deletion job framework (Lane 4 publishes the interface; you implement it).
- `brandme-cube/` belongs to Lane 4 — consume passport reads via its versioned, policy-filtered read API only.

## Global rules (all lanes)
Never edit another lane's owned files. Never edit `docs/design/brandme/**` or `contracts/**`. Fixtures stay in per-lane `tests/fixtures/<domain>/`. No `latest` tags — pin everything. Demo adapters carry visible simulation labels.

---

# Lane status log (maintained by the lane; newest stage last)

## Environment observed at start (2026-10-05)
- Branch worked: `claude/opus-consumer-domains-1csp2g` (session-designated push branch), created from `bench/opus-consumer-domains-20261005` @ `5d919ab`.
- **Foundation lane had not landed anything but its brief** (`bench/opus-foundation-20261005` @ `e4f1342`): no `packages/*`, no `brandme_core/domains/{__init__,base,events}.py`, no reservation READMEs, no `brandme_core/events/`, no migration runner/ledger/V001, no `routes/v1/index.ts`. This lane therefore builds against chapter-03 contracts directly and records every interim shim below so integration can replace them.
- Test runtime: Python 3.11.15; `google-cloud-spanner==3.71.0`, `pytest==9.1.1`, `pytest-asyncio==1.4.0`, `jsonschema==4.26.0`, `fastapi==0.142.2` (installed in the session; pins proposed below). Spanner emulator `gcr.io/cloud-spanner-emulator/emulator:1.5.28` run via Docker (`--network host`, ports 9010/9020).

## Interim shims (replace at integration — do not treat as final architecture)
> **Superseded by Stage 2 (2026-10-23):** the kernel now wraps the foundation framework, and the interim DDL fixture is deleted. See the Stage 2 table for what remains.
| Shim | Why | Replace with |
|---|---|---|
| `brandme_core/domains/persona/kernel.py` (Principal, Clock, problem errors, outbox writer, idempotency helper, `run_txn`/`run_read`) | foundation `base.py`/`events.py`/`brandme_core/events/` absent | thin re-export of foundation framework |
| `tests/fixtures/persona/interim_foundation.sql` (`OutboxEvents`, `InboxReceipts`, `IdempotencyRecords`) | V001/event tables absent | foundation V001 / events migration |
| `tests/test_persona_harness.py` (fresh emulator DB per session: interim DDL + V002..V005) | migration runner absent | foundation runner + ledger |
| `brandme_core/domains` has **no** `__init__.py` from this lane (PEP 420 namespace) | foundation owns that file | foundation's `__init__.py` |

## Proposed deviations (for parent / Lane 1 to compile into docs/build/deviations.md)
- **PD-01 PersonaPatch extension.** `contracts/domain.schema.json#PersonaPatch` is `additionalProperties:false` with only `changes/learning_enabled/client_revision`, but ch.03 says PATCH also carries locks, goals and exclusions, and ch.01 §4.1/§4.5 require hide / "Do not infer this" / let-adapt / budget / exclusions controls. Implemented two optional extension objects on the same PATCH: `axis_settings{axis:{hidden,inference_allowed,adapt_enabled}}` and `constraints{budget_ceiling_minor (decimal string), budget_currency, excluded_brands, excluded_materials, excluded_categories, prefer_owned, social_signals_enabled, goals}`. Every other key is still rejected (BM-PER-011). The `profile` sub-object of the response validates exactly against `#PersonaProfile`; extra detail lives beside it (`axes`, `constraints`, `context_overrides`, `adaptation_proposals`). Needs schema extension in `packages/contracts`.
- **PD-02 No FK/interleave to Members.** V002 tables are keyed by `member_id` without a foreign key because V001 did not exist. Add `FOREIGN KEY`/interleave once V001's table name is fixed.
- **PD-03 Axis values strictly integer.** Schema allows `number`; ch.01 §4.1 says integers 0–100. Server rejects non-integers (72.5, `true`, NaN) with 422. Stricter, not weaker.
- **PD-04 Retry of discarded transactions.** `run_txn`/`run_read` re-run a transaction reported as discarded-before-commit (NOT_FOUND "Transaction not found"; on the emulator also FAILED_PRECONDITION rollback messages, gated on `SPANNER_EMULATOR_HOST`). Safe because callbacks perform no external I/O.
- **PD-05 Learning default on.** New profiles start `learning_enabled=true` for in-app personalization evidence only (purpose `personalization`); evidence of any other purpose is refused. Founder/privacy review may prefer default-off.

## Dependency pins proposed for compatibility-lock.md
`google-cloud-spanner==3.71.0`, `jsonschema==4.26.0`, `fastapi==0.142.2` (pydantic 2.13.4, starlette 1.3.1), `pytest==9.1.1`, Spanner emulator image `gcr.io/cloud-spanner-emulator/emulator:1.5.28`. Note existing `brandme_core/requirements.txt` pins `google-cloud-spanner==3.40.1`/`fastapi==0.104.1`; this lane's code was only executed with the versions above.

## Stage 1 — Persona domain (W03 backend) — 2026-10-05
Files: `brandme_core/domains/persona/{kernel,model,recommender,service,deletion}.py`, `brandme-data/spanner/migrations/V002_persona.sql`, `tests/test_persona_{model,recommender,service,harness}.py`, `tests/fixtures/persona/*`.

Command: `python3 -m pytest tests/test_persona_model.py tests/test_persona_recommender.py tests/test_persona_service.py -q -W error::pytest.PytestUnhandledThreadExceptionWarning` with emulator up → **50 passed** (run 3× consecutively, all green; concurrency subset run 8× green).

| Acceptance / exit evidence | Result | Test |
|---|---|---|
| 12 axes, declared/inferred/effective separate, unknown is `null` not 50 | passed (domain+integration) | `test_unknown_is_none_not_neutral`, `test_get_before_any_save_is_unknown_and_writes_nothing` |
| BM-PER-002 change+lock persist with new version | passed (integration) | `test_change_lock_persist_reload` |
| BM-PER-003 lock races inference → lock wins, inference inspectable | passed (integration, threads) | `test_lock_races_inference_and_lock_wins` |
| BM-PER-005 two devices one version → one accepted, other mergeable conflict | passed (integration) | `test_two_devices_same_version_one_wins_with_merge_guidance`, `test_concurrent_same_version_patches_exactly_one_commits` (5 threads) |
| BM-PER-006 suppress evidence → recommendations change; same observation cannot be reused | passed (integration) | `test_suppression_changes_recommendations_and_blocks_reuse` |
| BM-PER-007 learning disabled → no new inference | passed (integration) | `test_learning_disabled_blocks_new_inference` |
| BM-PER-008 reset inference only keeps declarations | passed (integration) | `test_reset_inference_only_keeps_declarations` |
| BM-PER-009 snapshot inspect + restore as explicit new version | passed (integration) | `test_snapshot_inspect_and_restore_as_new_version` |
| BM-PER-010 budget/exclusions honoured; reasons reference actual score evidence | passed (domain+integration) | `test_hard_budget_and_exclusions_are_never_violated`, `test_reasons_reference_actual_scoring_evidence`, `test_budget_and_exclusions_flow_through_to_recommendations` |
| BM-PER-011 persona patch cannot touch rewards/ownership fields | passed (domain) | `test_patch_allowlist_rejects_factual_or_invalid_fields` |
| BM-ONB-007 deterministic recommender with no AI key | passed (subprocess with all *_API_KEY/ANTHROPIC/OPENAI vars removed) | `test_runs_with_no_ai_key_in_a_clean_process` |
| BM-ONB-003 neutral start has no false confidence | passed (domain) | `test_neutral_start_is_honest` |
| Transaction retry does not duplicate outbox events | passed (integration; injected ABORTED after mutations buffered) | `test_transaction_retry_does_not_duplicate_outbox` |
| Deletion races inference → cannot recreate | passed (integration; tombstone) | `test_deletion_tombstone_blocks_racing_inference` |
| BM-PER-001/004 (browser inspector, stale preview ordering in UI) | not_run — UI lanes; server returns `client_revision` echo on preview for the client to drop stale responses | — |

Next: persona FastAPI router + gateway `persona.ts` (unmounted), guest migration (BM-ONB-004), then wardrobe (W04).

## Foundation merge notice — 2026-10-05 19:53 UTC
PR #33 (opus-foundation W00–W02) is merged into **`bench/opus-foundation-20261005` @ `25dff5c`**. This lane's base, `bench/opus-consumer-domains-20261005`, is still at `5d919ab` and does not contain it. Reconciliation therefore happens when the parent moves this lane's base onto the foundation tip, or merges the foundation tip into it. This lane does not copy foundation-owned files into its branch.

Reconciliation checklist, from reading `25dff5c`:
| Interim piece here | Foundation equivalent | Compatibility |
|---|---|---|
| `kernel.write_outbox` (18 columns) | `brandme_core.events.write_events` + `EventEnvelope` + `domains.events.register` (closed JSON-schema payloads) | Insert columns match V001 `OutboxEvents`. **Shard key differs**: here `aggregate_id`, foundation `event_id`; switch to foundation. Re-register the 4 persona event types as closed schemas. The foundation `FORBIDDEN_PAYLOAD_KEYS` list includes `declared_axes`/`persona`; persona payloads already carry only refs, version and axis *names*. |
| `kernel.idempotency_lookup/store` (`response` column) | `run_idempotent_command` against V001 `IdempotencyRecords(state, response_status, response_body, resource_ref)` | **Incompatible columns.** Must switch to `run_idempotent_command` before running on V001. |
| `kernel.Principal(member_id, scopes, environment, ...)` | `base.Principal(member_id, subject, session_id, client_id, scopes, assurance_level, environment, delegation_id)` | Field superset; adapt constructor. `actor_ref` is the same format. |
| `kernel.VersionConflict` code `version_conflict` | `base.VersionConflict` code `revision_conflict` (+ `PreconditionRequired` 428 for a missing If-Match) | Adopt the foundation codes. Keep the mergeable-conflict extras (`mergeable`, `conflicting_axes`) as problem extension members. |
| `kernel.run_txn` emulator rollback retry (PD-04) | `base.run_command` | Check whether `run_command` covers the emulator's discarded-transaction errors. If not, propose PD-04 to foundation rather than wrapping it. |
| `deletion.py` (`DATA_CATEGORIES`, `export_member`, `delete_member`) | `base.register_data_category(DataCategory)` | Wrap the existing export/delete functions in a `DataCategory` registration. |
| Missing FK to Members (PD-02) | V001 `Members(member_id)` exists | Add interleave/FK to `Members` in V002 before V002 is applied anywhere (it is unapplied, so editing it is still allowed). |
| `tests/fixtures/persona/interim_foundation.sql` + harness | `brandme-data/spanner/migrations/runner.py` + V001 | Delete the interim DDL. The harness should run V001→V005 via the runner. |

Development continues on the interim shims until the base moves. The next stages write new code behind thin seams (Principal, outbox, idempotency) so the switch-over touches only `kernel.py`.

## Stage 2 — Persona reconciled with the foundation framework + W10 privacy registration — 2026-10-23
Branch `claude/opus-consumer-domains-1csp2g`, restarted from the merged lane base `d839267` (PR #32 merged 2026-10-07). It now merges **`bench/opus-foundation-20261005` @ `67327e4`**, as the commerce-agents lane did in `1020981`. No foundation-owned file was edited.

**What changed**
- `persona/kernel.py` is now a thin adapter over the foundation framework. It uses the foundation's `Principal`, errors, `authorize`/`Grant`, `parse_if_match` (428 when missing) and `canonical_digest`. All writes go through `run_command`/`run_idempotent_command`, which commit rows and V001 `OutboxEvents` together. Idempotency now runs on the V001 `IdempotencyRecords(state, response_status, response_body)` with 16–128-character keys. The lane-specific pieces it adds are:
  - `ValidationFailed` (422) and `RateLimited` (429)
  - problem extension members (`DetailedVersionConflict` keeps the `mergeable`/`conflicting_axes` guidance under the foundation code `revision_conflict`)
  - `Clock`
  - `ServicePrincipal` (`actor_ref` `service:<name>`) for workers
  - the PD-04 discarded-transaction retry, done by wrapping the database passed to `run_command`
- `persona/events.py` registers the 4 event types as closed JSON schemas (`persona.updated` carries a `change_kind` enum and axis names; no values). The foundation `EventEnvelope.validate` passes on every outbox row (`test_outbox_rows_are_valid_foundation_envelopes`).
- **V002** now interleaves `PersonaProfiles` in V001 `Members ON DELETE CASCADE` and adds CHECKs on version and budget. Tombstones and guest-migration rows stay non-interleaved so they outlive the member row. Every write requires an `active` member, otherwise 404. This closes PD-02.
- **W10 registration (`persona/deletion.py`).** Five categories: `persona.declared`, `persona.inferred`, `persona.evidence`, `persona.snapshots`, `persona.feedback`. They are registered two ways:
  - with the foundation `register_data_category` (export and delete callables);
  - with the privacy lane's published `DomainPrivacyHandler`, when `brandme_core.domains.privacy` is importable.

  Deleting evidence keeps the one-way fingerprints as suppression rules, so a queued job cannot re-ingest the same observations.
- **Privacy guard (`persona/privacy_guard.py`).** Every inference, adaptation or provisioning write calls the privacy lane's `assert_processing_allowed(txn, member_id, category, basis_time)` inside its own transaction. If that module is absent (this branch), it falls back to `PersonaTombstones`. `guard_enforced()` reports which guard ran. `ingest_evidence` takes a `basis_time`.
- **Legacy backfill (`persona/backfill.py`).** `Users.persona_warm_cold` and `Users.persona_sport_couture` are 0–1 floats where 0 = warm/sport. They become 0–100 `legacy_profile` **evidence**, in checkpointed and idempotent batches. Invalid, null and non-member rows are counted and skipped. Nothing is declared or locked (PD-06).
- **Test harness:** the interim DDL fixture is deleted. Each session applies **every** migration from an empty database through the foundation `runner.py` and its checksum ledger, and asserts that V001 is first.

**Evidence (pinned stack from `scripts/python/requirements.lock`: Python 3.11.15, google-cloud-spanner 3.40.1, pytest 7.4.3; emulator 1.5.28 per compatibility-lock)**
| Run | Result |
|---|---|
| This branch: `pytest tests/test_persona_*.py tests/foundation -W error::pytest.PytestUnhandledThreadExceptionWarning` | **148 passed, 3 skipped**. The 3 skips are the privacy-lane integration tests (module absent here, so NOT RUN). Persona and foundation together passed 3 runs in a row; the concurrency subset passed 5 runs in a row. |
| W11 integration `bec80b1` with this stage's files overlaid (scratch worktree, W11's own lock + commerce requirements): `pytest tests/test_persona_*.py tests/test_privacy.py tests/test_rights.py` | **80 passed, 0 skipped**. This includes `test_processing_freeze_blocks_inference_write`, `test_tombstone_newer_than_job_basis_blocks_write` and the privacy-registry test, all running for real. |
| Whole W11 Python suite, overlay vs untouched baseline | Baseline **16 failed / 242 passed**; overlay **15 failed / 253 passed**. The overlay adds no new failure and fixes one: W11's copy of `test_transaction_retry_does_not_duplicate_outbox` fails on google-cloud-spanner 3.40.1 because the injected Aborted needs a `trailing_metadata` cause. The remaining 15 failures and 3 collection errors are all `test_commerce_ap2.py`/`test_providers.py`/`test_mcp.py`/`test_commerce_protocols.py`/`test_commerce_assistant.py` (missing vendored AP2 files / external prerequisites), identical before and after. |

New tests: `test_persona_privacy.py` (registry, category export/delete, idempotent account delete, plus 3 privacy-lane integration tests), `test_persona_backfill.py` (scaling, no-legacy-table no-op, checkpoint/idempotency/honesty), and in `test_persona_service.py`: 428 on a missing If-Match, active-member requirement, envelope validation, service attribution of worker events.

**Remaining interim pieces**
| Piece | Status |
|---|---|
| `kernel._RetryingDatabase` (PD-04) | Kept. Foundation `run_command` does not retry transactions discarded before commit; foundation should adopt this or reject it. |
| `privacy_guard` fallback to lane tombstones | Kept until the privacy lane's module and V009 reach this lane's base; then the fallback can go. |
| Gateway→Python principal transport | **Not defined by foundation.** Commerce uses a gateway-signed executor assertion; privacy uses an `x-subject-ref` relay. This lane's routers take the transport by injection (proposal **PD-07**: foundation picks one; this lane recommends the commerce executor assertion, which is asymmetric and audience-bound). |

**Integration risks for the parent / W11 (please read)**
- **Migration order.** W11 already contains V006–V009 but not V003–V005. The runner refuses out-of-order versions unless run with `--allow-out-of-order` (refused in sandbox/production). Any *persistent* database built from W11 before V003–V005 merge would be stuck. Keep W11 databases ephemeral until this lane's V003–V005 land, or the integrator should decide the order explicitly.
- W11 carries the stage-1 `test_persona_service.py`, which fails on the pinned spanner 3.40.1. Stage 2 fixes it.

**Proposed deviations added**
- **PD-06** Legacy persona values become suppressible `legacy_profile` evidence, not declared or locked values, because their provenance is unknown.
- **PD-07** A single gateway→domain principal transport needs to be chosen by foundation (see above).
- **PD-08** `brandme_core/domains/media` has no reserved migration number (foundation README: "propose at integration"). This lane's brief allows only V002–V005, so try-on/media tables will be placed in **V003_wardrobe** unless foundation reserves a number first.
- PD-02 is **closed** (interleaved in Members).

## Stage 3 — Persona HTTP surface (internal router + unmounted gateway router) and guest migration — 2026-10-23
**Python (internal, UNMOUNTED): `brandme_core/domains/persona/api.py` → `create_persona_router(persona, guest, resolve_principal)`**
- Paths mirror the foundation-generated OpenAPI `persona` tag:
  - `GET`/`PATCH /me/persona` (ETag; If-Match → 428/409)
  - `POST /me/persona/preview`
  - `GET /me/persona/evidence?cursor&limit` (opaque cursor, default 24, max 100)
  - `POST /me/persona/evidence/{id}/suppress` (Idempotency-Key)
  - `POST /me/persona/reset` (If-Match + Idempotency-Key)
  - `POST /me/persona/snapshots` (Idempotency-Key, 201)
  - `GET /recommendations` (`next_cursor: null`, a single ranked page)
  - `POST /recommendations/{id}/feedback` (Idempotency-Key; `{id}` = catalog product id, since recommendations are computed per request)
- Lane additions, **proposed for `packages/contracts` (PD-09)**:
  - `GET /me/persona/snapshots/{id}/diff` and `POST /me/persona/snapshots/{id}/restore`: BM-PER-009, inspect then apply as a new version
  - `POST /me/persona/contexts` and `PATCH /me/persona/contexts/{id}`: ch.01 §4.2 context overrides
  - `POST /me/persona/adaptations/{axis}/accept`: ch.01 §4.2, first bounded adaptation needs confirmation
  - `POST /me/guest-migration`: ch.01 §3.1, BM-ONB-004
- Response shapes: the generated OpenAPI leaves them to the owning lane. Paginated lists are `{items, next_cursor}`. The profile DTO is `{profile (exact #PersonaProfile), axes[], constraints, context_overrides[], adaptation_proposals[], exists}`.
- `persona/http.py` is the lane-shared plumbing:
  - problem+json for every domain error (including `extra` members)
  - `X-Request-Id`, `X-Brandme-Environment`, `Cache-Control: private, no-store`
  - JSON parse errors return 422
  - blocking Spanner calls run off the event loop
  - the principal is injected (PD-07)

**Guest migration (`persona/onboarding.py`, BM-ONB-004)**
- Idempotent at the domain level, not only per key: `GuestMigrations` (member, namespace), plus a unique index so a namespace can be claimed by only one account.
- A second sign-in with a *new* Idempotency-Key returns `already_migrated` and writes nothing.
- Account choices always win; guest values fill only unanswered axes.
- Other domains plug in as sections that apply in the same transaction (wardrobe will register saved products, outfits and closet theme). Unknown sections are rejected.

**Gateway (UNMOUNTED): `brandme-gateway/src/routes/v1/persona.ts` → `personaRouter(client: DomainClient)`**
- Uses foundation `requirePrincipal`, `problems` and `handle` read-only; `index.ts` is not touched.
- Checks scopes `profile:read`/`profile:write`, If-Match (428), Idempotency-Key (16–128, otherwise 400 `idempotency_key_invalid`) and UUID path params (otherwise 404, never forwarded).
- Rejects identity fields in the body, allowlists query parameters, and relays domain status, ETag and problem bodies unchanged.
- Exports `DomainClient`/`forwardTo`/`relay`/`requireScope`/`ifMatch`/`idempotencyKey`/`uuidParam`/`objectBody` for this lane's other routers.
- Mount at integration with `router.use(personaRouter(domainClient))` after `principalMiddleware`.

**Evidence**
| Check | Result |
|---|---|
| `pytest tests/test_persona_*.py tests/foundation -W error::…UnhandledThreadException` (pinned venv, emulator 1.5.28) | **158 passed, 3 skipped** (privacy-lane tests not run on this branch) |
| `tests/test_persona_api.py` | **10 passed**. 401; ETag and private headers; 428/409 with mergeable fields; 422 for allowlist and invalid JSON; Idempotency-Key required, short key 400, replay identical; cursor pagination over 5 items and bad cursor/limit 422; recommendations + `not_me` feedback; guest migration twice → 1 row and 1 event; account wins; **5 concurrent migrations → exactly one `migrated`**; another member → 422 `guest_namespace_claimed` |
| Gateway, Node 24.21.0 / pnpm 10.34.6 (`pnpm install --frozen-lockfile --filter @brandme/gateway...`): `tsc --noEmit` | exit 0 |
| `eslint src/routes/v1/persona*.ts` | exit 0 |
| `vitest run` (whole gateway) | **25 passed** (18 foundation + 7 `persona.test.ts`) |

Acceptance: **BM-ONB-004 passed (integration)**. BM-ONB-007 stays passed: `/recommendations` needs no model key.

## Stage 4 — Wardrobe, closet placement, outfits, packing (W04 backend) — 2026-10-23
**Migration `V003_wardrobe.sql`** (applies after V001/V002 from empty through the runner). Member aggregates are interleaved in `Members`:
- `WardrobeItems`, with indexes by collection, variant and receipt line, plus a **unique NULL_FILTERED tag-serial index**
- `WardrobeOrderLinks`, `ClosetLayouts`, `ClosetPlacements` (**unique NULL_FILTERED (room, group, slot)**; NULL group means the Unplaced tray)
- `Outfits` with a global `OutfitsByOutfitId` index; immutable `OutfitVersions`; `OutfitProposals` (unique per proposer+content)
- `PackingLists`/`PackingEntries`
- try-on/media tables `TryOnConsents`, `TryOnJobs`, `MediaObjects` for stage W08 (PD-08)

The emulator caught two DDL bugs during this stage, both fixed: `decided_at` was missing `allow_commit_timestamp`, and the emulator rejects `FORCE_INDEX` on NULL_FILTERED indexes, so those member-scoped lookups now use the base table.

**Domain (`brandme_core/domains/wardrobe/`)**
- `model.py` — intake rules and duplicate logic:
  - A catalog save defaults to **want** and never implies ownership; manual and photo entries are owned and self-reported.
  - A receipt line with *n* units becomes *n* items. They stay self-reported with `receipt_pending_review` until a reviewer path (`accept_receipt_evidence`; members cannot call it) makes them `receipt_backed`.
  - Factual fields are refused at intake and in PATCH.
  - No invented size or category.
  - Duplicates are *suggestions*; distinct tag serials or receipt units can never merge. Tag serials are stored as a one-way normalized hash.
- `placement.py` + `rooms.py` — placement validation:
  - finite numbers only (NaN/±Inf rejected; the HTTP layer also refuses JSON `NaN`/`Infinity` literals)
  - quaternion |‖q‖−1| ≤ 1e-3, then canonicalized (exact unit length, w ≥ 0)
  - position inside the room's collision bounds **and** the selected group's volume
  - slot index within capacity, category-eligible group, room asset revision must match, scale within the garment's `displayScaleBounds`
  - slot uniqueness enforced in the domain and by the unique index
  - deterministic theme remap (keep group+slot or go to Unplaced)

  Room geometry mirrors the spatial lane's manifests at `original-v1` and is **checked against them** (`test_server_room_templates_match_spatial_manifests`, run with the manifests from `bench/astra-spatial-ar-20261005@7ccc0b4`).
- `service.py` — intake, closet and orders:
  - idempotent intake with optional placement in the same transaction
  - get/list with filter, search and cursor
  - patch (owned↔want only; order/receipt items can't become want), archive/unarchive, duplicate resolve, worn log, cost per wear (estimates labelled)
  - closet layout, `PUT` placement (If-Match on the placement version; 409 returns the current placement), batch ≤ 50 with swaps
  - theme change with preview
  - **`commerce.order.observed` reducer**:
    - exactly once via the foundation inbox
    - monotonic by order version
    - deterministic per-unit item ids
    - on-the-way → owned → returned per unit
    - returned units leave the room
    - unknown category stays NULL with an honest placeholder title
  - `wardrobe_refs` feeds the persona recommender
- `outfits.py` — outfits, proposals and packing:
  - immutable versions
  - friend proposals addressed by outfit id; the owner is resolved server-side and the policy is injected (social supplies it next; default deny); same 404 for missing and not-allowed
  - accept creates a **new version authored by the friend**; the original is preserved
  - duplicate and self proposals refused
  - packing lists with entry states; trip dates appear in no event
- `guest_sections.py` — `saved_products` (want items) and `closet_theme` migrate in the **same transaction** as the persona guest migration; a failing section rolls everything back.
- `deletion.py` — 5 categories (foundation registry + privacy handler). A proposer's deletion **anonymizes** their attribution in a friend's outfit history instead of erasing the friend's record.
- Writers call the privacy guard (`wardrobe.items`).
- `api.py` (FastAPI, unmounted) mirrors the ch.03 paths. Lane additions go to PD-09: unarchive, duplicate resolve, worn, proposal accept/decline, packing lists.

**Gateway (UNMOUNTED):** `routes/v1/wardrobe.ts` → `wardrobeRouter(client)`, `routes/v1/outfits.ts` → `outfitsRouter(client)`. They reuse the `persona.ts` helpers and add a cheap placement-shape check (finite vectors, scale > 0, field allowlist), batch ≤ 50, theme preview without If-Match, and accept/decline-only decisions.

**Evidence**
| Check | Result |
|---|---|
| This branch: `pytest tests/test_persona_*.py tests/test_wardrobe_*.py tests/foundation -W error::…UnhandledThreadException` | **211 passed, 5 skipped** (4 privacy-lane, 1 spatial-manifest check, all NOT RUN here); wardrobe suites 3 runs in a row green |
| W11 `bec80b1` overlay with spatial manifests: `pytest tests/test_persona_*.py tests/test_wardrobe_*.py tests/test_privacy.py tests/test_rights.py` | **145 passed, 0 skipped** |
| Gateway: `tsc --noEmit` 0; `eslint` 0; `vitest run` | **31 passed** (+6 `wardrobe.test.ts`) |
| 500-item closet, full cursor pagination (5×100) on emulator | 204 ms; complete, no duplicates; collection/category/search filters exact. Emulator timing is not a production benchmark. |

| Acceptance | Result | Test |
|---|---|---|
| BM-WARD-001 manual/catalog/receipt keep source, collection, claim | passed (integration) | `test_intake_paths_keep_source_collection_and_claim` |
| BM-WARD-002 discovery save → Want, no ownership | passed (integration) | same + `test_catalog_save_defaults_to_want_and_never_ownership` |
| BM-WARD-003 retry after lost response → exactly one item + placement | passed (integration; same key replay + injected ABORTED) | `test_lost_response_retry_creates_exactly_one_item_and_placement` |
| BM-WARD-004 member-controlled duplicates; distinct units never lost | passed (integration) | `test_duplicates_are_member_controlled` |
| BM-WARD-005 500-item organization | **functional half passed** (pagination, filters, search). The performance/scene-virtualization half belongs to the UI/spatial lanes: not_run here | `test_500_item_closet_stays_organizable` |
| BM-WARD-006 outfit + accepted friend proposal → immutable versions, attribution | passed (integration) | `test_versions_are_immutable_and_proposals_keep_attribution` |
| BM-WARD-007 care/packing persist, provenance unchanged, trip details private | passed (integration; checks outbox payloads) | `test_care_and_packing_persist_privately` |
| BM-WARD-008 partial order then return → only those units change | passed (integration) | `test_partial_order_then_return_changes_only_those_units` |
| Exit: placement quaternions finite/normalized, positions asset-bounded | passed (domain + integration + HTTP NaN/Infinity literals) | `test_wardrobe_placement.py`, `test_placement_versioning_slot_uniqueness_and_validation`, `test_create_place_and_reject_non_finite_json` |
| Exit: concurrent moves into one slot | passed (4 threads → 1 commit, 3 `slot_occupied`) | `test_concurrent_moves_into_one_slot_commit_once` |
| Exit: placement survives refresh and theme change | passed (integration; fresh service instance) | `test_theme_change_remaps_semantically_and_survives_reload` |

## Stage 5 — Social: friendships, blocks, five-minute decisions, shares, notifications (W05 backend, part 1) — 2026-10-23
**Migration `V004_social.sql`** (applies from empty after V001–V003 through the runner). Member aggregates are interleaved in `Members`:
- `Relationships`: two mirrored rows per pair (`requested_out`/`requested_in`/`accepted`), so each member lists only their own circle
- `MemberBlocks`: directional rows; a block in either direction blocks interaction
- `Decisions`:
  - `CHECK duration_seconds = 300`
  - `opened_at`/`closes_at` are server times
  - unique `DecisionsById`, plus `DecisionsByStateClose` for the closer
- `DecisionAudience`: one row per recipient (the primary key enforces one invitation per recipient per request)
- `DecisionResponses`: one row per respondent and decision (primary key) with `submitted_at` = server time and `eligible` set at close
- `ShareGrants`: `token_hash` only, unique; `subject_version` pins what was shared
- `SharePreviews`: the controlled preview cache, interleaved in the grant
- `Notifications`: unique per (recipient, event, type)

The emulator rejected a query on the NULL_FILTERED `DecisionsByStateClose` index, so it is now an ordinary index.

**Domain (`brandme_core/domains/social/`)**
- `clock.py`:
  - `SpannerTxnClock` (production) reads `CURRENT_TIMESTAMP()` inside the very transaction that opens, answers or closes a decision.
  - `FixedTxnClock` is for deterministic tests only.
  - **Documented boundary (BM-SOC-005):** a response is accepted iff the server time read inside its own transaction is strictly before `closes_at` and the decision is `open`.
- `relationships.py`:
  - A friendship needs a request and an accept by the recipient side's own session. The requester or a third party gets the same 404 as a missing request.
  - Unknown, inactive and blocked members all look like 404.
  - **Block** removes, in one transaction:
    - the friendship
    - each party from the other's open decision audiences
    - each party from the other's selected-member shares
    - unread notifications either caused for the other

    It also refuses future requests, notifications and proposals between them.
  - `friendship_proposal_policy` is the policy `OutfitService(proposal_policy=…)` takes at wiring time (tested).
- `decisions.py`:
  - Recipients must be reachable friends (`ineligible_recipients` lists who is not).
  - Subjects must be the creator's own item/outfit, or a catalog product via an injected check (providers lane).
  - Limits are configurable: 5 per UTC day (counted on server-timed `opened_at`), 3 open at once, 12 recipients.
  - A request identical to one in the last 24 h is allowed but flagged `repeat_request` (in `decision.closed`, for the rewards domain).
  - Agent principals without `social:send` create a **draft**: no notification, no `decision.opened`, invisible to recipients. Only the member's own session can `open` it.
  - Responses:
    - an identical replay is a no-op (no revision, no event)
    - a changed answer is a new revision of the same record until the deadline
    - "Try this instead" needs an item visible to the respondent
    - the creator cannot answer
  - **Blind mode** hides others' choices and notes from a respondent until they answer or the decision closes; the creator always sees results.
  - **Close happens once:** the state check and tally run in one serializable transaction. Eligibility is reconciled at close: in the audience, not the creator, not blocked, `submitted_at < closes_at`. `decision.closed` carries sorted eligible respondent ids, `zero_replies` and `repeat_request` (references only).
  - Zero replies give "No replies this time" plus `next_actions: [save, ask_again_as_new_request]`; nothing is fabricated.
  - The requester outcome is labelled self-reported.
- `shares.py`:
  - `allowed_fields` is a typed request checked against a per-subject allowlist. Anything else is refused with `refused_fields`:

    | Subject | Shareable fields |
    |---|---|
    | item | title, category, color family, colors, materials |
    | outfit | title, occasion, notes, items |
    | persona snapshot | saved name, summary, declared axes; never inferred/effective values |

    Prices, sizes, notes, receipts, tag serials, owner/member ids, ownership identity and closet totals are never shareable.
  - An outfit share lists only the pinned version's items, by position, with no item ids.
  - Expiry is 5 min–365 d from server time; at most 200 active shares per member.
  - The token (`secrets.token_urlsafe(32)`) is **returned once**. Only its SHA-256 is stored, and an idempotent replay returns `token: null, token_already_issued: true`, so the token never enters `IdempotencyRecords`.
  - Every access re-checks, under current permissions: revocation, expiry, audience membership + friendship, blocks, owner active, subject still present.
  - **Revoke** sets `revoked_at`, deletes the cached preview and the recipients' unread `share_received` notices in the same transaction, and emits `share.revoked`. Later access gets **410 `share_unavailable`** with `reason` (`revoked`/`expired`/`removed`); unknown or malformed tokens get 404.
  - `closet_capsule` and `badge` are refused with `unsupported_subject_type` (no backing entity in this lane yet).
  - Share creation calls the privacy guard (`social.shares`).
- `notifications.py`: in-app only (no email/push provider is configured; ch.06 gate). Rows are written in the same transaction as their cause. Payload keys are allowlisted (ids, enums, result label). `mark_read` touches only the caller's rows.
- `deletion.py`: 5 categories (`social.relationships`, `.blocks`, `.decisions`, `.shares`, `.notifications`), registered with the foundation registry and the privacy-lane handler.
  - Deleting a member erases their answers on friends' decisions; the closed tally keeps counts only.
  - It removes them from others' audiences and share recipient lists, and nulls the actor on notifications they caused.
- `api.py` (FastAPI, unmounted): `POST /decisions`, `POST /decisions/{id}/responses`, `POST /shares`, `DELETE /shares/{id}` from ch.03 §6. Lane additions go to **PD-09**:
  - relationships, blocks
  - decision get/list/open/close/cancel/outcome
  - share list, member open, `POST /shares/resolve`
  - notifications

  `POST /shares/resolve` is the only route that accepts an anonymous caller; the token travels in the body so it stays out of URL logs.

**Gateway (UNMOUNTED):** `routes/v1/social.ts` → `socialRouter(client)` and `routes/v1/decisions.ts` → `decisionsRouter(client)`.
- Cheap shape checks with field allowlists: exactly 300 s, 1–12 unique recipients, share shape and audience rules, token shape.
- Relationship/block targets use **`target_member_id`**, because `member_id` is a refused identity field.
- `DomainRequest.principal` is now `Principal | null`. Null is used only by `forwardOptionalPrincipal` on `/shares/resolve`, which should sit behind the foundation rate limiter at mount time.

**Evidence** (pinned venv: Python 3.11.15, google-cloud-spanner 3.40.1, pytest 7.4.3; emulator 1.5.28)
| Check | Result |
|---|---|
| This branch: `pytest tests/test_persona_*.py tests/test_wardrobe_*.py tests/test_social_*.py tests/foundation -W error::…UnhandledThreadException` | **235 passed, 6 skipped** (5 privacy-lane + 1 spatial-manifest, all NOT RUN here). Social suites 3 runs in a row green; deadline/concurrency subset 5 runs in a row green |
| W11 `bec80b1` overlay with spatial manifests: `pytest tests/test_persona_*.py tests/test_wardrobe_*.py tests/test_social_*.py tests/test_privacy.py tests/test_rights.py` | **170 passed, 0 skipped** (includes the social privacy-handler registration and the processing-freeze refusal of share creation) |
| Gateway: `tsc --noEmit` 0; `eslint src` 0; `vitest run src/routes/v1` | **30 passed** (+7 `social.test.ts`) |

| Acceptance | Result | Test |
|---|---|---|
| BM-SOC-001 only the intended recipient establishes the friendship | passed (integration) | `test_only_the_intended_recipient_can_accept` |
| BM-SOC-002 audience and 5-minute deadline server-owned and visible | passed (integration, **production `SpannerTxnClock`**: `opened_at` lies between two Spanner reads taken around the call, `closes_at − opened_at = 300 s`; client `closes_at`/other durations refused) | `test_server_owns_audience_and_five_minute_deadline` |
| BM-SOC-003 unrelated member learns nothing | passed (integration; uninvited friend and stranger get the same 404 as a missing id, with no subject in the error; lists empty) | `test_private_decision_invisible_to_unrelated_member` |
| BM-SOC-004 yes/pass/alternative stored; alternative needs a visible item | passed (integration) | `test_votes_and_alternative_reference` |
| BM-SOC-005 at and after the exact deadline | passed (integration): accepted at `closes_at − 1 µs`; rejected at `closes_at`, `+1 µs`, `+1 h` (`FixedTxnClock`). With `SpannerTxnClock`, moving the stored deadline to Spanner-now − 1 µs makes the next response fail with `decision_closed` (`server_time ≥ closes_at`). The closer does not close at `closes_at − 1 µs` | `test_exact_deadline_boundary`, `test_server_clock_rejects_late_response` |
| BM-SOC-006 concurrent replay of response and expiry | passed (integration, threads): 10 identical concurrent replays → 1 record, revision 1, 1 `decision.responded`. Then 6 schedulers + 3 owner closes + 3 late responses race at the deadline → **exactly 1 `decision.closed`**, tally unchanged, late responses refused | `test_concurrent_replays_one_response_one_close` |
| BM-SOC-007 blind until response | passed (integration) | `test_blind_until_response` |
| BM-SOC-008 zero replies truthful | **server half passed** (no fabricated responses; explicit next actions). The browser half belongs to the UI lane: not_run | `test_zero_replies_is_truthful` |
| BM-SOC-009 block revokes shares, decisions, pending notifications | passed (integration) | `test_block_revokes_friendship_decisions_shares_and_pending_notifications` |
| BM-SOC-010 external preview leaks nothing | passed (integration; anonymous link view of an outfit contains only requested fields and the pinned items; no owner id, item ids, sizes, notes, rest of closet or unrequested occasion; token not stored in `ShareGrants` or `IdempotencyRecords`) | `test_outfit_preview_discloses_only_requested_fields_of_the_outfit`, `test_refuses_fields_outside_the_allowlist` |
| BM-SOC-011 revoke while cached | passed (integration; preview row deleted in the revoking transaction, 410 for member and link access, notices withdrawn, one `share.revoked`) | `test_revocation_purges_cached_preview_and_blocks_access` |
| BM-SOC-012 agent without send authority | passed (integration; draft only, 0 notifications, 0 `decision.opened`, recipients 404, agent cannot open, member opens from own session) | `test_agent_without_send_authority_only_drafts` |
| Exit: server-timed decision deadlines | passed (see BM-SOC-002/005/006) | — |

**Not done in this stage / honest limits**
- Firestore projections of shares/decisions are not written by this lane. `share.revoked` is the event a projector must consume to delete shared projections (ch.03). No such projector exists yet.
- Search discovery between members does not exist, so "blocking excludes search" has nothing to act on yet.
- The decision closer (`DecisionService.close_due`) is a callable, not a deployed scheduler; integration must run it (Cloud Scheduler/Tasks). Responses are refused at the deadline whether or not it has run.
- Catalog subjects/alternatives use an injected `catalog_check` (providers lane); the default allows any id and must be replaced at wiring.

**Proposed deviations added**
- **PD-09 (extended)**: social lane endpoints listed above, plus `target_member_id` as the request field for relationships and blocks.
- **PD-10**: share expiry bounds (5 min–365 d) and the 200-active-share cap are lane choices; the contracts do not specify them.
- **PD-11**: 410 `share_unavailable` with `reason` for revoked/expired/removed shares reached by a valid token or an authorized member; 404 for anything else.

## Stage 6 — Rewards: ledger, caps, reversals, badges, benefits, disputes (W05 backend, part 2) — 2026-10-23
**Migration `V005_rewards.sql`** (applies from empty after V001–V004 through the runner). Member rows are interleaved in `Members`:
- `RewardAccounts`: reducer row; CHECK `available ≥ 0`, `reserved ≥ 0`, `recovery_due ≥ 0`
- `RewardEntries`: append-only journal (`credit`/`reversal`/`reserve`/`redeem`/`release`/`correction`; state `posted`/`capped`/`excluded`). It has unique NULL_FILTERED indexes on the cause `(member, rule, version, qualifying event)` and on `reverses_entry_id`.
- `RewardFacts`
- `BadgeAwards`
- `Benefits`: CHECK that a partner benefit is funded and names a sponsor; inventory CHECKs
- `BenefitReservations`
- `RewardDisputes`

**Domain (`brandme_core/domains/rewards/`)**
- `rules.py` mirrors `contracts/reward-rules.json`; `test_rules_mirror_the_contract` compares the two field by field. Caps use **UTC** windows on the qualifying server event time: calendar day, ISO week from Monday 00:00, calendar month. The member's timezone is never consulted. `referral_activated` and `optional_research_contribution` are listed with `available: false`: no referral system or funded campaign exists, so they never settle.
- `ledger.py`:
  - **Cause uniqueness.** A credit's primary key is derived from the cause key (or from member+rule+version for lifetime-once rules), so a duplicate cause collides inside the settling transaction. The unique cause index backs this up.
  - A credit first pays down `recovery_due`.
  - A **reversal is a new linked entry**. It takes what it can from `available` and records the shortfall as `recovery_due`, so spendable points never go negative and are never a cash debt. It is idempotent per original entry.
  - Operator corrections are reasoned entries tied to a dispute.
  - `consistency()` checks the account equals the sum of the journal.
  - Spanner reads in a read/write transaction do not see that transaction's buffered mutations. A per-transaction overlay (fresh on every retry attempt, verified in the client's `run_in_transaction`) makes later checks in the same settlement see what it just wrote.
- `consumer.py`: inbox consumer `rewards.ledger`, one transaction per delivery (`first_delivery` → rules → badges → reward events). Event mapping:

  | Event | Outcome |
  |---|---|
  | member-declared `persona.updated` / `persona.guest.migrated`, plus first own `outfit.version.created` or migrated saved look | **100 setup once** |
  | `wardrobe.item.created`/`updated` into `owned` | **25 once**; want / on-the-way never qualify |
  | `outfit.proposal.accepted` | **25** to the proposer: never self, one per owner→proposer pair per UTC day (disclosed policy), 100/day |
  | `decision.closed` | **10** per eligible respondent, identical for yes/pass/alternative (the event carries no choices), 100/day; a `repeat_request` gives an `excluded` entry |

  Inactive or frozen members get nothing (privacy guard `rewards.ledger`).
- `badges.py`: all six badges with visible criteria (version 1), evidence references, earned date and revocation.

  | Badge | Evidence |
  |---|---|
  | First Reflection | first member-saved persona |
  | Closet Curator | 10 placed owned items |
  | Trusted Eye | 20 valid responses across ≥ 5 decisions; capped responses count as participation |
  | Style Collaborator | 5 accepted proposals |
  | Care Keeper | approved-workflow repair |
  | Material Story | reviewer-accepted product-history contribution |

  A badge is revoked only when a verified reversal removes its evidence.
- `benefits.py`:
  - Reserve checks points and inventory **atomically** in one transaction, with `Idempotency-Key`.
  - The pending reservation is the durable fulfillment work item. `run_fulfillment` calls the fulfiller outside any transaction; `settle` records the outcome once.
  - Success moves points reserved → spent. Failure, a fulfiller exception or expiry (`expire_due`) moves reserved → available and returns the inventory unit.
  - Partner benefits cannot exist unfunded.
- `service.py`:
  - member reads: summary with honest labelling ("not currency…"), entries cursor, badge progress, next milestone, rules and the recovery policy
  - member disputes (`rewards:write`, no agent delegation, ≤ 5 open)
  - operator commands (`moderation:admin`; aal2 outside development; never delegated; **self-review refused**): dispute queue/resolution with a reasoned correction, member ledger audit, linked reversal, reviewer acceptance of catalog corrections (50, 250/ISO week) and product-history contributions
  - verified repairs only from a **service principal whose issuer is on the approved list**; the default list is empty, so no repair can award until a workflow is approved
- `deletion.py`: 4 W10 categories. Deletion returns a pending reservation's inventory unit to the benefit.
- `api.py`:
  - member router: `GET /rewards`, `POST /benefits/{id}/reservations` (ch.03), plus `/rewards/entries`, `/rewards/reservations`, `/rewards/disputes`, `GET /benefits` (PD-09)
  - separate **ops router** under `/ops`
  - there is **no member route that awards or edits points**

**Gateway (UNMOUNTED):** `routes/v1/rewards.ts` → `rewardsRouter(client)` + `rewardsOpsRouter(client)`.
- Reservation bodies must be empty; the cost comes from the server-side benefit.
- Disputes are member-only.
- Ops routes require `moderation:admin`, no delegation, and aal2 outside development.

**Evidence** (pinned venv: spanner 3.40.1, pytest 7.4.3; emulator 1.5.28)
| Check | Result |
|---|---|
| This branch: `pytest tests/test_persona_*.py tests/test_wardrobe_*.py tests/test_social_*.py tests/test_rewards_*.py tests/foundation -W error::…UnhandledThreadException` | **261 passed, 7 skipped**. The 7 skips are 6 privacy-lane and 1 spatial-manifest check, NOT RUN here. Rewards suites green 3 runs in a row. |
| W11 `bec80b1` overlay with spatial manifests, lane suites + `test_privacy.py` + `test_rights.py` | **197 passed, 0 skipped** |
| Gateway: `tsc --noEmit` 0; `eslint src` 0; `vitest run src/routes/v1` | **35 passed** (+5 `rewards.test.ts`) |

| Acceptance / exit evidence | Result | Test |
|---|---|---|
| BM-LOY-001 setup 100 and first owned item 25, once, with evidence and rule version | passed (integration). Driven by the **real** persona/wardrobe/outfit outbox rows; wishlist item and provisioned profile earn nothing; redelivery changes nothing. | `test_setup_and_first_owned_item_post_once_with_evidence`, `test_provisioned_or_inferred_profile_does_not_count_as_saved` |
| BM-LOY-002 / **exit: 10 concurrent duplicates → one ledger cause, correct balance** | passed (integration, threads) | `test_ten_parallel_duplicates_change_the_balance_once`: 10 simultaneous deliveries → 1 processed, 9 `duplicate_delivery`, 1 entry, balance 10, 1 inbox receipt. `test_same_cause_through_different_events_settles_once`: 6 different events racing the lifetime-once rule → 1 award. `test_injected_abort_does_not_duplicate_entries`: ABORTED after buffering → 1 entry, 1 `reward.posted`. |
| BM-LOY-003 / **exit: caps** | passed (integration) | `test_daily_response_cap_and_utc_reset`: 12 responses → 10 posted + 2 `capped` = 100, then 00:00 UTC opens a new window. `test_weekly_and_monthly_caps`: 6 corrections → 250/ISO week, 5 repairs → 200/month. `test_cap_windows_are_utc_and_ignore_member_timezone`. |
| BM-LOY-004 yes and pass earn equal points | passed (integration; real decision → close → outbox → consumer) | `test_yes_and_pass_earn_equal_points` |
| BM-LOY-005 cannot self-award via API | **API half passed**: no award/edit routes (Python 404/405, gateway 404); members, delegated or aal1-production operators, self-review and member-as-repair-workflow all refused; duplicate contribution settles once. **Firestore half not_run**: no Firestore rules or reward projection exist in the repo. | `test_member_routes_and_no_award_route`, `test_untrusted_paths_cannot_award`, `rewards.test.ts` |
| BM-LOY-006 all six badges, criteria and evidence inspectable | passed (integration) | `test_all_six_badges_with_inspectable_evidence` |
| BM-LOY-007 / **exit: racing redemptions never go negative** | passed (integration, threads): 100 points vs two 60-point benefits at once (repeated 3×) → exactly one; 150 points vs 10 concurrent 50-point reservations → exactly 3; inventory 2 vs 4 members → exactly 2; same key ×5 → one reservation | `test_two_benefits_race_for_insufficient_points`, `test_ten_concurrent_reservations_never_overspend`, `test_inventory_is_reserved_atomically` |
| BM-LOY-008 failed fulfillment releases once, visible status | passed (integration): failed and fulfilled side by side; a second settle or worker run changes nothing; 8 racing settlements → 1; expiry release | `test_failed_fulfillment_releases_once_with_visible_status`, `test_concurrent_settlements_resolve_once`, `test_expired_reservations_are_released` |
| BM-LOY-009 / **exit: reversals** | passed (integration): original preserved plus linked reversal. Spent points become `recovery_due` 40 with available 0; the next award pays recovery first; idempotent; the badge is revoked, then re-earned from new evidence; reversals cannot be reversed. | `test_reversal_is_linked_and_spent_points_become_recovery_due` |
| BM-LOY-010 benefits without research consent | **server half**: no core function depends on rewards or consent; research rule unavailable. Browser half belongs to the UI lane: not_run | — |
| Exit: idempotency keys | passed (reservation replay over HTTP and concurrently) | `test_reserve_over_http`, `test_ten_concurrent_reservations_never_overspend` |

**Not done / honest limits**
- Console pages `brandme-console/app/(ops)/{moderation,rewards-disputes}` are not built yet. The shell they must plug into (`console-page-header`, console identity adapter) exists only on `bench/astra-consumer-ui-20261005`, not on this lane's base. Planned after W08, verified against an overlay of that shell.
- Reward projection to Firestore (and its security rules) does not exist. The ledger is API-only.
- No referral or research campaign system; those two rules never settle.
- Return-driven reversal of `first_owned_item` (a returned order unit) is not automatic. An operator can reverse it with evidence.

**Proposed deviations added**
- **PD-12** `rewards:write` scope for member writes that can never award (benefit reservation, dispute). ch.03 lists only `rewards:read`. Also: foundation first-party sessions currently grant only `profile:*` and `privacy:manage` (`brandme-gateway/src/middleware/session.ts:113`). Integration must add `wardrobe:*`, `outfits:*`, `social:*`, `rewards:read`, `rewards:write`, or none of this lane's routes are reachable by members.
- **PD-13** Operator authority = `moderation:admin` + aal2 outside development + no delegation + no self-review (ch.03 lists `moderation:admin` as console-only operator authority but does not define reward reviewer roles).
- **PD-14** Proposal anti-collusion policy: one award per owner→proposer pair per UTC day (disclosed in the rule text). Capped and pair-excluded results are recorded as zero-point entries, so members can see why.
- **PD-15** Material Story is earned from a reviewer-accepted *product-history* contribution, which carries no points: the rule table has no product-history rule. Catalog corrections earn points under `catalog_correction_accepted`.

## Stage 7 — Try-on server: consent, jobs, retention, deletion (W08 server side) — 2026-10-23
**Schema.** V003 media tables (PD-08) gained the columns this stage needs:
- `MediaObjects`: `state`, `content_type`, `rejection_code`, `purged_at`, `version`, plus CHECK *saved ∨ expiring ∨ deleted*
- `TryOnJobs`: `provider_deletion`

The expiry indexes are now ordinary indexes, because the emulator refuses NULL_FILTERED index queries. V003 is unmerged and unapplied anywhere persistent, so editing it in place is safe.

**Domain (`brandme_core/domains/media/`)**
- `store.py`:
  - a `MediaStore` interface: constrained upload target, stat, read, write, delete
  - private object paths `members/{id}/media/{id}` (no file name, no public URL)
  - magic-byte type check for JPEG/PNG/WebP, 10 MB cap
  - **`MemoryMediaStore` is a labelled simulation**; no production object store is configured in this repo
- `providers.py`: a `TryOnProvider` interface (terms, region, retention disclosure, deletion support) and a registry that only uses an *approved* provider. **No provider is approved here.** No Vertex `virtual-try-on-001` adapter ships: no account, region or terms exist to verify one. `SimulatedTryOnProvider` is a labelled test double that records every upload.
- `service.py`:
  - **Uploads.** An idempotent create mints a fresh constrained URL per response; the URL is never stored in the idempotency record. Completion verifies size, type and hash outside any transaction; rejected bytes are purged. `GET /media/jobs/{id}` returns status only.
  - **Jobs.** Creation needs `consent.accepted === true` for the approved provider's *current* `provider_id` and `terms_version` (otherwise `consent_required`/`consent_outdated` with the disclosure). Each input photo serves one job, and there is a daily spend limit (default 10). `calibrated_fit` is refused with `capability_unavailable` and creates nothing; `live_overlay` is refused with `on_device_only`, so the server accepts no frames.
  - **Dispatch.** Consent is re-checked in the claiming transaction right before the upload: revoked consent, privacy freeze or unapproved provider means no upload. Provider calls and blob I/O run outside transactions, and outcomes are recorded with state re-checks. A job deleted mid-upload has its provider copy deleted; a late output is dropped.
  - **Results.** Labelled `generated_visual_preview` (`…_simulated` with the double) with text "Generated visual preview. Not a fit or size guarantee." Retrieval goes through an authorized route only (private, no-store). Saving is explicit; unsaved results expire 24 h after job creation (server time). The input is deleted as soon as processing ends.
  - **Delete** follows a manifest: the job and every linked object are tombstoned in one transaction, then blobs are purged, then provider deletion is requested (`confirmed`/`failed`/`unsupported`/`not_sent` recorded). Consent revocation cancels queued jobs and deletes their photos.
  - **Sweepers:** `expire_due` (unsaved media/jobs past expiry, with provider deletion) and `purge_pending` (blob purge retry).
- `deletion.py`: W10 categories `media.tryon_consents` and `media.tryon_media`. Rows are deleted or tombstoned in the transaction; blobs are purged after commit through the store registered by `MediaService`, then the rows are removed.
- `api.py` (unmounted): ch.03 `POST /media/uploads` (201), `GET /media/jobs/{id}`, `POST /try-on/jobs` (202), `DELETE /try-on/jobs/{id}` (204). Lane additions (PD-09): upload complete, capabilities, job get/result/save, consents list/revoke.

**Gateway (UNMOUNTED):** `routes/v1/media.ts` → `mediaRouter(client)` and `routes/v1/tryon.ts` → `tryOnRouter(client)`.
- Bounded upload shape.
- Consent shape required; `calibrated_fit` and `live_overlay` are refused at the edge and never forwarded.
- Result bytes are relayed only for `image/png|jpeg|webp`, with `private, no-store`.
- **Ownership note:** the foundation endpoint inventory (`packages/contracts/scripts/endpoints.mjs:93-94`) tags `/try-on/jobs` as owner `spatial-ar`. This lane's brief assigns the W08 *server* side here and lists `tryon.ts` as lane-owned. The client UI remains the spatial lane's.

**Evidence** (pinned venv; emulator 1.5.28)
| Check | Result |
|---|---|
| This branch: lane suites (persona, wardrobe, social, rewards, media) + `tests/foundation` | **272 passed, 7 skipped** before the freeze test was added (privacy-lane/spatial checks NOT RUN here); `test_media_tryon.py` alone **11 passed, 1 skipped**, 3 runs in a row |
| W11 `bec80b1` overlay: lane suites + `test_privacy.py` + `test_rights.py` | **209 passed, 0 skipped**. Includes the freeze test: a frozen member cannot upload, and a job queued before the freeze is cancelled at dispatch with no upload. |
| Gateway: `tsc --noEmit` 0; `eslint src` 0; `vitest run src/routes/v1` | **39 passed** (+4 `tryon.test.ts`) |

| Acceptance / exit evidence | Result | Test |
|---|---|---|
| BM-AR-007 no provider upload without explicit consent | passed (integration). Missing, false, non-boolean and outdated consent create no job. A consent revoked before dispatch cancels the job with no upload and deletes the photo. Freeze → no upload (W11). | `test_no_provider_upload_without_explicit_consent`, `test_privacy_lane_freeze_stops_uploads_and_dispatch` |
| BM-AR-008 approved provider job labelled, saved only by choice | **server half passed with the simulated provider** (label, explicit save, unsaved by default, owner-only retrieval). Real-provider half **not_run**: no approved provider exists. | `test_photo_job_is_labelled_and_saved_only_by_choice` |
| BM-AR-009 calibrated fit unavailable | passed (domain + HTTP + gateway; nothing created, never relabelled) | `test_unavailable_modes_and_unconfigured_provider`, `test_http_surface`, `tryon.test.ts` |
| BM-AR-010 delete saved image removes originals/derivatives | passed (integration, simulated store): manifest, blobs gone, provider deletion confirmed, result 404, idempotent; deletion during processing leaves no orphan | `test_delete_saved_preview_follows_the_manifest`, `test_delete_while_processing_leaves_no_orphans` |
| BM-DATA-009 / **exit: unsaved media expiry demonstrable** | passed (integration). `expires_at` = creation + 24 h by server time. After moving the expiry to Spanner-now − 1 µs, the sweeper tombstones and purges the unsaved output and the never-completed upload, marks the job `expired` and confirms provider deletion. The saved preview is untouched. No unpurged tombstones remain. Provider retention is disclosed from provider terms, never promised. | `test_unsaved_media_expires_and_saved_media_stays` |
| Exit: try-on consent/job/deletion flow | passed (see above) plus HTTP end to end | `test_http_surface` |
| BM-AR-001..006 (labels in UI, device AR, camera lifecycle, tracking) | not this lane (spatial-ar UI, devices) | — |

**Honest limits**
- No real provider and no real object store: all provider and blob behaviour is proven against labelled simulation doubles. Production needs an approved provider adapter and a private-bucket store adapter with V4 signed URLs, then a re-run of these tests against them.
- Workers (`dispatch_queued`, `collect_processing`, `expire_due`, `purge_pending`) are callables. Integration must schedule them.
- Media export returns metadata. Image bytes need the export lane's authenticated download.

**Proposed deviations added**
- **PD-16** Try-on and media use the `wardrobe:read`/`wardrobe:write` scopes; ch.03 defines no media scope.
- **PD-17** Consent travels in the `POST /try-on/jobs` body, and one standing consent per provider and terms version is reused. A terms change requires re-consent (`consent_outdated`).

## Stage 8 — Member reports, moderation and the operator console pages — 2026-10-23
**Reports and moderation (social, V004 `MemberReports`).** ch.01 §6.4 requires report/mute/block on member-generated content, and the console needs a moderation queue.
- **Who can report what.** A member can report only content they can see:
  - a response on a decision they created or were invited to
  - a share sent to them
  - a proposal on their own outfit
  - a member they have a relationship row with, or a block with

  There is one report per reporter and target, and at most 20 per UTC day. A report never auto-hides content, and the reported member never learns who reported them or that a report exists.
- **Operator resolution** (`moderation:admin`, aal2 outside development, never delegated, never their own report and never a report about themselves):
  - dismiss
  - remove content: redact the response note while keeping the vote, revoke the share through the shared `revoke_grant`, or decline and redact the proposal
  - escalate: member conduct only; no account actions exist in this lane

  Each resolution is attributed and notifies the reporter (`report_resolved`).
- **Privacy.** `social.reports` is anonymized, not erased. The reporter id is replaced by the report's own id, which is unlinkable and cannot collide on the unique `(reporter, target)` index, and the note is removed. Content owners are anonymized the same way.
- **Kernel.** Operator checks moved into the lane kernel (`require_operator`, `require_not_self`); `rewards.operators` re-exports them.
- **Routes.**
  - Python: `POST`/`GET /reports` and `create_moderation_ops_router` (`/ops/moderation/reports`, `/resolve`).
  - Gateway `social.ts`: `/reports` (typed targets, exact target keys, identity fields refused) and `moderationOpsRouter`.

**Console subtrees (contract v1 from `docs/build/status/astra-consumer-ui.md`)**
- `brandme-console/app/(ops)/moderation/`
  - `page.tsx`: report queue with Open/Actioned/Dismissed tabs; a resolve form per report (`actions.ts` server action)
  - `loading.tsx` and `error.tsx`
  - `_lib/ops-gateway.ts`: server-only client. It forwards the operator's own cookie/bearer to the gateway `/api/v1/ops/*` and maps 401/403/unset-URL to honest states.
  - `_lib/states.tsx`: shared unconnected, signed-out, denied and failed states
  - `_lib/ops.module.css`: shell `--bm-*` tokens only
- `brandme-console/app/(ops)/rewards-disputes/`
  - `page.tsx`: dispute queue; "no change" or a reasoned correction entry with an evidence reference
  - `members/[memberId]/page.tsx`: ledger audit showing the reducer consistency check, account facts and the journal, with a linked-reversal form on reversible entries only
  - `actions.ts`, `loading.tsx`, `error.tsx`
- **Contract v1 compliance.** Each page renders exactly one `<h1>` via `ConsolePageHeader` and adds no `<main>`/rail. Wide tables sit in a labelled, focusable `console-table-region`. Pages assume no role: every read and action is authorized by the gateway and domain with the operator's own session.

**Evidence**
| Check | Result |
|---|---|
| This branch, `pytest tests/test_social_reports.py tests/test_social_privacy_api.py` | **7 passed, 1 skipped** (privacy-lane check NOT RUN here). Covers visibility rules, dedupe, no disclosure to the reported member, removal per target type, escalation-only for members, attributed resolution with reporter notification, and anonymization by two reporters of the same target without collision. |
| Gateway `vitest run src/routes/v1`; `tsc --noEmit`; `eslint src` | **40 passed**; tsc 0; eslint 0 |
| Console overlay: these subtrees copied onto `bench/astra-consumer-ui-20261005@a37ec2b` (the shell lives only there), per-app `npm install`, Next 14.2.35 | `tsc --noEmit` exit 0; `next build` exit 0 (`ƒ /moderation`, `ƒ /rewards-disputes`, `ƒ /rewards-disputes/members/[memberId]`). `next lint` not run: the console has no ESLint config, which the UI lane owns. |
| Browser smoke (scratch harness; Chromium 1194 via playwright-core, `next start`; the console calls this lane's Python ops routers under `/api/v1` on the Spanner emulator, with a test-only cookie resolver standing in for the gateway hop, whose routers are covered by vitest) | **13/13**: signed-out state; single `h1`; member without role sees the denied state; report listed → remove content → note redacted and actioned outcome shown; dispute listed → +50 correction → ledger consistent with credit + correction → reversal recorded as a third linked entry; no page-level horizontal scroll at 390 px. Screenshots were inspected at 1440 and 390 px. |

**Not done / honest limits**
- The console→gateway operator credential transport is not defined (PD-18 below). The pages forward the incoming cookie/authorization, which works only if console and gateway share a cookie domain or the integrator adds a server-side token exchange.
- The browser smoke bypassed the TypeScript gateway hop (unmounted routers), and it ran against the UI lane's shell from another branch, not on this lane's base. It is not evidence for the final mounted stack.
- Mute is not implemented. Member conduct escalations have no downstream owner yet.

**Proposed deviations added**
- **PD-18** Console→gateway operator auth transport: shared cookie domain vs server-side token exchange. Foundation or UI lane to decide; the pages need one header-forwarding change either way.
- **PD-19** Route mismatch. The shell's `lib/navigation.ts` links `/rewards/disputes`, but this lane's brief owns `app/(ops)/rewards-disputes`, which serves `/rewards-disputes`. The pages were built at the owned path. Proposal: the shell nav points to `/rewards-disputes`, or the brief is updated to own `app/(ops)/rewards/disputes`. Moving the folder is a one-line change.

**Stage 8 addendum (same day).**
- The pages first imported the shell's `ConsolePageHeader`, which does not exist on this lane's base. The foundation CI job runs `pnpm -r build`, which includes the console's `next build`, and would have failed. The import is optional under contract v1 §3, so the pages now render the same `console-page-header` markup from `(ops)/moderation/_lib/page-header.tsx` (commit `11860e4`).
- Re-verified on this branch (Node 24.21.0, pnpm 10.34.6, `pnpm install --frozen-lockfile`): `pnpm --filter @brandme/console build` exit 0, and `pnpm check` exit 0. That covers the spec validator, contract/token drift, packages type-check/tests, gateway type-check/tests, python foundation tests and docs links.
- Re-verified on the UI-shell overlay: tsc 0, `next build` 0, browser smoke **13/13** on the final code.
- Commit `e13fd43` (the version before the fix) may show a red `check` run for this reason. `11860e4` supersedes it.

## Stage 9 — Ultra Plan: privacy completeness, event delivery, shell adapter, PD defaults, mute, jobs — 2026-10-23
Commits `eb12620`, `84fad9d`, `e48414a`, `b79436d`, `efa1a25` on `claude/opus-consumer-domains-1csp2g`.

**Privacy (Ultra Plan item 4, My Data hooks).**
- **Every writer is guarded.** `kernel.guard_write`/`processing_allowed` wrap the privacy lane's `assert_processing_allowed` inside the writer's own transaction and return `processing_frozen`. They cover persona, wardrobe, social, rewards and media writers.
  - Reductions and safety actions stay open: remove, block, unblock, mute, revoke, cancel, delete, reversal.
  - A notification to a frozen recipient is skipped and never fails the actor.
- **Record-scoped requests are refused, not widened.** Handlers delete whole categories, so a request carrying `record_keys` returns a truthful exception outcome (`WHOLE_CATEGORY_ONLY`). It never reads or writes.
- **Registration hook.** `persona.lane.register_consumer_domains(registry, database=, media_store=)` registers all five handlers in any `PrivacyRegistry` (e.g. `ReadService.catalog`), is idempotent, and wires media blob purge. `coverage()` reports honest completeness.
- **Two deletion gaps found and fixed by the new end-to-end test:**
  - An account-scoped deletion left an empty `PersonaProfiles` row. It is now dropped once every persona category is empty, including on tombstone reapply.
  - Reports *about* a deleted member kept their id in `MemberReports.target_ref`. The id is now replaced per report.

**Events (Ultra Plan item 4, coordination with PR #47's outbox).**
- **Catalog.** On `main`, the foundation worker builds its allowlist from the foundation catalog only, so all 36 lane contracts stay `pending` (demonstrated in the test below). `python -m brandme_core.domains.persona.outbox_worker` runs the same foundation worker with the lane catalog loaded.
- **Ingress.** `persona.ingress` is the lane subscriber. It applies these checks:
  - closed envelope; attributes must equal the body; canonical form
  - configured environment only; registered privacy class; contract validation
  - the consumer applies the effect with `first_delivery` in the same transaction as the freeze recheck and stale-version check
  - ack only after commit; rejections are never acked (subscription dead-letter policy); fixed log codes only

  It ships a REST pull client (emulator in dev, ADC otherwise, no redirects or ambient proxy) and `python -m ...persona.ingress [--once]`.
- **`commerce.order.observed` has no registered contract on `main`.** The foundation publisher would refuse it, so the wardrobe would never receive orders through Pub/Sub. Ingress validates it against a closed consumer copy of commerce's payload as emitted at `main` 5174ec2. Drift fails closed.

**Shell contract (Ultra Plan item 3).** All three ops pages import `ConsolePageHeader` only from `brandme-console/app/(ops)/_shell/console-page-header.tsx`. Its props `{eyebrow?, title, description?, actions?}` and markup are the consumer-ui contract v1 §3 component exactly. The swap is one line: `export { ConsolePageHeader } from '@/components/console-page-header'`. It was proven by applying that line on the UI lane `a37ec2b` and type-checking against the real component.

**PD-09/10/11 defaults (Ultra Plan item 2).** All three were already live. `brandme_core/domains/social/policy.py` now holds the PD-10 lifetime and cap and the PD-11 gone-share status, labelled pending ratification. Setting `SHARE_GONE_STATUS = 404` makes revoked, expired and removed shares indistinguishable from unknown ones (tested).

**Mute (ch.01 §6.4).**
- **Data and routes.** V004 `MemberMutes`. `POST`/`DELETE`/`GET /mutes` in the FastAPI and gateway routers. Circle entries carry `muted`.
- **Semantics.**
  - Mute is one-sided and private: no event, no notification, and the muted member keeps every permission.
  - The muter stops getting the muted member's notifications.
  - The muted member's asks leave the muter's circle list, with the count in `hidden_muted` for the `/circle` empty state, but stay readable and answerable by id.
- **Privacy.** Mutes are exported and deleted (both directions) under `social.blocks`.

**Scheduled work.** `python -m brandme_core.domains.persona.jobs [--once]` closes due decisions and releases expired reservations. Media retention and benefit fulfillment report `not_configured`: the only media store is per-process memory, and no partner fulfiller exists.

**Evidence**
| Check | Result |
|---|---|
| This branch: all lane suites (`tests/test_{persona,wardrobe,social,rewards,media}_*.py`), emulator 1.5.28 | **197 passed, 10 skipped**. Every skip names its missing dependency: the privacy lane (8) or PR #47 worker + Pub/Sub emulator (2). |
| `main` 5174ec2 with this lane overlaid: lane suites + `tests/test_privacy*.py`, `test_rights*.py`, `test_read_api.py`, `tests/foundation/`. Real Pub/Sub emulator 0.8.37 via `PUBSUB_EMULATOR_BIN` | **482 passed, 0 skipped** |
| `tests/test_persona_lane_mydata.py` (overlay) | Real data in all five domains goes through `MyDataService`: inventory equals the foundation catalog; export passes the forbidden-content scan; freeze refuses persona, wardrobe, rewards and media writers; the receipt is all `deleted`; **an INFORMATION_SCHEMA scan finds no lane STRING/ARRAY/JSON column still containing the member id**. A restore from an older backup is re-deleted by tombstone reapply, and serving resumes. Mutation check: reverting the `target_ref` fix makes the scan fail. |
| `tests/test_persona_lane_events.py` (overlay, real Pub/Sub) | The foundation worker alone leaves lane events pending. The lane worker publishes them. The subscriber applies them once: 25 `first_owned_item` + 100 `meaningful_style_setup`. A republished event is `duplicate_delivery`. A sandbox-environment message is never acked or applied. A duplicate order observation through the subscriber *process* creates exactly one wardrobe item. Logs contain no member ids. |
| Gateway `vitest run src/routes/v1`; `tsc --noEmit`; eslint | **41 passed**; 0; 0 |
| Console on this branch: `tsc --noEmit`; `pnpm build` | 0; 0. The UI-lane swap type-checks: 0. |
| PR #52 CI on `efa1a25` | `check`, `regression`, Test Core, Test Gateway, Test Chain, Security Scan: success. Trivy: failure, see below. |

**Trivy.** It reports **70** alerts on every head (7 critical, 27 high, 29 medium, 7 low), not 30. `git diff 67327e4 HEAD` over every `package.json`, lockfile, `requirements*.txt`, `pyproject.toml` and Dockerfile is empty, so they come from foundation manifests. Per the plan, there was no in-lane dependency work.

**Measured, not fixed (foundation-owned).** After an account deletion, **20 `member_private` `OutboxEvents` rows still name the member** (aggregate id or payload). `main` has no outbox purge or redaction. See check-in Q9.

**Not done / honest limits**
- No real media object store, try-on provider or benefit fulfiller exists. Media sweepers cannot run outside the API process.
- BM-LOY-005's Firestore half is not built. Referral and research reward rules never settle.
- No dev seed script. Not needed for any evidence above.

## Credential manifest (founder authority, Ultra Plan)
| Name | Scope | Where stored | Created | Rotate |
|---|---|---|---|---|
| — | — | — | — | — |

**None created.** Every check above ran against local emulators: Spanner 1.5.28 and Google's Pub/Sub emulator 0.8.37, fetched by `main`'s pinned script with its published SHA256. No API key, service account, token or `.env` entry exists for this lane. Real integrations will need credentials (Q14). None is prod-scoped yet.

## Check-in packet — 2026-10-23
**(a) Evidence summary.**
- **PR #52** (`efa1a25`) is green except Trivy. Trivy's 70 alerts come from manifests identical to foundation `67327e4`.
- **Stages 2–8 are complete against the brief**, with the limits listed above. Persona, wardrobe, social (including mute and reports), rewards and the try-on server are built.
- **Test results:**
  - this branch: 197 passed / 10 named skips
  - with `main`'s privacy lane and outbox: 482 passed, 0 skipped
  - gateway: 41 vitest
  - console: builds here, and the shell swap is proven
- **Integration:** My Data registration and deletion with a zero-trace scan, plus real Pub/Sub delivery applied exactly once.
- **Found for other owners:** lane contracts outside the foundation worker allowlist, the unregistered commerce order contract, and outbox rows retaining deleted members' payloads.

**(b) Questions (default in bold; I build on the default until told otherwise).**

*Direction*
1. **Shell contract: enforce or retire?** **Enforce.** The consumer-ui `ConsolePageHeader` is the only page header. This lane swaps its adapter with the one-line re-export when the shell reaches the shared base, and commerce does the same. My adapter already matches props and markup exactly.
2. **PD-09 (extended).** Ratify the lane's endpoint additions (persona, wardrobe, social, rewards, media lists in stages 3–7, plus `/mutes`), with `target_member_id` as the request field for relationships, blocks and mutes? **Ratify; the contracts lane folds them into `packages/contracts`.**
3. **PD-10.** Share lifetime 5 min–365 d and at most 200 active shares per member? **Ratify.**
4. **PD-11.** A gone share (revoked/expired/removed) reached by a valid token or an authorized member answers 410 `share_unavailable` with `reason`; anything else is 404? **Ratify 410.** The 404 alternative is one constant.
5. **Mute semantics.** One-sided and private: it suppresses notifications and hides asks from the circle list, but they stay answerable by id, and the muted member never learns of it. Should mute also hide shares received and outfit proposals? **Ratify as built; no extension.**
6. **PD-05.** Should persona learning default to on, for in-app personalization evidence only? **Keep on, disclosed in onboarding.** Privacy review can flip it with one default.
7. **Retention after account deletion.** The lane keeps only `PersonaTombstones` (member id + time, so a racing job cannot recreate the profile) and anonymized moderation reports. **Ratify; review with privacy counsel before launch.**

*Integration & security*

8. **Outbox catalog.** How do the 36 lane contracts reach the outbox worker? **The foundation worker imports `brandme_core.domains.persona.lane` (one line).** I then delete `persona/outbox_worker.py`.
9. **Outbox retention.** `OutboxEvents` keep a deleted member's `member_private` payloads indefinitely (20 rows in the test). **Foundation purges delivered rows after a fixed window (proposal: 7 days), and the privacy lane redacts the subject's undelivered payloads at deletion.** The lane will not write to the foundation's table.
10. **`commerce.order.observed`.** It is not in a registered closed catalog, so it cannot be published and the wardrobe order path is not end-to-end. **Commerce registers it with the schema mirrored in `persona/ingress.py` `ORDER_OBSERVED_V1`;** my consumer copy then retires.
11. **PD-12 session scopes.** **Foundation first-party sessions grant `wardrobe:*`, `outfits:*`, `social:*`, `rewards:read`, `rewards:write`.** Agents never receive `social:write` or `rewards:write`.
12. **PD-07 / PD-18 auth transports.** **The gateway mints a short-lived, audience-bound internal JWT for gateway→Python. The console uses a server-side token exchange, not a shared cookie domain.**
13. **Lane subscription.** Ingress never acks rejections. **Infra provisions `brandme-<env>-consumer-lane` on the member_private topic** with:
    - a dead-letter topic after 5 attempts
    - 7-day retention
    - a subscriber identity holding `pubsub.subscriber` on that subscription only
14. **Credentials.** None exist. **The founder approves dev-only equivalents when each integration starts:**
    - a dev-project service account with subscriber rights on one subscription
    - a dev GCS bucket with a 24 h lifecycle for try-on media
    - no try-on provider key until a provider's terms pass review

    Each is logged in the manifest. Flag: provider and storage are inherently prod-facing.

*Scope & sequencing*

15. **Trivy (70 alerts).** **A separate dependency PR by the foundation/UI owners. PR #52 merges with Trivy accepted as pre-existing.**
16. **V002 replacement.** The lane's V002 replaces `main`'s stage-1 V002, which would cause a checksum mismatch on any persistent database. **No persistent DB has it: replace in place.** Otherwise I add a forward migration.
17. **Merge path.** PR #52 targets the bench base while `main` has moved (privacy, outbox, commerce, rights). **Merge `main` into the lane branch (no rebase), retarget PR #52 to `main`, and run the 482-test overlay suite in CI with the Pub/Sub emulator.**
18. **PD-19.** **The shell nav links `/rewards-disputes`; the folder does not move.**
19. **Media.** **Next lane build: a GCS-backed `MediaStore` (signed URLs, lifecycle, purge) on the dev bucket from Q14.** The try-on provider stays simulated until one is approved.
20. **BM-LOY-005 Firestore reward projection.** **Defer.** Serve rewards from Spanner and build the projection only when the foundation publishes its projection pattern.
21. **Referral and research reward rules.** No system emits them. **Drop them from the launch rule table and keep the rule ids reserved.**

**(c) Next build steps for the top three (Q1, Q8, Q17).**
- **Q1 shell contract**
  - *Enforce (default):* once the shell lands on the shared base, replace the adapter body with the re-export and run console `tsc`/`build` plus the 13-step browser smoke. Then remove the adapter comment block. Commerce follows the same recipe.
  - *Retire:* move the adapter to `components/ops/page-header.tsx` with lane-owned CSS, since shell classes may go, and add a test that each ops page renders exactly one `h1`.
  - *Keep optional (v1 §3 as is):* leave the adapter and add a markup snapshot test against the contract so drift is caught in CI.
- **Q8 outbox catalog**
  - *Foundation imports the lane module (default):* delete `persona/outbox_worker.py`, point the Pub/Sub test at `brandme_core.events.worker`, and add a test that all 36 lane contracts are in its allowlist.
  - *`OUTBOX_CATALOG_MODULES` env list:* keep `brandme_core.domains.persona.lane` as the stable module name and test the env path.
  - *A separate lane worker:* default its `OUTBOX_EVENT_TYPES` to lane types only, run it as its own Deployment, and add a test that it never claims foundation types.
- **Q17 merge path**
  - *Retarget to `main` (default):* merge `origin/main`, resolve V002 and persona overlaps in favour of the lane where `main` has stage-1 code, add the Pub/Sub emulator to the lane CI job, and retarget.
  - *Stay on bench; the integrator merges:* keep the overlay evidence current after each `main` move and do nothing else.
  - *Split the PR:* persona + wardrobe first, then social + rewards, then media + console. This is easier to review, but consumers wait on producers across PRs.

## Check-in rulings — 2026-10-23
The founder delegated all 21 questions to the lane ("use your best judgement on all questions"). Each is ruled as below. "Handoff" means the action belongs to another owner, and the lane does not edit their files.

| Q | Ruling | Owner / state |
|---|---|---|
| 1 | **Enforce the shell contract.** | consumer-ui publishes `@/components/console-page-header` to `main` (it is not there at 5174ec2). The lane then swaps its adapter in one line. Until then the ops pages render unstyled on `main`: the shell's `--bm-*` tokens and classes are absent, and inputs show no borders. They pass all 13 smoke steps (see Stage 10). |
| 2 | **PD-09 ratified.** | Handoff: the contracts lane adds the lane endpoints, `/mutes` and `target_member_id` to `packages/contracts`. `social.policy.RATIFICATION` is updated. |
| 3 | **PD-10 ratified** (5 min–365 d; 200 active shares). | Done (`social.policy`). |
| 4 | **PD-11 ratified** (410 `share_unavailable` with reason; 404 otherwise). | Done (`social.policy`). |
| 5 | **Mute ratified as built.** No extension to shares or proposals. | Done. |
| 6 | **PD-05: learning stays on.** This matches ch.03's `PersonaProfile` example (`learning_enabled: true`). | Handoff: the UI lane discloses it in onboarding. |
| 7 | **Retention after deletion ratified:** `PersonaTombstones` plus anonymized reports. | Open: privacy-counsel review before launch. |
| 8 | **The foundation worker imports `brandme_core.domains.persona.lane`.** | Handoff to foundation. The lane keeps `persona/outbox_worker.py` until that lands, then deletes it. |
| 9 | **Foundation purges delivered outbox rows after 7 days. The privacy lane redacts a deleted subject's undelivered `member_private` payloads.** | Handoff to foundation and privacy. **Launch-blocking for account deletion.** |
| 10 | **Commerce registers `commerce.order.observed@1`** as a closed contract mirroring `ORDER_OBSERVED_V1`. | Handoff to commerce. The lane retires its consumer copy when the registered contract exists. |
| 11 | **PD-12:** first-party sessions grant `wardrobe:*`, `outfits:*`, `social:*`, `rewards:read`, `rewards:write`. Agents never get `social:write` or `rewards:write`. | Handoff to foundation. |
| 12 | **PD-07:** the gateway mints a short-lived, audience-bound internal JWT. **PD-18:** the console uses a server-side token exchange. | Handoff to foundation and UI. |
| 13 | **Lane subscription spec:** `brandme-<env>-consumer-lane` on the member_private topic; dead letter after 5 attempts; 7-day retention; a subscriber identity with `pubsub.subscriber` on that subscription only. | Handoff to infra. |
| 14 | **Credentials: dev-only, created when an integration starts, each logged in the manifest.** No try-on provider key until a provider's terms pass review. | None needed yet; none created. |
| 15 | **Trivy:** a dependency PR by the owning lanes; PR #52 accepts the pre-existing alerts. | `main`'s dependency patch (#46) is now merged in; see Stage 10 for the count after the merge. |
| 16 | **V002 replaced in place.** No persistent database holds `main`'s stage-1 V002. | Done in the merge. |
| 17 | **Merge `main` into the lane branch (no rebase) and retarget PR #52 to `main`.** | Done in Stage 10. |
| 18 | **PD-19:** the shell nav links `/rewards-disputes`. | Handoff to the UI lane (no nav file on `main` yet). |
| 19 | **Next lane build: a GCS-backed `MediaStore`** (signed URLs, lifecycle, purge), developed against a local GCS emulator and then a dev bucket (Q14). | Lane, next. |
| 20 | **Defer the Firestore reward projection.** Rewards are read from Spanner. | Deferred. |
| 21 | **Unwired rules (referral, research) are not advertised.** Their ids stay reserved and refuse to settle. | Done: the member `rules` list holds only wired rules (tested). |

## Stage 10 — `main` merged in, PR #52 retargeted to `main` (Q17) — 2026-10-23
- **Merge.** `09ad4e1` merges `main` 5174ec2 into the lane branch (no rebase). Both the lane base `d839267` and foundation `67327e4` were already ancestors of `main`. There were no textual conflicts: the lane's V002 supersedes `main`'s stage-1 V002, and V003–V005 fill the gap before V006. PR #52 now targets `main`. Its diff is the lane's work only (110 files) and it reports mergeable/clean.
- **Semantic conflict found and fixed.** `main`'s dependency patch (#46) moved the console to **Next 15.5.28**. There, page `params`/`searchParams` and `cookies()`/`headers()` are async, so the ops pages failed `next build`. `315879c` awaits them; behaviour is unchanged.
- **Rulings applied in the lane** (`bce7514`): PD-09/10/11 are marked ratified in `social.policy`, and the member rules table lists only wired rules.

**Evidence on the merged tree (in place, not an overlay)**
| Check | Result |
|---|---|
| Lane suites + `test_privacy*`, `test_rights*`, `test_read_api`, `tests/foundation/` (Spanner emulator 1.5.28, real Pub/Sub emulator 0.8.37) | **482 passed, 0 skipped** |
| Gateway: full `vitest run`, `tsc --noEmit`, `eslint src` | **91 passed** (`main`'s + lane); 0; 0 |
| `pnpm install --frozen-lockfile`; `pnpm check` | 0; 0 (spec validator, contract/token drift, packages, gateway, python foundation, docs links) |
| `pnpm --filter @brandme/console build` (Next 15.5.28) | 0 after `315879c` (failed before it) |
| Browser smoke, this branch's console with no UI-lane overlay, `next start` + the lane's Python ops routers on the emulator | **13/13**. The pages render unstyled on `main`: shell tokens and classes are absent until consumer-ui lands (Q1). |
- **CI gate for the lane (Q17).** After the merge, `main`'s workflows replaced the bench-era `foundation.yml`; `main` dropped it at its W11 integration merge `2eac4d7`. `main`'s `test-core` runs only the foundation, privacy, rights and read-API suites, so nothing in CI ran this lane's Python tests. A new `test-consumer-domains` job in `ci-cd.yml` runs all five lane suites against the Spanner emulator 1.5.45 and the pinned Pub/Sub emulator, and `build-images` now waits on it. Reproduced locally with the job's exact command on 1.5.45: **207 passed, 1 skipped** (the spatial room manifests belong to another lane).
- **Trivy** is **green** on `17c7d9a` (0 new alerts). The 70 earlier alerts came from the bench-era manifests that `main`'s dependency patch (#46) replaced.
- **A real lane bug, caught by the new job.** Its first run failed 13 persona tests: `tests/fixtures/persona/catalog_candidates.json`, a fictional demo catalog, was matched by the repo-wide `.gitignore` `*.json` rule and had never been committed. Those tests passed only in working trees that already had the file, including the "207 passed" reproduction above, which ran in the working tree rather than a clean checkout. The fixture is now force-added. **Clean-checkout run (`git worktree add` of the fixed head, emulator 1.5.45, the job's exact command): 207 passed, 1 skipped.** Every earlier "this branch" result for those 13 persona tests carried the same blind spot.

## Stage 11 — re-merge after #53/#54, Codex review fixes — 2026-10-23/24
**Merge.** `main` at 48686d2 (#53 foundation round 2, #54, orchestration docs) is merged in by `588245b` and `7f7316e`, with no rebase.
- The only conflict was `.github/workflows/ci-cd.yml`, and both sides were kept. Foundation's Firestore-emulator and security-rules steps stay in `test-core`. `test-consumer-domains` follows it, and `build-images` still waits on it.
- Nothing else conflicted. Foundation's new `brandme_core/events/projections.py` registers no reducers for lane events, so there is no semantic overlap. It does unblock Q20, the Firestore reward projection.

**Codex review on `4b98472`: 12 findings, all verified as real and fixed with regression tests.**
| # | Finding | Fix |
|---|---|---|
| P1 | V002 edited in place (checksum drift) | V002 restored byte-identical to `main`. The persona member link (cascading FK, since Spanner cannot convert a table to interleaved) and its constraints open the reserved V003. A first attempt renumbered the lane files to V016–V019; the clean-checkout run caught that it breaks foundation's reservation registry, and `caa980e` reverts to V003–V005. `test_persona_migrations_upgrade.py` upgrades a database migrated to exactly `main`'s set, holding real persona data. |
| P1 | Media deletion dropped provider job refs, so providers kept copies | A reference-only job row stays until the provider confirms deletion after commit (retried on failure). Providers that cannot delete are reported in the receipt. |
| P1 | Deleting redemptions left points reserved | Pending reservations are released through ledger entries first. When the ledger is already deleted (account scope), nothing is recreated. |
| P1 | Debit correction bypassed the freeze | Every resolution checks `rewards.disputes`, and every correction checks `rewards.ledger`. |
| P1 | Deleting wardrobe items left outfit share previews | Deleting wardrobe items or outfits revokes those shares and drops their previews. **Persona snapshots had the same gap (not flagged by Codex) and are fixed the same way.** |
| P2 | Overlapping fulfillment workers could both deliver | A server-time lease is taken before the external call. Only the holder settles, and the expiry sweeper skips leased reservations. Fulfillers must still be idempotent on `reservation_id`, because a crash after delivery is retried after the lease. |
| P2 | Opened draft kept unreachable recipients in its audience | They are marked `removed`, and the privacy-freeze check now applies too. |
| P2 | Draft repeats computed at creation | Recomputed at send time, from previously sent requests only. |
| P2 | Proposal `base_version` "0" accepted | The version must be ≥ 1 and must exist. |
| P2 | Substitute items not ownership-checked | They get the same active, owner-only check as `item_refs`. |
| P2 | Failed dispatch kept the input photo | Every dispatch failure tombstones and purges the job's input immediately. |
| P2 | `persona.declared` deletion kept the learning switches | Both are turned off: a deletion never re-enables processing. |

**Open for foundation (migration ordering).** The registry reserves V003–V005 below `main`'s applied V006–V014. A database that applied `main` first can take them only with `--allow-out-of-order`, which the runner refuses in sandbox and production. The upgrade test pins this. No such database is known to exist; if one does, foundation must choose between allowing reserved gaps and renumbering the reservations. Commerce PR #51 adds a V015 that is not in the registry either.

**Evidence (clean `git worktree` of the pushed head, CI commands verbatim, Spanner emulator 1.5.45, Pub/Sub 0.8.37, Firestore emulator)**
| Check (head `caa980e`) | Result |
|---|---|
| `test-consumer-domains` command (lane suites) | **218 passed, 1 skipped** (spatial room manifests belong to another lane) |
| `test-core` command (`tests/foundation`, rights, privacy, read API, exports; `BRANDME_REQUIRE_EMULATORS=1`, Firestore and Pub/Sub up) | **292 passed** |
| `pnpm install --frozen-lockfile`; `pnpm check` | 0; 0. All 8 steps pass, with `BRANDME_PYTHON` pointed at a venv holding `datamodel-code-generator`: the contracts drift step needs it, and a fresh worktree has none. |
| `pnpm --filter @brandme/console build`; gateway `vitest run` | 0; **93 passed** |

**The clean checkout caught one more mistake before it shipped.** The first clean run (on `4964fe8`) failed `test_only_reserved_numbers_are_used`. That is what moved the files back to the reserved V003–V005 in `caa980e`. Everything else in that run passed.

**CI on `caa980e`.** Test Core, Gateway, Chain, regression, Durable Operation Store, Build Test, Trivy and one Security Scan job are green. **`Test Frontend` and the other `Security Scan` job fail on `pnpm audit --prod`:** 6 advisories published after `main`'s last green run (zod and body-parser in `brandme-chain`, fast-uri via `brandme-gateway>ajv`). The lockfile and manifests are byte-identical to `main`, so this does not come from this PR. A proposed override patch is in the PR comment. zod has no 3.x fix, so the chain lane must choose between a zod 4 migration and a documented exception. Per Q15, the dependency work stays with the owning lanes.

**Review threads.** All 12 Codex threads have a reply naming the fixing commit and are resolved.

## Stage 12 — `main` 47cdba7 (#58, foundation round 3) merged in — 2026-10-24
**Merge.** `a4f7ef0` merges `main` 47cdba7 with no rebase. The only conflict was `.github/workflows/ci-cd.yml`, and both sides were kept, as `docs/build/workspace-governance.md` directs. That gives two jobs: the lane's `test-consumer-domains` and foundation's new `foundation-check`. `build-images` needs both. Nothing else conflicted.

**Quarantine entries deleted (`tests/conftest.py`).** `main`'s new registry quarantined two lane blockers that this branch already fixes:
- **The `catalog_candidates.json` fixture** (12 recommender and service tests). It is committed with `git add -f`.
- **The `AbortOnceDB` retry test.** The harness raises `Aborted` with an `AbortCause` that has `trailing_metadata()`.

Under strict xfail both entries would XPASS and fail the run. Per the registry rule, this PR deletes them.

**The dependency blocker is cleared by #58.** Commit `123a069` pins zod 4.6.7 in `brandme-chain` and adds the `body-parser@1` 1.20.9 and `fast-uri@3` 3.1.9 overrides to `pnpm-workspace.yaml`. The lane changed no manifests.

**Note for foundation.** `main`'s `test-core` now runs every test under `tests/`, lane suites included. `test-consumer-domains` therefore repeats them in parallel, which costs no wall-clock time. It stays until foundation decides to drop it.

**Evidence (clean `git worktree` of `a4f7ef0`; CI commands verbatim; venv from the hashed lock; Spanner emulator 1.5.45 with REST, Pub/Sub 0.8.37, Firestore emulator)**
| Check | Result |
|---|---|
| `test-consumer-domains` command | **218 passed, 1 skipped** (allowlisted: spatial room manifests) |
| `test-core`: `pytest tests` with `BRANDME_REQUIRE_EMULATORS=1` | **787 passed, 4 allowlisted skips, 32 quarantined xfails (commerce-agents 15, unowned-legacy 17; consumer-domains 0)** |
| Firestore security rules | 6 pass, 0 fail, 0 skipped |
| `pnpm check` (`BRANDME_CHECK_SKIP_PYTHON=1`, as in CI) | 0; all 10 steps pass (workspace governance, credential manifest, contract drift, packages, gateway, docs links) |
| `pnpm smoke` | PASSED (gateway → brain → Spanner, restart persistence, outbox dispatch) |
| `pnpm audit --prod`; `--audit-level=critical` | no known vulnerabilities; 0 critical |
| frontend build | 0 |
| console build; gateway lint, type-check, vitest | covered by CI on this head (Build Docker Images (console), Test Gateway): both green |

**CI on `a4f7ef0`.** All 20 check runs succeed; Deploy to GKE (sandbox) is skipped, as on every PR. That includes Test Frontend, both Security Scan jobs, Foundation check, Test Core, Test Consumer Domains and the five image builds. `mergeable_state` is `clean`.

## Stage 13 — GCS media store on a local GCS emulator (ruling Q19) — 2026-10-24
PR #52 merged into `main` (`3d4cc0b`). This stage starts fresh from `main` on the same branch name.

**What ships (`brandme_core/domains/media/gcs_store.py`)**
- **`GcsMediaStore` implements `MediaStore` on a private bucket.** It speaks the JSON API through an authorized session and signs upload URLs with V4 (GOOG4-RSA-SHA256). It uses only `requests`, `google-auth` and `cryptography`, all already in the hashed lock, so the lock needs no recompile.
- **Upload URLs.** Path style, valid at most 15 minutes. Each URL signs:
  - `content-type`;
  - `x-goog-content-length-range: 0,<declared bytes>`;
  - `x-goog-if-generation-match: 0`, so uploads are create-only and a verified object cannot be swapped;
  - `x-goog-custom-time`.

  `complete_upload` still checks size, magic bytes and SHA-256 itself.
- **`stat`** hashes the bytes, because GCS reports only MD5/CRC32C. The download is pinned to the generation just read and checked against the object's MD5. An object over 10 MB is reported by size without being downloaded.
- **Lifecycle backstop.** Every object starts with `customTime` = creation time. The bucket rule `Delete if daysSinceCustomTime >= 2` catches anything the 24 h app sweeper missed.
  - `save_job` first calls the new `MediaStore.retain`, which moves the saved preview's `customTime` to 9999-12-31; GCS only allows moving it later.
  - Then the save commits. If storage is down, the save fails with a 503 and the preview stays unsaved and expiring. The bucket can never delete a saved preview.
- **Purge** is a JSON API delete. `bucket_findings` lists what would stop that delete from being final, and strict modes refuse to start on a bucket with any finding:
  - soft delete on, object versioning, or a retention policy or hold;
  - uniform access off, or public access prevention not enforced;
  - the backstop rule missing, or a lifecycle rule that could delete saved media;
  - no CORS `PUT` entry.
- **Selection: `from_environment`.**
  - `BRANDME_MEDIA_BUCKET` picks GCS.
  - `STORAGE_EMULATOR_HOST` picks the emulator. It is allowed in demo/development only, and a throwaway key signs the URLs there.
  - Otherwise Application Default Credentials are used. A key file signs locally; workload identity signs through IAM `signBlob`.
- **The jobs process** (`python -m brandme_core.domains.persona.jobs`) now sweeps unsaved media and retries purges whenever a bucket is configured. Without one it still reports `not_configured`.
- **Emulator.** fake-gcs-server 1.56.1, fetched by `scripts/python/fetch_gcs_emulator.py`. The SHA256 is the one published in the release's `checksums.txt`. Tests start it from `GCS_EMULATOR_BIN`, and CI fetches it in `test-core` and `test-consumer-domains`.

**Evidence (this branch, Spanner emulator 1.5.45, fake-gcs-server 1.56.1)**
| Check | Result |
|---|---|
| V4 signing vs Google's conformance vectors (`tests/fixtures/media/gcs_v4_signing_vectors.json`: 18 path-style `signingV4Tests`, Apache-2.0) | **18/18**: canonical request, string-to-sign and full URL match byte for byte. Google's expected signature verifies over our string-to-sign under the published dummy key's public half. The private key is not vendored. |
| Signing, bucket policy, environment selection and credential shapes (`test_media_gcs_signing.py`) | **25 passed** |
| Emulator suite (`test_media_gcs_store.py`, own migrated database) | **6 passed**: store contract; full try-on flow with every byte in the bucket (verify, dispatch, input deleted at processing end, result, save → retained, delete → object gone and `purged_at` set); oversize and type-spoofed uploads that the emulator accepts are still rejected and purged; save fails closed on a storage outage (503, unsaved); the jobs process sweeps unsaved media on the bucket; a default bucket is flagged unfit |
| Mutation checks | Removing the retain call fails 2 tests; inverting the MD5 check fails the flow test |
| Media, My Data and jobs suites with the `save_job` change | 49 passed |
| Trivy secret scan (pinned `aquasec/trivy:0.75.0`, `trivy-secret.yaml`, repo-wide) | 0 findings. On `6a81c26` it found 1 CRITICAL: a test built a service-account info dict around a key generated at runtime, and its key-type field matched Trivy's GCP service-account rule. The test now omits that unneeded field; no allow rule was added. |
| Clean `git worktree` of `6a81c26`, CI commands verbatim (fresh venv from the hashed lock; fake-gcs-server fetched by the script) | Lane suites **249 passed**, 1 allowlisted skip. `pytest tests` with `BRANDME_REQUIRE_EMULATORS=1`: **818 passed**, 4 allowlisted skips, 32 quarantined, none of them consumer-domains. No new skip: every GCS test ran. Firestore rules pass. `pnpm check` 0 (10 steps). `pnpm smoke` passed. `pnpm audit --prod` clean. Frontend and console builds 0. Gateway lint, type-check and 145 vitest pass. Later commits change only one test dict and this document; the secret scan covers them |

**Honest limits**
- **The emulator enforces none of the signed constraints.** It checks no signatures and ignores `x-goog-if-generation-match`, `x-goog-content-length-range` and `x-goog-custom-time` on the signed PUT. It also has no lifecycle execution and no soft delete. The emulator runs prove the object flow and the service's own checks, not GCS enforcement.
- **No dev-bucket run (Q14): NOT RUN.** This session's environment holds no valid GCP credential (the injected access token is rejected), so no bucket or service account was created. GCS's acceptance of `customTime` 9999-12-31 is part of what that run must confirm.
- **The `MediaService` HTTP API is still unmounted.** The API process does not yet build the store from the environment; only the jobs process does.

**Dev bucket the run needs** (dev project only; log it in the manifest when created). `check_bucket()` verifies each setting:
- uniform bucket-level access on, public access prevention enforced;
- soft delete off (retention 0) and object versioning off;
- no retention policy and no default event-based hold;
- lifecycle `{"rule":[{"action":{"type":"Delete"},"condition":{"daysSinceCustomTime":2}}]}` and no other delete rule;
- a CORS entry allowing `PUT` from the app origins whose `responseHeader` lists every signed upload header: `Content-Type`, `x-goog-content-length-range`, `x-goog-if-generation-match`, `x-goog-custom-time`. Without them the browser preflight fails.

The service account needs:
- object create, get, update and delete on that bucket only;
- `storage.buckets.get` for the policy check;
- under workload identity, `iam.serviceAccounts.signBlob` on itself. The store requests the `devstorage.read_write` and `iam` scopes.

**Codex review on `64cc4b1`: 5 findings, all verified as real and fixed with regression tests.** Each regression test fails when its fix is reverted.
| # | Finding | Fix |
|---|---|---|
| P1 | A client's unsigned `Content-Encoding: gzip` let a tiny upload expand in memory, because `requests` decodes it | Downloads ask for the stored bytes (`Accept-Encoding: gzip`, no decoding) and stream them with a hard 10 MB cap. `write` refuses objects over the cap. A local server playing real GCS (which keeps gzip uploads compressed) shows the store returns the stored bytes, which then fail the magic-byte check. On the emulator (which decompresses on write), the upload is rejected and a read stops at 10 MB. |
| P2 | Bucket CORS check accepted a `PUT` entry without the signed `x-goog-*` headers, so the browser preflight would fail | `bucket_findings` adds `cors_upload_headers_missing`. It checks the same header list `upload_target` signs. |
| P2 | ADC requested a storage-only scope, so `signBlob` fails on runtimes that honour requested scopes | Requests `devstorage.read_write` + `iam`; nothing broader. |
| P2 | An unexpired upload URL can recreate a purged input, because create-only succeeds again once the object is gone | Each store declares `replay_window`: GCS uses the URL lifetime plus 1 minute; the memory store uses 0, because its tokens are single use. `purge_pending` purges such inputs once more after the window, and the new `purged_at` makes the row final. Account deletion keeps those tombstoned inputs and reports the purge as pending until the window closes, then deletes the blob again and the rows. No schema change. Rows purged more than a day ago are left to the lifecycle backstop. |
| P2 | Retain ran before the save transaction could refuse, so a refused save left the preview without its backstop | The save's own checks (finished, unexpired, not frozen) run in a read before `retain`. Only a failed commit can still leave a retained but unsaved preview. That case is not reconciled durably: GCS cannot move `customTime` back, and a ledger would need a schema change. The app sweeper still deletes that preview at its expiry. |

After the fixes: `test_media_gcs_signing.py` **27 passed**, `test_media_gcs_store.py` **10 passed**.

**Credential manifest.** No credential was created in this stage.

**Handoffs (foundation)**
- `scripts/brandme.mjs` should treat `GCS_EMULATOR_BIN` the way it treats `PUBSUB_EMULATOR_BIN`, so `pnpm check` with `BRANDME_REQUIRE_EMULATORS=1` reports it up front. Today the skip fails inside pytest, with a clear reason.
- Fill in the `docs/build/security/lane-service-accounts.md` row "media bucket once GCS replaces MemoryMediaStore" with the roles above when the bucket is provisioned.

## Stage 14 — Ultra plan 02, item 1: lane routers mounted behind foundation auth — 2026-10-25
Ultra plan 02 (design-alignment stage) was uploaded by the founder on 2026-10-25, and the lane treats that upload as the trigger. Its header still says "DRAFT … not yet triggered", so the founder should confirm.
- **Source of the locked design.** The plan cites an "Oct 23 locked design" for Now/Flow/loyalty/visibility. That document is not in the repository or on any branch, so the plan's own text is the specification this lane builds to.
- **Branch.** The plan names `bench/opus-consumer-domains-20261005`. The lane keeps its designated `claude/opus-consumer-domains-1csp2g`, restarted from `main` `d5b993f` after #59 merged.

**What ships**
- **Gateway → domain hop (ruling Q12).** `brandme-gateway/src/services/domains.ts` signs one ES256 principal assertion per request, valid 30 s, with audience `brandme:consumer-domains` and a single-use `jti`. The member's cookie or token never leaves the gateway. Only router-built fields cross: method, path, query, JSON body, If-Match, Idempotency-Key, request id. Try-on result images come back as bytes; any other non-JSON reply is a 503, never relayed.
- **Verifier.** `brandme_core/domains/persona/assertion.py` checks key id and algorithm (ES256 only), issuer, audience, lifetime ≤ 60 s, currency, `jti` replay and environment. It mirrors the commerce lane's executor assertion. The service holds public keys only (`CONSUMER_DOMAIN_ASSERTION_JWKS`) and refuses a private JWK.
- **Domain service.** `python -m brandme_core.domains.persona.app` serves persona, wardrobe and outfits, social, decisions, shares, notifications, reports, rewards and benefits. With `BRANDME_MEDIA_BUCKET` set it also serves media and try-on. The `/ops` routers stay unmounted until the console has operator auth. It runs foundation's in-process boot guard as `consumer_domains`. That name is not yet in the audited inventory, so strict modes refuse it until foundation adds it.
- **Mount.** `routes/v1/index.ts` mounts the eight lane routers after the existing ones, behind `principalMiddleware` and its CSRF, origin and rate-limit checks. Unconfigured, every lane route answers 503.
- **Session scopes (ruling Q11 / PD-12).** First-party sessions now also carry `wardrobe:*`, `outfits:*`, `social:*`, `rewards:read` and `rewards:write`; this is a one-line edit in foundation's `middleware/session.ts`. Bearer clients still get only what their token grants. Without this scope edit, no lane route is reachable by a member.
- **Try-on provider selection.** `BRANDME_TRYON_PROVIDER` is unset by default, giving no provider. `simulated` selects the labelled stand-in in demo/development only and is refused in strict modes. The jobs process now also runs `dispatch_queued` and `collect_processing`.
- **Config and manifest.** New gateway fields: `CONSUMER_DOMAIN_SERVICE_URL`, `_ASSERTION_KEY`, `_ASSERTION_KID`. The manifest gains rows for the key and kid (status `active`, owner `dom`), and 8 consumer line numbers that the config insertion shifted are updated. The checker shows 0 errors and the same 14 warnings as `main`.

**Evidence (Spanner emulator 1.5.45, fake-gcs-server 1.56.1)**
| Check | Result |
|---|---|
| `consumer-domains.test.ts`: dev session → real gateway → domain service → Spanner + GCS emulator | **passed**. Unauthenticated → 401. Then: capabilities (simulated, labelled) → wardrobe item → signed upload to the bucket → complete (verified) → job (202) → jobs process dispatches and collects → result `image/png`, `private, no-store`, `generated_visual_preview_simulated` → save → delete → result 404. The service answers 401 to no assertion and to a forged one. |
| `domains.test.ts` (gateway client) | **4 passed**: claim set, 30 s lifetime, ES256 `kid`, only router-built headers, fresh `jti` per request, no assertion for anonymous calls, image passthrough, non-JSON → 503, unconfigured or unreachable → 503 |
| `test_persona_domain_app.py` | **6 passed**: valid assertion; replay, wrong issuer, unknown kid, foreign key, TTL > 60 s, expired, other environment, malformed scopes, wrong audience and HS256 all refused; private JWK refused; mounted app 401 → 200; media not mounted without a bucket; config refusals; simulated provider dev-only |
| Mutation checks | Removing the replay, lifetime or environment check each fails the refusal test |
| Gateway suite (type-check, lint, vitest) | 0 / 0 / **151 passed** (145 before + 4 client + 2 e2e) |

**Not yet**
- **No real provider or real bucket.** The try-on run uses the simulated provider and the GCS emulator. The dev-bucket run (item 11) still needs the founder's GCP credential.
- **No deployment wiring.** Helm and compose still lack the domain service and its key; that is foundation's.

## Stage 15 — Ultra plan 02, items 2–4: Now loop, Home = Flow, per-house loyalty standing — 2026-10-25
Built on PR #61 (the mount). Migration **V016** (`consumer_design`) is registered in `tests/foundation/test_migrations.py` `RESERVED`, after commerce's reserved V015.

**Now loop (item 2)**
- **Windows.** The asker picks 180, 300, 600 or 900 s, or gets the 300 s default. Values must be strict integers: `300.0` and `true` are refused. The asker may add a "why" of up to 280 characters, and the audience sees it. Constants live in `social/policy.py`; V016 replaces `ck_dec_duration` with `ck_dec_window`.
- **Comment thread** (`DecisionComments`):
  - creator and invited audience only;
  - in blind mode a recipient answers before reading or writing;
  - 20 comments per author per decision;
  - withdrawing a comment erases its text and leaves a placeholder;
  - the thread closes with the window;
  - comments can be reported (`decision_comment` target, console label added).
- **In-window rewards.** The existing `friend_decision_response` rule already pays only eligible, on-time answers; unchanged.
- **Influence credit** (`decision_influence`, lane extension **PD-20**): 25 points to each friend who said yes in-window (or named it as their alternative) when the asker then receives a **provider-observed delivery** of that catalog piece within 14 days of the close.
  - One credit per decision and friend, however many units arrive. Capped at 100/day.
  - A self-reported "I bought it" never pays, and neither do self, blocked or ineligible members.
- **Catalog check.** A catalog-product decision now needs a live catalog piece (`catalog_piece_exists`). It previously accepted any id.

**Home = Flow (item 3)** — `GET /api/v1/flow`
- **Position is freshness only.** First come friends' open requests addressed to the member, soonest-closing first, excluding muted and blocked friends. Then the newest pieces from followed houses and from houses of pieces in the closet, newest first, with cursor paging.
- **Size and depth come from excitement:** 0.6 × engagement + 0.4 × persona affinity.
  - Engagement counts Now decisions about the piece plus want-list saves in the last 7 days. Under 3 counts as none, and the scale saturates at 25.
  - Sizes: hero/standard/compact, depth 3/2/1. Each item states its reason, and no count is ever returned.
  - Catalog pieces carry no persona axes yet, so affinity is neutral today and size follows engagement.
- **The persona lens applies only the member's own constraints**: budget, brands, materials, categories and dismissed pieces. Stock is shown on the piece, not filtered.
- **Houses** (`MemberHouses`): `GET /houses` and `PUT`/`DELETE /houses/{house_ref}/follow`. `share_standing` is an opt-in, off by default. Only the member can follow or share, never an agent.
- **Catalog shim.** `social/houses.py` `CatalogHouses` reads the providers lane's `CatalogSourceVariants`, read-only. A house is a brand slug, and a piece is a variant.
- **Order reducer.** It now resolves pieces from that catalog, so order-acquired items carry `product_id` = `variant_id`. Before this, no catalog lookup was wired and order items had no product.

**Loyalty standing (item 4)** — `rewards/standing.py`
- **Computation.** The jobs process recomputes standings at most daily from verified, delivered, still-owned order units per house. Self-reported items are excluded by two independent filters.
- **Tiers:** `top_1`/`top_5`/`top_10`/`top_25`/`member`. A member's percentile is the share of the house's buyers with strictly more units, so ties share a tier.
- **Small cohorts:** under 20 buyers, everyone is `member`.
- **Storage:** only the tier is kept (`HouseStandings`), never units, spend or orders.
- **Members** read their own tiers (`GET /rewards/standings`).
- **What a house sees** (`house_view`, `provider:admin`; no route yet): per-tier counts, with counts under 5 suppressed, plus the tier of members who opted in for that house. Turning sharing off hides the member at once.
- **House rewards:** partner benefits with `house_ref` + `min_standing` are reservable only at or above that tier (`standing_required`). A V016 check constrains them to funded partner benefits.

**Privacy.** New categories `social.houses` and `rewards.standings`; `DecisionComments` joins `social.decisions` (export "commented", deleted by author). The My Data end-to-end now seeds and checks all three tables, and the zero-trace scan covers V016.

**Evidence (Spanner emulator 1.5.45)**
| Check | Result |
|---|---|
| `tests/test_social_now_flow.py` | **9 passed**: windows and why; catalog check; comment thread (answer-first, idempotent replay, withdrawal, cap, close); influence credit (yes paid once over 2 units and redelivery, pass/self/self-report unpaid); excitement sizing; Home = Flow (requests first, freshness order, lens, closet/followed houses, paging, mute, unfollow); tier boundaries; standing (ties, cohort, opt-in house view, suppression, return drops standing, daily gate); standing-gated house reward |
| `tests/test_persona_lane_mydata.py` | **2 passed** with comments, followed houses and standings seeded; export, deletion, zero-trace scan and restore re-apply |
| `consumer-domains.test.ts` (dev gateway → domain service → Spanner + GCS emulator) | **3 passed**. New scenario: two dev members befriend each other; asker follows a seeded house; 180 s Now request with a why cuts into the friend's Flow; friend answers and comments; asker's Flow lists the house's pieces newest first; a bogus catalog id gets 422; delivery observed → friend's ledger shows one 25-point `decision_influence`; jobs recompute → asker sees tier `member` (one buyer, below the cohort) |
| `flow.test.ts`, `social.test.ts` (gateway) | 3 + 10 passed: scopes, strict bodies, house-ref shape, agent refusal, window/why shapes, comment routes |
| Clean checkout of `8ff49c2`, CI mirror | lane 270 passed / 1 allowlisted skip; test-core 839 passed, 4 skipped, 32 xfailed (quarantined); rules 6; `pnpm check` and `pnpm smoke` passed; frontend and console builds; audit clean; gateway 156/156 |
| Mutation checks (13 Python, 2 gateway) | All killed except the two purchase filters on standings, each of which backs the other (removing both fails the test): opt-in filter on the house view, count suppression, small-cohort rule, pass earning credit, self-report paying, per-unit double credit, muted friend cutting in, engagement floor, `300.0` window, blind-mode comment, house reward without standing, discontinued catalog piece, agent following/sharing, gateway why check |

**Not yet**
- **No house operator principal**, so the house view has no route.
- **The catalog shim scans by brand without an index.** It needs a providers-lane read API or an index.
- **No experiment flags yet.** Foundation has no flag primitive (item 8).
- **Items 5–11** are next, on defaults.

**Credential manifest.** No credential was created in this stage. The e2e generates throwaway in-memory ES256 keys per run.

## Check-in packet — Ultra plan 02 — 2026-10-25
**Trigger reached:** Now, Flow and loyalty run against the dev gateway with the media API mounted (PR #61 plus this stage; `consumer-domains.test.ts`). The lane builds on every default the plan already states (its questions 1–21). The questions below are new: decisions the build surfaced. No step this round was irreversible or prod-scoped.

**(a) Evidence summary**
- **Item 1** (PR #61, green on all 17 checks): media and try-on, plus every lane router, sit behind foundation auth and the ES256 gateway assertion. Try-on runs end to end on the dev gateway.
- **Items 2–4** (Stage 15): timed windows with a why, the in-window thread, influence credit on provider-observed purchases, Home = Flow with freshness position and excitement size, and per-house standing in which houses see tiers only. Standing gates house rewards.
- **Not done:**
  - Items 5–8 and 10 are next, on defaults.
  - Item 9 waits on foundation's Q8 import.
  - Item 11 waits on the GCP credential; the emulator is used until then.

**(b) Questions (default in bold; I build on the default until told otherwise)**

*Direction*
1. **Locked design source.** The plan cites the "Oct 23 locked design", but no such document is in the repository. **The plan text is the spec until the document is supplied; anything it adds becomes a follow-up.**
2. **Now windows.** 180 / 300 / 600 / 900 s, with 300 as the default and strict integers only. **Keep.**
3. **Influence credit.** 25 points, 100/day, a 14-day window, yes or a named alternative only, and only on a provider-observed delivery. It implies to the friend that the asker bought the piece, although the ledger entry names only the decision the friend already saw. **Keep as built. Privacy review decides whether the buyer gets a "credit friends who helped" setting (default on).**
4. **Excitement weights.** 0.6 engagement / 0.4 affinity, a floor of 3, saturation at 25, and hero/standard/compact cut-offs at 0.75/0.4. Catalog pieces have no persona axes, so size follows engagement today. **Keep until catalog axes exist.**
5. **What standing ranks.** Verified delivered units, not spend. The percentile counts buyers with strictly more units, so ties share a tier. **Units.** Spend would need commerce's order amounts and expose more.
6. **What a house sees.** Opted-in members' tiers (sharing is off by default) plus per-tier counts, with counts under 5 suppressed and no ranking under 20 buyers. **Keep these privacy floors.**
7. **Flow and stock.** Out-of-stock pieces stay in Flow with their availability shown; the lens applies only the member's own constraints. **Keep.**

*Integration & security*

8. **Foundation-owned edits in PRs #61 and Stage 15.** The `middleware/session.ts` scope line, the mount block in `routes/v1/index.ts`, and the V016 entry in the migration registry. **Foundation ratifies as is.**
9. **Migration order.** V016 must not reach a database before commerce's V015 (PR #51): the runner then refuses V015 as out of order. **This PR stays a draft until #51 merges; then `main` is merged in. If #51 slips past this PR, commerce renumbers to V017.**
10. **House operator principal.** No house role exists, so `house_view` requires `provider:admin` and has no route. **No route until foundation defines a house-operator principal bound to one `house_ref`.**
11. **Catalog dependency.** Flow, standing and the decision check read the providers lane's `CatalogSourceVariants` directly. It is read-only, scans by brand without an index, and treats a piece as a variant. **Interim. The commerce/providers lane publishes a catalog read API, or an index on the brand slug, and a product identity; this lane switches over.**
12. **Boot inventory.** The `consumer_domains` service is not in foundation's audited inventory, so strict modes refuse it. **Foundation adds it after reviewing PR #61.**
13. **Experiment flags (item 8).** Foundation has no flag primitive. **The lane defines the five experiments as data, with a resolver that always answers "off" until the primitive lands. Nothing runs without founder approval.**
14. **Cross-member aggregates.** Flow's engagement counts other members' decisions and saves, and standing ranks members against each other. Both expose only sizes or tiers, with the floors above. **Keep; privacy review confirms before launch.**

*Scope & sequencing*

15. **Plan status.** The upload's header still reads "DRAFT … not yet triggered". **Treated as triggered by the upload; confirm.**
16. **Branch.** The plan names `bench/opus-consumer-domains-20261005`. **The lane keeps its designated `claude/opus-consumer-domains-1csp2g`.**
17. **PR split.** #61 (mount) first, then this stage, then one PR per item group. **Keep; each PR verified from a clean checkout before push.**
18. **Item 9.** Worker deletion is blocked until foundation imports the lane catalog (Q8). **Wait; delete in that PR.**
19. **Item 11.** No GCP credential exists. **Emulator only, stated plainly. The real run happens the day the credential lands.**
20. **Next order.** Surveys and points → in-app credit (5), persona card and per-piece visibility (6), rooms (7), experiment definitions (8), then the share projector (10). **That order.**
21. **Surveys.** The plan says daily-capped surveys feed points. The contract's `optional_research_contribution` has no compensation and stays reserved for consented research campaigns. **A lane extension rule `survey_completed` (PD-21): 10 points per completed survey or quiz, at most 30 a day. Points convert to in-app credit only, enforced at the ledger with no cash-out path. Questions are operator-authored, never about sensitive categories, and answers stay in the member's own data.**

## Stage 16 — Ultra plan 02, items 5–8 and 10: surveys and in-app credit, persona card and closet visibility, rooms, experiments, share projector — 2026-10-25
Built on the check-in defaults (packet above), without waiting for answers. Every table is in V016, which is still unmerged. Commerce's V015 merged first (#51), so the out-of-order hazard in Q9 has cleared.

**Base.** The designated branch was restarted from `main` `2b5ae88`, after #61 (the mount), #51 (commerce, V015) and #56 (consumer UI) merged, and this stage's commits were re-applied on top. The only conflict was the migration registry, which now lists both V015 and V016. #56 touched this lane's `wardrobe/rooms.py` and its tests (`cccfe7b`, room revisions aligned with the spatial manifests); that change is kept as is.

**Surveys and in-app credit (item 5)**
- **Surveys and quizzes** (`rewards/surveys.py`, `Surveys`, `SurveyResponses`) are operator-authored (`moderation:admin`).
  - A survey has 1–10 questions (single, multi or 1–5 scale) and a declared purpose: style, product feedback or house knowledge.
  - A quiz has a key for each question, sent only after the member answers, together with the score.
  - Each member answers once, every question, and only the member can answer, never an agent.
  - `survey_completed` (lane extension **PD-21**) pays 10 points, capped at 30 per UTC day. The fourth completion of a day is recorded as `capped` with 0 points.
  - Answers stay in the member's own data.
- **Points → in-app credit only** (`rewards/credits.py`, `PurchaseCredits`).
  - The member converts whole hundreds of points, at least 500, at `RATES`. The dev default is 1 point = 1 US cent.
  - Conversion writes a `reserve` entry. Applying credit to an in-app order (`apply_credit`, for commerce to call inside its order transaction) writes `redeem`. Expiry after a year writes `release`, and the points come back.
  - The ledger has no entry kind that pays out (V005 `ck_re_kind`), no member route takes money, a destination or another member, and a credit cannot move between members.

**Persona card and closet visibility (item 6)**
- **Per-piece closet visibility** (`wardrobe/visibility.py`) is private by default, with a sliding scale.
  - Audience: `friends` or `members`.
  - Detail: `piece`, `story` (adds the showcase note and wear count) or `full` (adds price and the year acquired, friends only).
  - Strangers never see more than the story: the locked disclosure default.
  - Receipts, order and source references, tag serials, sizes, care and private notes are never shown.
  - Routes: `PUT /wardrobe/items/{id}/visibility` and `GET /members/{id}/closet`.
- **The living persona card** (`persona/card.py`, `PersonaCards`).
  - It shows up to three strongest leanings (never a hidden, unanswered or mid-band axis), badges held, standing tiers (only when the member turns that on) and up to six highlights. Each highlight shows only if that piece's own visibility allows the viewer.
  - Audience: `private`, `friends` (the default) or `members`. A card the viewer may not see answers 404.
  - Recomposition: trigger events (`persona.updated`, `badge.awarded`/`revoked`, `wardrobe.item.created`/`updated`, standings recompute) mark the card stale through a second consumer on the lane subscriber. The jobs pass recomposes stale cards and backfills every card daily, creating cards for profiles that have none.

**Small-group rooms (item 7)** — `social/rooms.py`
- **Membership.** Rooms are invite-only among the owner's friends, at most 12 people, and invisible to outsiders.
- **Content.** Members post pieces (their own closet item or a live catalog piece) or notes, and react yes/maybe/no (one reaction each, changeable).
  - Authors withdraw their own posts.
  - Posts can be reported (`room_post`); moderation removes their content.
- **Blocking wins inside a room**, and the owner cannot add a blocked pair.
- **Lifecycle.** Members can leave and the owner can remove anyone. The owner archives a room, which leaves it read-only.
- **Routes:** `/rooms…`, under `social:*`, member-only.

**Experiments (item 8)** — `persona/experiments.py`
- **Five definitions:** closet memory, curator verbosity, the reveal, visitor traces and decision-thread persistence. Each has a question, arms, a default (today's behaviour), the built arms, its wiring point, metrics and guardrails.
- **The flag.** `arm()` answers the default unless the founder approved that exact definition version **and** foundation's flag primitive is installed. Neither has happened, so nothing runs.
- **Wiring.** Two experiments read their flag in code: verbosity in recommendations, thread persistence in decision comments. The other three have only the default built, so they cannot run until their second arm exists.

**Share projector (item 10)** — `social/projection.py`
- **Reducers.** `share.created` writes one shared Firestore document per invited member, holding only the kind and the filtered preview, read from Spanner rather than from the event. `share.revoked` deletes every copy and tombstones the share permanently.
- **Privacy.** Fields that the framework treats as private (persona axes and the rest) never reach the projection. Link shares are not projected.
- **Registration.** Exposed as `persona/lane.register_consumer_projections(database, registry)` for foundation's projection worker.

**Fixes found along the way**
- **Gateway report targets.** The gateway's report map lacked `decision_comment` (Stage 15), so comment reports were refused at the edge. Both new targets are now in.
- **Deletion ordering.** During deletion, a credit row had a buffered update and a DML delete in the same transaction. The release now leaves the row alone.
- **Commit-timestamp option.** `PurchaseCredits.settled_at` gained the `allow_commit_timestamp` option.

**Privacy.** New categories:
- `rewards.surveys`, `rewards.credits` (held points are returned before deletion), `persona.card` and `social.rooms`. Rooms a member owns close with their account.
- Item visibility and showcase notes join `wardrobe.items`.
- The My Data end-to-end seeds all of them and passes the zero-trace scan.

**Evidence (Spanner emulator 1.5.45, Firestore emulator, fake-gcs-server 1.56.1)**
| Check | Result |
|---|---|
| `tests/test_rewards_surveys_credits.py` | **4 passed**: survey authoring rules; answer once, complete, member-only, idempotent; quiz key only after answering; fourth daily completion `capped` at 0; conversion rules (whole hundreds ≥ 500, USD only, no extra fields, member-only, idempotent); reserve → redeem once in its own currency → release on expiry with points back; no payout kind in the ledger, no payout/cash/transfer route |
| `tests/test_persona_card_visibility.py` | **2 passed**: private by default; friends see `full`, strangers at most `story`, blocked members nothing; private fields never shown; card taste never shows hidden or mid-band axes; highlights obey piece visibility; audience and standings opt-in honoured; a trigger event marks the card stale, the jobs pass recomposes it; the backfill creates missing cards |
| `tests/test_social_rooms.py` | **2 passed**: friends only, owner-only adds, outsiders get 404, reactions counted and changeable, blocking hides posts and reactions, reports and moderation removal, author withdrawal, the owner cannot leave, archive is read-only, 12-person cap |
| `tests/test_persona_experiments.py` | **3 passed**: five definitions, nothing approved or running; only an approved current version with the primitive assigns, and only built arms; the wired thread-persistence flag changes behaviour only when approved and assigned |
| `tests/test_social_share_projection.py` | **1 passed**: per-recipient copies; uninvited members get none; link shares are not projected; persona axes dropped from a snapshot share; revocation removes copies and blocks a late re-projection |
| `tests/test_persona_lane_mydata.py` | **2 passed** with surveys, credit, the card, a shown piece and rooms seeded; export, deletion, zero-trace scan, restore re-apply |
| `consumer-domains.test.ts` (dev gateway → domain service → emulators) | **4 passed**. New scenario: a piece shown to friends at story level (stranger sees nothing); the card shows the Expressive leaning and the highlight to a friend, and answers 404 to a stranger; survey answered for 10 points; points converted to $5.00 in-app credit, held as reserved; a payout field is refused |
| Gateway unit | `members.test.ts` 3, `rooms.test.ts` 2, `rewards.test.ts` 7, `social.test.ts` 10; lint and type-check clean |
| Mutation checks (29) | All killed. Survey: key leak, partial answers, float scale, agent answering, no daily cap, undeclared purpose. Credit: odd amounts, agent converting, wrong currency, double apply, expiry keeping points. Visibility: stranger price, blocked viewer, price at story level. Card: private highlight, hidden axis, audience ignored, standings without opt-in, trigger not marking stale. Projector: persona axes in the projection; a link share is stopped by two independent guards (both removed: killed). Rooms: non-friend added, outsider reading, blocked author visible, over 12, member adding people, posting to an archived room. Experiments: unapproved run, unbuilt arm served |
| Clean checkout of the final code, `068001d` on `main` `2b5ae88` (#51, #56, #61, #65), CI mirror | lane **283 passed** (the spatial-manifest check now runs); test-core **1769 passed**, 20 skipped, 17 xfailed (quarantined); rules; `pnpm check`; `pnpm smoke` PASSED; frontend and console builds; audit; gateway **180/180**. Trivy (pinned 0.75.0) on `29913cb`: 0 findings |

**Not yet**
- **Item 9 (worker deletion)** is blocked. Foundation's `brandme_core/events/worker.py` on `main` still imports only `brandme_core.domains.events`, not the lane catalog (Q8). The lane worker stays.
- **Item 11 (dev bucket)** has no GCP credential; the emulator is used, stated plainly.
- **Experiments:**
  - Foundation has no flag primitive.
  - No definition is approved.
  - Three experiments (diary, reveal pause, visitor signals) have only today's arm built.
- **Credit is issuable but not yet spendable.** The commerce checkout has to call `apply_credit` first.
- **The share projector is registered, not running.** No foundation projection worker in the repository applies a registry yet.
- **No console pages for surveys or rooms.** Survey publishing and room moderation are in the ops router, which stays unmounted until the console has operator auth.
- **The credit rate is a dev default** (1 point = 1 US cent, USD only). The founder sets the real rate.

**Found for another owner (commerce)**
- **What fails.** `tests/test_commerce_payments_flow.py::test_payment_identifiers_never_reach_models_events_or_wires` failed once on the combined run.
- **Why.** The flagged payload holds only UUIDs and a `sha256:` hex digest. The providers lane's `contains_card_number` (`brandme_core/domains/providers/redaction.py:82`) treats a 13+ digit run inside a hex digest as a card number when it passes the Luhn check. Measured on 2,000 random payloads of the same shape: 0.75% flagged.
- **Whose.** The detector and test came with #51, so `main` carries it and any CI run can hit it at random. This lane does not touch commerce code.
- **Proposed patch (commerce lane).** Leave digit runs inside 64-character hex digests intact, as `_card_spans` already does for UUIDs.

**Ultra plan 02 exit evidence**
| Required | State | Where |
|---|---|---|
| MediaService API mounted behind auth; try-on end to end on the dev gateway | done | PR #61, Stage 14 |
| Now loop on dev: timed windows, in-window rewards, influence credit, with tests | done | Stage 15 |
| Flow ranking with the specified semantics; Home = Flow demonstrated | done | Stage 15 |
| Loyalty standing per house; houses see standing only, asserted by a test | done | Stage 15 (`house_view` equality: tiers, suppressed counts and opted-in members, nothing else) |
| Surveys/quizzes daily-capped, feeding points; points → credit in-app only | done | this stage |
| Persona card recomposing; per-piece visibility controls live | done | this stage |
| Five experiment definitions written and flag-wired; none running without approval | done | this stage |
| Lane outbox worker deleted post-Q8; share projector registered | projector done; worker blocked on Q8 | this stage |
| Dev-bucket run recorded, or emulator-only status stated | emulator only, stated | Stage 14 and here |

**Credential manifest.** No credential was created in this stage.
