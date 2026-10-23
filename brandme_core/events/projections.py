"""Firestore UI projections: field-minimal, monotonic, revocable.

Spec: docs/design/brandme/03-architecture-data-api.md §5 "Cross-device
projection rules". Spanner stays authoritative. A projection is a disposable
read model that a trusted worker writes after an event commits.

Guarantees implemented here:

* Each document holds only the fields its ``ProjectionSpec`` allows, plus
  ``source_version``. Shared documents also refuse private field names
  (owner references, body data, prices, wallet/ownership history), so a
  reducer bug cannot leak them into a friend/public view.
* Writes are monotonic per document: an update whose ``source_version`` is not
  newer than the stored one is ignored, so redelivered or out-of-order events
  never roll a view back.
* Revocation deletes the document *and* records a tombstone at that version.
  A delayed older upsert cannot resurrect a revoked share. Tombstones live in
  a collection that the security rules close to every client.
* ``purge_member`` removes every private projection of a member (deletion jobs).

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

# Never projected into shared documents (ch.03 §5, ch.01 §8).
FORBIDDEN_SHARED_FIELDS = frozenset({
    "owner_id", "member_id", "owner_ref", "subject_ref", "email", "phone", "address",
    "body_measurements", "body_profile", "measurements", "size", "price", "amount",
    "amount_minor", "purchase_receipt", "receipt", "closet_total", "wallet_address",
    "chain_address", "ownership_history", "controller_commitment", "persona",
    "declared_axes", "inferred_axes", "effective_axes",
})

_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class ProjectionError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectionSpec:
    """A projected document kind.

    ``path_template`` has an even number of segments. Placeholders are filled
    from the key; for example ``members/{member_id}/views/profile`` or
    ``shared/{share_id}``. Member-private documents must live under
    ``members/{member_id}/``.
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
            if not self.path_template.startswith("shared/"):
                raise ProjectionError(f"{self.name}: shared projections live under shared/")
            leaked = self.allowed_fields & FORBIDDEN_SHARED_FIELDS
            if leaked:
                raise ProjectionError(f"{self.name}: shared spec allows private fields {sorted(leaked)}")
        reserved = self.allowed_fields & {"source_version", "projected_at", "audience", "expires_at"}
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
                    if str(k).lower() in FORBIDDEN_SHARED_FIELDS:
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


class ProjectionStore:
    """Trusted projection writer over a ``google.cloud.firestore.Client``."""

    def __init__(self, client):
        self.client = client

    def _versions(self, transaction, path: str) -> tuple[int, int]:
        doc = self.client.document(path).get(transaction=transaction)
        stone = self.client.collection(TOMBSTONES).document(_tombstone_id(path)).get(transaction=transaction)
        current = int(doc.get("source_version")) if doc.exists else -1
        tomb = int(stone.get("source_version")) if stone.exists else -1
        return current, tomb

    def apply(self, op: ProjectionOp) -> str:
        """Apply one op. Returns ``applied``, ``stale`` or ``revoked``."""
        from google.cloud import firestore

        if op.source_version < 0:
            raise ProjectionError("source_version must be >= 0")
        path = op.spec.path(op.key)
        if isinstance(op, Upsert):
            _validate_fields(op.spec, op.fields)
            if op.spec.audience == "shared":
                if not op.audience_member_ids:
                    raise ProjectionError(f"{op.spec.name}: shared projection needs an explicit audience")
                if op.expires_at is None:
                    raise ProjectionError(f"{op.spec.name}: shared projection needs expires_at")

        outcome: dict[str, str] = {}

        @firestore.transactional
        def run(transaction):
            current, tomb = self._versions(transaction, path)
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
                if op.spec.audience == "shared":
                    body["audience"] = list(op.audience_member_ids)
                    body["expires_at"] = op.expires_at.astimezone(timezone.utc)
                transaction.set(self.client.document(path), body)
                outcome["r"] = "applied"
            else:
                # A revocation older than the stored view was superseded (the
                # share was re-created later); applying it would delete newer data.
                if op.source_version < current:
                    outcome["r"] = "stale"
                    return
                transaction.delete(self.client.document(path))
                transaction.set(
                    self.client.collection(TOMBSTONES).document(_tombstone_id(path)),
                    {"source_version": max(op.source_version, tomb), "revoked_at": firestore.SERVER_TIMESTAMP},
                )
                outcome["r"] = "applied"

        run(self.client.transaction())
        return outcome["r"]

    def get(self, spec: ProjectionSpec, key: Mapping[str, str]) -> Optional[dict]:
        snap = self.client.document(spec.path(key)).get()
        return snap.to_dict() if snap.exists else None

    def purge_member(self, member_id: str) -> int:
        """Delete every document under ``members/{member_id}`` (deletion jobs). Idempotent."""
        if not _SEGMENT.match(member_id):
            raise ProjectionError("invalid member id")
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
    """Event type → reducer. Reducers are pure: build ops from the envelope
    (plus authorized reads they perform themselves). They never write."""

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
