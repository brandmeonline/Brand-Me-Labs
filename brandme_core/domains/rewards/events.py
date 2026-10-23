"""Rewards event types (closed payload schemas; references and integers only)."""

from __future__ import annotations

from brandme_core.domains.persona.kernel import UUID, closed, register_event_type

from .rules import BADGES, RULES

POINTS = {"type": "integer", "minimum": 0, "maximum": 1_000_000}
RULE_ID = {"type": "string", "enum": sorted(RULES)}
BADGE_ID = {"type": "string", "enum": sorted(BADGES)}
NULLABLE_RULE = {"anyOf": [RULE_ID, {"type": "null"}]}

register_event_type("reward.posted", "1", closed(
    {"member_id": UUID, "entry_id": UUID, "kind": {"type": "string", "enum": ["credit", "correction"]}, "rule_id": NULLABLE_RULE,
     "rule_version": {"anyOf": [{"type": "integer", "minimum": 1}, {"type": "null"}]}, "points": POINTS,
     "state": {"type": "string", "enum": ["posted", "capped", "excluded"]}},
    ("member_id", "entry_id", "kind", "rule_id", "rule_version", "points", "state")), "member_private")
register_event_type("reward.reversed", "1", closed(
    {"member_id": UUID, "entry_id": UUID, "reverses_entry_id": UUID, "points": POINTS, "recovery_due_added": POINTS},
    ("member_id", "entry_id", "reverses_entry_id", "points", "recovery_due_added")), "member_private")
register_event_type("badge.awarded", "1", closed(
    {"member_id": UUID, "badge_id": BADGE_ID, "criteria_version": {"type": "integer", "minimum": 1}},
    ("member_id", "badge_id", "criteria_version")), "member_private")
register_event_type("badge.revoked", "1", closed(
    {"member_id": UUID, "badge_id": BADGE_ID}, ("member_id", "badge_id")), "member_private")
for _t in ("benefit.reserved", "benefit.fulfilled", "benefit.refunded"):
    register_event_type(_t, "1", closed(
        {"member_id": UUID, "reservation_id": UUID, "benefit_id": UUID, "cost_points": POINTS},
        ("member_id", "reservation_id", "benefit_id", "cost_points")), "member_private")
register_event_type("reward.dispute.opened", "1", closed(
    {"member_id": UUID, "dispute_id": UUID}, ("member_id", "dispute_id")), "member_private")
register_event_type("reward.dispute.resolved", "1", closed(
    {"member_id": UUID, "dispute_id": UUID, "state": {"type": "string", "enum": ["resolved_correction", "resolved_no_change"]}},
    ("member_id", "dispute_id", "state")), "member_private")
