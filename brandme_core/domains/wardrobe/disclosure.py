"""
Disclosure facets (Ultra plan 03, item 12): the locked stranger-scan default,
enforced where the lane's API builds what another member sees of a piece.

A piece has seven facets:

* ``identity``: what it is (title, category, colours);
* ``house``: whose design it is (the catalog house);
* ``maker``: what it is made of (materials);
* ``story``: the owner's showcase note and how often it is worn;
* ``price``: what was paid;
* ``ownership``: when it entered the closet and whether ownership is verified;
* ``logistics``: where it is in its care cycle (clean, at the cleaner, in repair).

Strangers see at most identity, house, maker and story. Price, ownership and
logistics stay hidden unless the owner unfolds them (closet detail ``full``),
and an unfold reaches friends only.

Every ``WardrobeItems`` column is classified here: a facet, ``NEVER`` (never
shown to anyone else at any level), or ``META`` (bookkeeping that is not piece
data). Views are built only from :data:`PROJECTION`, so an unclassified column
cannot reach a response, and ``tests/test_wardrobe_disclosure.py`` fails until a
new column is classified.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, FrozenSet, Mapping, Optional, Tuple

FACETS = ("identity", "house", "maker", "story", "price", "ownership", "logistics")
STRANGER_FACETS: FrozenSet[str] = frozenset({"identity", "house", "maker", "story"})  # locked default
UNFOLD_FACETS: FrozenSet[str] = frozenset({"price", "ownership", "logistics"})
NEVER = "never"
META = "meta"

# Every WardrobeItems column, by facet. ``product_id`` is house: only the house it resolves to is shown.
COLUMNS: Dict[str, str] = {
    "item_id": META, "member_id": "ownership",
    "title": "identity", "category": "identity", "color_family": "identity", "colors": "identity",
    "product_id": "house",
    "materials": "maker",
    "showcase_note": "story", "worn_count": "story",
    "price_minor": "price", "price_currency": "price", "price_is_estimate": "price",
    "claim_level": "ownership", "evidence_status": "ownership", "acquisition_source": "ownership", "created_at": "ownership",
    "care_state": "logistics", "acquisition_status": "logistics", "last_worn_at": "logistics",
    "variant_ref": NEVER, "asset_instance_id": NEVER, "source_ref": NEVER, "receipt_line_ref": NEVER, "unit_index": NEVER,
    "tag_serial_hash": NEVER, "size_label": NEVER, "item_condition": NEVER, "care_notes": NEVER, "user_notes": NEVER,
    "duplicate_of": NEVER, "pre_archive_collection": NEVER,
    "collection": META, "version": META, "updated_at": META, "visibility": META, "visible_detail": META,
}

Row = Mapping[str, Any]
# (output key, facet, columns read, value). Nothing else is ever emitted about a piece.
PROJECTION: Tuple[Tuple[str, str, Tuple[str, ...], Callable[[Row, Mapping[str, str]], Any]], ...] = (
    ("title", "identity", ("title",), lambda r, h: r["title"]),
    ("category", "identity", ("category",), lambda r, h: r["category"]),
    ("color_family", "identity", ("color_family",), lambda r, h: r["color_family"]),
    ("colors", "identity", ("colors",), lambda r, h: list(r["colors"] or [])),
    ("house_ref", "house", ("product_id",), lambda r, h: h.get(r["product_id"]) if r["product_id"] else None),
    ("materials", "maker", ("materials",), lambda r, h: list(r["materials"] or [])),
    ("showcase_note", "story", ("showcase_note",), lambda r, h: r["showcase_note"]),
    ("worn_count", "story", ("worn_count",), lambda r, h: r["worn_count"]),
    ("price", "price", ("price_minor", "price_currency", "price_is_estimate"),
     lambda r, h: None if r["price_minor"] is None else {"minor": r["price_minor"], "currency": r["price_currency"],
                                                         "estimate": bool(r["price_is_estimate"])}),
    ("in_closet_since", "ownership", ("created_at",), lambda r, h: r["created_at"].year),
    ("verified", "ownership", ("claim_level",), lambda r, h: r["claim_level"] != "self_reported"),
    ("care_state", "logistics", ("care_state",), lambda r, h: r["care_state"]),
)
READ_COLUMNS = ("item_id", "visible_detail", *sorted({c for _, _, cols, _ in PROJECTION for c in cols}))

# What each owner-chosen closet detail level shows. ``full`` is the owner's unfold.
LEVELS: Dict[str, FrozenSet[str]] = {
    "piece": frozenset({"identity", "house", "maker"}),
    "story": frozenset({"identity", "house", "maker", "story"}),
    "full": frozenset(FACETS),
}


def facets_for(detail: Optional[str], rel: Optional[str]) -> FrozenSet[str]:
    """Facets ``rel`` sees of a piece shown at ``detail``. Only friends (and the owner) ever get an unfold."""
    if rel is None or detail not in LEVELS:
        return frozenset()
    shown = LEVELS[detail]
    return shown if rel in ("self", "friends") else shown & STRANGER_FACETS


def keys_of(facets: FrozenSet[str]) -> FrozenSet[str]:
    return frozenset(k for k, f, _, _ in PROJECTION if f in facets)


def disclose(row: Row, facets: FrozenSet[str], houses: Mapping[str, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"item_id": row["item_id"]}
    for key, facet, _, value in PROJECTION:
        if facet in facets:
            out[key] = value(row, houses)
    return out
