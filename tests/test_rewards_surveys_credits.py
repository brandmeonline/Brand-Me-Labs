"""Ultra plan 02 item 5 on the Spanner emulator: daily-capped surveys and quizzes
feeding points, and points → in-app purchase credit only (never cash)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from brandme_core.domains.persona.kernel import (
    DetailedInvalidTransition,
    Forbidden,
    NotFound,
    ValidationFailed,
    command,
    member_principal,
    run_read,
    run_txn,
    service_principal,
)
from brandme_core.domains.rewards import ledger
from brandme_core.domains.rewards.api import create_rewards_router
from brandme_core.domains.rewards.benefits import BenefitService
from brandme_core.domains.rewards.credits import CreditService, apply_credit
from brandme_core.domains.rewards.rules import RULES
from brandme_core.domains.rewards.service import RewardsService
from brandme_core.domains.rewards.surveys import SurveyService
from test_persona_harness import MEMBER_SCOPES, count, insert_member, spanner_db  # noqa: F401

OPS = frozenset({"moderation:admin"})
WRITER = MEMBER_SCOPES | {"rewards:read", "rewards:write"}


def key():
    return "k-" + uuid.uuid4().hex


def person(db):
    return member_principal(insert_member(db), WRITER)


def operator(db):
    return member_principal(insert_member(db), OPS)


def grant(db, member_id, months=5):
    """1000 points: verified repairs spread over past months (200 a month is the rule's cap)."""
    for month in range(1, months + 1):
        for _ in range(4):
            command(db, service_principal("repair-workflow"), lambda t, ctx, month=month: ledger.credit(
                t, ctx, member_id, RULES["verified_repair"], str(uuid.uuid4()), datetime(2025, month, 15, tzinfo=timezone.utc), ["repair:test"]))


def account(db, member_id):
    return run_read(db, lambda s: ledger.load_account(s, member_id))


SURVEY = {"kind": "survey", "purpose": "style", "title": "Your weekend wardrobe", "questions": [
    {"id": "fit", "prompt": "Which fit do you reach for?", "type": "single", "options": ["Relaxed", "Tailored"]},
    {"id": "colours", "prompt": "Colours you wear most", "type": "multi", "options": ["Navy", "Olive", "Cream"]},
    {"id": "comfort", "prompt": "How much does comfort matter?", "type": "scale"},
]}
QUIZ = {"kind": "quiz", "purpose": "house_knowledge", "title": "Know your linen", "questions": [
    {"id": "q1", "prompt": "Linen is made from", "type": "single", "options": ["Flax", "Hemp", "Cotton"], "answer": "Flax"},
    {"id": "q2", "prompt": "Linen gets softer with", "type": "single", "options": ["Washing", "Ironing"], "answer": "Washing"},
]}
ANSWERS = {"answers": {"fit": "Relaxed", "colours": ["Navy", "Cream"], "comfort": 4}}


def test_operators_publish_only_well_formed_surveys(spanner_db):
    svc = SurveyService(spanner_db)
    with pytest.raises(Forbidden):
        svc.create_survey(person(spanner_db), SURVEY)
    op = operator(spanner_db)
    q = SURVEY["questions"]
    for bad in ({**SURVEY, "questions": []}, {**SURVEY, "questions": q * 4}, {**SURVEY, "purpose": "health"}, {**SURVEY, "kind": "poll"},
                {**SURVEY, "questions": [q[0], q[0]]}, {**SURVEY, "questions": [{**q[0], "answer": "Relaxed"}]},
                {**SURVEY, "questions": [{**q[2], "options": ["a", "b"]}]}, {**SURVEY, "questions": [{**q[0], "options": ["a"]}]},
                {**SURVEY, "questions": [{**q[0], "options": ["a", "a"]}]}, {**SURVEY, "questions": [{**q[0], "id": "has space"}]},
                {**QUIZ, "questions": [{**QUIZ["questions"][0], "answer": "Wool"}]}, {**QUIZ, "questions": [q[1]]},
                {**SURVEY, "audience": "everyone"}):
        with pytest.raises(ValidationFailed):
            svc.create_survey(op, bad)
    assert svc.create_survey(op, QUIZ)["kind"] == "quiz"


def test_answer_once_daily_capped_points_and_quiz_keys_after(spanner_db):
    db = spanner_db
    op, me = operator(db), person(db)
    svc = SurveyService(db)
    ids = [svc.create_survey(op, {**SURVEY, "title": f"Survey {i}"})["survey_id"] for i in range(3)]
    quiz = svc.create_survey(op, QUIZ)["survey_id"]
    listed = svc.available(me)
    mine = {i["survey_id"]: i for i in listed["items"]}
    assert set(ids) | {quiz} <= set(mine) and listed["today"]["rewarded_remaining"] == 3
    assert all("answer" not in q for q in mine[quiz]["questions"])  # no answer key before answering
    for bad in ({"answers": {"fit": "Relaxed"}}, {"answers": {**ANSWERS["answers"], "comfort": 6}},
                {"answers": {**ANSWERS["answers"], "colours": ["Navy", "Navy"]}}, {"answers": {**ANSWERS["answers"], "fit": "Baggy"}},
                {"answers": {**ANSWERS["answers"], "comfort": 4.0}}, {"answers": {**ANSWERS["answers"], "extra": 1}}, {"score": 3}):
        with pytest.raises(ValidationFailed):
            svc.respond(me, ids[0], bad, key())
    agent = member_principal(me.member_id, WRITER, delegation_id=str(uuid.uuid4()))
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.respond(agent, ids[0], ANSWERS, key())
    assert e.value.code == "member_only"

    k = key()
    first = svc.respond(me, ids[0], ANSWERS, k)
    assert first["reward"] == {"status": "posted", "points": 10}
    assert svc.respond(me, ids[0], ANSWERS, k) == first  # idempotent replay
    with pytest.raises(DetailedInvalidTransition) as e:
        svc.respond(me, ids[0], ANSWERS, key())
    assert e.value.code == "already_answered"
    svc.respond(me, ids[1], ANSWERS, key())
    scored = svc.respond(me, quiz, {"answers": {"q1": "Flax", "q2": "Ironing"}}, key())
    assert (scored["score"], scored["out_of"], scored["correct"]) == (1, 2, {"q1": "Flax", "q2": "Washing"})
    # The fourth completion of the UTC day is recorded but earns nothing.
    assert svc.respond(me, ids[2], ANSWERS, key())["reward"] == {"status": "capped", "points": 0}
    assert account(db, me.member_id).available == 30
    left = svc.available(me)
    assert left["today"]["rewarded_remaining"] == 0 and not {i["survey_id"] for i in left["items"]} & (set(ids) | {quiz})
    # Closed surveys take no more answers.
    other = person(db)
    svc.deactivate(op, ids[0])
    with pytest.raises(NotFound):
        svc.respond(other, ids[0], ANSWERS, key())


def test_points_become_in_app_credit_only(spanner_db):
    db = spanner_db
    me = person(db)
    grant(db, me.member_id)
    credits = CreditService(db)
    for bad in ({"points": 450}, {"points": 550}, {"points": 500.0}, {"points": True}, {"points": "500"}, {"points": 200_000},
                {"points": 500, "currency": "EUR"}, {"points": 500, "payout_account": "acct_1"}, {"points": 500, "member_id": str(uuid.uuid4())}):
        with pytest.raises(ValidationFailed):
            credits.convert(me, bad, key())
    with pytest.raises(DetailedInvalidTransition) as e:
        credits.convert(member_principal(me.member_id, WRITER, delegation_id=str(uuid.uuid4())), {"points": 500}, key())
    assert e.value.code == "member_only"

    k = key()
    c = credits.convert(me, {"points": 500}, k)
    assert c["amount"] == {"minor": 500, "currency": "USD"} and c["state"] == "available" and "not cash" in c["usable"]
    assert credits.convert(me, {"points": 500}, k)["credit_id"] == c["credit_id"]  # replay converts once
    acct = account(db, me.member_id)
    assert (acct.available, acct.reserved) == (500, 500)  # held while the credit is outstanding
    with pytest.raises(DetailedInvalidTransition) as e:
        credits.convert(me, {"points": 600}, key())
    assert e.value.code == "insufficient_points"

    # Only the in-app checkout spends it, in its own currency, once.
    with pytest.raises(DetailedInvalidTransition) as e:
        run_txn(db, lambda t: apply_credit(t, member_id=me.member_id, credit_id=c["credit_id"], order_ref="order-1", currency="EUR"))
    assert e.value.code == "credit_currency_mismatch"
    stranger = insert_member(db)
    with pytest.raises(NotFound):
        run_txn(db, lambda t: apply_credit(t, member_id=stranger, credit_id=c["credit_id"], order_ref="order-1", currency="USD"))
    used = run_txn(db, lambda t: apply_credit(t, member_id=me.member_id, credit_id=c["credit_id"], order_ref="order-1", currency="USD"))
    assert used["amount"] == {"minor": 500, "currency": "USD"}
    with pytest.raises(DetailedInvalidTransition) as e:
        run_txn(db, lambda t: apply_credit(t, member_id=me.member_id, credit_id=c["credit_id"], order_ref="order-2", currency="USD"))
    assert e.value.code == "credit_unavailable"
    acct = account(db, me.member_id)
    assert (acct.available, acct.reserved, acct.spent_total) == (500, 0, 500)

    # Unused credit expires after its year and the points come back.
    c2 = credits.convert(me, {"points": 500}, key())
    run_txn(db, lambda t: t.execute_update("UPDATE PurchaseCredits SET expires_at=TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 MINUTE) "
                                           f"WHERE member_id='{me.member_id}' AND credit_id='{c2['credit_id']}'"))
    assert credits.expire_due() >= 1
    assert {i["credit_id"]: i["state"] for i in credits.mine(me)["items"]} == {c["credit_id"]: "applied", c2["credit_id"]: "expired"}
    acct = account(db, me.member_id)
    assert (acct.available, acct.reserved) == (500, 0)
    kinds = {r for (r,) in run_read(db, lambda s: list(s.execute_sql(f"SELECT DISTINCT kind FROM RewardEntries WHERE member_id='{me.member_id}'")))}
    assert kinds == {"credit", "reserve", "redeem", "release"}


def test_the_ledger_has_no_way_to_pay_out(spanner_db):
    me = person(spanner_db)
    with pytest.raises(Exception, match="ck_re_kind"):
        run_txn(spanner_db, lambda t: ledger.insert_entry(t, member_id=me.member_id, entry_id=str(uuid.uuid4()), kind="payout", state="posted",
                                                          points=100, available_delta=-100, actor_ref="member:x"))
    r = create_rewards_router(RewardsService(spanner_db), BenefitService(spanner_db), lambda _r: None, None, SurveyService(spanner_db),
                              CreditService(spanner_db))
    paths = {(m, route.path) for route in r.routes for m in route.methods}
    assert ("POST", "/rewards/credits") in paths
    assert not [p for _m, p in paths if any(w in p for w in ("payout", "cash", "withdraw", "transfer", "gift"))]
    assert count(spanner_db, "SELECT COUNT(*) FROM RewardEntries WHERE member_id=@m", m=me.member_id) == 0


def reverse_all_awards(db, member_id):
    ids = [r[0] for r in run_read(db, lambda s: list(s.execute_sql(
        f"SELECT entry_id FROM RewardEntries WHERE member_id='{member_id}' AND kind='credit' AND state='posted'")))]
    for entry_id in ids:
        command(db, service_principal("repair-workflow"), lambda t, ctx, e=entry_id: ledger.reverse(t, ctx, member_id, e, "repair_voided", ["repair:test"]))


def test_released_credit_pays_down_recovery_debt_first(spanner_db):
    from brandme_core.domains.rewards import deletion

    db = spanner_db
    me, other = person(db), person(db)
    for m in (me, other):
        grant(db, m.member_id)
        CreditService(db).convert(m, {"points": 500}, key())
        reverse_all_awards(db, m.member_id)  # 1000 reversed: 500 taken from available, 500 owed while held in credit
        acct = account(db, m.member_id)
        assert (acct.available, acct.reserved, acct.recovery_due) == (0, 500, 500)
    # Deleting the credit releases its points, which settle the debt instead of becoming spendable again.
    run_txn(db, lambda t: deletion.delete_category(t, me.member_id, "rewards.credits"))
    # Expiry releases the same way.
    run_txn(db, lambda t: t.execute_update(f"UPDATE PurchaseCredits SET expires_at=TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 MINUTE) "
                                           f"WHERE member_id='{other.member_id}'"))
    assert CreditService(db).expire_due() >= 1
    for m in (me, other):
        acct = account(db, m.member_id)
        assert (acct.available, acct.reserved, acct.recovery_due) == (0, 0, 0)
        assert run_read(db, lambda s, m=m: ledger.consistency(s, m.member_id))["ok"]


def test_a_credit_outlives_a_deleted_ledger_without_breaking_it(spanner_db):
    from brandme_core.domains.rewards import deletion

    db = spanner_db
    me = person(db)
    grant(db, me.member_id)
    credits = CreditService(db)
    spend, lapse = (credits.convert(me, {"points": 500}, key())["credit_id"] for _ in range(2))
    run_txn(db, lambda t: deletion.delete_category(t, me.member_id, "rewards.ledger"))  # the points and their history go
    grant(db, me.member_id, months=1)  # a new account, with points earned since
    # The converted credit is still the member's: it spends and expires without touching the new account.
    assert run_txn(db, lambda t: apply_credit(t, member_id=me.member_id, credit_id=spend, order_ref="order-1", currency="USD"))["credit_id"] == spend
    run_txn(db, lambda t: t.execute_update(f"UPDATE PurchaseCredits SET expires_at=TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 MINUTE) "
                                           f"WHERE member_id='{me.member_id}' AND credit_id='{lapse}'"))
    assert credits.expire_due() >= 1
    assert {i["credit_id"]: i["state"] for i in credits.mine(me)["items"]} == {spend: "applied", lapse: "expired"}
    acct = account(db, me.member_id)
    assert (acct.available, acct.reserved, acct.spent_total) == (200, 0, 0)
    assert run_read(db, lambda s: ledger.consistency(s, me.member_id))["ok"]


def test_nothing_posts_points_while_the_ledger_is_frozen(spanner_db):
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

    db = spanner_db
    op, me = operator(db), person(db)
    grant(db, me.member_id)
    before = account(db, me.member_id)
    survey = SurveyService(db).create_survey(op, {**SURVEY, "title": "Frozen ledger"})["survey_id"]
    run_txn(db, lambda t: t.insert("ProcessingFreezes", columns=("subject_ref", "category", "reason", "deletion_job_id", "created_at"),
                                   values=[(me.member_id, "rewards.ledger", "deletion", str(uuid.uuid4()), COMMIT_TIMESTAMP)]))
    for attempt in (lambda: SurveyService(db).respond(me, survey, ANSWERS, key()), lambda: CreditService(db).convert(me, {"points": 500}, key())):
        with pytest.raises(DetailedInvalidTransition) as e:
            attempt()
        assert e.value.code == "processing_frozen"
    # Refused, not answered without pay: the member can answer once the deletion is done.
    assert count(db, "SELECT COUNT(*) FROM SurveyResponses WHERE member_id=@m", m=me.member_id) == 0
    assert count(db, "SELECT COUNT(*) FROM PurchaseCredits WHERE member_id=@m", m=me.member_id) == 0
    assert account(db, me.member_id) == before
