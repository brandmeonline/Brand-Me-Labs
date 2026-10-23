"""Purchases end to end through the merchant's payment rail (ch.05 §6; BM-COM-009/010/011).

The commerce service is unchanged by the rail: it sees the merchant's order and its
payment status. Tests on the ``w`` fixture run on both stores and on both rails:

* ``simulated``: the deterministic simulated processor (deterministic app behaviour);
* ``stripe_double``: the real ``StripeTestPaymentProcessor`` over ``StripeSemanticsDouble`` —
  FIXTURE DOUBLE, NOT STRIPE (adapter logic, not Stripe behaviour).

stripe-mock (wire shape only) is ``test_providers_stripe_wire.py``; Stripe test mode
itself is ``test_commerce_stripe_live.py`` (``not_run`` without ``STRIPE_TEST_SECRET_KEY``).
"""

import json
import os
from datetime import timedelta

import pytest

from brandme_core.domains.commerce.errors import Forbidden, InvalidRequest
from brandme_core.domains.commerce.money import Money
from brandme_core.domains.providers.contracts import ProviderError, ProviderErrorKind, SubmitRequest
from brandme_core.domains.providers.local_atelier import (
    PAYMENT_SETTLE_WINDOW, Behavior, LocalAtelierProvider, local_atelier_connection, payment_key,
)
from brandme_core.domains.providers.payments import TEST_CARD_NEEDS_AUTHENTICATION
from brandme_core.domains.providers.payments.simulated import PaymentBehavior
from tests.fixtures.commerce.harness import limits, line, world
from tests.fixtures.commerce.stores import _spanner_db, commerce_store  # noqa: F401  (fixtures)
from tests.fixtures.providers import stripe_events
from tests.fixtures.providers.stripe_double import StripeSemanticsDouble

SK_TEST = "sk_" + "test_" + "0" * 24  # built at runtime: no key-shaped literal in the repo
STRIPE_METHOD = {"authorize": "create_payment_intent", "capture": "capture_payment_intent",
                 "void": "cancel_payment_intent", "refund": "create_refund"}


def stripe_double_rail(clock, *, secret=None, double=None):
    """The real Stripe processor over the semantics double (fixture double, not Stripe)."""
    from brandme_core.domains.providers.payments.stripe_test import StripeTestConfig, StripeTestPaymentProcessor
    double = double or StripeSemanticsDouble(clock)
    rail = StripeTestPaymentProcessor(StripeTestConfig(SK_TEST, webhook_secrets=(secret,) if secret else ()),
                                      wire=double, environment="development", clock=clock, log=lambda r: None)
    rail.double = double  # test handle only
    return rail


def rail_world(rail, store=None, secret=None):
    if rail == "simulated":
        w = world(store=store)
    else:
        secret = secret or stripe_events.webhook_secret()
        w = world(store=store, payments=lambda clock: stripe_double_rail(clock, secret=secret))
        w.secret = secret
    w.rail = rail
    return w


@pytest.fixture(params=["simulated", "stripe_double"])
def w(request, commerce_store):
    return rail_world(request.param, commerce_store)


def _calls(w, op):
    """(op, idempotency key) of every money call the rail received, either rail."""
    if w.rail == "simulated":
        return [c for c in w.provider.payments.calls if c[0] == op]
    return [(op, key) for method, _, key in w.provider.payments.double.mutating_calls() if method == STRIPE_METHOD[op]]


def _lose_response(w, op):
    """The next ``op`` is applied by the processor, and its answer never arrives."""
    if w.rail == "simulated":
        w.provider.payments.arm(PaymentBehavior.TIMEOUT_AFTER_ACCEPT if op == "authorize"
                                else PaymentBehavior.RESPONSE_LOST, op=op)
    else:
        w.provider.payments.double.lose_next(STRIPE_METHOD[op])


def _lose_request(w, op):
    """The next ``op`` never reaches the processor."""
    if w.rail == "simulated":
        w.provider.payments.arm(PaymentBehavior.LOST_BEFORE_PROCESSING, op=op)
    else:
        w.provider.payments.double.lose_next(STRIPE_METHOD[op], before=True)


def _held(w, order_ref):
    rec = w.provider._orders[order_ref]
    return w.provider.payments.lookup(rec.payment_ref)


def _buy(w, actor, *lines_, key="pay-flow-buy-0000001"):
    _, quote, op = w.prepared(actor, *(lines_ or [line()]))
    res = w.svc.execute_purchase(actor, operation_id=op.id, approval_id=w.approve(op).id, idempotency_key=key)
    return quote, res


def _order(w, res):
    order = w.store.get("orders", res.order_id)
    # The first observation after acceptance shows the authorization (acceptance itself is not payment).
    w.svc._apply_observation(order.id, w.provider.lookup(order.provider_order_ref), "system:reconciler")
    return w.store.get("orders", order.id)


def _hook(w, deliveries):
    for headers, body in deliveries:
        w.svc.handle_webhook("demo_atelier", headers, body)


def _effects(w):
    return [e.payload["wardrobe_effect"] for e in w.store.outbox() if e.event_type == "commerce.order.observed"]


def test_authorized_at_submit_captured_at_first_shipment(w):
    quote, res = _buy(w, w.member, line("overshirt"), line("bag"))
    order = _order(w, res)
    assert res.state == "accepted" and order.payment_status == "authorized"
    pay = w.provider.payments.lookup(w.provider._orders[order.provider_order_ref].payment_ref)
    assert pay.authorized == quote.total and pay.captured == Money(0, "USD")
    w.provider.arm(Behavior.PARTIAL_FULFILLMENT, source_variant_ref="demo-bag-m", quantity=0)
    _hook(w, w.provider.ship(order.provider_order_ref))
    o = w.store.get("orders", order.id)
    assert o.payment_status == "captured" and o.fulfillment_status == "partially_fulfilled"
    assert w.provider.payments.lookup(pay.payment_ref).captured == quote.total  # one capture, the whole order
    assert _calls(w, "capture") == [
        ("capture", payment_key(w.store.get("operations", res.id).provider_idempotency_key, "capture"))]


def test_cancelling_before_capture_voids_the_hold_and_releases_the_budget(w):
    d, ag = w.delegate(lim=limits(refund_credit_back=False))  # a void is not a refund: released anyway
    quote, res = _buy(w, ag)
    order = _order(w, res)
    _hook(w, w.provider.cancel(order.provider_order_ref))
    o = w.store.get("orders", order.id)
    assert (o.order_status, o.payment_status, o.refunded_total) == ("cancelled", "voided", Money(0, "USD"))
    assert [l.quantity_cancelled for l in o.lines] == [1] and [l.quantity_returned for l in o.lines] == [0]
    assert w.store.get("operations", res.id).state == "cancelled"
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000, "USD")
    assert _effects(w)[-1] == "cancelled"


def test_partial_cancellation_before_capture_reduces_the_capture(w):
    d, ag = w.delegate(lim=limits())
    quote, res = _buy(w, ag, line("overshirt"), line("bag"))
    order = _order(w, res)
    _hook(w, w.provider.cancel(order.provider_order_ref, "demo-bag-m"))
    _hook(w, w.provider.ship(order.provider_order_ref))
    o = w.store.get("orders", order.id)
    bag = 12900 + 12900 * 800 // 10_000
    pay = w.provider.payments.lookup(w.provider._orders[order.provider_order_ref].payment_ref)
    assert pay.captured == Money(quote.total.amount_minor - bag, "USD")
    assert o.payment_status == "captured" and o.fulfillment_status == "fulfilled"  # every unit still owed arrived
    # The released remainder never counted as spend.
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000 - pay.captured.amount_minor, "USD")


def test_refund_before_delivery_cancels_units_instead_of_returning_them(w):
    _, res = _buy(w, w.member, line("overshirt"), line("bag"))
    order = _order(w, res)
    w.provider.arm(Behavior.PARTIAL_FULFILLMENT, source_variant_ref="demo-bag-m", quantity=0)
    _hook(w, w.provider.ship(order.provider_order_ref))  # captures; the bag has not shipped
    w.provider.arm(Behavior.REFUND, source_variant_ref="demo-bag-m", quantity=1)
    _hook(w, w.provider.refund(order.provider_order_ref))
    o = w.store.get("orders", order.id)
    bag = next(l for l in o.lines if l.source_variant_ref == "demo-bag-m")
    assert (bag.quantity_cancelled, bag.quantity_returned, bag.quantity_delivered) == (1, 0, 0)
    assert o.payment_status == "partially_refunded" and o.refunded_total == Money(12900 + 1032, "USD")
    assert o.fulfillment_status == "fulfilled"  # nothing else is owed
    assert all(l.quantity_returned <= l.quantity_delivered for l in o.lines)


def test_an_expired_hold_cancels_an_unshipped_order(w):
    _, res = _buy(w, w.member)
    order = _order(w, res)
    if w.rail == "simulated":
        w.provider.expire_authorization(order.provider_order_ref)  # the demo scenario's control
    else:
        w.clock.advance(days=7, seconds=1)  # the double expires the hold at capture_before
    _hook(w, w.provider.ship(order.provider_order_ref))
    o = w.store.get("orders", order.id)
    assert (o.order_status, o.payment_status) == ("cancelled", "voided")
    assert sum(l.quantity_shipped for l in o.lines) == 0 and _calls(w, "capture") == []


def test_a_declined_card_rejects_the_purchase_and_restocks(w):
    stock = dict(w.provider._stock)
    w.provider.arm(Behavior.REJECTED_AUTH)
    _, res = _buy(w, w.member)
    assert res.state == "rejected" and res.reason_code == "payment_authorization_declined"
    assert w.store.rows("orders") == [] and w.provider._stock == stock


def test_a_lost_payment_response_reconciles_without_a_second_authorization(w):
    _lose_response(w, "authorize")
    _, res = _buy(w, w.member)
    assert res.state == "outcome_unknown"
    done = w.svc.reconcile(res.id)  # the merchant finds the payment by purpose; it never re-sends
    assert done.state == "accepted" and w.store.get("orders", done.order_id).payment_status == "authorized"
    assert _calls(w, "authorize") == [
        ("authorize", payment_key(w.store.get("operations", res.id).provider_idempotency_key, "authorize"))]


def test_absence_of_a_payment_is_final_only_after_the_settle_window(w):
    stock = dict(w.provider._stock)
    _lose_request(w, "authorize")
    _, res = _buy(w, w.member)
    assert res.state == "outcome_unknown"
    assert w.svc.reconcile(res.id).state == "outcome_unknown"  # search may lag a fresh payment
    w.clock.advance(seconds=PAYMENT_SETTLE_WINDOW.total_seconds())
    done = w.svc.reconcile(res.id)
    assert done.state == "rejected" and done.reason_code == "not_found_at_provider"
    assert w.store.rows("orders") == [] and w.provider._stock == stock


def test_authentication_required_is_voided_never_redirected():
    from tests.fixtures.commerce.harness import Clock
    clock = Clock()
    p = LocalAtelierProvider(clock)
    cart = p.create_cart("fictional-demo-merchant", [line()])
    q = p.quote(cart)
    ack = p.submit(SubmitRequest("bm-sca-00000000000001", q.checkout_reference, "h", Money(9612, "USD"),
                                 TEST_CARD_NEEDS_AUTHENTICATION, (line(),)))
    assert not ack.accepted and ack.reason_code == "payment_authentication_required"
    voided = [c for c in p.payments.calls if c[0] == "void"]
    assert voided == [("void", "bm-sca-00000000000001:void")]


def test_stripe_payment_events_reach_the_order_once_and_only_as_a_hint():
    """FIXTURE DOUBLE, NOT STRIPE: the Stripe processor over StripeSemanticsDouble, events signed locally."""
    from brandme_core.domains.providers.payments.stripe_test import StripeTestConfig, StripeTestPaymentProcessor
    from tests.fixtures.providers import stripe_events
    from tests.fixtures.providers.stripe_double import StripeSemanticsDouble

    secret = stripe_events.webhook_secret()
    w = world()
    double = StripeSemanticsDouble(w.clock)
    rail = StripeTestPaymentProcessor(StripeTestConfig("sk_" + "test_" + "0" * 24, webhook_secrets=(secret,)),
                                      wire=double, environment="development", clock=w.clock)
    w.provider = LocalAtelierProvider(w.clock, payments=rail)
    w.registry._connections.clear()
    w.registry.register(local_atelier_connection(w.provider, "development", w.clock.now))
    _, res = _buy(w, w.member)
    order = w.store.get("orders", res.order_id)
    pi = w.provider._orders[order.provider_order_ref].payment_ref
    w.provider.capture(order.provider_order_ref)  # the processor changes state; Stripe would notify
    at = int(w.clock.now.timestamp())
    headers, body = stripe_events.payment_intent_event(double.intents[pi], "payment_intent.succeeded", secret, at,
                                                       event_id="evt_1TestDuplicate")
    before = len(w.store.outbox())
    first = w.svc.handle_webhook("demo_atelier", headers, body)
    again = w.svc.handle_webhook("demo_atelier", headers, body)  # duplicate delivery
    assert first.state == "applied" and again.event_id == first.event_id == "stripe_test:evt_1TestDuplicate"
    assert len(w.store.rows("webhook_receipts")) == 1 and len(w.store.outbox()) == before + 1
    assert w.store.get("orders", order.id).payment_status == "captured"  # re-read, not taken from the event
    with pytest.raises(ProviderError):
        w.svc.handle_webhook("demo_atelier", headers, body + b" ")  # tampered


# ----------------------------------------------------------------------- composition
SK_TEST = "sk_" + "test_" + "0" * 24  # built at runtime: no key-shaped literal in the repo
STRIPE = {"BRANDME_COMMERCE_PAYMENTS": "stripe_test"}


@pytest.mark.parametrize("environment,env,code", [
    ("development", STRIPE, "stripe_test_not_configured"),
    ("development", {**STRIPE, "STRIPE_TEST_SECRET_KEY": "sk_" + "live_" + "a" * 24}, "stripe_key_refused"),
    ("development", {**STRIPE, "STRIPE_TEST_SECRET_KEY": "pk_" + "test_" + "a" * 24}, "stripe_key_refused"),
    ("development", {**STRIPE, "STRIPE_TEST_SECRET_KEY": "whsec_" + "a" * 24}, "stripe_key_refused"),
    ("development", {**STRIPE, "STRIPE_TEST_SECRET_KEY": SK_TEST, "STRIPE_TEST_WEBHOOK_SECRET": "nope"},
     "stripe_webhook_secret_refused"),
    ("development", {**STRIPE, "STRIPE_TEST_SECRET_KEY": SK_TEST, "STRIPE_LOG": "debug"}, "stripe_log_refused"),
    ("development", {**STRIPE, "STRIPE_TEST_SECRET_KEY": SK_TEST, "STRIPE_LOG": " Info "}, "stripe_log_refused"),
    ("development", {**STRIPE, "STRIPE_TEST_SECRET_KEY": SK_TEST, "BRANDME_STRIPE_EGRESS_PROXY": "socks5://p:1"},
     "stripe_egress_proxy_refused"),
    ("development", {"BRANDME_COMMERCE_PAYMENTS": "paypal"}, "payments_rail_unknown"),
    ("production", {"BRANDME_COMMERCE_PAYMENTS": "simulated"}, "payments_rail_not_allowed"),
    ("sandbox", {**STRIPE, "STRIPE_TEST_SECRET_KEY": SK_TEST}, "payments_rail_not_allowed"),
    ("staging", {}, "environment_unknown"),
])
def test_composition_refuses_to_boot_rather_than_fall_back(environment, env, code):
    from brandme_core.domains.commerce.composition import CompositionError, build_providers
    from tests.fixtures.providers.stripe_double import StripeSemanticsDouble
    with pytest.raises(CompositionError) as e:
        build_providers(environment, env=env, stripe_wire_factory=StripeSemanticsDouble(lambda: None))
    assert e.value.code == code and "sk_" not in str(e.value) and "whsec_" not in str(e.value)


def test_composition_selects_the_rail_and_labels_it():
    from brandme_core.domains.commerce.composition import build_providers
    from tests.fixtures.commerce.harness import Clock
    from tests.fixtures.providers.stripe_double import StripeSemanticsDouble
    sim = build_providers("development", env={})
    assert sim.payments_rail == "simulated" and sim.demo_atelier.payments.simulation
    assert sim.payments is sim.demo_atelier.payments
    clock = Clock()
    stripe = build_providers("demo", env={**STRIPE, "STRIPE_TEST_SECRET_KEY": SK_TEST}, clock=clock,
                             stripe_wire_factory=StripeSemanticsDouble(clock))
    conn = stripe.registry.get("demo_atelier")
    assert stripe.demo_atelier.payments.processor_id == "stripe_test" and conn.simulation  # the merchant is fictional
    assert "Stripe test mode" in conn.disclosure and "no real money" in conn.disclosure
    assert conn.capability("checkout.submit").state == "sandbox"
    assert conn.capability("checkout.submit").evidence_ref is None  # nothing exercised yet
    assert conn.payment_rail.mode == "sandbox" and conn.payment_rail.environment == "demo"
    assert build_providers("production", env={}).registry.all() == []  # no simulated merchant outside dev
    # The founder's least-privilege choice: a restricted test key is accepted too.
    restricted = build_providers("development", env={**STRIPE, "STRIPE_TEST_SECRET_KEY": "rk_" + "test_" + "A1" * 12},
                                 stripe_wire_factory=StripeSemanticsDouble(clock))
    assert restricted.payments_rail == "stripe_test"


def test_composition_builds_the_real_sdk_wire_without_a_network_call():
    pytest.importorskip("stripe")
    from brandme_core.domains.commerce.composition import build_providers
    from brandme_core.domains.providers.payments.stripe_wire import SdkStripeWire
    built = build_providers("development", env={**STRIPE, "STRIPE_TEST_SECRET_KEY": SK_TEST})
    assert isinstance(built.payments._wire, SdkStripeWire)


class _RecordingEnv(dict):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.read = set()

    def __getitem__(self, k):
        self.read.add(k)
        return super().__getitem__(k)

    def __contains__(self, k):
        self.read.add(k)
        return super().__contains__(k)

    def get(self, k, default=None):
        self.read.add(k)
        return super().get(k, default)


def test_composition_reads_only_allowlisted_env():
    from brandme_core.domains.commerce.composition import ENV_KEYS, build_providers
    from tests.fixtures.providers.stripe_double import StripeSemanticsDouble
    env = _RecordingEnv({"ANTHROPIC_API_KEY": "x", "ANTHROPIC_BASE_URL": "http://x", "HTTPS_PROXY": "http://p:1",
                         "STRIPE_SECRET_KEY": SK_TEST, "STRIPE_API_KEY": SK_TEST, **STRIPE,
                         "STRIPE_TEST_SECRET_KEY": SK_TEST})
    build_providers("development", env=env, stripe_wire_factory=StripeSemanticsDouble(lambda: None))
    assert env.read and env.read <= set(ENV_KEYS)
    assert not any(k.startswith("ANTHROPIC_") or k == "HTTPS_PROXY" for k in ENV_KEYS)


def test_composition_runs_trust_path_check(monkeypatch):
    import importlib
    from brandme_core.domains.commerce.composition import CompositionError, build_providers
    config = importlib.import_module("brandme_core.config")  # the module (the package re-exports a settings object)
    seen = []

    def violating(mode, registrations):
        seen.extend(registrations)
        return ["commerce.checkout via test is simulated without a visible simulation label"]
    monkeypatch.setattr(config, "check_registrations", violating)
    with pytest.raises(CompositionError) as e:
        build_providers("development", env={})
    assert e.value.code == "trust_path_violation"
    assert [r.kind.value for r in seen] == ["simulated", "simulated"] and all(r.simulation_label for r in seen)


def test_default_path_imports_without_stripe():
    import subprocess
    import sys
    from pathlib import Path
    code = ("import sys; sys.modules['stripe'] = None\n"
            "from brandme_core.domains.commerce.composition import build_providers\n"
            "p = build_providers('development', env={})\n"
            "assert p.payments_rail == 'simulated' and 'stripe' not in [m for m in sys.modules if sys.modules[m]]\n"
            "print('ok')")
    out = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr[-2000:]


def test_runtime_stripe_failure_never_switches_rail():
    from brandme_core.domains.commerce.composition import build_providers
    from brandme_core.domains.providers.payments.stripe_wire import WireError
    from tests.fixtures.commerce.harness import Clock
    from tests.fixtures.providers.stripe_double import StripeSemanticsDouble
    clock = Clock()
    double = StripeSemanticsDouble(clock)
    built = build_providers("development", env={**STRIPE, "STRIPE_TEST_SECRET_KEY": SK_TEST}, clock=clock,
                            stripe_wire_factory=double)
    adapter = built.registry.get("demo_atelier").adapter
    rail = adapter.payments
    cart = adapter.create_cart("fictional-demo-merchant", [line()])
    q = adapter.quote(cart)
    double.fail_next("create_payment_intent", WireError("api"))
    with pytest.raises(ProviderError) as e:
        adapter.submit(SubmitRequest("bm-" + "5" * 32, q.checkout_reference, "h", Money(8900 + 712, "USD"), None,
                                     (line(),), q.payee_ref))
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN
    assert built.registry.get("demo_atelier").adapter.payments is rail and rail.processor_id == "stripe_test"


# ------------------------------------------------------------------- exchanges (BM-COM-011)
def test_exchange_back_into_an_earlier_variant_keeps_every_step(w):
    _, res = _buy(w, w.member, line("overshirt", "m"))
    order = _order(w, res)
    _hook(w, w.provider.ship(order.provider_order_ref))
    _hook(w, w.provider.exchange(order.provider_order_ref, "demo-overshirt-m", "demo-overshirt-l"))
    _hook(w, w.provider.ship(order.provider_order_ref))
    _hook(w, w.provider.exchange(order.provider_order_ref, "demo-overshirt-l", "demo-overshirt-m"))
    o = w.store.get("orders", order.id)
    lines = {l.source_variant_ref: (l.quantity_ordered, l.quantity_delivered, l.quantity_returned, l.exchanged_from_ref)
             for l in o.lines}
    assert lines == {"demo-overshirt-m": (2, 1, 1, None), "demo-overshirt-l": (1, 1, 1, "demo-overshirt-m")}
    assert _effects(w)[-1] == "exchanged" and o.payment_status == "captured" and o.refunded_total == Money(0, "USD")


def test_units_being_returned_cannot_also_be_exchanged(w):
    _, res = _buy(w, w.member, line("overshirt", "m"))
    order = _order(w, res)
    _hook(w, w.provider.ship(order.provider_order_ref))
    assert w.svc.request_return(w.member, order.id, "demo-overshirt-m", 1)["status"] == "return_requested"
    with pytest.raises(ProviderError):
        w.provider.exchange(order.provider_order_ref, "demo-overshirt-m", "demo-overshirt-l")


# ------------------------------------------------- member-requested cancellation (ch.05 §6)
CANCEL_KEY = "cancel-flow-key-00001"


def _voids(w):
    return _calls(w, "void")


def test_member_cancels_an_unshipped_order_and_the_hold_is_voided_once(w):
    _, res = _buy(w, w.member)
    order = _order(w, res)
    out = w.svc.request_cancellation(w.member, order.id, idempotency_key=CANCEL_KEY)
    assert out == {"order_id": order.id, "status": "cancelled", "order_status": "cancelled",
                   "payment_status": "voided", "units_cancelled": 1}
    assert w.store.get("operations", res.id).state == "cancelled" and _effects(w)[-1] == "cancelled"
    assert w.svc.request_cancellation(w.member, order.id, idempotency_key=CANCEL_KEY) == out  # replay
    assert len(_voids(w)) == 1 and len(w.provider._cancellations) == 1
    with pytest.raises(InvalidRequest) as e:  # a new key: nothing is left to cancel
        w.svc.request_cancellation(w.member, order.id, idempotency_key="cancel-flow-key-00002")
    assert e.value.code == "nothing_to_cancel"


def test_shipped_units_are_returned_not_cancelled(w):
    _, res = _buy(w, w.member)
    order = _order(w, res)
    _hook(w, w.provider.ship(order.provider_order_ref))
    with pytest.raises(InvalidRequest) as e:
        w.svc.request_cancellation(w.member, order.id, idempotency_key=CANCEL_KEY)
    assert e.value.code == "nothing_to_cancel" and w.provider._cancellations == {}


def test_cancelling_after_a_partial_shipment_refunds_only_the_unshipped_units(w):
    quote, res = _buy(w, w.member, line("overshirt"), line("bag"))
    order = _order(w, res)
    w.provider.arm(Behavior.PARTIAL_FULFILLMENT, source_variant_ref="demo-bag-m", quantity=0)
    _hook(w, w.provider.ship(order.provider_order_ref))  # captured in full; the bag has not shipped
    out = w.svc.request_cancellation(w.member, order.id, idempotency_key=CANCEL_KEY)
    bag = 12900 + 12900 * 800 // 10_000
    o = w.store.get("orders", order.id)
    assert (out["status"], out["units_cancelled"], out["payment_status"]) == ("partially_cancelled", 1,
                                                                              "partially_refunded")
    assert o.refunded_total == Money(bag, "USD") and o.fulfillment_status == "fulfilled"
    assert {l.source_variant_ref: l.quantity_cancelled for l in o.lines} == {"demo-overshirt-m": 0, "demo-bag-m": 1}


def test_agents_cancel_only_orders_placed_under_their_own_grant(w):
    _, ag = w.delegate(lim=limits())
    _, mine = _buy(w, w.member, key="pay-flow-buy-member01")
    with pytest.raises(Forbidden) as e:
        w.svc.request_cancellation(ag, mine.order_id, idempotency_key=CANCEL_KEY)
    assert e.value.code == "order_not_yours"
    _, theirs = _buy(w, ag, key="pay-flow-buy-agent001")
    _order(w, theirs)
    assert w.svc.request_cancellation(ag, theirs.order_id, idempotency_key=CANCEL_KEY)["status"] == "cancelled"


def test_a_merchant_without_a_cancellation_path_is_an_explicit_handoff(w):
    _, res = _buy(w, w.member)
    w.registry.suspend("demo_atelier", "orders.read", "operator_hold", w.clock())
    out = w.svc.request_cancellation(w.member, res.order_id, idempotency_key=CANCEL_KEY)
    assert out["status"] == "handoff" and out["disclosure"] and w.provider._cancellations == {}
    assert w.store.get("operations", res.id).state == "accepted"


def test_a_cancellation_the_merchant_never_received_can_be_retried_with_the_same_key(w, monkeypatch):
    _, res = _buy(w, w.member)
    order = _order(w, res)
    real = w.provider.request_cancellation

    def refused(ref, *, idempotency_key):
        monkeypatch.setattr(w.provider, "request_cancellation", real)
        raise ProviderError(ProviderErrorKind.TRANSIENT, "merchant unavailable")
    monkeypatch.setattr(w.provider, "request_cancellation", refused)
    with pytest.raises(ProviderError):
        w.svc.request_cancellation(w.member, order.id, idempotency_key=CANCEL_KEY)
    assert w.store.get("operations", res.id).state == "accepted"  # undone: the merchant never saw it
    assert w.svc.request_cancellation(w.member, order.id, idempotency_key=CANCEL_KEY)["status"] == "cancelled"


def test_a_lost_cancellation_response_is_re_sent_under_the_same_merchant_key(w, monkeypatch):
    _, res = _buy(w, w.member)
    order = _order(w, res)
    real, keys = w.provider.request_cancellation, []

    def lost(ref, *, idempotency_key):
        keys.append(idempotency_key)
        result = real(ref, idempotency_key=idempotency_key)
        if len(keys) == 1:
            raise ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN, "response lost", transmitted=True)
        return result
    monkeypatch.setattr(w.provider, "request_cancellation", lost)
    with pytest.raises(ProviderError):
        w.svc.request_cancellation(w.member, order.id, idempotency_key=CANCEL_KEY)
    assert w.store.get("operations", res.id).state == "cancel_requested"
    out = w.svc.request_cancellation(w.member, order.id, idempotency_key=CANCEL_KEY)
    assert out["status"] == "cancelled" and keys[0] == keys[1] and len(_voids(w)) == 1


@pytest.mark.parametrize("lost", ["response", "request"])
def test_a_retried_cancellation_never_refunds_the_same_units_twice(w, lost):
    """A refund lost inside a member cancellation is settled under its own key on retry, never sent anew."""
    _, res = _buy(w, w.member, line("overshirt"), line("bag"))
    order = _order(w, res)
    w.provider.arm(Behavior.PARTIAL_FULFILLMENT, source_variant_ref="demo-bag-m", quantity=0)
    _hook(w, w.provider.ship(order.provider_order_ref))  # captured in full; the bag has not shipped
    (_lose_response if lost == "response" else _lose_request)(w, "refund")
    with pytest.raises(ProviderError):
        w.svc.request_cancellation(w.member, order.id, idempotency_key=CANCEL_KEY)
    if lost == "request":  # absent inside the settle window: the retry waits for it, never sends another
        with pytest.raises(ProviderError) as e:
            w.svc.request_cancellation(w.member, order.id, idempotency_key=CANCEL_KEY)
        assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN
        w.clock.advance(minutes=3)
    out = w.svc.request_cancellation(w.member, order.id, idempotency_key=CANCEL_KEY)  # the same key, as documented
    assert set(_calls(w, "refund")) == {("refund", payment_key(_base(w, res), "refund", 1))}
    assert _held(w, order.provider_order_ref).refunded == Money(BAG, "USD")  # one bag, refunded once
    o = w.store.get("orders", order.id)
    assert (out["status"], out["units_cancelled"]) == ("partially_cancelled", 1)
    assert o.refunded_total == Money(BAG, "USD") and w.provider.rail_health()["pending_money_ops"] == 0
    assert w.svc.request_cancellation(w.member, order.id, idempotency_key=CANCEL_KEY) == out  # replay


# ======================================================= payments and fulfillment behind the merchant (§13.4)
BAG = 12900 + 12900 * 800 // 10_000


def _base(w, res):
    return w.store.get("operations", res.id).provider_idempotency_key


def _signed_pi_event(w, order_ref, event_type="payment_intent.amount_capturable_updated", **kw):
    (pi,) = w.provider.payments.double.intents_for(order_ref)
    return stripe_events.payment_intent_event(pi, event_type, w.secret, int(w.clock.now.timestamp()), **kw)


def test_simulator_purchase_through_stripe_adapter_on_semantics_double(commerce_store):
    """The founder's flow, offline. Evidence: fixture double, not Stripe.

    An agent prepares, the member approves on the trusted surface, the agent executes inside its grant; the
    simulator merchant authorizes, captures and refunds through the real Stripe test-mode processor, whose
    wire is the semantics double. No network and no key."""
    w = rail_world("stripe_double", commerce_store)
    double = w.provider.payments.double
    d, ag = w.delegate(lim=limits(refund_credit_back=True))
    _, quote, op = w.prepared(ag, line("overshirt"), line("bag"))  # the agent prepares
    approval = w.approve(op)  # the member approves
    res = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id,
                                 idempotency_key="founder-flow-000000001")
    assert res.state == "accepted"
    order = w.store.get("orders", res.order_id)
    (pi,) = double.intents.values()  # exactly one PaymentIntent
    assert (pi["status"], pi["capture_method"], pi["amount"], pi["currency"], pi["livemode"]) == (
        "requires_capture", "manual", quote.total.amount_minor, "usd", False)
    assert pi["metadata"]["brandme_purpose_ref"] == order.provider_order_ref
    assert pi["metadata"]["brandme_idem"] == payment_key(_base(w, res), "authorize")
    assert pi["metadata"]["brandme_payee_ref"] == quote.payee_ref == "demo-atelier-stripe-test"
    assert w.svc.handle_webhook("demo_atelier", *_signed_pi_event(w, order.provider_order_ref)).state == "applied"
    assert w.store.get("orders", order.id).payment_status == "authorized"
    _hook(w, w.provider.ship(order.provider_order_ref))  # the capture point
    o = w.store.get("orders", order.id)
    assert (o.payment_status, o.fulfillment_status) == ("captured", "fulfilled")
    assert double.intents[pi["id"]]["amount_received"] == quote.total.amount_minor
    w.provider.arm(Behavior.REFUND, source_variant_ref="demo-bag-m", quantity=1)
    _hook(w, w.provider.refund(order.provider_order_ref))
    o = w.store.get("orders", order.id)
    assert o.payment_status == "partially_refunded" and o.refunded_total == Money(BAG, "USD")
    assert [r["status"] for r in double.refunds.values()] == ["succeeded"]
    event = _signed_pi_event(w, order.provider_order_ref, "payment_intent.succeeded")
    first, again = (w.svc.handle_webhook("demo_atelier", *event) for _ in range(2))  # one signed event, twice
    assert first.event_id == again.event_id and len([r for r in w.store.rows("webhook_receipts")
                                                     if r.event_id == first.event_id]) == 1
    spent = quote.total.amount_minor - BAG  # refund_credit_back: the refunded bag returns to the grant
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000 - spent, "USD")
    _assert_no_processor_ids(w)


def _assert_no_processor_ids(w):
    import re

    from brandme_core.domains.commerce.http_api import operation_wire, order_wire
    from brandme_core.mcp.authz import ExecutorAssertionVerifier
    from brandme_core.mcp.tools import McpToolExecutor
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1()).public_key()
    mcp = McpToolExecutor(commerce=w.svc, registry=w.registry, verifier=ExecutorAssertionVerifier(
        gateway_issuer="https://gateway.example.invalid", keys={"k": key}, environment="development"))
    blobs = [json.dumps(e.payload) for e in w.store.outbox()]
    for op in w.store.rows("operations"):
        blobs.append(json.dumps(operation_wire(op)))
        blobs.append(json.dumps(mcp._op_status(w.member, op), default=str))
    blobs += [json.dumps(order_wire(o)) for o in w.store.rows("orders")]
    blobs += [repr(o.evidence_refs) for o in w.store.rows("orders")]
    leak = re.compile(r"(?<![A-Za-z0-9])(pi|pm|ch|re|evt)_[A-Za-z0-9]{6,}|simpay_|_secret_|4242")
    for b in blobs:
        assert not leak.search(b), b[:300]


def test_processor_response_lost_reconciles_to_one_payment(w):
    _lose_response(w, "authorize")
    _, res = _buy(w, w.member)
    assert res.state == "outcome_unknown"
    done = w.svc.reconcile(res.id)
    assert done.state == "accepted" and len(w.store.rows("orders")) == 1
    assert _calls(w, "authorize") == [("authorize", payment_key(_base(w, res), "authorize"))]  # BM-COM-009
    if w.rail == "stripe_double":
        assert len(w.provider.payments.double.intents) == 1


def test_absence_is_final_only_after_settle_window(w):
    stock = dict(w.provider._stock)
    _lose_request(w, "authorize")
    _, res = _buy(w, w.member)
    assert w.svc.reconcile(res.id).state == "outcome_unknown"
    w.clock.advance(seconds=PAYMENT_SETTLE_WINDOW.total_seconds() - 1)
    assert w.svc.reconcile(res.id).state == "outcome_unknown"  # not settled yet
    w.clock.advance(seconds=1)
    done = w.svc.reconcile(res.id)
    assert done.state == "rejected" and done.reason_code == "not_found_at_provider"
    assert w.provider._stock == stock and w.store.rows("orders") == []


def test_search_lag_beyond_window_is_covered_by_list_scan(commerce_store):
    w = rail_world("stripe_double", commerce_store)
    w.provider.payments.double.search_lag = timedelta(minutes=30)
    _lose_response(w, "authorize")
    _, res = _buy(w, w.member)
    w.clock.advance(minutes=3)  # absence would now be final: only the consistent list scan can save it
    done = w.svc.reconcile(res.id)
    assert done.state == "accepted" and len(w.provider.payments.double.intents) == 1
    assert "list_payment_intents" in [c[0] for c in w.provider.payments.double.calls]


def test_orphan_hold_voided_when_payment_surfaces_after_rejection(w):
    from brandme_core.domains.providers.merchant import order_ref_for
    from brandme_core.domains.providers.payments import PaymentAuthorization
    _lose_request(w, "authorize")
    _, res = _buy(w, w.member)
    w.clock.advance(minutes=3)
    assert w.svc.reconcile(res.id).state == "rejected"
    base = _base(w, res)
    ref = order_ref_for(base)
    # The lost request was only delayed: the processor executes it after the merchant gave up.
    if w.rail == "simulated":
        w.provider.payments.authorize(PaymentAuthorization(
            payment_key(base, "authorize"), Money(9612, "USD"), w.provider.payee_ref, ref, "pm_card_visa",
            {}, "development"))
        assert w.provider.lookup_by_idempotency_key(base) is None  # the merchant's sweep releases it
    else:
        double = w.provider.payments.double
        _, params, key = double.calls[0]
        double.create_payment_intent(params, idempotency_key=key)
        receipt = w.svc.handle_webhook("demo_atelier", *_signed_pi_event(w, ref))
        assert receipt.state == "ignored"  # acknowledged, not applied: no order holds it
    late = w.provider.payments.find(ref, settled=True)
    assert (late.status, late.release_reason) == ("voided", "orphan_authorization")
    assert w.provider.rail_health()["orphans_voided"] == 1 and w.store.rows("orders") == []


def test_merchant_restart_voids_orphan_and_reports_cancelled(w):
    d, ag = w.delegate(lim=limits())
    _, res = _buy(w, ag)
    order = _order(w, res)
    assert order.payment_status == "authorized"
    rail = w.provider.payments
    if w.rail == "stripe_double":  # a new process: a fresh processor (empty journal) over the same account
        rail = stripe_double_rail(w.clock, secret=w.secret, double=rail.double)
    w.provider = LocalAtelierProvider(w.clock, payments=rail)  # the merchant restarted; its ledger is gone
    w.registry._connections.clear()
    w.registry.register(local_atelier_connection(w.provider, "development", w.clock.now))
    w.clock.advance(minutes=3)
    obs = w.provider.lookup(order.provider_order_ref)
    assert (obs.order_status, obs.payment_status, obs.lines) == ("cancelled", "voided", ())
    w.svc._apply_observation(order.id, obs, "system:reconciler")
    o = w.store.get("orders", order.id)
    assert (o.order_status, o.payment_status) == ("cancelled", "voided") and len(o.lines) == 1  # lines kept
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000, "USD")
    assert w.store.get("operations", res.id).state == "cancelled"


@pytest.mark.parametrize("lost", ["response", "request"])
def test_lost_refund_response_is_reconciled_then_resent_with_same_key(w, lost):
    _, res = _buy(w, w.member, line("overshirt"), line("bag"))
    order = _order(w, res)
    _hook(w, w.provider.ship(order.provider_order_ref))
    (_lose_response if lost == "response" else _lose_request)(w, "refund")
    w.provider.arm(Behavior.REFUND, source_variant_ref="demo-bag-m", quantity=1)
    with pytest.raises(ProviderError) as e:
        w.provider.refund(order.provider_order_ref)
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN and e.value.transmitted
    key = payment_key(_base(w, res), "refund", 1)
    assert w.provider.rail_health()["pending_money_ops"] == 1
    w.svc._apply_observation(order.id, w.provider.lookup(order.provider_order_ref), "system:reconciler")
    if lost == "response":  # applied: the read settles it, nothing is re-sent
        assert _calls(w, "refund") == [("refund", key)]
    else:  # absent, but inside the settle window: nothing is re-sent yet
        assert _calls(w, "refund") == [("refund", key)] and _held(w, order.provider_order_ref).refunded == Money(0, "USD")
        w.clock.advance(minutes=3)
        w.svc._apply_observation(order.id, w.provider.lookup(order.provider_order_ref), "system:reconciler")
        assert _calls(w, "refund") == [("refund", key)] * 2  # the same key, once more
    assert w.provider.rail_health()["pending_money_ops"] == 0
    o = w.store.get("orders", order.id)
    assert o.payment_status == "partially_refunded" and o.refunded_total == Money(BAG, "USD")  # once
    assert _held(w, order.provider_order_ref).refunded == Money(BAG, "USD")


def test_lost_capture_response_blocks_shipping_until_reconciled(w):
    _, res = _buy(w, w.member)
    order = _order(w, res)
    _lose_response(w, "capture")
    with pytest.raises(ProviderError) as e:
        w.provider.ship(order.provider_order_ref)
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN
    assert not w.provider.fulfillment.record(order.provider_order_ref).shipped_any  # nothing shipped
    _hook(w, w.provider.ship(order.provider_order_ref))  # the pending capture is read as applied first
    o = w.store.get("orders", order.id)
    assert (o.payment_status, o.fulfillment_status) == ("captured", "fulfilled")
    assert _calls(w, "capture") == [("capture", payment_key(_base(w, res), "capture"))]


def test_a_pending_capture_is_not_re_sent_inside_its_settle_window(w):
    _, res = _buy(w, w.member)
    order = _order(w, res)
    _lose_request(w, "capture")
    for _ in range(2):  # lost, then refused locally: the same key is not sent again inside the window
        with pytest.raises(ProviderError) as e:
            w.provider.ship(order.provider_order_ref)
        assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN
    key = payment_key(_base(w, res), "capture")
    assert _calls(w, "capture") == [("capture", key)]
    w.clock.advance(minutes=3)  # absent after the window: reconciliation re-sends the same key once
    _hook(w, w.provider.ship(order.provider_order_ref))
    assert _calls(w, "capture") == [("capture", key)] * 2
    assert w.store.get("orders", order.id).payment_status == "captured"
    rec = w.provider._orders[order.provider_order_ref]
    assert rec.pending == {} and w.provider.rail_health()["needs_operator"] == 0


def test_an_absent_money_op_past_the_key_horizon_waits_for_an_operator(w):
    _, res = _buy(w, w.member)
    order = _order(w, res)
    _lose_request(w, "capture")
    with pytest.raises(ProviderError):
        w.provider.ship(order.provider_order_ref)
    w.clock.advance(hours=23, minutes=1)  # beyond the processor's idempotency-key retention: never re-sent
    for _ in range(2):
        with pytest.raises(ProviderError) as e:
            w.provider.ship(order.provider_order_ref)
        assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN
    assert len(_calls(w, "capture")) == 1
    assert w.provider.rail_health()["needs_operator"] == 1 and w.provider.rail_health()["pending_money_ops"] == 1
    assert not w.provider.fulfillment.record(order.provider_order_ref).shipped_any


def test_void_failure_during_submit_keeps_operation_unknown(w):
    stock = dict(w.provider._stock)
    d, ag = w.delegate(lim=limits())
    if w.rail == "simulated":
        w.provider.payments.arm(PaymentBehavior.AMOUNT_MISMATCH)
    else:
        w.provider.payments.double.corrupt_next_create(amount=9613)
    _lose_request(w, "void")
    _, res = _buy(w, ag)
    assert res.state == "outcome_unknown"  # never rejected while a hold may remain
    assert w.provider._stock != stock  # the stock stays held until the void resolves
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000 - 9612, "USD")
    done = w.svc.reconcile(res.id)  # the void is retried under its key, then the order is released
    assert done.state == "rejected" and w.provider._stock == stock
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000, "USD")
    key = payment_key(_base(w, res), "void")
    assert set(_calls(w, "void")) == {("void", key)}
    rec = next(iter(w.provider._orders.values()))
    assert w.provider.payments.lookup(rec.payment_ref).status == "voided"


def test_payee_mismatch_refused_before_payment_io():
    from tests.fixtures.commerce.harness import Clock
    for rail in ("simulated", "stripe_double"):
        clock = Clock()
        p = LocalAtelierProvider(clock, payments=None if rail == "simulated" else stripe_double_rail(clock))
        q = p.quote(p.create_cart("fictional-demo-merchant", [line()]))
        ack = p.submit(SubmitRequest("bm-" + "6" * 32, q.checkout_reference, "h", Money(9612, "USD"), None,
                                     (line(),), "someone-else"))
        assert (ack.accepted, ack.reason_code) == (False, "payee_changed")
        assert p._orders == {}
        assert (p.payments.calls if rail == "simulated" else p.payments.double.calls) == []


def test_binding_mismatch_voids_and_rejects(w):
    stock = dict(w.provider._stock)
    if w.rail == "simulated":
        w.provider.payments.arm(PaymentBehavior.AMOUNT_MISMATCH)
    else:
        w.provider.payments.double.corrupt_next_create(amount=9613)
    _, res = _buy(w, w.member)
    assert (res.state, res.reason_code) == ("rejected", "payment_binding_mismatch")
    rec = next(iter(w.provider._orders.values()))
    pay = w.provider.payments.lookup(rec.payment_ref)
    assert pay.status == "voided" and w.provider._stock == stock and w.store.rows("orders") == []


def test_authorization_expiry_cancels_unshipped_order(w):
    d, ag = w.delegate(lim=limits(refund_credit_back=False))
    _, res = _buy(w, ag)
    order = _order(w, res)
    w.clock.advance(days=8)
    w.svc._apply_observation(order.id, w.provider.lookup(order.provider_order_ref), "system:reconciler")
    o = w.store.get("orders", order.id)
    assert (o.order_status, o.payment_status) == ("cancelled", "voided")
    assert w.store.get("operations", res.id).state == "cancelled"
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000, "USD")  # never taken
    assert _calls(w, "capture") == [] and sum(l.quantity_cancelled for l in o.lines) == 1
    assert _held(w, order.provider_order_ref).release_reason == "authorization_expired"


def test_foreign_stripe_event_is_acknowledged_ignored(commerce_store, monkeypatch):
    w = rail_world("stripe_double", commerce_store)
    at = int(w.clock.now.timestamp())
    foreign = {"id": "pi_foreign00001", "object": "payment_intent", "status": "requires_capture",
               "metadata": {"brandme_env": "production", "brandme_purpose_ref": "someone-elses-order"}}
    monkeypatch.setattr(w.svc, "reconcile", lambda *_: pytest.fail("an ignored event must not sweep"))
    receipt = w.svc.handle_webhook("demo_atelier", *stripe_events.payment_intent_event(foreign, "payment_intent.succeeded",
                                                                                         w.secret, at))
    assert receipt.state == "ignored" and w.provider.rail_health()["webhooks_ignored"] == 1
    other_type = stripe_events.signed(stripe_events.event("customer.created", {"id": "cus_123456789"}, created=at),
                                      w.secret, at)
    assert w.svc.handle_webhook("demo_atelier", *other_type).state == "ignored"


def test_stripe_event_through_domain_http_route(commerce_store):
    import base64

    from cryptography.hazmat.primitives.asymmetric import ec
    from fastapi.testclient import TestClient

    from brandme_core.domains.commerce.http_api import PREFIX, CommerceHttpApi, create_commerce_app
    from brandme_core.mcp.authz import DOMAIN_AUDIENCE, ExecutorAssertionVerifier, sign_executor_assertion
    w = rail_world("stripe_double", commerce_store)
    gw = "https://gateway.example.invalid"
    key = ec.generate_private_key(ec.SECP256R1())
    api = CommerceHttpApi(service=w.svc, verifier=ExecutorAssertionVerifier(
        gateway_issuer=gw, keys={"gw-1": key.public_key()}, environment="development", audience=DOMAIN_AUDIENCE,
        allow_session=True))
    client = TestClient(create_commerce_app(api))

    def post(headers, body):  # what the gateway relay sends: the raw body and the allowlisted signature header
        token = sign_executor_assertion(private_key=key, kid="gw-1", gateway_issuer=gw, principal=None,
                                        jti=os.urandom(8).hex(), audience=DOMAIN_AUDIENCE)
        envelope = json.dumps({"headers": headers, "body_b64": base64.b64encode(body).decode()})
        return client.post(f"{PREFIX}/webhooks/demo_atelier", content=envelope,
                           headers={"Authorization": "Bearer " + token})

    _, res = _buy(w, w.member)
    order = w.store.get("orders", res.order_id)
    headers, body = _signed_pi_event(w, order.provider_order_ref)
    ok = post(headers, body)
    assert ok.status_code == 200 and ok.json() == {"received": True, "state": "applied"}
    assert w.store.get("orders", order.id).payment_status == "authorized"
    tampered = post(headers, body.replace(b"requires_capture", b"succeeded"))
    assert tampered.status_code == 400 and tampered.json()["code"] == "webhook_rejected"
    at = int(w.clock.now.timestamp())
    foreign = {"id": "pi_foreign00002", "object": "payment_intent", "metadata": {"brandme_env": "demo"}}
    ignored = post(*stripe_events.payment_intent_event(foreign, "payment_intent.canceled", w.secret, at))
    assert ignored.status_code == 200 and ignored.json() == {"received": True, "state": "ignored"}


def test_no_processor_or_fulfillment_io_inside_store_transactions(w, monkeypatch):
    """Spanner may retry a transaction body: no processor or fulfillment call may happen inside one."""
    depth = {"n": 0}
    real_run = w.store.run

    def run(fn, *a, **kw):
        depth["n"] += 1
        try:
            return real_run(fn, *a, **kw)
        finally:
            depth["n"] -= 1
    monkeypatch.setattr(w.store, "run", run)
    seen = []

    def guard(obj, names):
        for name in names:
            real = getattr(obj, name)

            def wrapped(*a, _real=real, _name=name, **kw):
                assert depth["n"] == 0, f"{_name} called inside a store transaction"
                seen.append(_name)
                return _real(*a, **kw)
            monkeypatch.setattr(obj, name, wrapped)
    guard(w.provider.payments, ("authorize", "capture", "void", "refund", "lookup", "find", "operation_effect",
                                "verify_webhook"))
    guard(w.provider.fulfillment, ("open", "record", "cancel_unshipped", "authorize_return", "request_exchange",
                                   "ship", "receive_return"))
    d, ag = w.delegate(lim=limits())
    _, res = _buy(w, ag, line("overshirt"), line("bag"))
    order = w.store.get("orders", res.order_id)
    w.provider.arm(Behavior.PARTIAL_FULFILLMENT, source_variant_ref="demo-bag-m", quantity=0)
    _hook(w, w.provider.ship(order.provider_order_ref))
    w.svc.request_return(w.member, order.id, "demo-overshirt-m", 1)
    w.svc.request_cancellation(w.member, order.id, idempotency_key="no-io-in-tx-cancel-01")
    w.provider.arm(Behavior.REFUND, source_variant_ref="demo-overshirt-m", quantity=1)
    _hook(w, w.provider.refund(order.provider_order_ref))
    _lose_response(w, "authorize")
    _, unknown = _buy(w, ag, line("dress"), key="no-io-in-tx-buy-0002")
    w.svc.reconcile(unknown.id)
    assert {"authorize", "capture", "refund", "lookup", "open", "record", "cancel_unshipped",
            "authorize_return"} <= set(seen)


def test_payment_identifiers_never_reach_models_events_or_wires(w):
    _, res = _buy(w, w.member, line("overshirt"), line("bag"))
    order = _order(w, res)
    _hook(w, w.provider.ship(order.provider_order_ref))
    w.provider.arm(Behavior.REFUND, source_variant_ref="demo-bag-m", quantity=1)
    _hook(w, w.provider.refund(order.provider_order_ref))
    _assert_no_processor_ids(w)
    o = w.store.get("orders", order.id)
    assert o.evidence_refs == (f"sim:demo_atelier:order:{order.provider_order_ref}",)  # constant and de-duplicated


def _scripted(rail):
    w = rail_world(rail)
    d, ag = w.delegate(lim=limits())
    seen = []

    def snap(res_id):
        op = w.store.get("operations", res_id)
        o = w.store.get("orders", op.order_id) if op.order_id else None
        seen.append((op.state,) + ((o.order_status, o.payment_status, o.refunded_total.amount_minor,
                                    o.fulfillment_status) if o else ()))
    _, res = _buy(w, ag, line("overshirt"), line("bag", qty=2))
    order = _order(w, res)
    snap(res.id)
    _hook(w, w.provider.cancel(order.provider_order_ref, "demo-bag-m", 1))  # before capture: a smaller capture
    snap(res.id)
    w.provider.arm(Behavior.PARTIAL_FULFILLMENT, source_variant_ref="demo-bag-m", quantity=0)
    _hook(w, w.provider.ship(order.provider_order_ref))
    snap(res.id)
    w.provider.arm(Behavior.REFUND, source_variant_ref="demo-bag-m", quantity=1)  # unshipped: cancelled, refunded
    _hook(w, w.provider.refund(order.provider_order_ref))
    snap(res.id)
    w.provider.arm(Behavior.REFUND)  # the rest comes back: exactly the collected remainder is refunded
    _hook(w, w.provider.refund(order.provider_order_ref))
    snap(res.id)
    _lose_response(w, "authorize")
    _, lost = _buy(w, ag, line("dress"), key="parity-buy-lost-00001")
    snap(lost.id)
    w.svc.reconcile(lost.id)
    snap(lost.id)
    seen.append(w.svc.available_budget(w.store.get("delegations", d.id)).amount_minor)
    return seen


def test_parity_simulated_vs_stripe_double():
    sim, stripe = _scripted("simulated"), _scripted("stripe_double")
    assert sim == stripe
    captured = 37476 - BAG  # one bag cancelled before capture: the capture is smaller, the rest was never taken
    dress = 15900 + 15900 * 800 // 10_000
    assert sim[4][1:3] == ("accepted", "refunded") and sim[-1] == 50_000 - captured - dress  # no refund credit-back


def test_mixed_mode_labels_capabilities_and_operator_rail():
    from brandme_core.domains.commerce.http_api import CommerceHttpApi
    from brandme_core.domains.providers.local_atelier import (
        SIMULATION_LABEL, STRIPE_TEST_LABEL, STRIPE_TEST_SETUP_PROFILE,
    )
    from brandme_core.domains.providers.contracts import CAPABILITY_STATES
    admin = None
    for rail in ("simulated", "stripe_double"):
        w = rail_world(rail)
        conn = w.registry.get("demo_atelier")
        assert all(c.state == "sandbox" for c in conn.capabilities.values()) and "verified" in CAPABILITY_STATES
        assert len(conn.disclosure) <= 200 and "payment_rail" not in conn.to_public()
        api = CommerceHttpApi.__new__(CommerceHttpApi)
        api.svc = w.svc
        admin = admin or w.member.__class__(**{**w.member.__dict__, "scopes": frozenset({"provider:admin"})})
        _, got = api._provider_get(admin, {"provider_id": "demo_atelier"}, {})
        _, health = api._provider_health(admin, {"provider_id": "demo_atelier"}, {})
        _, caps = api._capabilities(w.member, {}, {})
        agg = caps["items"][0]
        assert agg["state"] == "simulated" and agg["reason_code"] == "simulated_provider_only"
        assert all(i["state"] != "available" for i in caps["items"])
        assert health["rail_health"] == {"pending_money_ops": 0, "needs_operator": 0, "orphans_voided": 0,
                                         "webhooks_ignored": 0, "money_ops_refused": 0}
        if rail == "simulated":
            assert conn.display_name == "Demo Atelier (simulated, fictional)" and conn.disclosure == SIMULATION_LABEL
            assert got["payment_rail"] == {"processor_id": "simulated", "mode": "simulated",
                                           "label": "Simulated payment — no real payment occurs.",
                                           "currencies": ["USD"], "api_version": None, "webhooks_configured": False}
        else:
            assert conn.display_name.endswith("· Stripe test mode") and conn.disclosure == STRIPE_TEST_LABEL
            assert agg["simulation_label"] == STRIPE_TEST_LABEL
            assert got["payment_rail"] == {"processor_id": "stripe_test", "mode": "sandbox",
                                           "label": "Stripe test mode — no real money moves.", "currencies": ["USD"],
                                           "api_version": "2026-09-30.endive", "webhooks_configured": True}
            assert conn.capability("checkout.submit").reason_code == "simulated_merchant_stripe_test_payments"
            assert conn.access_level == "simulation_stripe_test" and conn.credential_ref == "env:STRIPE_TEST_SECRET_KEY"
            assert w.provider.setup_profile is STRIPE_TEST_SETUP_PROFILE
            assert w.provider.handoff(w.provider._variants["demo-bag-m"].source_product_id, None).disclosure == \
                STRIPE_TEST_LABEL
            assert w.provider.probe("checkout.submit", "read_only_test", w.clock.now).result == "blocked"
            status = w.registry.record_verification("demo_atelier", "checkout.submit", evidence_ref="sandbox:run-1",
                                                    evidence_kind="sandbox_operation", checked_at=w.clock.now)
            assert status.state == "sandbox"  # a simulated merchant is never verified, even with Stripe evidence


def test_no_credential_literals_in_lane_files():
    import re
    import subprocess
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]
    lane = ["brandme_core/domains/commerce", "brandme_core/domains/providers", "brandme_core/mcp",
            "brandme_core/orchestrator", "brandme-agents", "brandme-governance", "packages/provider-contracts/src",
            "packages/provider-contracts/test", "brandme-gateway/src/routes/v1", "brandme-console/app",
            "tests/fixtures/commerce", "tests/fixtures/providers"]
    files = subprocess.run(["git", "ls-files", "--", *lane], cwd=repo, capture_output=True, text=True).stdout.split()
    files += [str(p.relative_to(repo)) for p in repo.glob("tests/test_*.py")
              if p.name.startswith(("test_commerce", "test_providers", "test_mcp"))]
    pattern = re.compile(r"(sk|rk)_(live|test)_[0-9A-Za-z]{16,}|whsec_[0-9A-Za-z]{16,}")
    hits = [f for f in set(files) if (repo / f).is_file() and pattern.search((repo / f).read_text(errors="ignore"))]
    assert hits == []
