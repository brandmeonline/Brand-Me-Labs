"""
Friendships and blocks (ch.01 §6.4; BM-SOC-001, BM-SOC-009).

Friendship needs a request and an acceptance by the *intended recipient's own
session*. Nothing in a request body can establish a relationship for someone
else. No contact upload exists. Blocking:
  * removes the friendship;
  * removes each party from the other's open decision audiences;
  * removes them from the other's selected-member shares;
  * withdraws unread notifications either caused for the other;
  * refuses future requests, notifications and proposals between them.
Blocking overrides ordinary sharing everywhere (foundation ``authorize``).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, KeySet

from brandme_core.domains.persona.kernel import (
    STR,
    CommandContext,
    DetailedInvalidTransition,
    NotFound,
    Principal,
    command,
    iso,
    member_active,
    query,
    require_scope,
    require_uuid,
    run_read,
    stable_id,
)

from . import events as _events  # noqa: F401
from .notifications import blocked_between, notify, withdraw_between


def relationship_id(a: str, b: str) -> str:
    lo, hi = sorted((a, b))
    return stable_id("relationship", lo, hi)


def are_friends(txn, a: str, b: str) -> bool:
    rows = query(txn, "SELECT state FROM Relationships WHERE member_id=@a AND other_member_id=@b",
                 {"a": a, "b": b}, {"a": STR, "b": STR})
    return bool(rows) and rows[0][0] == "accepted" and not blocked_between(txn, a, b)


def friendship_proposal_policy(txn, owner: str, proposer: str) -> bool:
    """Outfit proposals: accepted, unblocked friends only (injected into OutfitService)."""
    return are_friends(txn, owner, proposer)


class RelationshipService:
    def __init__(self, database):
        self.db = database

    def _pair(self, txn, me: str, other: str) -> Optional[Dict[str, Any]]:
        rows = query(txn, "SELECT relationship_id, state, requested_by, version FROM Relationships WHERE member_id=@a AND other_member_id=@b",
                     {"a": me, "b": other}, {"a": STR, "b": STR})
        return dict(zip(("relationship_id", "state", "requested_by", "version"), rows[0])) if rows else None

    def request(self, principal: Principal, target_member_id: Any) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        target = require_uuid(target_member_id, name="member_id")
        me = principal.member_id
        if target == me:
            raise DetailedInvalidTransition("you cannot befriend yourself", code="self_relationship")

        def tx(txn, ctx: CommandContext):
            # Missing, inactive and blocked look the same to the requester.
            if not member_active(txn, target) or blocked_between(txn, me, target):
                raise NotFound("member not found")
            existing = self._pair(txn, me, target)
            rid = relationship_id(me, target)
            if existing:
                if existing["state"] == "requested_in":  # they already asked: accept instead
                    raise DetailedInvalidTransition("this member already asked you; accept their request", code="request_pending_from_them",
                                                    extra={"relationship_id": rid})
                return {"relationship_id": rid, "state": existing["state"]}
            for a, b, state in ((me, target, "requested_out"), (target, me, "requested_in")):
                txn.insert("Relationships", columns=("member_id", "other_member_id", "relationship_id", "state", "requested_by", "created_at", "version"),
                           values=[(a, b, rid, state, me, COMMIT_TIMESTAMP, 1)])
            ev = ctx.emit("relationship.requested", "1", "relationship", rid, 1,
                          {"relationship_id": rid, "requester_id": me, "recipient_id": target}, "member_private")
            notify(txn, recipient_id=target, event_id=ev.event_id, type_="friend_request", actor_member_id=me,
                   subject_ref=f"relationship:{rid}", payload={"relationship_id": rid})
            return {"relationship_id": rid, "state": "requested_out"}

        return command(self.db, principal, tx)

    def accept(self, principal: Principal, rel_id: Any) -> Dict[str, Any]:
        """Invitation-bound: only the recipient side (state requested_in) can accept."""
        require_scope(principal, "social:write")
        rid = require_uuid(rel_id, name="relationship_id")
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            rows = query(txn, "SELECT other_member_id, state, version FROM Relationships WHERE member_id=@m AND relationship_id=@r",
                         {"m": me, "r": rid}, {"m": STR, "r": STR})
            if not rows:
                raise NotFound("request not found")
            other, state, version = rows[0]
            if state == "accepted":
                return {"relationship_id": rid, "state": "accepted"}
            if state != "requested_in":
                # The requester cannot accept their own request.
                raise NotFound("request not found")
            if blocked_between(txn, me, other):
                raise NotFound("request not found")
            for a, b in ((me, other), (other, me)):
                txn.update("Relationships", columns=("member_id", "other_member_id", "state", "accepted_at", "version"),
                           values=[(a, b, "accepted", COMMIT_TIMESTAMP, version + 1)])
            lo, hi = sorted((me, other))
            ev = ctx.emit("relationship.accepted", "1", "relationship", rid, version + 1,
                          {"relationship_id": rid, "member_a": lo, "member_b": hi}, "member_private")
            notify(txn, recipient_id=other, event_id=ev.event_id, type_="friend_accepted", actor_member_id=me,
                   subject_ref=f"relationship:{rid}", payload={"relationship_id": rid})
            return {"relationship_id": rid, "state": "accepted"}

        return command(self.db, principal, tx)

    def remove(self, principal: Principal, other_member_id: Any) -> Dict[str, Any]:
        """Unfriend or withdraw/decline a request (either side)."""
        require_scope(principal, "social:write")
        other = require_uuid(other_member_id, name="member_id")
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            if self._pair(txn, me, other) is None:
                raise NotFound("relationship not found")
            txn.delete("Relationships", KeySet(keys=[[me, other], [other, me]]))
            return {"removed": True}

        return command(self.db, principal, tx)

    def list(self, principal: Principal) -> Dict[str, Any]:
        """The caller's own circle only (friend lists are never public)."""
        require_scope(principal, "social:read")
        rows = run_read(self.db, lambda s: query(
            s, "SELECT other_member_id, relationship_id, state, created_at, accepted_at FROM Relationships WHERE member_id=@m ORDER BY other_member_id",
            {"m": principal.member_id}, {"m": STR}))
        return {"items": [{"member_id": r[0], "relationship_id": r[1], "state": r[2], "created_at": iso(r[3]), "accepted_at": iso(r[4])}
                          for r in rows], "next_cursor": None}

    def block(self, principal: Principal, target_member_id: Any) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        target = require_uuid(target_member_id, name="member_id")
        me = principal.member_id
        if target == me:
            raise DetailedInvalidTransition("you cannot block yourself", code="self_block")

        def tx(txn, ctx: CommandContext):
            if query(txn, "SELECT 1 FROM MemberBlocks WHERE member_id=@a AND blocked_member_id=@b", {"a": me, "b": target}, {"a": STR, "b": STR}):
                return {"blocked": True, "already": True}
            if not query(txn, "SELECT 1 FROM Members WHERE member_id=@m", {"m": target}, {"m": STR}):
                raise NotFound("member not found")
            txn.insert("MemberBlocks", columns=("member_id", "blocked_member_id", "created_at"), values=[(me, target, COMMIT_TIMESTAMP)])
            txn.delete("Relationships", KeySet(keys=[[me, target], [target, me]]))
            # Each party leaves the other's open decision audiences.
            removed = 0
            for owner, other in ((me, target), (target, me)):
                removed += txn.execute_update(
                    "UPDATE DecisionAudience SET removed = TRUE WHERE member_id=@o AND recipient_id=@r AND removed = FALSE "
                    "AND decision_id IN (SELECT decision_id FROM Decisions WHERE member_id=@o AND state IN ('draft','open'))",
                    params={"o": owner, "r": other}, param_types={"o": STR, "r": STR})
            # Each party leaves the other's selected-member shares.
            revoked = 0
            for owner, other in ((me, target), (target, me)):
                for share_id, recips in query(txn, "SELECT share_id, recipient_ids FROM ShareGrants WHERE member_id=@o AND revoked_at IS NULL "
                                                   "AND @r IN UNNEST(recipient_ids)", {"o": owner, "r": other}, {"o": STR, "r": STR}):
                    txn.update("ShareGrants", columns=("member_id", "share_id", "recipient_ids"),
                               values=[(owner, share_id, [x for x in recips if x != other])])
                    revoked += 1
            withdrawn = withdraw_between(txn, me, target)
            ctx.emit("member.blocked", "1", "member_block", me, 1, {"blocker_id": me, "blocked_id": target}, "restricted")
            return {"blocked": True, "already": False, "audience_removals": removed, "share_removals": revoked, "notifications_withdrawn": withdrawn}

        return command(self.db, principal, tx)

    def unblock(self, principal: Principal, target_member_id: Any) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        target = require_uuid(target_member_id, name="member_id")

        def tx(txn, ctx: CommandContext):
            txn.delete("MemberBlocks", KeySet(keys=[[principal.member_id, target]]))
            return {"blocked": False}  # friendship is not restored automatically

        return command(self.db, principal, tx)
