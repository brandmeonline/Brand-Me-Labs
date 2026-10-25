"""Five-minute decisions (BM-SOC-002..008, BM-SOC-012).

Deadline evidence uses both clocks: ``SpannerTxnClock`` (production; the
deadline is read from Spanner inside the transaction) and ``FixedTxnClock``
to hit the exact microsecond boundary deterministically.
"""

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from google.cloud.spanner_v1 import param_types

from brandme_core.domains.persona.kernel import (
    DetailedInvalidTransition,
    NotFound,
    RateLimited,
    ValidationFailed,
    json_value,
    member_principal,
    run_txn,
    server_now,
)
from brandme_core.domains.social.clock import FixedTxnClock, SpannerTxnClock
from brandme_core.domains.social.decisions import DecisionLimits, DecisionService
from brandme_core.domains.social.notifications import NotificationService
from brandme_core.domains.social.relationships import RelationshipService
from brandme_core.domains.wardrobe.service import WardrobeService
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
US = timedelta(microseconds=1)


def key():
    return "k-" + uuid.uuid4().hex


def person(db):
    return member_principal(insert_member(db), MEMBER_SCOPES)


@pytest.fixture
def circle(spanner_db):
    rel = RelationshipService(spanner_db)
    owner = person(spanner_db)
    friends = [person(spanner_db) for _ in range(3)]
    for f in friends:
        rel.accept(f, rel.request(owner, f.member_id)["relationship_id"])
    w = WardrobeService(spanner_db)
    item = w.create_items(owner, {"source": "manual", "title": "Blazer", "category": "outerwear"}, key())["items"][0]["id"]
    alt = w.create_items(friends[0], {"source": "manual", "title": "Cardigan", "category": "top"}, key())["items"][0]["id"]
    return owner, friends, item, alt


def body(item, recipients, **kw):
    b = {"subject_type": "wardrobe_item", "subject_id": item, "prompt": "Wear this tonight?",
         "recipient_ids": [r.member_id for r in recipients], "duration_seconds": 300, "discussion_mode": "blind_until_response"}
    b.update(kw)
    return b


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_server_owns_audience_and_five_minute_deadline(spanner_db, circle):
    """BM-SOC-002 with the production clock."""
    owner, friends, item, _ = circle
    svc = DecisionService(spanner_db)  # SpannerTxnClock
    before = run_txn(spanner_db, server_now)
    d = svc.create(owner, body(item, friends[:2]), key())
    after = run_txn(spanner_db, server_now)
    opened, closes = ts(d["opened_at"]), ts(d["closes_at"])
    assert before <= opened <= after
    assert closes - opened == timedelta(seconds=300)
    assert d["state"] == "open" and d["duration_seconds"] == 300 and 295 <= d["remaining_seconds"] <= 300
    assert sorted(d["audience"]) == sorted(f.member_id for f in friends[:2])
    # Only the offered windows (180/300/600/900 s); no smuggled fields (e.g. a client deadline).
    for bad in (body(item, friends, duration_seconds=240), body(item, friends, duration_seconds=300.0 + 1),
                {**body(item, friends), "closes_at": "2099-01-01T00:00:00Z"}):
        with pytest.raises(ValidationFailed):
            svc.create(owner, bad, key())
    # Non-friends cannot be invited.
    stranger = person(spanner_db)
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.create(owner, body(item, [friends[2], stranger]), key())
    assert e.value.extra["ineligible_recipient_ids"] == [stranger.member_id]
    # The audience was notified, the excluded friend was not.
    notes = NotificationService(spanner_db)
    assert [n["payload"]["decision_id"] for n in notes.list(friends[0])["items"] if n["type"] == "decision_request"] == [d["decision_id"]]
    assert [n for n in notes.list(friends[2])["items"] if n["type"] == "decision_request"] == []


def test_server_clock_rejects_late_response(spanner_db, circle):
    """BM-SOC-005 with the production clock: the deadline is compared with
    Spanner's time inside the responding transaction, not any client time."""
    owner, friends, item, _ = circle
    svc = DecisionService(spanner_db)
    d = svc.create(owner, body(item, friends), key())
    assert svc.respond(friends[0], d["decision_id"], {"choice": "yes"})["revision"] == 1

    def expire(t):  # simulate five minutes passing: move the stored server deadline into the past
        now = server_now(t)
        t.execute_update("UPDATE Decisions SET closes_at=@c WHERE member_id=@m AND decision_id=@d",
                         params={"c": now - US, "m": owner.member_id, "d": d["decision_id"]},
                         param_types={"c": param_types.TIMESTAMP,
                                      "m": param_types.STRING,
                                      "d": param_types.STRING})

    run_txn(spanner_db, expire)
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.respond(friends[1], d["decision_id"], {"choice": "pass"})
    assert e.value.code == "decision_closed" and ts(e.value.extra["server_time"]) >= ts(e.value.extra["closes_at"])
    # Changing an existing answer after the deadline is equally refused.
    with pytest.raises(DetailedInvalidTransition):
        svc.respond(friends[0], d["decision_id"], {"choice": "pass"})


def test_exact_deadline_boundary(spanner_db, circle):
    """BM-SOC-005: accepted iff server time < closes_at. At closes_at and after: rejected."""
    owner, friends, item, _ = circle
    clock = FixedTxnClock(NOW)
    svc = DecisionService(spanner_db, clock=clock)
    d = svc.create(owner, body(item, friends), key())
    closes = ts(d["closes_at"])
    assert closes == NOW + timedelta(seconds=300)
    clock.set(closes - US)
    assert svc.respond(friends[0], d["decision_id"], {"choice": "yes"})["submitted_at"] == (closes - US).isoformat().replace("+00:00", "Z")
    for t in (closes, closes + US, closes + timedelta(hours=1)):
        clock.set(t)
        with pytest.raises(DetailedInvalidTransition) as e:
            svc.respond(friends[1], d["decision_id"], {"choice": "pass"})
        assert e.value.code == "decision_closed"
    clock.set(closes)
    assert svc.close_due() == {"closed": 1, "skipped": 0}
    got = svc.get(owner, d["decision_id"])
    assert got["state"] == "closed" and got["result"]["yes"] == 1 and got["result"]["pass"] == 0
    assert [r["eligible"] for r in got["responses"]] == [True]
    # The scheduler does not close early.
    d2 = svc.create(owner, body(item, friends[:1], prompt="Second?"), key())
    clock.set(ts(d2["closes_at"]) - US)
    assert svc.close_due() == {"closed": 0, "skipped": 0}
    assert svc.get(owner, d2["decision_id"])["state"] == "open"


def test_votes_and_alternative_reference(spanner_db, circle):
    """BM-SOC-004."""
    owner, friends, item, alt = circle
    svc = DecisionService(spanner_db, clock=FixedTxnClock(NOW), catalog_check=lambda _t, pid: False)
    d = svc.create(owner, body(item, friends, discussion_mode="open"), key())
    did = d["decision_id"]
    assert svc.respond(friends[0], did, {"choice": "alternative", "alternative_ref": alt, "note": "Try mine"})["revision"] == 1
    with pytest.raises(ValidationFailed):  # not visible to friend 1 (it is friend 0's item)
        svc.respond(friends[1], did, {"choice": "alternative", "alternative_ref": alt})
    with pytest.raises(ValidationFailed):
        svc.respond(friends[1], did, {"choice": "alternative"})
    with pytest.raises(ValidationFailed):
        svc.respond(friends[1], did, {"choice": "yes", "alternative_ref": alt})
    with pytest.raises(ValidationFailed):
        svc.respond(friends[1], did, {"choice": "maybe"})
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.respond(owner, did, {"choice": "yes"})
    assert e.value.code == "self_response"
    svc.respond(friends[1], did, {"choice": "yes"})
    svc.respond(friends[2], did, {"choice": "pass"})
    # A changed answer is a new revision of the same record; an identical replay is a no-op.
    assert svc.respond(friends[1], did, {"choice": "pass"})["revision"] == 2
    again = svc.respond(friends[1], did, {"choice": "pass"})
    assert again["revision"] == 2 and again["unchanged"] is True
    got = svc.get(owner, did)
    assert sorted((r["respondent_id"], r["choice"]) for r in got["responses"]) == sorted(
        [(friends[0].member_id, "alternative"), (friends[1].member_id, "pass"), (friends[2].member_id, "pass")])
    assert count(spanner_db, "SELECT COUNT(*) FROM DecisionResponses WHERE decision_id=@d", d=did) == 3


def test_private_decision_invisible_to_unrelated_member(spanner_db, circle):
    """BM-SOC-003."""
    owner, friends, item, _ = circle
    svc = DecisionService(spanner_db, clock=FixedTxnClock(NOW))
    d = svc.create(owner, body(item, friends[:1]), key())
    outsider = friends[2]  # even a friend of the owner who was not invited
    stranger = person(spanner_db)
    for who in (outsider, stranger):
        with pytest.raises(NotFound) as e:
            svc.get(who, d["decision_id"])
        assert "Blazer" not in str(e.value) and item not in str(e.value)
        with pytest.raises(NotFound):
            svc.respond(who, d["decision_id"], {"choice": "yes"})
        assert svc.list(who)["items"] == []
    missing = str(uuid.uuid4())
    with pytest.raises(NotFound) as e2:
        svc.get(stranger, missing)
    assert e2.value.code == "not_found"  # identical to the unauthorized case


def test_blind_until_response(spanner_db, circle):
    """BM-SOC-007."""
    owner, friends, item, _ = circle
    clock = FixedTxnClock(NOW)
    svc = DecisionService(spanner_db, clock=clock)
    d = svc.create(owner, body(item, friends), key())
    did = d["decision_id"]
    svc.respond(friends[0], did, {"choice": "yes", "note": "Love it"})
    view = svc.get(friends[1], did)
    assert view["responses"] == [] and view["responses_hidden_until_you_answer"] is True and view["my_response"] is None
    assert "Love it" not in str(view) and "yes" not in str(view["responses"])
    assert len(svc.get(owner, did)["responses"]) == 1  # the creator sees results
    svc.respond(friends[1], did, {"choice": "pass"})
    view = svc.get(friends[1], did)
    assert view["responses_hidden_until_you_answer"] is False
    assert sorted(r["choice"] for r in view["responses"]) == ["pass", "yes"]
    # After close, non-respondents may see the outcome.
    clock.set(NOW + timedelta(seconds=300))
    svc.close_due()
    assert svc.get(friends[2], did)["responses_hidden_until_you_answer"] is False


def test_zero_replies_is_truthful(spanner_db, circle):
    """BM-SOC-008 (server side): no fabricated responses, explicit next actions."""
    owner, friends, item, _ = circle
    clock = FixedTxnClock(NOW)
    svc = DecisionService(spanner_db, clock=clock)
    d = svc.create(owner, body(item, friends), key())
    clock.set(NOW + timedelta(seconds=301))
    svc.close_due()
    got = svc.get(owner, d["decision_id"])
    assert got["state"] == "closed" and got["responses"] == [] and got["response_count"] == 0
    assert got["result"] == {"yes": 0, "pass": 0, "alternative": 0, "label": "No replies this time", "zero_replies": True}
    assert got["next_actions"] == ["save", "ask_again_as_new_request"]
    with pytest.raises(DetailedInvalidTransition):  # a closed decision cannot be cancelled
        svc.cancel(owner, d["decision_id"])
    out = svc.record_outcome(owner, d["decision_id"], "saved")
    assert out["label"] == "self-reported"


def test_concurrent_replays_one_response_one_close(spanner_db, circle):
    """BM-SOC-006: duplicate responses, owner close and expiry run concurrently."""
    owner, friends, item, _ = circle
    clock = FixedTxnClock(NOW)
    svc = DecisionService(spanner_db, clock=clock)
    d = svc.create(owner, body(item, friends), key())
    did = d["decision_id"]
    errors = []

    def run(fn):
        try:
            fn()
        except DetailedInvalidTransition as e:  # decision_closed is an allowed outcome once closed
            if e.code not in ("decision_closed",):
                errors.append(e)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    # 1) Ten identical replays of one answer: one record, one revision, one event.
    threads = [threading.Thread(target=run, args=(lambda: svc.respond(friends[0], did, {"choice": "yes"}),)) for _ in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors
    assert count(spanner_db, "SELECT COUNT(*) FROM DecisionResponses WHERE decision_id=@d", d=did) == 1
    assert count(spanner_db, "SELECT COUNT(*) FROM DecisionResponses WHERE decision_id=@d AND revision=1", d=did) == 1
    assert count(spanner_db, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id=@d AND event_type='decision.responded'", d=did) == 1

    # 2) At the deadline: scheduler x6, owner close x3 and late responses race.
    clock.set(NOW + timedelta(seconds=300))
    jobs = [lambda: svc.close_due()] * 6 + [lambda: svc.close(owner, did)] * 3 + \
           [lambda: svc.respond(friends[1], did, {"choice": "pass"})] * 3
    threads = [threading.Thread(target=run, args=(j,)) for j in jobs]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors
    assert count(spanner_db, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id=@d AND event_type='decision.closed'", d=did) == 1
    assert count(spanner_db, "SELECT COUNT(*) FROM DecisionResponses WHERE decision_id=@d", d=did) == 1
    got = svc.get(owner, did)
    assert got["state"] == "closed" and got["result"]["yes"] == 1 and got["result"]["pass"] == 0
    with spanner_db.snapshot() as s:
        payload = list(s.execute_sql("SELECT payload FROM OutboxEvents WHERE aggregate_id=@d AND event_type='decision.closed'",
                                     params={"d": did}, param_types={"d": param_types.STRING}))[0][0]
    p = json_value(payload)
    assert p["eligible_respondent_ids"] == [friends[0].member_id] and p["zero_replies"] is False and p["repeat_request"] is False


def test_agent_without_send_authority_only_drafts(spanner_db, circle):
    """BM-SOC-012."""
    owner, friends, item, _ = circle
    svc = DecisionService(spanner_db, clock=FixedTxnClock(NOW))
    agent = member_principal(owner.member_id, MEMBER_SCOPES, delegation_id=str(uuid.uuid4()))
    d = svc.create(agent, body(item, friends[:2]), key())
    did = d["decision_id"]
    assert d["state"] == "draft" and d["requires_member_approval"] is True and d["closes_at"] is None
    assert count(spanner_db, "SELECT COUNT(*) FROM Notifications WHERE subject_ref=@s", s=f"decision:{did}") == 0
    assert count(spanner_db, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id=@d AND event_type='decision.opened'", d=did) == 0
    with pytest.raises(NotFound):  # recipients cannot see a draft
        svc.get(friends[0], did)
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.open_draft(agent, did)
    assert e.value.code == "member_approval_required"
    # The member reviews the audience/action and sends it from their own session.
    review = svc.get(owner, did)
    assert review["state"] == "draft" and sorted(review["audience"]) == sorted(f.member_id for f in friends[:2])
    opened = svc.open_draft(owner, did)
    assert opened["state"] == "open" and opened["closes_at"] == (NOW + timedelta(seconds=300)).isoformat().replace("+00:00", "Z")
    assert count(spanner_db, "SELECT COUNT(*) FROM Notifications WHERE subject_ref=@s", s=f"decision:{did}") == 2
    # An agent that *was* granted social:send opens directly.
    sender = member_principal(owner.member_id, MEMBER_SCOPES | {"social:send"}, delegation_id=str(uuid.uuid4()))
    assert svc.create(sender, body(item, friends[2:], prompt="Other?"), key())["state"] == "open"


def test_rate_limits_and_repeat_flag(spanner_db, circle):
    owner, friends, item, _ = circle
    clock = FixedTxnClock(NOW)
    svc = DecisionService(spanner_db, clock=clock, limits=DecisionLimits(per_day=3, concurrent_open=2))
    a = svc.create(owner, body(item, friends[:1]), key())
    b = svc.create(owner, body(item, friends[:1]), key())  # identical request: allowed, flagged
    assert a["repeat_request"] is False and b["repeat_request"] is True
    with pytest.raises(RateLimited) as e:
        svc.create(owner, body(item, friends[1:2], prompt="Third"), key())
    assert e.value.extra == {"limit": "concurrent_open"}
    clock.set(NOW + timedelta(seconds=300))
    svc.close_due()
    svc.create(owner, body(item, friends[1:2], prompt="Third"), key())
    with pytest.raises(RateLimited) as e:
        svc.create(owner, body(item, friends[2:], prompt="Fourth"), key())
    assert e.value.extra == {"limit": "per_day"}
    clock.set(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))  # next UTC day
    assert svc.create(owner, body(item, friends[2:], prompt="Fourth"), key())["state"] == "open"
    # Idempotent create: the same key returns the same decision, no second row.
    k = key()
    first = svc.create(owner, body(item, friends[:1], prompt="Keyed"), k)
    assert svc.create(owner, body(item, friends[:1], prompt="Keyed"), k)["decision_id"] == first["decision_id"]
    assert count(spanner_db, "SELECT COUNT(*) FROM Decisions WHERE decision_id=@d", d=first["decision_id"]) == 1


def test_production_clock_is_spanner():
    assert isinstance(DecisionService(None).clock, SpannerTxnClock)


def test_opening_a_draft_drops_unreachable_recipients_and_rechecks_repeats(spanner_db, circle):
    owner, friends, item, _ = circle
    rel = RelationshipService(spanner_db)
    clock = FixedTxnClock(NOW)
    svc = DecisionService(spanner_db, clock=clock)
    agent = member_principal(owner.member_id, MEMBER_SCOPES, delegation_id=str(uuid.uuid4()))
    draft = svc.create(agent, body(item, friends[:2], prompt="Drafted?"), key())
    early = svc.create(agent, body(item, friends[:2], prompt="Drafted?"), key())  # identical, also unsent
    assert draft["repeat_request"] is False and early["repeat_request"] is False  # unsent drafts are never repeats
    rel.remove(owner, friends[1].member_id)  # no longer friends when the draft is sent
    opened = svc.open_draft(owner, draft["decision_id"])
    assert opened["repeat_request"] is False
    with pytest.raises(NotFound):  # the dropped recipient can neither read nor answer it
        svc.get(friends[1], draft["decision_id"])
    with pytest.raises(NotFound):
        svc.respond(friends[1], draft["decision_id"], {"choice": "yes"})
    assert draft["decision_id"] not in [d["decision_id"] for d in svc.list(friends[1])["items"]]
    assert svc.respond(friends[0], draft["decision_id"], {"choice": "pass"})["revision"] == 1
    # The identical draft sent afterwards is a repeat of the one actually sent first.
    clock.set(NOW + timedelta(seconds=300))
    svc.close_due()
    assert svc.open_draft(owner, early["decision_id"])["repeat_request"] is True
