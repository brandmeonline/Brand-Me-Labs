"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Bridge from the opus-foundation registry (``brandme_core.domains.register_data_category``,
callbacks ``export(database, member_id)`` / ``delete(database, member_id)``)
to the My Data orchestrator, so a domain registered either way is inventoried,
exported, deleted, tombstoned and re-deleted after restore.

Foundation-style deletes run in their own transaction(s) rather than inside
the orchestrator's: the tombstone is written right after, and the processing
freeze (set when the deletion was accepted) already blocks guarded writers in
between. Domains that need the stricter single-transaction behaviour
implement ``DomainPrivacyHandler`` directly.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .deletion import (
    DataCategory, DeletionOutcome, ExportSection, OnDelete, PrivacyRegistry, SubjectContext, Supplier, Tombstone,
)

_SUPPLIERS = {s.value: s for s in Supplier}


class FoundationCategoryHandler:
    """Wraps one foundation ``DataCategory`` (duck-typed: name, domain, description,
    supplied_by, visible_to, retention, export, delete)."""

    transactional = False

    def __init__(self, cat: Any) -> None:
        if cat.delete is None:
            raise ValueError(f"foundation category {cat.name} has no delete callback")
        self.cat = cat
        self.domain = cat.domain
        self.key = cat.name if cat.name.startswith(f"{cat.domain}.") else f"{cat.domain}.{cat.name}"

    def categories(self):
        return [DataCategory(
            key=self.key, domain=self.domain, title=self.cat.description,
            supplied_by=_SUPPLIERS.get(str(self.cat.supplied_by), Supplier.SYSTEM),
            visible_to=(self.cat.visible_to,) if isinstance(self.cat.visible_to, str) else tuple(self.cat.visible_to),
            retention=self.cat.retention, on_edit="See domain", on_delete=OnDelete.ERASE,
        )]

    def export(self, snapshot: Any, ctx: SubjectContext, category: str) -> ExportSection:
        rows: Iterable[dict] = self.cat.export(self._db, ctx.subject_ref) if self.cat.export else []
        notes = [] if self.cat.export else ["This category has no export callback registered."]
        return ExportSection(category, [dict(r) for r in rows], notes=notes)

    def delete(self, txn: Any, ctx: SubjectContext, category: str) -> DeletionOutcome:  # pragma: no cover - not used
        raise RuntimeError("foundation categories delete outside the orchestrator transaction")

    def delete_outside_txn(self, database: Any, ctx: SubjectContext, category: str) -> DeletionOutcome:
        self.cat.delete(database, ctx.subject_ref)
        return DeletionOutcome(category, rows_affected=0, detail="deleted by domain callback (row count not reported)")

    def purge_derived(self, ctx: SubjectContext, category: str) -> DeletionOutcome:
        # Foundation contract: delete() must also suppress re-creation from derived sources.
        return DeletionOutcome(category, 0, detail="derived data handled by the domain's delete callback")

    def reapply_tombstone(self, txn: Any, t: Tombstone) -> int:  # pragma: no cover - not used
        raise RuntimeError("use delete_outside_txn")

    _db: Any = None


def bridge_foundation_categories(reg: PrivacyRegistry, database: Any, categories: Optional[Iterable[Any]] = None) -> int:
    """Register every foundation data category not already registered natively. Returns the count added."""
    if categories is None:
        from brandme_core.domains import data_categories  # foundation framework (present after integration)
        categories = data_categories()
    known = {c.key for c in reg.categories()}
    added = 0
    for cat in categories:
        h = FoundationCategoryHandler(cat)
        if h.key in known:
            continue
        h._db = database
        reg.register(h)
        added += 1
    return added
