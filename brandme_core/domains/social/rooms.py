"""
Small-group rooms (Ultra plan 02, item 7): the slower, intimate decision rhythm
beside fast Now verdicts, such as a bridesmaids' gown room.

* **Invite-only and small.** The owner opens a room and adds people, who must
  be their friends; at most ``MAX_MEMBERS`` including the owner. Only members
  can see that the room exists. The owner may remove anyone; anyone may leave.
* **Posts are pieces or notes.** A piece is the author's own closet item or a
  live catalog piece, optionally with a note.
  - Members react with yes, maybe or no; one reaction per post, changeable
    while the room is open.
  - Authors withdraw their own posts; the text is erased and a placeholder
    stays.
  - Posts can be reported (``room_post``).
* **Blocking wins.** A member never sees posts or reactions from someone they
  blocked or who blocked them, and the owner cannot add a blocked pair.
* **Archive.** The owner archives a room. It stays readable to its members and
  takes no new posts, reactions or members.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, KeySet

from brandme_core.domains.persona.kernel import (
    INT,
    STR,
    STR_ARRAY,
    CommandContext,
    DetailedInvalidTransition,
    NotFound,
    Principal,
    RateLimited,
    ValidationFailed,
    command,
    guard_write,
    idempotent_command,
    iso,
    member_active,
    query,
    reject_unknown_keys,
    require_scope,
    require_text,
    require_uuid,
    run_read,
    stable_id,
)

from .notifications import blocked_between, notify
from .relationships import are_friends

MAX_MEMBERS = 12
MAX_OPEN_ROOMS = 20
POSTS_PER_DAY = 100
REACTIONS = ("yes", "maybe", "no")
POST_LIMIT = 100


def _member_only(principal: Principal) -> None:
    if principal.delegation_id:
        raise DetailedInvalidTransition("rooms are the member's own; an agent cannot act in them", code="member_only")


class RoomService:
    def __init__(self, database, *, catalog_check: Any = None):
        self.db = database
        self.catalog_check = catalog_check or (lambda _txn, _pid: False)

    # ---------------------------------------------------------------- helpers

    def _room(self, txn, room_id: str) -> Optional[Dict[str, Any]]:
        rows = query(txn, "SELECT room_id, owner_id, title, purpose, state, version FROM Rooms WHERE room_id=@r", {"r": room_id}, {"r": STR})
        return dict(zip(("room_id", "owner_id", "title", "purpose", "state", "version"), rows[0])) if rows else None

    def _members(self, txn, room_id: str) -> List[str]:
        return [r[0] for r in query(txn, "SELECT member_id FROM RoomMembers WHERE room_id=@r ORDER BY joined_at, member_id", {"r": room_id}, {"r": STR})]

    def _as_member(self, txn, room_id: str, me: str) -> Dict[str, Any]:
        room = self._room(txn, room_id)
        if room is None or me not in self._members(txn, room_id):
            raise NotFound("room not found")
        return room

    def _addable(self, txn, owner: str, member_ids: List[str], existing: List[str]) -> None:
        bad = [m for m in member_ids if m == owner or not are_friends(txn, owner, m) or not member_active(txn, m)
               or any(blocked_between(txn, m, x) for x in existing)]
        if bad:
            raise DetailedInvalidTransition("you can add your own friends only", code="not_addable", extra={"member_ids": bad})

    # ----------------------------------------------------------------- owner

    def create(self, principal: Principal, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        _member_only(principal)
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("title", "purpose", "member_ids"), where="room")
        title = require_text(body.get("title"), name="title", max_len=80)
        purpose = require_text(body["purpose"], name="purpose", max_len=200) if body.get("purpose") is not None else None
        ids = body.get("member_ids", [])
        if not isinstance(ids, list) or len(ids) > MAX_MEMBERS - 1:
            raise ValidationFailed(f"a room has at most {MAX_MEMBERS} people, you included", extra={"field": "member_ids"})
        ids = [require_uuid(i, name="member_ids") for i in ids]
        if len(set(ids)) != len(ids):
            raise ValidationFailed("add each person once", extra={"field": "member_ids"})
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, me):
                raise NotFound("member not found")
            guard_write(txn, me, "social.rooms")
            n = query(txn, "SELECT COUNT(*) FROM Rooms@{FORCE_INDEX=RoomsByOwner} WHERE owner_id=@m AND state='open'", {"m": me}, {"m": STR})[0][0]
            if n >= MAX_OPEN_ROOMS:
                raise RateLimited(f"at most {MAX_OPEN_ROOMS} open rooms", extra={"limit": "open_rooms"})
            self._addable(txn, me, ids, [me])
            room_id = stable_id("room", me, ctx.correlation_id)
            txn.insert("Rooms", columns=("room_id", "owner_id", "title", "purpose", "state", "created_at", "updated_at", "version"),
                       values=[(room_id, me, title, purpose, "open", COMMIT_TIMESTAMP, COMMIT_TIMESTAMP, 1)])
            txn.insert("RoomMembers", columns=("room_id", "member_id", "role", "added_by", "joined_at"),
                       values=[(room_id, me, "owner", me, COMMIT_TIMESTAMP)] + [(room_id, m, "member", me, COMMIT_TIMESTAMP) for m in ids])
            for m in ids:
                notify(txn, recipient_id=m, event_id=room_id, type_="room_added", actor_member_id=me, subject_ref=f"room:{room_id}",
                       payload={"room_id": room_id})
            return {"room_id": room_id, "title": title, "purpose": purpose, "state": "open", "member_ids": [me, *ids]}

        response, _ = idempotent_command(self.db, principal, "rooms.create", idempotency_key, dict(body), tx)
        return response

    def add_member(self, principal: Principal, room_id: Any, member_id: Any) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        _member_only(principal)
        room_id, member_id = require_uuid(room_id, name="room_id"), require_uuid(member_id, name="member_id")
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            room = self._as_member(txn, room_id, me)
            if room["owner_id"] != me:
                raise NotFound("room not found")
            if room["state"] != "open":
                raise DetailedInvalidTransition("this room is archived", code="room_archived")
            members = self._members(txn, room_id)
            if member_id in members:
                return {"room_id": room_id, "member_ids": members}
            if len(members) >= MAX_MEMBERS:
                raise RateLimited(f"a room has at most {MAX_MEMBERS} people", extra={"limit": "room_members"})
            self._addable(txn, me, [member_id], members)
            guard_write(txn, me, "social.rooms")
            txn.insert("RoomMembers", columns=("room_id", "member_id", "role", "added_by", "joined_at"),
                       values=[(room_id, member_id, "member", me, COMMIT_TIMESTAMP)])
            notify(txn, recipient_id=member_id, event_id=stable_id("room-added", room_id, member_id), type_="room_added", actor_member_id=me,
                   subject_ref=f"room:{room_id}", payload={"room_id": room_id})
            return {"room_id": room_id, "member_ids": [*members, member_id]}

        return command(self.db, principal, tx)

    def remove_member(self, principal: Principal, room_id: Any, member_id: Any) -> Dict[str, Any]:
        """The owner removes someone, or a member leaves (``member_id`` is themselves)."""
        require_scope(principal, "social:write")
        room_id, member_id = require_uuid(room_id, name="room_id"), require_uuid(member_id, name="member_id")
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            room = self._as_member(txn, room_id, me)
            if member_id != me and room["owner_id"] != me:
                raise NotFound("room not found")
            if member_id == room["owner_id"]:
                raise DetailedInvalidTransition("the owner archives the room instead of leaving it", code="owner_cannot_leave")
            txn.delete("RoomMembers", keyset=KeySet(keys=[[room_id, member_id]]))
            return {"room_id": room_id, "removed": member_id}

        return command(self.db, principal, tx)

    def archive(self, principal: Principal, room_id: Any) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        room_id = require_uuid(room_id, name="room_id")
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            room = self._as_member(txn, room_id, me)
            if room["owner_id"] != me:
                raise NotFound("room not found")
            txn.update("Rooms", columns=("room_id", "state", "updated_at", "version"), values=[(room_id, "archived", COMMIT_TIMESTAMP, room["version"] + 1)])
            return {"room_id": room_id, "state": "archived"}

        return command(self.db, principal, tx)

    # --------------------------------------------------------------- members

    def post(self, principal: Principal, room_id: Any, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        _member_only(principal)
        room_id = require_uuid(room_id, name="room_id")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("kind", "body", "subject_type", "subject_id"), where="room post")
        kind = body.get("kind")
        if kind not in ("note", "piece"):
            raise ValidationFailed("kind must be note or piece", extra={"field": "kind"})
        text = require_text(body["body"], name="body", max_len=1000) if body.get("body") is not None else None
        if kind == "note" and text is None:
            raise ValidationFailed("a note needs a body", extra={"field": "body"})
        subject_type = body.get("subject_type")
        subject_id = None
        if kind == "piece":
            if subject_type not in ("wardrobe_item", "catalog_product"):
                raise ValidationFailed("a piece is a wardrobe_item or a catalog_product", extra={"field": "subject_type"})
            subject_id = require_uuid(body.get("subject_id"), name="subject_id")
        elif subject_type is not None or body.get("subject_id") is not None:
            raise ValidationFailed("a note has no subject")
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            room = self._as_member(txn, room_id, me)
            if room["state"] != "open":
                raise DetailedInvalidTransition("this room is archived", code="room_archived")
            if kind == "piece":
                ok = (query(txn, "SELECT 1 FROM WardrobeItems WHERE member_id=@m AND item_id=@i AND collection != 'archive'",
                            {"m": me, "i": subject_id}, {"m": STR, "i": STR}) if subject_type == "wardrobe_item"
                      else self.catalog_check(txn, subject_id))
                if not ok:
                    raise ValidationFailed("post your own closet pieces or live catalog pieces", extra={"field": "subject_id"})
            guard_write(txn, me, "social.rooms")
            today = query(txn, "SELECT COUNT(*) FROM RoomPosts@{FORCE_INDEX=RoomPostsByAuthor} WHERE author_id=@m "
                               "AND created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)", {"m": me}, {"m": STR})[0][0]
            if today >= POSTS_PER_DAY:
                raise RateLimited(f"at most {POSTS_PER_DAY} room posts a day", extra={"limit": "room_posts"})
            post_id = stable_id("room-post", room_id, me, ctx.correlation_id)
            txn.insert("RoomPosts", columns=("room_id", "post_id", "author_id", "kind", "body", "subject_type", "subject_id", "created_at"),
                       values=[(room_id, post_id, me, kind, text, subject_type if kind == "piece" else None, subject_id, COMMIT_TIMESTAMP)])
            return {"room_id": room_id, "post_id": post_id, "kind": kind, "body": text, "subject_type": subject_type if kind == "piece" else None,
                    "subject_id": subject_id}

        response, _ = idempotent_command(self.db, principal, "rooms.post", idempotency_key, {"room_id": room_id, **dict(body)}, tx)
        return response

    def react(self, principal: Principal, room_id: Any, post_id: Any, body: Any) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        _member_only(principal)
        room_id, post_id = require_uuid(room_id, name="room_id"), require_uuid(post_id, name="post_id")
        if not isinstance(body, Mapping) or set(body) != {"reaction"} or body["reaction"] not in REACTIONS:
            raise ValidationFailed(f'body must be {{"reaction": one of {list(REACTIONS)}}}')
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            room = self._as_member(txn, room_id, me)
            if room["state"] != "open":
                raise DetailedInvalidTransition("this room is archived", code="room_archived")
            p = query(txn, "SELECT author_id FROM RoomPosts WHERE room_id=@r AND post_id=@p AND removed_at IS NULL", {"r": room_id, "p": post_id},
                      {"r": STR, "p": STR})
            if not p or blocked_between(txn, me, p[0][0]):
                raise NotFound("post not found")
            guard_write(txn, me, "social.rooms")
            txn.insert_or_update("RoomReactions", columns=("room_id", "post_id", "member_id", "reaction", "updated_at"),
                                 values=[(room_id, post_id, me, body["reaction"], COMMIT_TIMESTAMP)])
            return {"room_id": room_id, "post_id": post_id, "reaction": body["reaction"]}

        return command(self.db, principal, tx)

    def withdraw(self, principal: Principal, room_id: Any, post_id: Any) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        room_id, post_id = require_uuid(room_id, name="room_id"), require_uuid(post_id, name="post_id")
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            self._as_member(txn, room_id, me)
            n = txn.execute_update("UPDATE RoomPosts SET body = NULL, subject_type = NULL, subject_id = NULL, kind = 'note', "
                                   "removed_at = CURRENT_TIMESTAMP(), removed_reason = 'author' "
                                   "WHERE room_id=@r AND post_id=@p AND author_id=@m AND removed_at IS NULL",
                                   params={"r": room_id, "p": post_id, "m": me}, param_types={"r": STR, "p": STR, "m": STR})
            if not n and not query(txn, "SELECT 1 FROM RoomPosts WHERE room_id=@r AND post_id=@p AND author_id=@m",
                                   {"r": room_id, "p": post_id, "m": me}, {"r": STR, "p": STR, "m": STR}):
                raise NotFound("post not found")
            return {"room_id": room_id, "post_id": post_id, "removed": True}

        return command(self.db, principal, tx)

    # ----------------------------------------------------------------- reads

    def mine(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "social:read")
        me = principal.member_id
        rows = run_read(self.db, lambda s: query(
            s, "SELECT r.room_id, r.title, r.purpose, r.state, r.owner_id, m.role FROM RoomMembers@{FORCE_INDEX=RoomMembersByMember} m "
               "JOIN Rooms r ON r.room_id = m.room_id WHERE m.member_id=@m ORDER BY r.updated_at DESC LIMIT 100", {"m": me}, {"m": STR}))
        return {"items": [{"room_id": r[0], "title": r[1], "purpose": r[2], "state": r[3], "owner_id": r[4], "role": r[5]} for r in rows]}

    def get(self, principal: Principal, room_id: Any) -> Dict[str, Any]:
        require_scope(principal, "social:read")
        room_id = require_uuid(room_id, name="room_id")
        me = principal.member_id

        def read(s):
            room = self._as_member(s, room_id, me)
            members = self._members(s, room_id)
            posts = query(s, "SELECT post_id, author_id, kind, body, subject_type, subject_id, created_at, removed_at FROM RoomPosts "
                             "WHERE room_id=@r ORDER BY created_at DESC, post_id LIMIT @l", {"r": room_id, "l": POST_LIMIT}, {"r": STR, "l": INT})
            ids = [p[0] for p in posts]
            rows = query(s, "SELECT post_id, member_id, reaction FROM RoomReactions WHERE room_id=@r AND post_id IN UNNEST(@p)",
                         {"r": room_id, "p": ids}, {"r": STR, "p": STR_ARRAY}) if ids else []
            # Blocking covers everyone whose content is shown, including people who have since left the room.
            people = set(members) | {p[1] for p in posts} | {r[1] for r in rows}
            hidden = {m for m in people if m != me and blocked_between(s, me, m)}
            reactions: Dict[str, Dict[str, int]] = {}
            mine: Dict[str, str] = {}
            for pid, who, reaction in rows:
                if who in hidden:
                    continue
                reactions.setdefault(pid, {k: 0 for k in REACTIONS})[reaction] += 1
                if who == me:
                    mine[pid] = reaction
            items = []
            for pid, author, kind, body, stype, sid, created, removed in posts:
                if author in hidden:
                    continue
                base = {"post_id": pid, "author_id": author, "created_at": iso(created), "mine": author == me}
                if removed is not None:
                    items.append({**base, "removed": True})
                    continue
                items.append({**base, "removed": False, "kind": kind, "body": body, "subject_type": stype, "subject_id": sid,
                              "reactions": reactions.get(pid, {k: 0 for k in REACTIONS}), "my_reaction": mine.get(pid)})
            return {**{k: room[k] for k in ("room_id", "title", "purpose", "state", "owner_id")},
                    "member_ids": [m for m in members if m not in hidden], "posts": items}

        return run_read(self.db, read)


def export_rooms(snap, member_id: str) -> List[Dict[str, Any]]:
    m = {"m": member_id}
    owned = [{"room_id": r[0], "title": r[1], "purpose": r[2], "state": r[3]}
             for r in query(snap, "SELECT room_id, title, purpose, state FROM Rooms@{FORCE_INDEX=RoomsByOwner} WHERE owner_id=@m", m, {"m": STR})]
    joined = [r[0] for r in query(snap, "SELECT room_id FROM RoomMembers@{FORCE_INDEX=RoomMembersByMember} WHERE member_id=@m", m, {"m": STR})]
    posts = [{"room_id": r[0], "post_id": r[1], "kind": r[2], "body": r[3], "subject_type": r[4], "subject_id": r[5], "created_at": iso(r[6]),
              "removed": r[7] is not None}
             for r in query(snap, "SELECT room_id, post_id, kind, body, subject_type, subject_id, created_at, removed_at FROM RoomPosts"
                                  "@{FORCE_INDEX=RoomPostsByAuthor} WHERE author_id=@m ORDER BY created_at", m, {"m": STR})]
    reacted = [{"room_id": r[0], "post_id": r[1], "reaction": r[2]}
               for r in query(snap, "SELECT room_id, post_id, reaction FROM RoomReactions@{FORCE_INDEX=RoomReactionsByMember} WHERE member_id=@m",
                              m, {"m": STR})]
    return [{"owned": owned, "member_of": joined, "posts": posts, "reactions": reacted}]


def delete_rooms(txn, member_id: str) -> int:
    """Rooms the member owns go with them (members, posts, reactions cascade);
    elsewhere their posts, reactions and memberships are removed."""
    m = {"m": member_id}
    n = txn.execute_update("DELETE FROM RoomReactions WHERE member_id=@m", params=m, param_types={"m": STR})
    n += txn.execute_update("DELETE FROM RoomPosts WHERE author_id=@m", params=m, param_types={"m": STR})
    n += txn.execute_update("DELETE FROM RoomMembers WHERE member_id=@m", params=m, param_types={"m": STR})
    return n + txn.execute_update("DELETE FROM Rooms WHERE owner_id=@m", params=m, param_types={"m": STR})
