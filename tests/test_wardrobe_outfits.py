"""Outfits, friend proposals and packing (BM-WARD-006, BM-WARD-007)."""

import uuid
from datetime import datetime, timezone

import pytest

from brandme_core.domains.persona.kernel import (
    DetailedInvalidTransition,
    DetailedVersionConflict,
    FixedClock,
    NotFound,
    ValidationFailed,
    member_principal,
)
from brandme_core.domains.wardrobe.outfits import OutfitService
from brandme_core.domains.wardrobe.service import WardrobeService
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def key():
    return "k-" + uuid.uuid4().hex


@pytest.fixture
def world(spanner_db):
    owner = member_principal(insert_member(spanner_db), MEMBER_SCOPES)
    friend = member_principal(insert_member(spanner_db), MEMBER_SCOPES)
    stranger = member_principal(insert_member(spanner_db), MEMBER_SCOPES)
    w = WardrobeService(spanner_db, clock=FixedClock(NOW))
    items = [w.create_items(owner, {"source": "manual", "title": t, "category": c}, key())["items"][0]["id"]
             for t, c in (("Shirt", "top"), ("Trousers", "bottom"), ("Sneakers", "shoes"), ("Jacket", "outerwear"))]
    friends = {(owner.member_id, friend.member_id)}
    outfits = OutfitService(spanner_db, clock=FixedClock(NOW), proposal_policy=lambda _t, o, p: (o, p) in friends)
    return owner, friend, stranger, items, outfits, w


def test_versions_are_immutable_and_proposals_keep_attribution(world, spanner_db):
    owner, friend, stranger, items, outfits, _ = world
    o = outfits.create_outfit(owner, {"title": "Work Monday", "item_refs": items[:3], "occasion": "work"}, key())
    oid = o["outfit_id"]
    assert o["head_version"] == "1" and o["head"]["author_member_id"] == owner.member_id
    with pytest.raises(NotFound):  # not a friend: same 404 as a missing outfit
        outfits.propose(stranger, oid, {"base_version": "1", "item_refs": items[1:]}, key())
    with pytest.raises(DetailedInvalidTransition):
        outfits.propose(owner, oid, {"base_version": "1", "item_refs": items[1:]}, key())
    prop = outfits.propose(friend, oid, {"base_version": "1", "item_refs": [items[0], items[1], items[3]], "notes": "Add the jacket"}, key())
    with pytest.raises(DetailedInvalidTransition) as e:  # same content again
        outfits.propose(friend, oid, {"base_version": "1", "item_refs": [items[3], items[0], items[1]], "layer_order": [items[0], items[1], items[3]]}, key())
    assert e.value.code == "duplicate_proposal"
    # The friend's proposal did not touch the owner's outfit.
    assert outfits.get_outfit(owner, oid)["head_version"] == "1"
    with pytest.raises(DetailedVersionConflict):
        outfits.decide_proposal(owner, oid, prop["proposal_id"], "accept", '"0"')
    acc = outfits.decide_proposal(owner, oid, prop["proposal_id"], "accept", '"1"')
    assert acc == {"proposal_id": prop["proposal_id"], "state": "accepted", "accepted_version": "2", "author_member_id": friend.member_id}
    full = outfits.get_outfit(owner, oid)
    v1, v2 = full["versions"]
    assert v1["item_refs"] == items[:3] and v1["author_member_id"] == owner.member_id  # original preserved
    assert v2["author_member_id"] == friend.member_id and v2["source_proposal_id"] == prop["proposal_id"]
    assert full["head_version"] == "2"
    with pytest.raises(DetailedInvalidTransition):
        outfits.decide_proposal(owner, oid, prop["proposal_id"], "accept", '"2"')  # cannot accept twice
    assert count(spanner_db, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id=@o AND event_type='outfit.proposal.accepted'", o=oid) == 1
    v3 = outfits.create_version(owner, oid, '"2"', {"item_refs": items[:2], "notes": "lighter"})
    assert v3["head_version"] == "3" and [v["version_no"] for v in v3["versions"]] == ["1", "2", "3"]


def test_outfit_items_must_be_the_owners_active_items(world, spanner_db):
    owner, friend, _s, items, outfits, w = world
    other_item = w.create_items(friend, {"source": "manual", "title": "Not yours", "category": "top"}, key())["items"][0]["id"]
    with pytest.raises(ValidationFailed) as e:
        outfits.create_outfit(owner, {"title": "x", "item_refs": [items[0], other_item]}, key())
    assert e.value.extra["missing_item_refs"] == [other_item]
    with pytest.raises(ValidationFailed):
        outfits.create_outfit(owner, {"title": "x", "item_refs": [items[0]], "layer_order": [items[1]]}, key())


def test_care_and_packing_persist_privately(world, spanner_db):
    """BM-WARD-007: care/packing states persist without changing provenance or leaking trip details."""
    owner, _f, _s, items, outfits, w = world
    o = outfits.create_outfit(owner, {"title": "Trip look", "item_refs": items[:2]}, key())
    pl = outfits.create_packing_list(owner, {"title": "Lisbon", "starts_on": "2026-11-02", "ends_on": "2026-11-06",
                                             "entries": [{"outfit_id": o["outfit_id"]}, {"item_id": items[2], "quantity": 2}]}, key())
    e = pl["entries"][1]["entry_id"]
    upd = outfits.set_packing_entry_state(owner, pl["list_id"], e, "packed", '"1"')
    assert upd["version"] == "2"
    got = outfits.get_packing_list(owner, pl["list_id"])
    assert got["starts_on"] == "2026-11-02" and [x["state"] for x in got["entries"] if x["entry_id"] == e] == ["packed"]
    with pytest.raises(NotFound):
        outfits.get_packing_list(member_principal(insert_member(spanner_db), MEMBER_SCOPES), pl["list_id"])
    w.patch_item(owner, items[2], '"1"', {"care_state": "needs_care"})
    assert w.get_item(owner, items[2])["claim_level"] == "self_reported"
    with spanner_db.snapshot() as s:
        payloads = [str(r[0]) for r in s.execute_sql(
            "SELECT TO_JSON_STRING(payload) FROM OutboxEvents WHERE actor_ref=@a",
            params={"a": f"member:{owner.member_id}"},
            param_types={"a": __import__("google.cloud.spanner_v1", fromlist=["param_types"]).param_types.STRING})]
    assert payloads and not any("2026-11" in p or "Lisbon" in p for p in payloads)  # trip details never in events
    with pytest.raises(ValidationFailed):
        outfits.create_packing_list(owner, {"title": "x", "starts_on": "2026-11-06", "ends_on": "2026-11-02"}, key())


def test_proposal_base_version_must_exist(world):
    owner, friend, _, items, outfits, _ = world
    o = outfits.create_outfit(owner, {"title": "Look", "item_refs": items[:2]}, key())
    for base in ("0", "2"):
        with pytest.raises(ValidationFailed):
            outfits.propose(friend, o["outfit_id"], {"base_version": base, "item_refs": items[:3]}, key())
    assert outfits.propose(friend, o["outfit_id"], {"base_version": "1", "item_refs": items[:3]}, key())["proposal_id"]


def test_substitutes_must_be_the_owners_active_items(world, spanner_db):
    owner, friend, _, items, outfits, w = world
    theirs = w.create_items(friend, {"source": "manual", "title": "Borrowed", "category": "top"}, key())["items"][0]["id"]
    for alt in (theirs, str(uuid.uuid4())):
        with pytest.raises(ValidationFailed):
            outfits.create_outfit(owner, {"title": "Look", "item_refs": items[:2], "substitutes": {items[0]: [alt]}}, key())
    o = outfits.create_outfit(owner, {"title": "Look", "item_refs": items[:2], "substitutes": {items[0]: [items[3]]}}, key())
    with pytest.raises(ValidationFailed):  # also on a new version
        outfits.create_version(owner, o["outfit_id"], '"1"', {"item_refs": items[:2], "substitutes": {items[1]: [theirs]}})
