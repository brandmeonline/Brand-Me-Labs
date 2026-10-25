"""Ultra plan 02 items 2-4 on the Spanner emulator: the Now loop (asker windows,
the asker's why, the in-window comment thread, influence credit), Home = Flow,
and per-house loyalty standing with standing-gated house rewards."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from google.cloud.spanner_v1 import param_types

from brandme_core.domains.persona.kernel import (
    DetailedInvalidTransition,
    Forbidden,
    NotFound,
    RateLimited,
    ValidationFailed,
    member_principal,
    run_txn,
    service_principal,
)
from brandme_core.domains.persona.service import PersonaService
from brandme_core.domains.rewards.benefits import BenefitService
from brandme_core.domains.rewards.consumer import RewardsConsumer
from brandme_core.domains.rewards.service import RewardsService
from brandme_core.domains.rewards.standing import MIN_COHORT, StandingService, meets, tier_for
from brandme_core.domains.social.decisions import DecisionService
from brandme_core.domains.social.flow import FlowService, excitement, size_for
from brandme_core.domains.social.houses import CatalogHouses, HouseService, catalog_piece_exists, catalog_variant_lookup, house_ref_of
from brandme_core.domains.social.policy import COMMENTS_PER_AUTHOR
from brandme_core.domains.social.relationships import RelationshipService
from brandme_core.domains.wardrobe.service import WardrobeService
from brandme_core.events import EventEnvelope
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

OPS = frozenset({"moderation:admin"})
HOUSE_OPS = frozenset({"provider:admin"})
ISSUER = "repairer:atelier-north"
OUTBOX_COLS = ("event_id", "event_type", "schema_version", "aggregate_type", "aggregate_id", "aggregate_version", "environment",
               "actor_ref", "correlation_id", "causation_id", "privacy_class", "payload", "occurred_at")
VARIANT_COLS = ("provider_id", "merchant_id", "source_product_id", "source_variant_id", "variant_id", "brand", "title", "category",
                "product_url", "observed_price_minor", "observed_price_currency", "availability", "source_updated_at",
                "rights_policy_ref", "revision", "tombstoned", "first_seen_at", "last_ingested_at")


def key():
    return "k-" + uuid.uuid4().hex


def person(db, scopes=MEMBER_SCOPES):
    return member_principal(insert_member(db), scopes | {"rewards:write"})


def friends(db, a, *others):
    rel = RelationshipService(db)
    for o in others:
        rel.accept(o, rel.request(a, o.member_id)["relationship_id"])


def house(name):
    """A house of its own per test: the emulator database is shared by the whole session."""
    brand = f"{name} {uuid.uuid4().hex[:8]}"
    return brand, house_ref_of(brand)


def piece(db, brand, title, *, ago, price=12000, availability="in_stock", category="top"):
    """A catalog variant as the providers lane ingests it (fictional dev data)."""
    vid = str(uuid.uuid4())
    seen = datetime.now(timezone.utc) - ago
    run_txn(db, lambda t: t.insert("CatalogSourceVariants", columns=VARIANT_COLS, values=[(
        "dev-provider", "dev-merchant", vid, vid, vid, brand, title, category, f"https://shop.example/{vid}", price, "USD",
        availability, seen, "policy:dev", 1, False, seen, seen)]))
    return vid


def order(db, member_id, variant_id, units, *, version=1, returned=0, order_id=None):
    order_id = order_id or str(uuid.uuid4())
    ev = EventEnvelope(event_type="commerce.order.observed", schema_version="1", aggregate_type="Order", aggregate_id=order_id,
                       aggregate_version=version, environment="development", actor_ref="service:commerce", correlation_id=str(uuid.uuid4()),
                       privacy_class="member_private",
                       payload={"order_id": order_id, "member_id": member_id, "order_status": "accepted",
                                "lines": [{"variant_id": variant_id, "source_variant_ref": "SKU-1", "ordered": units, "delivered": units,
                                           "returned": returned}]})
    WardrobeService(db, catalog_lookup=catalog_variant_lookup(db)).apply_order_observation(ev)
    return order_id


def outbox(db, event_type, member_id):
    with db.snapshot() as s:
        rows = list(s.execute_sql(f"SELECT {', '.join(OUTBOX_COLS)} FROM OutboxEvents WHERE event_type=@t "
                                  "AND JSON_VALUE(payload, '$.member_id') = @m ORDER BY occurred_at",
                                  params={"t": event_type, "m": member_id}, param_types={"t": param_types.STRING, "m": param_types.STRING}))
    return [EventEnvelope.from_row(dict(zip(OUTBOX_COLS, r))) for r in rows]


def ask(svc, owner, recipients, subject_type, subject_id, **kw):
    body = {"subject_type": subject_type, "subject_id": subject_id, "prompt": "Should I?", "recipient_ids": [r.member_id for r in recipients],
            "discussion_mode": "open", **kw}
    return svc.create(owner, body, key())


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ------------------------------------------------------------------ Now loop


def test_asker_window_and_why(spanner_db):
    owner, f = person(spanner_db), person(spanner_db)
    friends(spanner_db, owner, f)
    item = WardrobeService(spanner_db).create_items(owner, {"source": "manual", "title": "Blazer", "category": "outerwear"}, key())["items"][0]["id"]
    svc = DecisionService(spanner_db)
    default = ask(svc, owner, [f], "wardrobe_item", item)
    assert default["duration_seconds"] == 300 and ts(default["closes_at"]) - ts(default["opened_at"]) == timedelta(seconds=300)
    assert default["why"] is None
    quick = ask(svc, owner, [f], "wardrobe_item", item, duration_seconds=180, why="Dinner at eight, smart casual")
    assert ts(quick["closes_at"]) - ts(quick["opened_at"]) == timedelta(seconds=180) and quick["why"] == "Dinner at eight, smart casual"
    assert svc.get(f, quick["decision_id"])["why"] == "Dinner at eight, smart casual"  # the audience sees the why
    for bad in ({"duration_seconds": 240}, {"duration_seconds": 300.0}, {"duration_seconds": True}, {"why": "x" * 281}, {"why": " "}):
        with pytest.raises(ValidationFailed):
            ask(svc, owner, [f], "wardrobe_item", item, **bad)


def test_catalog_subject_must_exist(spanner_db):
    owner, f = person(spanner_db), person(spanner_db)
    friends(spanner_db, owner, f)
    brand, _ = house("Atelier North")
    live = piece(spanner_db, brand, "Overshirt", ago=timedelta(hours=1))
    gone = piece(spanner_db, brand, "Old coat", ago=timedelta(hours=2), availability="discontinued")
    svc = DecisionService(spanner_db, catalog_check=catalog_piece_exists)
    assert ask(svc, owner, [f], "catalog_product", live)["subject_id"] == live
    for missing in (gone, str(uuid.uuid4())):
        with pytest.raises(ValidationFailed):
            ask(svc, owner, [f], "catalog_product", missing)


def test_comment_thread_lives_inside_the_window(spanner_db):
    owner, a, b = person(spanner_db), person(spanner_db), person(spanner_db)
    stranger = person(spanner_db)
    friends(spanner_db, owner, a, b)
    item = WardrobeService(spanner_db).create_items(owner, {"source": "manual", "title": "Coat", "category": "outerwear"}, key())["items"][0]["id"]
    svc = DecisionService(spanner_db)
    blind = ask(svc, owner, [a, b], "wardrobe_item", item, discussion_mode="blind_until_response")
    did = blind["decision_id"]
    # Blind mode: a recipient answers before seeing or joining the thread.
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.add_comment(a, did, {"body": "Hmm"}, key())
    assert e.value.code == "answer_first"
    assert svc.comments(a, did) == {"decision_id": did, "items": [], "hidden_until_you_answer": True}
    svc.respond(a, did, {"choice": "yes"})
    k = key()
    first = svc.add_comment(a, did, {"body": "The navy one"}, k)
    assert svc.add_comment(a, did, {"body": "The navy one"}, k)["comment_id"] == first["comment_id"]  # idempotent replay
    svc.add_comment(owner, did, {"body": "Thanks"}, key())
    seen = svc.comments(owner, did)["items"]
    assert [(c["author_id"], c["body"]) for c in seen] == [(a.member_id, "The navy one"), (owner.member_id, "Thanks")]
    assert svc.comments(b, did)["hidden_until_you_answer"] is True  # b has not answered yet
    with pytest.raises(NotFound):
        svc.comments(stranger, did)
    # The author withdraws: the text is erased, a placeholder keeps the thread readable.
    svc.remove_comment(a, did, first["comment_id"])
    assert svc.comments(owner, did)["items"][0] == {"comment_id": first["comment_id"], "removed": True, "created_at": seen[0]["created_at"]}
    assert count(spanner_db, "SELECT COUNT(*) FROM DecisionComments WHERE comment_id=@c AND body=''", c=first["comment_id"]) == 1
    with pytest.raises(NotFound):
        svc.remove_comment(owner, did, seen[0]["comment_id"])  # only the author can withdraw
    # Per-author cap.
    for i in range(COMMENTS_PER_AUTHOR - 1):
        svc.add_comment(a, did, {"body": f"note {i}"}, key())
    with pytest.raises(RateLimited):
        svc.add_comment(a, did, {"body": "one more"}, key())
    # The thread closes with the window.
    svc.close(owner, did)
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.add_comment(owner, did, {"body": "late"}, key())
    assert e.value.code == "decision_closed"
    assert svc.comments(b, did)["hidden_until_you_answer"] is False  # readable by the audience once closed


def test_influence_credit_goes_to_the_friend_whose_verdict_was_followed(spanner_db):
    buyer, yes, no = person(spanner_db), person(spanner_db), person(spanner_db)
    friends(spanner_db, buyer, yes, no)
    brand, _ = house("Atelier North")
    vid = piece(spanner_db, brand, "Field overshirt", ago=timedelta(hours=1))
    svc = DecisionService(spanner_db, catalog_check=catalog_piece_exists)
    d = ask(svc, buyer, [yes, no], "catalog_product", vid)
    svc.respond(yes, d["decision_id"], {"choice": "yes"})
    svc.respond(no, d["decision_id"], {"choice": "pass"})
    svc.close(buyer, d["decision_id"])
    # The buyer orders two and both are delivered: the provider-observed order, not a self-report, is the evidence.
    order(spanner_db, buyer.member_id, vid, 2)
    consumer = RewardsConsumer(spanner_db)
    events = outbox(spanner_db, "wardrobe.item.created", buyer.member_id)
    assert len(events) == 2
    for ev in events:
        consumer.handle(ev)
    for ev in events:
        consumer.handle(ev)  # redelivery changes nothing

    def influence(member_id):
        return count(spanner_db, "SELECT COUNT(*) FROM RewardEntries WHERE member_id=@m AND rule_id='decision_influence' AND state='posted' "
                                 "AND points=25", m=member_id)

    assert (influence(yes.member_id), influence(no.member_id), influence(buyer.member_id)) == (1, 0, 0)
    assert count(spanner_db, "SELECT COUNT(*) FROM RewardEntries WHERE member_id=@m AND rule_id='decision_influence'", m=yes.member_id) == 1
    # A manual "I bought it" never pays anyone.
    other = piece(spanner_db, brand, "Scarf", ago=timedelta(hours=1))
    d2 = ask(svc, buyer, [yes], "catalog_product", other)
    svc.respond(yes, d2["decision_id"], {"choice": "yes"})
    svc.close(buyer, d2["decision_id"])
    WardrobeService(spanner_db).create_items(buyer, {"source": "manual", "title": "Scarf", "category": "accessory", "product_id": other}, key())
    for ev in outbox(spanner_db, "wardrobe.item.created", buyer.member_id)[2:]:
        consumer.handle(ev)
    assert influence(yes.member_id) == 1


# ---------------------------------------------------------------------- Flow


def test_excitement_sizes_but_never_positions():
    assert size_for(excitement(0, None)) == ("compact", 1)
    assert size_for(excitement(2, None)) == ("compact", 1)  # under the floor counts as none
    assert size_for(excitement(3, None)) == ("standard", 2)
    assert size_for(excitement(25, None)) == ("hero", 3)
    assert size_for(excitement(0, 1.0)) == ("standard", 2)


def test_home_flow(spanner_db):
    db = spanner_db
    me, friend, quiet = person(db), person(db), person(db)
    friends(db, me, friend, quiet)
    hour = timedelta(hours=1)
    (north, north_ref), (closet, _), (other, _) = house("Atelier North"), house("Closet House"), house("Other House")
    n1 = piece(db, north, "Overshirt", ago=3 * hour)
    n2 = piece(db, north, "Chore coat", ago=2 * hour)
    n3 = piece(db, north, "Cashmere coat", ago=hour, price=50000)
    piece(db, other, "Not followed", ago=hour / 2)
    c1 = piece(db, closet, "Owned tee", ago=5 * hour)
    c2 = piece(db, closet, "New tee", ago=hour / 6, availability="out_of_stock")
    catalog = CatalogHouses()
    houses = HouseService(db, catalog=catalog)
    assert houses.follow(me, north_ref, None) == {"house_ref": north_ref, "name": north, "followed": True,
                                                        "share_standing": False}
    with pytest.raises(NotFound):
        houses.follow(me, "no-such-house", {})
    w = WardrobeService(db)
    w.create_items(me, {"source": "manual", "title": "My tee", "category": "top", "product_id": c1}, key())  # Closet House via the closet
    for _ in range(3):  # three members save the chore coat
        w.create_items(person(db), {"source": "catalog", "title": "Chore coat", "category": "outerwear", "product_id": n2}, key())
    PersonaService(db).patch(me, '"0"', {"changes": [], "client_revision": "c",
                                         "constraints": {"budget_ceiling_minor": "15000", "budget_currency": "USD"}})
    item = w.create_items(friend, {"source": "manual", "title": "Boots", "category": "shoes"}, key())["items"][0]["id"]
    decisions = DecisionService(db)
    req = ask(decisions, friend, [me], "wardrobe_item", item, why="Wedding on Saturday")
    q_item = w.create_items(quiet, {"source": "manual", "title": "Hat", "category": "accessory"}, key())["items"][0]["id"]
    ask(decisions, quiet, [me], "wardrobe_item", q_item)
    RelationshipService(db).mute(me, quiet.member_id)  # a muted friend's requests never cut in

    flow = FlowService(db, catalog=catalog, persona=PersonaService(db))
    home = flow.flow(me)
    first = home["items"][0]
    assert first["kind"] == "decision_request" and first["position"] == 1 and first["size"] == "hero"
    assert first["decision"]["decision_id"] == req["decision_id"] and first["decision"]["why"] == "Wedding on Saturday"
    assert 0 < first["decision"]["remaining_seconds"] <= 300 and first["decision"]["answered"] is False
    pieces = [i for i in home["items"] if i["kind"] == "house_piece"]
    # Freshness alone sets position: the over-budget coat is lensed out, the unfollowed house never appears.
    assert [p["piece"]["product_id"] for p in pieces] == [c2, n2, n1, c1]
    assert [p["position"] for p in home["items"]] == list(range(1, 6))
    assert {p["piece"]["product_id"]: (p["size"], p["piece"]["via"]) for p in pieces} == {
        c2: ("compact", "closet"), n2: ("standard", "followed"), n1: ("compact", "followed"), c1: ("compact", "closet")}
    assert pieces[1]["size_reason"] == "Larger because members are talking about it"
    assert pieces[0]["piece"]["available"] is False  # stock is shown, not filtered
    assert home["lens_applied"] is True and home["houses"] == 2 and home["next_cursor"] is None
    assert n3 not in json.dumps(home) and "count" not in json.dumps(home)  # counts are never returned

    # Paging is by freshness; requests cut in on the first page only.
    seen, cursor, pages = [], None, 0
    while True:
        page = flow.flow(me, limit=2, cursor=cursor)
        pages += 1
        assert all(i["kind"] == "house_piece" for i in page["items"]) or pages == 1
        seen += [i["piece"]["product_id"] for i in page["items"] if i["kind"] == "house_piece"]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [c2, n2, n1, c1]
    for bad in ({"limit": 0}, {"limit": 49}, {"cursor": "not-a-cursor"}):
        with pytest.raises(ValidationFailed):
            flow.flow(me, **bad)
    # Once answered, the request says so.
    decisions.respond(me, req["decision_id"], {"choice": "yes"})
    assert flow.flow(me)["items"][0]["decision"]["answered"] is True
    # Unfollowing drops the house from Flow.
    houses.unfollow(me, north_ref)
    assert [i["piece"]["product_id"] for i in flow.flow(me)["items"] if i["kind"] == "house_piece"] == [c2, c1]


# ------------------------------------------------------------------ standing


def test_tier_boundaries():
    assert tier_for(0, MIN_COHORT - 1) == "member"  # small cohorts never rank anyone
    assert tier_for(0, 100) == "top_1" and tier_for(1, 100) == "top_5" and tier_for(5, 100) == "top_10"
    assert tier_for(10, 100) == "top_25" and tier_for(24, 100) == "top_25" and tier_for(25, 100) == "member"
    assert meets("top_1", "top_5") and meets("top_5", "top_5") and not meets("top_10", "top_5") and not meets(None, "member")


def test_house_standing_from_verified_purchases(spanner_db):
    db = spanner_db
    (north, ref), (other, other_ref) = house("Atelier North"), house("Other House")
    vid = piece(db, north, "Overshirt", ago=timedelta(days=2))
    elsewhere = piece(db, other, "Tee", ago=timedelta(days=2))
    top, *rest = [person(db) for _ in range(6)]
    order(db, top.member_id, vid, 3)
    orders = {m.member_id: order(db, m.member_id, vid, 1) for m in rest}
    order(db, rest[0].member_id, elsewhere, 1)
    # A self-reported item is not a verified purchase.
    WardrobeService(db).create_items(rest[1], {"source": "manual", "title": "Overshirt", "category": "top", "product_id": vid}, key())
    houses = HouseService(db, catalog=CatalogHouses())
    houses.follow(top, ref, {"share_standing": True})
    houses.follow(rest[0], ref, {"share_standing": False})

    svc = StandingService(db, catalog=CatalogHouses(), min_cohort=1)
    out = svc.recompute()
    assert out["houses"] >= 2 and out["standings"] >= 7

    def at(house_ref):
        return count(db, "SELECT COUNT(*) FROM HouseStandings WHERE house_ref=@h", h=house_ref)

    assert (at(ref), at(other_ref)) == (6, 1)
    mine = svc.mine(top)
    assert mine["items"] == [{"house_ref": ref, "house_name": north, "tier": "top_1", "computed_at": mine["items"][0]["computed_at"],
                              "shared_with_house": True}]
    assert {i["tier"] for m in rest for i in svc.mine(m)["items"] if i["house_ref"] == ref} == {"top_25"}  # ties share a tier
    assert "units" not in json.dumps(mine) and count(db, "SELECT COUNT(*) FROM HouseStandings WHERE member_id=@m", m=rest[0].member_id) == 2

    # The house sees tier counts (small ones suppressed) and only members who opted in. Never units or orders.
    with pytest.raises(Forbidden):
        svc.house_view(top, ref)
    view = svc.house_view(member_principal(insert_member(db), HOUSE_OPS), ref)
    assert view == {"house_ref": ref, "tiers": {"top_1": None, "top_5": None, "top_10": None, "top_25": 5, "member": None},
                    "suppressed_below": 5, "members_sharing": [{"member_id": top.member_id, "tier": "top_1"}]}
    # Turning sharing off hides the member at once.
    houses.follow(top, ref, {"share_standing": False})
    assert svc.house_view(member_principal(insert_member(db), HOUSE_OPS), ref)["members_sharing"] == []

    # Daily at most; a return removes the standing on the next run.
    assert svc.recompute_if_due() == "not_due"
    order(db, rest[2].member_id, vid, 1, version=2, returned=1, order_id=orders[rest[2].member_id])
    again = svc.recompute()
    assert again["removed"] >= 1 and svc.mine(rest[2])["items"] == [] and at(ref) == 5

    # Below the default cohort size, everyone is simply a member.
    StandingService(db, catalog=CatalogHouses()).recompute()
    assert svc.mine(top)["items"][0]["tier"] == "member"


def test_house_reward_needs_standing(spanner_db):
    db = spanner_db
    north, ref = house("Atelier North")
    vid = piece(db, north, "Overshirt", ago=timedelta(days=2))
    top, other = person(db), person(db)
    order(db, top.member_id, vid, 2)
    order(db, other.member_id, vid, 1)
    StandingService(db, catalog=CatalogHouses(), min_cohort=1).recompute()
    rewards = RewardsService(db, approved_repair_issuers=frozenset({ISSUER}))
    for m in (top, other):
        for _ in range(2):
            rewards.record_verified_repair(service_principal("repair-workflow"), m.member_id, repair_ref=str(uuid.uuid4()), issuer_ref=ISSUER)
    benefits = BenefitService(db)
    op = member_principal(insert_member(db), OPS)
    base = {"kind": "partner", "title": "First look", "description": "Early access to the next drop", "cost_points": 50,
            "inventory_total": 5, "funded": True, "sponsor": north}
    for bad in ({"house_ref": ref}, {"min_standing": "top_1"}, {"house_ref": north, "min_standing": "top_1"},
                {"house_ref": ref, "min_standing": "gold"}, {"kind": "room_finish", "house_ref": ref, "min_standing": "top_1"}):
        with pytest.raises(ValidationFailed):
            benefits.create_benefit(op, {**base, **bad})
    drop = benefits.create_benefit(op, {**base, "house_ref": ref, "min_standing": "top_1"})
    assert drop["house_ref"] == ref and drop["min_standing"] == "top_1"
    with pytest.raises(DetailedInvalidTransition) as e:
        benefits.reserve(other, drop["benefit_id"], key())
    assert e.value.code == "standing_required"
    assert benefits.reserve(top, drop["benefit_id"], key())["state"] == "pending"
