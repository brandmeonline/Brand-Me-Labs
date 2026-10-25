"""
Wardrobe application service (W04): items, intake, duplicates, care, closet
layout/placement and provider-order reduction. Spanner-backed; every command
commits rows + outbox events in one transaction via the foundation framework.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, KeySet

from brandme_core.domains.persona.kernel import (
    INT,
    STR,
    TS,
    Clock,
    CommandContext,
    DetailedInvalidTransition,
    DetailedVersionConflict,
    NotFound,
    Principal,
    SystemClock,
    ValidationFailed,
    command,
    decode_cursor,
    encode_cursor,
    idempotent_command,
    iso,
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
    service_principal,
    stable_id,
)
from brandme_core.domains.persona.privacy_guard import ProcessingFrozen, assert_processing_allowed
from brandme_core.domains.persona.recommender import WardrobeRef
from brandme_core.events import EventEnvelope, first_delivery

from . import events as _events  # noqa: F401  (event registration)
from .model import (
    CARE_STATES,
    CATEGORIES,
    COLOR_FAMILIES,
    CONDITIONS,
    FACTUAL_FIELDS,
    MEMBER_COLLECTIONS,
    PATCH_KEYS,
    ExistingItem,
    Intake,
    can_merge,
    duplicate_candidates,
    item_dto,
    order_unit_states,
    parse_intake,
)
from .placement import Placement, check_unique_slots, parse_placement, placement_dto, remap_theme
from .rooms import DEFAULT_ROOM, ROOMS

ITEM_COLUMNS = (
    "member_id", "item_id", "product_id", "variant_ref", "asset_instance_id", "title", "category", "collection",
    "claim_level", "evidence_status", "acquisition_source", "acquisition_status", "source_ref", "receipt_line_ref",
    "unit_index", "tag_serial_hash", "color_family", "colors", "materials", "size_label", "item_condition", "care_state",
    "care_notes", "user_notes", "worn_count", "last_worn_at", "price_minor", "price_currency", "price_is_estimate",
    "duplicate_of", "pre_archive_collection", "version", "created_at", "updated_at",
)
PLACEMENT_COLUMNS = (
    "member_id", "item_id", "layout_id", "room_template_id", "semantic_group", "slot_id", "pos_x", "pos_y", "pos_z",
    "rot_x", "rot_y", "rot_z", "rot_w", "uniform_scale", "asset_revision", "version", "updated_at",
)
PLACEABLE_COLLECTIONS = ("owned", "digital")
MAX_BATCH = 50
ORDER_CONSUMER = "wardrobe.order-reducer"

CatalogLookup = Callable[[str], Optional[Dict[str, Any]]]  # variant_id -> {product_id,title,category}


def _row(cols: Sequence[str], r: Sequence[Any]) -> Dict[str, Any]:
    return dict(zip(cols, r))


class WardrobeService:
    def __init__(self, database, *, clock: Clock = None, catalog_lookup: Optional[CatalogLookup] = None):
        self.db = database
        self.clock = clock or SystemClock()
        self.catalog_lookup = catalog_lookup or (lambda _v: None)

    # ----------------------------------------------------------------- reads

    def _item(self, txn, member_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        rows = query(
            txn,
            f"SELECT {', '.join(ITEM_COLUMNS)} FROM WardrobeItems WHERE member_id=@m AND item_id=@i",
            {"m": member_id, "i": item_id},
            {"m": STR, "i": STR},
        )
        return _row(ITEM_COLUMNS, rows[0]) if rows else None

    def _require_item(self, txn, member_id: str, item_id: str) -> Dict[str, Any]:
        row = self._item(txn, member_id, item_id)
        if row is None:
            raise NotFound("item not found")
        return row

    def _writable(self, txn, member_id: str) -> None:
        if not member_active(txn, member_id):
            raise NotFound("member not found")
        try:
            assert_processing_allowed(txn, member_id, "wardrobe.items", self.clock.now())
        except ProcessingFrozen as exc:
            raise DetailedInvalidTransition(str(exc), code="processing_frozen") from None

    def full_item(self, row: Mapping[str, Any], placement: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        out = item_dto(row)
        out.update(
            {
                "category": row["category"],
                "variant_ref": row["variant_ref"],
                "evidence_status": row["evidence_status"],
                "acquisition_source": row["acquisition_source"],
                "acquisition_status": row["acquisition_status"],
                "receipt_line_ref": row["receipt_line_ref"],
                "unit_index": row["unit_index"],
                "has_tag_serial": row["tag_serial_hash"] is not None,
                "color_family": row["color_family"],
                "colors": list(row["colors"] or []),
                "materials": list(row["materials"] or []),
                "size_label": row["size_label"],
                "condition": row["item_condition"],
                "care_state": row["care_state"],
                "care_notes": row["care_notes"],
                "user_notes": row["user_notes"],
                "worn_count": row["worn_count"],
                "last_worn_at": iso(row["last_worn_at"]),
                "price": None
                if row["price_minor"] is None
                else {"amount_minor": str(row["price_minor"]), "currency": row["price_currency"], "is_estimate": bool(row["price_is_estimate"])},
                "cost_per_wear": self._cost_per_wear(row),
                "duplicate_of": row["duplicate_of"],
                "created_at": iso(row["created_at"]),
                "updated_at": iso(row["updated_at"]),
                "placement": placement,
            }
        )
        return out

    @staticmethod
    def _cost_per_wear(row: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        # Only when price and wear count are known; labelled as an estimate when the price is.
        if row["price_minor"] is None or not row["worn_count"]:
            return None
        return {
            "amount_minor": str(row["price_minor"] // row["worn_count"]),
            "currency": row["price_currency"],
            "is_estimate": bool(row["price_is_estimate"]),
            "basis": f"{row['worn_count']} recorded wears",
        }

    def get_item(self, principal: Principal, item_id: str) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:read")
        item_id = require_uuid(item_id, name="item_id")

        def read(s):
            row = self._require_item(s, principal.member_id, item_id)
            return row, self._placement(s, principal.member_id, item_id)

        row, pl = run_read(self.db, read)
        return self.full_item(row, pl)

    def list_items(
        self,
        principal: Principal,
        *,
        collection: Optional[str] = None,
        category: Optional[str] = None,
        q: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 24,
    ) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:read")
        limit = require_strict_int(limit, name="limit", lo=1, hi=100)
        sql = f"SELECT {', '.join(ITEM_COLUMNS)} FROM WardrobeItems WHERE member_id=@m "
        params: Dict[str, Any] = {"m": principal.member_id, "n": limit + 1}
        types: Dict[str, Any] = {"m": STR, "n": INT}
        if collection is not None:
            if collection not in ("owned", "want", "on_the_way", "digital", "archive"):
                raise ValidationFailed("unknown collection", extra={"field": "collection"})
            sql += "AND collection=@c "
            params["c"], types["c"] = collection, STR
        if category is not None:
            if category not in CATEGORIES:
                raise ValidationFailed("unknown category", extra={"field": "category"})
            sql += "AND category=@cat "
            params["cat"], types["cat"] = category, STR
        if q is not None:
            needle = require_text(q, name="q", max_len=80).lower()
            sql += "AND STRPOS(LOWER(title), @q) > 0 "
            params["q"], types["q"] = needle, STR
        if cursor:
            t, i = decode_cursor(cursor, kinds=("ts", "id"))
            sql += "AND (updated_at < @t OR (updated_at = @t AND item_id > @i)) "
            params.update(t=t, i=i)
            types.update(t=TS, i=STR)
        sql += "ORDER BY updated_at DESC, item_id LIMIT @n"
        rows = [_row(ITEM_COLUMNS, r) for r in run_read(self.db, lambda s: query(s, sql, params, types))]
        page = rows[:limit]
        nxt = encode_cursor(page[-1]["updated_at"], page[-1]["item_id"]) if len(rows) > limit else None
        return {"items": [self.full_item(r) for r in page], "next_cursor": nxt}

    def wardrobe_refs(self, txn, member_id: str) -> List[WardrobeRef]:
        """Persona recommender input: owned, categorized, colour-known items only."""
        return [
            WardrobeRef(r[0], r[1], r[2], r[3])
            for r in query(
                txn,
                "SELECT item_id, title, category, color_family FROM WardrobeItems "
                "WHERE member_id=@m AND collection='owned' AND category IS NOT NULL AND color_family IS NOT NULL "
                "AND duplicate_of IS NULL ORDER BY item_id LIMIT 500",
                {"m": member_id},
                {"m": STR},
            )
        ]

    # ---------------------------------------------------------- intake

    def _existing_for_duplicates(self, txn, member_id: str, intake: Intake) -> List[ExistingItem]:
        clauses, params, types = [], {"m": member_id}, {"m": STR}
        if intake.product_id and intake.variant_ref:
            clauses.append("(product_id=@p AND variant_ref=@v)")
            params.update(p=intake.product_id, v=intake.variant_ref)
            types.update(p=STR, v=STR)
        if intake.receipt_line_ref:
            clauses.append("receipt_line_ref=@r")
            params["r"], types["r"] = intake.receipt_line_ref, STR
        if intake.tag_serial_hash:
            clauses.append("tag_serial_hash=@t")
            params["t"], types["t"] = intake.tag_serial_hash, STR
        if not clauses:
            return []
        rows = query(
            txn,
            "SELECT item_id, product_id, variant_ref, receipt_line_ref, unit_index, tag_serial_hash, collection, duplicate_of "
            f"FROM WardrobeItems WHERE member_id=@m AND ({' OR '.join(clauses)}) LIMIT 50",
            params,
            types,
        )
        return [ExistingItem(*r) for r in rows]

    def _insert_item(self, txn, member_id: str, item_id: str, values: Mapping[str, Any]) -> Dict[str, Any]:
        row = {c: None for c in ITEM_COLUMNS}
        row.update(
            member_id=member_id,
            item_id=item_id,
            worn_count=0,
            care_state="clean",
            evidence_status="none",
            acquisition_status="declared",
            version=1,
            created_at=COMMIT_TIMESTAMP,
            updated_at=COMMIT_TIMESTAMP,
        )
        row.update(values)
        txn.insert("WardrobeItems", columns=ITEM_COLUMNS, values=[[row[c] for c in ITEM_COLUMNS]])
        return row

    def create_items(self, principal: Principal, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        """Idempotent intake (BM-WARD-001/002/003). Item(s) and an optional placement
        commit in one transaction; a retried request returns the original result."""
        require_scope(principal, "wardrobe:write")
        intake = parse_intake(body)
        member_id = principal.member_id

        def txn_fn(txn, ctx: CommandContext) -> Dict[str, Any]:
            now = self.clock.now()
            self._writable(txn, member_id)
            if intake.tag_serial_hash and query(
                txn,
                "SELECT item_id FROM WardrobeItems WHERE member_id=@m AND tag_serial_hash=@t",
                {"m": member_id, "t": intake.tag_serial_hash},
                {"m": STR, "t": STR},
            ):
                # Same physical unit already in this closet: never a second identity.
                existing = query(
                    txn,
                    "SELECT item_id FROM WardrobeItems WHERE member_id=@m AND tag_serial_hash=@t",
                    {"m": member_id, "t": intake.tag_serial_hash},
                    {"m": STR, "t": STR},
                )[0][0]
                raise DetailedInvalidTransition(
                    "this tagged item is already in your closet", code="duplicate_physical_instance", extra={"existing_item_id": existing}
                )
            candidates = duplicate_candidates(intake, self._existing_for_duplicates(txn, member_id, intake))
            created = []
            for unit in range(intake.units):
                item_id = new_id()
                values = {
                    "product_id": intake.product_id,
                    "variant_ref": intake.variant_ref,
                    "title": intake.title,
                    "category": intake.category,
                    "collection": intake.collection,
                    "claim_level": intake.claim_level,
                    "evidence_status": intake.evidence_status,
                    "acquisition_source": intake.source,
                    "acquisition_status": "declared",
                    "source_ref": intake.media_ref,
                    "receipt_line_ref": intake.receipt_line_ref,
                    "unit_index": unit if intake.receipt_line_ref else None,
                    "tag_serial_hash": intake.tag_serial_hash,
                    "color_family": intake.color_family,
                    "colors": intake.colors,
                    "materials": intake.materials,
                    "size_label": intake.size_label,
                    "item_condition": intake.condition,
                    "care_state": intake.care_state,
                    "user_notes": intake.user_notes,
                    "price_minor": intake.price_minor,
                    "price_currency": intake.price_currency,
                    "price_is_estimate": intake.price_is_estimate,
                }
                row = self._insert_item(txn, member_id, item_id, values)
                ctx.emit(
                    "wardrobe.item.created",
                    "1",
                    "wardrobe_item",
                    item_id,
                    1,
                    {
                        "member_id": member_id,
                        "item_id": item_id,
                        "collection": intake.collection,
                        "acquisition_source": intake.source,
                        "claim_level": intake.claim_level,
                    },
                    "member_private",
                )
                created.append(row)
            placement = None
            if intake.placement is not None:
                row = created[0]
                p = parse_placement(intake.placement, category=row["category"], product_id=row["product_id"])
                layout = self._ensure_layout(txn, ctx, member_id, p.room_template_id)
                placement = self._write_placement(txn, ctx, member_id, row["item_id"], layout, p, expected=0)
            items = []
            for row in created:
                row = dict(row, created_at=now, updated_at=now)
                items.append(self.full_item(row, placement if placement and placement["wardrobe_item_id"] == row["item_id"] else None))
            return {
                "items": items,
                "duplicate_candidates": [
                    {"item_id": c.item_id, "reason": c.reason, "strength": c.strength, "mergeable": c.mergeable} for c in candidates
                ],
            }

        request = body if isinstance(body, Mapping) else {}
        response, _replayed = idempotent_command(self.db, principal, "wardrobe.items.create", idempotency_key, request, txn_fn)
        return response

    # -------------------------------------------------------- item edits

    def _bump(self, txn, ctx: CommandContext, row: Dict[str, Any], changes: Mapping[str, Any], changed_fields: Iterable[str]) -> Dict[str, Any]:
        row = dict(row)
        row.update(changes)
        row["version"] += 1
        cols = ("member_id", "item_id", *changes.keys(), "version", "updated_at")
        txn.update("WardrobeItems", columns=cols, values=[[row["member_id"], row["item_id"], *changes.values(), row["version"], COMMIT_TIMESTAMP]])
        ctx.emit(
            "wardrobe.item.updated",
            "1",
            "wardrobe_item",
            row["item_id"],
            row["version"],
            {
                "member_id": row["member_id"],
                "item_id": row["item_id"],
                "item_version": str(row["version"]),
                "collection": row["collection"],
                "changed_fields": sorted(set(changed_fields)),
            },
            "member_private",
        )
        row["updated_at"] = self.clock.now()
        return row

    def _check_version(self, row: Mapping[str, Any], if_match: Optional[str]) -> None:
        expected = parse_revision(if_match)
        if expected != row["version"]:
            raise DetailedVersionConflict("item changed since you loaded it", row["version"])

    def patch_item(self, principal: Principal, item_id: str, if_match: Optional[str], body: Any) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:write")
        item_id = require_uuid(item_id, name="item_id")
        if not isinstance(body, Mapping) or not body:
            raise ValidationFailed("body must be a non-empty object")
        reject_non_finite(body)
        factual = sorted(set(body) & set(FACTUAL_FIELDS))
        if factual:
            raise ValidationFailed(
                f"these facts have another authority and cannot be edited here: {', '.join(factual)}",
                extra={"rejected_fields": factual},
            )
        reject_unknown_keys(body, PATCH_KEYS, where="item patch")
        changes: Dict[str, Any] = {}
        if "title" in body:
            changes["title"] = require_text(body["title"], name="title", max_len=200)
        if "collection" in body:
            if body["collection"] not in MEMBER_COLLECTIONS:
                raise ValidationFailed("collection can be changed between owned and want here; use archive/unarchive otherwise", extra={"field": "collection"})
            changes["collection"] = body["collection"]
        for key, col, allowed in (("color_family", "color_family", COLOR_FAMILIES), ("condition", "item_condition", CONDITIONS), ("care_state", "care_state", CARE_STATES)):
            if key in body:
                if body[key] is not None and body[key] not in allowed:
                    raise ValidationFailed(f"{key} must be one of {allowed}", extra={"field": key})
                if key == "care_state" and body[key] is None:
                    raise ValidationFailed("care_state cannot be null", extra={"field": key})
                changes[col] = body[key]
        for key, n in (("size_label", 40), ("care_notes", 1000), ("user_notes", 2000)):
            if key in body:
                changes[key] = None if body[key] is None else require_text(body[key], name=key, max_len=n)
        for key, n, m in (("colors", 8, 32), ("materials", 12, 60)):
            if key in body:
                v = body[key]
                if not isinstance(v, list) or len(v) > n:
                    raise ValidationFailed(f"{key} must be a list of at most {n}", extra={"field": key})
                changes[key] = [require_text(x, name=key, max_len=m) for x in v]

        def txn_fn(txn, ctx: CommandContext):
            self._writable(txn, principal.member_id)
            row = self._require_item(txn, principal.member_id, item_id)
            self._check_version(row, if_match)
            if "collection" in changes:
                if row["collection"] not in MEMBER_COLLECTIONS:
                    raise DetailedInvalidTransition(
                        f"a {row['collection']} item's collection follows its order or rights record", code="collection_not_member_editable"
                    )
                if changes["collection"] == "want" and row["acquisition_source"] in ("order", "receipt"):
                    raise DetailedInvalidTransition("purchase-evidenced items cannot become wishlist entries; archive instead", code="collection_not_member_editable")
            row = self._bump(txn, ctx, row, changes, changes.keys())
            if row["collection"] not in PLACEABLE_COLLECTIONS:
                self._remove_placement(txn, ctx, principal.member_id, item_id)
            return self.full_item(row, self._placement(txn, principal.member_id, item_id))

        return command(self.db, principal, txn_fn)

    def archive_item(self, principal: Principal, item_id: str, if_match: Optional[str], *, archive: bool = True) -> Dict[str, Any]:
        """Reversible organization; never touches ownership/chain records."""
        require_scope(principal, "wardrobe:write")
        item_id = require_uuid(item_id, name="item_id")

        def txn_fn(txn, ctx: CommandContext):
            self._writable(txn, principal.member_id)
            row = self._require_item(txn, principal.member_id, item_id)
            self._check_version(row, if_match)
            if archive:
                if row["collection"] == "archive":
                    return self.full_item(row, None)
                row = self._bump(txn, ctx, row, {"collection": "archive", "pre_archive_collection": row["collection"]}, ["collection"])
                self._remove_placement(txn, ctx, principal.member_id, item_id)
            else:
                if row["collection"] != "archive":
                    return self.full_item(row, self._placement(txn, principal.member_id, item_id))
                if row["acquisition_status"] in ("returned", "cancelled"):
                    raise DetailedInvalidTransition("a returned or cancelled order item cannot be restored", code="not_restorable")
                restore = row["pre_archive_collection"] or "owned"
                row = self._bump(txn, ctx, row, {"collection": restore, "pre_archive_collection": None, "duplicate_of": None}, ["collection"])
            return self.full_item(row, None)

        return command(self.db, principal, txn_fn)

    def resolve_duplicate(self, principal: Principal, item_id: str, other_id: str, action: str) -> Dict[str, Any]:
        """Member-controlled duplicate handling (BM-WARD-004). ``merge`` archives
        ``item_id`` as a duplicate of ``other_id`` (reversible via unarchive);
        ``keep_both`` changes nothing. Distinct physical units cannot merge."""
        require_scope(principal, "wardrobe:write")
        item_id = require_uuid(item_id, name="item_id")
        other_id = require_uuid(other_id, name="other_id")
        if action not in ("merge", "keep_both"):
            raise ValidationFailed("action must be merge or keep_both", extra={"field": "action"})

        def txn_fn(txn, ctx: CommandContext):
            self._writable(txn, principal.member_id)
            a = self._require_item(txn, principal.member_id, item_id)
            b = self._require_item(txn, principal.member_id, other_id)
            if action == "keep_both":
                return {"result": "kept_both", "items": [self.full_item(a), self.full_item(b)]}
            ok, reason = can_merge(
                ExistingItem(a["item_id"], a["product_id"], a["variant_ref"], a["receipt_line_ref"], a["unit_index"], a["tag_serial_hash"], a["collection"], a["duplicate_of"]),
                ExistingItem(b["item_id"], b["product_id"], b["variant_ref"], b["receipt_line_ref"], b["unit_index"], b["tag_serial_hash"], b["collection"], b["duplicate_of"]),
            )
            if not ok:
                raise DetailedInvalidTransition(f"these are different physical items ({reason})", code=reason)
            a = self._bump(
                txn, ctx, a, {"collection": "archive", "pre_archive_collection": a["collection"], "duplicate_of": other_id}, ["collection", "duplicate_of"]
            )
            self._remove_placement(txn, ctx, principal.member_id, item_id)
            return {"result": "merged", "items": [self.full_item(a), self.full_item(b)]}

        return command(self.db, principal, txn_fn)

    def record_worn(self, principal: Principal, item_id: str, idempotency_key: Optional[str]) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:write")
        item_id = require_uuid(item_id, name="item_id")

        def txn_fn(txn, ctx: CommandContext):
            self._writable(txn, principal.member_id)
            row = self._require_item(txn, principal.member_id, item_id)
            if row["collection"] not in ("owned", "digital"):
                raise DetailedInvalidTransition("only owned items can be worn", code="not_owned")
            row = self._bump(txn, ctx, row, {"worn_count": row["worn_count"] + 1, "last_worn_at": self.clock.now()}, ["worn_count"])
            return self.full_item(row)

        response, _ = idempotent_command(self.db, principal, "wardrobe.items.worn", idempotency_key, {"item_id": item_id}, txn_fn)
        return response

    def accept_receipt_evidence(self, member_id: str, receipt_line_ref: str, *, reviewer: str = "receipt-review") -> int:
        """Reviewer/automated path: receipt evidence accepted → receipt_backed.
        A member cannot call this (ch.01 §4.4 factual records)."""
        principal = service_principal(reviewer)

        def txn_fn(txn, ctx: CommandContext):
            rows = query(
                txn,
                f"SELECT {', '.join(ITEM_COLUMNS)} FROM WardrobeItems WHERE member_id=@m AND receipt_line_ref=@r",
                {"m": member_id, "r": receipt_line_ref},
                {"m": STR, "r": STR},
            )
            n = 0
            for r in rows:
                row = _row(ITEM_COLUMNS, r)
                if row["claim_level"] == "self_reported" and row["evidence_status"] == "receipt_pending_review":
                    self._bump(txn, ctx, row, {"claim_level": "receipt_backed", "evidence_status": "receipt_accepted"}, ["claim_level"])
                    n += 1
            return n

        return command(self.db, principal, txn_fn)

    # ------------------------------------------------------------ closet

    def _layout(self, txn, member_id: str) -> Optional[Dict[str, Any]]:
        rows = query(
            txn,
            "SELECT layout_id, room_template_id, room_revision, version FROM ClosetLayouts WHERE member_id=@m",
            {"m": member_id},
            {"m": STR},
        )
        if not rows:
            return None
        return dict(zip(("layout_id", "room_template_id", "room_revision", "version"), rows[0]))

    def _ensure_layout(self, txn, ctx: CommandContext, member_id: str, room_id: str) -> Dict[str, Any]:
        layout = self._layout(txn, member_id)
        if layout is None:
            layout = {
                "layout_id": stable_id("closet-layout", member_id),
                "room_template_id": room_id,
                "room_revision": ROOMS[room_id].revision,
                "version": 1,
            }
            txn.insert(
                "ClosetLayouts",
                columns=("member_id", "layout_id", "room_template_id", "room_revision", "version", "updated_at"),
                values=[(member_id, layout["layout_id"], room_id, layout["room_revision"], 1, COMMIT_TIMESTAMP)],
            )
            ctx.emit(
                "closet.layout.changed", "1", "closet_layout", layout["layout_id"], 1,
                {"member_id": member_id, "layout_version": "1", "room_template_id": room_id}, "member_private",
            )
        if layout["room_template_id"] != room_id:
            raise DetailedInvalidTransition(
                f"your closet is set to {layout['room_template_id']}; change the room first",
                code="room_mismatch",
                extra={"room_template_id": layout["room_template_id"]},
            )
        return layout

    def _placement(self, txn, member_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        rows = query(
            txn,
            f"SELECT {', '.join(PLACEMENT_COLUMNS)} FROM ClosetPlacements WHERE member_id=@m AND item_id=@i",
            {"m": member_id, "i": item_id},
            {"m": STR, "i": STR},
        )
        if not rows:
            return None
        return self._placement_dto(_row(PLACEMENT_COLUMNS, rows[0]))

    @staticmethod
    def _placement_dto(r: Mapping[str, Any]) -> Dict[str, Any]:
        if r["semantic_group"] is None:
            p = Placement(r["room_template_id"], None, None, None, None, None, r["asset_revision"])
        else:
            p = Placement(
                r["room_template_id"], r["semantic_group"], r["slot_id"], (r["pos_x"], r["pos_y"], r["pos_z"]),
                (r["rot_x"], r["rot_y"], r["rot_z"], r["rot_w"]), r["uniform_scale"], r["asset_revision"],
            )
        return placement_dto(r["item_id"], r["layout_id"], p, r["version"])

    def _slot_occupant(self, txn, member_id: str, p: Placement) -> Optional[str]:
        rows = query(
            txn,
            "SELECT item_id FROM ClosetPlacements "
            "WHERE member_id=@m AND room_template_id=@r AND semantic_group=@g AND slot_id=@s",
            {"m": member_id, "r": p.room_template_id, "g": p.semantic_group, "s": p.slot_id},
            {"m": STR, "r": STR, "g": STR, "s": STR},
        )
        return rows[0][0] if rows else None

    def _write_placement(
        self, txn, ctx: CommandContext, member_id: str, item_id: str, layout: Mapping[str, Any], p: Placement,
        *, expected: Optional[int], current: Optional[Dict[str, Any]] = None, ignore_occupants: Iterable[str] = (),
        change_kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        current_version = int(current["version"]) if current else 0
        if expected is not None and expected != current_version:
            raise DetailedVersionConflict(
                "this item was moved on another device", current_version, extra={"current_placement": current}
            )
        if p.placed:
            occupant = self._slot_occupant(txn, member_id, p)
            if occupant and occupant != item_id and occupant not in set(ignore_occupants):
                raise DetailedInvalidTransition(
                    "that slot is taken", code="slot_occupied", extra={"occupant_item_id": occupant, "slot_id": p.slot_id}
                )
        version = current_version + 1
        pos = p.position or (None, None, None)
        rot = p.rotation or (None, None, None, None)
        values = [
            member_id, item_id, layout["layout_id"], p.room_template_id, p.semantic_group, p.slot_id, *pos, *rot,
            p.uniform_scale, p.asset_revision, version, COMMIT_TIMESTAMP,
        ]
        txn.insert_or_update("ClosetPlacements", columns=PLACEMENT_COLUMNS, values=[values])
        kind = change_kind or ("unplaced" if not p.placed else ("placed" if current is None or current.get("semantic_group") is None else "moved"))
        ctx.emit(
            "closet.placement.changed", "1", "closet_placement", item_id, version,
            {"member_id": member_id, "item_id": item_id, "placement_version": str(version), "change_kind": kind},
            "member_private",
        )
        return placement_dto(item_id, layout["layout_id"], p, version)

    def _remove_placement(self, txn, ctx: CommandContext, member_id: str, item_id: str) -> None:
        current = self._placement(txn, member_id, item_id)
        if current is None:
            return
        txn.delete("ClosetPlacements", KeySet(keys=[[member_id, item_id]]))
        v = int(current["version"]) + 1
        ctx.emit(
            "closet.placement.changed", "1", "closet_placement", item_id, v,
            {"member_id": member_id, "item_id": item_id, "placement_version": str(v), "change_kind": "removed"},
            "member_private",
        )

    def get_layout(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:read")

        def read(s):
            layout = self._layout(s, principal.member_id)
            rows = query(
                s,
                f"SELECT {', '.join(PLACEMENT_COLUMNS)} FROM ClosetPlacements WHERE member_id=@m ORDER BY item_id",
                {"m": principal.member_id},
                {"m": STR},
            )
            return layout, [self._placement_dto(_row(PLACEMENT_COLUMNS, r)) for r in rows]

        layout, placements = run_read(self.db, read)
        room_id = layout["room_template_id"] if layout else DEFAULT_ROOM
        tpl = ROOMS[room_id]
        return {
            "layout_id": layout["layout_id"] if layout else None,
            "room_template_id": room_id,
            "room_revision": tpl.revision,
            "version": str(layout["version"]) if layout else "0",
            "placements": [p for p in placements if p["semantic_group"] is not None],
            "unplaced": [p for p in placements if p["semantic_group"] is None],
            "groups": [
                {"semantic_group": g.group_id, "capacity": g.capacity, "center_meters": list(g.center)}
                for g in tpl.groups.values()
            ],
        }

    def put_placement(self, principal: Principal, item_id: str, if_match: Optional[str], body: Any) -> Dict[str, Any]:
        """BM-WARD-003/placement contract: validated, versioned, slot-unique."""
        require_scope(principal, "wardrobe:write")
        item_id = require_uuid(item_id, name="item_id")
        expected = parse_revision(if_match)

        def txn_fn(txn, ctx: CommandContext):
            self._writable(txn, principal.member_id)
            row = self._require_item(txn, principal.member_id, item_id)
            if row["collection"] not in PLACEABLE_COLLECTIONS:
                raise DetailedInvalidTransition("only owned or digital items can be placed in the room", code="not_placeable")
            p = parse_placement(body, category=row["category"] or "", product_id=row["product_id"])
            layout = self._ensure_layout(txn, ctx, principal.member_id, p.room_template_id)
            return self._write_placement(
                txn, ctx, principal.member_id, item_id, layout, p, expected=expected, current=self._placement(txn, principal.member_id, item_id)
            )

        return command(self.db, principal, txn_fn)

    def batch_placements(self, principal: Principal, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        """Atomic reorder of at most 50 owned items; swaps within the batch allowed."""
        require_scope(principal, "wardrobe:write")
        if not isinstance(body, Mapping) or set(body) != {"placements"} or not isinstance(body["placements"], list):
            raise ValidationFailed('body must be {"placements": [...]}')
        entries = body["placements"]
        if not (1 <= len(entries) <= MAX_BATCH):
            raise ValidationFailed(f"a batch moves 1-{MAX_BATCH} items", extra={"field": "placements"})
        ids = []
        for e in entries:
            if not isinstance(e, Mapping):
                raise ValidationFailed("each placement must be an object")
            ids.append(require_uuid(e.get("wardrobe_item_id"), name="wardrobe_item_id"))
        if len(set(ids)) != len(ids):
            raise ValidationFailed("an item appears twice in one batch", extra={"field": "placements"})

        def txn_fn(txn, ctx: CommandContext):
            self._writable(txn, principal.member_id)
            parsed: List[Tuple[str, Placement, int, Optional[Dict[str, Any]]]] = []
            for item_id, e in zip(ids, entries):
                row = self._require_item(txn, principal.member_id, item_id)
                if row["collection"] not in PLACEABLE_COLLECTIONS:
                    raise DetailedInvalidTransition(f"item {item_id} cannot be placed", code="not_placeable")
                v = e.get("version")
                if not isinstance(v, str) or not v.isdigit():
                    raise ValidationFailed("each placement needs its current version", extra={"field": "version"})
                p = parse_placement({k: x for k, x in e.items() if k not in ("wardrobe_item_id", "version")}, category=row["category"] or "", product_id=row["product_id"])
                parsed.append((item_id, p, int(v), self._placement(txn, principal.member_id, item_id)))
            check_unique_slots((i, p) for i, p, _, _ in parsed)
            rooms = {p.room_template_id for _, p, _, _ in parsed}
            if len(rooms) != 1:
                raise ValidationFailed("a batch targets one room", extra={"field": "room_template_id"})
            layout = self._ensure_layout(txn, ctx, principal.member_id, rooms.pop())
            moving = set(ids)
            out = [
                self._write_placement(txn, ctx, principal.member_id, i, layout, p, expected=v, current=cur, ignore_occupants=moving)
                for i, p, v, cur in parsed
            ]
            return {"placements": out}

        response, _ = idempotent_command(self.db, principal, "closet.placements.batch", idempotency_key, dict(body), txn_fn)
        return response

    def set_theme(self, principal: Principal, if_match: Optional[str], room_template_id: Any, *, preview: bool = False) -> Dict[str, Any]:
        """Deterministic semantic remap (ch.02 §4.5); preview writes nothing."""
        require_scope(principal, "wardrobe:read" if preview else "wardrobe:write")
        if room_template_id not in ROOMS:
            raise ValidationFailed("unknown room_template_id", extra={"field": "room_template_id"})
        expected = None if preview else parse_revision(if_match)

        def plan(txn):
            rows = [
                _row(PLACEMENT_COLUMNS, r)
                for r in query(
                    txn,
                    f"SELECT {', '.join(PLACEMENT_COLUMNS)} FROM ClosetPlacements WHERE member_id=@m",
                    {"m": principal.member_id},
                    {"m": STR},
                )
            ]
            current = [
                (r["item_id"], r["semantic_group"], r["slot_id"], r["uniform_scale"],
                 None if r["rot_w"] is None else (r["rot_x"], r["rot_y"], r["rot_z"], r["rot_w"]))
                for r in rows
            ]
            return rows, remap_theme(current, room_template_id)

        def summary(entries) -> Dict[str, Any]:
            return {
                "room_template_id": room_template_id,
                "kept": [e.item_id for e in entries if e.to.placed],
                "moved_to_unplaced": [e.item_id for e in entries if not e.to.placed and e.from_group is not None],
            }

        if preview:
            _rows, entries = run_read(self.db, plan)
            return {"preview": True, **summary(entries)}

        def txn_fn(txn, ctx: CommandContext):
            self._writable(txn, principal.member_id)
            layout = self._layout(txn, principal.member_id)
            current_version = layout["version"] if layout else 0
            if expected != current_version:
                raise DetailedVersionConflict("closet layout changed on another device", current_version)
            rows, entries = plan(txn)
            if layout is None:
                layout = self._ensure_layout(txn, ctx, principal.member_id, room_template_id)
            else:
                layout = dict(layout, room_template_id=room_template_id, room_revision=ROOMS[room_template_id].revision, version=layout["version"] + 1)
                txn.update(
                    "ClosetLayouts",
                    columns=("member_id", "room_template_id", "room_revision", "version", "updated_at"),
                    values=[(principal.member_id, room_template_id, layout["room_revision"], layout["version"], COMMIT_TIMESTAMP)],
                )
                ctx.emit(
                    "closet.layout.changed", "1", "closet_layout", layout["layout_id"], layout["version"],
                    {"member_id": principal.member_id, "layout_version": str(layout["version"]), "room_template_id": room_template_id},
                    "member_private",
                )
            by_id = {r["item_id"]: r for r in rows}
            # Clear all first so the unique slot index never sees transient clashes.
            if rows:
                txn.delete("ClosetPlacements", KeySet(keys=[[principal.member_id, i] for i in by_id]))
            for e in entries:
                prev = by_id[e.item_id]
                version = prev["version"] + 1
                pos = e.to.position or (None, None, None)
                rot = e.to.rotation or (None, None, None, None)
                txn.insert(
                    "ClosetPlacements",
                    columns=PLACEMENT_COLUMNS,
                    values=[[principal.member_id, e.item_id, layout["layout_id"], e.to.room_template_id, e.to.semantic_group, e.to.slot_id,
                             *pos, *rot, e.to.uniform_scale, e.to.asset_revision, version, COMMIT_TIMESTAMP]],
                )
                ctx.emit(
                    "closet.placement.changed", "1", "closet_placement", e.item_id, version,
                    {"member_id": principal.member_id, "item_id": e.item_id, "placement_version": str(version), "change_kind": "theme_remapped"},
                    "member_private",
                )
            return {"preview": False, "layout_version": str(layout["version"]), **summary(entries)}

        return command(self.db, principal, txn_fn)

    # ------------------------------------------------------------ orders

    def apply_order_observation(self, event: EventEnvelope) -> Dict[str, Any]:
        """Reduce a ``commerce.order.observed`` event into per-unit wardrobe items
        (BM-WARD-008). Exactly-once via the foundation inbox; monotonic by
        order version; deterministic unit item ids."""
        if event.event_type != "commerce.order.observed":
            raise ValidationFailed("not an order observation")
        pl = event.payload
        member_id = require_uuid(pl.get("member_id"), name="member_id")
        order_id = str(pl.get("order_id"))
        lines = pl.get("lines") or []
        cancelled = pl.get("order_status") == "cancelled"
        principal = service_principal(ORDER_CONSUMER, environment=event.environment)

        def txn_fn(txn, ctx: CommandContext):
            ctx.causation_id = event.event_id
            if not first_delivery(txn, ORDER_CONSUMER, event):
                return {"status": "duplicate_delivery"}
            if not member_active(txn, member_id):
                return {"status": "member_inactive"}
            try:
                assert_processing_allowed(txn, member_id, "wardrobe.items", event.occurred_at)
            except ProcessingFrozen:
                return {"status": "processing_frozen"}
            link = query(
                txn,
                "SELECT last_order_version FROM WardrobeOrderLinks WHERE member_id=@m AND order_id=@o",
                {"m": member_id, "o": order_id},
                {"m": STR, "o": STR},
            )
            if link and link[0][0] >= event.aggregate_version:
                return {"status": "stale_version"}
            txn.insert_or_update(
                "WardrobeOrderLinks",
                columns=("member_id", "order_id", "last_order_version", "updated_at"),
                values=[(member_id, order_id, event.aggregate_version, COMMIT_TIMESTAMP)],
            )
            changes = {"created": 0, "updated": 0, "unchanged": 0}
            for line in lines:
                variant_ref = str(line.get("source_variant_ref"))
                info = self.catalog_lookup(str(line.get("variant_id"))) or {}
                for u in order_unit_states(int(line.get("ordered", 0)), int(line.get("delivered", 0)), int(line.get("returned", 0)), cancelled):
                    item_id = stable_id("order-unit", member_id, order_id, variant_ref, str(u.unit_index))
                    row = self._item(txn, member_id, item_id)
                    if row is None:
                        self._insert_item(
                            txn, member_id, item_id,
                            {
                                "product_id": info.get("product_id"),
                                "variant_ref": variant_ref,
                                "title": info.get("title") or "Item from your order",
                                "category": info.get("category") if info.get("category") in CATEGORIES else None,
                                "collection": u.collection,
                                "claim_level": "receipt_backed",
                                "evidence_status": "provider_order_observed",
                                "acquisition_source": "order",
                                "acquisition_status": u.acquisition_status,
                                "source_ref": order_id,
                                "unit_index": u.unit_index,
                            },
                        )
                        ctx.emit(
                            "wardrobe.item.created", "1", "wardrobe_item", item_id, 1,
                            {"member_id": member_id, "item_id": item_id, "collection": u.collection, "acquisition_source": "order", "claim_level": "receipt_backed"},
                            "member_private",
                        )
                        changes["created"] += 1
                        continue
                    if row["acquisition_status"] == u.acquisition_status:
                        changes["unchanged"] += 1
                        continue
                    member_archived = row["collection"] == "archive" and row["acquisition_status"] not in ("returned", "cancelled")
                    new_collection = u.collection
                    upd: Dict[str, Any] = {"acquisition_status": u.acquisition_status}
                    if member_archived and u.collection != "archive":
                        upd["pre_archive_collection"] = u.collection  # respect the member's archive
                        new_collection = "archive"
                    upd["collection"] = new_collection
                    self._bump(txn, ctx, row, upd, ["collection", "acquisition_status"])
                    if new_collection not in PLACEABLE_COLLECTIONS:
                        self._remove_placement(txn, ctx, member_id, item_id)
                    changes["updated"] += 1
            return {"status": "applied", **changes}

        return command(self.db, principal, txn_fn)
