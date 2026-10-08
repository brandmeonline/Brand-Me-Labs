"""Spanner implementation of the delegated-budget reservation (BM-COM-007).

The availability check and the reservation insert run inside one Spanner
read/write transaction. Concurrent reservations against the same delegation
conflict on the read set; Spanner aborts one and the client retries it with a
fresh read, so the sum of reserved+consumed−credited never exceeds the limit.
No provider I/O happens inside the transaction callback.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from google.cloud.spanner_v1 import param_types

from .errors import BudgetExceeded
from .money import Money


class SpannerBudgetLedger:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def _spent(tx, delegation_id: str, window_start: datetime) -> int:
        rows = tx.execute_sql(
            """SELECT
                 COALESCE(SUM(CASE WHEN kind = 'reservation' AND state IN ('reserved', 'consumed')
                                   THEN amount_minor ELSE 0 END), 0)
               - COALESCE(SUM(CASE WHEN kind = 'credit' AND state = 'credited' THEN amount_minor ELSE 0 END), 0)
               FROM DelegationBudgetEntries
               WHERE delegation_id = @d AND created_at >= @since""",
            params={"d": delegation_id, "since": window_start},
            param_types={"d": param_types.STRING, "since": param_types.TIMESTAMP})
        return max(0, list(rows)[0][0])

    def reserve(self, *, delegation_id: str, operation_id: str, amount: Money, limit: Money,
                window_start: datetime, now: datetime) -> str:
        if amount.currency != limit.currency:
            raise BudgetExceeded("currency differs from the grant")
        entry_id = str(uuid.uuid4())

        def txn(tx):
            if self._spent(tx, delegation_id, window_start) + amount.amount_minor > limit.amount_minor:
                raise BudgetExceeded("purchase exceeds the remaining delegated budget")
            tx.insert("DelegationBudgetEntries",
                      columns=("delegation_id", "entry_id", "operation_id", "kind", "state", "amount_minor",
                               "currency", "created_at"),
                      values=[(delegation_id, entry_id, operation_id, "reservation", "reserved",
                               amount.amount_minor, amount.currency, now)])

        self.database.run_in_transaction(txn)
        return entry_id

    def set_state(self, *, delegation_id: str, operation_id: str, from_state: str, to_state: str) -> int:
        def txn(tx):
            return tx.execute_update(
                """UPDATE DelegationBudgetEntries SET state = @to
                   WHERE delegation_id = @d AND operation_id = @op AND kind = 'reservation' AND state = @from""",
                params={"to": to_state, "d": delegation_id, "op": operation_id, "from": from_state},
                param_types={"to": param_types.STRING, "d": param_types.STRING, "op": param_types.STRING,
                             "from": param_types.STRING})
        return self.database.run_in_transaction(txn)

    def spent(self, delegation_id: str, window_start: datetime) -> int:
        with self.database.snapshot() as snap:
            return self._spent(snap, delegation_id, window_start)
