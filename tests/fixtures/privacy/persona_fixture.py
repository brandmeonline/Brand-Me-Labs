"""
Test-only stand-in for a consumer domain (the real persona domain belongs to
another lane). It implements the published DomainPrivacyHandler interface the
way a domain is expected to: Spanner rows + a Firestore-like projection + a cache.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from google.cloud.spanner_v1 import KeySet, param_types as pt

from brandme_core.domains.privacy.deletion import (
    DataCategory, DeletionOutcome, ExportSection, OnDelete, SubjectContext, Supplier, Tombstone, assert_processing_allowed,
)

FIXTURE_DDL = [
    """CREATE TABLE FixturePersonaTraits (
         subject_ref STRING(128) NOT NULL, trait STRING(64) NOT NULL, value FLOAT64, source STRING(16) NOT NULL,
         updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true)
       ) PRIMARY KEY (subject_ref, trait)""",
]


class ProjectionStore:
    """Firestore-like projection + read cache."""
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}
        self.cache: dict[str, Any] = {}

    def read_profile(self, subject_ref: str) -> Any:
        return self.cache.get(subject_ref) or self.docs.get(f"profiles/{subject_ref}")


class PersonaFixtureHandler:
    domain = "persona"

    def __init__(self, projections: ProjectionStore) -> None:
        self.p = projections

    def categories(self):
        return [
            DataCategory("persona.declared", "persona", "Style traits you declared", Supplier.MEMBER, ("member",),
                         "Until you delete it", "Edits replace the value immediately", OnDelete.ERASE),
            DataCategory("persona.inferred", "persona", "Style traits Brand.Me inferred", Supplier.INFERRED, ("member",),
                         "Until you delete or reset it", "Corrections lock the trait", OnDelete.ERASE),
        ]

    def _source(self, category: str) -> str:
        return "member" if category == "persona.declared" else "inferred"

    def export(self, snapshot, ctx: SubjectContext, category: str) -> ExportSection:
        rows = snapshot.execute_sql(
            "SELECT trait, value, updated_at FROM FixturePersonaTraits WHERE subject_ref = @s AND source = @src",
            params={"s": ctx.subject_ref, "src": self._source(category)}, param_types={"s": pt.STRING, "src": pt.STRING})
        return ExportSection(category, [{"trait": r[0], "value": r[1], "updated_at": r[2]} for r in rows])

    def delete(self, txn, ctx: SubjectContext, category: str) -> DeletionOutcome:
        n = txn.execute_update(
            "DELETE FROM FixturePersonaTraits WHERE subject_ref = @s AND source = @src",
            params={"s": ctx.subject_ref, "src": self._source(category)}, param_types={"s": pt.STRING, "src": pt.STRING})
        return DeletionOutcome(category, n)

    def purge_derived(self, ctx: SubjectContext, category: str) -> DeletionOutcome:
        n = 0
        if self.p.docs.pop(f"profiles/{ctx.subject_ref}", None) is not None:
            n += 1
        if self.p.cache.pop(ctx.subject_ref, None) is not None:
            n += 1
        return DeletionOutcome(category, n)

    def reapply_tombstone(self, txn, t: Tombstone) -> int:
        return self.delete(txn, SubjectContext(t.subject_ref, t.deletion_job_id, t.created_at), t.category).rows_affected

    # ---- domain writes (what the real domain does) ----
    def write_inference(self, database, subject_ref: str, trait: str, value: float, basis_time: datetime, before_write=None) -> None:
        def fn(txn):
            assert_processing_allowed(txn, subject_ref, "persona.inferred", basis_time)
            if before_write:
                before_write()
            txn.insert_or_update("FixturePersonaTraits", ["subject_ref", "trait", "value", "source", "updated_at"],
                                 [[subject_ref, trait, value, "inferred", __import__("google.cloud.spanner_v1", fromlist=["COMMIT_TIMESTAMP"]).COMMIT_TIMESTAMP]])
        database.run_in_transaction(fn)
        self.p.docs[f"profiles/{subject_ref}"] = {"trait": trait, "value": value}
        self.p.cache[subject_ref] = {"trait": trait, "value": value}

    def declare(self, database, subject_ref: str, trait: str, value: float) -> None:
        from google.cloud.spanner_v1 import COMMIT_TIMESTAMP
        with database.batch() as b:
            b.insert_or_update("FixturePersonaTraits", ["subject_ref", "trait", "value", "source", "updated_at"],
                               [[subject_ref, trait, value, "member", COMMIT_TIMESTAMP]])
        self.p.docs[f"profiles/{subject_ref}"] = {"trait": trait, "value": value}
        self.p.cache[subject_ref] = {"trait": trait, "value": value}

    def count(self, database, subject_ref: str) -> int:
        with database.snapshot() as s:
            return list(s.execute_sql("SELECT COUNT(*) FROM FixturePersonaTraits WHERE subject_ref = @s",
                                      params={"s": subject_ref}, param_types={"s": pt.STRING}))[0][0]
