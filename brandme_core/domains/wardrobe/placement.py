"""
Closet placement validation and theme remapping: pure, deterministic.

Contract (ch.02 §4.5, contracts/README invariant 4): quaternions are finite and
normalized within an explicit tolerance; positions and scales are finite,
asset-bounded and inside the selected semantic group; the slot must exist in
the room and suit the item's category. NaN/Infinity are rejected before
anything is serialized. Placement is decorative: it can never change a
wardrobe item's collection or ownership.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from brandme_core.domains.persona.kernel import ValidationFailed

from .rooms import ELIGIBLE, ROOMS, RoomTemplate, scale_bounds

QUATERNION_TOLERANCE = 1e-3  # |‖q‖ − 1| must not exceed this
PLACEMENT_KEYS = (
    "room_template_id",
    "semantic_group",
    "slot_id",
    "position_meters",
    "rotation_quaternion",
    "uniform_scale",
    "asset_revision",
)


@dataclass(frozen=True)
class Placement:
    room_template_id: str
    semantic_group: Optional[str]  # None = Unplaced tray
    slot_id: Optional[str]
    position: Optional[Tuple[float, float, float]]
    rotation: Optional[Tuple[float, float, float, float]]
    uniform_scale: Optional[float]
    asset_revision: str

    @property
    def placed(self) -> bool:
        return self.semantic_group is not None


def _finite(v: Any, name: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValidationFailed(f"{name} must be a number", extra={"field": name})
    f = float(v)
    if not math.isfinite(f):
        raise ValidationFailed(f"{name} must be finite", extra={"field": name})
    return f


def _vector(v: Any, n: int, name: str) -> Tuple[float, ...]:
    if not isinstance(v, (list, tuple)) or len(v) != n:
        raise ValidationFailed(f"{name} must be an array of {n} numbers", extra={"field": name})
    return tuple(_finite(x, f"{name}[{i}]") for i, x in enumerate(v))


def normalize_quaternion(q: Sequence[float]) -> Tuple[float, float, float, float]:
    """Validate ‖q‖ ≈ 1, then canonicalize: exact unit length, w ≥ 0 (q ≡ −q)."""
    norm = math.sqrt(sum(c * c for c in q))
    if not math.isfinite(norm) or abs(norm - 1.0) > QUATERNION_TOLERANCE:
        raise ValidationFailed(
            f"rotation_quaternion must be normalized (|norm-1| <= {QUATERNION_TOLERANCE}); got norm {norm:.6g}",
            extra={"field": "rotation_quaternion"},
        )
    x, y, z, w = (c / norm for c in q)
    if w < 0 or (w == 0 and (x, y, z) < (0.0, 0.0, 0.0)):
        x, y, z, w = -x, -y, -z, -w
    return (round(x, 9), round(y, 9), round(z, 9), round(w, 9))


def parse_placement(body: Any, *, category: str, product_id: Optional[str]) -> Placement:
    if not isinstance(body, Mapping):
        raise ValidationFailed("placement must be an object")
    allowed = set(PLACEMENT_KEYS) | {"wardrobe_item_id", "layout_id", "version"}
    unknown = sorted(set(body) - allowed)
    if unknown:
        raise ValidationFailed(f"placement contains unsupported fields: {', '.join(unknown)}", extra={"rejected_fields": unknown})
    room_id = body.get("room_template_id")
    tpl: Optional[RoomTemplate] = ROOMS.get(room_id) if isinstance(room_id, str) else None
    if tpl is None:
        raise ValidationFailed("unknown room_template_id", extra={"field": "room_template_id"})
    rev = body.get("asset_revision")
    if not isinstance(rev, str) or not (1 <= len(rev) <= 128):
        raise ValidationFailed("asset_revision is required", extra={"field": "asset_revision"})
    if rev != tpl.revision:
        raise ValidationFailed(
            f"room asset revision {rev!r} is not the current {tpl.revision!r}; reload the room",
            extra={"field": "asset_revision", "current_asset_revision": tpl.revision},
        )
    group = body.get("semantic_group")
    if group is None:
        # Explicit move to the Unplaced tray: no coordinates are kept.
        if any(body.get(k) is not None for k in ("slot_id", "position_meters", "rotation_quaternion", "uniform_scale")):
            raise ValidationFailed("an unplaced item has no slot or transform")
        return Placement(tpl.room_id, None, None, None, None, None, rev)
    if not isinstance(group, str) or group not in tpl.groups:
        raise ValidationFailed(f"{tpl.title} has no {group!r} group", extra={"field": "semantic_group"})
    if group not in ELIGIBLE.get(category, frozenset()):
        raise ValidationFailed(
            f"a {category} item cannot go in {group}",
            extra={"field": "semantic_group", "eligible_groups": sorted(ELIGIBLE.get(category, frozenset()) & set(tpl.groups))},
        )
    g = tpl.groups[group]
    slot = body.get("slot_id")
    if not isinstance(slot, str) or slot not in g.slot_ids():
        raise ValidationFailed(f"slot_id must be one of 0..{g.capacity - 1} for {group}", extra={"field": "slot_id"})
    pos = _vector(body.get("position_meters"), 3, "position_meters")
    if not tpl.inside(pos):
        raise ValidationFailed("position_meters is outside the room", extra={"field": "position_meters"})
    if not g.contains(pos):
        raise ValidationFailed(f"position_meters is outside the {group} group", extra={"field": "position_meters"})
    rot = normalize_quaternion(_vector(body.get("rotation_quaternion"), 4, "rotation_quaternion"))
    scale = _finite(body.get("uniform_scale"), "uniform_scale")
    lo, hi = scale_bounds(product_id)
    if not (lo <= scale <= hi):
        raise ValidationFailed(
            f"uniform_scale must be within this item's display bounds [{lo}, {hi}]",
            extra={"field": "uniform_scale", "scale_bounds": [lo, hi]},
        )
    return Placement(tpl.room_id, group, slot, pos, rot, scale, rev)


def check_unique_slots(placements: Iterable[Tuple[str, Placement]]) -> None:
    """Within one batch, no two items may target the same (room, group, slot)."""
    seen: Dict[Tuple[str, str, str], str] = {}
    for item_id, p in placements:
        if not p.placed:
            continue
        key = (p.room_template_id, p.semantic_group, p.slot_id)
        if key in seen:
            raise ValidationFailed(
                f"items {seen[key]} and {item_id} target the same slot", extra={"field": "placements", "slot": list(key)}
            )
        seen[key] = item_id


@dataclass(frozen=True)
class RemapEntry:
    item_id: str
    from_group: Optional[str]
    from_slot: Optional[str]
    to: Placement


def remap_theme(
    current: Sequence[Tuple[str, Optional[str], Optional[str], Optional[float], Optional[Tuple[float, float, float, float]]]],
    target_room_id: str,
) -> List[RemapEntry]:
    """Deterministic semantic remap (ch.02 §4.5).

    ``current`` rows are (item_id, group, slot, scale, rotation). Each item
    keeps its semantic group and slot index if the target room has them; its
    position becomes that slot's nominal position in the target room. Anything
    without a corresponding group/slot moves to the Unplaced tray, still
    accessible. Order of input never changes the result.
    """
    tpl = ROOMS[target_room_id]
    out: List[RemapEntry] = []
    for item_id, group, slot, scale, rot in sorted(current, key=lambda r: r[0]):
        g = tpl.groups.get(group) if group else None
        if g is not None and slot is not None and slot in g.slot_ids():
            out.append(
                RemapEntry(
                    item_id,
                    group,
                    slot,
                    Placement(tpl.room_id, group, slot, g.slot_position(slot), rot or (0.0, 0.0, 0.0, 1.0), scale or 1.0, tpl.revision),
                )
            )
        else:
            out.append(RemapEntry(item_id, group, slot, Placement(tpl.room_id, None, None, None, None, None, tpl.revision)))
    return out


def placement_dto(item_id: str, layout_id: str, p: Placement, version: int) -> Dict[str, Any]:
    """Wire form; a placed item validates against contracts #ClosetPlacement."""
    if not p.placed:
        return {
            "wardrobe_item_id": item_id,
            "layout_id": layout_id,
            "room_template_id": p.room_template_id,
            "semantic_group": None,
            "slot_id": None,
            "unplaced": True,
            "asset_revision": p.asset_revision,
            "version": str(version),
        }
    return {
        "wardrobe_item_id": item_id,
        "layout_id": layout_id,
        "room_template_id": p.room_template_id,
        "semantic_group": p.semantic_group,
        "slot_id": p.slot_id,
        "position_meters": list(p.position),
        "rotation_quaternion": list(p.rotation),
        "uniform_scale": p.uniform_scale,
        "asset_revision": p.asset_revision,
        "version": str(version),
    }
