"""Wardrobe / closet / outfit event types (closed payload schemas).

Payloads carry identifiers and enums only: no titles, notes, prices, trip
dates or placement coordinates.
"""

from __future__ import annotations

from brandme_core.domains.persona.kernel import REVISION, UUID, closed, register_event_type

from .model import CLAIM_LEVELS, COLLECTIONS

ENUM = lambda values: {"type": "string", "enum": list(values)}  # noqa: E731
NULLABLE_UUID = {"anyOf": [UUID, {"type": "null"}]}

register_event_type(
    "wardrobe.item.created",
    "1",
    closed(
        {
            "member_id": UUID,
            "item_id": UUID,
            "collection": ENUM(COLLECTIONS),
            "acquisition_source": ENUM(("manual", "photo", "catalog", "receipt", "qr", "agent", "order", "guest")),
            "claim_level": ENUM(CLAIM_LEVELS),
        },
        ("member_id", "item_id", "collection", "acquisition_source", "claim_level"),
    ),
    "member_private",
)

register_event_type(
    "wardrobe.item.updated",
    "1",
    closed(
        {
            "member_id": UUID,
            "item_id": UUID,
            "item_version": REVISION,
            "collection": ENUM(COLLECTIONS),
            "changed_fields": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 20, "uniqueItems": True},
        },
        ("member_id", "item_id", "item_version", "collection", "changed_fields"),
    ),
    "member_private",
)

register_event_type(
    "closet.placement.changed",
    "1",
    closed(
        {
            "member_id": UUID,
            "item_id": UUID,
            "placement_version": REVISION,
            "change_kind": ENUM(("placed", "moved", "unplaced", "theme_remapped", "removed")),
        },
        ("member_id", "item_id", "placement_version", "change_kind"),
    ),
    "member_private",
)

register_event_type(
    "closet.layout.changed",
    "1",
    closed(
        {"member_id": UUID, "layout_version": REVISION, "room_template_id": ENUM(("walnut_atelier", "limestone_gallery", "garden_studio"))},
        ("member_id", "layout_version", "room_template_id"),
    ),
    "member_private",
)

register_event_type(
    "outfit.version.created",
    "1",
    closed(
        {
            "outfit_id": UUID,
            "owner_member_id": UUID,
            "version_no": REVISION,
            "author_member_id": UUID,
            "source_proposal_id": NULLABLE_UUID,
        },
        ("outfit_id", "owner_member_id", "version_no", "author_member_id", "source_proposal_id"),
    ),
    "member_private",
)

register_event_type(
    "outfit.proposal.created",
    "1",
    closed(
        {"outfit_id": UUID, "owner_member_id": UUID, "proposal_id": UUID, "proposer_member_id": UUID},
        ("outfit_id", "owner_member_id", "proposal_id", "proposer_member_id"),
    ),
    "member_private",
)

register_event_type(
    "outfit.proposal.accepted",
    "1",
    closed(
        {
            "outfit_id": UUID,
            "owner_member_id": UUID,
            "proposal_id": UUID,
            "proposer_member_id": UUID,
            "accepted_version": REVISION,
        },
        ("outfit_id", "owner_member_id", "proposal_id", "proposer_member_id", "accepted_version"),
    ),
    "member_private",
)
