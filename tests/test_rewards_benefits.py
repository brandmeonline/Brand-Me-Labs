"""Benefit reservations (BM-LOY-007, BM-LOY-008) and ledger retry safety."""

import threading
import uuid
from datetime import datetime, timezone

import pytest
from google.cloud.spanner_v1 import param_types

from brandme_core.domains.persona.kernel import (
    DetailedInvalidTransition,
    Forbidden,
    NotFound,
    ValidationFailed,
    member_principal,
    run_read,
    run_txn,
    server_now,
    service_principal,
)
from brandme_core.domains.rewards import ledger
from brandme_core.domains.rewards.benefits import BenefitService
from brandme_core.domains.rewards.consumer import RewardsConsumer
from brandme_core.domains.rewards.service import RewardsService
from brandme_core.events import EventEnvelope
from test_persona_harness import MEMBER_SCOPES, AbortOnceDB, count, insert_member, spanner_db  # noqa: F401

OPS = frozenset({"moderation:admin"})
WRITER = MEMBER_SCOPES | {"rewards:write"}
NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
ISSUER = "repairer:atelier-north"


def key():
    return "k-" + uuid.uuid4().hex


def funded_member(db, points):
    """A member with ``points`` earned through the trusted repair path (50 each)."""
    m = member_principal(insert_member(db), WRITER)
    svc = RewardsService(db, approved_repair_issuers=frozenset({ISSUER}))
    for _ in range(points // 50):
        svc.record_verified_repair(service_principal("repair-workflow"), m.member_id, repair_ref=str(uuid.uuid4()), issuer_ref=ISSUER)
    assert run_read(db, lambda s: ledger.load_account(s, m.member_id)).available == points
    return m


def benefit(db, cost, inventory=10, **kw):
    ops = member_principal(insert_member(db), OPS)
    body = {"kind": "room_finish", "title": f"Finish {cost}", "description": "Cosmetic room finish", "cost_points": cost, "inventory_total": inventory}
    body.update(kw)
    return BenefitService(db).create_benefit(ops, body)


def acct(db, m):
    c = run_read(db, lambda s: ledger.consistency(s, m))
    assert c["ok"], c
    return c["account"]


def race(fns):
    results, errors = [], []

    def run(fn):
        try:
            results.append(fn())
        except DetailedInvalidTransition as e:
            results.append(e.code)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=run, args=(f,)) for f in fns]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors
    return results


def test_two_benefits_race_for_insufficient_points(spanner_db):
    """BM-LOY-007: 100 available; two 60-point benefits reserved at once → one succeeds."""
    m = funded_member(spanner_db, 100)
    svc = BenefitService(spanner_db)
    a, b = benefit(spanner_db, 60), benefit(spanner_db, 60)
    for _ in range(3):  # repeat the race; the outcome never varies
        before = acct(spanner_db, m.member_id)["available"]
        results = race([lambda: svc.reserve(m, a["benefit_id"], key()), lambda: svc.reserve(m, b["benefit_id"], key())])
        ok = [r for r in results if isinstance(r, dict)]
        if before >= 60:
            assert len(ok) == 1 and results.count("insufficient_points") == 1
        else:
            assert results == ["insufficient_points", "insufficient_points"]
        a_now = acct(spanner_db, m.member_id)
        assert a_now["available"] >= 0 and a_now["available"] + a_now["reserved"] == 100
    final = acct(spanner_db, m.member_id)
    assert (final["available"], final["reserved"]) == (40, 60)


def test_ten_concurrent_reservations_never_overspend(spanner_db):
    m = funded_member(spanner_db, 150)
    svc = BenefitService(spanner_db)
    b = benefit(spanner_db, 50, inventory=100)
    results = race([lambda: svc.reserve(m, b["benefit_id"], key()) for _ in range(10)])
    assert len([r for r in results if isinstance(r, dict)]) == 3 and results.count("insufficient_points") == 7
    a = acct(spanner_db, m.member_id)
    assert (a["available"], a["reserved"]) == (0, 150)
    # Same Idempotency-Key replayed concurrently → one reservation.
    m2 = funded_member(spanner_db, 100)
    k = key()
    results = race([lambda: svc.reserve(m2, b["benefit_id"], k) for _ in range(5)])
    assert len({r["reservation_id"] for r in results}) == 1
    assert acct(spanner_db, m2.member_id)["reserved"] == 50


def test_inventory_is_reserved_atomically(spanner_db):
    svc = BenefitService(spanner_db)
    b = benefit(spanner_db, 10, inventory=2)
    members = [funded_member(spanner_db, 50) for _ in range(4)]
    results = race([lambda m=m: svc.reserve(m, b["benefit_id"], key()) for m in members])
    assert len([r for r in results if isinstance(r, dict)]) == 2 and results.count("benefit_unavailable") == 2
    listed = {x["benefit_id"]: x for x in svc.list_benefits(members[0])["items"]}[b["benefit_id"]]
    assert listed["remaining"] == 0 and listed["available"] is False
    losers = [m for m in members if acct(spanner_db, m.member_id)["reserved"] == 0]
    assert len(losers) == 2 and all(acct(spanner_db, m.member_id)["available"] == 50 for m in losers)


def test_failed_fulfillment_releases_once_with_visible_status(spanner_db):
    """BM-LOY-008."""
    m = funded_member(spanner_db, 100)
    svc = BenefitService(spanner_db)
    b = benefit(spanner_db, 40, inventory=3)
    r1 = svc.reserve(m, b["benefit_id"], key())
    r2 = svc.reserve(m, b["benefit_id"], key())
    assert acct(spanner_db, m.member_id)["reserved"] == 80

    def fulfiller(r):
        if r["reservation_id"] == r1["reservation_id"]:
            raise RuntimeError("provider timeout")
        return True

    counts = svc.run_fulfillment(fulfiller, benefit_id=b["benefit_id"])
    assert counts == {"fulfilled": 1, "refunded": 1, "skipped": 0}
    a = acct(spanner_db, m.member_id)
    assert (a["available"], a["reserved"], a["spent"]) == (60, 0, 40)
    mine = {x["reservation_id"]: x for x in svc.list_reservations(m)["items"]}
    assert mine[r1["reservation_id"]]["state"] == "refunded" and mine[r1["reservation_id"]]["release_reason"] == "fulfillment_failed"
    assert mine[r2["reservation_id"]]["state"] == "fulfilled"
    # Settling again (or racing settlements) changes nothing.
    assert svc.settle(r1["reservation_id"], succeeded=True)["changed"] is False
    assert svc.run_fulfillment(lambda r: True, benefit_id=b["benefit_id"]) == {"fulfilled": 0, "refunded": 0, "skipped": 0}
    assert acct(spanner_db, m.member_id)["available"] == 60
    assert count(spanner_db, "SELECT COUNT(*) FROM RewardEntries WHERE reservation_id=@r AND kind='release'", r=r1["reservation_id"]) == 1
    inv = {x["benefit_id"]: x for x in svc.list_benefits(m)["items"]}[b["benefit_id"]]
    assert inv["remaining"] == 2  # 3 total, 1 fulfilled, the failed unit returned


def test_concurrent_settlements_resolve_once(spanner_db):
    m = funded_member(spanner_db, 50)
    svc = BenefitService(spanner_db)
    r = svc.reserve(m, benefit(spanner_db, 50)["benefit_id"], key())
    results = race([lambda ok=ok: svc.settle(r["reservation_id"], succeeded=ok) for ok in (True, False) * 4])
    assert sum(1 for x in results if x["changed"]) == 1
    a = acct(spanner_db, m.member_id)
    assert a["reserved"] == 0 and a["available"] + a["spent"] == 50


def test_expired_reservations_are_released(spanner_db):
    m = funded_member(spanner_db, 50)
    svc = BenefitService(spanner_db)
    r = svc.reserve(m, benefit(spanner_db, 50)["benefit_id"], key())

    def expire(t):
        t.execute_update("UPDATE BenefitReservations SET expires_at=@e WHERE member_id=@m AND reservation_id=@r",
                         params={"e": server_now(t), "m": m.member_id, "r": r["reservation_id"]},
                         param_types={"e": param_types.TIMESTAMP, "m": param_types.STRING, "r": param_types.STRING})

    run_txn(spanner_db, expire)
    assert svc.expire_due() == {"released": 1}
    assert svc.expire_due() == {"released": 0}
    assert acct(spanner_db, m.member_id)["available"] == 50


def test_benefit_rules(spanner_db):
    ops = member_principal(insert_member(spanner_db), OPS)
    svc = BenefitService(spanner_db)
    with pytest.raises(ValidationFailed):  # an unfunded partner offer cannot exist
        svc.create_benefit(ops, {"kind": "partner", "title": "10% off", "description": "x", "cost_points": 100, "inventory_total": 5})
    with pytest.raises(Forbidden):
        svc.create_benefit(member_principal(insert_member(spanner_db), MEMBER_SCOPES), {"kind": "room_finish"})
    m = member_principal(insert_member(spanner_db), MEMBER_SCOPES)  # no rewards:write
    with pytest.raises(Forbidden):
        svc.reserve(m, str(uuid.uuid4()), key())
    with pytest.raises(NotFound):
        svc.reserve(member_principal(m.member_id, WRITER), str(uuid.uuid4()), key())
    ok = svc.create_benefit(ops, {"kind": "partner", "title": "Tailoring credit", "description": "Funded by Atelier North", "cost_points": 100,
                                  "inventory_total": 5, "funded": True, "sponsor": "Atelier North"})
    assert ok["sponsor"] == "Atelier North"


def test_injected_abort_does_not_duplicate_entries(spanner_db):
    """A retried settlement attempt does not double-post (fresh transaction overlay per attempt)."""
    friend, creator = insert_member(spanner_db), insert_member(spanner_db)
    ev = EventEnvelope(event_type="decision.closed", schema_version="1", aggregate_type="decision", aggregate_id=str(uuid.uuid4()),
                       aggregate_version=2, environment="development", actor_ref="service:decision-closer", correlation_id=str(uuid.uuid4()),
                       privacy_class="member_private", occurred_at=NOW,
                       payload={"decision_id": str(uuid.uuid4()), "creator_id": creator, "close_reason": "expired",
                                "eligible_respondent_ids": [friend], "repeat_request": False, "zero_replies": False})
    flaky = AbortOnceDB(spanner_db)
    out = RewardsConsumer(flaky).handle(ev)
    assert flaky.attempts == 2 and out["status"] == "processed"
    assert count(spanner_db, "SELECT COUNT(*) FROM RewardEntries WHERE member_id=@m", m=friend) == 1
    assert count(spanner_db, "SELECT COUNT(*) FROM OutboxEvents WHERE event_type='reward.posted' AND JSON_VALUE(payload, '$.member_id')=@m", m=friend) == 1
    assert acct(spanner_db, friend)["available"] == 10
