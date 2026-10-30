"""Wardrobe slices of guest → account migration (BM-ONB-004).

Registered with the persona onboarding registry; they run inside the same
transaction as the persona migration, so the guest's room choice and saved
products migrate together with the profile or not at all. Account data wins:
an existing room choice is kept, and a product already saved is not added twice.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

from brandme_core.domains.persona.kernel import STR, CommandContext, ValidationFailed, query, reject_unknown_keys, require_text, require_uuid, stable_id
from brandme_core.domains.persona.onboarding import GuestSection, register_guest_section

from .model import CATEGORIES
from .rooms import ROOMS

MAX_SAVED = 50


def _validate_saved(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, list) or len(payload) > MAX_SAVED:
        raise ValidationFailed(f"saved_products must be a list of at most {MAX_SAVED}")
    out, seen = [], set()
    for p in payload:
        if not isinstance(p, Mapping):
            raise ValidationFailed("each saved product must be an object")
        reject_unknown_keys(p, ("product_id", "variant_ref", "title", "category"), where="saved product")
        pid = require_uuid(p.get("product_id"), name="saved_products.product_id")
        cat = p.get("category")
        if cat not in CATEGORIES:
            raise ValidationFailed("saved product category is required", extra={"field": "saved_products.category"})
        v = require_text(p["variant_ref"], name="variant_ref", max_len=256) if p.get("variant_ref") is not None else None
        if (pid, v) in seen:
            continue
        seen.add((pid, v))
        out.append({"product_id": pid, "variant_ref": v, "title": require_text(p.get("title"), name="title", max_len=200), "category": cat})
    return out


def _apply_saved(txn, ctx: CommandContext, member_id: str, products: List[Dict[str, Any]]) -> Dict[str, Any]:
    from .service import ITEM_COLUMNS  # local import: service imports this module's registry indirectly

    added = skipped = 0
    for p in products:
        exists = query(
            txn,
            "SELECT 1 FROM WardrobeItems WHERE member_id=@m AND product_id=@p AND collection != 'archive' LIMIT 1",
            {"m": member_id, "p": p["product_id"]},
            {"m": STR, "p": STR},
        )
        if exists:
            skipped += 1
            continue
        item_id = stable_id("guest-saved", member_id, p["product_id"], p["variant_ref"] or "")
        row = {c: None for c in ITEM_COLUMNS}
        row.update(member_id=member_id, item_id=item_id, product_id=p["product_id"], variant_ref=p["variant_ref"], title=p["title"],
                   category=p["category"], collection="want", claim_level="self_reported", evidence_status="none",
                   acquisition_source="guest", acquisition_status="declared", care_state="clean", worn_count=0, version=1,
                   created_at=COMMIT_TIMESTAMP, updated_at=COMMIT_TIMESTAMP)
        txn.insert("WardrobeItems", columns=ITEM_COLUMNS, values=[[row[c] for c in ITEM_COLUMNS]])
        ctx.emit("wardrobe.item.created", "1", "wardrobe_item", item_id, 1,
                 {"member_id": member_id, "item_id": item_id, "collection": "want", "acquisition_source": "guest", "claim_level": "self_reported"},
                 "member_private")
        added += 1
    return {"saved_products_added": added, "already_saved": skipped}


def _validate_theme(payload: Any) -> str:
    if not isinstance(payload, Mapping) or set(payload) != {"room_template_id"} or payload["room_template_id"] not in ROOMS:
        raise ValidationFailed('closet_theme must be {"room_template_id": <room>}')
    return payload["room_template_id"]


def _apply_theme(txn, ctx: CommandContext, member_id: str, room_id: str) -> Dict[str, Any]:
    if query(txn, "SELECT 1 FROM ClosetLayouts WHERE member_id=@m", {"m": member_id}, {"m": STR}):
        return {"closet_theme": "kept_account_room"}
    layout_id = stable_id("closet-layout", member_id)
    txn.insert("ClosetLayouts", columns=("member_id", "layout_id", "room_template_id", "room_revision", "version", "updated_at"),
               values=[(member_id, layout_id, room_id, ROOMS[room_id].revision, 1, COMMIT_TIMESTAMP)])
    ctx.emit("closet.layout.changed", "1", "closet_layout", layout_id, 1,
             {"member_id": member_id, "layout_version": "1", "room_template_id": room_id}, "member_private")
    return {"closet_theme": room_id}


SAVED_PRODUCTS = GuestSection("saved_products", _validate_saved, _apply_saved)
CLOSET_THEME = GuestSection("closet_theme", _validate_theme, _apply_theme)
register_guest_section(SAVED_PRODUCTS)
register_guest_section(CLOSET_THEME)
