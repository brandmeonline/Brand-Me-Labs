"""Event envelope, payload registry and validation.

Envelope fields follow docs/design/brandme/03-architecture-data-api.md §5 and
the ``EventEnvelope`` definition in domain.schema.json. ``payload`` is never a
free-form bag: every event type registers an exact payload schema and privacy
class, and an unregistered type cannot be written to the outbox.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional

from jsonschema import Draft202012Validator, FormatChecker

DOMAIN_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "packages/contracts/generated/domain.schema.json"

PRIVACY_CLASSES = ("public", "member_private", "restricted")

# Keys that must never travel in an event payload (raw frames, secrets,
# payment credentials, unrestricted contact data, whole persona vectors).
FORBIDDEN_PAYLOAD_KEYS = frozenset({
    "seed", "seed_phrase", "mnemonic", "private_key", "password", "secret",
    "card_number", "pan", "cvv", "cvc", "access_token", "refresh_token", "id_token",
    "email", "phone", "address", "street_address", "camera_frame", "image_bytes",
    "body_measurements", "declared_axes", "inferred_axes", "effective_axes", "persona",
})


class EventValidationError(ValueError):
    pass


@dataclass(frozen=True)
class EventType:
    event_type: str
    schema_version: str
    payload_schema: Mapping[str, Any]
    privacy_class: str


class EventRegistry:
    def __init__(self) -> None:
        self._types: dict[tuple[str, str], EventType] = {}

    def register(self, event_type: str, schema_version: str, payload_schema: Mapping[str, Any], privacy_class: str) -> EventType:
        if privacy_class not in PRIVACY_CLASSES:
            raise ValueError(f"privacy_class must be one of {PRIVACY_CLASSES}")
        if payload_schema.get("type") != "object" or payload_schema.get("additionalProperties") is not False:
            raise ValueError(f"{event_type}: payload schema must be a closed object (additionalProperties: false)")
        Draft202012Validator.check_schema(payload_schema)
        key = (event_type, schema_version)
        existing = self._types.get(key)
        et = EventType(event_type, schema_version, dict(payload_schema), privacy_class)
        if existing and existing != et:
            raise ValueError(f"{event_type}@{schema_version} already registered with a different contract")
        self._types[key] = et
        return et

    def get(self, event_type: str, schema_version: str) -> EventType:
        try:
            return self._types[(event_type, schema_version)]
        except KeyError:
            raise EventValidationError(f"unregistered event type {event_type}@{schema_version}") from None

    def types(self) -> list[EventType]:
        return sorted(self._types.values(), key=lambda t: (t.event_type, t.schema_version))


registry = EventRegistry()


@lru_cache(maxsize=1)
def _envelope_validator() -> Draft202012Validator:
    schema = json.loads(DOMAIN_SCHEMA_PATH.read_text())
    return Draft202012Validator(
        {"$ref": "#/$defs/EventEnvelope", "$defs": schema["$defs"]}, format_checker=FormatChecker()
    )


def _forbidden_keys(node: Any, path: str = "payload") -> list[str]:
    hits: list[str] = []
    if isinstance(node, Mapping):
        for k, v in node.items():
            if str(k).lower() in FORBIDDEN_PAYLOAD_KEYS:
                hits.append(f"{path}.{k}")
            hits.extend(_forbidden_keys(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hits.extend(_forbidden_keys(v, f"{path}[{i}]"))
    return hits


def _utc_iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class EventEnvelope:
    event_type: str
    schema_version: str
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    environment: str
    actor_ref: str
    correlation_id: str
    privacy_class: str
    payload: dict
    causation_id: Optional[str] = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_wire(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "aggregate_version": str(self.aggregate_version),
            "occurred_at": _utc_iso(self.occurred_at),
            "environment": self.environment,
            "actor_ref": self.actor_ref,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "privacy_class": self.privacy_class,
            "payload": self.payload,
        }

    def validate(self, reg: EventRegistry = registry) -> None:
        errors = [e.message for e in _envelope_validator().iter_errors(self.to_wire())]
        if errors:
            raise EventValidationError(f"{self.event_type}: envelope invalid: {errors[:3]}")
        et = reg.get(self.event_type, self.schema_version)
        if et.privacy_class != self.privacy_class:
            raise EventValidationError(
                f"{self.event_type}: privacy_class {self.privacy_class} != registered {et.privacy_class}"
            )
        forbidden = _forbidden_keys(self.payload)
        if forbidden:
            raise EventValidationError(f"{self.event_type}: forbidden payload fields {forbidden}")
        payload_errors = [e.message for e in Draft202012Validator(et.payload_schema, format_checker=FormatChecker()).iter_errors(self.payload)]
        if payload_errors:
            raise EventValidationError(f"{self.event_type}: payload invalid: {payload_errors[:3]}")

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "EventEnvelope":
        payload = row["payload"]
        if not isinstance(payload, dict):
            payload = json.loads(payload.serialize() if hasattr(payload, "serialize") else str(payload))
        return cls(
            event_id=row["event_id"], event_type=row["event_type"], schema_version=row["schema_version"],
            aggregate_type=row["aggregate_type"], aggregate_id=row["aggregate_id"],
            aggregate_version=int(row["aggregate_version"]), environment=row["environment"],
            actor_ref=row["actor_ref"], correlation_id=row["correlation_id"], causation_id=row["causation_id"],
            privacy_class=row["privacy_class"], payload=payload, occurred_at=row["occurred_at"],
        )
