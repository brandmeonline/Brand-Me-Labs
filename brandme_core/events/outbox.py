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
import threading
import uuid
from dataclasses import dataclass
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
    stale: int = 0


class PermanentDeliveryError(Exception):
    """A locally rejected message cannot be repaired by retrying its payload."""


class OutboxDispatcher:
    """One environment, one fresh fenced lease per delivery, bounded work.

    ``deliver`` returns only after a transport acknowledgement. Unknown outcomes
    are retried with the same event ID; consumers must deduplicate that ID.
    A process crash consumes an attempt, so repeated crashes cannot retry forever.
    """

    def __init__(self, database, deliver: Callable[[EventEnvelope], None], *, environment: str,
                 event_types: Optional[Iterable[str]] = None,
                 reg: EventRegistry = default_registry, owner: Optional[str] = None,
                 lease_seconds: int = 30, batch_size: int = 50, max_attempts: int = 10,
                 base_backoff_seconds: float = 1.0, max_backoff_seconds: float = 300.0):
        if environment not in {"demo", "development", "sandbox", "production"}:
            raise ValueError("explicit event environment required")
        if not (1 <= batch_size <= 100 and 1 <= max_attempts <= 100 and 1 <= lease_seconds <= 300):
            raise ValueError("invalid dispatcher bounds")
        if not (0 <= base_backoff_seconds <= max_backoff_seconds <= 3600):
            raise ValueError("invalid retry bounds")
        self.database = database
        self.deliver = deliver
        self.environment = environment
        self.event_types = None if event_types is None else sorted(set(event_types))
        if self.event_types == []:
            raise ValueError("empty event allowlist")
        self.reg = reg
        self.owner = (owner or "dispatcher")[:24]
        self.lease_seconds = lease_seconds
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        self.base_backoff = base_backoff_seconds
        self.max_backoff = max_backoff_seconds
        self._lock = threading.Lock()
        self._next_shard = 0

    def _claim(self, shard: int, seen: Iterable[str] = ()) -> Optional[dict]:
        from google.cloud.spanner_v1 import param_types

        # Unique even if two processes reuse an operator-provided owner name.
        token = f"{self.owner}:{uuid.uuid4().hex}"

        def _tx(tx):
            params = {"shard": shard, "environment": self.environment, "seen": list(seen)}
            types = {"shard": param_types.INT64, "environment": param_types.STRING,
                     "seen": param_types.Array(param_types.STRING)}
            allowlist = ""
            if self.event_types is not None:
                allowlist = " AND event_type IN UNNEST(@event_types)"
                params["event_types"] = self.event_types
                types["event_types"] = param_types.Array(param_types.STRING)
            rows = tx.execute_sql(
                """SELECT event_id, event_type, schema_version, aggregate_type, aggregate_id, aggregate_version,
                          occurred_at, environment, actor_ref, correlation_id, causation_id, privacy_class,
                          payload, attempts
                   FROM OutboxEvents@{FORCE_INDEX=OutboxByEnvironmentStatus}
                   WHERE environment = @environment AND shard = @shard
                     AND event_id NOT IN UNNEST(@seen)
                     AND ((status = 'pending' AND next_attempt_at <= CURRENT_TIMESTAMP())
                          OR (status = 'leased' AND lease_expires_at <= CURRENT_TIMESTAMP()))
                """ + allowlist + " ORDER BY next_attempt_at, event_id LIMIT 1",
                params=params, param_types=types,
            )
            fields = ("event_id", "event_type", "schema_version", "aggregate_type", "aggregate_id",
                      "aggregate_version", "occurred_at", "environment", "actor_ref", "correlation_id",
                      "causation_id", "privacy_class", "payload", "attempts")
            row = next(iter(rows), None)
            if row is None:
                return None
            claimed = dict(zip(fields, row))
            claimed.update(shard=shard, lease_token=token, exhausted=claimed["attempts"] >= self.max_attempts)
            params = {"shard": shard, "id": claimed["event_id"]}
            types = {"shard": param_types.INT64, "id": param_types.STRING}
            if claimed["exhausted"]:
                tx.execute_update("""UPDATE OutboxEvents SET status = 'dead',
                    lease_owner = NULL, lease_expires_at = NULL, last_error = 'delivery_attempts_exhausted'
                    WHERE shard = @shard AND event_id = @id""", params=params, param_types=types)
            else:
                params.update(owner=token, lease=self.lease_seconds)
                types.update(owner=param_types.STRING, lease=param_types.INT64)
                tx.execute_update("""UPDATE OutboxEvents SET status = 'leased', lease_owner = @owner,
                    attempts = attempts + 1,
                    lease_expires_at = TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL @lease SECOND)
                    WHERE shard = @shard AND event_id = @id""", params=params, param_types=types)
                claimed["attempts"] += 1
            return claimed

        return self.database.run_in_transaction(_tx)

    def _finish(self, row: dict, error: Optional[str], permanent: bool = False) -> str:
        from google.cloud.spanner_v1 import param_types

        params = {"shard": row["shard"], "id": row["event_id"], "owner": row["lease_token"]}
        types = {"shard": param_types.INT64, "id": param_types.STRING, "owner": param_types.STRING}
        if error is None:
            sql = """UPDATE OutboxEvents SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP(),
                            lease_owner = NULL, lease_expires_at = NULL, last_error = NULL"""
            outcome = "delivered"
        else:
            dead = permanent or row["attempts"] >= self.max_attempts
            delay = min(self.max_backoff, self.base_backoff * (2 ** min(row["attempts"] - 1, 30))) * (0.5 + random.random() / 2)
            sql = """UPDATE OutboxEvents SET status = @status, last_error = @err,
                            lease_owner = NULL, lease_expires_at = NULL,
                            next_attempt_at = TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL @delay_ms MILLISECOND)"""
            # Only fixed reason codes; never persist exception text, URLs or payloads.
            params.update(status="dead" if dead else "pending", err=error, delay_ms=int(delay * 1000))
            types.update(status=param_types.STRING, err=param_types.STRING, delay_ms=param_types.INT64)
            outcome = "dead" if dead else "failed"
        sql += """ WHERE shard = @shard AND event_id = @id AND status = 'leased'
                   AND lease_owner = @owner AND lease_expires_at > CURRENT_TIMESTAMP()"""
        changed = self.database.run_in_transaction(lambda tx: tx.execute_update(sql, params=params, param_types=types))
        return outcome if changed == 1 else "stale"

    def run_once(self, shards: Optional[Iterable[int]] = None,
                 should_stop: Callable[[], bool] = lambda: False) -> DispatchResult:
        result = DispatchResult()
        with self._lock:
            selected = list(shards) if shards is not None else [(self._next_shard + i) % SHARDS for i in range(SHARDS)]
            if any(type(s) is not int or not 0 <= s < SHARDS for s in selected):
                raise ValueError("invalid shard")
            seen: set[str] = set()
            while len(seen) < self.batch_size:
                progress = False
                for shard in selected:
                    if len(seen) >= self.batch_size or should_stop():
                        return result
                    row = self._claim(shard, seen)
                    if row is None:
                        continue
                    progress = True
                    seen.add(row["event_id"])
                    self._next_shard = (shard + 1) % SHARDS
                    if row["exhausted"]:
                        result.dead += 1
                        continue
                    try:
                        ev = EventEnvelope.from_row(row)
                        ev.validate(self.reg)
                    except (ValueError, TypeError, KeyError):
                        outcome = self._finish(row, "invalid_event", permanent=True)
                    else:
                        try:
                            self.deliver(ev)
                        except PermanentDeliveryError:
                            outcome = self._finish(row, "message_rejected", permanent=True)
                        except Exception:
                            outcome = self._finish(row, "delivery_unconfirmed")
                        else:
                            outcome = self._finish(row, None)
                    setattr(result, outcome, getattr(result, outcome) + 1)
                if not progress:
                    break
        return result


def json_payload(value) -> dict:
    """Spanner JSON values come back as JsonObject; normalise to dict."""
    if isinstance(value, dict):
        return dict(value)
    return json.loads(value.serialize())
