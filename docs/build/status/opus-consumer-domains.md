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
