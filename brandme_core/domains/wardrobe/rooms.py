"""
Server-side room templates and garment display bounds used to validate
closet placements (ch.02 §4.2/§4.5).

Values mirror the spatial lane's manifests at revision ``original-v1``
(``brandme-frontend/public/demo/rooms/*/manifest.json`` and
``.../garments/*/manifest.json`` on ``bench/astra-spatial-ar-20261005``).
``tests/test_wardrobe_placement.py`` compares them against those manifests when
the files are present, so geometry cannot silently drift. Walnut Atelier group
centres are the ch.02 §4.2 values verbatim.

A placement for a room revision the server does not know is rejected: the
client must reload the room manifest rather than persist coordinates against
geometry the server cannot check.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Mapping, Optional, Tuple

Vec3 = Tuple[float, float, float]

GROUP_IDS = ("rail.left", "rail.right", "shelf.shoes", "shelf.folded", "tray.accessories", "stand.outfit")

# Category → eligible semantic destinations ("show eligible semantic destinations").
ELIGIBLE: Mapping[str, FrozenSet[str]] = {
    "top": frozenset({"rail.left", "rail.right", "shelf.folded", "stand.outfit"}),
    "bottom": frozenset({"rail.left", "rail.right", "shelf.folded", "stand.outfit"}),
    "dress": frozenset({"rail.left", "rail.right", "stand.outfit"}),
    "outerwear": frozenset({"rail.left", "rail.right", "stand.outfit"}),
    "shoes": frozenset({"shelf.shoes", "stand.outfit"}),
    "accessory": frozenset({"tray.accessories", "shelf.folded", "stand.outfit"}),
}

# Half-extents of a group's placement volume beyond its slot line (metres).
GROUP_HALF_HEIGHT = 0.40
GROUP_HALF_DEPTH = 0.35
GROUP_WIDTH_TOLERANCE = 0.05


@dataclass(frozen=True)
class SlotGroup:
    group_id: str
    center: Vec3
    capacity: int
    pitch: float
    width: float

    def slot_ids(self) -> Tuple[str, ...]:
        return tuple(str(i) for i in range(self.capacity))

    def slot_position(self, slot_id: str) -> Vec3:
        i = int(slot_id)
        cx, cy, cz = self.center
        offset = (i - (self.capacity - 1) / 2.0) * self.pitch
        return (round(cx + offset, 6), cy, cz)

    def contains(self, p: Vec3) -> bool:
        cx, cy, cz = self.center
        return (
            abs(p[0] - cx) <= self.width / 2.0 + GROUP_WIDTH_TOLERANCE
            and abs(p[1] - cy) <= GROUP_HALF_HEIGHT
            and abs(p[2] - cz) <= GROUP_HALF_DEPTH
        )


@dataclass(frozen=True)
class RoomTemplate:
    room_id: str
    title: str
    revision: str
    dimensions: Vec3
    bounds_min: Vec3
    bounds_max: Vec3
    groups: Mapping[str, SlotGroup]

    def inside(self, p: Vec3) -> bool:
        return all(self.bounds_min[i] <= p[i] <= self.bounds_max[i] for i in range(3))


def _groups(*specs) -> Dict[str, SlotGroup]:
    return {g[0]: SlotGroup(g[0], g[1], g[2], g[3], g[4]) for g in specs}


ROOMS: Dict[str, RoomTemplate] = {
    "walnut_atelier": RoomTemplate(
        "walnut_atelier",
        "Walnut Atelier",
        "original-v1",
        (4.8, 3.6, 2.8),
        (-2.4425, -0.09, -1.8425),
        (2.445, 2.8, 1.8),
        _groups(
            ("rail.left", (-1.45, 1.75, -0.65), 12, 0.12, 1.45),
            ("rail.right", (1.45, 1.75, -0.65), 12, 0.12, 1.45),
            ("shelf.shoes", (0.0, 0.24, -1.15), 8, 0.12, 1.1),
            ("shelf.folded", (0.0, 1.05, -1.15), 6, 0.12, 1.1),
            ("tray.accessories", (1.45, 0.85, 0.4), 6, 0.12, 1.1),
            ("stand.outfit", (0.0, 0.0, -0.1), 1, 0.12, 1.1),
        ),
    ),
    "limestone_gallery": RoomTemplate(
        "limestone_gallery",
        "Limestone Gallery",
        "original-v1",
        (5.2, 4.0, 3.0),
        (-2.6425, -0.09, -2.0425),
        (2.645, 3.0, 2.0),
        _groups(
            ("rail.left", (-1.65, 1.75, -0.85), 12, 0.12, 1.45),
            ("rail.right", (1.65, 1.75, -0.85), 12, 0.12, 1.45),
            ("shelf.shoes", (0.0, 0.24, -1.15), 8, 0.12, 1.1),
            ("shelf.folded", (0.0, 1.05, -1.15), 6, 0.12, 1.1),
            ("tray.accessories", (1.45, 0.85, 0.4), 6, 0.12, 1.1),
            ("stand.outfit", (0.0, 0.0, -0.1), 1, 0.12, 1.1),
        ),
    ),
    "garden_studio": RoomTemplate(
        "garden_studio",
        "Garden Studio",
        "original-v1",
        (4.6, 3.8, 2.8),
        (-2.3425, -0.09, -1.9425),
        (2.345, 2.8, 1.9),
        _groups(
            ("rail.left", (-1.45, 1.75, -0.65), 12, 0.12, 1.45),
            ("shelf.shoes", (-1.35, 0.24, -0.87), 8, 0.12, 1.1),
            ("shelf.folded", (1.34, 1.05, -1.15), 6, 0.12, 1.1),
            ("tray.accessories", (1.45, 0.85, 0.4), 6, 0.12, 1.1),
        ),
    ),
}

DEFAULT_ROOM = "walnut_atelier"

# Asset-specific display scale bounds (garment manifests: displayScaleBounds).
DEFAULT_SCALE_BOUNDS: Tuple[float, float] = (0.65, 1.25)
GARMENT_SCALE_BOUNDS: Dict[str, Tuple[float, float]] = {
    "a4036cb0-7ab2-54b5-9238-ee5ffb378771": (0.65, 1.25),  # overshirt
    "6b4ee94a-4998-55d8-8298-c8f81a40b7aa": (0.65, 1.25),  # trousers
    "9572fdc7-31e0-5b80-be82-147ef4a5e69c": (0.65, 1.25),  # dress
    "5a0ccc0d-d627-52fa-ab80-de662ef92b1b": (0.65, 1.25),  # jacket
    "bdbff281-45f2-5887-b09b-6db9151126f6": (0.65, 1.25),  # sneaker
    "21e655b5-f16d-57c8-bf99-c7af6e942c6f": (0.65, 1.25),  # bag
}


def room(room_id: str) -> Optional[RoomTemplate]:
    return ROOMS.get(room_id)


def scale_bounds(product_id: Optional[str]) -> Tuple[float, float]:
    return GARMENT_SCALE_BOUNDS.get(product_id or "", DEFAULT_SCALE_BOUNDS)
