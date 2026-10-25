"""
Houses (brands) a member follows, and the catalog port that Flow and loyalty
standing read (Ultra plan 02, items 3-4).

A house is identified by ``house_ref``: the catalog brand name, lowercased,
with every run of characters outside ``[a-z0-9]`` replaced by ``-``, trimmed,
and capped at 120 characters. ``HOUSE_REF_SQL`` computes the same value in
Spanner, so references agree in both places.

No house registry exists yet. ``CatalogHouses`` derives houses from the
providers lane's ingested catalog (``CatalogSourceVariants``, V006). It only
reads, scans by brand without an index, and is an interim shim until that lane
publishes a catalog read API. A piece is a catalog variant, identified by its
``variant_id``; its freshness is ``first_seen_at``, the time the catalog first
saw it.

``share_standing`` is the member's opt-in for a house to see their standing
tier. It is off by default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, KeySet

from brandme_core.domains.persona.kernel import (
    STR,
    STR_ARRAY,
    INT,
    TS,
    CommandContext,
    NotFound,
    Principal,
    ValidationFailed,
    command,
    guard_write,
    iso,
    member_active,
    query,
    reject_unknown_keys,
    require_scope,
    run_read,
)

HOUSE_REF = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,118}[a-z0-9])?$")
HOUSE_REF_SQL = "SUBSTR(TRIM(REGEXP_REPLACE(LOWER(brand), r'[^a-z0-9]+', '-'), '-'), 1, 120)"
MAX_FOLLOWS = 200


def house_ref_of(brand: Optional[str]) -> Optional[str]:
    if not brand:
        return None
    ref = re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-")[:120]
    return ref or None


def require_house_ref(value: Any) -> str:
    if not isinstance(value, str) or not HOUSE_REF.match(value):
        raise NotFound("house not found")
    return value


@dataclass(frozen=True)
class HouseItem:
    product_id: str
    house_ref: str
    house_name: str
    title: str
    category: Optional[str]
    published_at: datetime
    price_minor: Optional[int]
    currency: Optional[str]
    available: bool


class HouseCatalog(Protocol):
    def newest(self, snap: Any, house_refs: Sequence[str], *, before: Optional[Tuple[datetime, str]], limit: int) -> List[HouseItem]: ...
    def houses_of(self, snap: Any, product_ids: Sequence[str]) -> Dict[str, str]: ...
    def house_name(self, snap: Any, house_ref: str) -> Optional[str]: ...


class CatalogHouses:
    """``HouseCatalog`` over ``CatalogSourceVariants`` (providers lane, read-only)."""

    _COLS = "variant_id, brand, title, category, first_seen_at, observed_price_minor, observed_price_currency, availability"

    def newest(self, snap, house_refs, *, before=None, limit=24):
        if not house_refs:
            return []
        params: Dict[str, Any] = {"h": list(house_refs), "l": limit}
        types: Dict[str, Any] = {"h": STR_ARRAY, "l": INT}
        page = ""
        if before is not None:
            page = "AND (first_seen_at < @t OR (first_seen_at = @t AND variant_id < @v)) "
            params.update(t=before[0], v=before[1])
            types.update(t=TS, v=STR)
        rows = query(snap, f"SELECT {self._COLS} FROM CatalogSourceVariants WHERE NOT tombstoned AND brand IS NOT NULL "
                           f"AND availability != 'discontinued' AND {HOUSE_REF_SQL} IN UNNEST(@h) {page}"
                           "ORDER BY first_seen_at DESC, variant_id DESC LIMIT @l", params, types)
        return [HouseItem(r[0], house_ref_of(r[1]) or "", r[1], r[2], r[3], r[4], r[5], r[6], r[7] == "in_stock") for r in rows]

    def houses_of(self, snap, product_ids):
        if not product_ids:
            return {}
        rows = query(snap, f"SELECT variant_id, {HOUSE_REF_SQL} FROM CatalogSourceVariants WHERE variant_id IN UNNEST(@p) AND brand IS NOT NULL",
                     {"p": list(product_ids)}, {"p": STR_ARRAY})
        return {r[0]: r[1] for r in rows if r[1]}

    def house_name(self, snap, house_ref):
        rows = query(snap, f"SELECT brand FROM CatalogSourceVariants WHERE brand IS NOT NULL AND {HOUSE_REF_SQL} = @h LIMIT 1",
                     {"h": house_ref}, {"h": STR})
        return rows[0][0] if rows else None


def catalog_variant_lookup(database) -> Callable[[str], Optional[Dict[str, Any]]]:
    """The wardrobe order reducer's ``CatalogLookup`` over the same catalog. A
    catalog piece is identified by its ``variant_id``, so order-acquired items
    carry it as ``product_id`` and count toward Flow and standing."""

    def lookup(variant_id: str) -> Optional[Dict[str, Any]]:
        if not variant_id:
            return None
        rows = run_read(database, lambda s: query(s, "SELECT variant_id, title, category FROM CatalogSourceVariants WHERE variant_id=@v",
                                                  {"v": variant_id}, {"v": STR}))
        return {"product_id": rows[0][0], "title": rows[0][1], "category": rows[0][2]} if rows else None

    return lookup


def catalog_piece_exists(txn, variant_id: str) -> bool:
    """``DecisionService`` catalog check: a live catalog piece (not tombstoned or discontinued)."""
    return bool(query(txn, "SELECT 1 FROM CatalogSourceVariants@{FORCE_INDEX=CatalogSourceVariantsByVariantId} WHERE variant_id=@v "
                           "AND NOT tombstoned AND availability != 'discontinued'", {"v": variant_id}, {"v": STR}))


def member_houses(snap, member_id: str, catalog: HouseCatalog) -> Dict[str, str]:
    """house_ref → how the member is connected: 'followed' wins over 'closet'
    (houses of pieces they own, verified or declared)."""
    out: Dict[str, str] = {}
    owned = [r[0] for r in query(snap, "SELECT product_id FROM WardrobeItems WHERE member_id=@m AND collection='owned' AND product_id IS NOT NULL "
                                       "LIMIT 500", {"m": member_id}, {"m": STR})]
    for ref in catalog.houses_of(snap, owned).values():
        out[ref] = "closet"
    for (ref,) in query(snap, "SELECT house_ref FROM MemberHouses WHERE member_id=@m", {"m": member_id}, {"m": STR}):
        out[ref] = "followed"
    return out


class HouseService:
    def __init__(self, database, *, catalog: HouseCatalog):
        self.db = database
        self.catalog = catalog

    def list(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "social:read")
        m = principal.member_id

        def read(s):
            follows = {r[0]: {"share_standing": r[1], "followed_at": iso(r[2])} for r in query(
                s, "SELECT house_ref, share_standing, followed_at FROM MemberHouses WHERE member_id=@m ORDER BY house_ref", {"m": m}, {"m": STR})}
            items = []
            for ref, via in sorted(member_houses(s, m, self.catalog).items()):
                f = follows.get(ref)
                items.append({"house_ref": ref, "name": self.catalog.house_name(s, ref), "via": via, "followed": f is not None,
                              "share_standing": bool(f and f["share_standing"]), "followed_at": f["followed_at"] if f else None})
            return {"items": items}

        return run_read(self.db, read)

    def follow(self, principal: Principal, house_ref: Any, body: Any) -> Dict[str, Any]:
        """Follow a house, or change whether it may see your standing tier."""
        require_scope(principal, "social:write")
        ref = require_house_ref(house_ref)
        body = body if body is not None else {}
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("share_standing",), where="house")
        share = body.get("share_standing", False)
        if not isinstance(share, bool):
            raise ValidationFailed("share_standing must be true or false", extra={"field": "share_standing"})
        m = principal.member_id

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, m):
                raise NotFound("member not found")
            name = self.catalog.house_name(txn, ref)
            if name is None:
                raise NotFound("house not found")
            guard_write(txn, m, "social.houses")
            cur = query(txn, "SELECT version FROM MemberHouses WHERE member_id=@m AND house_ref=@h", {"m": m, "h": ref}, {"m": STR, "h": STR})
            if cur:
                txn.update("MemberHouses", columns=("member_id", "house_ref", "share_standing", "updated_at", "version"),
                           values=[(m, ref, share, COMMIT_TIMESTAMP, cur[0][0] + 1)])
            else:
                n = query(txn, "SELECT COUNT(*) FROM MemberHouses WHERE member_id=@m", {"m": m}, {"m": STR})[0][0]
                if n >= MAX_FOLLOWS:
                    raise ValidationFailed(f"you can follow at most {MAX_FOLLOWS} houses", extra={"limit": "follows"})
                txn.insert("MemberHouses", columns=("member_id", "house_ref", "share_standing", "followed_at", "updated_at", "version"),
                           values=[(m, ref, share, COMMIT_TIMESTAMP, COMMIT_TIMESTAMP, 1)])
            return {"house_ref": ref, "name": name, "followed": True, "share_standing": share}

        return command(self.db, principal, tx)

    def unfollow(self, principal: Principal, house_ref: Any) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        ref = require_house_ref(house_ref)
        m = principal.member_id

        def tx(txn, ctx: CommandContext):
            guard_write(txn, m, "social.houses")
            txn.delete("MemberHouses", keyset=KeySet(keys=[[m, ref]]))
            return {"house_ref": ref, "followed": False}

        return command(self.db, principal, tx)
