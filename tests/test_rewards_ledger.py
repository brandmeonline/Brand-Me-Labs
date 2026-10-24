"""Reward ledger settlement (BM-LOY-001..004, 006, 009; exit evidence:
exactly-once ledger under concurrent duplicates, caps, reversals)."""

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from google.cloud.spanner_v1 import param_types

from brandme_core.domains.persona.kernel import (
    DetailedInvalidTransition,
    FixedClock,
    Forbidden,
    member_principal,
    run_read,
    service_principal,
)
from brandme_core.domains.persona.service import PersonaService
from brandme_core.domains.rewards import ledger
from brandme_core.domains.rewards.consumer import RewardsConsumer
from brandme_core.domains.rewards.rules import BADGES, RULES, cap_window
from brandme_core.domains.rewards.service import RewardsService
from brandme_core.domains.social.clock import FixedTxnClock
from brandme_core.domains.social.decisions import DecisionService
from brandme_core.domains.social.relationships import RelationshipService
from brandme_core.domains.wardrobe.outfits import OutfitService
from brandme_core.domains.wardrobe.rooms import ROOMS
from brandme_core.domains.wardrobe.service import WardrobeService
from brandme_core.events import EventEnvelope
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
OPS = frozenset({"moderation:admin"})
OUTBOX_COLS = ("event_id", "event_type", "schema_version", "aggregate_type", "aggregate_id", "aggregate_version", "environment",
               "actor_ref", "correlation_id", "causation_id", "privacy_class", "payload", "occurred_at")


def key():
    return "k-" + uuid.uuid4().hex


def person(db, scopes=MEMBER_SCOPES):
    return member_principal(insert_member(db), scopes)


def operator(db):
    return member_principal(insert_member(db), OPS)


def outbox(db, event_type, **where):
    sql = f"SELECT {', '.join(OUTBOX_COLS)} FROM OutboxEvents WHERE event_type=@t"
    params = {"t": event_type}
    for k, v in where.items():
        sql += f" AND JSON_VALUE(payload, '$.{k}') = @{k}"
        params[k] = v
    with db.snapshot() as s:
        rows = list(s.execute_sql(sql + " ORDER BY occurred_at", params=params, param_types={k: param_types.STRING for k in params}))
    return [EventEnvelope.from_row(dict(zip(OUTBOX_COLS, r))) for r in rows]


def deliver_all(db, consumer, member_id, types):
    out = []
    for t in types:
        for ev in outbox(db, t, member_id=member_id) + outbox(db, t, owner_member_id=member_id):
            out.append(consumer.handle(ev))
    return out


def synthetic(event_type, payload, *, at=NOW, actor="service:test"):
    return EventEnvelope(event_type=event_type, schema_version="1", aggregate_type="test", aggregate_id=str(uuid.uuid4()),
                         aggregate_version=1, environment="development", actor_ref=actor, correlation_id=str(uuid.uuid4()),
                         privacy_class="member_private", payload=payload, occurred_at=at)


def closed(decision_id, creator, respondents, *, at=NOW, repeat=False):
    ev = synthetic("decision.closed", {"decision_id": decision_id, "creator_id": creator, "close_reason": "expired",
                                       "eligible_respondent_ids": sorted(respondents), "repeat_request": repeat,
                                       "zero_replies": not respondents}, at=at)
    ev.validate()
    return ev


def entries(db, member_id, rule_id=None):
    sql = "SELECT entry_id, kind, state, rule_id, points, available_delta, recovery_delta, reverses_entry_id, outcome_reason FROM RewardEntries WHERE member_id=@m"
    params = {"m": member_id}
    if rule_id:
        sql += " AND rule_id=@r"
        params["r"] = rule_id
    with db.snapshot() as s:
        rows = list(s.execute_sql(sql + " ORDER BY created_at, entry_id", params=params, param_types={k: param_types.STRING for k in params}))
    return [dict(zip(("entry_id", "kind", "state", "rule_id", "points", "available", "recovery", "reverses", "reason"), r)) for r in rows]


def account(db, member_id):
    return run_read(db, lambda s: ledger.load_account(s, member_id))


def consistent(db, member_id):
    c = run_read(db, lambda s: ledger.consistency(s, member_id))
    assert c["ok"], c
    return c["account"]


# ---------------------------------------------------------------- rule table


def test_rules_mirror_the_contract():
    spec = json.loads((REPO / "docs/design/brandme/contracts/reward-rules.json").read_text())
    assert spec["window_timezone"] == "UTC"
    assert {r["id"] for r in spec["rules"]} == set(RULES)
    for r in spec["rules"]:
        mine = RULES[r["id"]]
        assert (mine.version, mine.points) == (r["version"], r["points"]), r["id"]
        assert mine.cap_points == r.get("cap_points") and mine.cap_window == r.get("cap_window"), r["id"]
        assert mine.lifetime_max == r.get("maximum_awards_lifetime"), r["id"]
    assert len(BADGES) == 6


def test_cap_windows_are_utc_and_ignore_member_timezone():
    t = datetime(2026, 12, 31, 23, 30, tzinfo=timezone(timedelta(hours=-8)))  # = 2027-01-01 07:30 UTC
    assert cap_window("calendar_day", t) == (datetime(2027, 1, 1, tzinfo=timezone.utc), datetime(2027, 1, 2, tzinfo=timezone.utc))
    assert cap_window("calendar_month", t) == (datetime(2027, 1, 1, tzinfo=timezone.utc), datetime(2027, 2, 1, tzinfo=timezone.utc))
    assert cap_window("calendar_month", datetime(2026, 12, 15, tzinfo=timezone.utc))[1] == datetime(2027, 1, 1, tzinfo=timezone.utc)
    # ISO week starts Monday 00:00 UTC; 2026-10-05 is a Monday.
    assert cap_window("iso_week", datetime(2026, 10, 11, 23, 59, tzinfo=timezone.utc))[0] == datetime(2026, 10, 5, tzinfo=timezone.utc)
    assert cap_window("iso_week", datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc))[0] == datetime(2026, 10, 12, tzinfo=timezone.utc)


# ------------------------------------------------------------ BM-LOY-001


def test_setup_and_first_owned_item_post_once_with_evidence(spanner_db):
    me = person(spanner_db)
    m = me.member_id
    consumer = RewardsConsumer(spanner_db)
    persona = PersonaService(spanner_db, clock=FixedClock(NOW))
    wardrobe = WardrobeService(spanner_db, clock=FixedClock(NOW))
    outfits = OutfitService(spanner_db, clock=FixedClock(NOW))
    # Wishlist items and a profile alone earn nothing.
    wardrobe.create_items(me, {"source": "manual", "title": "Dream coat", "category": "outerwear", "collection": "want"}, key())
    persona.patch(me, '"0"', {"changes": [{"axis": "expression", "value": 70, "locked": False}], "client_revision": "r1"})
    deliver_all(spanner_db, consumer, m, ("persona.updated", "wardrobe.item.created"))
    assert entries(spanner_db, m) == []
    # Owned item → 25 once, even with a second owned item and redelivery.
    items = [wardrobe.create_items(me, {"source": "manual", "title": t, "category": "top"}, key())["items"][0]["id"] for t in ("Tee", "Shirt")]
    outfits.create_outfit(me, {"title": "Monday", "item_refs": items}, key())
    for _ in range(2):
        deliver_all(spanner_db, consumer, m, ("persona.updated", "wardrobe.item.created", "outfit.version.created"))
    es = entries(spanner_db, m)
    assert sorted((e["rule_id"], e["points"], e["state"]) for e in es) == [("first_owned_item", 25, "posted"), ("meaningful_style_setup", 100, "posted")]
    a = consistent(spanner_db, m)
    assert (a["available"], a["lifetime_earned"]) == (125, 125)
    with spanner_db.snapshot() as s:
        rows = {r[0]: (r[1], list(r[2])) for r in s.execute_sql(
            "SELECT rule_id, rule_version, evidence_refs FROM RewardEntries WHERE member_id=@m", params={"m": m}, param_types={"m": param_types.STRING})}
    assert rows["first_owned_item"] == (1, [f"item:{items[0]}"])
    assert rows["meaningful_style_setup"][0] == 1 and len(rows["meaningful_style_setup"][1]) == 2
    assert count(spanner_db, "SELECT COUNT(*) FROM OutboxEvents WHERE event_type='reward.posted' AND JSON_VALUE(payload, '$.member_id')=@m", m=m) == 2
    summary = RewardsService(spanner_db).summary(me)
    assert summary["account"]["available"] == 125 and summary["next_milestone"]["kind"] == "badge"
    assert {b["badge_id"]: b["earned"] for b in summary["badges"]}["first_reflection"] is True


def test_provisioned_or_inferred_profile_does_not_count_as_saved(spanner_db):
    m = insert_member(spanner_db)
    consumer = RewardsConsumer(spanner_db)
    PersonaService(spanner_db, clock=FixedClock(NOW)).ensure_profile(m)  # worker-created empty profile
    deliver_all(spanner_db, consumer, m, ("persona.updated",))
    assert run_read(spanner_db, lambda s: ledger.facts(s, m)) == {}


# ------------------------------------------------------------ BM-LOY-002


def test_ten_parallel_duplicates_change_the_balance_once(spanner_db):
    friend, creator = person(spanner_db), insert_member(spanner_db)
    consumer = RewardsConsumer(spanner_db)
    ev = closed(str(uuid.uuid4()), creator, [friend.member_id])
    results, errors = [], []

    def run():
        try:
            results.append(consumer.handle(ev))  # the same event delivered ten times at once
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors
    assert sorted(r["status"] for r in results) == ["duplicate_delivery"] * 9 + ["processed"]
    assert len(entries(spanner_db, friend.member_id)) == 1
    assert consistent(spanner_db, friend.member_id)["available"] == 10
    assert count(spanner_db, "SELECT COUNT(*) FROM InboxReceipts WHERE consumer='rewards.ledger' AND event_id=@e", e=ev.event_id) == 1


def test_same_cause_through_different_events_settles_once(spanner_db):
    """Two different item events racing for the lifetime-once rule: one award."""
    m = insert_member(spanner_db)
    consumer = RewardsConsumer(spanner_db)
    evs = [synthetic("wardrobe.item.created", {"member_id": m, "item_id": str(uuid.uuid4()), "collection": "owned",
                                               "acquisition_source": "manual", "claim_level": "self_reported"}) for _ in range(6)]
    threads = [threading.Thread(target=consumer.handle, args=(e,)) for e in evs]
    [t.start() for t in threads]
    [t.join() for t in threads]
    es = entries(spanner_db, m, "first_owned_item")
    assert len(es) == 1 and es[0]["points"] == 25
    assert consistent(spanner_db, m)["available"] == 25


# ------------------------------------------------------------ BM-LOY-003


def test_daily_response_cap_and_utc_reset(spanner_db):
    friend, creator = insert_member(spanner_db), insert_member(spanner_db)
    consumer = RewardsConsumer(spanner_db)
    day = datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc)
    for i in range(12):
        consumer.handle(closed(str(uuid.uuid4()), creator, [friend], at=day + timedelta(minutes=i)))
    es = entries(spanner_db, friend)
    assert [e["state"] for e in es].count("posted") == 10 and [e["state"] for e in es].count("capped") == 2
    assert sum(e["points"] for e in es) == 100
    # 00:00 UTC the next day: a new window (the member's own timezone is irrelevant).
    consumer.handle(closed(str(uuid.uuid4()), creator, [friend], at=datetime(2026, 10, 7, 0, 0, tzinfo=timezone.utc)))
    assert consistent(spanner_db, friend)["available"] == 110


def test_weekly_and_monthly_caps(spanner_db):
    reviewer, me = operator(spanner_db), person(spanner_db)
    svc = RewardsService(spanner_db, approved_repair_issuers=frozenset({"repairer:atelier-north"}))
    for _ in range(6):
        svc.accept_contribution(reviewer, me.member_id, kind="catalog_correction", contribution_ref=str(uuid.uuid4()), evidence_ref="photo-1")
    workflow = service_principal("repair-workflow")
    for _ in range(5):
        svc.record_verified_repair(workflow, me.member_id, repair_ref=str(uuid.uuid4()), issuer_ref="repairer:atelier-north")
    with spanner_db.snapshot() as s:
        rows = list(s.execute_sql("SELECT rule_id, qualifying_at, points, state FROM RewardEntries WHERE member_id=@m AND kind='credit'",
                                  params={"m": me.member_id}, param_types={"m": param_types.STRING}))
    for rule_id, cap in (("catalog_correction_accepted", 250), ("verified_repair", 200)):
        rule = RULES[rule_id]
        windows = {}
        for r in rows:
            if r[0] == rule_id:
                windows.setdefault(cap_window(rule.cap_window, r[1]), []).append(r)
        for w, rs in windows.items():
            assert sum(r[2] for r in rs) <= cap
        if len(windows) == 1:  # the usual case: all within one window
            assert sum(r[2] for r in rows if r[0] == rule_id) == cap
            assert [r[3] for r in rows if r[0] == rule_id].count("capped") == 1  # 6x50 > 250, 5x50 > 200
    consistent(spanner_db, me.member_id)


# ------------------------------------------------------------ BM-LOY-004


def test_yes_and_pass_earn_equal_points(spanner_db):
    rel = RelationshipService(spanner_db)
    owner, yes, pas = person(spanner_db), person(spanner_db), person(spanner_db)
    for f in (yes, pas):
        rel.accept(f, rel.request(owner, f.member_id)["relationship_id"])
    item = WardrobeService(spanner_db).create_items(owner, {"source": "manual", "title": "Bag", "category": "accessory"}, key())["items"][0]["id"]
    clock = FixedTxnClock(NOW)
    decisions = DecisionService(spanner_db, clock=clock)
    d = decisions.create(owner, {"subject_type": "wardrobe_item", "subject_id": item, "prompt": "Buy it?", "recipient_ids": [yes.member_id, pas.member_id],
                                 "duration_seconds": 300, "discussion_mode": "blind_until_response"}, key())
    decisions.respond(yes, d["decision_id"], {"choice": "yes"})
    decisions.respond(pas, d["decision_id"], {"choice": "pass"})
    clock.set(NOW + timedelta(seconds=300))
    decisions.close_due()
    consumer = RewardsConsumer(spanner_db)
    for ev in outbox(spanner_db, "decision.closed", decision_id=d["decision_id"]):
        consumer.handle(ev)
    assert account(spanner_db, yes.member_id).available == account(spanner_db, pas.member_id).available == 10
    assert account(spanner_db, owner.member_id).available == 0  # the creator earns nothing for asking


def test_repeated_identical_request_cannot_farm(spanner_db):
    friend, creator = insert_member(spanner_db), insert_member(spanner_db)
    RewardsConsumer(spanner_db).handle(closed(str(uuid.uuid4()), creator, [friend], repeat=True))
    (e,) = entries(spanner_db, friend)
    assert (e["state"], e["points"], e["reason"]) == ("excluded", 0, "repeated_identical_request")


# ------------------------------------------------------------ BM-LOY-006


def accepted(proposer, owner, at=NOW):
    return synthetic("outfit.proposal.accepted", {"outfit_id": str(uuid.uuid4()), "owner_member_id": owner, "proposal_id": str(uuid.uuid4()),
                                                  "proposer_member_id": proposer, "accepted_version": "2"}, at=at)


def test_all_six_badges_with_inspectable_evidence(spanner_db):
    me = person(spanner_db)
    m = me.member_id
    consumer = RewardsConsumer(spanner_db)
    svc = RewardsService(spanner_db, approved_repair_issuers=frozenset({"repairer:atelier-north"}))
    # First Reflection
    PersonaService(spanner_db, clock=FixedClock(NOW)).patch(me, '"0"', {"changes": [{"axis": "expression", "value": 60, "locked": False}],
                                                                        "client_revision": "b"})
    # Closet Curator: 10 owned items placed in the room
    w = WardrobeService(spanner_db, clock=FixedClock(NOW))
    room = ROOMS["walnut_atelier"]
    slots = [(g, str(i)) for g in ("rail.left", "rail.right") for i in range(room.groups[g].capacity)][:10]
    for g, s_id in slots:
        grp = room.groups[g]
        w.create_items(me, {"source": "manual", "title": f"Top {g} {s_id}", "category": "top", "placement": {
            "room_template_id": room.room_id, "semantic_group": g, "slot_id": s_id, "position_meters": list(grp.slot_position(s_id)),
            "rotation_quaternion": [0, 0, 0, 1], "uniform_scale": 1.0, "asset_revision": room.revision}}, key())
    deliver_all(spanner_db, consumer, m, ("persona.updated", "wardrobe.item.created", "closet.placement.changed"))
    # Trusted Eye: 20 valid responses over 20 decisions (10 earn points, 10 capped; badge counts participation)
    creator = insert_member(spanner_db)
    for i in range(20):
        consumer.handle(closed(str(uuid.uuid4()), creator, [m], at=NOW + timedelta(minutes=i)))
    # Style Collaborator: 5 accepted proposals from 5 different owners
    for i in range(5):
        consumer.handle(accepted(m, insert_member(spanner_db), at=NOW + timedelta(hours=1, minutes=i)))
    # Care Keeper and Material Story through their trusted paths
    svc.record_verified_repair(service_principal("repair-workflow"), m, repair_ref=str(uuid.uuid4()), issuer_ref="repairer:atelier-north")
    svc.accept_contribution(operator(spanner_db), m, kind="product_history", contribution_ref=str(uuid.uuid4()), evidence_ref="archive-scan")

    badges = {b["badge_id"]: b for b in svc.summary(me)["badges"]}
    assert all(b["earned"] for b in badges.values()), {k: v["earned"] for k, v in badges.items()}
    assert len(badges["closet_curator"]["evidence_refs"]) == 10
    assert len(badges["trusted_eye"]["evidence_refs"]) == 20 and all(r.startswith("decision:") for r in badges["trusted_eye"]["evidence_refs"])
    assert len(badges["style_collaborator"]["evidence_refs"]) == 5
    assert badges["care_keeper"]["evidence_refs"][0].startswith("repair:")
    assert "identity" in badges["trusted_eye"]["criteria"] and all(b["criteria"] and b["criteria_version"] == 1 for b in badges.values())
    for b in badges.values():  # no badge claims authenticity or ownership
        assert "authentic" not in b["criteria"].lower()
    consistent(spanner_db, m)


def test_proposal_rewards_exclude_self_and_repeated_pairs(spanner_db):
    me, owner = insert_member(spanner_db), insert_member(spanner_db)
    consumer = RewardsConsumer(spanner_db)
    assert consumer.handle(accepted(me, me))["outcomes"][0]["reason"] == "self_acceptance"
    consumer.handle(accepted(me, owner))
    consumer.handle(accepted(me, owner, at=NOW + timedelta(minutes=5)))  # same pair, same UTC day
    consumer.handle(accepted(me, owner, at=NOW + timedelta(days=1)))
    es = entries(spanner_db, me, "styling_proposal_accepted")
    assert [(e["state"], e["points"]) for e in es] == [("posted", 25), ("excluded", 0), ("posted", 25)]
    assert es[1]["reason"] == "collusive_repeated_acceptance"


# ------------------------------------------------------------ BM-LOY-009


def test_reversal_is_linked_and_spent_points_become_recovery_due(spanner_db):
    from brandme_core.domains.rewards.benefits import BenefitService

    me, ops = person(spanner_db), operator(spanner_db)
    m = me.member_id
    svc = RewardsService(spanner_db, approved_repair_issuers=frozenset({"repairer:atelier-north"}))
    out = svc.record_verified_repair(service_principal("repair-workflow"), m, repair_ref=str(uuid.uuid4()), issuer_ref="repairer:atelier-north")
    assert out["badges"] == {"care_keeper": "awarded"}
    # Spend 40 of the 50 points.
    benefits = BenefitService(spanner_db)
    b = benefits.create_benefit(ops, {"kind": "room_finish", "title": "Walnut lacquer", "description": "A deeper finish", "cost_points": 40,
                                      "inventory_total": 5})
    res = benefits.reserve(member_principal(m, MEMBER_SCOPES | {"rewards:write"}), b["benefit_id"], key())
    benefits.settle(res["reservation_id"], succeeded=True)
    assert account(spanner_db, m).available == 10
    # A verified disqualifying event reverses the repair award.
    with pytest.raises(Forbidden):
        svc.reverse_entry(me, m, out["entry_id"], reason="self", evidence_ref="x")  # members cannot reverse/edit
    rev = svc.reverse_entry(ops, m, out["entry_id"], reason="repair attestation revoked by issuer", evidence_ref="issuer-revocation-17")
    assert rev["status"] == "reversed" and rev["points"] == 50 and rev["recovery_due_added"] == 40
    assert rev["badges"] == {"care_keeper": "revoked"}
    a = consistent(spanner_db, m)
    assert (a["available"], a["recovery_due"], a["lifetime_earned"], a["gross_earned"], a["reversed"]) == (0, 40, 0, 50, 50)
    es = entries(spanner_db, m, "verified_repair")
    assert [e["kind"] for e in es] == ["credit", "reversal"] and es[1]["reverses"] == out["entry_id"]
    assert es[0]["points"] == 50 and es[0]["state"] == "posted"  # the original is preserved, not rewritten
    # Idempotent: a second reversal changes nothing.
    assert svc.reverse_entry(ops, m, out["entry_id"], reason="again", evidence_ref="dup")["status"] == "already_reversed"
    # The next eligible award first pays down recovery due.
    svc.record_verified_repair(service_principal("repair-workflow"), m, repair_ref=str(uuid.uuid4()), issuer_ref="repairer:atelier-north")
    a = consistent(spanner_db, m)
    assert (a["available"], a["recovery_due"]) == (10, 0)
    badges = {b["badge_id"]: b for b in svc.summary(me)["badges"]}
    assert badges["care_keeper"]["earned"] is True  # re-earned from new evidence
    with pytest.raises(DetailedInvalidTransition):  # reversals themselves are not reversible
        svc.reverse_entry(ops, m, rev["entry_id"], reason="x", evidence_ref="y")


def test_untrusted_paths_cannot_award(spanner_db):
    """BM-LOY-005 (server half)."""
    me, ops = person(spanner_db), operator(spanner_db)
    svc = RewardsService(spanner_db, approved_repair_issuers=frozenset({"repairer:atelier-north"}))
    for call in (
        lambda: svc.accept_contribution(me, me.member_id, kind="catalog_correction", contribution_ref=str(uuid.uuid4()), evidence_ref="e"),
        lambda: svc.accept_contribution(ops, ops.member_id, kind="catalog_correction", contribution_ref=str(uuid.uuid4()), evidence_ref="e"),
        lambda: svc.record_verified_repair(me, me.member_id, repair_ref=str(uuid.uuid4()), issuer_ref="repairer:atelier-north"),
        lambda: svc.accept_contribution(member_principal(ops.member_id, OPS, delegation_id=str(uuid.uuid4())), me.member_id,
                                        kind="catalog_correction", contribution_ref=str(uuid.uuid4()), evidence_ref="e"),
        lambda: svc.accept_contribution(member_principal(ops.member_id, OPS, environment="production", assurance_level="aal1"), me.member_id,
                                        kind="catalog_correction", contribution_ref=str(uuid.uuid4()), evidence_ref="e"),
    ):
        with pytest.raises(Forbidden):
            call()
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.record_verified_repair(service_principal("repair-workflow"), me.member_id, repair_ref=str(uuid.uuid4()), issuer_ref="repairer:unknown")
    assert e.value.code == "repair_issuer_not_approved"
    # A duplicate correction for the same contribution settles once.
    ref = str(uuid.uuid4())
    svc.accept_contribution(ops, me.member_id, kind="catalog_correction", contribution_ref=ref, evidence_ref="e")
    assert svc.accept_contribution(ops, me.member_id, kind="catalog_correction", contribution_ref=ref, evidence_ref="e")["status"] == "duplicate_cause"
    assert consistent(spanner_db, me.member_id)["available"] == 50
    # Disqualified members (inactive) earn nothing from events.
    gone = insert_member(spanner_db, account_state="suspended")
    out = RewardsConsumer(spanner_db).handle(closed(str(uuid.uuid4()), insert_member(spanner_db), [gone]))
    assert out["outcomes"][0]["status"] == "member_not_eligible" and entries(spanner_db, gone) == []
