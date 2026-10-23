"""Social event types (closed payload schemas; identifiers and enums only —
no prompts, choices, notes or friend lists)."""

from __future__ import annotations

from brandme_core.domains.persona.kernel import UUID, closed, register_event_type

UUIDS12 = {"type": "array", "items": UUID, "maxItems": 12, "uniqueItems": True}
TS = {"type": "string", "format": "date-time"}

register_event_type("relationship.requested", "1", closed(
    {"relationship_id": UUID, "requester_id": UUID, "recipient_id": UUID}, ("relationship_id", "requester_id", "recipient_id")), "member_private")
register_event_type("relationship.accepted", "1", closed(
    {"relationship_id": UUID, "member_a": UUID, "member_b": UUID}, ("relationship_id", "member_a", "member_b")), "member_private")
register_event_type("member.blocked", "1", closed(
    {"blocker_id": UUID, "blocked_id": UUID}, ("blocker_id", "blocked_id")), "restricted")
register_event_type("decision.opened", "1", closed(
    {"decision_id": UUID, "creator_id": UUID, "audience_count": {"type": "integer", "minimum": 1, "maximum": 12}, "closes_at": TS},
    ("decision_id", "creator_id", "audience_count", "closes_at")), "member_private")
register_event_type("decision.responded", "1", closed(
    {"decision_id": UUID, "creator_id": UUID, "respondent_id": UUID, "revision": {"type": "integer", "minimum": 1}},
    ("decision_id", "creator_id", "respondent_id", "revision")), "member_private")
register_event_type("decision.closed", "1", closed(
    {
        "decision_id": UUID,
        "creator_id": UUID,
        "close_reason": {"type": "string", "enum": ["expired", "owner_closed"]},
        "eligible_respondent_ids": UUIDS12,
        "repeat_request": {"type": "boolean"},
        "zero_replies": {"type": "boolean"},
    },
    ("decision_id", "creator_id", "close_reason", "eligible_respondent_ids", "repeat_request", "zero_replies")), "member_private")
register_event_type("decision.cancelled", "1", closed(
    {"decision_id": UUID, "creator_id": UUID}, ("decision_id", "creator_id")), "member_private")
register_event_type("share.created", "1", closed(
    {"share_id": UUID, "owner_id": UUID, "subject_type": {"type": "string", "maxLength": 24}}, ("share_id", "owner_id", "subject_type")), "member_private")
register_event_type("share.revoked", "1", closed(
    {"share_id": UUID, "owner_id": UUID}, ("share_id", "owner_id")), "member_private")
