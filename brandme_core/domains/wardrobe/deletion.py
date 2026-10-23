"""W10 privacy registration for wardrobe, closet, outfits and packing.

Same pattern as persona: foundation ``register_data_category`` always, the
privacy lane's ``DomainPrivacyHandler`` when that module is present.

A friend's proposal on someone else's outfit belongs to the outfit owner's
record (it is attributed collaboration on their outfit). Deleting the
*proposer's* account anonymizes their attribution there rather than deleting
the owner's history (``wardrobe.proposals_authored``).
"""

from __future__ import annotations

from typing import Any, Dict, List

from brandme_core.domains import DataCategory as FoundationDataCategory, register_data_category
from brandme_core.domains.persona.kernel import NIL_MEMBER, STR, iso, json_value, query, run_read, run_txn
from brandme_core.domains.persona.privacy_guard import record_scope_refusal

DOMAIN = "wardrobe"
_M = {"m": STR}

CATEGORIES: Dict[str, Dict[str, Any]] = {
    "wardrobe.items": {
        "title": "Closet items (owned, wanted, on the way, archived) with care, wear and notes",
        "supplied_by": "member",
        "retention": "Until you delete them or your account; provider order evidence is referenced, not copied",
        "on_edit": "Edits change your closet record only; claim levels and order facts keep their authority",
        "tables": ("WardrobeItems", "WardrobeOrderLinks"),
    },
    "wardrobe.closet": {
        "title": "Your room choice and where each item is placed",
        "supplied_by": "member",
        "retention": "Until you change or delete it",
        "on_edit": "Placement is decorative and never changes ownership",
        "tables": ("ClosetLayouts", "ClosetPlacements"),
    },
    "wardrobe.outfits": {
        "title": "Outfits, their versions and proposals friends sent you",
        "supplied_by": "member",
        "retention": "Until you delete them or your account",
        "on_edit": "Edits create a new version; earlier versions stay in your history",
        "tables": ("Outfits", "OutfitVersions", "OutfitProposals"),
    },
    "wardrobe.proposals_authored": {
        "title": "Styling proposals you sent to friends",
        "supplied_by": "member",
        "retention": "Part of your friend's outfit history; your name is removed if you delete your account",
        "on_edit": "Proposals cannot be edited after sending",
        "tables": ("OutfitProposals", "OutfitVersions"),
    },
    "wardrobe.packing": {
        "title": "Packing lists and trip dates",
        "supplied_by": "member",
        "retention": "Until you delete them; trip dates are never shared",
        "on_edit": "Packing states change only the list",
        "tables": ("PackingLists", "PackingEntries"),
    },
}


def export_category(snap, member_id: str, category: str) -> List[Dict[str, Any]]:
    m = {"m": member_id}
    if category == "wardrobe.items":
        cols = ("item_id", "title", "category", "collection", "claim_level", "evidence_status", "acquisition_source",
                "acquisition_status", "product_id", "variant_ref", "size_label", "colors", "materials", "care_state",
                "care_notes", "user_notes", "worn_count", "last_worn_at", "price_minor", "price_currency", "created_at")
        rows = query(snap, f"SELECT {', '.join(cols)} FROM WardrobeItems WHERE member_id=@m ORDER BY created_at, item_id", m, _M)
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            d.update(colors=list(d["colors"] or []), materials=list(d["materials"] or []), last_worn_at=iso(d["last_worn_at"]),
                     created_at=iso(d["created_at"]), price_minor=None if d["price_minor"] is None else str(d["price_minor"]))
            out.append(d)
        return out
    if category == "wardrobe.closet":
        layout = query(snap, "SELECT room_template_id, room_revision, version FROM ClosetLayouts WHERE member_id=@m", m, _M)
        pls = query(snap, "SELECT item_id, room_template_id, semantic_group, slot_id, pos_x, pos_y, pos_z, rot_x, rot_y, rot_z, rot_w, uniform_scale "
                          "FROM ClosetPlacements WHERE member_id=@m ORDER BY item_id", m, _M)
        return [{
            "layout": None if not layout else {"room_template_id": layout[0][0], "room_revision": layout[0][1], "version": str(layout[0][2])},
            "placements": [
                {"item_id": p[0], "room_template_id": p[1], "semantic_group": p[2], "slot_id": p[3],
                 "position_meters": None if p[4] is None else [p[4], p[5], p[6]],
                 "rotation_quaternion": None if p[7] is None else [p[7], p[8], p[9], p[10]], "uniform_scale": p[11]}
                for p in pls
            ],
        }]
    if category == "wardrobe.outfits":
        outs = []
        for o in query(snap, "SELECT outfit_id, title, visibility, head_version FROM Outfits WHERE member_id=@m ORDER BY outfit_id", m, _M):
            versions = query(snap, "SELECT version_no, item_refs, layer_order, substitutes, occasion, notes, author_member_id, created_at "
                                   "FROM OutfitVersions WHERE member_id=@m AND outfit_id=@o ORDER BY version_no",
                             {"m": member_id, "o": o[0]}, {"m": STR, "o": STR})
            outs.append({"outfit_id": o[0], "title": o[1], "visibility": o[2], "head_version": str(o[3]), "versions": [
                {"version_no": str(v[0]), "item_refs": list(v[1]), "layer_order": list(v[2]), "substitutes": json_value(v[3]),
                 "occasion": v[4], "notes": v[5], "author_member_id": v[6], "created_at": iso(v[7])} for v in versions]})
        return outs
    if category == "wardrobe.proposals_authored":
        return [
            {"owner_outfit_ref": f"{r[0]}/{r[1]}", "proposal_id": r[2], "state": r[3], "notes": r[4], "created_at": iso(r[5])}
            for r in query(snap, "SELECT member_id, outfit_id, proposal_id, state, notes, created_at FROM OutfitProposals@{FORCE_INDEX=OutfitProposalsByProposer} "
                                 "WHERE proposer_member_id=@m ORDER BY created_at", m, _M)
        ]
    if category == "wardrobe.packing":
        lists = []
        for pl in query(snap, "SELECT list_id, title, starts_on, ends_on FROM PackingLists WHERE member_id=@m ORDER BY list_id", m, _M):
            entries = query(snap, "SELECT entry_id, outfit_id, item_id, quantity, state FROM PackingEntries WHERE member_id=@m AND list_id=@l",
                            {"m": member_id, "l": pl[0]}, {"m": STR, "l": STR})
            lists.append({"list_id": pl[0], "title": pl[1], "starts_on": pl[2].isoformat() if pl[2] else None,
                          "ends_on": pl[3].isoformat() if pl[3] else None,
                          "entries": [{"entry_id": e[0], "outfit_id": e[1], "item_id": e[2], "quantity": e[3], "state": e[4]} for e in entries]})
        return lists
    raise KeyError(category)


def delete_category(txn, member_id: str, category: str) -> int:
    m = {"m": member_id}
    if category == "wardrobe.items":
        n = txn.execute_update("DELETE FROM ClosetPlacements WHERE member_id=@m", params=m, param_types=_M)
        n += txn.execute_update("DELETE FROM WardrobeOrderLinks WHERE member_id=@m", params=m, param_types=_M)
        n += txn.execute_update("DELETE FROM WardrobeItems WHERE member_id=@m", params=m, param_types=_M)
        return n
    if category == "wardrobe.closet":
        n = txn.execute_update("DELETE FROM ClosetPlacements WHERE member_id=@m", params=m, param_types=_M)
        return n + txn.execute_update("DELETE FROM ClosetLayouts WHERE member_id=@m", params=m, param_types=_M)
    if category == "wardrobe.outfits":
        return txn.execute_update("DELETE FROM Outfits WHERE member_id=@m", params=m, param_types=_M)  # versions/proposals cascade
    if category == "wardrobe.proposals_authored":
        # Anonymize, do not erase another member's outfit history.
        n = txn.execute_update(
            "UPDATE OutfitProposals SET proposer_member_id=@nil, notes=NULL WHERE proposer_member_id=@m",
            params={"m": member_id, "nil": NIL_MEMBER}, param_types={"m": STR, "nil": STR},
        )
        n += txn.execute_update(
            "UPDATE OutfitVersions SET author_member_id=@nil WHERE author_member_id=@m AND member_id != @m",
            params={"m": member_id, "nil": NIL_MEMBER}, param_types={"m": STR, "nil": STR},
        )
        return n
    if category == "wardrobe.packing":
        return txn.execute_update("DELETE FROM PackingLists WHERE member_id=@m", params=m, param_types=_M)
    raise KeyError(category)


for _key, _c in CATEGORIES.items():
    register_data_category(FoundationDataCategory(
        name=_key, domain=DOMAIN, description=_c["title"], supplied_by=_c["supplied_by"], visible_to="member only",
        retention=_c["retention"], tables=_c["tables"],
        export=(lambda k: lambda db, mid: run_read(db, lambda s: export_category(s, mid, k)))(_key),
        delete=(lambda k: lambda db, mid: run_txn(db, lambda t: delete_category(t, mid, k)))(_key),
    ))


def build_privacy_handler():
    """A fresh handler instance, or None when the privacy lane is absent."""
    try:
        from brandme_core.domains.privacy import deletion as pd
    except ImportError:
        return None

    class WardrobePrivacyHandler:
        domain = DOMAIN

        def categories(self):
            return [
                pd.DataCategory(
                    key=k, domain=DOMAIN, title=c["title"], supplied_by=pd.Supplier.MEMBER, visible_to=("member",),
                    retention=c["retention"], on_edit=c["on_edit"],
                    on_delete=pd.OnDelete.ANONYMIZE if k == "wardrobe.proposals_authored" else pd.OnDelete.ERASE,
                )
                for k, c in CATEGORIES.items()
            ]

        def export(self, snapshot, ctx, category):
            return pd.ExportSection(category, export_category(snapshot, ctx.subject_ref, category))

        def delete(self, txn, ctx, category):
            return record_scope_refusal(pd, ctx, category) or pd.DeletionOutcome(category, delete_category(txn, ctx.subject_ref, category))

        def purge_derived(self, ctx, category):
            return pd.DeletionOutcome(category, 0, done=True, detail="wardrobe keeps no derived stores; try-on media is purged by the media domain")

        def reapply_tombstone(self, txn, tombstone):
            if tombstone.record_keys:
                return 0  # record-level deletions are refused by delete(); nothing to reapply
            return delete_category(txn, tombstone.subject_ref, tombstone.category)

    return WardrobePrivacyHandler()


def _register_default():
    handler = build_privacy_handler()
    if handler is None:
        return None
    from brandme_core.domains.privacy import deletion as pd

    try:
        pd.register_domain(handler)
    except pd.PrivacyRegistryError:
        # Already registered (module re-import) or a lane-local stand-in owns the
        # keys (e.g. the privacy lane's test fixture); never register twice.
        return None
    return handler


PRIVACY_HANDLER = _register_default()
