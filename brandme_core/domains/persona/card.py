"""
The living persona card (Ultra plan 02, item 6).

* **What it shows:**
  - up to three of the member's strongest taste leanings (never a hidden or
    unanswered axis);
  - the badges they hold;
  - their house standing tiers, only if they turn that on (off by default);
  - up to six pieces they pick as highlights.
* **Recomposition.** A trigger event marks the card stale: a persona change,
  a badge awarded or revoked, a wardrobe change, or a standings recompute. The
  jobs process recomposes stale cards each pass and backfills every card once
  a day, creating cards for members who have a profile but no card yet.
* **Who sees it.** The member chooses ``private``, ``friends`` (the default)
  or ``members``. A viewer sees a highlight only if that piece's own closet
  visibility allows it, at the piece's own detail level. A card the viewer may
  not see answers 404, exactly like one that does not exist.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Mapping, Optional

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject

from .kernel import (
    INT,
    STR,
    STR_ARRAY,
    TS,
    CommandContext,
    NotFound,
    Principal,
    ValidationFailed,
    command,
    guard_write,
    iso,
    json_value,
    member_active,
    processing_allowed,
    query,
    reject_unknown_keys,
    require_scope,
    require_uuid,
    run_read,
    run_txn,
    server_now,
    service_principal,
)

AUDIENCES = ("private", "friends", "members")
DEFAULT_AUDIENCE = "friends"
MAX_HIGHLIGHTS = 6
BACKFILL_EVERY = timedelta(hours=24)
TRIGGERS = ("persona.updated", "badge.awarded", "badge.revoked", "wardrobe.item.created", "wardrobe.item.updated")
CARD_COLS = ("member_id", "audience", "show_standings", "highlight_item_ids", "card", "composed_at", "stale_since", "version")


def _row(snap, member_id: str) -> Optional[Dict[str, Any]]:
    rows = query(snap, f"SELECT {', '.join(CARD_COLS)} FROM PersonaCards WHERE member_id=@m", {"m": member_id}, {"m": STR})
    if not rows:
        return None
    d = dict(zip(CARD_COLS, rows[0]))
    d["card"] = json_value(d["card"])
    d["highlight_item_ids"] = list(d["highlight_item_ids"] or [])
    return d


def mark_stale(txn, member_id: str, trigger: str) -> int:
    return txn.execute_update("UPDATE PersonaCards SET stale_since = COALESCE(stale_since, CURRENT_TIMESTAMP()), last_trigger=@t "
                              "WHERE member_id=@m", params={"m": member_id, "t": trigger[:40]}, param_types={"m": STR, "t": STR})


class PersonaCardService:
    def __init__(self, database, *, persona: Any, catalog: Any = None):
        self.db = database
        self.persona = persona
        self.catalog = catalog

    # -------------------------------------------------------------- compose

    def _compose(self, snap, member_id: str, settings: Mapping[str, Any]) -> Dict[str, Any]:
        try:
            taste = self.persona.taste_summary(snap, member_id)
        except NotFound:
            taste = []
        badges = [r[0] for r in query(snap, "SELECT badge_id FROM BadgeAwards WHERE member_id=@m AND revoked_at IS NULL ORDER BY badge_id",
                                      {"m": member_id}, {"m": STR})]
        standings = [{"house_ref": r[0], "tier": r[1]} for r in query(
            snap, "SELECT house_ref, tier FROM HouseStandings WHERE member_id=@m AND tier != 'member' ORDER BY house_ref",
            {"m": member_id}, {"m": STR})] if settings["show_standings"] else []
        keep = {r[0] for r in query(snap, "SELECT item_id FROM WardrobeItems WHERE member_id=@m AND item_id IN UNNEST(@i) "
                                          "AND collection IN ('owned', 'digital')",
                                    {"m": member_id, "i": list(settings["highlight_item_ids"])}, {"m": STR, "i": STR_ARRAY})}
        return {"taste": taste, "badges": badges, "standings": standings,
                "highlight_item_ids": [i for i in settings["highlight_item_ids"] if i in keep]}

    def recompose(self, member_id: str, *, trigger: str = "backfill") -> Optional[Dict[str, Any]]:
        def tx(txn, ctx: CommandContext):
            if not member_active(txn, member_id):
                return None
            now = server_now(txn)
            if not processing_allowed(txn, member_id, "persona.card", basis_time=now):
                return None
            row = _row(txn, member_id) or {"member_id": member_id, "audience": DEFAULT_AUDIENCE, "show_standings": False,
                                           "highlight_item_ids": [], "version": 0}
            card = self._compose(txn, member_id, row)
            txn.insert_or_update("PersonaCards", columns=("member_id", "audience", "show_standings", "highlight_item_ids", "card", "composed_at",
                                                          "stale_since", "last_trigger", "version", "updated_at"),
                                 values=[(member_id, row["audience"], row["show_standings"], row["highlight_item_ids"] or None, JsonObject(card),
                                          now, None, trigger[:40], row["version"] + 1, COMMIT_TIMESTAMP)])
            return {**card, "composed_at": iso(now)}

        return command(self.db, service_principal("persona.card"), tx)

    def recompose_due(self, *, limit: int = 200) -> Dict[str, int]:
        """Stale cards first, then the daily backfill (old cards, and profiles with no card yet)."""
        def due(s):
            now = server_now(s)
            stale = [r[0] for r in query(s, "SELECT member_id FROM PersonaCards@{FORCE_INDEX=PersonaCardsByStale} WHERE stale_since IS NOT NULL "
                                            "ORDER BY stale_since LIMIT @l", {"l": limit}, {"l": INT})]
            old = [r[0] for r in query(s, "SELECT member_id FROM PersonaCards WHERE stale_since IS NULL AND (composed_at IS NULL OR composed_at < @t) "
                                          "ORDER BY composed_at LIMIT @l", {"t": now - BACKFILL_EVERY, "l": limit}, {"t": TS, "l": INT})]
            new = [r[0] for r in query(s, "SELECT p.member_id FROM PersonaProfiles p LEFT JOIN PersonaCards c ON c.member_id = p.member_id "
                                          "WHERE c.member_id IS NULL LIMIT @l", {"l": limit}, {"l": INT})]
            return stale, old, new

        stale, old, new = run_read(self.db, due)
        done = {"stale": 0, "backfilled": 0, "created": 0}
        for name, ids, trig in (("stale", stale, "trigger"), ("backfilled", old, "backfill"), ("created", new, "backfill")):
            for m in ids:
                if self.recompose(m, trigger=trig) is not None:
                    done[name] += 1
        return done

    def mark_all_with_standings(self) -> int:
        """After a standings recompute, cards that show standings recompose."""
        return run_txn(self.db, lambda t: t.execute_update(
            "UPDATE PersonaCards SET stale_since = COALESCE(stale_since, CURRENT_TIMESTAMP()), last_trigger='standings.recomputed' "
            "WHERE show_standings"))

    # --------------------------------------------------------------- owner

    def settings(self, principal: Principal, body: Any) -> Dict[str, Any]:
        require_scope(principal, "profile:write")
        if principal.delegation_id:
            raise ValidationFailed("who sees your card is your own choice; an agent cannot change it")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("audience", "show_standings", "highlight_item_ids"), where="persona card")
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, me):
                raise NotFound("member not found")
            guard_write(txn, me, "persona.card")
            row = _row(txn, me) or {"audience": DEFAULT_AUDIENCE, "show_standings": False, "highlight_item_ids": [], "version": 0}
            audience = body.get("audience", row["audience"])
            if audience not in AUDIENCES:
                raise ValidationFailed(f"audience must be one of {AUDIENCES}", extra={"field": "audience"})
            show = body.get("show_standings", row["show_standings"])
            if not isinstance(show, bool):
                raise ValidationFailed("show_standings must be true or false", extra={"field": "show_standings"})
            ids = body.get("highlight_item_ids", row["highlight_item_ids"])
            if not isinstance(ids, list) or len(ids) > MAX_HIGHLIGHTS:
                raise ValidationFailed(f"pick at most {MAX_HIGHLIGHTS} highlights", extra={"field": "highlight_item_ids"})
            ids = [require_uuid(i, name="highlight_item_ids") for i in ids]
            if len(set(ids)) != len(ids):
                raise ValidationFailed("each highlight once", extra={"field": "highlight_item_ids"})
            owned = {r[0] for r in query(txn, "SELECT item_id FROM WardrobeItems WHERE member_id=@m AND item_id IN UNNEST(@i) "
                                              "AND collection IN ('owned', 'digital')", {"m": me, "i": ids}, {"m": STR, "i": STR_ARRAY})}
            if set(ids) - owned:
                raise ValidationFailed("highlights must be pieces you own", extra={"field": "highlight_item_ids"})
            settings = {"audience": audience, "show_standings": show, "highlight_item_ids": ids}
            card = self._compose(txn, me, settings)
            now = server_now(txn)
            txn.insert_or_update("PersonaCards", columns=("member_id", "audience", "show_standings", "highlight_item_ids", "card", "composed_at",
                                                          "stale_since", "last_trigger", "version", "updated_at"),
                                 values=[(me, audience, show, ids or None, JsonObject(card), now, None, "settings", row["version"] + 1, COMMIT_TIMESTAMP)])
            return {**settings, "card": card, "composed_at": iso(now)}

        return command(self.db, principal, tx)

    def mine(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "profile:read")
        me = principal.member_id
        row = run_read(self.db, lambda s: _row(s, me))
        if row is None or row["card"] is None:
            self.recompose(me, trigger="first_view")
            row = run_read(self.db, lambda s: _row(s, me))
        if row is None:
            raise NotFound("card not found")
        return {"audience": row["audience"], "show_standings": row["show_standings"], "highlight_item_ids": row["highlight_item_ids"],
                "card": self._view(None, me, row), "composed_at": iso(row["composed_at"]), "recomposing": row["stale_since"] is not None}

    # -------------------------------------------------------------- viewer

    def _view(self, snap, owner: str, row: Mapping[str, Any], viewer: Optional[str] = None) -> Dict[str, Any]:
        from brandme_core.domains.wardrobe.visibility import shown_piece, visible_items

        card = row["card"] or {}

        def pieces(s):
            items = visible_items(s, viewer or owner, owner, card.get("highlight_item_ids", []))
            houses = self.catalog.houses_of(s, sorted({i["product_id"] for i in items if i["product_id"]})) if self.catalog and items else {}
            return [shown_piece(i, houses) for i in items]

        highlights = pieces(snap) if snap is not None else run_read(self.db, pieces)
        return {"taste": card.get("taste", []), "badges": card.get("badges", []), "standings": card.get("standings", []), "highlights": highlights}

    def view(self, viewer: Principal, owner_id: Any) -> Dict[str, Any]:
        require_scope(viewer, "social:read")
        owner = require_uuid(owner_id, name="member_id")
        from brandme_core.domains.wardrobe.visibility import relation

        def read(s):
            row = _row(s, owner)
            rel = relation(s, viewer.member_id, owner)
            if row is None or row["card"] is None or rel is None or not member_active(s, owner):
                raise NotFound("card not found")
            if rel != "self" and (row["audience"] == "private" or (row["audience"] == "friends" and rel != "friends")):
                raise NotFound("card not found")
            return {"member_id": owner, "card": self._view(s, owner, row, viewer.member_id), "composed_at": iso(row["composed_at"])}

        return run_read(self.db, read)


class PersonaCardConsumer:
    """Marks cards stale on the trigger events (lane subscriber fan-out)."""

    def __init__(self, database):
        self.db = database

    def handle(self, event) -> Dict[str, Any]:
        member_id = (event.payload or {}).get("member_id")
        if event.event_type not in TRIGGERS or not member_id:
            return {"status": "ignored"}
        n = run_txn(self.db, lambda t: mark_stale(t, member_id, event.event_type))
        return {"status": "card_marked_stale" if n else "no_card"}


def export_card(snap, member_id: str) -> List[Dict[str, Any]]:
    row = _row(snap, member_id)
    if row is None:
        return []
    return [{"audience": row["audience"], "show_standings": row["show_standings"], "highlight_item_ids": row["highlight_item_ids"],
             "card": row["card"], "composed_at": iso(row["composed_at"])}]
