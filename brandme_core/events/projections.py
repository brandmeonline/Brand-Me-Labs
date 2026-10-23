"""Firestore UI projections: field-minimal, monotonic, revocable.

Spec: docs/design/brandme/03-architecture-data-api.md §5 "Cross-device
projection rules". Spanner stays authoritative. A projection is a disposable
read model that a trusted worker writes after an event commits.

Guarantees implemented here:

* **Full snapshots.** An ``Upsert`` *replaces* the document with the complete
  view at ``source_version``. Reducers must build that view from authoritative
  state (or a payload that carries the whole view), never apply a delta. A
  skipped intermediate version therefore cannot leave the view incomplete.
* **Field-minimal.** Each document holds only the fields its spec allows.
  Shared specs and documents also refuse private field names under any naming
  style (``ownerId``, ``walletAddress``, ``body_measurements`` …), nested ones
  included.
* **Monotonic.** An update not newer than the stored document or its tombstone
  is ignored, so redelivered or out-of-order events never roll a view back.
* **Shared views are per recipient.** A share is written as one document per
  audience member at ``shared/{share_id}/recipients/{member_id}``. A recipient
  can read only their own copy, so no document carries the audience list or
  other members' IDs.
* **Revocation.** Deleting a share removes every recipient copy and records a
  tombstone, so a delayed older upsert cannot resurrect it.
* **Member deletion.** ``purge_member`` removes every private projection and
  records a member-wide marker; later upserts for that member are refused.

Clients never write projections (see packages/firestore-rules). Server
writers also need service IAM and application checks; rules do not replace
server authorization.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Literal, Mapping, Optional, Union

from .envelope import EventEnvelope

Audience = Literal["member_private", "shared"]

TOMBSTONES = "projection_tombstones"
RECIPIENTS = "recipients"
MAX_AUDIENCE = 100  # one transaction writes every recipient copy (Firestore limit 500)

# Stems that mark a field as private in a shared projection (ch.03 §5,
# ch.01 §8). Keys are normalized (lowercase, alphanumerics only) and rejected
# if they contain any stem, so ``ownerId``, ``owner_ref`` and ``walletAddress``
# are all caught.
FORBIDDEN_SHARED_STEMS = (
    "owner", "member", "subject", "audience", "recipient", "email", "phone", "address",
    "body", "measurement", "size", "price", "amount", "cost", "receipt", "total",
    "wallet", "chain", "ownership", "controller", "commitment", "persona", "axes",
)

_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SHARED_TEMPLATE = "shared/{share_id}"


def _normalize(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def is_private_field(key: str) -> bool:
    norm = _normalize(key)
    return any(stem in norm for stem in FORBIDDEN_SHARED_STEMS)


class ProjectionError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectionSpec:
    """A projected document kind.

    Member-private templates address a document under ``members/{member_id}/``
    (even segment count). A shared spec must use exactly ``shared/{share_id}``;
    the store fans it out to per-recipient documents the security rules can
    serve.
    """

    name: str
    audience: Audience
    path_template: str
    allowed_fields: frozenset[str]

    def __post_init__(self) -> None:
        parts = self.path_template.split("/")
        if len(parts) % 2:
            raise ProjectionError(f"{self.name}: path must address a document (even segment count)")
        if self.audience == "member_private" and not self.path_template.startswith("members/{member_id}/"):
            raise ProjectionError(f"{self.name}: member-private projections live under members/{{member_id}}/")
        if self.audience == "shared":
            if self.path_template != _SHARED_TEMPLATE:
                raise ProjectionError(f"{self.name}: shared projections use exactly {_SHARED_TEMPLATE}")
            leaked = sorted(f for f in self.allowed_fields if is_private_field(f))
            if leaked:
                raise ProjectionError(f"{self.name}: shared spec allows private fields {leaked}")
        reserved = self.allowed_fields & {"source_version", "projected_at", "expires_at"}
        if reserved:
            raise ProjectionError(f"{self.name}: reserved field names {sorted(reserved)}")

    def path(self, key: Mapping[str, str]) -> str:
        def fill(m: re.Match) -> str:
            value = str(key.get(m.group(1), ""))
            if not _SEGMENT.match(value):
                raise ProjectionError(f"{self.name}: invalid key segment for {m.group(1)!r}")
            return value
        return re.sub(r"\{(\w+)\}", fill, self.path_template)


@dataclass(frozen=True)
class Upsert:
    """Replace the view with its complete state at ``source_version``."""

    spec: ProjectionSpec
    key: Mapping[str, str]
    fields: Mapping[str, Any]
    source_version: int
    audience_member_ids: tuple[str, ...] = ()
    expires_at: Optional[datetime] = None


@dataclass(frozen=True)
class Delete:
    spec: ProjectionSpec
    key: Mapping[str, str]
    source_version: int


ProjectionOp = Union[Upsert, Delete]


def _tombstone_id(path: str) -> str:
    return hashlib.sha256(path.encode()).hexdigest()


def _member_marker_id(member_id: str) -> str:
    return hashlib.sha256(f"member-purged:{member_id}".encode()).hexdigest()


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def _validate_fields(spec: ProjectionSpec, fields: Mapping[str, Any]) -> None:
    extra = set(fields) - spec.allowed_fields
    if extra:
        raise ProjectionError(f"{spec.name}: fields not allowed {sorted(extra)}")
    if spec.audience == "shared":

        def walk(node: Any, where: str) -> None:
            if isinstance(node, Mapping):
                for k, v in node.items():
                    if is_private_field(k):
                        raise ProjectionError(f"{spec.name}: private field {where}.{k} in a shared projection")
                    walk(v, f"{where}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{where}[{i}]")

        walk(dict(fields), spec.name)
    try:
        json.dumps(fields, default=_json_default)
    except TypeError as exc:
        raise ProjectionError(f"{spec.name}: fields must be JSON-compatible") from exc


def _validate_shared_upsert(op: Upsert) -> None:
    audience = op.audience_member_ids
    if not audience:
        raise ProjectionError(f"{op.spec.name}: shared projection needs an explicit audience")
    if len(audience) > MAX_AUDIENCE or len(set(audience)) != len(audience):
        raise ProjectionError(f"{op.spec.name}: audience must be unique and at most {MAX_AUDIENCE} members")
    for member in audience:
        if not _SEGMENT.match(member):
            raise ProjectionError(f"{op.spec.name}: invalid audience member id")
    if op.expires_at is None:
        raise ProjectionError(f"{op.spec.name}: shared projection needs expires_at")
    if op.expires_at.tzinfo is None or op.expires_at.utcoffset() is None:
        raise ProjectionError(f"{op.spec.name}: expires_at must be timezone-aware (UTC)")


class ProjectionStore:
    """Trusted projection writer over a ``google.cloud.firestore.Client``."""

    def __init__(self, client):
        self.client = client

    def _stone(self, path: str):
        return self.client.collection(TOMBSTONES).document(_tombstone_id(path))

    def _member_marker(self, member_id: str):
        return self.client.collection(TOMBSTONES).document(_member_marker_id(member_id))

    def apply(self, op: ProjectionOp) -> str:
        """Apply one op. Returns ``applied``, ``stale`` or ``revoked``."""
        from google.cloud import firestore

        if op.source_version < 0:
            raise ProjectionError("source_version must be >= 0")
        path = op.spec.path(op.key)
        shared = op.spec.audience == "shared"
        if isinstance(op, Upsert):
            _validate_fields(op.spec, op.fields)
            if shared:
                _validate_shared_upsert(op)
        recipients = self.client.collection(path + "/" + RECIPIENTS) if shared else None
        doc_ref = None if shared else self.client.document(path)
        outcome: dict[str, str] = {}

        @firestore.transactional
        def run(transaction):
            stone = self._stone(path).get(transaction=transaction)
            tomb = int(stone.get("source_version")) if stone.exists else -1
            if shared:
                existing = {snap.id: snap for snap in transaction.get(recipients.select(["source_version"]))}
                current = max((int(s.get("source_version")) for s in existing.values()), default=-1)
            else:
                member_id = op.key.get("member_id", "")
                if self._member_marker(member_id).get(transaction=transaction).exists:
                    outcome["r"] = "revoked"
                    return
                snap = doc_ref.get(transaction=transaction)
                current = int(snap.get("source_version")) if snap.exists else -1

            if isinstance(op, Upsert):
                if op.source_version <= tomb:
                    outcome["r"] = "revoked"
                    return
                if op.source_version <= current:
                    outcome["r"] = "stale"
                    return
                body: dict[str, Any] = dict(op.fields)
                body["source_version"] = op.source_version
                body["projected_at"] = firestore.SERVER_TIMESTAMP
                if shared:
                    body["expires_at"] = op.expires_at.astimezone(timezone.utc)
                    keep = set(op.audience_member_ids)
                    for member in keep:
                        transaction.set(recipients.document(member), body)
                    for member, snap in existing.items():
                        if member not in keep:
                            transaction.delete(snap.reference)
                else:
                    transaction.set(doc_ref, body)
                outcome["r"] = "applied"
                return

            # A revocation older than the stored view was superseded (the share
            # was re-created later); applying it would delete newer data.
            if op.source_version < current:
                outcome["r"] = "stale"
                return
            if shared:
                for snap in existing.values():
                    transaction.delete(snap.reference)
            else:
                transaction.delete(doc_ref)
            transaction.set(self._stone(path), {
                "source_version": max(op.source_version, tomb, current),
                "revoked_at": firestore.SERVER_TIMESTAMP,
            })
            outcome["r"] = "applied"

        run(self.client.transaction())
        return outcome["r"]

    def get(self, spec: ProjectionSpec, key: Mapping[str, str], recipient: Optional[str] = None) -> Optional[dict]:
        """Read a member-private view, or one recipient's copy of a shared view."""
        path = spec.path(key)
        if spec.audience == "shared":
            if recipient is None:
                raise ProjectionError("reading a shared view needs the recipient member id")
            path = f"{path}/{RECIPIENTS}/{recipient}"
        snap = self.client.document(path).get()
        return snap.to_dict() if snap.exists else None

    def purge_member(self, member_id: str) -> int:
        """Delete every document under ``members/{member_id}`` and block re-creation.

        The member-wide marker is written first, so an upsert racing the purge is
        refused; the recursive delete is idempotent and safe to rerun.
        """
        from google.cloud import firestore

        if not _SEGMENT.match(member_id):
            raise ProjectionError("invalid member id")
        self._member_marker(member_id).set({"purged_at": firestore.SERVER_TIMESTAMP})
        root = self.client.collection("members").document(member_id)
        deleted = 0
        stack = [root]
        while stack:
            ref = stack.pop()
            for coll in ref.collections():
                for doc in coll.list_documents():
                    stack.append(doc)
            snap = ref.get()
            if snap.exists:
                ref.delete()
                deleted += 1
        return deleted


Reducer = Callable[[EventEnvelope], Iterable[ProjectionOp]]


@dataclass
class ProjectionRegistry:
    """Event type → reducer. Reducers are pure: they build full-snapshot ops
    from authorized state and never write."""

    reducers: dict[str, Reducer] = field(default_factory=dict)

    def register(self, event_type: str, reducer: Reducer) -> Reducer:
        if event_type in self.reducers and self.reducers[event_type] is not reducer:
            raise ValueError(f"reducer for {event_type} already registered")
        self.reducers[event_type] = reducer
        return reducer

    def apply(self, store: ProjectionStore, event: EventEnvelope) -> list[str]:
        """Apply the event's ops. Unknown types are a no-op (other consumers own them)."""
        reducer = self.reducers.get(event.event_type)
        if reducer is None:
            return []
        return [store.apply(op) for op in reducer(event)]


registry = ProjectionRegistry()
