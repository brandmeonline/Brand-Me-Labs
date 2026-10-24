"""Delegated budget: a rolling-window cap that includes in-flight reservations (ch.05 §5).

A credit (a void, an expired hold, a reduced capture, a refund credited back) is
observed after the purchase it offsets. It belongs to that purchase's window and can
never give back more than that purchase consumed, so a late credit cannot open new
headroom in the current window. Runs on both stores and both payment rails.
"""

from dataclasses import replace
from datetime import timedelta

import pytest

from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.domains.commerce.errors import BudgetExceeded
from brandme_core.domains.commerce.money import Money
from brandme_core.domains.commerce.records import BudgetEntry
from brandme_core.domains.commerce.store import new_id
from brandme_core.domains.providers.local_atelier import PROVIDER_ID
from tests.fixtures.commerce.harness import AGENT_CLIENT, agent, limits, line
from tests.fixtures.commerce.stores import _spanner_db, commerce_store  # noqa: F401  (fixtures)
from tests.test_commerce_payments_flow import _hook, _order, rail_world

DAY = 86400
CAP = 20_000
OVERSHIRT = 9612  # 8900 + 8% tax, all-in


@pytest.fixture(params=["simulated", "stripe_double"])
def w(request, commerce_store):
    return rail_world(request.param, commerce_store)


def _one_day_grant(w):
    """A buy-within-rules grant: CAP per rolling day, valid for 30 days (longer than a 7-day hold)."""
    lim = replace(limits(per_order=CAP, cumulative=CAP), window_seconds=DAY)
    d = w.svc.create_delegation(w.member, client_id=AGENT_CLIENT, mode=AssistanceMode.BUY_WITHIN_RULES,
                                allowed_providers={PROVIDER_ID}, limits=lim,
                                expires_at=w.clock.now + timedelta(days=30))
    return d, agent(d.id, d.scopes)


def _buy(w, ag, size, n):
    _, quote, op = w.prepared(ag, line("overshirt", size))
    assert quote.total == Money(OVERSHIRT, "USD")
    return w.svc.execute_purchase(ag, operation_id=op.id, approval_id=w.approve(op).id,
                                  idempotency_key=f"budget-window-buy-{n:04d}")


def _available(w, d):
    return w.svc.available_budget(w.store.get("delegations", d.id)).amount_minor


def test_a_late_void_credit_does_not_open_headroom_in_a_later_window(w):
    d, ag = _one_day_grant(w)
    old = _order(w, _buy(w, ag, "m", 1))  # day 0: authorized, never captured
    w.clock.advance(days=2)  # the day-0 reservation has left the 1-day window
    assert _available(w, d) == CAP
    assert _buy(w, ag, "s", 2).state == "accepted"
    # The agent cancels its own day-0 order now: the void is observed, and credited, on day 2.
    assert w.svc.request_cancellation(ag, old.id, idempotency_key="budget-window-cancel-1")["status"] == "cancelled"
    assert _available(w, d) == CAP - OVERSHIRT  # the day-0 credit offsets only the day-0 spend
    assert _buy(w, ag, "l", 3).state == "accepted"
    with pytest.raises(BudgetExceeded):  # a third order in the day would be 28836 against 20000
        _buy(w, ag, "m", 4)
    assert w.provider.submit_calls and len(w.provider.submit_calls) == 3


def test_an_expired_hold_credited_after_the_window_adds_no_headroom(w):
    d, ag = _one_day_grant(w)
    old = _order(w, _buy(w, ag, "m", 1))
    w.clock.advance(days=7, seconds=5)  # past the processor's 7-day hold
    assert _buy(w, ag, "s", 2).state == "accepted"
    _hook(w, w.provider.ship(old.provider_order_ref))  # the service observes the released hold now
    assert w.store.get("orders", old.id).payment_status == "voided"
    assert _available(w, d) == CAP - OVERSHIRT
    assert _buy(w, ag, "l", 3).state == "accepted"
    with pytest.raises(BudgetExceeded):
        _buy(w, ag, "m", 4)


def test_a_credit_in_its_own_window_still_frees_the_budget(w):
    d, ag = _one_day_grant(w)
    old = _order(w, _buy(w, ag, "m", 1))
    assert _available(w, d) == CAP - OVERSHIRT
    w.svc.request_cancellation(ag, old.id, idempotency_key="budget-window-cancel-1")
    assert _available(w, d) == CAP  # voided inside its own window: never spent


def test_credits_never_exceed_what_their_purchase_consumed(w):
    d, ag = _one_day_grant(w)
    first = _buy(w, ag, "m", 1)
    w.svc.request_cancellation(ag, _order(w, first).id, idempotency_key="budget-window-cancel-1")
    assert _buy(w, ag, "s", 2).state == "accepted" and _available(w, d) == CAP - OVERSHIRT
    # A second credit for the first purchase (a duplicate observation, a refund on top of a void)
    # cannot offset the second purchase's spend.
    extra = BudgetEntry(new_id(), d.id, first.id, Money(5_000, "USD"), "credit", "credited", w.clock())
    w.store.run(lambda tx: tx.put("reservations", (extra.delegation_id, extra.id), extra))
    assert _available(w, d) == CAP - OVERSHIRT
