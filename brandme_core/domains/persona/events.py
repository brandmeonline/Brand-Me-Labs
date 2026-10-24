"""Persona event types, registered with exact closed payload schemas.

Payloads carry references and axis *names* only, never axis values or whole
persona vectors (foundation ``FORBIDDEN_PAYLOAD_KEYS`` enforces the latter).
"""

from __future__ import annotations

from .kernel import REVISION, UUID, closed, register_event_type
from .model import AXIS_KEYS

AXIS_NAMES = {"type": "array", "items": {"type": "string", "enum": list(AXIS_KEYS)}, "maxItems": 12, "uniqueItems": True}
CHANGE_KINDS = [
    "declared",
    "inference",
    "evidence_suppressed",
    "reset_inference",
    "reset_declarations",
    "reset_all",
    "snapshot_restored",
    "context_override",
    "adaptation_accepted",
    "adaptation_applied",
    "guest_migrated",
    "profile_created",
]

PERSONA_UPDATED = register_event_type(
    "persona.updated",
    "1",
    closed(
        {
            "member_id": UUID,
            "profile_version": REVISION,
            "change_kind": {"type": "string", "enum": CHANGE_KINDS},
            "changed_axes": AXIS_NAMES,
        },
        ("member_id", "profile_version", "change_kind", "changed_axes"),
    ),
    "member_private",
)

PERSONA_EVIDENCE_SUPPRESSED = register_event_type(
    "persona.evidence.suppressed",
    "1",
    closed(
        {"member_id": UUID, "profile_version": REVISION, "evidence_id": UUID},
        ("member_id", "profile_version", "evidence_id"),
    ),
    "member_private",
)

PERSONA_SNAPSHOT_SAVED = register_event_type(
    "persona.snapshot.saved",
    "1",
    closed(
        {"member_id": UUID, "snapshot_id": UUID, "profile_version": REVISION, "first_snapshot": {"type": "boolean"}},
        ("member_id", "snapshot_id", "profile_version", "first_snapshot"),
    ),
    "member_private",
)

PERSONA_GUEST_MIGRATED = register_event_type(
    "persona.guest.migrated",
    "1",
    closed(
        {
            "member_id": UUID,
            "migration_id": UUID,
            "profile_version": REVISION,
            "saved_look": {"type": "boolean"},
        },
        ("member_id", "migration_id", "profile_version", "saved_look"),
    ),
    "member_private",
)


def emit_updated(ctx, member_id: str, version: int, change_kind: str, changed_axes) -> None:
    ctx.emit(
        "persona.updated",
        "1",
        "persona_profile",
        member_id,
        version,
        {
            "member_id": member_id,
            "profile_version": str(version),
            "change_kind": change_kind,
            "changed_axes": sorted(set(changed_axes)),
        },
        "member_private",
    )
