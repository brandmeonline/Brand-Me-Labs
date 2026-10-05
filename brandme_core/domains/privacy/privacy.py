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
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Protocol, Sequence

from google.cloud.spanner_v1 import param_types as pt
from google.cloud.spanner_v1.database import Database

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


class RestoreNotServing(Exception):
    pass


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
            if str(k).lower() in FORBIDDEN_EXPORT_KEYS:
                raise ForbiddenExportContent(f"forbidden key '{k}' at {path}")
            _scan_forbidden(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _scan_forbidden(v, f"{path}[{i}]")


def _jsonable(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, bytes):
        return o.hex()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


class MyDataService:
    def __init__(self, database: Database, store: ObjectStore, reg: PrivacyRegistry | None = None,
                 retention: RetentionPolicy = RetentionPolicy()) -> None:
        self.db = database
        self.store = store
        self.reg = reg or default_registry
        self.retention = retention

    # ------------------------------------------------------------ inventory
    def inventory(self) -> list[dict[str, Any]]:
        """Readable description of every category: who supplied it, who sees it, retention, edit/delete."""
        return [
            {**asdict(c), "supplied_by": c.supplied_by.value, "on_delete": c.on_delete.value}
            for c in self.reg.categories()
        ]

    # --------------------------------------------------------------- export
    def export(self, subject_ref: str, reauth_at: datetime, categories: Optional[Sequence[str]] = None) -> dict[str, Any]:
        now = _now()
        _check_reauth(reauth_at, now)
        cats = list(categories) if categories else [c.key for c in self.reg.categories()]
        job_id = new_id()
        with self.db.batch() as b:
            b.insert("ExportJobs", ["job_id", "subject_ref", "state", "categories", "reauth_at", "requested_at"],
                     [[job_id, subject_ref, "running", cats, reauth_at, now]])
        ctx = SubjectContext(subject_ref=subject_ref, job_id=job_id, requested_at=now)
        sections: dict[str, Any] = {}
        chain_refs: list[Any] = []
        with self.db.snapshot(multi_use=True) as snap:
            for key in cats:
                sec = self.reg.handler_for(key).export(snap, ctx, key)
                cat = self.reg.category(key)
                sections[key] = {
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
        ref = self.store.put(f"exports/{subject_ref}/{job_id}.json", body, "application/json")
        expires = now + self.retention.export_link_ttl
        manifest = {"categories": cats, "sha256": digest, "bytes": len(body)}
        with self.db.batch() as b:
            b.update("ExportJobs", ["job_id", "state", "manifest_json", "package_ref", "package_sha256", "completed_at", "expires_at"],
                     [[job_id, "ready", json.dumps(manifest), ref, digest, _now(), expires]])
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
        cats = [c.key for c in self.reg.categories()] if account else list(categories)
        for k in cats:
            self.reg.category(k)
        job_id = new_id()

        def txn_fn(txn: Any) -> None:
            txn.insert("DeletionJobs", ["job_id", "subject_ref", "scope", "categories", "state", "reauth_at", "requested_at", "version"],
                       [[job_id, subject_ref, "account" if account else "category", cats, "requested", reauth_at, now, 1]])
            freezes = ["*"] if account else cats
            txn.insert_or_update("ProcessingFreezes", ["subject_ref", "category", "reason", "deletion_job_id", "created_at"],
                                 [[subject_ref, f, "deletion", job_id, pt_commit()] for f in freezes])
            steps = []
            for k in cats:
                for step in ("delete_records", "delete_projections"):
                    steps.append([job_id, k, step, "pending", None, None, pt_commit()])
            txn.insert("DeletionSteps", ["job_id", "category", "step", "state", "rows_affected", "detail", "updated_at"], steps)

        self.db.run_in_transaction(txn_fn)
        return job_id

    def run_deletion(self, job_id: str) -> dict[str, Any]:
        job = self._job(job_id)
        ctx = SubjectContext(subject_ref=job["subject_ref"], job_id=job_id, requested_at=job["requested_at"])
        self._set_job_state(job_id, "running")
        results: dict[str, dict[str, Any]] = {}
        for key in job["categories"]:
            cat = self.reg.category(key)
            handler = self.reg.handler_for(key)
            steps = self._steps(job_id, key)
            out_records: Optional[DeletionOutcome] = None
            if steps.get("delete_records") != "done":
                def txn_fn(txn: Any, key: str = key) -> DeletionOutcome:
                    outcome = handler.delete(txn, ctx, key)
                    txn.insert("DeletionTombstones", ["subject_ref", "category", "tombstone_id", "deletion_job_id", "record_keys", "created_at"],
                               [[ctx.subject_ref, key, new_id(), job_id, list(ctx.record_keys), pt_commit()]])
                    txn.update("DeletionSteps", ["job_id", "category", "step", "state", "rows_affected", "detail", "updated_at"],
                               [[job_id, key, "delete_records", "exception" if outcome.exception else "done",
                                 outcome.rows_affected, outcome.exception or outcome.detail, pt_commit()]])
                    return outcome
                out_records = self.db.run_in_transaction(txn_fn)
            # Projections / caches / media: after commit, idempotent.
            out_derived = handler.purge_derived(ctx, key)
            with self.db.batch() as b:
                b.update("DeletionSteps", ["job_id", "category", "step", "state", "rows_affected", "detail", "updated_at"],
                         [[job_id, key, "delete_projections", "done" if out_derived.done else "failed",
                           out_derived.rows_affected, out_derived.exception or out_derived.detail, pt_commit()]])
            results[key] = self._category_receipt(cat, out_records, out_derived)
        exceptions = [r for r in results.values() if r["status"] != "deleted"]
        state = "completed_with_exceptions" if exceptions else "completed"
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "job_id": job_id,
            "subject_ref": job["subject_ref"],
            "scope": job["scope"],
            "requested_at": job["requested_at"].isoformat(),
            "completed_at": _now().isoformat(),
            "categories": results,
            "backups": {
                "statement": "Encrypted backups taken before this deletion may still contain this data until they expire. "
                             "If a backup is ever restored, this deletion is re-applied before any data is served.",
                "expires_no_later_than": (job["requested_at"] + self.retention.backup_retention).date().isoformat(),
            },
            "processing": "Frozen: no new inferences or derived data will be created from the deleted data.",
        }
        if job["scope"] == "category":
            # A category deletion lifts the freeze once complete; tombstones still block stale jobs (basis_time check).
            def lift(txn: Any) -> None:
                txn.delete("ProcessingFreezes", keyset_for([[job["subject_ref"], k] for k in job["categories"]]))
            self.db.run_in_transaction(lift)
        with self.db.batch() as b:
            b.update("DeletionJobs", ["job_id", "state", "completed_at", "receipt_json"],
                     [[job_id, state, _now(), json.dumps(receipt, default=_jsonable)]])
        return receipt

    @staticmethod
    def _category_receipt(cat: DataCategory, rec: Optional[DeletionOutcome], derived: DeletionOutcome) -> dict[str, Any]:
        r: dict[str, Any] = {
            "title": cat.title,
            "rows_affected": (rec.rows_affected if rec else None),
            "derived_purged": derived.rows_affected,
        }
        if cat.on_delete is OnDelete.NOT_ERASABLE_PUBLIC_LEDGER:
            r["status"] = "not_erasable"
            r["reason"] = ("Public blockchain commitments cannot be erased. They contain no personal data in plaintext; "
                           "the link between you and them has been removed from Brand.Me.")
        elif cat.on_delete is OnDelete.RETAIN_LEGAL:
            r["status"] = "retained"
            r["reason"] = cat.retention_basis
        elif rec and rec.exception:
            r["status"] = "exception"
            r["reason"] = rec.exception
        elif not derived.done:
            r["status"] = "pending_derived"
            r["reason"] = derived.exception or "derived copies are still being removed"
        else:
            r["status"] = "deleted" if cat.on_delete is OnDelete.ERASE else "anonymized"
            if r["status"] == "anonymized":
                r["status"] = "deleted"  # anonymized records carry no link to the member
        return r

    # -------------------------------------------------------------- restore
    def reapply_tombstones_after_restore(self, backup_ref: str, backup_taken_at: datetime) -> dict[str, Any]:
        """
        Run immediately after a database restore, before serving traffic.
        Re-deletes every tombstoned category; the restored DB is not served
        until this completes (``assert_serving``).
        """
        restore_id = new_id()
        with self.db.batch() as b:
            b.insert("RestoreRuns", ["restore_id", "backup_ref", "backup_taken_at", "state", "started_at"],
                     [[restore_id, backup_ref, backup_taken_at, "restoring", _now()]])
        applied = 0
        rows = 0
        with self.db.snapshot() as snap:
            tombs = [Tombstone(subject_ref=r[0], category=r[1], tombstone_id=r[2], deletion_job_id=r[3],
                               record_keys=tuple(r[4] or ()), created_at=r[5])
                     for r in snap.execute_sql("SELECT subject_ref, category, tombstone_id, deletion_job_id, record_keys, created_at FROM DeletionTombstones")]
        for t in tombs:
            handler = self.reg.handler_for(t.category)
            rows += self.db.run_in_transaction(lambda txn, t=t: handler.reapply_tombstone(txn, t))
            handler.purge_derived(SubjectContext(t.subject_ref, t.deletion_job_id, t.created_at, t.record_keys), t.category)
            applied += 1
        with self.db.batch() as b:
            b.update("RestoreRuns", ["restore_id", "state", "tombstones_applied", "completed_at"],
                     [[restore_id, "tombstones_reapplied", applied, _now()]])
        return {"restore_id": restore_id, "tombstones_applied": applied, "rows_redeleted": rows}

    def assert_serving(self) -> None:
        with self.db.snapshot() as snap:
            pending = list(snap.execute_sql("SELECT restore_id FROM RestoreRuns WHERE state = 'restoring' LIMIT 1"))
        if pending:
            raise RestoreNotServing("restore in progress: tombstones not yet reapplied")

    # ------------------------------------------------------------- helpers
    def _job(self, job_id: str) -> dict[str, Any]:
        with self.db.snapshot() as snap:
            rows = list(snap.execute_sql(
                "SELECT subject_ref, scope, categories, state, requested_at FROM DeletionJobs WHERE job_id = @j",
                params={"j": job_id}, param_types={"j": pt.STRING}))
        if not rows:
            raise KeyError(job_id)
        r = rows[0]
        return {"subject_ref": r[0], "scope": r[1], "categories": list(r[2]), "state": r[3], "requested_at": r[4]}

    def _steps(self, job_id: str, category: str) -> dict[str, str]:
        with self.db.snapshot() as snap:
            return {r[0]: r[1] for r in snap.execute_sql(
                "SELECT step, state FROM DeletionSteps WHERE job_id = @j AND category = @c",
                params={"j": job_id, "c": category}, param_types={"j": pt.STRING, "c": pt.STRING})}

    def _set_job_state(self, job_id: str, state: str) -> None:
        with self.db.batch() as b:
            b.update("DeletionJobs", ["job_id", "state"], [[job_id, state]])


def pt_commit() -> Any:
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

    return COMMIT_TIMESTAMP


def keyset_for(keys: list[list[Any]]) -> Any:
    from google.cloud.spanner_v1 import KeySet

    return KeySet(keys=keys)
