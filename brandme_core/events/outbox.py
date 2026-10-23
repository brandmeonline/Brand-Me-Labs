"""Transactional outbox writer and lease-based dispatcher.

Write: domain rows and their events commit in one Spanner read/write
transaction (``write_events``). Transaction callbacks may run more than once;
only the committed attempt's rows exist, so retries cannot duplicate events.

Dispatch: ``OutboxDispatcher.run_once`` claims a bounded lease per shard,
delivers outside the transaction with the stable ``event_id`` and marks the
row delivered. Delivery is at least once; consumers dedupe with
``brandme_core.events.inbox``. No component promises exactly-once delivery.
"""
from __future__ import annotations

import hashlib
import json
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional

from .envelope import EventEnvelope, EventRegistry, registry as default_registry

SHARDS = 16
OUTBOX_COLUMNS = (
    "shard", "event_id", "event_type", "schema_version", "aggregate_type", "aggregate_id",
    "aggregate_version", "occurred_at", "environment", "actor_ref", "correlation_id", "causation_id",
    "privacy_class", "payload", "status", "attempts", "next_attempt_at", "created_at",
)


def shard_for(event_id: str) -> int:
    return int(hashlib.sha256(event_id.encode()).hexdigest()[:8], 16) % SHARDS


def write_events(transaction, events: Iterable[EventEnvelope], reg: EventRegistry = default_registry) -> int:
    """Validate and insert events inside the caller's read/write transaction."""
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject

    rows = []
    for ev in events:
        ev.validate(reg)
        rows.append((
            shard_for(ev.event_id), ev.event_id, ev.event_type, ev.schema_version, ev.aggregate_type,
            ev.aggregate_id, ev.aggregate_version, ev.occurred_at, ev.environment, ev.actor_ref,
            ev.correlation_id, ev.causation_id, ev.privacy_class, JsonObject(ev.payload), "pending", 0,
            ev.occurred_at, COMMIT_TIMESTAMP,
        ))
    if rows:
        transaction.insert("OutboxEvents", columns=OUTBOX_COLUMNS, values=rows)
    return len(rows)


@dataclass
class DispatchResult:
    delivered: int = 0
    failed: int = 0
    dead: int = 0


class OutboxDispatcher:
    """Lease-claiming dispatcher. ``deliver`` raises to signal failure."""

    def __init__(self, database, deliver: Callable[[EventEnvelope], None], owner: Optional[str] = None,
                 lease_seconds: int = 30, batch_size: int = 50, max_attempts: int = 10,
                 base_backoff_seconds: float = 1.0, max_backoff_seconds: float = 300.0):
        self.database = database
        self.deliver = deliver
        self.owner = owner or f"dispatcher-{uuid.uuid4().hex[:12]}"
        self.lease_seconds = lease_seconds
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        self.base_backoff = base_backoff_seconds
        self.max_backoff = max_backoff_seconds

    def _claim(self, shard: int) -> list[dict]:
        from google.cloud.spanner_v1 import param_types

        claimed: list[dict] = []

        def _tx(tx):
            claimed.clear()
            rows = tx.execute_sql(
                """SELECT event_id, event_type, schema_version, aggregate_type, aggregate_id, aggregate_version,
                          occurred_at, environment, actor_ref, correlation_id, causation_id, privacy_class,
                          payload, attempts
                   FROM OutboxEvents@{FORCE_INDEX=OutboxByStatus}
                   WHERE shard = @shard
                     AND ((status = 'pending' AND next_attempt_at <= CURRENT_TIMESTAMP())
                          OR (status = 'leased' AND lease_expires_at <= CURRENT_TIMESTAMP()))
                   ORDER BY next_attempt_at
                   LIMIT @n""",
                params={"shard": shard, "n": self.batch_size},
                param_types={"shard": param_types.INT64, "n": param_types.INT64},
            )
            fields = ("event_id", "event_type", "schema_version", "aggregate_type", "aggregate_id",
                      "aggregate_version", "occurred_at", "environment", "actor_ref", "correlation_id",
                      "causation_id", "privacy_class", "payload", "attempts")
            for r in rows:
                claimed.append(dict(zip(fields, r)))
            if claimed:
                tx.execute_update(
                    """UPDATE OutboxEvents
                       SET status = 'leased', lease_owner = @owner,
                           lease_expires_at = TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL @lease SECOND)
                       WHERE shard = @shard AND event_id IN UNNEST(@ids)""",
                    params={"owner": self.owner, "lease": self.lease_seconds, "shard": shard,
                            "ids": [c["event_id"] for c in claimed]},
                    param_types={"owner": param_types.STRING, "lease": param_types.INT64,
                                 "shard": param_types.INT64, "ids": param_types.Array(param_types.STRING)},
                )

        self.database.run_in_transaction(_tx)
        return list(claimed)

    def _finish(self, shard: int, event_id: str, error: Optional[str], attempts: int) -> str:
        from google.cloud.spanner_v1 import param_types

        if error is None:
            sql = """UPDATE OutboxEvents SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP(),
                            lease_owner = NULL, lease_expires_at = NULL, attempts = attempts + 1
                     WHERE shard = @shard AND event_id = @id AND lease_owner = @owner"""
            params = {"shard": shard, "id": event_id, "owner": self.owner}
            types = {"shard": param_types.INT64, "id": param_types.STRING, "owner": param_types.STRING}
            outcome = "delivered"
        else:
            dead = attempts + 1 >= self.max_attempts
            delay = min(self.max_backoff, self.base_backoff * (2 ** attempts)) * (0.5 + random.random() / 2)
            sql = """UPDATE OutboxEvents SET status = @status, attempts = attempts + 1, last_error = @err,
                            lease_owner = NULL, lease_expires_at = NULL,
                            next_attempt_at = TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL @delay_ms MILLISECOND)
                     WHERE shard = @shard AND event_id = @id AND lease_owner = @owner"""
            params = {"status": "dead" if dead else "pending", "err": error[:512], "delay_ms": int(delay * 1000),
                      "shard": shard, "id": event_id, "owner": self.owner}
            types = {"status": param_types.STRING, "err": param_types.STRING, "delay_ms": param_types.INT64,
                     "shard": param_types.INT64, "id": param_types.STRING, "owner": param_types.STRING}
            outcome = "dead" if dead else "failed"
        self.database.run_in_transaction(lambda tx: tx.execute_update(sql, params=params, param_types=types))
        return outcome

    def run_once(self, shards: Optional[Iterable[int]] = None) -> DispatchResult:
        result = DispatchResult()
        for shard in (range(SHARDS) if shards is None else shards):
            for row in self._claim(shard):
                ev = EventEnvelope.from_row(row)
                try:
                    self.deliver(ev)
                    err = None
                except Exception as exc:  # delivery failure is data, not a crash
                    err = f"{type(exc).__name__}: {exc}"
                outcome = self._finish(shard, ev.event_id, err, int(row["attempts"]))
                setattr(result, outcome, getattr(result, outcome) + 1)
        return result


def json_payload(value) -> dict:
    """Spanner JSON values come back as JsonObject; normalise to dict."""
    if isinstance(value, dict):
        return dict(value)
    return json.loads(value.serialize())
