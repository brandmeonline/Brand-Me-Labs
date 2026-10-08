"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Per-domain privacy registration interface (W10).

PUBLISHED INTERFACE — consumer-domain and commerce-agent lanes implement
``DomainPrivacyHandler`` for every domain that stores member data, and call
``register_domain(handler)`` at import time of their domain package. The
privacy orchestrator (``privacy.py``) never knows table names; it only drives
handlers.

Contract for implementers
-------------------------
1. ``categories()`` declares every data category the domain holds, with who
   supplied it, who can see it, its configured retention and what edit/delete
   does. This is the source of the My Data inventory: undeclared data is a bug.
2. ``export(snapshot, ctx)`` returns the member's data for a category from a
   consistent Spanner snapshot. Never include wallet seeds, private keys,
   payment credentials or third-party content that cannot be redistributed
   (return a reference instead). The orchestrator rejects forbidden keys.
3. ``delete(txn, ctx, category)`` removes or anonymizes rows inside the given
   Spanner read/write transaction. It MUST NOT call external services
   (Spanner may retry the callback). Return the rows affected.
4. ``purge_derived(ctx, category)`` runs after the transaction commits:
   projections (Firestore), caches, search indexes, object-storage media.
   It must be idempotent; it is retried until it reports ``done``.
5. ``reapply_tombstone(txn, tombstone)`` re-deletes after a restore from an
   older backup. The default calls ``delete`` for the tombstone's scope.
6. Every writer of personal or derived data in the domain calls
   ``assert_processing_allowed(txn, subject_ref, category, basis_time)`` inside
   the same read/write transaction as its write. That is what prevents a
   queued job (e.g. persona inference) that started before a deletion from
   recreating deleted data.
"""

from __future__ import annotations

import enum
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable


class Supplier(str, enum.Enum):
    MEMBER = "member"            # declared/entered by the member
    INFERRED = "inferred"        # derived by Brand.Me models
    PROVIDER = "provider"        # connected provider (retailer, wallet, etc.)
    PARTNER = "partner"          # issuer/brand/manufacturer attestation
    SYSTEM = "system"            # operational records


class OnDelete(str, enum.Enum):
    ERASE = "erase"
    ANONYMIZE = "anonymize"
    RETAIN_LEGAL = "retain_legal"                      # retained under a stated legal/contract basis
    NOT_ERASABLE_PUBLIC_LEDGER = "not_erasable_public_ledger"  # public chain commitments


@dataclass(frozen=True)
class DataCategory:
    key: str                       # globally unique, "<domain>.<name>"
    domain: str
    title: str
    supplied_by: Supplier
    visible_to: tuple[str, ...]    # e.g. ("member",), ("member", "friends:granted")
    retention: str                 # configured retention in plain language
    on_edit: str
    on_delete: OnDelete
    personal: bool = True
    retention_basis: Optional[str] = None   # required for RETAIN_LEGAL


@dataclass(frozen=True)
class SubjectContext:
    subject_ref: str
    job_id: str
    requested_at: datetime
    record_keys: tuple[str, ...] = ()       # narrower than the whole category, when set


@dataclass
class ExportSection:
    category: str
    records: list[Mapping[str, Any]]
    references: list[Mapping[str, Any]] = field(default_factory=list)  # e.g. public chain refs, licensed media refs
    notes: list[str] = field(default_factory=list)


@dataclass
class DeletionOutcome:
    category: str
    rows_affected: int
    done: bool = True
    exception: Optional[str] = None          # truthful reason when something could not be deleted
    detail: Optional[str] = None


@dataclass(frozen=True)
class Tombstone:
    subject_ref: str
    category: str
    tombstone_id: str
    deletion_job_id: str
    record_keys: tuple[str, ...]
    created_at: datetime


@runtime_checkable
class DomainPrivacyHandler(Protocol):
    domain: str

    def categories(self) -> Sequence[DataCategory]: ...

    def export(self, snapshot: Any, ctx: SubjectContext, category: str) -> ExportSection: ...

    def delete(self, txn: Any, ctx: SubjectContext, category: str) -> DeletionOutcome: ...

    def purge_derived(self, ctx: SubjectContext, category: str) -> DeletionOutcome: ...

    def reapply_tombstone(self, txn: Any, tombstone: Tombstone) -> int: ...


class PrivacyRegistryError(Exception):
    pass


class PrivacyRegistry:
    """Process-wide registry of domain handlers keyed by category."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handlers: dict[str, DomainPrivacyHandler] = {}
        self._categories: dict[str, DataCategory] = {}

    def register(self, handler: DomainPrivacyHandler) -> None:
        if not isinstance(handler, DomainPrivacyHandler):
            raise PrivacyRegistryError(f"{handler!r} does not implement DomainPrivacyHandler")
        cats = list(handler.categories())
        if not cats:
            raise PrivacyRegistryError(f"domain {handler.domain} declares no data categories")
        with self._lock:
            for c in cats:
                if not c.key.startswith(f"{handler.domain}."):
                    raise PrivacyRegistryError(f"category {c.key} must be prefixed with '{handler.domain}.'")
                if c.key in self._categories and self._handlers[c.key] is not handler:
                    raise PrivacyRegistryError(f"category {c.key} already registered")
                if c.on_delete is OnDelete.RETAIN_LEGAL and not c.retention_basis:
                    raise PrivacyRegistryError(f"category {c.key} retains data without a stated retention_basis")
            for c in cats:
                self._categories[c.key] = c
                self._handlers[c.key] = handler

    def unregister_domain(self, domain: str) -> None:
        with self._lock:
            for k in [k for k, c in self._categories.items() if c.domain == domain]:
                del self._categories[k]
                del self._handlers[k]

    def categories(self) -> list[DataCategory]:
        return sorted(self._categories.values(), key=lambda c: c.key)

    def category(self, key: str) -> DataCategory:
        try:
            return self._categories[key]
        except KeyError as e:
            raise PrivacyRegistryError(f"unknown data category {key}") from e

    def handler_for(self, key: str) -> DomainPrivacyHandler:
        self.category(key)
        return self._handlers[key]


#: The default registry used by ``register_domain``.
registry = PrivacyRegistry()


def register_domain(handler: DomainPrivacyHandler, reg: PrivacyRegistry | None = None) -> None:
    (reg or registry).register(handler)


# --------------------------------------------------------------------------
# Processing guard — call inside the writer's own read/write transaction.
# --------------------------------------------------------------------------

class ProcessingFrozenError(Exception):
    """A write of personal/derived data was refused because of a deletion or restriction."""


def assert_processing_allowed(txn: Any, subject_ref: str, category: str, basis_time: datetime) -> None:
    """
    Refuse the write if (a) the subject or this category is frozen, or (b) a
    deletion tombstone for this category is newer than the data the job was
    computed from (``basis_time``). Both rows are read inside ``txn``, so
    Spanner's serializable isolation makes the check race-free against a
    concurrently committing deletion request.
    """
    frozen = list(txn.execute_sql(
        "SELECT category, reason FROM ProcessingFreezes WHERE subject_ref = @s AND category IN UNNEST(@c)",
        params={"s": subject_ref, "c": [category, "*"]},
        param_types=_types({"s": "STRING", "c": "ARRAY<STRING>"}),
    ))
    if frozen:
        raise ProcessingFrozenError(f"processing frozen for {category} ({frozen[0][1]})")
    newer = list(txn.execute_sql(
        "SELECT tombstone_id FROM DeletionTombstones WHERE subject_ref = @s AND category = @c AND created_at >= @t LIMIT 1",
        params={"s": subject_ref, "c": category, "t": basis_time},
        param_types=_types({"s": "STRING", "c": "STRING", "t": "TIMESTAMP"}),
    ))
    if newer:
        raise ProcessingFrozenError(f"{category} was deleted after this job's basis time")


def _types(spec: Mapping[str, str]) -> dict[str, Any]:
    from google.cloud.spanner_v1 import param_types as pt

    m = {"STRING": pt.STRING, "TIMESTAMP": pt.TIMESTAMP, "INT64": pt.INT64, "ARRAY<STRING>": pt.Array(pt.STRING)}
    return {k: m[v] for k, v in spec.items()}


def new_id() -> str:
    return str(uuid.uuid4())
