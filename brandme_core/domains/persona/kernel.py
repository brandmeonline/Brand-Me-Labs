"""
Consumer-domain kernel (interim).

Shared primitives used by the persona, wardrobe, social, rewards and media
domains: principal, clock, typed domain errors, canonical digests, the
transactional outbox writer and the idempotency-record helper.

INTERIM: the opus-foundation lane owns ``brandme_core/domains/base.py``,
``brandme_core/domains/events.py`` and ``brandme_core/events/``. Those files did
not exist when this lane started (see docs/build/status/opus-consumer-domains.md).
This module mirrors the chapter-03 contracts so the domains can be built and
tested now; at integration it should become a thin re-export of the foundation
framework. Table names used here (``OutboxEvents``, ``IdempotencyRecords``) are
provisioned by ``tests/fixtures/persona/interim_foundation.sql`` until V001
lands.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Mapping, Optional, Protocol

from google.cloud import spanner
from google.cloud.spanner_v1 import JsonObject, param_types

ENVIRONMENTS = ("demo", "development", "sandbox", "production")
PRIVACY_CLASSES = ("public", "member_private", "restricted")
OUTBOX_SHARDS = 16


# ---------------------------------------------------------------------------
# Errors -> application/problem+json
# ---------------------------------------------------------------------------


class DomainError(Exception):
    status = 400
    code = "bad_request"
    title = "Bad request"
    retryable = False

    def __init__(self, detail: str, *, extra: Optional[Dict[str, Any]] = None):
        super().__init__(detail)
        self.detail = detail
        self.extra = extra or {}

    def to_problem(self, instance: str, request_id: str) -> Dict[str, Any]:
        body = {
            "type": f"https://brand.me/problems/{self.code}",
            "title": self.title,
            "status": self.status,
            "code": self.code,
            "detail": self.detail,
            "instance": instance,
            "request_id": request_id,
            "retryable": self.retryable,
        }
        body.update(self.extra)
        return body


class ValidationFailed(DomainError):
    status = 422
    code = "validation_failed"
    title = "The request is not valid"


class NotFound(DomainError):
    """Also used for unauthorized private resources so existence does not leak."""

    status = 404
    code = "not_found"
    title = "Not found"


class VersionConflict(DomainError):
    status = 409
    code = "version_conflict"
    title = "The resource changed since you loaded it"


class IdempotencyConflict(DomainError):
    status = 409
    code = "idempotency_key_reused"
    title = "Idempotency key was used with a different request"


class InvalidTransition(DomainError):
    status = 422
    code = "invalid_transition"
    title = "That action is not valid in the current state"


class RateLimited(DomainError):
    status = 429
    code = "rate_limited"
    title = "Too many requests"
    retryable = True


class Forbidden(DomainError):
    """Use only where revealing existence is harmless (own resource, missing scope)."""

    status = 403
    code = "forbidden"
    title = "Not permitted"


# ---------------------------------------------------------------------------
# Principal and clock
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Principal:
    member_id: str
    scopes: FrozenSet[str]
    environment: str = "development"
    session_id: Optional[str] = None
    client_id: Optional[str] = None
    delegation_id: Optional[str] = None
    operator_roles: FrozenSet[str] = frozenset()

    def require(self, scope: str) -> None:
        if scope not in self.scopes:
            raise Forbidden(f"missing scope {scope}")

    @property
    def actor_ref(self) -> str:
        return f"member:{self.member_id}"


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """Deterministic test clock. Never used outside tests/demo rebasing."""

    def __init__(self, at: datetime):
        if at.tzinfo is None:
            raise ValueError("FixedClock requires an aware datetime")
        self._at = at

    def now(self) -> datetime:
        return self._at

    def set(self, at: datetime) -> None:
        self._at = at

    def advance(self, seconds: float) -> None:
        self._at = self._at + timedelta(seconds=seconds)


def utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime")
    return dt.astimezone(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return utc(dt).isoformat().replace("+00:00", "Z")


def new_id() -> str:
    return str(uuid.uuid4())


def stable_id(namespace: str, *parts: str) -> str:
    """Deterministic UUIDv5 for idempotent derived records."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "brandme:" + namespace + ":" + "|".join(parts)))


# ---------------------------------------------------------------------------
# Canonical encoding
# ---------------------------------------------------------------------------


def _reject_non_finite(obj: Any) -> Any:
    if isinstance(obj, float) and not math.isfinite(obj):
        raise ValidationFailed("non-finite number in request")
    if isinstance(obj, dict):
        return {str(k): _reject_non_finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_reject_non_finite(v) for v in obj]
    return obj


def canonical_json(obj: Any) -> str:
    return json.dumps(_reject_non_finite(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def canonical_digest(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def require_strict_int(value: Any, *, name: str, lo: int, hi: int) -> int:
    """Integers only: rejects bool, float (even 5.0), NaN and out-of-range."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationFailed(f"{name} must be an integer", extra={"field": name})
    if value < lo or value > hi:
        raise ValidationFailed(f"{name} must be between {lo} and {hi}", extra={"field": name})
    return value


def reject_unknown_keys(body: Mapping[str, Any], allowed: Iterable[str], *, where: str) -> None:
    unknown = sorted(set(body) - set(allowed))
    if unknown:
        raise ValidationFailed(
            f"{where} contains fields that cannot be changed here: {', '.join(unknown)}",
            extra={"rejected_fields": unknown},
        )


def parse_revision(if_match: Optional[str]) -> int:
    if if_match is None:
        raise ValidationFailed("If-Match is required", extra={"field": "If-Match"})
    raw = if_match.strip()
    if raw.startswith("W/"):
        raise ValidationFailed("weak validators are not accepted")
    raw = raw.strip('"')
    if not raw.isdigit() or (len(raw) > 1 and raw[0] == "0") or len(raw) > 18:
        raise ValidationFailed("If-Match must be a revision string", extra={"field": "If-Match"})
    return int(raw)


# ---------------------------------------------------------------------------
# Transactional outbox
# ---------------------------------------------------------------------------

# Exact payload keys per event type. Payloads carry internal references and
# minimal data only (ch.03 §5). Unknown event types or extra keys are rejected.
EVENT_PAYLOAD_KEYS: Dict[str, FrozenSet[str]] = {}


def register_event(event_type: str, keys: Iterable[str]) -> None:
    keyset = frozenset(keys)
    existing = EVENT_PAYLOAD_KEYS.get(event_type)
    if existing is not None and existing != keyset:
        raise RuntimeError(f"conflicting registration for {event_type}")
    EVENT_PAYLOAD_KEYS[event_type] = keyset


OUTBOX_COLUMNS = (
    "shard",
    "event_id",
    "event_type",
    "schema_version",
    "aggregate_type",
    "aggregate_id",
    "aggregate_version",
    "occurred_at",
    "environment",
    "actor_ref",
    "correlation_id",
    "causation_id",
    "privacy_class",
    "payload",
    "status",
    "attempts",
    "next_attempt_at",
    "created_at",
)


@dataclass
class OutboxEvent:
    event_type: str
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    payload: Dict[str, Any]
    actor_ref: str
    environment: str
    occurred_at: datetime
    privacy_class: str = "member_private"
    schema_version: str = "1"
    correlation_id: str = field(default_factory=new_id)
    causation_id: Optional[str] = None
    event_id: str = field(default_factory=new_id)

    def validate(self) -> None:
        keys = EVENT_PAYLOAD_KEYS.get(self.event_type)
        if keys is None:
            raise RuntimeError(f"unregistered event type {self.event_type}")
        if set(self.payload) != keys:
            raise RuntimeError(
                f"payload for {self.event_type} must have exactly {sorted(keys)}, got {sorted(self.payload)}"
            )
        if self.environment not in ENVIRONMENTS:
            raise RuntimeError("bad environment")
        if self.privacy_class not in PRIVACY_CLASSES:
            raise RuntimeError("bad privacy class")

    def envelope(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "aggregate_version": str(self.aggregate_version),
            "occurred_at": iso(self.occurred_at),
            "environment": self.environment,
            "actor_ref": self.actor_ref,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "privacy_class": self.privacy_class,
            "payload": self.payload,
        }


def shard_for(aggregate_id: str) -> int:
    return int(hashlib.sha256(aggregate_id.encode()).hexdigest()[:8], 16) % OUTBOX_SHARDS


def write_outbox(txn, events: List[OutboxEvent]) -> None:
    """Buffer outbox rows inside the caller's read/write transaction.

    Because the rows are mutations in the same transaction as the domain
    change, an aborted/retried transaction cannot leave a duplicate or orphan
    event: either everything commits once or nothing does.
    """
    if not events:
        return
    rows = []
    for ev in events:
        ev.validate()
        rows.append(
            (
                shard_for(ev.aggregate_id),
                ev.event_id,
                ev.event_type,
                ev.schema_version,
                ev.aggregate_type,
                ev.aggregate_id,
                ev.aggregate_version,
                ev.occurred_at,
                ev.environment,
                ev.actor_ref,
                ev.correlation_id,
                ev.causation_id,
                ev.privacy_class,
                JsonObject(ev.payload),
                "pending",
                0,
                ev.occurred_at,
                spanner.COMMIT_TIMESTAMP,
            )
        )
    txn.insert("OutboxEvents", columns=OUTBOX_COLUMNS, values=rows)


# ---------------------------------------------------------------------------
# Idempotency records
# ---------------------------------------------------------------------------


@dataclass
class IdempotencyHit:
    response: Dict[str, Any]


def idempotency_lookup(txn, principal: Principal, operation: str, key: str, request_digest: str) -> Optional[IdempotencyHit]:
    if not key or len(key) > 128:
        raise ValidationFailed("Idempotency-Key is required (1-128 chars)", extra={"field": "Idempotency-Key"})
    rows = list(
        txn.execute_sql(
            "SELECT request_digest, response FROM IdempotencyRecords "
            "WHERE principal_ref = @p AND environment = @e AND operation = @o AND idempotency_key = @k",
            params={"p": principal.actor_ref, "e": principal.environment, "o": operation, "k": key},
            param_types={"p": param_types.STRING, "e": param_types.STRING, "o": param_types.STRING, "k": param_types.STRING},
        )
    )
    if not rows:
        return None
    digest, response = rows[0]
    if digest != request_digest:
        raise IdempotencyConflict("this Idempotency-Key was already used for a different request")
    return IdempotencyHit(response=_json_value(response))


def idempotency_store(
    txn,
    principal: Principal,
    operation: str,
    key: str,
    request_digest: str,
    response: Dict[str, Any],
    now: datetime,
    retention_days: int = 30,
) -> None:
    txn.insert(
        "IdempotencyRecords",
        columns=(
            "principal_ref",
            "environment",
            "operation",
            "idempotency_key",
            "request_digest",
            "response",
            "created_at",
            "expires_at",
        ),
        values=[
            (
                principal.actor_ref,
                principal.environment,
                operation,
                key,
                request_digest,
                JsonObject(response),
                spanner.COMMIT_TIMESTAMP,
                now + timedelta(days=retention_days),
            )
        ],
    )


# ---------------------------------------------------------------------------
# Spanner helpers
# ---------------------------------------------------------------------------


def _json_value(v: Any) -> Any:
    """Normalise a Spanner JSON cell to plain Python."""
    if v is None:
        return None
    if isinstance(v, str):
        return json.loads(v)
    if isinstance(v, JsonObject):
        if getattr(v, "_is_null", False):
            return None
        if getattr(v, "_is_array", False):
            return list(v._array_value)
        if getattr(v, "_is_scalar_value", False):
            return v._simple_value
        return dict(v)
    return v


json_value = _json_value


def query(txn_or_snapshot, sql: str, params: Optional[Dict[str, Any]] = None, types: Optional[Dict[str, Any]] = None) -> List[tuple]:
    return list(txn_or_snapshot.execute_sql(sql, params=params or {}, param_types=types or {}))


STR = param_types.STRING
INT = param_types.INT64
TS = param_types.TIMESTAMP
BOOL = param_types.BOOL


def server_now(txn) -> datetime:
    """Spanner's CURRENT_TIMESTAMP() inside the caller's transaction."""
    return query(txn, "SELECT CURRENT_TIMESTAMP()")[0][0]


def _rolled_back(exc: Exception) -> bool:
    """True when Spanner reports that our (uncommitted) transaction was discarded.

    Production Spanner: NOT_FOUND "Transaction not found" (e.g. session
    reclaimed). The emulator additionally discards concurrent transactions under
    its one-writer-at-a-time policy and reports that as FAILED_PRECONDITION
    ("...committed or rolledback", "Invalid transaction ID") or NOT_FOUND; those
    broader messages are only treated as retryable when SPANNER_EMULATOR_HOST
    is set.
    """
    import os

    from google.api_core.exceptions import FailedPrecondition, NotFound as GNotFound

    msg = str(exc)
    if isinstance(exc, GNotFound) and "Transaction not found" in msg:
        return True
    if os.environ.get("SPANNER_EMULATOR_HOST") and isinstance(exc, (FailedPrecondition, GNotFound)):
        return any(s in msg for s in ("committed or rolledback", "Invalid transaction ID", "Transaction not found"))
    return False


def _retrying(call: Callable[[], Any], max_attempts: int, budget_seconds: float) -> Any:
    import random
    import time

    from google.api_core.exceptions import FailedPrecondition, NotFound as GNotFound

    deadline = time.monotonic() + budget_seconds
    attempt = 0
    while True:
        attempt += 1
        try:
            return call()
        except (GNotFound, FailedPrecondition) as exc:
            if not _rolled_back(exc) or attempt >= max_attempts or time.monotonic() > deadline:
                raise
            time.sleep(min(0.5, 0.01 * (2 ** min(attempt, 6))) * (0.5 + random.random()))


def run_txn(db, fn: Callable[[Any], Any], *, max_attempts: int = 40, budget_seconds: float = 60.0) -> Any:
    """Run ``fn`` in a read/write transaction.

    The client library already retries ABORTED. A transaction discarded before
    commit (see ``_rolled_back``) never committed, and ``fn`` performs no
    external side effects, so re-running the whole function is safe.
    """
    return _retrying(lambda: db.run_in_transaction(fn), max_attempts, budget_seconds)


def run_read(db, fn: Callable[[Any], Any], *, max_attempts: int = 40, budget_seconds: float = 60.0) -> Any:
    """Run ``fn`` against a consistent multi-use read-only snapshot."""

    def call():
        with db.snapshot(multi_use=True) as snap:
            return fn(snap)

    return _retrying(call, max_attempts, budget_seconds)
