"""Commerce persistence port: transactional callbacks plus named, indexed reads.

The service never scans tables. It reads through ``get`` and the named queries
below, and writes only inside ``store.run(fn)``: ``fn(tx)`` sees its own
writes, commits domain rows and outbox events (foundation ``EventEnvelope``)
together, and may be retried, so it must never perform provider I/O (ch.03 §5).

Two implementations share the query predicates defined here:

* ``InMemoryCommerceStore`` — deterministic tests; ``run`` serializes on a lock
  and restores a snapshot on error.
* ``SpannerCommerceStore`` (``spanner_store.py``) — V006/V007 tables through
  ``database.run_in_transaction``; outbox via foundation ``write_events``.
"""

from __future__ import annotations

import threading
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple, TypeVar

from brandme_core.events import EventEnvelope

T = TypeVar("T")

# True while a ``store.run`` callback executes in this context. Code that must never do slow or
# external I/O inside a transaction (a model call, ch.03 §5) checks it instead of trusting layout.
IN_STORE_TRANSACTION: ContextVar[bool] = ContextVar("commerce_in_store_transaction", default=False)


def in_store_transaction() -> bool:
    return IN_STORE_TRANSACTION.get()

TABLES = (
    "carts", "quotes", "delegations", "challenges", "approvals", "reservations", "operations", "orders",
    "idempotency", "webhook_receipts", "outbox", "surface_keys", "ap2_used", "returns",
)

# name -> (logical table, predicate factory). The Spanner store pairs each with SQL
# over an index; the predicate also filters rows written earlier in the same transaction.
Predicate = Callable[[Any], bool]
QUERIES: Mapping[str, Tuple[str, Callable[..., Predicate]]] = {
    "active_delegations": ("delegations", lambda member_id, client_id, now: (
        lambda d: d.member_id == member_id and d.client_id == client_id and d.is_active(now))),
    "operations_for_delegation": ("operations", lambda delegation_id: (
        lambda o: o.delegation_id == delegation_id)),
    "operations_for_quote_hash": ("operations", lambda quote_hash: (lambda o: o.quote_hash == quote_hash)),
    "operations_in_state": ("operations", lambda provider_id, state: (
        lambda o: o.provider_id == provider_id and o.state == state)),
    "orders_by_provider_ref": ("orders", lambda provider_id, provider_order_ref: (
        lambda o: o.provider_id == provider_id and o.provider_order_ref == provider_order_ref)),
    "budget_entries": ("reservations", lambda delegation_id: (lambda e: e.delegation_id == delegation_id)),
    "budget_entries_for_operation": ("reservations", lambda operation_id: (
        lambda e: e.operation_id == operation_id)),
    "surface_keys": ("surface_keys", lambda member_id: (lambda row: row[0] == member_id)),
    # Operator queue (no member filter; the caller holds an operator role).
    "operations_by_state": ("operations", lambda state: (lambda o: o.state == state)),
    "webhook_receipts_pending": ("webhook_receipts", lambda: (lambda r: r.state == "pending_reconcile")),
    "returns_for_order": ("returns", lambda order_id: (lambda r: r.order_id == order_id)),
    # Privacy jobs (export/deletion) walk a member's rows.
    "delegations_for_member": ("delegations", lambda member_id: (lambda d: d.member_id == member_id)),
    "operations_for_member": ("operations", lambda member_id: (lambda o: o.member_id == member_id)),
    "carts_for_member": ("carts", lambda member_id: (lambda c: c.member_id == member_id)),
    "quotes_for_member": ("quotes", lambda member_id: (lambda row: row[0] == member_id)),
    "challenges_for_member": ("challenges", lambda member_id: (lambda c: c.member_id == member_id)),
    "approvals_for_member": ("approvals", lambda member_id: (lambda a: a.member_id == member_id)),
    "idempotency_for_member": ("idempotency", lambda member_id: (lambda r: r.scope[0] == member_id)),
}


class QueryMixin:
    """Named reads; each implementation provides ``_query(name, **params)``."""

    def _query(self, name: str, **params: Any) -> List[Any]:  # pragma: no cover - interface
        raise NotImplementedError

    def active_delegations(self, member_id: str, client_id: str, now: datetime) -> List[Any]:
        return self._query("active_delegations", member_id=member_id, client_id=client_id, now=now)

    def operations_for_delegation(self, delegation_id: str) -> List[Any]:
        return self._query("operations_for_delegation", delegation_id=delegation_id)

    def operations_for_quote_hash(self, quote_hash: str) -> List[Any]:
        return self._query("operations_for_quote_hash", quote_hash=quote_hash)

    def operations_in_state(self, provider_id: str, state: str) -> List[Any]:
        return self._query("operations_in_state", provider_id=provider_id, state=state)

    def order_by_provider_ref(self, provider_id: str, provider_order_ref: str) -> Optional[Any]:
        rows = self._query("orders_by_provider_ref", provider_id=provider_id,
                           provider_order_ref=provider_order_ref)
        return rows[0] if rows else None

    def operations_by_state(self, state: str) -> List[Any]:
        return self._query("operations_by_state", state=state)

    def webhook_receipts_pending(self) -> List[Any]:
        return self._query("webhook_receipts_pending")

    def returns_for_order(self, order_id: str) -> List[Any]:
        return self._query("returns_for_order", order_id=order_id)

    def budget_entries(self, delegation_id: str) -> List[Any]:
        return self._query("budget_entries", delegation_id=delegation_id)

    def budget_entries_for_operation(self, operation_id: str) -> List[Any]:
        return self._query("budget_entries_for_operation", operation_id=operation_id)

    def surface_keys(self, member_id: str) -> List[Dict[str, Any]]:
        """Registered public JWKs for the member (rows are ``(member_id, kid, jwk)``)."""
        return [row[2] for row in self._query("surface_keys", member_id=member_id)]

    def surface_key_ids(self, member_id: str) -> List[Tuple[str, str]]:
        return [(row[0], row[1]) for row in self._query("surface_keys", member_id=member_id)]

    def for_member(self, table: str, member_id: str) -> List[Any]:
        return self._query(f"{table}_for_member", member_id=member_id)


class InMemoryCommerceStore(QueryMixin):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tables: Dict[str, Dict[Any, Any]] = {t: {} for t in TABLES}
        self._depth = 0
        # In-memory stand-in for the V009 ProcessingFreezes rows: (member_id, category or "*").
        self._frozen: Set[Tuple[str, str]] = set()

    def run(self, fn: Callable[["InMemoryCommerceStore"], T]) -> T:
        """Atomic unit of work; a nested call joins the outer one."""
        with self._lock:
            outer = self._depth == 0
            snapshot = {t: dict(rows) for t, rows in self._tables.items()} if outer else None
            self._depth += 1
            token = IN_STORE_TRANSACTION.set(True)
            try:
                return fn(self)
            except BaseException:
                if outer:
                    self._tables = snapshot  # type: ignore[assignment]
                raise
            finally:
                IN_STORE_TRANSACTION.reset(token)
                self._depth -= 1

    # -- row access --------------------------------------------------------
    def get(self, table: str, key: Any) -> Any:
        with self._lock:
            return self._tables[table].get(key)

    def put(self, table: str, key: Any, row: Any) -> None:
        with self._lock:
            if self._depth == 0:
                raise RuntimeError("writes require store.run()")
            self._tables[table][key] = row

    def delete(self, table: str, key: Any) -> None:
        with self._lock:
            if self._depth == 0:
                raise RuntimeError("writes require store.run()")
            self._tables[table].pop(key, None)

    def rows(self, table: str) -> List[Any]:
        """Whole-table read for tests and introspection; domain code uses named queries."""
        with self._lock:
            return list(self._tables[table].values())

    def _query(self, name: str, **params: Any) -> List[Any]:
        table, factory = QUERIES[name]
        pred = factory(**params)
        with self._lock:
            if table == "surface_keys":
                return [(k[0], k[1], v) for k, v in self._tables[table].items() if pred(k)]
            return [r for r in self._tables[table].values() if pred(r)]

    # -- My Data processing guard ------------------------------------------
    def freeze(self, member_id: str, category: str = "*") -> None:
        self._frozen.add((member_id, category))

    def unfreeze(self, member_id: str, category: str = "*") -> None:
        self._frozen.discard((member_id, category))

    def assert_processing_allowed(self, member_id: str, category: str, basis_time: datetime) -> None:
        from brandme_core.domains.privacy.deletion import ProcessingFrozenError
        if (member_id, category) in self._frozen or (member_id, "*") in self._frozen:
            raise ProcessingFrozenError(f"processing frozen for {category}")

    # -- outbox ------------------------------------------------------------
    def emit(self, event: EventEnvelope) -> None:
        event.validate()  # same gate as foundation write_events: registered, closed, no forbidden keys
        self.put("outbox", event.event_id, event)

    def outbox(self) -> List[EventEnvelope]:
        return self.rows("outbox")  # commit (insertion) order


def new_id() -> str:
    return str(uuid.uuid4())
