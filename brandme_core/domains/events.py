"""Domain event registration helpers and the identity/platform event types.

Each domain registers its event types (exact payload schema + privacy class)
at import time. ``write_events`` rejects anything unregistered.
"""
from __future__ import annotations

from typing import Any, Mapping

from brandme_core.events import registry

UUID = {"type": "string", "format": "uuid"}


def closed(properties: Mapping[str, Any], required: tuple[str, ...]) -> dict:
    """Build a closed object schema (additionalProperties: false)."""
    return {"type": "object", "additionalProperties": False, "properties": dict(properties), "required": list(required)}


def register(event_type: str, schema_version: str, payload_schema: Mapping[str, Any], privacy_class: str):
    return registry.register(event_type, schema_version, payload_schema, privacy_class)


# Identity / platform events owned by the foundation lane.
MEMBER_CREATED = register(
    "member.created", "1",
    closed({"member_id": UUID, "identity_provider": {"type": "string", "maxLength": 40}}, ("member_id", "identity_provider")),
    "member_private",
)
MEMBER_UPDATED = register(
    "member.updated", "1",
    closed({"member_id": UUID, "changed_fields": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 16}},
           ("member_id", "changed_fields")),
    "member_private",
)
CONSENT_REVOKED = register(
    "consent.revoked", "1",
    closed({"member_id": UUID, "consent_id": UUID, "purpose": {"type": "string", "maxLength": 64}},
           ("member_id", "consent_id", "purpose")),
    "member_private",
)
SESSION_REVOKED = register(
    "session.revoked", "1",
    closed({"member_id": UUID, "reason": {"type": "string", "enum": ["sign_out", "account_switch", "security", "deletion"]}},
           ("member_id", "reason")),
    "restricted",
)
