"""
Per-piece closet visibility (Ultra plan 02, item 6): owner-curated, on a
sliding scale, private by default.

The owner sets two things for each owned or digital piece:
* **who** sees it: ``private`` (nobody else; the default), ``friends``
  (accepted, unblocked friends) or ``members`` (any signed-in member who is not
  blocked);
* **how much**:
  - ``piece``: title, category, house, and whether ownership is verified;
  - ``story``: adds the owner's showcase note and how often it is worn;
  - ``full``: adds the price and the year it entered the closet, for friends
    only.

Strangers (``members``) never see more than ``story``. That is the locked
disclosure default: price, ownership evidence and logistics stay hidden.
Receipts, order and source references, tag serials, sizes, care and private
notes are never shown to anyone else at any level.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

from brandme_core.domains.persona.kernel import (
    INT,
    STR,
    STR_ARRAY,
    CommandContext,
    NotFound,
    Principal,
    ValidationFailed,
    command,
    guard_write,
    member_active,
    query,
    reject_unknown_keys,
    require_scope,
    require_text,
    require_uuid,
    run_read,
)

AUDIENCES = ("private", "friends", "members")
DETAILS = ("piece", "story", "full")
STRANGER_MAX_DETAIL = "story"
SHOWN_COLLECTIONS = ("owned", "digital")
MAX_SHOWN = 200
_COLS = ("item_id", "title", "category", "product_id", "claim_level", "showcase_note", "worn_count", "price_minor", "price_currency",
         "created_at", "visibility", "visible_detail")


def relation(snap, viewer: str, owner: str) -> Optional[str]:
    """``self``, ``friends``, ``members``, or None when either member blocked the other."""
    from brandme_core.domains.social.notifications import blocked_between
    from brandme_core.domains.social.relationships import are_friends

    if viewer == owner:
        return "self"
    if blocked_between(snap, viewer, owner):
        return None
    return "friends" if are_friends(snap, viewer, owner) else "members"


def allowed(item_visibility: Optional[str], rel: Optional[str]) -> bool:
    if rel == "self":
        return True
    if rel is None or item_visibility is None:
        return False
    return item_visibility == "members" or (item_visibility == "friends" and rel == "friends")


def shown_piece(row: Mapping[str, Any], houses: Mapping[str, str]) -> Dict[str, Any]:
    detail = row["visible_detail"] or "piece"
    out: Dict[str, Any] = {"item_id": row["item_id"], "title": row["title"], "category": row["category"],
                           "house_ref": houses.get(row["product_id"]) if row["product_id"] else None,
                           "verified": row["claim_level"] != "self_reported", "detail": detail}
    if detail in ("story", "full"):
        out.update(showcase_note=row["showcase_note"], worn_count=row["worn_count"])
    if detail == "full":
        out.update(price=None if row["price_minor"] is None else {"minor": row["price_minor"], "currency": row["price_currency"]},
                   in_closet_since=row["created_at"].year)
    return out


class ClosetVisibilityService:
    def __init__(self, database, *, catalog: Any = None):
        self.db = database
        self.catalog = catalog  # HouseCatalog for house refs; None shows no house

    def set_visibility(self, principal: Principal, item_id: Any, body: Any) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:write")
        item_id = require_uuid(item_id, name="item_id")
        if principal.delegation_id:
            raise ValidationFailed("who sees your closet is your own choice; an agent cannot change it", extra={"field": "visibility"})
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("visibility", "detail", "showcase_note"), where="closet visibility")
        audience = body.get("visibility")
        if audience not in AUDIENCES:
            raise ValidationFailed(f"visibility must be one of {AUDIENCES}", extra={"field": "visibility"})
        detail = body.get("detail", "piece")
        if audience == "private":
            if "detail" in body:
                raise ValidationFailed("a private piece has no detail level", extra={"field": "detail"})
            detail = None
        elif detail not in DETAILS or (audience == "members" and DETAILS.index(detail) > DETAILS.index(STRANGER_MAX_DETAIL)):
            raise ValidationFailed("members who are not your friends see at most the story; price stays with friends", extra={"field": "detail"})
        note = body.get("showcase_note")
        if note is not None:
            note = require_text(note, name="showcase_note", max_len=280)
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, me):
                raise NotFound("item not found")
            rows = query(txn, "SELECT collection, version, showcase_note FROM WardrobeItems WHERE member_id=@m AND item_id=@i",
                         {"m": me, "i": item_id}, {"m": STR, "i": STR})
            if not rows:
                raise NotFound("item not found")
            collection, version, old_note = rows[0]
            if audience != "private" and collection not in SHOWN_COLLECTIONS:
                raise ValidationFailed("only pieces you own (or digital pieces) can be shown", extra={"field": "visibility"})
            guard_write(txn, me, "wardrobe.items")
            kept_note = note if "showcase_note" in body else old_note
            txn.update("WardrobeItems", columns=("member_id", "item_id", "visibility", "visible_detail", "showcase_note", "version", "updated_at"),
                       values=[(me, item_id, None if audience == "private" else audience, detail, kept_note, version + 1, COMMIT_TIMESTAMP)])
            ctx.emit("wardrobe.item.updated", "1", "wardrobe_item", item_id, version + 1,
                     {"member_id": me, "item_id": item_id, "item_version": str(version + 1), "collection": collection,
                      "changed_fields": ["visibility"]}, "member_private")
            return {"item_id": item_id, "visibility": audience, "detail": detail, "showcase_note": kept_note, "version": str(version + 1)}

        return command(self.db, principal, tx)

    def closet(self, viewer: Principal, owner_id: Any) -> Dict[str, Any]:
        """What ``viewer`` may see of ``owner_id``'s closet. Hidden members and
        empty closets look the same. The owner sees every piece they show, as friends see it."""
        require_scope(viewer, "wardrobe:read")
        owner = require_uuid(owner_id, name="member_id")

        def read(s):
            rel = relation(s, viewer.member_id, owner)
            if rel is None or not member_active(s, owner):
                return {"member_id": owner, "items": [], "relation": None}
            audiences = ["members"] if rel == "members" else ["friends", "members"]
            rows = [dict(zip(_COLS, r)) for r in query(
                s, f"SELECT {', '.join(_COLS)} FROM WardrobeItems WHERE member_id=@m AND collection IN UNNEST(@c) AND visibility IN UNNEST(@a) "
                   "ORDER BY created_at DESC, item_id LIMIT @l",
                {"m": owner, "c": list(SHOWN_COLLECTIONS), "a": audiences, "l": MAX_SHOWN},
                {"m": STR, "c": STR_ARRAY, "a": STR_ARRAY, "l": INT})]
            houses = self.catalog.houses_of(s, sorted({r["product_id"] for r in rows if r["product_id"]})) if self.catalog and rows else {}
            return {"member_id": owner, "relation": rel, "items": [shown_piece(r, houses) for r in rows]}

        return run_read(self.db, read)


def visible_items(snap, viewer: str, owner: str, item_ids: List[str]) -> List[Dict[str, Any]]:
    """The subset of ``item_ids`` the viewer may see, in the given order (persona card highlights)."""
    if not item_ids:
        return []
    rel = relation(snap, viewer, owner)
    rows = {r[0]: dict(zip(_COLS, r)) for r in query(
        snap, f"SELECT {', '.join(_COLS)} FROM WardrobeItems WHERE member_id=@m AND item_id IN UNNEST(@i) AND collection IN UNNEST(@c)",
        {"m": owner, "i": list(item_ids), "c": list(SHOWN_COLLECTIONS)}, {"m": STR, "i": STR_ARRAY, "c": STR_ARRAY})}
    return [rows[i] for i in item_ids if i in rows and allowed(rows[i]["visibility"], rel)]
