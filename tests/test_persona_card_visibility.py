"""Ultra plan 02 item 6 on the Spanner emulator: per-piece closet visibility
(owner-curated, sliding scale, private by default) and the living persona card
(recomposed on trigger events, backfilled daily, shown only as its owner allows)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from brandme_core.domains.persona.card import PersonaCardConsumer, PersonaCardService
from brandme_core.domains.persona.deletion import delete_category as persona_delete
from brandme_core.domains.rewards.deletion import delete_category as rewards_delete
from brandme_core.domains.persona.kernel import NotFound, ValidationFailed, member_principal, run_txn
from brandme_core.domains.persona.service import PersonaService
from brandme_core.domains.social.relationships import RelationshipService
from brandme_core.domains.wardrobe.service import WardrobeService
from brandme_core.domains.wardrobe.visibility import ClosetVisibilityService
from brandme_core.events import EventEnvelope
from brandme_core.domains.media.store import MemoryMediaStore
from brandme_core.domains.persona.lane import register_consumer_domains
from brandme_core.domains.privacy import deletion as pd
from brandme_core.domains.privacy.privacy import MyDataService
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401
from test_persona_lane_mydata import MemoryObjectStore

PIECE = {"item_id", "title", "category", "house_ref", "detail"}
STORY = PIECE | {"showcase_note", "worn_count"}
FULL = STORY | {"price", "in_closet_since", "verified"}


def key():
    return "k-" + uuid.uuid4().hex


def person(db):
    return member_principal(insert_member(db), MEMBER_SCOPES)


def item(db, who, title, **kw):
    body = {"source": "manual", "title": title, "category": "top", **kw}
    return WardrobeService(db).create_items(who, body, key())["items"][0]["id"]


@pytest.fixture
def people(spanner_db):
    owner, friend, stranger, blocked = (person(spanner_db) for _ in range(4))
    rel = RelationshipService(spanner_db)
    for f in (friend, blocked):
        rel.accept(f, rel.request(owner, f.member_id)["relationship_id"])
    rel.block(owner, blocked.member_id)
    return owner, friend, stranger, blocked


def test_closet_visibility_is_owner_curated_on_a_sliding_scale(spanner_db, people):
    db = spanner_db
    owner, friend, stranger, blocked = people
    a = item(db, owner, "Linen overshirt", price={"amount_minor": "18000", "currency": "USD"}, user_notes="private note", size_label="M")
    b = item(db, owner, "Field jacket")
    hidden = item(db, owner, "Old tee")
    wish = WardrobeService(db).create_items(owner, {"source": "catalog", "title": "Wanted", "category": "top", "product_id": str(uuid.uuid4())},
                                            key())["items"][0]["id"]
    vis = ClosetVisibilityService(db)
    assert vis.closet(friend, owner.member_id)["items"] == []  # private by default
    assert vis.set_visibility(owner, a, {"visibility": "friends", "detail": "full", "showcase_note": "Worn every summer"})["version"] == "2"
    vis.set_visibility(owner, b, {"visibility": "members", "detail": "story"})
    for bad_item, bad in ((b, {"visibility": "members", "detail": "full"}), (wish, {"visibility": "friends"}),
                          (hidden, {"visibility": "private", "detail": "piece"}), (hidden, {"visibility": "everyone"}),
                          (hidden, {"visibility": "friends", "price": "hide"}), (hidden, {"visibility": "friends", "showcase_note": "x" * 281})):
        with pytest.raises(ValidationFailed):
            vis.set_visibility(owner, bad_item, bad)
    with pytest.raises(ValidationFailed):
        vis.set_visibility(member_principal(owner.member_id, MEMBER_SCOPES, delegation_id=str(uuid.uuid4())), hidden, {"visibility": "members"})
    with pytest.raises(NotFound):
        vis.set_visibility(friend, a, {"visibility": "private"})  # only the owner

    seen = {i["item_id"]: i for i in vis.closet(friend, owner.member_id)["items"]}
    assert set(seen) == {a, b}
    assert set(seen[a]) == FULL and seen[a]["price"] == {"minor": 18000, "currency": "USD"} and seen[a]["showcase_note"] == "Worn every summer"
    assert set(seen[b]) == STORY
    strangers = vis.closet(stranger, owner.member_id)
    assert strangers["relation"] == "members" and [i["item_id"] for i in strangers["items"]] == [b] and set(strangers["items"][0]) == STORY
    assert vis.closet(blocked, owner.member_id) == {"member_id": owner.member_id, "items": [], "relation": None}
    assert {i["item_id"] for i in vis.closet(owner, owner.member_id)["items"]} == {a, b}  # the owner previews what they show
    assert "private note" not in str(seen) and "M" not in [v for i in seen.values() for v in i.values() if isinstance(v, str)]
    # Back to private: gone at once; the change is an item update other consumers see.
    vis.set_visibility(owner, a, {"visibility": "private"})
    assert [i["item_id"] for i in vis.closet(friend, owner.member_id)["items"]] == [b]
    assert count(db, "SELECT COUNT(*) FROM OutboxEvents WHERE event_type='wardrobe.item.updated' AND JSON_VALUE(payload, '$.item_id')=@i "
                     "AND STRPOS(TO_JSON_STRING(payload), 'visibility') > 0", i=a) == 2


def test_persona_card_composes_respects_visibility_and_recomposes_on_triggers(spanner_db, people):
    db = spanner_db
    owner, friend, stranger, blocked = people
    persona = PersonaService(db)
    persona.patch(owner, '"0"', {"changes": [{"axis": "expression", "value": 90, "locked": False}, {"axis": "color", "value": 15, "locked": False},
                                             {"axis": "detail", "value": 50, "locked": False}, {"axis": "novelty", "value": 80, "locked": False}],
                                 "axis_settings": {"novelty": {"hidden": True}}, "client_revision": "c"})
    shown = item(db, owner, "Signature coat")
    private = item(db, owner, "Private piece")
    ClosetVisibilityService(db).set_visibility(owner, shown, {"visibility": "friends", "detail": "piece"})
    run_txn(db, lambda t: t.insert("HouseStandings", columns=("member_id", "house_ref", "tier", "computed_at", "run_id"),
                                   values=[(owner.member_id, "atelier-card", "top_5", datetime.now(timezone.utc), str(uuid.uuid4()))]))
    cards = PersonaCardService(db, persona=persona)
    for bad in ({"highlight_item_ids": [item(db, friend, "Not mine")]}, {"highlight_item_ids": [shown] * 2}, {"audience": "everyone"},
                {"highlight_item_ids": [str(uuid.uuid4()) for _ in range(7)]}, {"show_standings": "yes"}, {"tagline": "hi"}):
        with pytest.raises(ValidationFailed):
            cards.settings(owner, bad)
    out = cards.settings(owner, {"highlight_item_ids": [shown, private]})
    assert out["audience"] == "friends" and out["show_standings"] is False
    assert [t["label"] for t in out["card"]["taste"]] == ["Expressive", "Neutral"]  # strongest first; mid-band and hidden axes never shown
    assert out["card"]["standings"] == []  # off until the member turns it on

    as_friend = cards.view(friend, owner.member_id)["card"]
    assert [h["item_id"] for h in as_friend["highlights"]] == [shown]  # the private piece stays private on the card too
    for outsider in (stranger, blocked):
        with pytest.raises(NotFound):
            cards.view(outsider, owner.member_id)
    cards.settings(owner, {"audience": "members", "show_standings": True})
    as_stranger = cards.view(stranger, owner.member_id)["card"]
    assert as_stranger["highlights"] == [] and as_stranger["standings"] == [{"house_ref": "atelier-card", "tier": "top_5"}]
    cards.settings(owner, {"audience": "private"})
    with pytest.raises(NotFound):
        cards.view(friend, owner.member_id)
    assert cards.mine(owner)["card"]["highlights"][0]["item_id"] == shown

    # A trigger event marks the card stale; the jobs pass recomposes it.
    persona.patch(owner, '"1"', {"changes": [{"axis": "color", "value": 95, "locked": False}], "client_revision": "c2"})
    ev = EventEnvelope(event_type="persona.updated", schema_version="1", aggregate_type="persona", aggregate_id=owner.member_id, aggregate_version=2,
                       environment="development", actor_ref="service:test", correlation_id=str(uuid.uuid4()), privacy_class="member_private",
                       payload={"member_id": owner.member_id, "profile_version": "2", "change_kind": "declared", "changed_axes": ["color"]})
    assert PersonaCardConsumer(db).handle(ev) == {"status": "card_marked_stale"}
    assert cards.mine(owner)["recomposing"] is True
    assert cards.recompose_due()["stale"] >= 1
    mine = cards.mine(owner)
    assert mine["recomposing"] is False and "Colorful" in [t["label"] for t in mine["card"]["taste"]]
    # Members with a profile but no card get one from the daily backfill.
    newcomer = person(db)
    persona.patch(newcomer, '"0"', {"changes": [{"axis": "structure", "value": 10, "locked": False}], "client_revision": "n"})
    assert count(db, "SELECT COUNT(*) FROM PersonaCards WHERE member_id=@m", m=newcomer.member_id) == 0
    assert cards.recompose_due()["created"] >= 1
    assert cards.view(newcomer, newcomer.member_id)["card"]["taste"] == [{"axis": "structure", "label": "Structured", "strength": 80}]


@pytest.mark.parametrize("category,field", [("persona.declared", "taste"), ("persona.inferred", "taste"), ("persona.evidence", "taste"),
                                            ("rewards.badges", "badges"), ("rewards.standings", "standings")])
def test_deleting_a_source_category_scrubs_the_cards_copy_at_once(spanner_db, people, category, field):
    """The card stores composed copies of taste, badges and standings: a completed deletion must not leave them readable."""
    db = spanner_db
    owner, friend, *_ = people
    persona = PersonaService(db)
    persona.patch(owner, '"0"', {"changes": [{"axis": "expression", "value": 90, "locked": False}], "client_revision": "c"})
    run_txn(db, lambda t: (t.insert("HouseStandings", columns=("member_id", "house_ref", "tier", "computed_at", "run_id"),
                                    values=[(owner.member_id, "atelier-scrub", "top_5", datetime.now(timezone.utc), str(uuid.uuid4()))]),
                           t.insert("BadgeAwards", columns=("member_id", "badge_id", "criteria_version", "evidence_refs", "awarded_at"),
                                    values=[(owner.member_id, "closet_curator", 1, ["test"], datetime.now(timezone.utc))])))
    cards = PersonaCardService(db, persona=persona)
    composed = cards.settings(owner, {"show_standings": True})["card"]
    assert composed["taste"] and composed["badges"] and composed["standings"]
    delete = persona_delete if category.startswith("persona.") else rewards_delete
    run_txn(db, lambda t: delete(t, owner.member_id, category))
    seen = cards.view(friend, owner.member_id)["card"]
    assert seen[field] == [] and cards.mine(owner)["card"][field] == []
    assert all(seen[f] for f in ("taste", "badges", "standings") if f != field)  # only the deleted source is scrubbed
    assert count(db, "SELECT COUNT(*) FROM PersonaCards WHERE member_id=@m AND stale_since IS NOT NULL", m=owner.member_id) == 1


def test_a_card_deleted_through_my_data_is_not_recreated_behind_the_members_back(spanner_db, people):
    db = spanner_db
    owner, friend, *_ = people
    persona = PersonaService(db)
    persona.patch(owner, '"0"', {"changes": [{"axis": "expression", "value": 90, "locked": False}], "client_revision": "c"})
    cards = PersonaCardService(db, persona=persona)
    cards.settings(owner, {"audience": "private"})
    reg = pd.PrivacyRegistry()
    register_consumer_domains(reg, database=db, media_store=MemoryMediaStore())
    svc = MyDataService(db, MemoryObjectStore(), reg, environment="development")
    svc.run_deletion(svc.request_deletion(owner.member_id, datetime.now(timezone.utc), categories=["persona.card"]))
    assert count(db, "SELECT COUNT(*) FROM PersonaCards WHERE member_id=@m", m=owner.member_id) == 0
    # The jobs pass (backfill or a trigger) does not bring it back.
    assert cards.recompose(owner.member_id, trigger="backfill") is None and cards.recompose(owner.member_id, trigger="trigger") is None
    assert count(db, "SELECT COUNT(*) FROM PersonaCards WHERE member_id=@m", m=owner.member_id) == 0
    # The backfill never even picks the deleted card, so deleted cards cannot crowd out new members.
    picked = []
    spy = PersonaCardService(db, persona=persona)
    spy.recompose = lambda m, trigger: picked.append(m)
    spy.recompose_due(limit=1_000_000)
    assert owner.member_id not in picked
    # The member's own visit does, private until they choose to share it again.
    assert cards.mine(owner)["audience"] == "private"
    with pytest.raises(NotFound):
        cards.view(friend, owner.member_id)
    # So does a settings change that names no audience.
    svc.run_deletion(svc.request_deletion(owner.member_id, datetime.now(timezone.utc), categories=["persona.card"]))
    assert cards.settings(owner, {"show_standings": False})["audience"] == "private"
