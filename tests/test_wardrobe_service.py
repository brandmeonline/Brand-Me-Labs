"""Wardrobe service on the Spanner emulator: BM-WARD-001..005, 007, 008 and
the placement contract under real transactions/unique indexes."""

import json
import math
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import pytest

from brandme_core.domains.persona.kernel import (
    DetailedInvalidTransition,
    DetailedVersionConflict,
    FixedClock,
    IdempotencyConflict,
    NotFound,
    ValidationFailed,
    member_principal,
)
from brandme_core.domains.persona.recommender import Candidate
from brandme_core.domains.persona.service import PersonaService
from brandme_core.domains.wardrobe.rooms import ROOMS
from brandme_core.domains.wardrobe.service import WardrobeService
from brandme_core.events import EventEnvelope
from test_persona_harness import MEMBER_SCOPES, AbortOnceDB, count, insert_member, spanner_db  # noqa: F401

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
SHIRT = "a4036cb0-7ab2-54b5-9238-ee5ffb378771"
TROUSERS = "6b4ee94a-4998-55d8-8298-c8f81a40b7aa"
SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "docs/design/brandme/contracts/domain.schema.json").read_text())
WALNUT = ROOMS["walnut_atelier"]


def validate(defname, obj):
    schema = {"$schema": SCHEMA["$schema"], "$defs": SCHEMA["$defs"], "$ref": f"#/$defs/{defname}"}
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(obj)


def key():
    return "k-" + uuid.uuid4().hex


def slot(group, s, room=WALNUT, **kw):
    g = room.groups[group]
    b = {"room_template_id": room.room_id, "semantic_group": group, "slot_id": s, "position_meters": list(g.slot_position(s)),
         "rotation_quaternion": [0, 0, 0, 1], "uniform_scale": 1.0, "asset_revision": room.revision}
    b.update(kw)
    return b


@pytest.fixture
def svc(spanner_db):
    return WardrobeService(spanner_db, clock=FixedClock(NOW))


@pytest.fixture
def me(spanner_db):
    return member_principal(insert_member(spanner_db), MEMBER_SCOPES)


def manual(svc, me, title="Linen shirt", category="top", **kw):
    return svc.create_items(me, {"source": "manual", "title": title, "category": category, "color_family": "neutral", **kw}, key())["items"][0]


def test_intake_paths_keep_source_collection_and_claim(svc, me):
    """BM-WARD-001 / BM-WARD-002."""
    m = manual(svc, me)
    c = svc.create_items(me, {"source": "catalog", "title": "Field Linen Overshirt", "category": "top", "product_id": SHIRT, "variant_ref": "v-M"}, key())["items"][0]
    r = svc.create_items(me, {"source": "receipt", "title": "Tee", "category": "top", "receipt": {"receipt_ref": "R-9", "line_ref": "2", "units": 2}}, key())["items"]
    assert (m["collection"], m["claim_level"], m["acquisition_source"]) == ("owned", "self_reported", "manual")
    assert (c["collection"], c["claim_level"], c["product_id"], c["variant_ref"]) == ("want", "self_reported", SHIRT, "v-M")
    assert [x["unit_index"] for x in r] == [0, 1] and len({x["id"] for x in r}) == 2
    assert all(x["evidence_status"] == "receipt_pending_review" and x["claim_level"] == "self_reported" for x in r)
    for x in (m, c, *r):
        validate("WardrobeItem", {k: x[k] for k in ("id", "member_id", "title", "collection", "product_id", "asset_instance_id", "claim_level", "version")})
    assert svc.accept_receipt_evidence(me.member_id, "R-9#2") == 2
    assert {svc.get_item(me, x["id"])["claim_level"] for x in r} == {"receipt_backed"}
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.put_placement(me, c["id"], '"0"', slot("rail.left", "0"))  # a wishlist item never enters the room
    assert e.value.code == "not_placeable"


def test_lost_response_retry_creates_exactly_one_item_and_placement(svc, me, spanner_db):
    """BM-WARD-003: same Idempotency-Key replays; an ABORTED retry inside also commits once."""
    k = key()
    body = {"source": "manual", "title": "Overshirt", "category": "top", "placement": slot("rail.left", "2")}
    first = svc.create_items(me, body, k)
    second = svc.create_items(me, body, k)
    assert first == second
    item_id = first["items"][0]["id"]
    assert first["items"][0]["placement"]["slot_id"] == "2"
    assert count(spanner_db, "SELECT COUNT(*) FROM WardrobeItems WHERE member_id=@m", m=me.member_id) == 1
    assert count(spanner_db, "SELECT COUNT(*) FROM ClosetPlacements WHERE member_id=@m", m=me.member_id) == 1
    assert count(spanner_db, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id=@i AND event_type='wardrobe.item.created'", i=item_id) == 1
    with pytest.raises(IdempotencyConflict):
        svc.create_items(me, {**body, "title": "Different"}, k)
    flaky = AbortOnceDB(spanner_db)
    fsvc = WardrobeService(flaky, clock=FixedClock(NOW))
    out = fsvc.create_items(me, {"source": "manual", "title": "Tee", "category": "top"}, key())
    assert flaky.attempts == 2
    assert count(spanner_db, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id=@i", i=out["items"][0]["id"]) == 1


def test_duplicates_are_member_controlled(svc, me):
    """BM-WARD-004."""
    a = svc.create_items(me, {"source": "catalog", "title": "Overshirt", "category": "top", "product_id": SHIRT, "variant_ref": "v-M", "collection": "owned"}, key())
    b = svc.create_items(me, {"source": "catalog", "title": "Overshirt", "category": "top", "product_id": SHIRT, "variant_ref": "v-M", "collection": "owned"}, key())
    a_id, b_id = a["items"][0]["id"], b["items"][0]["id"]
    assert b["duplicate_candidates"] == [{"item_id": a_id, "reason": "same_variant", "strength": "suggestion", "mergeable": True}]
    assert svc.get_item(me, b_id)["collection"] == "owned"  # nothing merged automatically
    kept = svc.resolve_duplicate(me, b_id, a_id, "keep_both")
    assert kept["result"] == "kept_both"
    merged = svc.resolve_duplicate(me, b_id, a_id, "merge")
    assert merged["items"][0]["collection"] == "archive" and merged["items"][0]["duplicate_of"] == a_id
    restored = svc.archive_item(me, b_id, f'"{merged["items"][0]["version"]}"', archive=False)
    assert restored["collection"] == "owned" and restored["duplicate_of"] is None
    # distinct physical units never merge
    s1 = svc.create_items(me, {"source": "manual", "title": "Tagged A", "category": "top", "tag_serial": "SER-AAAA-1"}, key())["items"][0]["id"]
    s2 = svc.create_items(me, {"source": "manual", "title": "Tagged B", "category": "top", "tag_serial": "SER-AAAA-2"}, key())["items"][0]["id"]
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.resolve_duplicate(me, s2, s1, "merge")
    assert e.value.code == "distinct_physical_instances"
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.create_items(me, {"source": "manual", "title": "Again", "category": "top", "tag_serial": "ser-aaaa-1"}, key())
    assert e.value.code == "duplicate_physical_instance" and e.value.extra["existing_item_id"] == s1


def test_placement_versioning_slot_uniqueness_and_validation(svc, me, spanner_db):
    a = manual(svc, me, "A")["id"]
    b = manual(svc, me, "B")["id"]
    p = svc.put_placement(me, a, '"0"', slot("rail.left", "5"))
    validate("ClosetPlacement", p)
    assert p["version"] == "1"
    with pytest.raises(DetailedVersionConflict) as e:
        svc.put_placement(me, a, '"0"', slot("rail.left", "6"))
    assert e.value.extra["current_placement"]["slot_id"] == "5"
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.put_placement(me, b, '"0"', slot("rail.left", "5"))
    assert e.value.code == "slot_occupied" and e.value.extra["occupant_item_id"] == a
    for bad in (dict(rotation_quaternion=[0, 0, 0, math.nan]), dict(position_meters=[math.inf, 1.75, -0.65]), dict(uniform_scale=3.0),
                dict(rotation_quaternion=[0, 0, 0.5, 0.5])):
        with pytest.raises(ValidationFailed):
            svc.put_placement(me, b, '"0"', slot("rail.left", "6", **bad))
    moved = svc.put_placement(me, a, '"1"', slot("rail.left", "6", rotation_quaternion=[0, -0.7071068, 0, -0.7071068]))
    assert moved["version"] == "2" and moved["rotation_quaternion"][3] > 0  # canonical w >= 0, normalized
    assert abs(sum(c * c for c in moved["rotation_quaternion"]) - 1) < 1e-9
    other = member_principal(insert_member(spanner_db), MEMBER_SCOPES)
    with pytest.raises(NotFound):
        svc.put_placement(other, a, '"2"', slot("rail.left", "1"))  # not their item


def test_concurrent_moves_into_one_slot_commit_once(svc, me):
    ids = [manual(svc, me, f"C{i}")["id"] for i in range(4)]
    ok, errs = [], []

    def go(i):
        try:
            ok.append(svc.put_placement(me, i, '"0"', slot("rail.right", "7")))
        except DetailedInvalidTransition as e:
            errs.append(e.code)

    ts = [threading.Thread(target=go, args=(i,)) for i in ids]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(ok) == 1 and errs == ["slot_occupied"] * 3


def test_batch_swap_is_atomic_and_bounded(svc, me):
    a, b = manual(svc, me, "A")["id"], manual(svc, me, "B")["id"]
    svc.put_placement(me, a, '"0"', slot("rail.left", "0"))
    svc.put_placement(me, b, '"0"', slot("rail.left", "1"))
    out = svc.batch_placements(me, {"placements": [
        {"wardrobe_item_id": a, "version": "1", **slot("rail.left", "1")},
        {"wardrobe_item_id": b, "version": "1", **slot("rail.left", "0")},
    ]}, key())
    assert {p["wardrobe_item_id"]: p["slot_id"] for p in out["placements"]} == {a: "1", b: "0"}
    with pytest.raises(ValidationFailed, match="same slot"):
        svc.batch_placements(me, {"placements": [
            {"wardrobe_item_id": a, "version": "2", **slot("rail.left", "3")},
            {"wardrobe_item_id": b, "version": "2", **slot("rail.left", "3")},
        ]}, key())
    with pytest.raises(ValidationFailed):
        svc.batch_placements(me, {"placements": [{"wardrobe_item_id": str(uuid.uuid4()), "version": "0", **slot("rail.left", "0")}] * 51}, key())
    assert svc.get_item(me, a)["placement"]["slot_id"] == "1"  # failed batch changed nothing


def test_theme_change_remaps_semantically_and_survives_reload(svc, me, spanner_db):
    left, right, shoes = manual(svc, me, "L")["id"], manual(svc, me, "R")["id"], manual(svc, me, "S", category="shoes")["id"]
    svc.put_placement(me, left, '"0"', slot("rail.left", "4"))
    svc.put_placement(me, right, '"0"', slot("rail.right", "2"))
    svc.put_placement(me, shoes, '"0"', slot("shelf.shoes", "6"))
    preview = svc.set_theme(me, None, "garden_studio", preview=True)
    assert preview["moved_to_unplaced"] == [right] and sorted(preview["kept"]) == sorted([left, shoes])
    assert svc.get_layout(me)["room_template_id"] == "walnut_atelier"  # preview wrote nothing
    with pytest.raises(DetailedVersionConflict):
        svc.set_theme(me, '"0"', "garden_studio")
    done = svc.set_theme(me, '"1"', "garden_studio")
    assert done["layout_version"] == "2"
    fresh = WardrobeService(spanner_db, clock=FixedClock(NOW)).get_layout(me)  # "reload"
    garden = ROOMS["garden_studio"]
    by = {p["wardrobe_item_id"]: p for p in fresh["placements"]}
    assert fresh["room_template_id"] == "garden_studio" and [u["wardrobe_item_id"] for u in fresh["unplaced"]] == [right]
    assert by[left]["slot_id"] == "4" and by[left]["position_meters"] == list(garden.groups["rail.left"].slot_position("4"))
    assert by[shoes]["position_meters"] == list(garden.groups["shelf.shoes"].slot_position("6"))
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.put_placement(me, right, f'"{fresh["unplaced"][0]["version"]}"', slot("rail.left", "0"))  # wrong room now
    assert e.value.code == "room_mismatch"
    svc.put_placement(me, right, f'"{fresh["unplaced"][0]["version"]}"', slot("rail.left", "0", room=garden))


def test_member_edits_cannot_rewrite_facts_or_ownership(svc, me):
    item = manual(svc, me)
    for bad in ({"claim_level": "issuer_attested"}, {"acquisition_source": "order"}, {"price": {"amount_minor": "1", "currency": "USD"}},
                {"collection": "on_the_way"}, {"owner_id": "x"}):
        with pytest.raises(ValidationFailed):
            svc.patch_item(me, item["id"], '"1"', bad)
    with pytest.raises(DetailedVersionConflict):
        svc.patch_item(me, item["id"], '"9"', {"title": "x"})
    out = svc.patch_item(me, item["id"], '"1"', {"care_state": "needs_care", "care_notes": "Hand wash"})
    assert out["care_state"] == "needs_care" and out["claim_level"] == "self_reported" and out["version"] == "2"


def _order_event(member_id, order_id, version, lines, status="accepted"):
    return EventEnvelope(
        event_type="commerce.order.observed", schema_version="1", aggregate_type="Order", aggregate_id=order_id,
        aggregate_version=version, environment="development", actor_ref="service:commerce", correlation_id=str(uuid.uuid4()),
        privacy_class="member_private",
        payload={"order_id": order_id, "member_id": member_id, "order_status": status, "lines": lines},
    )


def test_partial_order_then_return_changes_only_those_units(svc, me, spanner_db):
    """BM-WARD-008."""
    order = str(uuid.uuid4())
    lookup = {"var-shirt": {"product_id": SHIRT, "title": "Field Linen Overshirt", "category": "top"}}
    svc = WardrobeService(spanner_db, clock=FixedClock(NOW), catalog_lookup=lookup.get)
    line = lambda o, d, r: [{"variant_id": "var-shirt", "source_variant_ref": "SKU-1", "ordered": o, "delivered": d, "returned": r},
                            {"variant_id": "var-unknown", "source_variant_ref": "SKU-2", "ordered": 1, "delivered": 0, "returned": 0}]
    e1 = _order_event(me.member_id, order, 1, line(3, 0, 0))
    assert svc.apply_order_observation(e1)["created"] == 4
    assert svc.apply_order_observation(e1) == {"status": "duplicate_delivery"}
    assert svc.apply_order_observation(_order_event(me.member_id, order, 2, line(3, 2, 0)))["updated"] == 2
    items = svc.list_items(me, limit=100)["items"]
    by = sorted((i["title"], i["unit_index"], i["collection"]) for i in items)
    assert by == [("Field Linen Overshirt", 0, "owned"), ("Field Linen Overshirt", 1, "owned"),
                  ("Field Linen Overshirt", 2, "on_the_way"), ("Item from your order", 0, "on_the_way")]
    unknown = next(i for i in items if i["title"] == "Item from your order")
    assert unknown["category"] is None and unknown["claim_level"] == "receipt_backed"  # never a guessed category
    unit0 = next(i for i in items if i["unit_index"] == 0 and i["product_id"] == SHIRT)
    svc.put_placement(me, unit0["id"], '"0"', slot("rail.left", "1"))
    res = svc.apply_order_observation(_order_event(me.member_id, order, 3, line(3, 2, 1)))
    assert res["updated"] == 1
    after = {i["id"]: i for i in svc.list_items(me, limit=100)["items"]}
    assert after[unit0["id"]]["collection"] == "archive" and after[unit0["id"]]["acquisition_status"] == "returned"
    assert svc.get_item(me, unit0["id"])["placement"] is None  # returned unit leaves the room
    assert sorted(i["collection"] for i in after.values() if i["product_id"] == SHIRT) == ["archive", "on_the_way", "owned"]
    stale = _order_event(me.member_id, order, 2, line(3, 3, 0))
    assert svc.apply_order_observation(stale) == {"status": "stale_version"}
    with pytest.raises(DetailedInvalidTransition):
        svc.archive_item(me, unit0["id"], f'"{after[unit0["id"]]["version"]}"', archive=False)  # returned cannot be restored


def test_500_item_closet_stays_organizable(svc, me, spanner_db):
    """BM-WARD-005 (functional half): 500 items paginate completely with filters/search."""
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

    cats = ["top", "bottom", "shoes", "accessory", "outerwear"]

    def bulk(t):
        rows = []
        for i in range(500):
            rows.append([me.member_id, str(uuid.uuid4()), f"Item {i:03d} {'linen' if i % 7 == 0 else 'wool'}", cats[i % 5],
                         "owned" if i % 4 else "want", "self_reported", "none", "manual", "declared", "clean", 0, 1, COMMIT_TIMESTAMP, COMMIT_TIMESTAMP])
        t.insert("WardrobeItems", columns=("member_id", "item_id", "title", "category", "collection", "claim_level", "evidence_status",
                                           "acquisition_source", "acquisition_status", "care_state", "worn_count", "version", "created_at", "updated_at"), values=rows)

    from brandme_core.domains.persona.kernel import run_txn

    run_txn(spanner_db, bulk)
    t0 = time.perf_counter()
    seen, cursor = [], None
    while True:
        page = svc.list_items(me, limit=100, cursor=cursor)
        seen += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    elapsed = time.perf_counter() - t0
    assert len(seen) == 500 and len(set(seen)) == 500
    assert len(svc.list_items(me, collection="want", limit=100)["items"]) == 100
    shoes = svc.list_items(me, category="shoes", limit=100)
    assert len(shoes["items"]) == 100 and all(i["category"] == "shoes" for i in shoes["items"])
    linen = [i for p in [svc.list_items(me, q="LINEN", limit=100)] for i in p["items"]]
    assert len(linen) == 72 and all("linen" in i["title"] for i in linen)
    print(f"\n500-item full pagination on emulator: {elapsed * 1000:.0f} ms (5 pages of 100)")


def test_persona_recommendations_cite_real_wardrobe_items(svc, me, spanner_db):
    trousers = svc.create_items(me, {"source": "manual", "title": "Cream trousers", "category": "bottom", "color_family": "neutral"}, key())["items"][0]
    sneakers = svc.create_items(me, {"source": "manual", "title": "White sneakers", "category": "shoes", "color_family": "neutral"}, key())["items"][0]
    want = svc.create_items(me, {"source": "catalog", "title": "Sneaker", "category": "shoes", "product_id": SHIRT, "color_family": "neutral"}, key())["items"][0]
    cands = [Candidate(SHIRT, "Field Linen Overshirt", "Demo", "top", "neutral", {"expression": 70}, price_minor=8900, currency="USD")]
    persona = PersonaService(spanner_db, clock=FixedClock(NOW), candidate_source=lambda _p: cands, wardrobe_source=svc.wardrobe_refs)
    persona.patch(me, '"0"', {"changes": [{"axis": "expression", "value": 72, "locked": True}], "client_revision": "x"})
    rec = persona.recommendations(me)["items"][0]
    reason = next(r for r in rec["reasons"] if r["feature"] == "wardrobe_compatibility")
    assert sorted(reason["evidence"]) == sorted([f"wardrobe_item:{trousers['id']}", f"wardrobe_item:{sneakers['id']}"])  # wishlist item not cited
    assert "Cream trousers" in reason["text"] and want["id"] not in json.dumps(rec)
