"""Purchases end to end through the merchant's payment rail (ch.05 §6; BM-COM-009/010/011).

The commerce service is unchanged by the rail: it sees the merchant's order and its
payment status. These run on both stores with the simulated rail; the same flow
against Stripe test mode is the live test at the bottom (needs ``STRIPE_TEST_SECRET_KEY``).
"""

import hashlib
import hmac
import json
import os
import time
from datetime import timedelta

import pytest

from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.domains.commerce.money import Money
from brandme_core.domains.providers.contracts import ProviderError, SubmitRequest
from brandme_core.domains.providers.local_atelier import (
    PAYMENT_SETTLE_WINDOW, Behavior, LocalAtelierProvider, local_atelier_connection, payment_key,
)
from brandme_core.domains.providers.payments import TEST_CARD_NEEDS_AUTHENTICATION
from brandme_core.domains.providers.payments.simulated import PaymentBehavior, SimulatedPaymentProcessor
from tests.fixtures.commerce.harness import limits, line, world
from tests.fixtures.commerce.stores import _spanner_db, commerce_store  # noqa: F401  (fixtures)


@pytest.fixture
def w(commerce_store):
    return world(store=commerce_store)


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
    assert [c for c in w.provider.payments.calls if c[0] == "capture"] == [
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
    w.provider.expire_authorization(order.provider_order_ref)
    _hook(w, w.provider.ship(order.provider_order_ref))
    o = w.store.get("orders", order.id)
    assert (o.order_status, o.payment_status) == ("cancelled", "voided")
    assert sum(l.quantity_shipped for l in o.lines) == 0 and w.provider.payments.calls[-1][0] != "capture"


def test_a_declined_card_rejects_the_purchase_and_restocks(w):
    stock = dict(w.provider._stock)
    w.provider.arm(Behavior.REJECTED_AUTH)
    _, res = _buy(w, w.member)
    assert res.state == "rejected" and res.reason_code == "payment_authorization_declined"
    assert w.store.rows("orders") == [] and w.provider._stock == stock


def test_a_lost_payment_response_reconciles_without_a_second_authorization(w):
    w.provider.payments.arm(PaymentBehavior.TIMEOUT_AFTER_ACCEPT)
    _, res = _buy(w, w.member)
    assert res.state == "outcome_unknown"
    done = w.svc.reconcile(res.id)  # the merchant finds the payment by purpose; it never re-sends
    assert done.state == "accepted" and w.store.get("orders", done.order_id).payment_status == "authorized"
    assert [c for c in w.provider.payments.calls if c[0] == "authorize"] == [
        ("authorize", payment_key(w.store.get("operations", res.id).provider_idempotency_key, "authorize"))]


def test_absence_of_a_payment_is_final_only_after_the_settle_window(w):
    stock = dict(w.provider._stock)
    w.provider.payments.arm(PaymentBehavior.LOST_BEFORE_PROCESSING)
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


class _StripeSignedRail(SimulatedPaymentProcessor):
    """Simulated payments that deliver Stripe-signed events: exercises the webhook plumbing offline."""
    processor_id = "stripe_test"

    def __init__(self, clock, secret):
        super().__init__(clock)
        from brandme_core.domains.providers.payments.stripe_test import StripeTestPaymentProcessor
        self._verifier = StripeTestPaymentProcessor("sk_test_" + "0" * 24, webhook_secret=secret,
                                                    base_url="http://127.0.0.1:9")

    def verify_webhook(self, headers, body):
        return self._verifier.verify_webhook(headers, body)


def test_stripe_payment_events_reach_the_order_once_and_only_as_a_hint():
    pytest.importorskip("stripe")
    secret = "whsec_" + "7" * 32
    w = world()
    rail = _StripeSignedRail(w.clock, secret)
    w.provider = LocalAtelierProvider(w.clock, payments=rail)
    w.registry._connections.clear()
    w.registry.register(local_atelier_connection(w.provider, "development", w.clock.now))
    _, res = _buy(w, w.member)
    order = w.store.get("orders", res.order_id)
    pi = w.provider._orders[order.provider_order_ref].payment_ref
    w.provider.capture(order.provider_order_ref)  # the processor changes state; Stripe would notify
    event = {"id": "evt_test_1", "object": "event", "type": "payment_intent.succeeded", "livemode": False,
             "created": int(time.time()), "data": {"object": {"id": pi, "object": "payment_intent"}}}
    body = json.dumps(event).encode()
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    headers = {"stripe-signature": f"t={ts},v1={sig}"}
    before = len(w.store.outbox())
    first = w.svc.handle_webhook("demo_atelier", headers, body)
    again = w.svc.handle_webhook("demo_atelier", headers, body)  # duplicate delivery
    assert first.state == "applied" and again.event_id == first.event_id == "stripe_test:evt_test_1"
    assert len(w.store.rows("webhook_receipts")) == 1 and len(w.store.outbox()) == before + 1
    assert w.store.get("orders", order.id).payment_status == "captured"  # re-read, not taken from the event
    with pytest.raises(ProviderError):
        w.svc.handle_webhook("demo_atelier", headers, body + b" ")  # tampered


# --------------------------------------------------- LIVE: simulator merchant → Stripe test mode
@pytest.mark.skipif(not os.environ.get("STRIPE_TEST_SECRET_KEY"),
                    reason="STRIPE_TEST_SECRET_KEY not set: simulator→Stripe test-mode flow not_run")
def test_live_simulator_purchase_through_stripe_test_mode():
    """The founder's check-in flow: an agent prepares, the member approves, the purchase runs, and the
    simulator merchant authorizes, captures and refunds through Stripe test mode. No real money moves."""
    from brandme_core.domains.commerce.composition import build_providers
    from brandme_core.domains.commerce.service import CommerceService
    from brandme_core.domains.commerce.store import InMemoryCommerceStore
    from tests.fixtures.commerce.harness import AGENT_CLIENT, Clock, World, agent, member_session

    clock = Clock()
    clock.now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    providers = build_providers("development", env={"BRANDME_COMMERCE_PAYMENTS": "stripe_test",
                                                    "STRIPE_TEST_SECRET_KEY": os.environ["STRIPE_TEST_SECRET_KEY"]},
                                clock=clock)
    store = InMemoryCommerceStore()
    w = World(clock, providers.demo_atelier, providers.registry, store, CommerceService(
        store=store, registry=providers.registry, environment="development", clock=clock), member_session())
    d = w.svc.create_delegation(w.member, client_id=AGENT_CLIENT, mode=AssistanceMode.PREPARE,
                                allowed_providers={"demo_atelier"}, limits=None, expires_at=clock.now + timedelta(days=1))
    ag = agent(d.id, d.scopes)
    _, quote, op = w.prepared(ag, line("overshirt"), line("bag"))  # the agent prepares
    approval = w.approve(op)  # the member approves on the trusted surface
    res = w.svc.execute_purchase(w.member, operation_id=op.id, approval_id=approval.id,
                                 idempotency_key="live-stripe-" + os.urandom(6).hex())
    assert res.state == "accepted"
    order = _order(w, res)
    pi = w.provider._orders[order.provider_order_ref].payment_ref
    assert pi.startswith("pi_") and order.payment_status == "authorized"
    w.svc.handle_webhook("demo_atelier", *w.provider.ship(order.provider_order_ref)[0])  # captures in Stripe
    assert w.store.get("orders", order.id).payment_status == "captured"
    w.provider.arm(Behavior.REFUND, source_variant_ref="demo-bag-m", quantity=1)
    w.svc.handle_webhook("demo_atelier", *w.provider.refund(order.provider_order_ref)[0])
    o = w.store.get("orders", order.id)
    assert o.payment_status == "partially_refunded" and o.refunded_total == Money(12900 + 1032, "USD")
    print(json.dumps({"payment_intent": pi, "quote_total": quote.total.to_wire(), "order": o.provider_order_ref,
                      "payment_status": o.payment_status, "refunded": o.refunded_total.to_wire()}))


# ----------------------------------------------------------------------- composition
@pytest.mark.parametrize("environment,env,code", [
    ("development", {"BRANDME_COMMERCE_PAYMENTS": "stripe_test"}, "stripe_test_not_configured"),
    ("development", {"BRANDME_COMMERCE_PAYMENTS": "stripe_test", "STRIPE_TEST_SECRET_KEY": "sk_live_" + "a" * 24},
     "stripe_key_refused"),
    ("development", {"BRANDME_COMMERCE_PAYMENTS": "paypal"}, "payments_rail_unknown"),
    ("production", {"BRANDME_COMMERCE_PAYMENTS": "simulated"}, "payments_rail_not_allowed"),
    ("sandbox", {"BRANDME_COMMERCE_PAYMENTS": "stripe_test", "STRIPE_TEST_SECRET_KEY": "sk_test_" + "a" * 24},
     "payments_rail_not_allowed"),
])
def test_composition_refuses_to_boot_rather_than_fall_back(environment, env, code):
    from brandme_core.domains.commerce.composition import CompositionError, build_providers
    with pytest.raises(CompositionError) as e:
        build_providers(environment, env=env)
    assert e.value.code == code and "sk_" not in str(e.value)


def test_composition_selects_the_rail_and_labels_it():
    pytest.importorskip("stripe")
    from brandme_core.domains.commerce.composition import build_providers
    sim = build_providers("development", env={})
    assert sim.payments_rail == "simulated" and sim.demo_atelier.payments.simulation
    stripe = build_providers("demo", env={"BRANDME_COMMERCE_PAYMENTS": "stripe_test",
                                          "STRIPE_TEST_SECRET_KEY": "rk_test_" + "a" * 24})
    conn = stripe.registry.get("demo_atelier")
    assert stripe.demo_atelier.payments.processor_id == "stripe_test" and conn.simulation  # the merchant is fictional
    assert "Stripe test mode" in conn.disclosure and "no real money" in conn.disclosure
    assert conn.capability("checkout.submit").state == "sandbox"
    assert conn.capability("checkout.submit").evidence_ref is None  # nothing exercised yet
    assert build_providers("production", env={}).registry.all() == []  # no simulated merchant outside dev


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
