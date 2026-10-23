"""
Consumer-domain kernel: the lane's thin adapter over the foundation framework.

The persona, wardrobe, social, rewards and media domains share this module.
Everything with a foundation equivalent comes from the foundation framework:
``Principal``, the error types, ``authorize``/``Grant``, If-Match parsing,
canonical digests, ``run_command``/``run_idempotent_command`` (rows + outbox in
one Spanner transaction) and the closed-schema event registry
(``brandme_core.domains.events``). The V001 ``OutboxEvents`` and
``IdempotencyRecords`` tables back them.

This module adds only what the framework does not provide:

* ``ValidationFailed`` / ``RateLimited`` and an ``extra`` payload on errors
  (problem+json extension members such as mergeable-conflict guidance);
* a deterministic ``Clock`` (domain time; tests freeze it);
* ``ServicePrincipal`` for worker commands (actor_ref ``service:<name>``);
* strict integer / allowlist validation helpers;
* ``command`` / ``idempotent_command`` wrappers that re-run a transaction
  Spanner discarded before commit (proposed deviation PD-04);
* read helpers (``run_read``, ``query``, ``json_value``).
"""

from __future__ import annotations

import json
import math
import os
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Protocol, Tuple, TypeVar

from google.cloud.spanner_v1 import JsonObject, param_types

from brandme_core.domains import (  # noqa: F401  (re-exported for lane modules)
    CommandContext,
    DomainError,
    Forbidden,
    Grant,
    IdempotencyConflict,
    InvalidTransition,
    NotFound,
    PreconditionRequired,
    Principal,
    VersionConflict,
    authorize,
    canonical_digest,
    parse_if_match,
    run_command,
    run_idempotent_command,
)
from brandme_core.domains.events import UUID, closed, register as register_event_type  # noqa: F401

T = TypeVar("T")

ENVIRONMENTS = ("demo", "development", "sandbox", "production")
NIL_MEMBER = "00000000-0000-0000-0000-000000000000"
REVISION = {"type": "string", "pattern": "^(0|[1-9][0-9]{0,17})$"}


# ---------------------------------------------------------------------------
# Errors (extensions of the foundation hierarchy)
# ---------------------------------------------------------------------------


def _with_extra(err: DomainError, extra: Optional[Dict[str, Any]]) -> DomainError:
    err.extra = dict(extra or {})
    return err


class ValidationFailed(DomainError):
    status, code = 422, "validation_failed"

    def __init__(self, detail: str, *, extra: Optional[Dict[str, Any]] = None):
        super().__init__(detail)
        _with_extra(self, extra)


class RateLimited(DomainError):
    status, code, retryable = 429, "rate_limited", True

    def __init__(self, detail: str, *, extra: Optional[Dict[str, Any]] = None):
        super().__init__(detail)
        _with_extra(self, extra)


class DetailedVersionConflict(VersionConflict):
    """A 409 that also tells the client whether its edit can be merged."""

    def __init__(self, detail: str, current_version: int, *, extra: Optional[Dict[str, Any]] = None):
        super().__init__(detail, current_version=current_version)
        _with_extra(self, {"current_version": str(current_version), **(extra or {})})


class DetailedInvalidTransition(InvalidTransition):
    def __init__(self, detail: str, *, code: Optional[str] = None, extra: Optional[Dict[str, Any]] = None):
        super().__init__(detail, code=code)
        _with_extra(self, extra)


def problem_extras(err: Exception) -> Dict[str, Any]:
    extra = dict(getattr(err, "extra", {}) or {})
    cv = getattr(err, "current_version", None)
    if cv is not None and "current_version" not in extra:
        extra["current_version"] = str(cv)
    return extra


def problem_body(err: DomainError, *, instance: str, request_id: str) -> Dict[str, Any]:
    """application/problem+json body for a domain error (ch.03 §6)."""
    title = {
        400: "Bad request", 403: "Not permitted", 404: "Not found", 409: "Conflict",
        422: "The request is not valid", 428: "Precondition required", 429: "Too many requests",
    }.get(err.status, "Error")
    body = {
        "type": f"https://brand.me/problems/{err.code}",
        "title": title,
        "status": err.status,
        "code": err.code,
        "detail": err.detail,
        "instance": instance,
        "request_id": request_id,
        "retryable": bool(getattr(err, "retryable", False)),
    }
    for k, v in problem_extras(err).items():
        body.setdefault(k, v)
    return body


# ---------------------------------------------------------------------------
# Principals
# ---------------------------------------------------------------------------


def member_principal(
    member_id: str,
    scopes: Iterable[str],
    *,
    environment: str = "development",
    subject: Optional[str] = None,
    session_id: Optional[str] = None,
    client_id: Optional[str] = None,
    assurance_level: str = "simulated",
    delegation_id: Optional[str] = None,
) -> Principal:
    return Principal(
        member_id=member_id,
        subject=subject or f"dev|{member_id}",
        session_id=session_id,
        client_id=client_id,
        scopes=frozenset(scopes),
        assurance_level=assurance_level,
        environment=environment,
        delegation_id=delegation_id,
    )


@dataclass(frozen=True)
class ServicePrincipal(Principal):
    """A worker/service actor. It never owns member data, so ``authorize`` on a
    member resource fails for it unless the domain code explicitly allows the
    service path."""

    service: str = "worker"

    @property
    def actor_ref(self) -> str:  # type: ignore[override]
        return f"service:{self.service}"


def service_principal(service: str, *, environment: str = "development") -> ServicePrincipal:
    return ServicePrincipal(
        member_id=NIL_MEMBER,
        subject=f"service|{service}",
        session_id=None,
        client_id=None,
        scopes=frozenset(),
        assurance_level="service",
        environment=environment,
        service=service,
    )


def require_scope(principal: Principal, scope: str) -> None:
    if scope not in principal.scopes:
        raise Forbidden(f"scope {scope} required")


OPERATOR_SCOPE = "moderation:admin"


def require_operator(principal: Principal) -> None:
    """Console operator authority (ch.03 §3): ``moderation:admin``, an aal2 session
    outside development, never a delegated agent or a service."""
    if isinstance(principal, ServicePrincipal) or principal.delegation_id is not None:
        raise Forbidden("operator session required")
    if OPERATOR_SCOPE not in principal.scopes:
        raise Forbidden(f"scope {OPERATOR_SCOPE} required")
    if principal.environment != "development" and principal.assurance_level != "aal2":
        raise Forbidden("operator actions require a recently strengthened (aal2) session")


def require_not_self(principal: Principal, member_id: str) -> None:
    """Operators never review or act on their own records."""
    if principal.member_id == member_id:
        raise Forbidden("operators cannot review or act on their own records")


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """Deterministic clock for tests and demo-session rebasing; never production."""

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


def parse_iso(value: Any, *, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValidationFailed(f"{name} must be an RFC 3339 timestamp", extra={"field": name})
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationFailed(f"{name} must be an RFC 3339 timestamp", extra={"field": name}) from None
    if dt.tzinfo is None:
        raise ValidationFailed(f"{name} needs an explicit UTC offset", extra={"field": name})
    return utc(dt)


def new_id() -> str:
    return str(uuid.uuid4())


def stable_id(namespace: str, *parts: str) -> str:
    """Deterministic UUIDv5 for derived records (idempotent re-derivation)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "brandme:" + namespace + ":" + "|".join(parts)))


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def reject_non_finite(obj: Any) -> Any:
    if isinstance(obj, float) and not math.isfinite(obj):
        raise ValidationFailed("non-finite number in request")
    if isinstance(obj, Mapping):
        for v in obj.values():
            reject_non_finite(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            reject_non_finite(v)
    return obj


def require_strict_int(value: Any, *, name: str, lo: int, hi: int) -> int:
    """Integers only: rejects bool, float (even 5.0), NaN and out-of-range."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationFailed(f"{name} must be an integer", extra={"field": name})
    if value < lo or value > hi:
        raise ValidationFailed(f"{name} must be between {lo} and {hi}", extra={"field": name})
    return value


def require_uuid(value: Any, *, name: str) -> str:
    try:
        return str(uuid.UUID(str(value))) if isinstance(value, str) and len(value) == 36 else _bad_uuid(name)
    except ValueError:
        return _bad_uuid(name)


def _bad_uuid(name: str) -> str:
    raise ValidationFailed(f"{name} must be a UUID", extra={"field": name})


def require_text(value: Any, *, name: str, max_len: int, min_len: int = 1) -> str:
    if not isinstance(value, str) or not (min_len <= len(value.strip()) <= max_len):
        raise ValidationFailed(f"{name} must be {min_len}-{max_len} characters", extra={"field": name})
    return value.strip()


def reject_unknown_keys(body: Mapping[str, Any], allowed: Iterable[str], *, where: str) -> None:
    unknown = sorted(set(body) - set(allowed))
    if unknown:
        raise ValidationFailed(
            f"{where} contains fields that cannot be changed here: {', '.join(unknown)}",
            extra={"rejected_fields": unknown},
        )


def parse_revision(if_match: Optional[str]) -> int:
    """Foundation If-Match parsing (428 when missing); bounded to 18 digits."""
    rev = parse_if_match(if_match)
    if rev > 10**18:
        raise PreconditionRequired("If-Match revision out of range")
    return rev


def require_idempotency_key(key: Optional[str]) -> str:
    if not isinstance(key, str) or not (16 <= len(key) <= 128):
        raise DomainError("Idempotency-Key must be 16-128 characters", code="idempotency_key_invalid")
    return key


# ---------------------------------------------------------------------------
# Opaque cursors (ch.03 §6: opaque, stable tie-breaking, default 24 / max 100)
# ---------------------------------------------------------------------------


def encode_cursor(*parts: Any) -> str:
    import base64

    wire = [iso(p) if isinstance(p, datetime) else p for p in parts]
    raw = json.dumps(wire, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: Any, *, kinds: Tuple[str, ...]) -> Tuple[Any, ...]:
    """Decode and type-check a cursor; ``kinds`` items are 'ts', 'id', 'int' or 'str'."""
    import base64

    bad = ValidationFailed("cursor is not valid", extra={"field": "cursor"})
    if not isinstance(cursor, str) or not (1 <= len(cursor) <= 512):
        raise bad
    try:
        parts = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except Exception:
        raise bad from None
    if not isinstance(parts, list) or len(parts) != len(kinds):
        raise bad
    out = []
    for kind, v in zip(kinds, parts):
        if kind == "ts":
            out.append(parse_iso(v, name="cursor"))
        elif kind == "id":
            out.append(require_uuid(v, name="cursor"))
        elif kind == "int":
            if isinstance(v, bool) or not isinstance(v, int):
                raise bad
            out.append(v)
        elif kind == "str":
            if not isinstance(v, str) or len(v) > 256:
                raise bad
            out.append(v)
        else:
            raise ValueError(kind)
    return tuple(out)


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


def _rolled_back(exc: Exception) -> bool:
    """True when Spanner reports that our (uncommitted) transaction was discarded.

    Production Spanner: NOT_FOUND "Transaction not found" (session reclaimed).
    The emulator also discards concurrent transactions under its
    one-writer-at-a-time policy and reports FAILED_PRECONDITION ("...committed
    or rolledback", "Invalid transaction ID") or NOT_FOUND; those broader
    messages are retryable only when SPANNER_EMULATOR_HOST is set.
    """
    from google.api_core.exceptions import FailedPrecondition, NotFound as GNotFound

    msg = str(exc)
    if isinstance(exc, GNotFound) and "Transaction not found" in msg:
        return True
    if os.environ.get("SPANNER_EMULATOR_HOST") and isinstance(exc, (FailedPrecondition, GNotFound)):
        return any(s in msg for s in ("committed or rolledback", "Invalid transaction ID", "Transaction not found"))
    return False


def _retrying(call: Callable[[], T], max_attempts: int = 40, budget_seconds: float = 60.0) -> T:
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


class _RetryingDatabase:
    """Passes everything through; re-runs whole transactions discarded pre-commit."""

    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def run_in_transaction(self, fn, *a, **kw):
        return _retrying(lambda: self._db.run_in_transaction(fn, *a, **kw))


def command(
    db,
    principal: Principal,
    fn: Callable[[Any, CommandContext], T],
    *,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
) -> T:
    """Foundation ``run_command``: rows + emitted events commit together."""
    ctx = CommandContext(principal=principal, environment=principal.environment, causation_id=causation_id)
    if correlation_id:
        ctx.correlation_id = correlation_id
    return run_command(_RetryingDatabase(db), ctx, fn)


def idempotent_command(
    db,
    principal: Principal,
    operation: str,
    idempotency_key: Optional[str],
    request: Mapping[str, Any],
    fn: Callable[[Any, CommandContext], Dict[str, Any]],
) -> Tuple[Dict[str, Any], bool]:
    """Foundation ``run_idempotent_command``: returns ``(response, replayed)``."""
    ctx = CommandContext(principal=principal, environment=principal.environment)
    reject_non_finite(request)
    return run_idempotent_command(
        _RetryingDatabase(db), ctx, operation, require_idempotency_key(idempotency_key), request, fn
    )


def run_txn(db, fn: Callable[[Any], T]) -> T:
    """Plain read/write transaction with no events (maintenance/test helpers)."""
    return _retrying(lambda: db.run_in_transaction(fn))


def run_read(db, fn: Callable[[Any], T]) -> T:
    """Run ``fn`` against a consistent multi-use read-only snapshot."""

    def call():
        with db.snapshot(multi_use=True) as snap:
            return fn(snap)

    return _retrying(call)


# ---------------------------------------------------------------------------
# Spanner helpers
# ---------------------------------------------------------------------------


def json_value(v: Any) -> Any:
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
        return json.loads(v.serialize()) if hasattr(v, "serialize") else dict(v)
    return v


def query(txn_or_snapshot, sql: str, params: Optional[Dict[str, Any]] = None, types: Optional[Dict[str, Any]] = None) -> List[tuple]:
    return list(txn_or_snapshot.execute_sql(sql, params=params or {}, param_types=types or {}))


STR = param_types.STRING
INT = param_types.INT64
TS = param_types.TIMESTAMP
BOOL = param_types.BOOL
FLOAT = param_types.FLOAT64
STR_ARRAY = param_types.Array(param_types.STRING)


def server_now(txn) -> datetime:
    """Spanner's CURRENT_TIMESTAMP() inside the caller's transaction, as a plain
    UTC datetime (the client's DatetimeWithNanoseconds breaks on ``replace``)."""
    t = query(txn, "SELECT CURRENT_TIMESTAMP()")[0][0]
    return datetime(t.year, t.month, t.day, t.hour, t.minute, t.second, t.microsecond, tzinfo=timezone.utc)


def member_active(txn, member_id: str) -> bool:
    """V001 Members row exists and the account accepts new personal data."""
    rows = query(txn, "SELECT account_state FROM Members WHERE member_id=@m", {"m": member_id}, {"m": STR})
    return bool(rows) and rows[0][0] == "active"
