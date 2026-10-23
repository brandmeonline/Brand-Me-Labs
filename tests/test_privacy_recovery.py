"""Privacy failure/retry cases against real Spanner transactions (no provider credentials)."""
from datetime import timedelta

import pytest
from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

from brandme_core.domains.privacy.deletion import DeletionOutcome, PrivacyRegistry, PrivacyRegistryError, ProcessingFrozenError
from brandme_core.domains.privacy.privacy import ExportFailed, ForbiddenExportContent, RestoreNotServing
from brandme_core.events.outbox import json_payload
from tests.test_privacy import database, setup, now, _emulator_up  # noqa: F401 fixtures

pytestmark = pytest.mark.skipif(not _emulator_up(), reason="Spanner emulator not running")


def read(db, sql):
    with db.snapshot() as snap:
        return list(snap.execute_sql(sql))


@pytest.mark.parametrize("categories", [[], ["persona.declared", "persona.declared"], ["missing.category"]])
def test_invalid_category_selection_creates_no_jobs_or_freezes(setup, categories):
    svc, _, _, _, db = setup
    for method in (svc.export, svc.request_deletion):
        with pytest.raises((ValueError, PrivacyRegistryError)):
            method("member", now(), categories)
    for table in ("ExportJobs", "DeletionJobs", "ProcessingFreezes", "OutboxEvents"):
        assert read(db, f"SELECT COUNT(*) FROM {table}") == [[0]]


def test_empty_registry_cannot_report_account_export_or_deletion(setup):
    svc, *_ = setup
    svc.reg = PrivacyRegistry()
    for method in (svc.export, svc.request_deletion):
        with pytest.raises(ValueError):
            method("member", now())


@pytest.mark.parametrize("key", ["holderSecret", "privateKey", "access-token", "SEED_PHRASE", "paymentCredential"])
def test_export_rejects_secret_aliases_and_records_failure(setup, monkeypatch, key):
    svc, persona, _, _, db = setup
    original = persona.export
    def leaking(*args):
        section = original(*args)
        section.records = [{"nested": [{key: "NEVER_EXPORT_THIS"}]}]
        return section
    monkeypatch.setattr(persona, "export", leaking)
    with pytest.raises(ForbiddenExportContent) as error:
        svc.export("member", now())
    assert "NEVER_EXPORT_THIS" not in str(error.value)
    row = read(db, "SELECT state, manifest_json, package_ref FROM ExportJobs")[0]
    assert row[0] == "failed" and row[2] is None
    assert json_payload(row[1]) == {"error": "export_failed", "cleanup": "not_needed"}
    assert not svc.store.objects


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_partial_storage_upload_failure_is_redacted_and_cleanup_truthful(setup, monkeypatch, cleanup_fails):
    svc, _, _, _, db = setup
    original = svc.store.put
    def upload(key, data, content_type):
        original(key, data, content_type)
        raise ConnectionError("provider?token=NEVER_LOG_THIS private body")
    monkeypatch.setattr(svc.store, "put", upload)
    if cleanup_fails:
        monkeypatch.setattr(svc.store, "delete", lambda _: (_ for _ in ()).throw(ConnectionError("NEVER_LOG_THIS")))
    with pytest.raises(ExportFailed, match="^export_failed$") as error:
        svc.export("sensitive/member/path", now())
    assert "NEVER_LOG_THIS" not in str(error.value)
    state, manifest, ref = read(db, "SELECT state, manifest_json, package_ref FROM ExportJobs")[0]
    assert state == "failed" and ref is None
    assert json_payload(manifest)["cleanup"] == ("required" if cleanup_fails else "confirmed")
    assert bool(svc.store.objects) == cleanup_fails
    assert all("sensitive" not in key for key in svc.store.objects)


def test_lost_finalization_ack_does_not_delete_committed_export(setup, monkeypatch):
    svc, _, _, _, db = setup
    batch_factory = db.batch
    class LostAck:
        def __init__(self):
            self.checkout = batch_factory()
            self.finalizing = False
        def __enter__(self):
            self.batch = self.checkout.__enter__()
            return self
        def __getattr__(self, name):
            return getattr(self.batch, name)
        def update(self, table, columns, values):
            self.finalizing |= table == "ExportJobs" and values[0][1] == "ready"
            self.batch.update(table, columns, values)
        def __exit__(self, *args):
            self.checkout.__exit__(*args)
            if self.finalizing:
                raise ConnectionError("commit acknowledged by database, response lost")
    monkeypatch.setattr(db, "batch", LostAck)
    with pytest.raises(ExportFailed, match="export_finalization_unconfirmed"):
        svc.export("member", now())
    state, ref = read(db, "SELECT state, package_ref FROM ExportJobs")[0]
    assert state == "ready" and ref.removeprefix("mem://") in svc.store.objects


def test_newer_deletion_finishing_first_keeps_freeze_until_older_finishes(setup):
    svc, _, _, _, db = setup
    older = svc.request_deletion("overlap", now(), ["persona.declared"])
    newer = svc.request_deletion("overlap", now(), ["persona.declared"])
    first = svc.run_deletion(newer)
    assert first["processing"].startswith("Frozen:")
    assert read(db, "SELECT COUNT(*) FROM ProcessingFreezes") == [[1]]
    second = svc.run_deletion(older)
    assert "may resume" in second["processing"]
    assert read(db, "SELECT COUNT(*) FROM ProcessingFreezes") == [[0]]
    assert svc.run_deletion(newer) == first  # historical receipt remains immutable
    assert read(db, "SELECT COUNT(*) FROM OutboxEvents") == [[4]]


def test_disjoint_category_job_does_not_prevent_unrelated_unfreeze(setup):
    svc, _, _, _, db = setup
    svc.request_deletion("member", now(), ["persona.inferred"])
    job = svc.request_deletion("member", now(), ["persona.declared"])
    assert "may resume" in svc.run_deletion(job)["processing"]
    assert read(db, "SELECT category FROM ProcessingFreezes") == [["persona.inferred"]]


@pytest.mark.parametrize("reason", ["restriction", "consent_revoked"])
def test_deletion_preserves_independent_processing_restriction(setup, reason):
    svc, _, _, _, db = setup
    with db.batch() as batch:
        batch.insert("ProcessingFreezes", ["subject_ref", "category", "reason", "created_at"],
                     [["member", "persona.declared", reason, COMMIT_TIMESTAMP]])
    receipt = svc.run_deletion(svc.request_deletion("member", now(), ["persona.declared"]))
    assert receipt["processing"].startswith("Frozen:")
    assert read(db, "SELECT reason, deletion_job_id FROM ProcessingFreezes") == [[reason, None]]


def test_failed_overlapping_job_still_blocks_processing(setup):
    svc, _, _, _, db = setup
    old = svc.request_deletion("member", now(), ["persona.declared"])
    with db.batch() as batch:
        batch.update("DeletionJobs", ["job_id", "state"], [[old, "failed"]])
    job = svc.request_deletion("member", now(), ["persona.declared"])
    assert svc.run_deletion(job)["processing"].startswith("Frozen:")
    assert read(db, "SELECT COUNT(*) FROM ProcessingFreezes") == [[1]]


@pytest.mark.parametrize("account", [False, True])
def test_lifting_independent_restriction_cannot_lift_deletion_barrier(setup, account):
    svc, persona, _, _, db = setup
    category = "*" if account else "persona.inferred"
    with db.batch() as batch:
        batch.insert("ProcessingFreezes", ["subject_ref", "category", "reason", "created_at"],
                     [["member", category, "restriction", COMMIT_TIMESTAMP]])
    job = svc.request_deletion("member", now(), None if account else [category])
    db.run_in_transaction(lambda tx: tx.execute_update("DELETE FROM ProcessingFreezes WHERE reason = 'restriction'"))
    with pytest.raises(ProcessingFrozenError, match="deletion request"):
        persona.write_inference(db, "member", "warm_cold", .5, basis_time=now())
    svc.run_deletion(job)
    if account:
        with pytest.raises(ProcessingFrozenError, match="deletion request"):
            persona.write_inference(db, "member", "warm_cold", .5, basis_time=now())
        followup = svc.request_deletion("member", now(), ["persona.inferred"])
        assert svc.run_deletion(followup)["processing"].startswith("Frozen:")
    else:
        persona.write_inference(db, "member", "warm_cold", .5, basis_time=now() + timedelta(seconds=1))


def test_partial_record_count_survives_retry_and_pending_exception_never_completes(setup, monkeypatch):
    svc, persona, _, _, db = setup
    persona.declare(db, "member", "warm_cold", .5)
    job = svc.request_deletion("member", now(), ["persona.declared"])
    delete, purge = persona.delete, persona.purge_derived
    def partial(tx, ctx, category):
        result = delete(tx, ctx, category)
        result.done, result.exception = False, "provider cleanup pending"
        return result
    monkeypatch.setattr(persona, "delete", partial)
    monkeypatch.setattr(persona, "purge_derived", lambda *_: pytest.fail("cannot purge before records finish"))
    receipt = svc.run_deletion(job)
    assert receipt["completed_at"] is None
    assert receipt["categories"]["persona.declared"]["rows_affected"] == 1
    assert receipt["categories"]["persona.declared"]["status"] == "pending_records"
    assert read(db, "SELECT COUNT(*) FROM ProcessingFreezes") == [[1]]
    monkeypatch.setattr(persona, "delete", delete)
    monkeypatch.setattr(persona, "purge_derived", purge)
    final = svc.run_deletion(job)
    assert final["categories"]["persona.declared"]["rows_affected"] == 1
    assert final["completed_at"] is not None


def test_terminal_record_exception_and_counts_survive_derived_retry(setup, monkeypatch):
    svc, persona, _, _, db = setup
    job = svc.request_deletion("member", now(), ["persona.declared"])
    monkeypatch.setattr(persona, "delete", lambda tx, ctx, key: DeletionOutcome(key, 3, exception="manual review required"))
    monkeypatch.setattr(persona, "purge_derived", lambda ctx, key: DeletionOutcome(key, 1, done=False))
    assert svc.run_deletion(job)["completed_at"] is None
    monkeypatch.setattr(persona, "delete", lambda *_: pytest.fail("completed record step was repeated"))
    monkeypatch.setattr(persona, "purge_derived", lambda ctx, key: DeletionOutcome(key, 2))
    final = svc.run_deletion(job)
    category = final["categories"]["persona.declared"]
    assert category["rows_affected"] == category["derived_purged"] == 3
    assert category["status"] == "exception" and category["reason"] == "manual review required"
    assert read(db, "SELECT state FROM DeletionJobs") == [["completed_with_exceptions"]]


def test_legacy_ambiguous_exception_step_is_rechecked_before_completion(setup, monkeypatch):
    svc, persona, _, _, db = setup
    job = svc.request_deletion("member", now(), ["persona.declared"])
    with db.batch() as batch:
        batch.update("DeletionSteps", ["job_id", "category", "step", "state", "rows_affected", "detail"],
                     [[job, "persona.declared", "delete_records", "exception", 2, "cleanup pending"]])
    monkeypatch.setattr(persona, "delete", lambda tx, ctx, key: DeletionOutcome(key, 0, done=False))
    receipt = svc.run_deletion(job)
    assert receipt["completed_at"] is None
    assert receipt["categories"]["persona.declared"]["status"] == "pending_records"
    assert receipt["categories"]["persona.declared"]["rows_affected"] == 2
    assert read(db, "SELECT COUNT(*) FROM ProcessingFreezes") == [[1]]


@pytest.mark.parametrize("outcome", [DeletionOutcome("wrong.category", 1), DeletionOutcome("persona.declared", -1),
                                    DeletionOutcome("persona.declared", True), DeletionOutcome("persona.declared", 1, done="yes")])
def test_invalid_handler_outcome_rolls_back_record_deletion(setup, monkeypatch, outcome):
    svc, persona, _, _, db = setup
    persona.declare(db, "member", "warm_cold", .5)
    job = svc.request_deletion("member", now(), ["persona.declared"])
    delete = persona.delete
    def invalid(tx, ctx, key):
        delete(tx, ctx, key)
        return outcome
    monkeypatch.setattr(persona, "delete", invalid)
    with pytest.raises(ValueError, match="invalid privacy handler"):
        svc.run_deletion(job)
    assert persona.count(db, "member") == 1
    assert read(db, "SELECT COUNT(*) FROM DeletionTombstones") == [[0]]
    assert read(db, "SELECT COUNT(*) FROM OutboxEvents") == [[1]]


def make_restore(setup):
    svc, persona, projections, _, db = setup
    job = svc.request_deletion("restore-member", now(), ["persona.declared"])
    svc.run_deletion(job)
    persona.declare(db, "restore-member", "warm_cold", .5)
    return svc, persona, projections, db, job


@pytest.mark.parametrize("outcome", [DeletionOutcome("persona.declared", 0, done=False),
                                    DeletionOutcome("persona.declared", 0, exception="provider refused")])
def test_restore_remains_blocked_until_derived_cleanup_resumes(setup, monkeypatch, outcome):
    svc, persona, projections, db, job = make_restore(setup)
    purge = persona.purge_derived
    monkeypatch.setattr(persona, "purge_derived", lambda *_: outcome)
    backup_time = now() - timedelta(days=2)
    with pytest.raises(RestoreNotServing) as error:
        svc.reapply_tombstones_after_restore("gs://fixture/backup", backup_time)
    restore_id = error.value.restore_id
    assert restore_id
    assert projections.read_profile("restore-member") is not None
    assert read(db, "SELECT state FROM RestoreRuns") == [["restoring"]]
    for action in (svc.assert_serving, lambda: svc.export("member", now()),
                   lambda: svc.request_deletion("member", now()), lambda: svc.run_deletion(job)):
        with pytest.raises(RestoreNotServing):
            action()
    monkeypatch.setattr(persona, "purge_derived", purge)
    result = svc.reapply_tombstones_after_restore("gs://fixture/backup", backup_time, restore_id=restore_id)
    assert result["restore_id"] == restore_id and result["tombstones_applied"] == 1
    assert projections.read_profile("restore-member") is None
    assert read(db, "SELECT COUNT(*) FROM RestoreRuns") == [[1]]
    svc.assert_serving()
    with pytest.raises(ValueError):  # a new physical restore cannot reuse a completed run
        svc.reapply_tombstones_after_restore("gs://fixture/backup", backup_time, restore_id=restore_id)


@pytest.mark.parametrize("state", ["failed", "restoring", "unknown"])
def test_all_unverified_restore_states_block_serving(setup, state):
    svc, _, _, _, db = setup
    with db.batch() as batch:
        batch.insert("RestoreRuns", ["restore_id", "backup_ref", "backup_taken_at", "state", "started_at"],
                     [["blocked", "gs://fixture/backup", now() - timedelta(days=1), state, now()]])
    with pytest.raises(RestoreNotServing):
        svc.assert_serving()


def test_restore_resume_binds_backup_identity_and_redacts_handler_error(setup, monkeypatch):
    svc, persona, _, db, _ = make_restore(setup)
    def fail(*_):
        raise ConnectionError("NEVER_LOG_THIS provider?credential=private")
    monkeypatch.setattr(persona, "purge_derived", fail)
    backup_time = now() - timedelta(days=2)
    with pytest.raises(RestoreNotServing) as error:
        svc.reapply_tombstones_after_restore("gs://fixture/backup", backup_time)
    assert "NEVER_LOG_THIS" not in str(error.value)
    for ref, timestamp in (("gs://other/backup", backup_time), ("gs://fixture/backup", now())):
        with pytest.raises(ValueError):
            svc.reapply_tombstones_after_restore(ref, timestamp, restore_id=error.value.restore_id)
    assert read(db, "SELECT state FROM RestoreRuns") == [["restoring"]]


def test_failed_restore_resumes_same_ledger_entry(setup):
    svc, _, _, _, db = setup
    backup_time = now() - timedelta(days=1)
    with db.batch() as batch:
        batch.insert("RestoreRuns", ["restore_id", "backup_ref", "backup_taken_at", "state", "started_at"],
                     [["retry", "gs://fixture/backup", backup_time, "failed", now()]])
    svc.reapply_tombstones_after_restore("gs://fixture/backup", backup_time, restore_id="retry")
    svc.assert_serving()
    assert read(db, "SELECT COUNT(*) FROM RestoreRuns") == [[1]]


def test_missing_restore_handler_never_marks_database_ready(setup):
    svc, _, _, db, _ = make_restore(setup)
    svc.reg.unregister_domain("persona")
    with pytest.raises(RestoreNotServing):
        svc.reapply_tombstones_after_restore("gs://fixture/backup", now() - timedelta(days=1))
    assert read(db, "SELECT state FROM RestoreRuns") == [["restoring"]]


@pytest.mark.parametrize("outcome", [DeletionOutcome("persona.declared", 0, done=False),
                                    DeletionOutcome("persona.declared", 0, exception="not removed")])
def test_outside_transaction_restore_requires_confirmed_record_removal(setup, monkeypatch, outcome):
    svc, persona, _, db, _ = make_restore(setup)
    monkeypatch.setattr(persona, "transactional", False, raising=False)
    monkeypatch.setattr(persona, "delete_outside_txn", lambda *_: outcome, raising=False)
    with pytest.raises(RestoreNotServing):
        svc.reapply_tombstones_after_restore("gs://fixture/backup", now() - timedelta(days=1))
    assert read(db, "SELECT state FROM RestoreRuns") == [["restoring"]]
    assert persona.count(db, "restore-member") == 1


def test_bad_restore_count_rolls_back_transaction(setup, monkeypatch):
    svc, persona, _, db, _ = make_restore(setup)
    reapply = persona.reapply_tombstone
    def invalid(tx, tombstone):
        reapply(tx, tombstone)
        return False
    monkeypatch.setattr(persona, "reapply_tombstone", invalid)
    with pytest.raises(RestoreNotServing):
        svc.reapply_tombstones_after_restore("gs://fixture/backup", now() - timedelta(days=1))
    assert persona.count(db, "restore-member") == 1

