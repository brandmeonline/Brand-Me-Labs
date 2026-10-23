"""LIVE: Stripe test mode (sandbox evidence). No real money moves; only Stripe test cards are used.

Gated on ``STRIPE_TEST_SECRET_KEY``. Absent, every test is skipped with a reason
that starts ``not_run`` — never reported as passed. A key that is set but is not
a test key (``sk_test_…`` or restricted ``rk_test_…``) fails; it does not skip.

The clock is real UTC. The webhook secret is generated per run: these tests sign
their own events over real PaymentIntent ids (real Stripe delivery needs the
gateway relay mounted; see the lane status doc). Every PaymentIntent carries
``brandme_run=<run tag>`` metadata, and teardown voids any still holding funds.
Recorded properties are sanitized facts only: statuses and counts, no ids.

Egress ignores ambient proxy and CA settings. Behind a proxy, set
``BRANDME_STRIPE_EGRESS_PROXY`` and ``BRANDME_STRIPE_CA_BUNDLE`` explicitly.
"""

import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from brandme_core.domains.commerce.money import Money
from brandme_core.domains.providers.payments import PaymentAuthorization, payment_key

KEY = os.environ.get("STRIPE_TEST_SECRET_KEY")
pytestmark = pytest.mark.skipif(not KEY, reason="not_run: STRIPE_TEST_SECRET_KEY absent (live Stripe test mode)")
USD = lambda n: Money(n, "USD")  # noqa: E731
LABEL = "sandbox evidence"
BAG = 12900 + 12900 * 800 // 10_000


class RealClock:
    def __call__(self) -> datetime:
        return datetime.now(timezone.utc)

    @property
    def now(self) -> datetime:
        return self()


def _config(**over):
    from brandme_core.domains.providers.payments.stripe_test import StripeTestConfig, require_test_secret_key
    require_test_secret_key(KEY)  # a set non-test key fails here instead of skipping
    env = {k: v for k, v in os.environ.items() if k in ("STRIPE_TEST_SECRET_KEY", "BRANDME_STRIPE_EGRESS_PROXY",
                                                        "BRANDME_STRIPE_CA_BUNDLE")}
    base = StripeTestConfig.from_env(env)
    return StripeTestConfig(base.secret_key, egress_proxy=base.egress_proxy, ca_bundle=base.ca_bundle, **over)


def _wire(cfg, http_client=None):
    from brandme_core.domains.providers.payments.stripe_wire import SdkStripeWire
    return SdkStripeWire(cfg, http_client=http_client)


def _lossy_wire(cfg):
    """The first POST is sent, and its answer is lost (a connection error after transmission)."""
    from tests.fixtures.providers import stripe_events
    return _wire(cfg, http_client=stripe_events.lose_response_client(cfg.timeout_seconds))


@pytest.fixture
def run(request):
    """A run tag, a webhook secret, and teardown that releases every hold this run left behind."""
    tag = "run-" + uuid.uuid4().hex[:16]
    started = int(time.time()) - 60
    secret = "whsec_" + uuid.uuid4().hex
    yield {"tag": tag, "secret": secret}
    cfg = _config(run_tag=tag)
    wire = _wire(cfg)
    released = 0
    cursor = None
    for _ in range(5):
        page, more = wire.list_payment_intents(created_gte=started, starting_after=cursor)
        for pi in page:
            if (pi.get("metadata") or {}).get("brandme_run") == tag and pi.get("status") == "requires_capture":
                wire.cancel_payment_intent(pi["id"], {"cancellation_reason": "abandoned"},
                                           idempotency_key=f"teardown-{tag}-{pi['id'][-8:]}")
                released += 1
        if not more or not page:
            break
        cursor = page[-1]["id"]
    request.node.user_properties.append(("teardown_released_holds", released))


def _world(run, wire_factory=None):
    from brandme_core.domains.commerce.service import CommerceService
    from brandme_core.domains.commerce.store import InMemoryCommerceStore
    from brandme_core.domains.providers.local_atelier import LocalAtelierProvider, local_atelier_connection
    from brandme_core.domains.providers.payments.stripe_test import StripeTestPaymentProcessor
    from brandme_core.domains.providers.registry import ProviderRegistry
    from tests.fixtures.commerce.harness import World, member_session
    clock = RealClock()
    cfg = _config(run_tag=run["tag"], webhook_secrets=(run["secret"],))
    rail = StripeTestPaymentProcessor(cfg, wire=(wire_factory or _wire)(cfg), environment="development", clock=clock,
                                      log=lambda r: None)
    provider = LocalAtelierProvider(clock, payments=rail)
    registry = ProviderRegistry("development")
    registry.register(local_atelier_connection(provider, "development", clock()))
    store = InMemoryCommerceStore()
    return World(clock, provider, registry, store, CommerceService(store=store, registry=registry,
                                                                   environment="development", clock=clock),
                 member_session())


def _buy(w, actor, *lines_, key):
    _, quote, op = w.prepared(actor, *lines_)
    res = w.svc.execute_purchase(actor, operation_id=op.id, approval_id=w.approve(op).id, idempotency_key=key)
    return quote, res


def _hook(w, deliveries):
    for headers, body in deliveries:
        w.svc.handle_webhook("demo_atelier", headers, body)


def test_live_simulator_purchase_through_stripe_test_mode(run, record_property):
    """The founder's check-in flow against Stripe test mode: an agent prepares, the member approves, the agent
    executes inside its grant, and the simulator merchant authorizes, captures and refunds. No real money moves."""
    from brandme_core.domains.providers.local_atelier import Behavior
    from tests.fixtures.commerce.harness import limits, line
    from tests.fixtures.providers import stripe_events
    w = _world(run)
    d, ag = w.delegate(lim=limits(refund_credit_back=True))
    quote, res = _buy(w, ag, line("overshirt"), line("bag"), key="live-founder-" + uuid.uuid4().hex[:12])
    assert res.state == "accepted"
    order = w.store.get("orders", res.order_id)
    rec = w.provider._orders[order.provider_order_ref]
    pay = w.provider.payments.lookup(rec.payment_ref)  # requires_capture, manual capture, livemode false
    assert (pay.status, pay.authorized, pay.purpose_ref) == ("authorized", quote.total, order.provider_order_ref)
    assert pay.capture_before is not None and pay.environment == "development"
    pi = w.provider.payments._wire.retrieve_payment_intent(rec.payment_ref)
    assert (pi["capture_method"], pi["livemode"], pi["metadata"]["brandme_run"]) == ("manual", False, run["tag"])
    event = stripe_events.payment_intent_event(pi, "payment_intent.amount_capturable_updated", run["secret"],
                                               int(time.time()))
    receipts = [w.svc.handle_webhook("demo_atelier", *event) for _ in range(2)]  # re-posted: one receipt
    assert receipts[0].event_id == receipts[1].event_id and len(w.store.rows("webhook_receipts")) == 1
    assert w.store.get("orders", order.id).payment_status == "authorized"
    _hook(w, w.provider.ship(order.provider_order_ref))  # a real test-mode capture
    captured = w.provider.payments.lookup(rec.payment_ref)
    assert captured.captured == quote.total and w.store.get("orders", order.id).payment_status == "captured"
    w.provider.arm(Behavior.REFUND, source_variant_ref="demo-bag-m", quantity=1)
    _hook(w, w.provider.refund(order.provider_order_ref))  # a real test-mode refund
    o = w.store.get("orders", order.id)
    assert o.payment_status == "partially_refunded" and o.refunded_total == USD(BAG)
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == USD(50_000 - (quote.total.amount_minor - BAG))
    status = w.registry.record_verification("demo_atelier", "checkout.submit", evidence_ref=f"stripe_test:run:{run['tag']}",
                                            evidence_kind="sandbox_operation", checked_at=w.clock())
    assert status.state == "sandbox"  # the merchant is a simulation: Stripe evidence never makes it verified
    record_property("statuses", [res.state, pay.status, captured.status, o.payment_status, status.state])


def test_live_processor_lost_response_reconciles_to_one_payment_intent(run, record_property):
    from tests.fixtures.commerce.harness import line
    w = _world(run, _lossy_wire)
    _, res = _buy(w, w.member, line(), key="live-lost-" + uuid.uuid4().hex[:12])
    assert res.state == "outcome_unknown"
    deadline = time.monotonic() + 180
    op = res
    while op.state == "outcome_unknown" and time.monotonic() < deadline:
        op = w.svc.reconcile(res.id)  # reads only: journal, Search, then the consistent List scan
        if op.state == "outcome_unknown":
            time.sleep(5)
    assert op.state == "accepted"
    purpose = w.store.get("orders", op.order_id).provider_order_ref
    wire = _wire(_config())
    page, _ = wire.list_payment_intents(created_gte=int(time.time()) - 900, starting_after=None)
    mine = [pi for pi in page if (pi.get("metadata") or {}).get("brandme_purpose_ref") == purpose]
    assert len(mine) == 1  # one order, exactly one PaymentIntent: the authorization was never re-sent
    record_property("payment_intents_for_purpose", len(mine))


def test_live_decline_with_stripe_test_card(run, record_property):
    from brandme_core.domains.providers.local_atelier import Behavior
    from tests.fixtures.commerce.harness import line
    w = _world(run)
    w.provider.arm(Behavior.REJECTED_AUTH)  # the merchant uses pm_card_chargeDeclined; Stripe declines it
    _, res = _buy(w, w.member, line(), key="live-decline-" + uuid.uuid4().hex[:12])
    assert (res.state, res.reason_code) == ("rejected", "payment_authorization_declined")
    assert len(w.provider.submit_calls) == 1 and w.store.rows("orders") == []
    record_property("statuses", [res.state, res.reason_code])


def test_live_cancel_before_capture_voids(run, record_property):
    from tests.fixtures.commerce.harness import line
    w = _world(run)
    _, res = _buy(w, w.member, line(), key="live-void-" + uuid.uuid4().hex[:12])
    order = w.store.get("orders", res.order_id)
    out = w.svc.request_cancellation(w.member, order.id, idempotency_key="live-cancel-" + uuid.uuid4().hex[:12])
    assert (out["status"], out["payment_status"]) == ("cancelled", "voided")
    pay = w.provider.payments.lookup(w.provider._orders[order.provider_order_ref].payment_ref)
    assert pay.status == "voided" and pay.captured == USD(0)
    record_property("statuses", [out["status"], pay.status])


def test_live_processor_authorize_capture_refund_void_decline(run, record_property):
    from brandme_core.domains.providers.payments.stripe_test import StripeTestPaymentProcessor
    cfg = _config(run_tag=run["tag"])
    p = StripeTestPaymentProcessor(cfg, wire=_wire(cfg), environment="development", clock=RealClock(),
                                   log=lambda r: None)

    def auth(base, amount, token="pm_card_visa"):
        return PaymentAuthorization(payment_key(base, "authorize"), USD(amount), "demo-atelier-stripe-test",
                                    f"demo-order-live-{base[-12:]}", token)
    base = "bm-live-" + uuid.uuid4().hex
    a = p.authorize(auth(base, 1500))
    assert a.status == "authorized" and a.test_mode and a.capture_before is not None
    assert a.capture_before > datetime.now(timezone.utc) + timedelta(days=5)
    assert p.authorize(auth(base, 1500)).payment_ref == a.payment_ref  # same key: same PaymentIntent
    c = p.capture(a.payment_ref, USD(1000), idempotency_key=payment_key(base, "capture"))
    assert (c.status, c.captured, c.release_reason) == ("captured", USD(1000), "partial_capture_remainder")
    r = p.refund(a.payment_ref, USD(400), idempotency_key=payment_key(base, "refund", 1))
    assert (r.status, r.refunded) == ("partially_refunded", USD(400))
    assert p.operation_effect(a.payment_ref, payment_key(base, "refund", 1)) == "applied"
    vbase = "bm-live-" + uuid.uuid4().hex
    v = p.authorize(auth(vbase, 700))
    assert p.void(v.payment_ref, idempotency_key=payment_key(vbase, "void")).status == "voided"
    d = p.authorize(auth("bm-live-" + uuid.uuid4().hex, 700, token="pm_card_chargeDeclined"))
    assert d.status == "failed" and d.decline_code
    record_property("statuses", [a.status, c.status, r.status, "voided", d.status])
