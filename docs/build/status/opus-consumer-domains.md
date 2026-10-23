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
