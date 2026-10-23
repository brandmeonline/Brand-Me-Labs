"""Commerce persistence port plus an in-memory transactional implementation.

The in-memory store mirrors the Spanner read/write transaction contract used in
production (ch.03 §5): domain rows and outbox events (foundation
``EventEnvelope``) commit together or not at all, and nothing inside
``transaction()`` performs provider I/O. Records are
immutable dataclasses replaced on write, so a rollback restores the snapshot.

The Spanner implementation targets tables in V006/V007 and is pending emulator
validation (see lane status file).
"""

from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List

from brandme_core.events import EventEnvelope

TABLES = (
    "carts", "quotes", "delegations", "challenges", "approvals", "reservations",
    "operations", "orders", "idempotency", "webhook_receipts", "outbox", "surface_keys", "ap2_used",
)


class InMemoryCommerceStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tables: Dict[str, Dict[Any, Any]] = {t: {} for t in TABLES}
        self._depth = 0

    @contextmanager
    def transaction(self) -> Iterator["InMemoryCommerceStore"]:
        with self._lock:
            outer = self._depth == 0
            snapshot = {t: dict(rows) for t, rows in self._tables.items()} if outer else None
            self._depth += 1
            try:
                yield self
            except BaseException:
                if outer:
                    self._tables = snapshot  # type: ignore[assignment]
                raise
            finally:
                self._depth -= 1

    # -- generic row access (call inside transaction for read-modify-write) --
    def get(self, table: str, key: Any) -> Any:
        with self._lock:
            return self._tables[table].get(key)

    def put(self, table: str, key: Any, row: Any) -> None:
        with self._lock:
            if self._depth == 0:
                raise RuntimeError("writes require an open transaction")
            self._tables[table][key] = row

    def keys(self, table: str) -> List[Any]:
        with self._lock:
            return list(self._tables[table].keys())

    def rows(self, table: str) -> List[Any]:
        with self._lock:
            return list(self._tables[table].values())

    def emit(self, event: EventEnvelope) -> None:
        event.validate()  # same gate as foundation write_events: registered, closed, no forbidden keys
        self.put("outbox", event.event_id, event)

    def outbox(self) -> List[EventEnvelope]:
        return self.rows("outbox")  # commit (insertion) order


def new_id() -> str:
    return str(uuid.uuid4())
