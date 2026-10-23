"""
Copyright (c) Brand.Me, Inc. All rights reserved.

My Data orchestration (W10): inventory, export, deletion, restore.

Drives the domain handlers registered through ``deletion.register_domain``.
State lives in the V009 tables (ExportJobs, DeletionJobs, DeletionSteps,
DeletionTombstones, ProcessingFreezes, RestoreRuns).

Receipts are truthful: every category reports what was deleted, what could
not be and why (public ledger commitments, legally retained records,
third-party copies we do not control), and when encrypted backups that still
contain the data expire. Nothing reports "deleted" for data that remains.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Protocol, Sequence

from google.cloud.spanner_v1 import param_types as pt
from google.cloud.spanner_v1.database import Database

from brandme_core.events import EventEnvelope, write_events
from brandme_core.events.outbox import json_payload
from brandme_core.domains.events import PRIVACY_DELETION_REQUESTED, PRIVACY_DELETION_COMPLETED

from .deletion import (
    DataCategory,
    DeletionOutcome,
    OnDelete,
    PrivacyRegistry,
    SubjectContext,
    Tombstone,
    new_id,
    registry as default_registry,
)

EXPORT_SCHEMA = "brandme.my-data-export/v1"
RECEIPT_SCHEMA = "brandme.deletion-receipt/v1"
REAUTH_WINDOW = timedelta(minutes=10)

#: Keys that must never appear anywhere in an ordinary export (ch.03 My Data).
FORBIDDEN_EXPORT_KEYS = frozenset({
    "seed", "mnemonic", "seed_phrase", "private_key", "secret", "holder_secret", "governance_secret",
    "issuer_secret", "password", "card_number", "cvc", "payment_credential", "access_token", "refresh_token",
})

PRIVATE_STATE_BACKUP_INSTRUCTIONS = (
    "Midnight ownership secrets are not included in this export and are never held by Brand.Me. "
    "Export them separately from Wallet → Ownership backup, which produces an encrypted file bound to "
    "one network and contract. Your wallet seed phrase alone does not restore them."
)


class ReauthRequired(Exception):
    pass


class ForbiddenExportContent(Exception):
    pass


class ExportFailed(Exception):
    """A provider failure; details must not cross the member boundary."""


class RestoreNotServing(Exception):
    def __init__(self, message: str, restore_id: str | None = None):
        super().__init__(message)
        self.restore_id = restore_id


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> str: ...
    def delete(self, key: str) -> None: ...


@dataclass(frozen=True)
class RetentionPolicy:
    backup_retention: timedelta = timedelta(days=30)
    export_link_ttl: timedelta = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _check_reauth(reauth_at: datetime, now: datetime) -> None:
    if reauth_at.tzinfo is None or now - reauth_at > REAUTH_WINDOW or reauth_at > now + timedelta(seconds=5):
        raise ReauthRequired("recent re-authentication is required for this action")


def _scan_forbidden(obj: Any, path: str = "$") -> None:
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            # Domain handlers use both Python and JSON naming conventions.
            if re.sub(r"[^a-z0-9]", "", str(k).lower()) in _FORBIDDEN_NORMALIZED:
                raise ForbiddenExportContent("export contains forbidden credential material")
            _scan_forbidden(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _scan_forbidden(v, f"{path}[{i}]")


_FORBIDDEN_NORMALIZED = frozenset(re.sub(r"[^a-z0-9]", "", k) for k in FORBIDDEN_EXPORT_KEYS)


def _checked_outcome(outcome: DeletionOutcome, category: str) -> DeletionOutcome:
    if (not isinstance(outcome, DeletionOutcome) or outcome.category != category
            or type(outcome.rows_affected) is not int or outcome.rows_affected < 0
            or type(outcome.done) is not bool
            or any(v is not None and (not isinstance(v, str) or not v.strip() or len(v) > 1024)
                   for v in (outcome.exception, outcome.detail))):
        raise ValueError("invalid privacy handler outcome")
    return outcome


def _jsonable(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, bytes):
        return o.hex()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


class MyDataService:
    def __init__(self, database: Database, store: ObjectStore, reg: PrivacyRegistry | None = None,
                 retention: RetentionPolicy = RetentionPolicy(), *, environment: str) -> None:
        if environment not in ("demo", "development", "sandbox", "production"):
            raise ValueError("explicit Brand.Me environment required")
        self.db = database
        self.store = store
        self.reg = reg or default_registry
        self.retention = retention
        self.environment = environment

    def _event(self, event_type: str, job_id: str, version: int, payload: dict) -> EventEnvelope:
        return EventEnvelope(event_type=event_type, schema_version="1", aggregate_type="deletion_job",
                             aggregate_id=job_id, aggregate_version=version, environment=self.environment,
                             actor_ref="service:privacy", correlation_id=job_id, privacy_class="restricted", payload=payload)

    # ------------------------------------------------------------ inventory
    def inventory(self) -> list[dict[str, Any]]:
        """Readable description of every category: who supplied it, who sees it, retention, edit/delete."""
        return [
            {**asdict(c), "supplied_by": c.supplied_by.value, "on_delete": c.on_delete.value}
            for c in self.reg.categories()
        ]

    # --------------------------------------------------------------- export
    def _categories(self, categories: Optional[Sequence[str]]) -> list[str]:
        cats = [c.key for c in self.reg.categories()] if categories is None else list(categories)
        if not cats or len(cats) > 100 or any(not isinstance(c, str) for c in cats) or len(set(cats)) != len(cats):
            raise ValueError("select between 1 and 100 distinct registered categories")
        for key in cats:
            self.reg.category(key)
        return cats

    def export(self, subject_ref: str, reauth_at: datetime, categories: Optional[Sequence[str]] = None) -> dict[str, Any]:
        now = _now()
        _check_reauth(reauth_at, now)
        cats = self._categories(categories)
        self.assert_serving()
        job_id = new_id()
        with self.db.batch() as b:
            b.insert("ExportJobs", ["job_id", "subject_ref", "state", "categories", "reauth_at", "requested_at"],
                     [[job_id, subject_ref, "running", cats, reauth_at, now]])
        # Object keys carry no subject identifier and never use caller-controlled path components.
        key = f"exports/{job_id}.json"
        upload_attempted = False
        try:
            ctx = SubjectContext(subject_ref=subject_ref, job_id=job_id, requested_at=now)
            sections: dict[str, Any] = {}
            chain_refs: list[Any] = []
            with self.db.snapshot(multi_use=True) as snap:
                for category in cats:
                    sec = self.reg.handler_for(category).export(snap, ctx, category)
                    if sec.category != category:
                        raise ValueError("export handler returned another category")
                    cat = self.reg.category(category)
                    sections[category] = {
                        "title": cat.title, "supplied_by": cat.supplied_by.value, "visible_to": list(cat.visible_to),
                        "retention": cat.retention, "records": sec.records, "references": sec.references, "notes": sec.notes,
                    }
                    if cat.on_delete is OnDelete.NOT_ERASABLE_PUBLIC_LEDGER:
                        chain_refs.extend(sec.references)
            package = {
                "schema": EXPORT_SCHEMA,
                "subject_ref": subject_ref,
                "generated_at": now.isoformat(),
                "categories": sections,
                "public_chain_references": chain_refs,
                "private_state_backup": PRIVATE_STATE_BACKUP_INSTRUCTIONS,
            }
            _scan_forbidden(package)
            body = json.dumps(package, default=_jsonable, sort_keys=True, indent=2).encode()
            digest = hashlib.sha256(body).hexdigest()
            upload_attempted = True
            ref = self.store.put(key, body, "application/json")
            if not isinstance(ref, str) or not ref or len(ref) > 512:
                raise ValueError("invalid export storage reference")
        except Exception as exc:
            cleanup = "not_needed"
            if upload_attempted:
                try:
                    self.store.delete(key)
                    cleanup = "confirmed"
                except Exception:
                    cleanup = "required"
            # No raw provider error, URL, credential or private payload in the job.
            try:
                with self.db.batch() as b:
                    b.update("ExportJobs", ["job_id", "state", "manifest_json", "completed_at"],
                             [[job_id, "failed", json.dumps({"error": "export_failed", "cleanup": cleanup}), _now()]])
            except Exception:
                # A database outage may leave a running job; an operator must reconcile it.
                raise ExportFailed("export_failed") from None
            if isinstance(exc, ForbiddenExportContent):
                raise
            raise ExportFailed("export_failed") from None
        expires = now + self.retention.export_link_ttl
        manifest = {"categories": cats, "sha256": digest, "bytes": len(body)}
        try:
            with self.db.batch() as b:
                b.update("ExportJobs", ["job_id", "state", "manifest_json", "package_ref", "package_sha256", "completed_at", "expires_at"],
                         [[job_id, "ready", json.dumps(manifest), ref, digest, _now(), expires]])
        except Exception:
            # Commit acknowledgement may be lost after success. Do not delete an object
            # that a committed ready job references, or invent a failure receipt.
            raise ExportFailed("export_finalization_unconfirmed") from None
        return {"job_id": job_id, "package_ref": ref, "sha256": digest, "expires_at": expires.isoformat(),
                "categories": cats, "package": package}

    # ------------------------------------------------------------- deletion
    def request_deletion(self, subject_ref: str, reauth_at: datetime, categories: Optional[Sequence[str]] = None) -> str:
        """
        Accept a deletion request. In ONE transaction: record the job and freeze
        processing (whole account, or the named categories), so any later writer
        guarded by assert_processing_allowed is refused from this commit on.
        """
        now = _now()
        _check_reauth(reauth_at, now)
        account = categories is None
        cats = self._categories(categories)
        self.assert_serving()
        job_id = new_id()

        def txn_fn(txn: Any) -> None:
            txn.insert("DeletionJobs", ["job_id", "subject_ref", "scope", "categories", "state", "reauth_at", "requested_at", "version"],
                       [[job_id, subject_ref, "account" if account else "category", cats, "requested", reauth_at, now, 1]])
            freezes = ["*"] if account else cats
            for category in freezes:
                existing = list(txn.execute_sql(
                    "SELECT reason FROM ProcessingFreezes WHERE subject_ref = @s AND category = @c",
                    params={"s": subject_ref, "c": category}, param_types={"s": pt.STRING, "c": pt.STRING}))
                # A deletion cannot replace or later clear an independent restriction.
                if not existing or existing[0][0] == "deletion":
                    txn.insert_or_update("ProcessingFreezes", ["subject_ref", "category", "reason", "deletion_job_id", "created_at"],
                                         [[subject_ref, category, "deletion", job_id, pt_commit()]])
            steps = []
            for k in cats:
                for step in ("delete_records", "delete_projections"):
                    steps.append([job_id, k, step, "pending", None, None, pt_commit()])
            txn.insert("DeletionSteps", ["job_id", "category", "step", "state", "rows_affected", "detail", "updated_at"], steps)
            write_events(txn, [self._event(PRIVACY_DELETION_REQUESTED.event_type, job_id, 1,
                                         {"job_id": job_id, "scope": "account" if account else "category"})])

        self.db.run_in_transaction(txn_fn)
        return job_id

    def run_deletion(self, job_id: str) -> dict[str, Any]:
        """Resume persisted steps. The caller must serialize execution per subject.

        External handler callbacks are idempotent but cannot be fenced by this
        library. Do not invoke it concurrently from an at-least-once consumer.
        """
        self.assert_serving()
        job = self._job(job_id)
        if job["state"] in ("completed", "completed_with_exceptions") and job["receipt_json"]:
            return json_payload(job["receipt_json"])
        ctx = SubjectContext(subject_ref=job["subject_ref"], job_id=job_id, requested_at=job["requested_at"])
        self._set_job_state(job_id, "running")
        results: dict[str, dict[str, Any]] = {}
        for key in job["categories"]:
            cat = self.reg.category(key)
            handler = self.reg.handler_for(key)
            with self.db.snapshot() as snap:
                saved_records = self._step(snap, job_id, key, "delete_records")
            out_records = saved_records
            if not saved_records.done:
                # Outside-transaction adapters must be idempotent; keep the freeze
                # until both their record and derived cleanup have finished.
                pre = None if getattr(handler, "transactional", True) else _checked_outcome(
                    handler.delete_outside_txn(self.db, ctx, key), key)

                def txn_fn(txn: Any) -> DeletionOutcome:
                    saved = self._step(txn, job_id, key, "delete_records")
                    if saved.done:
                        return saved
                    outcome = _checked_outcome(pre if pre is not None else handler.delete(txn, ctx, key), key)
                    outcome = replace(outcome, rows_affected=outcome.rows_affected + saved.rows_affected)
                    txn.insert("DeletionTombstones", ["subject_ref", "category", "tombstone_id", "deletion_job_id", "record_keys", "created_at"],
                               [[ctx.subject_ref, key, new_id(), job_id, list(ctx.record_keys), pt_commit()]])
                    self._save_step(txn, job_id, key, "delete_records", outcome)
                    return outcome
                out_records = self.db.run_in_transaction(txn_fn)
            with self.db.snapshot() as snap:
                out_derived = self._step(snap, job_id, key, "delete_projections")
            if out_records.done and not out_derived.done:
                fresh = _checked_outcome(handler.purge_derived(ctx, key), key)
                fresh = replace(fresh, rows_affected=fresh.rows_affected + out_derived.rows_affected)
                self.db.run_in_transaction(lambda txn: self._save_step(txn, job_id, key, "delete_projections", fresh))
                out_derived = fresh
            results[key] = self._category_receipt(cat, out_records, out_derived)
        exceptions = [r for r in results.values() if r["status"] != "deleted"]
        finished = all(r["status"] not in ("pending_derived", "pending_records") for r in results.values())
        state = ("completed_with_exceptions" if exceptions else "completed") if finished else "running"
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "job_id": job_id,
            "subject_ref": job["subject_ref"],
            "scope": job["scope"],
            "requested_at": job["requested_at"].isoformat(),
            "completed_at": _now().isoformat() if finished else None,
            "categories": results,
            "backups": {
                "statement": "Encrypted backups taken before this deletion may still contain this data until they expire. "
                             "If a backup is ever restored, this deletion is re-applied before any data is served.",
                "expires_no_later_than": (job["requested_at"] + self.retention.backup_retention).date().isoformat(),
            },
            "processing": ("Category processing may resume from fresh inputs; tombstones reject stale work."
                           if job["scope"] == "category" and finished else
                           "Frozen: deletion processing has not been lifted."),
        }
        def complete(txn: Any) -> dict[str, Any]:
            # A retried/concurrent completion keeps the first receipt and emits once.
            rows = list(txn.execute_sql("SELECT state, receipt_json, version FROM DeletionJobs WHERE job_id = @j",
                                       params={"j": job_id}, param_types={"j": pt.STRING}))
            if rows[0][0] in ("completed", "completed_with_exceptions") and rows[0][1]:
                return json_payload(rows[0][1])
            version = rows[0][2] + 1
            if finished:
                if job["scope"] == "category":
                    # Either completion order must preserve overlapping unfinished
                    # requests, including failed jobs that still need intervention.
                    pending = list(txn.execute_sql(
                        "SELECT scope, categories FROM DeletionJobs WHERE subject_ref = @s AND job_id != @j "
                        "AND state NOT IN ('completed', 'completed_with_exceptions')",
                        params={"s": job["subject_ref"], "j": job_id}, param_types={"s": pt.STRING, "j": pt.STRING}))
                    for category in job["categories"]:
                        if any(scope == "account" or category in categories for scope, categories in pending):
                            continue
                        txn.execute_update(
                            "DELETE FROM ProcessingFreezes WHERE subject_ref = @s AND category = @c AND reason = 'deletion'",
                            params={"s": job["subject_ref"], "c": category}, param_types={"s": pt.STRING, "c": pt.STRING})
                    frozen = list(txn.execute_sql(
                        "SELECT category FROM ProcessingFreezes WHERE subject_ref = @s AND category IN UNNEST(@c)",
                        params={"s": job["subject_ref"], "c": ["*", *job["categories"]]},
                        param_types={"s": pt.STRING, "c": pt.Array(pt.STRING)}))
                    receipt["processing"] = (
                        "Frozen: another deletion request or processing restriction is still active." if frozen else
                        "Category processing may resume from fresh inputs; tombstones reject stale work.")
                write_events(txn, [self._event(PRIVACY_DELETION_COMPLETED.event_type, job_id, version,
                                             {"job_id": job_id, "state": state})])
            txn.update("DeletionJobs", ["job_id", "state", "completed_at", "receipt_json", "version"],
                       [[job_id, state, _now() if finished else None, json.dumps(receipt, default=_jsonable), version]])
            return receipt
        return self.db.run_in_transaction(complete)

    @staticmethod
    def _category_receipt(cat: DataCategory, rec: Optional[DeletionOutcome], derived: DeletionOutcome) -> dict[str, Any]:
        r: dict[str, Any] = {
            "title": cat.title,
            "rows_affected": (rec.rows_affected if rec else None),
            "derived_purged": derived.rows_affected,
        }
        if rec and not rec.done:
            r["status"] = "pending_records"
            r["reason"] = "records are still being removed"
        elif not derived.done:
            r["status"] = "pending_derived"
            r["reason"] = derived.exception or "derived copies are still being removed"
        elif derived.exception:
            r["status"] = "exception"
            r["reason"] = derived.exception
        elif cat.on_delete is OnDelete.NOT_ERASABLE_PUBLIC_LEDGER:
            r["status"] = "not_erasable"
            r["reason"] = ("Public blockchain commitments cannot be erased. They contain no personal data in plaintext; "
                           "deleting this category does not erase the ledger. Member control links are a separate category.")
        elif cat.on_delete is OnDelete.RETAIN_LEGAL:
            r["status"] = "retained"
            r["reason"] = cat.retention_basis
        elif rec and rec.exception:
            r["status"] = "exception"
            r["reason"] = rec.exception
        else:
            r["status"] = "deleted" if cat.on_delete is OnDelete.ERASE else "anonymized"
            if r["status"] == "anonymized":
                r["status"] = "deleted"  # anonymized records carry no link to the member
        return r

    # -------------------------------------------------------------- restore
    def reapply_tombstones_after_restore(self, backup_ref: str, backup_taken_at: datetime, *,
                                         restore_id: str | None = None) -> dict[str, Any]:
        """Reapply a preserved tombstone ledger while traffic and writers are stopped.

        Resume a failed/interrupted attempt using its restore_id and the exact
        same backup identity. Every replayed handler must be idempotent. A new
        physical restore always needs a new run, even for the same backup.
        """
        if not backup_ref or len(backup_ref) > 512 or backup_taken_at.tzinfo is None:
            raise ValueError("backup identity and timezone-aware timestamp required")
        if restore_id is None:
            restore_id = new_id()
            with self.db.batch() as b:
                b.insert("RestoreRuns", ["restore_id", "backup_ref", "backup_taken_at", "state", "started_at"],
                         [[restore_id, backup_ref, backup_taken_at, "restoring", _now()]])
        else:
            def resume(txn: Any) -> None:
                rows = list(txn.execute_sql(
                    "SELECT backup_ref, backup_taken_at, state FROM RestoreRuns WHERE restore_id = @r",
                    params={"r": restore_id}, param_types={"r": pt.STRING}))
                if not rows or rows[0][:2] != [backup_ref, backup_taken_at] or rows[0][2] not in ("restoring", "failed"):
                    raise ValueError("restore run cannot resume with this backup identity or state")
                txn.update("RestoreRuns", ["restore_id", "state"], [[restore_id, "restoring"]])
            self.db.run_in_transaction(resume)
        applied = 0
        rows_deleted = 0
        try:
            with self.db.snapshot() as snap:
                tombs = [Tombstone(subject_ref=r[0], category=r[1], tombstone_id=r[2], deletion_job_id=r[3],
                                   record_keys=tuple(r[4] or ()), created_at=r[5])
                         for r in snap.execute_sql("SELECT subject_ref, category, tombstone_id, deletion_job_id, record_keys, created_at FROM DeletionTombstones")]
            for tombstone in tombs:
                handler = self.reg.handler_for(tombstone.category)
                ctx = SubjectContext(tombstone.subject_ref, tombstone.deletion_job_id, tombstone.created_at, tombstone.record_keys)
                if getattr(handler, "transactional", True):
                    def reapply(txn: Any) -> int:
                        count = handler.reapply_tombstone(txn, tombstone)
                        if type(count) is not int or count < 0:
                            raise ValueError("invalid restore handler count")
                        return count
                    rows_deleted += self.db.run_in_transaction(reapply)
                else:
                    outcome = _checked_outcome(handler.delete_outside_txn(self.db, ctx, tombstone.category), tombstone.category)
                    if not outcome.done or outcome.exception:
                        raise RestoreNotServing("record cleanup is incomplete")
                    rows_deleted += outcome.rows_affected
                derived = _checked_outcome(handler.purge_derived(ctx, tombstone.category), tombstone.category)
                if not derived.done or derived.exception:
                    raise RestoreNotServing("derived cleanup is incomplete")
                applied += 1
            with self.db.batch() as b:
                b.update("RestoreRuns", ["restore_id", "state", "tombstones_applied", "completed_at"],
                         [[restore_id, "tombstones_reapplied", applied, _now()]])
        except Exception:
            # The existing restoring row remains a durable serving barrier.
            # Do not persist or expose arbitrary handler/provider exception text.
            raise RestoreNotServing("restore cleanup is incomplete; resume this run before serving", restore_id) from None
        return {"restore_id": restore_id, "tombstones_applied": applied, "rows_redeleted": rows_deleted}

    def assert_serving(self) -> None:
        with self.db.snapshot() as snap:
            pending = list(snap.execute_sql(
                "SELECT restore_id FROM RestoreRuns WHERE state NOT IN ('tombstones_reapplied', 'serving') LIMIT 1"))
        if pending:
            raise RestoreNotServing("restore is incomplete: serving is blocked", pending[0][0])

    # ------------------------------------------------------------- helpers
    def _job(self, job_id: str) -> dict[str, Any]:
        with self.db.snapshot() as snap:
            rows = list(snap.execute_sql(
                "SELECT subject_ref, scope, categories, state, requested_at, receipt_json FROM DeletionJobs WHERE job_id = @j",
                params={"j": job_id}, param_types={"j": pt.STRING}))
        if not rows:
            raise KeyError(job_id)
        r = rows[0]
        return {"subject_ref": r[0], "scope": r[1], "categories": list(r[2]), "state": r[3], "requested_at": r[4], "receipt_json": r[5]}

    @staticmethod
    def _step(reader: Any, job_id: str, category: str, step: str) -> DeletionOutcome:
        rows = list(reader.execute_sql(
            "SELECT state, rows_affected, detail FROM DeletionSteps WHERE job_id = @j AND category = @c AND step = @step",
            params={"j": job_id, "c": category, "step": step},
            param_types={"j": pt.STRING, "c": pt.STRING, "step": pt.STRING}))
        if not rows or rows[0][0] not in ("pending", "done", "exception", "exception_done", "failed"):
            raise ValueError("missing or invalid deletion step")
        state, count, detail = rows[0]
        if state in ("exception", "exception_done") and not detail:
            raise ValueError("missing deletion exception reason")
        # Older writers used 'exception' for both done=True and done=False.
        # Recheck that ambiguous state instead of upgrading it to completion.
        return _checked_outcome(DeletionOutcome(category, count or 0, done=state in ("done", "exception_done"),
                                                exception=detail if state == "exception_done" else None,
                                                detail=detail if state != "exception_done" else None), category)

    @staticmethod
    def _save_step(txn: Any, job_id: str, category: str, step: str, outcome: DeletionOutcome) -> None:
        state = "failed" if not outcome.done else "exception_done" if outcome.exception else "done"
        txn.update("DeletionSteps", ["job_id", "category", "step", "state", "rows_affected", "detail", "updated_at"],
                   [[job_id, category, step, state, outcome.rows_affected, outcome.exception or outcome.detail, pt_commit()]])

    def _set_job_state(self, job_id: str, state: str) -> None:
        self.db.run_in_transaction(lambda txn: txn.execute_update(
            "UPDATE DeletionJobs SET state = @s WHERE job_id = @j AND state NOT IN ('completed', 'completed_with_exceptions')",
            params={"s": state, "j": job_id}, param_types={"s": pt.STRING, "j": pt.STRING}))


def pt_commit() -> Any:
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

    return COMMIT_TIMESTAMP


def keyset_for(keys: list[list[Any]]) -> Any:
    from google.cloud.spanner_v1 import KeySet

    return KeySet(keys=keys)
