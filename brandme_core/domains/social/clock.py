"""Server time for decision deadlines.

Production reads Spanner's ``CURRENT_TIMESTAMP()`` inside the very read/write
transaction that opens, answers or closes a decision. Device clocks are never
consulted. ``FixedTxnClock`` is for deterministic tests and demo-session
rebasing only.

Documented boundary (BM-SOC-005): a response is accepted iff the server time
read inside its own transaction is **strictly before** ``closes_at`` and the
decision is still open. Closing reads every response in a serializable
transaction at server time ``>= closes_at``, so no response can commit after
the close is decided.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from brandme_core.domains.persona.kernel import server_now


class TxnClock(Protocol):
    def now(self, txn) -> datetime: ...


class SpannerTxnClock:
    def now(self, txn) -> datetime:
        return server_now(txn)


class FixedTxnClock:
    def __init__(self, at: datetime):
        if at.tzinfo is None:
            raise ValueError("aware datetime required")
        self._at = at

    def now(self, txn=None) -> datetime:
        return self._at

    def set(self, at: datetime) -> None:
        self._at = at

    def advance(self, seconds: float) -> None:
        self._at += timedelta(seconds=seconds)


def utc_day_start(t: datetime) -> datetime:
    t = t.astimezone(timezone.utc)
    return t.replace(hour=0, minute=0, second=0, microsecond=0)
