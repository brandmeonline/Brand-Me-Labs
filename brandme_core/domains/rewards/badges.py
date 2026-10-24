"""
Badge evaluation (ch.01 §7.3). Badges are evidence of completed activity,
never of identity, authenticity or purchasing power.

Each badge's criteria are computed from ledger entries, reward facts and
(for Closet Curator) the member's current closet, inside the settling
transaction. Awards record the evidence references used. A badge is revoked
only when a verified reversal removes the evidence it rested on
(``allow_revoke``); ordinary later changes (e.g. unplacing items) do not
revoke a badge already earned.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

from brandme_core.domains.persona.kernel import INT, STR, CommandContext, iso, query, stable_id

from .ledger import active_entries, facts
from .rules import (
    BADGES,
    CLOSET_CURATOR_ITEMS,
    STYLE_COLLABORATOR_ACCEPTED,
    TRUSTED_EYE_DECISIONS,
    TRUSTED_EYE_RESPONSES,
)

Evidence = Optional[List[str]]  # None = not satisfied


def _first_reflection(txn, m: str) -> Evidence:
    f = facts(txn, m).get("profile_saved")
    return [f"event:{f['event_id']}"] if f else None


def _closet_curator(txn, m: str) -> Evidence:
    rows = query(txn, "SELECT p.item_id FROM ClosetPlacements p JOIN WardrobeItems i ON i.member_id=p.member_id AND i.item_id=p.item_id "
                      "WHERE p.member_id=@m AND p.semantic_group IS NOT NULL AND i.collection='owned' ORDER BY p.item_id LIMIT @n",
                 {"m": m, "n": CLOSET_CURATOR_ITEMS}, {"m": STR, "n": INT})
    return [f"item:{r[0]}" for r in rows] if len(rows) >= CLOSET_CURATOR_ITEMS else None


def _trusted_eye(txn, m: str) -> Evidence:
    es = active_entries(txn, m, "friend_decision_response")
    decisions = sorted({r for e in es for r in e["evidence_refs"] if r.startswith("decision:")})
    if len(es) >= TRUSTED_EYE_RESPONSES and len(decisions) >= TRUSTED_EYE_DECISIONS:
        return decisions[:TRUSTED_EYE_RESPONSES]
    return None


def _style_collaborator(txn, m: str) -> Evidence:
    es = active_entries(txn, m, "styling_proposal_accepted")
    if len(es) < STYLE_COLLABORATOR_ACCEPTED:
        return None
    return [r for e in es[:STYLE_COLLABORATOR_ACCEPTED] for r in e["evidence_refs"] if r.startswith("proposal:")]


def _care_keeper(txn, m: str) -> Evidence:
    es = active_entries(txn, m, "verified_repair")
    return [r for r in es[0]["evidence_refs"] if r.startswith("repair:")] if es else None


def _material_story(txn, m: str) -> Evidence:
    f = facts(txn, m).get("product_history_accepted")
    return [f"event:{f['event_id']}"] if f else None


CRITERIA = {
    "first_reflection": _first_reflection,
    "closet_curator": _closet_curator,
    "trusted_eye": _trusted_eye,
    "style_collaborator": _style_collaborator,
    "care_keeper": _care_keeper,
    "material_story": _material_story,
}


def _award_row(txn, m: str, badge_id: str) -> Optional[Tuple[Any, Any]]:
    rows = query(txn, "SELECT awarded_at, revoked_at FROM BadgeAwards WHERE member_id=@m AND badge_id=@b", {"m": m, "b": badge_id}, {"m": STR, "b": STR})
    return rows[0] if rows else None


def evaluate(txn, ctx: CommandContext, member_id: str, badge_ids: Iterable[str], *, allow_revoke: bool = False) -> Dict[str, str]:
    """Award (or, after a verified reversal, revoke) the given badges. Returns {badge: outcome}."""
    out: Dict[str, str] = {}
    for b in badge_ids:
        badge = BADGES[b]
        evidence = CRITERIA[b](txn, member_id)
        row = _award_row(txn, member_id, b)
        if evidence is not None and (row is None or row[1] is not None):
            txn.insert_or_update("BadgeAwards", columns=("member_id", "badge_id", "criteria_version", "evidence_refs", "awarded_at", "revoked_at", "revoke_reason"),
                                 values=[(member_id, b, badge.criteria_version, evidence, COMMIT_TIMESTAMP, None, None)])
            ctx.emit("badge.awarded", "1", "badge", stable_id("badge", member_id, b), 1 if row is None else 3,
                     {"member_id": member_id, "badge_id": b, "criteria_version": badge.criteria_version}, "member_private")
            out[b] = "awarded"
        elif evidence is None and row is not None and row[1] is None and allow_revoke:
            txn.update("BadgeAwards", columns=("member_id", "badge_id", "revoked_at", "revoke_reason"),
                       values=[(member_id, b, COMMIT_TIMESTAMP, "qualifying evidence reversed")])
            ctx.emit("badge.revoked", "1", "badge", stable_id("badge", member_id, b), 2, {"member_id": member_id, "badge_id": b}, "member_private")
            out[b] = "revoked"
    return out


def badges_for_rule(rule_id: Optional[str]) -> Tuple[str, ...]:
    return {
        "friend_decision_response": ("trusted_eye",),
        "styling_proposal_accepted": ("style_collaborator",),
        "verified_repair": ("care_keeper",),
    }.get(rule_id or "", ())


def member_badges(snap, member_id: str) -> List[Dict[str, Any]]:
    """Every badge with visible criteria; earned ones with date, evidence and revocation."""
    earned = {r[0]: r[1:] for r in query(
        snap, "SELECT badge_id, criteria_version, evidence_refs, awarded_at, revoked_at, revoke_reason FROM BadgeAwards WHERE member_id=@m",
        {"m": member_id}, {"m": STR})}
    out = []
    for b in BADGES.values():
        e = earned.get(b.id)
        out.append({
            "badge_id": b.id, "title": b.title, "criteria": b.criteria, "criteria_version": b.criteria_version,
            "earned": bool(e) and e[3] is None,
            "awarded_at": iso(e[2]) if e else None, "revoked_at": iso(e[3]) if e else None, "revoke_reason": e[4] if e else None,
            "evidence_refs": list(e[1]) if e else [],
        })
    return out
