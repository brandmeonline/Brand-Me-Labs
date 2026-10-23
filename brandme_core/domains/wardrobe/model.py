"""
Wardrobe intake and item rules: pure functions.

Ch.01 §5: item status (collection) and trust status (claim level) are
independent. A catalog save is "want" and never ownership; an owned item may
be self-declared; a receipt line with several units becomes several items;
two unique tag serials are never merged; the system never invents a size or a
GTIN. Collection moves the member may make are limited; "on the way" and
"digital" come only from provider/rights observations.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from brandme_core.domains.persona.kernel import (
    ValidationFailed,
    reject_non_finite,
    reject_unknown_keys,
    require_strict_int,
    require_text,
    require_uuid,
)

CATEGORIES = ("top", "bottom", "dress", "outerwear", "shoes", "accessory")
COLLECTIONS = ("owned", "want", "on_the_way", "digital", "archive")
CLAIM_LEVELS = ("self_reported", "receipt_backed", "tag_verified", "issuer_attested")
SOURCES = ("manual", "photo", "catalog", "receipt", "qr", "agent", "order", "guest")
CARE_STATES = ("clean", "needs_care", "at_cleaner", "in_repair")
CONDITIONS = ("new", "good", "worn", "needs_repair")
COLOR_FAMILIES = ("neutral", "color")

# Collections a member may choose at intake / by PATCH. on_the_way/digital are
# observation-driven; archive has its own reversible command.
MEMBER_COLLECTIONS = ("owned", "want")

INTAKE_KEYS = (
    "source",
    "title",
    "category",
    "collection",
    "product_id",
    "variant_ref",
    "size_label",
    "color_family",
    "colors",
    "materials",
    "condition",
    "care_state",
    "user_notes",
    "price",
    "receipt",
    "tag_serial",
    "media_ref",
    "placement",
)
PATCH_KEYS = (
    "title",
    "collection",
    "size_label",
    "color_family",
    "colors",
    "materials",
    "condition",
    "care_state",
    "care_notes",
    "user_notes",
)
# Facts with another authority: member edits are refused (BM-PER-011 analogue).
FACTUAL_FIELDS = (
    "claim_level",
    "evidence_status",
    "asset_instance_id",
    "product_id",
    "variant_ref",
    "acquisition_source",
    "acquisition_status",
    "receipt_line_ref",
    "tag_serial",
    "price",
    "worn_count",
    "member_id",
    "owner_id",
)
MAX_RECEIPT_UNITS = 20


def _str_list(v: Any, name: str, *, max_items: int, max_len: int) -> List[str]:
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > max_items:
        raise ValidationFailed(f"{name} must be a list of at most {max_items}", extra={"field": name})
    out: List[str] = []
    for s in v:
        t = require_text(s, name=name, max_len=max_len)
        if t not in out:
            out.append(t)
    return out


def tag_serial_hash(serial: str) -> str:
    """One-way, normalized: the raw serial is not stored."""
    norm = unicodedata.normalize("NFKC", serial).strip().upper()
    norm = re.sub(r"\s+", "", norm)
    if not (4 <= len(norm) <= 128):
        raise ValidationFailed("tag_serial must be 4-128 characters", extra={"field": "tag_serial"})
    return hashlib.sha256(b"brandme:tag-serial:" + norm.encode()).hexdigest()


@dataclass
class Intake:
    source: str
    title: str
    category: str
    collection: str
    product_id: Optional[str]
    variant_ref: Optional[str]
    size_label: Optional[str]
    color_family: Optional[str]
    colors: List[str]
    materials: List[str]
    condition: Optional[str]
    care_state: str
    user_notes: Optional[str]
    price_minor: Optional[int]
    price_currency: Optional[str]
    price_is_estimate: Optional[bool]
    receipt_ref: Optional[str]
    receipt_line_ref: Optional[str]
    units: int
    tag_serial_hash: Optional[str]
    media_ref: Optional[str]
    placement: Optional[Dict[str, Any]]
    claim_level: str = "self_reported"
    evidence_status: str = "none"


def parse_intake(body: Any) -> Intake:
    if not isinstance(body, Mapping):
        raise ValidationFailed("body must be an object")
    reject_non_finite(body)
    factual = sorted(set(body) & set(FACTUAL_FIELDS) - {"product_id", "variant_ref", "price", "tag_serial"})
    if factual:
        raise ValidationFailed(f"these fields are set by their authority, not by intake: {', '.join(factual)}", extra={"rejected_fields": factual})
    reject_unknown_keys(body, INTAKE_KEYS, where="wardrobe intake")
    source = body.get("source")
    if source not in ("manual", "photo", "catalog", "receipt", "qr"):
        raise ValidationFailed("source must be manual, photo, catalog, receipt or qr", extra={"field": "source"})
    title = require_text(body.get("title"), name="title", max_len=200)
    category = body.get("category")
    if category not in CATEGORIES:
        raise ValidationFailed(f"category must be one of {CATEGORIES}", extra={"field": "category"})
    product_id = require_uuid(body["product_id"], name="product_id") if body.get("product_id") is not None else None
    variant_ref = require_text(body["variant_ref"], name="variant_ref", max_len=256) if body.get("variant_ref") is not None else None
    if variant_ref and not product_id:
        raise ValidationFailed("variant_ref requires product_id", extra={"field": "variant_ref"})
    if source == "catalog" and not product_id:
        raise ValidationFailed("a catalog save needs product_id", extra={"field": "product_id"})
    # Default collection: a catalog save is aspiration, never ownership (BM-WARD-002).
    collection = body.get("collection")
    if collection is None:
        collection = "want" if source == "catalog" else "owned"
    if collection not in MEMBER_COLLECTIONS:
        raise ValidationFailed("collection must be owned or want at intake", extra={"field": "collection"})
    color_family = body.get("color_family")
    if color_family is not None and color_family not in COLOR_FAMILIES:
        raise ValidationFailed("color_family must be neutral or color", extra={"field": "color_family"})
    condition = body.get("condition")
    if condition is not None and condition not in CONDITIONS:
        raise ValidationFailed(f"condition must be one of {CONDITIONS}", extra={"field": "condition"})
    care_state = body.get("care_state", "clean")
    if care_state not in CARE_STATES:
        raise ValidationFailed(f"care_state must be one of {CARE_STATES}", extra={"field": "care_state"})
    size_label = require_text(body["size_label"], name="size_label", max_len=40) if body.get("size_label") is not None else None
    notes = require_text(body["user_notes"], name="user_notes", max_len=2000) if body.get("user_notes") is not None else None
    price_minor = price_currency = None
    price_is_estimate = None
    if body.get("price") is not None:
        price = body["price"]
        if not isinstance(price, Mapping):
            raise ValidationFailed("price must be an object")
        reject_unknown_keys(price, ("amount_minor", "currency", "is_estimate"), where="price")
        raw = price.get("amount_minor")
        if not isinstance(raw, str) or not raw.isdigit() or len(raw) > 15 or (len(raw) > 1 and raw[0] == "0"):
            raise ValidationFailed("price.amount_minor must be a decimal string", extra={"field": "price.amount_minor"})
        cur = price.get("currency")
        if not isinstance(cur, str) or len(cur) != 3 or not cur.isalpha() or not cur.isupper():
            raise ValidationFailed("price.currency must be ISO 4217", extra={"field": "price.currency"})
        est = price.get("is_estimate", True)
        if not isinstance(est, bool):
            raise ValidationFailed("price.is_estimate must be a boolean")
        price_minor, price_currency, price_is_estimate = int(raw), cur, est
    receipt_ref = receipt_line_ref = None
    units = 1
    evidence_status = "none"
    if source == "receipt":
        r = body.get("receipt")
        if not isinstance(r, Mapping):
            raise ValidationFailed("a receipt intake needs receipt {receipt_ref, line_ref, units}", extra={"field": "receipt"})
        reject_unknown_keys(r, ("receipt_ref", "line_ref", "units"), where="receipt")
        receipt_ref = require_text(r.get("receipt_ref"), name="receipt.receipt_ref", max_len=200)
        receipt_line_ref = f"{receipt_ref}#{require_text(r.get('line_ref'), name='receipt.line_ref', max_len=50)}"
        units = require_strict_int(r.get("units", 1), name="receipt.units", lo=1, hi=MAX_RECEIPT_UNITS)
        if collection != "owned":
            raise ValidationFailed("receipt-derived items are owned", extra={"field": "collection"})
        evidence_status = "receipt_pending_review"
    elif body.get("receipt") is not None:
        raise ValidationFailed("receipt is only valid with source=receipt", extra={"field": "receipt"})
    serial_hash = tag_serial_hash(body["tag_serial"]) if body.get("tag_serial") is not None else None
    if serial_hash and units != 1:
        raise ValidationFailed("a tag serial identifies one physical unit", extra={"field": "tag_serial"})
    media_ref = require_text(body["media_ref"], name="media_ref", max_len=256) if body.get("media_ref") is not None else None
    placement = body.get("placement")
    if placement is not None and not isinstance(placement, Mapping):
        raise ValidationFailed("placement must be an object")
    if placement is not None and (units != 1 or collection != "owned"):
        raise ValidationFailed("only a single owned item can be placed at intake", extra={"field": "placement"})
    return Intake(
        source=source,
        title=title,
        category=category,
        collection=collection,
        product_id=product_id,
        variant_ref=variant_ref,
        size_label=size_label,
        color_family=color_family,
        colors=_str_list(body.get("colors"), "colors", max_items=8, max_len=32),
        materials=_str_list(body.get("materials"), "materials", max_items=12, max_len=60),
        condition=condition,
        care_state=care_state,
        user_notes=notes,
        price_minor=price_minor,
        price_currency=price_currency,
        price_is_estimate=price_is_estimate,
        receipt_ref=receipt_ref,
        receipt_line_ref=receipt_line_ref,
        units=units,
        tag_serial_hash=serial_hash,
        media_ref=media_ref,
        placement=dict(placement) if placement is not None else None,
        evidence_status=evidence_status,
    )


@dataclass(frozen=True)
class ExistingItem:
    item_id: str
    product_id: Optional[str]
    variant_ref: Optional[str]
    receipt_line_ref: Optional[str]
    unit_index: Optional[int]
    tag_serial_hash: Optional[str]
    collection: str
    duplicate_of: Optional[str]


@dataclass(frozen=True)
class DuplicateCandidate:
    item_id: str
    reason: str          # same_variant | same_receipt_line | same_tag_serial
    strength: str        # suggestion | certain
    mergeable: bool


def duplicate_candidates(new: Intake, existing: Sequence[ExistingItem]) -> List[DuplicateCandidate]:
    """Suggestions only; the member decides (BM-WARD-004). Never auto-merge."""
    out: List[DuplicateCandidate] = []
    for e in sorted(existing, key=lambda e: e.item_id):
        if e.duplicate_of or e.collection == "archive":
            continue
        if new.tag_serial_hash and e.tag_serial_hash == new.tag_serial_hash:
            out.append(DuplicateCandidate(e.item_id, "same_tag_serial", "certain", True))
        elif new.receipt_line_ref and e.receipt_line_ref == new.receipt_line_ref:
            out.append(DuplicateCandidate(e.item_id, "same_receipt_line", "suggestion", True))
        elif new.product_id and new.variant_ref and e.product_id == new.product_id and e.variant_ref == new.variant_ref:
            # Two physical units of the same variant are common; distinct serials block merging.
            distinct = bool(new.tag_serial_hash and e.tag_serial_hash and new.tag_serial_hash != e.tag_serial_hash)
            out.append(DuplicateCandidate(e.item_id, "same_variant", "suggestion", not distinct))
    return out


def can_merge(a: ExistingItem, b: ExistingItem) -> Tuple[bool, str]:
    if a.item_id == b.item_id:
        return False, "same_item"
    if a.tag_serial_hash and b.tag_serial_hash and a.tag_serial_hash != b.tag_serial_hash:
        return False, "distinct_physical_instances"
    if a.receipt_line_ref and b.receipt_line_ref and a.receipt_line_ref == b.receipt_line_ref and a.unit_index != b.unit_index:
        return False, "distinct_receipt_units"
    return True, "ok"


# ---------------------------------------------------------------- orders


@dataclass(frozen=True)
class UnitState:
    unit_index: int
    collection: str
    acquisition_status: str  # ordered | delivered | returned | cancelled


def order_unit_states(ordered: int, delivered: int, returned: int, order_cancelled: bool) -> List[UnitState]:
    """Deterministic per-unit state from provider-observed line counts.

    Returned units are taken from the delivered ones; undelivered units are
    "on the way" unless the order is cancelled.
    """
    for name, v in (("ordered", ordered), ("delivered", delivered), ("returned", returned)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0 or v > 99:
            raise ValidationFailed(f"order line {name} must be 0..99")
    delivered = min(delivered, ordered)
    returned = min(returned, delivered)
    out: List[UnitState] = []
    for i in range(ordered):
        if i < returned:
            out.append(UnitState(i, "archive", "returned"))
        elif i < delivered:
            out.append(UnitState(i, "owned", "delivered"))
        elif order_cancelled:
            out.append(UnitState(i, "archive", "cancelled"))
        else:
            out.append(UnitState(i, "on_the_way", "ordered"))
    return out


def item_dto(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Wire form. The core fields validate against contracts #WardrobeItem."""
    return {
        "id": row["item_id"],
        "member_id": row["member_id"],
        "title": row["title"],
        "collection": row["collection"],
        "product_id": row.get("product_id"),
        "asset_instance_id": row.get("asset_instance_id"),
        "claim_level": row["claim_level"],
        "version": str(row["version"]),
    }
