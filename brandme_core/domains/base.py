"""Domain command framework shared by every consumer domain.

A command: authenticate (``Principal``), load the aggregate version, check
object policy and invariants, then commit domain rows *and* outbox events in
one Spanner read/write transaction (``run_command``). Transaction callbacks
can be retried by Spanner, so they must never call a merchant, upload a blob,
invoke a model or broadcast a chain transaction.

Also provides deny-by-default object authorization, ``If-Match`` parsing,
canonical request digests, idempotent commands and the data-category registry
that export/deletion jobs walk.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Optional, TypeVar

from brandme_core.events import EventEnvelope, write_events

T = TypeVar("T")


# --- errors (mapped to application/problem+json by the HTTP layer) ---------

class DomainError(Exception):
    status = 400
    code = "domain_error"
    retryable = False

    def __init__(self, detail: str, *, code: Optional[str] = None):
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code


class NotFound(DomainError):
    """Also used for unauthorized private resources so existence does not leak."""
    status, code = 404, "not_found"


class Forbidden(DomainError):
    status, code = 403, "forbidden"


class VersionConflict(DomainError):
    status, code = 409, "revision_conflict"

    def __init__(self, detail: str, current_version: Optional[int] = None):
        super().__init__(detail)
        self.current_version = current_version


class PreconditionRequired(DomainError):
    status, code = 428, "if_match_required"


class InvalidTransition(DomainError):
    status, code = 422, "invalid_transition"


class IdempotencyConflict(DomainError):
    status, code = 409, "idempotency_key_reused"


# --- principal and policy ---------------------------------------------------

@dataclass(frozen=True)
class Principal:
    member_id: str
    subject: str
    session_id: Optional[str]
    client_id: Optional[str]
    scopes: frozenset[str]
    assurance_level: str
    environment: str
    delegation_id: Optional[str] = None

    @property
    def actor_ref(self) -> str:
        return f"member:{self.member_id}" + (f"/delegation:{self.delegation_id}" if self.delegation_id else "")


@dataclass(frozen=True)
class Grant:
    """An explicit permission another component established (share, friendship, role)."""
    kind: str  # "share" | "friendship" | "role"
    actions: frozenset[str]
    grantee_member_id: Optional[str] = None
    role: Optional[str] = None
    expires_at: Optional[datetime] = None
    revoked: bool = False

    def permits(self, principal: Principal, action: str, now: datetime) -> bool:
        if self.revoked or (self.expires_at and self.expires_at <= now) or action not in self.actions:
            return False
        if self.kind == "role":
            return self.role is not None and f"role:{self.role}" in principal.scopes
        return self.grantee_member_id == principal.member_id


def authorize(principal: Optional[Principal], action: str, owner_member_id: str,
              grants: Iterable[Grant] = (), required_scope: Optional[str] = None,
              blocked: bool = False, now: Optional[datetime] = None) -> None:
    """Deny unless owner, or an unexpired, unrevoked grant permits ``action``.

    Blocking overrides ordinary sharing. Failures raise ``NotFound`` so a
    private resource's existence is not revealed.
    """
    if principal is None:
        raise NotFound("resource not found")
    if required_scope and required_scope not in principal.scopes:
        raise Forbidden(f"scope {required_scope} required")
    if principal.member_id == owner_member_id:
        return
    if blocked:
        raise NotFound("resource not found")
    now = now or datetime.now(timezone.utc)
    if any(g.permits(principal, action, now) for g in grants):
        return
    raise NotFound("resource not found")


def parse_if_match(header: Optional[str]) -> int:
    if not header:
        raise PreconditionRequired("If-Match header with the current revision is required")
    value = header.strip()
    if value.startswith("W/"):
        value = value[2:]
    value = value.strip('"')
    if not value.isdigit():
        raise PreconditionRequired("If-Match must be a quoted decimal revision")
    return int(value)


def expect_version(current: int, expected: int) -> int:
    if current != expected:
        raise VersionConflict(f"expected revision {expected}, current is {current}", current_version=current)
    return current + 1


def canonical_digest(value: Any) -> str:
    """SHA-256 over canonical JSON (sorted keys, no insignificant whitespace)."""
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# --- commands ---------------------------------------------------------------

@dataclass
class CommandContext:
    principal: Principal
    environment: str
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    causation_id: Optional[str] = None
    events: list[EventEnvelope] = field(default_factory=list)

    def emit(self, event_type: str, schema_version: str, aggregate_type: str, aggregate_id: str,
             aggregate_version: int, payload: dict, privacy_class: str) -> EventEnvelope:
        ev = EventEnvelope(
            event_type=event_type, schema_version=schema_version, aggregate_type=aggregate_type,
            aggregate_id=aggregate_id, aggregate_version=aggregate_version, environment=self.environment,
            actor_ref=self.principal.actor_ref, correlation_id=self.correlation_id,
            causation_id=self.causation_id, privacy_class=privacy_class, payload=payload,
        )
        ev.validate()  # fail inside the command, before any commit
        self.events.append(ev)
        return ev


def run_command(database, ctx: CommandContext, fn: Callable[[Any, CommandContext], T]) -> T:
    """Run ``fn(transaction, ctx)`` and commit its rows plus emitted events atomically."""

    def _attempt(tx):
        ctx.events.clear()  # a retried attempt re-emits; only the committed attempt persists
        result = fn(tx, ctx)
        write_events(tx, ctx.events)
        return result

    return database.run_in_transaction(_attempt)


IDEMPOTENCY_TTL = timedelta(days=30)


def run_idempotent_command(database, ctx: CommandContext, operation: str, idempotency_key: str,
                           request: Mapping[str, Any], fn: Callable[[Any, CommandContext], dict],
                           ttl: timedelta = IDEMPOTENCY_TTL) -> tuple[dict, bool]:
    """Execute once per (principal, environment, operation, key).

    Returns ``(response, replayed)``. Reusing a key with a different canonical
    request raises ``IdempotencyConflict``. The record, domain rows and events
    commit together, so concurrent duplicates serialize on the record row.
    """
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject, KeySet

    if not (16 <= len(idempotency_key) <= 128):
        raise DomainError("Idempotency-Key must be 16-128 characters", code="idempotency_key_invalid")
    digest = canonical_digest({"operation": operation, "request": request})
    key = [ctx.principal.actor_ref, ctx.environment, operation, idempotency_key]

    def _attempt(tx):
        ctx.events.clear()
        rows = list(tx.read("IdempotencyRecords", columns=("request_digest", "state", "response_body"),
                            keyset=KeySet(keys=[key])))
        if rows:
            stored_digest, state, body = rows[0]
            if stored_digest != digest:
                raise IdempotencyConflict("Idempotency-Key was used with a different request")
            if state == "completed":
                return (dict(body) if isinstance(body, dict) else json.loads(body.serialize())), True
            raise DomainError("operation in progress", code="operation_in_progress")
        response = fn(tx, ctx)
        write_events(tx, ctx.events)
        tx.insert(
            "IdempotencyRecords",
            columns=("principal_ref", "environment", "operation", "idempotency_key", "request_digest",
                     "state", "response_status", "response_body", "created_at", "expires_at"),
            values=[(*key, digest, "completed", 200, JsonObject(response), COMMIT_TIMESTAMP,
                     datetime.now(timezone.utc) + ttl)],
        )
        return response, False

    return database.run_in_transaction(_attempt)


# --- data categories (export/deletion scaffolding) ----------------------------

@dataclass(frozen=True)
class DataCategory:
    """A category of personal data a domain owns, for My Data, export and deletion.

    ``export`` and ``delete`` are called by the privacy jobs with
    ``(database, member_id)``; ``delete`` must be idempotent and must also
    suppress re-creation from derived sources.
    """
    name: str
    domain: str
    description: str
    supplied_by: str
    visible_to: str
    retention: str
    tables: tuple[str, ...]
    export: Optional[Callable[[Any, str], Iterable[dict]]] = None
    delete: Optional[Callable[[Any, str], None]] = None


_CATEGORIES: dict[str, DataCategory] = {}


def register_data_category(category: DataCategory) -> DataCategory:
    if category.name in _CATEGORIES and _CATEGORIES[category.name] != category:
        raise ValueError(f"data category {category.name} already registered by {_CATEGORIES[category.name].domain}")
    _CATEGORIES[category.name] = category
    return category


def data_categories() -> list[DataCategory]:
    return sorted(_CATEGORIES.values(), key=lambda c: (c.domain, c.name))
