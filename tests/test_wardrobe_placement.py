"""Closet placement validation (ch.02 §4.5; contracts invariant 4): finite,
normalized quaternions; finite, asset-bounded, group-contained positions;
deterministic theme remapping. Pure — no database."""

import json
import math
import os
from pathlib import Path

import pytest

from brandme_core.domains.persona.kernel import ValidationFailed
from brandme_core.domains.wardrobe.placement import (
    QUATERNION_TOLERANCE,
    check_unique_slots,
    normalize_quaternion,
    parse_placement,
    placement_dto,
    remap_theme,
)
from brandme_core.domains.wardrobe.rooms import ROOMS

SHIRT = "a4036cb0-7ab2-54b5-9238-ee5ffb378771"
REPO = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((REPO / "docs/design/brandme/contracts/domain.schema.json").read_text())


def body(**kw):
    g = ROOMS["walnut_atelier"].groups["rail.left"]
    b = {
        "room_template_id": "walnut_atelier",
        "semantic_group": "rail.left",
        "slot_id": "3",
        "position_meters": list(g.slot_position("3")),
        "rotation_quaternion": [0, 0, 0, 1],
        "uniform_scale": 1.0,
        "asset_revision": "original-shelves-v2",
    }
    b.update(kw)
    return b


def test_valid_placement_round_trips_to_contract_shape():
    import jsonschema

    p = parse_placement(body(), category="top", product_id=SHIRT)
    dto = placement_dto("2ad9041e-561e-527b-aa0d-5a7fda5f710b", "fa9ad97d-0187-5b71-a602-b05aabb329e1", p, 1)
    schema = {"$schema": SCHEMA["$schema"], "$defs": SCHEMA["$defs"], "$ref": "#/$defs/ClosetPlacement"}
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(dto)


@pytest.mark.parametrize(
    "field,value",
    [
        ("position_meters", [math.nan, 1.75, -0.65]),
        ("position_meters", [math.inf, 1.75, -0.65]),
        ("position_meters", [-1.45, -math.inf, -0.65]),
        ("position_meters", ["-1.45", 1.75, -0.65]),
        ("position_meters", [True, 1.75, -0.65]),
        ("position_meters", [-1.45, 1.75]),
        ("rotation_quaternion", [0, 0, 0, math.nan]),
        ("rotation_quaternion", [0, 0, math.inf, 1]),
        ("rotation_quaternion", [0, 0, 0, 1.01]),
        ("rotation_quaternion", [0, 0, 0, 0]),
        ("rotation_quaternion", [0, 0, 1]),
        ("uniform_scale", math.nan),
        ("uniform_scale", 0),
        ("uniform_scale", -1),
        ("uniform_scale", 1.3),   # above this garment's display bound 1.25
        ("uniform_scale", 0.6),   # below 0.65
        ("uniform_scale", 9.0),   # schema allows <=10 but asset bounds do not
    ],
)
def test_non_finite_unnormalized_or_out_of_bounds_values_are_rejected(field, value):
    with pytest.raises(ValidationFailed):
        parse_placement(body(**{field: value}), category="top", product_id=SHIRT)


def test_quaternion_tolerance_and_canonical_form():
    eps = QUATERNION_TOLERANCE / 2
    q = normalize_quaternion([0, 0, 0, 1 + eps])
    assert q == (0.0, 0.0, 0.0, 1.0)
    a = normalize_quaternion([0, 0.7071068, 0, 0.7071068])
    b = normalize_quaternion([0, -0.7071068, 0, -0.7071068])  # same rotation
    assert a == b and a[3] >= 0
    assert abs(math.sqrt(sum(c * c for c in a)) - 1.0) < 1e-9


def test_position_must_be_inside_room_and_group():
    tpl = ROOMS["walnut_atelier"]
    with pytest.raises(ValidationFailed, match="outside the rail.left group"):
        parse_placement(body(position_meters=[1.45, 1.75, -0.65]), category="top", product_id=SHIRT)  # that's rail.right
    with pytest.raises(ValidationFailed, match="outside the room"):
        parse_placement(body(position_meters=[-1.45, 1.75, -5.0]), category="top", product_id=SHIRT)
    for room in ROOMS.values():  # every nominal slot is valid in its own room
        for g in room.groups.values():
            for s in g.slot_ids():
                pos = g.slot_position(s)
                assert room.inside(pos) and g.contains(pos), (room.room_id, g.group_id, s)
    assert tpl.groups["rail.left"].capacity * tpl.groups["rail.left"].pitch <= tpl.groups["rail.left"].width


def test_slot_room_category_and_revision_rules():
    with pytest.raises(ValidationFailed, match="slot_id"):
        parse_placement(body(slot_id="12"), category="top", product_id=SHIRT)
    with pytest.raises(ValidationFailed, match="cannot go in"):
        parse_placement(body(), category="shoes", product_id=None)
    with pytest.raises(ValidationFailed, match="has no 'rail.right'"):
        parse_placement(body(room_template_id="garden_studio", semantic_group="rail.right"), category="top", product_id=SHIRT)
    with pytest.raises(ValidationFailed, match="unknown room"):
        parse_placement(body(room_template_id="penthouse"), category="top", product_id=SHIRT)
    for stale_revision in ("original-v0", "original-v1"):
        with pytest.raises(ValidationFailed, match="reload the room") as e:
            parse_placement(body(asset_revision=stale_revision), category="top", product_id=SHIRT)
        assert e.value.extra["current_asset_revision"] == "original-shelves-v2"
    with pytest.raises(ValidationFailed):
        parse_placement(body(owner_id="x"), category="top", product_id=SHIRT)  # no extra fields


def test_unplaced_tray_has_no_transform():
    p = parse_placement({"room_template_id": "walnut_atelier", "semantic_group": None, "asset_revision": "original-shelves-v2"}, category="top", product_id=None)
    assert not p.placed and p.position is None
    with pytest.raises(ValidationFailed):
        parse_placement({"room_template_id": "walnut_atelier", "semantic_group": None, "slot_id": "1", "asset_revision": "original-shelves-v2"}, category="top", product_id=None)


def test_batch_slot_uniqueness():
    p1 = parse_placement(body(), category="top", product_id=SHIRT)
    with pytest.raises(ValidationFailed, match="same slot"):
        check_unique_slots([("a", p1), ("b", p1)])
    check_unique_slots([("a", p1), ("b", parse_placement(body(slot_id="4", position_meters=list(ROOMS["walnut_atelier"].groups["rail.left"].slot_position("4"))), category="top", product_id=SHIRT))])


def test_theme_remap_is_deterministic_and_keeps_semantics():
    q = (0.0, 0.0, 0.0, 1.0)
    current = [("i3", "rail.right", "2", 1.0, q), ("i1", "rail.left", "3", 1.1, q), ("i2", "shelf.shoes", "7", 1.0, q), ("i4", "stand.outfit", "0", 1.0, q)]
    a = remap_theme(current, "garden_studio")
    b = remap_theme(list(reversed(current)), "garden_studio")
    assert a == b
    by = {e.item_id: e for e in a}
    garden = ROOMS["garden_studio"]
    assert by["i1"].to.semantic_group == "rail.left" and by["i1"].to.position == garden.groups["rail.left"].slot_position("3")
    assert by["i1"].to.uniform_scale == 1.1
    assert by["i2"].to.semantic_group == "shelf.shoes" and by["i2"].to.position == garden.groups["shelf.shoes"].slot_position("7")
    assert not by["i3"].to.placed and not by["i4"].to.placed  # garden has no rail.right / stand.outfit → Unplaced tray


def _spatial_manifest_dir():
    d = os.environ.get("BRANDME_SPATIAL_MANIFEST_DIR") or str(REPO / "brandme-frontend/public/demo")
    return Path(d) if (Path(d) / "rooms" / "walnut_atelier" / "manifest.json").exists() else None


@pytest.mark.skipif(_spatial_manifest_dir() is None, reason="spatial-lane room manifests not present on this branch; consistency check NOT RUN")
def test_server_room_templates_match_spatial_manifests():
    base = _spatial_manifest_dir()
    for room_id, tpl in ROOMS.items():
        m = json.loads((base / "rooms" / room_id / "manifest.json").read_text())
        assert m["revision"] == tpl.revision
        for axis in range(3):
            assert m["collisionBounds"]["min"][axis] == pytest.approx(tpl.bounds_min[axis], abs=1e-4)
            assert m["collisionBounds"]["max"][axis] == pytest.approx(tpl.bounds_max[axis], abs=1e-4)
        groups = {g["id"]: g for g in m["groups"]}
        assert set(groups) == set(tpl.groups), room_id
        for gid, g in groups.items():
            t = tpl.groups[gid]
            assert list(g["center"]) == pytest.approx(list(t.center)) and g["capacity"] == t.capacity
            assert g["pitch"] == pytest.approx(t.pitch) and g["width"] == pytest.approx(t.width)
