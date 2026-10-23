"""
Outfits, friend proposals and packing lists (ch.01 §5.4; BM-WARD-006/007).

An outfit is a versioned composition of the owner's wardrobe item references.
Versions are immutable. A friend never edits the owner's outfit: they submit a
proposal; accepting it creates a *new* version authored by the friend, so the
original and the accepted author attribution are both preserved. Packing
lists reference outfits/items; trip dates stay private (no event carries them).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject

from brandme_core.domains.persona.kernel import (
    INT,
    STR,
    STR_ARRAY,
    Clock,
    CommandContext,
    DetailedInvalidTransition,
    DetailedVersionConflict,
    NotFound,
    Principal,
    SystemClock,
    ValidationFailed,
    canonical_digest,
    command,
    decode_cursor,
    encode_cursor,
    idempotent_command,
    iso,
    json_value,
    guard_write,
    member_active,
    new_id,
    parse_revision,
    query,
    reject_non_finite,
    reject_unknown_keys,
    require_scope,
    require_strict_int,
    require_text,
    require_uuid,
    run_read,
)

from . import events as _events  # noqa: F401

VISIBILITIES = ("private", "friends", "selected", "public")
MAX_ITEMS_PER_OUTFIT = 20
PACKING_STATES = ("to_pack", "packed", "needs_care")

# (txn, owner_member_id, proposer_member_id) -> bool. Injected; the social
# domain supplies the friendship/grant check. Default: deny (fail closed).
ProposalPolicy = Callable[[Any, str, str], bool]


def _deny(_txn, _owner, _proposer) -> bool:
    return False


def _composition(body: Mapping[str, Any]) -> Dict[str, Any]:
    refs = body.get("item_refs")
    if not isinstance(refs, list) or not (1 <= len(refs) <= MAX_ITEMS_PER_OUTFIT):
        raise ValidationFailed(f"item_refs must list 1-{MAX_ITEMS_PER_OUTFIT} wardrobe items", extra={"field": "item_refs"})
    refs = [require_uuid(r, name="item_refs") for r in refs]
    if len(set(refs)) != len(refs):
        raise ValidationFailed("item_refs must be unique", extra={"field": "item_refs"})
    layer = body.get("layer_order", refs)
    if not isinstance(layer, list) or sorted(require_uuid(x, name="layer_order") for x in layer) != sorted(refs):
        raise ValidationFailed("layer_order must be a permutation of item_refs", extra={"field": "layer_order"})
    subs = body.get("substitutes")
    if subs is not None:
        if not isinstance(subs, Mapping) or len(subs) > MAX_ITEMS_PER_OUTFIT:
            raise ValidationFailed("substitutes must map item ids to alternatives")
        subs = {require_uuid(k, name="substitutes"): [require_uuid(x, name="substitutes") for x in v] for k, v in subs.items()}
        if set(subs) - set(refs):
            raise ValidationFailed("substitutes must reference items in the outfit")
    occasion = require_text(body["occasion"], name="occasion", max_len=60) if body.get("occasion") is not None else None
    notes = require_text(body["notes"], name="notes", max_len=1000) if body.get("notes") is not None else None
    return {"item_refs": refs, "layer_order": [str(x) for x in layer], "substitutes": subs, "occasion": occasion, "notes": notes}


def _all_refs(comp: Mapping[str, Any]) -> List[str]:
    """Every item an outfit version names: its items and each substitute."""
    alts = [x for v in (comp["substitutes"] or {}).values() for x in v]
    return list(dict.fromkeys([*comp["item_refs"], *alts]))


class OutfitService:
    def __init__(self, database, *, clock: Clock = None, proposal_policy: ProposalPolicy = _deny):
        self.db = database
        self.clock = clock or SystemClock()
        self.proposal_policy = proposal_policy

    # ---------------------------------------------------------- helpers

    def _outfit(self, txn, owner: str, outfit_id: str) -> Optional[Dict[str, Any]]:
        rows = query(
            txn,
            "SELECT title, visibility, head_version, version, archived, created_at, updated_at FROM Outfits WHERE member_id=@m AND outfit_id=@o",
            {"m": owner, "o": outfit_id},
            {"m": STR, "o": STR},
        )
        if not rows:
            return None
        return dict(zip(("title", "visibility", "head_version", "version", "archived", "created_at", "updated_at"), rows[0]), outfit_id=outfit_id, member_id=owner)

    def _versions(self, txn, owner: str, outfit_id: str) -> List[Dict[str, Any]]:
        cols = ("version_no", "item_refs", "layer_order", "substitutes", "occasion", "notes", "author_member_id", "source_proposal_id", "created_at")
        rows = query(
            txn,
            f"SELECT {', '.join(cols)} FROM OutfitVersions WHERE member_id=@m AND outfit_id=@o ORDER BY version_no",
            {"m": owner, "o": outfit_id},
            {"m": STR, "o": STR},
        )
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            out.append(
                {
                    "version_no": str(d["version_no"]),
                    "item_refs": list(d["item_refs"]),
                    "layer_order": list(d["layer_order"]),
                    "substitutes": json_value(d["substitutes"]),
                    "occasion": d["occasion"],
                    "notes": d["notes"],
                    "author_member_id": d["author_member_id"],
                    "source_proposal_id": d["source_proposal_id"],
                    "created_at": iso(d["created_at"]),
                }
            )
        return out

    def _check_items(self, txn, owner: str, refs: Sequence[str]) -> None:
        rows = query(
            txn,
            "SELECT item_id FROM WardrobeItems WHERE member_id=@m AND item_id IN UNNEST(@ids) AND collection != 'archive'",
            {"m": owner, "ids": list(refs)},
            {"m": STR, "ids": STR_ARRAY},
        )
        missing = sorted(set(refs) - {r[0] for r in rows})
        if missing:
            raise ValidationFailed("every outfit item must be an active item in the owner's closet", extra={"missing_item_refs": missing})

    def _insert_version(self, txn, ctx: CommandContext, owner: str, outfit_id: str, version_no: int, comp: Mapping[str, Any], author: str, proposal_id: Optional[str]) -> None:
        txn.insert(
            "OutfitVersions",
            columns=("member_id", "outfit_id", "version_no", "item_refs", "layer_order", "substitutes", "occasion", "notes", "author_member_id", "source_proposal_id", "created_at"),
            values=[(owner, outfit_id, version_no, comp["item_refs"], comp["layer_order"], JsonObject(comp["substitutes"]) if comp["substitutes"] else None,
                     comp["occasion"], comp["notes"], author, proposal_id, COMMIT_TIMESTAMP)],
        )
        ctx.emit(
            "outfit.version.created", "1", "outfit", outfit_id, version_no,
            {"outfit_id": outfit_id, "owner_member_id": owner, "version_no": str(version_no), "author_member_id": author, "source_proposal_id": proposal_id},
            "member_private",
        )

    def _dto(self, txn, o: Mapping[str, Any]) -> Dict[str, Any]:
        versions = self._versions(txn, o["member_id"], o["outfit_id"])
        return {
            "outfit_id": o["outfit_id"],
            "owner_member_id": o["member_id"],
            "title": o["title"],
            "visibility": o["visibility"],
            "head_version": str(o["head_version"]),
            "version": str(o["version"]),
            "head": next((v for v in versions if v["version_no"] == str(o["head_version"])), None),
            "versions": versions,
        }

    # ---------------------------------------------------------- outfits

    def create_outfit(self, principal: Principal, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        require_scope(principal, "outfits:write")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_non_finite(body)
        reject_unknown_keys(body, ("title", "visibility", "item_refs", "layer_order", "substitutes", "occasion", "notes"), where="outfit")
        title = require_text(body.get("title"), name="title", max_len=120)
        visibility = body.get("visibility", "private")
        if visibility not in VISIBILITIES:
            raise ValidationFailed(f"visibility must be one of {VISIBILITIES}", extra={"field": "visibility"})
        comp = _composition(body)
        owner = principal.member_id

        def txn_fn(txn, ctx: CommandContext):
            if not member_active(txn, owner):
                raise NotFound("member not found")
            guard_write(txn, owner, "wardrobe.outfits")
            self._check_items(txn, owner, _all_refs(comp))
            outfit_id = new_id()
            txn.insert(
                "Outfits",
                columns=("member_id", "outfit_id", "title", "visibility", "head_version", "version", "archived", "created_at", "updated_at"),
                values=[(owner, outfit_id, title, visibility, 1, 1, False, COMMIT_TIMESTAMP, COMMIT_TIMESTAMP)],
            )
            self._insert_version(txn, ctx, owner, outfit_id, 1, comp, owner, None)
            now = iso(self.clock.now())
            return {
                "outfit_id": outfit_id,
                "owner_member_id": owner,
                "title": title,
                "visibility": visibility,
                "head_version": "1",
                "version": "1",
                "head": {**{k: comp[k] for k in ("item_refs", "layer_order", "substitutes", "occasion", "notes")}, "version_no": "1",
                         "author_member_id": owner, "source_proposal_id": None, "created_at": now},
            }

        response, _ = idempotent_command(self.db, principal, "outfits.create", idempotency_key, dict(body), txn_fn)
        return response

    def get_outfit(self, principal: Principal, outfit_id: str) -> Dict[str, Any]:
        require_scope(principal, "outfits:read")
        outfit_id = require_uuid(outfit_id, name="outfit_id")

        def read(s):
            o = self._outfit(s, principal.member_id, outfit_id)
            if o is None:
                raise NotFound("outfit not found")
            return self._dto(s, o)

        return run_read(self.db, read)

    def list_outfits(self, principal: Principal, *, cursor: Optional[str] = None, limit: int = 24) -> Dict[str, Any]:
        require_scope(principal, "outfits:read")
        limit = require_strict_int(limit, name="limit", lo=1, hi=100)
        params: Dict[str, Any] = {"m": principal.member_id, "n": limit + 1}
        types: Dict[str, Any] = {"m": STR, "n": INT}
        sql = "SELECT outfit_id, title, visibility, head_version, updated_at FROM Outfits WHERE member_id=@m AND NOT archived "
        if cursor:
            (oid,) = decode_cursor(cursor, kinds=("id",))
            sql += "AND outfit_id > @c "
            params["c"], types["c"] = oid, STR
        sql += "ORDER BY outfit_id LIMIT @n"
        rows = run_read(self.db, lambda s: query(s, sql, params, types))
        items = [
            {"outfit_id": r[0], "title": r[1], "visibility": r[2], "head_version": str(r[3]), "updated_at": iso(r[4])} for r in rows[:limit]
        ]
        return {"items": items, "next_cursor": encode_cursor(rows[limit - 1][0]) if len(rows) > limit else None}

    def create_version(self, principal: Principal, outfit_id: str, if_match: Optional[str], body: Any) -> Dict[str, Any]:
        """Owner edit = a new immutable version on top of the current head."""
        require_scope(principal, "outfits:write")
        outfit_id = require_uuid(outfit_id, name="outfit_id")
        expected = parse_revision(if_match)
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_non_finite(body)
        reject_unknown_keys(body, ("item_refs", "layer_order", "substitutes", "occasion", "notes"), where="outfit version")
        comp = _composition(body)

        def txn_fn(txn, ctx: CommandContext):
            o = self._outfit(txn, principal.member_id, outfit_id)
            if o is None or o["archived"]:
                raise NotFound("outfit not found")
            guard_write(txn, principal.member_id, "wardrobe.outfits")
            if expected != o["head_version"]:
                raise DetailedVersionConflict("outfit has a newer version", o["head_version"])
            self._check_items(txn, principal.member_id, _all_refs(comp))
            v = o["head_version"] + 1
            self._insert_version(txn, ctx, principal.member_id, outfit_id, v, comp, principal.member_id, None)
            txn.update("Outfits", columns=("member_id", "outfit_id", "head_version", "version", "updated_at"),
                       values=[(principal.member_id, outfit_id, v, o["version"] + 1, COMMIT_TIMESTAMP)])
            return v

        command(self.db, principal, txn_fn)
        # Reads inside the transaction cannot see its buffered version; re-read after commit.
        return self.get_outfit(principal, outfit_id)

    # -------------------------------------------------------- proposals

    def _owner_of(self, txn, outfit_id: str) -> Optional[str]:
        rows = query(txn, "SELECT member_id FROM Outfits@{FORCE_INDEX=OutfitsByOutfitId} WHERE outfit_id=@o", {"o": outfit_id}, {"o": STR})
        return rows[0][0] if rows else None

    def propose(self, principal: Principal, outfit_id: str, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        """A friend's styling proposal; never edits the owner's outfit. The owner is
        resolved from the outfit id, never taken from the request."""
        require_scope(principal, "outfits:write")
        outfit_id = require_uuid(outfit_id, name="outfit_id")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_non_finite(body)
        reject_unknown_keys(body, ("base_version", "item_refs", "layer_order", "notes"), where="proposal")
        comp = _composition(body)
        base = body.get("base_version")
        if not isinstance(base, str) or not base.isdigit():
            raise ValidationFailed("base_version is required", extra={"field": "base_version"})
        digest = canonical_digest({"item_refs": sorted(comp["item_refs"]), "layer_order": comp["layer_order"]})

        def txn_fn(txn, ctx: CommandContext):
            owner = self._owner_of(txn, outfit_id)
            if owner == principal.member_id:
                raise DetailedInvalidTransition("edit your own outfit by creating a version", code="self_proposal")
            o = self._outfit(txn, owner, outfit_id) if owner else None
            # Same 404 whether the outfit is missing or the proposer may not see it.
            if o is None or o["archived"] or not self.proposal_policy(txn, owner, principal.member_id):
                raise NotFound("outfit not found")
            guard_write(txn, principal.member_id, "wardrobe.proposals_authored")
            guard_write(txn, owner, "wardrobe.outfits")
            if not 1 <= int(base) <= o["head_version"] or not query(
                txn, "SELECT 1 FROM OutfitVersions WHERE member_id=@m AND outfit_id=@o AND version_no=@v",
                {"m": owner, "o": outfit_id, "v": int(base)}, {"m": STR, "o": STR, "v": INT}):
                raise ValidationFailed("base_version does not exist", extra={"field": "base_version"})
            if query(
                txn,
                "SELECT 1 FROM OutfitProposals@{FORCE_INDEX=OutfitProposalsByContent} WHERE member_id=@m AND outfit_id=@o "
                "AND proposer_member_id=@p AND content_digest=@d",
                {"m": owner, "o": outfit_id, "p": principal.member_id, "d": digest},
                {"m": STR, "o": STR, "p": STR, "d": STR},
            ):
                raise DetailedInvalidTransition("you already proposed this exact look", code="duplicate_proposal")
            self._check_items(txn, owner, _all_refs(comp))
            proposal_id = new_id()
            txn.insert(
                "OutfitProposals",
                columns=("member_id", "outfit_id", "proposal_id", "proposer_member_id", "base_version", "item_refs", "layer_order", "notes", "content_digest", "state", "created_at"),
                values=[(owner, outfit_id, proposal_id, principal.member_id, int(base), comp["item_refs"], comp["layer_order"], comp["notes"], digest, "pending", COMMIT_TIMESTAMP)],
            )
            ctx.emit(
                "outfit.proposal.created", "1", "outfit", outfit_id, o["version"],
                {"outfit_id": outfit_id, "owner_member_id": owner, "proposal_id": proposal_id, "proposer_member_id": principal.member_id},
                "member_private",
            )
            return {"proposal_id": proposal_id, "outfit_id": outfit_id, "state": "pending", "base_version": base}

        response, _ = idempotent_command(self.db, principal, "outfits.propose", idempotency_key, {"outfit": outfit_id, **dict(body)}, txn_fn)
        return response

    def list_proposals(self, principal: Principal, outfit_id: str) -> List[Dict[str, Any]]:
        require_scope(principal, "outfits:read")
        outfit_id = require_uuid(outfit_id, name="outfit_id")
        cols = ("proposal_id", "proposer_member_id", "base_version", "item_refs", "layer_order", "notes", "state", "accepted_version", "created_at")
        rows = run_read(
            self.db,
            lambda s: query(
                s,
                f"SELECT {', '.join(cols)} FROM OutfitProposals WHERE member_id=@m AND outfit_id=@o ORDER BY created_at, proposal_id",
                {"m": principal.member_id, "o": outfit_id},
                {"m": STR, "o": STR},
            ),
        )
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            d.update(base_version=str(d["base_version"]), item_refs=list(d["item_refs"]), layer_order=list(d["layer_order"]),
                     accepted_version=None if d["accepted_version"] is None else str(d["accepted_version"]), created_at=iso(d["created_at"]))
            out.append(d)
        return out

    def decide_proposal(self, principal: Principal, outfit_id: str, proposal_id: str, decision: str, if_match: Optional[str]) -> Dict[str, Any]:
        """Owner accepts (new version authored by the proposer) or declines."""
        require_scope(principal, "outfits:write")
        outfit_id = require_uuid(outfit_id, name="outfit_id")
        proposal_id = require_uuid(proposal_id, name="proposal_id")
        if decision not in ("accept", "decline"):
            raise ValidationFailed("decision must be accept or decline", extra={"field": "decision"})
        expected = parse_revision(if_match) if decision == "accept" else None
        owner = principal.member_id

        def txn_fn(txn, ctx: CommandContext):
            o = self._outfit(txn, owner, outfit_id)
            if o is None or o["archived"]:
                raise NotFound("outfit not found")
            guard_write(txn, owner, "wardrobe.outfits")
            rows = query(
                txn,
                "SELECT proposer_member_id, item_refs, layer_order, notes, state FROM OutfitProposals "
                "WHERE member_id=@m AND outfit_id=@o AND proposal_id=@p",
                {"m": owner, "o": outfit_id, "p": proposal_id},
                {"m": STR, "o": STR, "p": STR},
            )
            if not rows:
                raise NotFound("proposal not found")
            proposer, refs, layer, notes, state = rows[0]
            if state != "pending":
                raise DetailedInvalidTransition(f"this proposal was already {state}", code="proposal_decided")
            if decision == "decline":
                txn.update("OutfitProposals", columns=("member_id", "outfit_id", "proposal_id", "state", "decided_at"),
                           values=[(owner, outfit_id, proposal_id, "declined", COMMIT_TIMESTAMP)])
                return {"proposal_id": proposal_id, "state": "declined"}
            if expected != o["head_version"]:
                raise DetailedVersionConflict("outfit has a newer version", o["head_version"])
            self._check_items(txn, owner, list(refs))
            v = o["head_version"] + 1
            comp = {"item_refs": list(refs), "layer_order": list(layer), "substitutes": None, "occasion": None, "notes": notes}
            self._insert_version(txn, ctx, owner, outfit_id, v, comp, proposer, proposal_id)
            txn.update("Outfits", columns=("member_id", "outfit_id", "head_version", "version", "updated_at"),
                       values=[(owner, outfit_id, v, o["version"] + 1, COMMIT_TIMESTAMP)])
            txn.update("OutfitProposals", columns=("member_id", "outfit_id", "proposal_id", "state", "accepted_version", "decided_at"),
                       values=[(owner, outfit_id, proposal_id, "accepted", v, COMMIT_TIMESTAMP)])
            ctx.emit(
                "outfit.proposal.accepted", "1", "outfit", outfit_id, o["version"] + 1,
                {"outfit_id": outfit_id, "owner_member_id": owner, "proposal_id": proposal_id, "proposer_member_id": proposer, "accepted_version": str(v)},
                "member_private",
            )
            return {"proposal_id": proposal_id, "state": "accepted", "accepted_version": str(v), "author_member_id": proposer}

        return command(self.db, principal, txn_fn)

    # ---------------------------------------------------------- packing

    def create_packing_list(self, principal: Principal, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:write")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("title", "starts_on", "ends_on", "entries"), where="packing list")
        title = require_text(body.get("title"), name="title", max_len=120)
        dates = {}
        for k in ("starts_on", "ends_on"):
            v = body.get(k)
            if v is not None:
                try:
                    dates[k] = date.fromisoformat(v) if isinstance(v, str) else None
                except ValueError:
                    dates[k] = None
                if dates[k] is None:
                    raise ValidationFailed(f"{k} must be YYYY-MM-DD", extra={"field": k})
        if dates.get("starts_on") and dates.get("ends_on") and dates["ends_on"] < dates["starts_on"]:
            raise ValidationFailed("ends_on is before starts_on")
        entries_in = body.get("entries") or []
        if not isinstance(entries_in, list) or len(entries_in) > 100:
            raise ValidationFailed("entries must be a list of at most 100")
        entries = []
        for e in entries_in:
            if not isinstance(e, Mapping):
                raise ValidationFailed("each entry must be an object")
            reject_unknown_keys(e, ("outfit_id", "item_id", "quantity"), where="packing entry")
            if (e.get("outfit_id") is None) == (e.get("item_id") is None):
                raise ValidationFailed("each entry references exactly one outfit or item")
            entries.append({
                "outfit_id": require_uuid(e["outfit_id"], name="outfit_id") if e.get("outfit_id") else None,
                "item_id": require_uuid(e["item_id"], name="item_id") if e.get("item_id") else None,
                "quantity": require_strict_int(e.get("quantity", 1), name="quantity", lo=1, hi=99),
            })

        def txn_fn(txn, ctx: CommandContext):
            guard_write(txn, principal.member_id, "wardrobe.packing")
            if not member_active(txn, principal.member_id):
                raise NotFound("member not found")
            item_ids = [e["item_id"] for e in entries if e["item_id"]]
            if item_ids:
                self._check_items(txn, principal.member_id, item_ids)
            for e in entries:
                if e["outfit_id"] and self._outfit(txn, principal.member_id, e["outfit_id"]) is None:
                    raise ValidationFailed("unknown outfit in packing list", extra={"field": "outfit_id"})
            list_id = new_id()
            txn.insert("PackingLists", columns=("member_id", "list_id", "title", "starts_on", "ends_on", "version", "created_at", "updated_at"),
                       values=[(principal.member_id, list_id, title, dates.get("starts_on"), dates.get("ends_on"), 1, COMMIT_TIMESTAMP, COMMIT_TIMESTAMP)])
            out_entries = []
            for e in entries:
                eid = new_id()
                txn.insert("PackingEntries", columns=("member_id", "list_id", "entry_id", "outfit_id", "item_id", "quantity", "state"),
                           values=[(principal.member_id, list_id, eid, e["outfit_id"], e["item_id"], e["quantity"], "to_pack")])
                out_entries.append({"entry_id": eid, **e, "state": "to_pack"})
            return {"list_id": list_id, "title": title, "starts_on": body.get("starts_on"), "ends_on": body.get("ends_on"), "version": "1", "entries": out_entries}

        response, _ = idempotent_command(self.db, principal, "packing.create", idempotency_key, dict(body), txn_fn)
        return response

    def set_packing_entry_state(self, principal: Principal, list_id: str, entry_id: str, state: str, if_match: Optional[str]) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:write")
        list_id, entry_id = require_uuid(list_id, name="list_id"), require_uuid(entry_id, name="entry_id")
        if state not in PACKING_STATES:
            raise ValidationFailed(f"state must be one of {PACKING_STATES}", extra={"field": "state"})
        expected = parse_revision(if_match)

        def txn_fn(txn, ctx: CommandContext):
            rows = query(txn, "SELECT version FROM PackingLists WHERE member_id=@m AND list_id=@l", {"m": principal.member_id, "l": list_id}, {"m": STR, "l": STR})
            if not rows:
                raise NotFound("packing list not found")
            guard_write(txn, principal.member_id, "wardrobe.packing")
            if rows[0][0] != expected:
                raise DetailedVersionConflict("packing list changed", rows[0][0])
            if not query(txn, "SELECT 1 FROM PackingEntries WHERE member_id=@m AND list_id=@l AND entry_id=@e",
                         {"m": principal.member_id, "l": list_id, "e": entry_id}, {"m": STR, "l": STR, "e": STR}):
                raise NotFound("entry not found")
            txn.update("PackingEntries", columns=("member_id", "list_id", "entry_id", "state"), values=[(principal.member_id, list_id, entry_id, state)])
            txn.update("PackingLists", columns=("member_id", "list_id", "version", "updated_at"), values=[(principal.member_id, list_id, expected + 1, COMMIT_TIMESTAMP)])
            return {"list_id": list_id, "entry_id": entry_id, "state": state, "version": str(expected + 1)}

        return command(self.db, principal, txn_fn)

    def get_packing_list(self, principal: Principal, list_id: str) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:read")
        list_id = require_uuid(list_id, name="list_id")

        def read(s):
            rows = query(s, "SELECT title, starts_on, ends_on, version FROM PackingLists WHERE member_id=@m AND list_id=@l",
                         {"m": principal.member_id, "l": list_id}, {"m": STR, "l": STR})
            if not rows:
                raise NotFound("packing list not found")
            title, s_on, e_on, version = rows[0]
            entries = [
                {"entry_id": r[0], "outfit_id": r[1], "item_id": r[2], "quantity": r[3], "state": r[4]}
                for r in query(s, "SELECT entry_id, outfit_id, item_id, quantity, state FROM PackingEntries WHERE member_id=@m AND list_id=@l ORDER BY entry_id",
                               {"m": principal.member_id, "l": list_id}, {"m": STR, "l": STR})
            ]
            return {"list_id": list_id, "title": title, "starts_on": s_on.isoformat() if s_on else None,
                    "ends_on": e_on.isoformat() if e_on else None, "version": str(version), "entries": entries}

        return run_read(self.db, read)
