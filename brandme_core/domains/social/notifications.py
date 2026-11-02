"""In-app notifications: written in the same transaction as the domain change
that caused them, keyed to the emitted event id and deduplicated by
(recipient, event, type). Payloads are sanitized: ids and enums only.

External delivery (email/push) needs a real provider and opted-in recipients
(ch.06 gate "Email/push"); none is configured, so only in-app exists here.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject

from brandme_core.domains.persona.kernel import (
    INT,
    STR,
    STR_ARRAY,
    Principal,
    ValidationFailed,
    decode_cursor,
    encode_cursor,
    iso,
    json_value,
    processing_allowed,
    new_id,
    query,
    require_scope,
    require_strict_int,
    require_uuid,
    run_read,
    run_txn,
)

SAFE_KEYS = frozenset({"decision_id", "relationship_id", "outfit_id", "proposal_id", "share_id", "report_id", "room_id", "result", "counts",
                       "closes_at"})


def blocked_between(txn, a: str, b: str) -> bool:
    return bool(query(
        txn,
        "SELECT 1 FROM MemberBlocks WHERE (member_id=@a AND blocked_member_id=@b) OR (member_id=@b AND blocked_member_id=@a) LIMIT 1",
        {"a": a, "b": b},
        {"a": STR, "b": STR},
    ))


def muted_by(txn, member_id: str, other: str) -> bool:
    """True when ``member_id`` muted ``other`` (one-sided; ``other`` is never told)."""
    return bool(query(txn, "SELECT 1 FROM MemberMutes WHERE member_id=@m AND muted_member_id=@o",
                      {"m": member_id, "o": other}, {"m": STR, "o": STR}))


def notify(txn, *, recipient_id: str, event_id: str, type_: str, actor_member_id: Optional[str], subject_ref: Optional[str],
           payload: Mapping[str, Any]) -> bool:
    """Insert one notification unless the recipient blocked/was blocked by the actor
    or it already exists for (recipient, event, type). Returns True if written."""
    unsafe = set(payload) - SAFE_KEYS
    if unsafe:
        raise ValueError(f"notification payload keys not allowed: {sorted(unsafe)}")
    if actor_member_id and (blocked_between(txn, recipient_id, actor_member_id) or muted_by(txn, recipient_id, actor_member_id)):
        return False
    if not processing_allowed(txn, recipient_id, "social.notifications"):
        return False  # deletion pending for the recipient: skip, never fail the actor's action
    if query(txn, "SELECT 1 FROM Notifications WHERE member_id=@m AND event_id=@e AND type=@t",
             {"m": recipient_id, "e": event_id, "t": type_}, {"m": STR, "e": STR, "t": STR}):
        return False
    txn.insert(
        "Notifications",
        columns=("member_id", "notification_id", "event_id", "type", "actor_member_id", "subject_ref", "sanitized_payload", "created_at", "read_at"),
        values=[(recipient_id, new_id(), event_id, type_, actor_member_id, subject_ref, JsonObject(dict(payload)), COMMIT_TIMESTAMP, None)],
    )
    return True


def withdraw_between(txn, a: str, b: str) -> int:
    """On block: drop unread notifications either party caused for the other."""
    n = txn.execute_update(
        "DELETE FROM Notifications WHERE member_id=@a AND actor_member_id=@b AND read_at IS NULL",
        params={"a": a, "b": b}, param_types={"a": STR, "b": STR},
    )
    return n + txn.execute_update(
        "DELETE FROM Notifications WHERE member_id=@b AND actor_member_id=@a AND read_at IS NULL",
        params={"a": a, "b": b}, param_types={"a": STR, "b": STR},
    )


class NotificationService:
    def __init__(self, database):
        self.db = database

    def list(self, principal: Principal, *, cursor: Optional[str] = None, limit: int = 24) -> Dict[str, Any]:
        require_scope(principal, "social:read")
        limit = require_strict_int(limit, name="limit", lo=1, hi=100)
        sql = ("SELECT notification_id, type, subject_ref, sanitized_payload, created_at, read_at FROM Notifications "
               "WHERE member_id=@m ")
        params: Dict[str, Any] = {"m": principal.member_id, "n": limit + 1}
        types: Dict[str, Any] = {"m": STR, "n": INT}
        if cursor:
            from brandme_core.domains.persona.kernel import TS

            t, i = decode_cursor(cursor, kinds=("ts", "id"))
            sql += "AND (created_at < @t OR (created_at = @t AND notification_id > @i)) "
            params.update(t=t, i=i)
            types.update(t=TS, i=STR)
        sql += "ORDER BY created_at DESC, notification_id LIMIT @n"
        rows = run_read(self.db, lambda s: query(s, sql, params, types))
        items = [{"notification_id": r[0], "type": r[1], "subject_ref": r[2], "payload": json_value(r[3]),
                  "created_at": iso(r[4]), "read_at": iso(r[5])} for r in rows[:limit]]
        nxt = encode_cursor(rows[limit - 1][4], rows[limit - 1][0]) if len(rows) > limit else None
        return {"items": items, "next_cursor": nxt}

    def mark_read(self, principal: Principal, ids: Iterable[Any]) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        ids = list(ids) if isinstance(ids, (list, tuple)) else None
        if ids is None or not (1 <= len(ids) <= 100):
            raise ValidationFailed("ids must list 1-100 notification ids", extra={"field": "ids"})
        ids = [require_uuid(i, name="ids") for i in ids]

        def tx(t):
            # Only the caller's own rows can match: member_id is part of the key.
            return t.execute_update(
                "UPDATE Notifications SET read_at = PENDING_COMMIT_TIMESTAMP() "
                "WHERE member_id=@m AND notification_id IN UNNEST(@ids) AND read_at IS NULL",
                params={"m": principal.member_id, "ids": ids}, param_types={"m": STR, "ids": STR_ARRAY},
            )

        return {"marked_read": run_txn(self.db, tx)}
