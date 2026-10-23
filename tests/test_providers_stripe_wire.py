"""stripe-mock — WIRE SHAPE ONLY.

stripe-mock validates request shape against Stripe's OpenAPI spec and returns
canned fixtures (status stays requires_payment_method, metadata comes back {});
this proves wire validity, not payment behaviour.

The real ``SdkStripeWire`` (pinned egress client, API version, no retries) talks
to a local stripe-mock v0.206.0 (``tests/fixtures/providers/stripe_mock.py``).
Without the binary every test here is skipped with a "not run" reason, never
reported as passed. Evidence label: "wire shape only".
"""

from datetime import timedelta

import pytest

from brandme_core.domains.commerce.money import Money
from brandme_core.domains.providers.contracts import ProviderError, ProviderErrorKind
from brandme_core.domains.providers.payments import PaymentAuthorization, payment_key
from brandme_core.domains.providers.payments.stripe_test import StripeTestConfig, StripeTestPaymentProcessor
from tests.fixtures.providers import stripe_events
from tests.fixtures.providers.stripe_mock import stripe_mock_url  # noqa: F401  (fixture)

SK_TEST = "sk_" + "test_" + "0" * 24
BASE = "bm-" + "fedcba9876543210" * 2
PURPOSE = "demo-order-fedcba9876543210fedcba98"
LABEL = "wire shape only"
_DOC = ("stripe-mock validates request shape against Stripe's OpenAPI spec and returns canned fixtures (status stays "
        "requires_payment_method, metadata comes back {}); this proves wire validity, not payment behaviour.")


def _wire(url, **kw):
    pytest.importorskip("stripe")
    from brandme_core.domains.providers.payments.stripe_wire import SdkStripeWire
    return SdkStripeWire(StripeTestConfig(SK_TEST), api_base=url, **kw)


def _processor(wire, clock=None):
    from datetime import datetime, timezone
    return StripeTestPaymentProcessor(StripeTestConfig(SK_TEST), wire=wire, environment="development",
                                      clock=clock or (lambda: datetime.now(timezone.utc)), log=lambda r: None)


def _auth(key=BASE, purpose=PURPOSE):
    return PaymentAuthorization(payment_key(key, "authorize"), Money(9612, "USD"), "demo-atelier-stripe-test", purpose,
                                "pm_card_visa", {"brandme_provider": "demo_atelier",
                                                 "brandme_merchant": "fictional-demo-merchant",
                                                 "brandme_quote_hash": "sha256:" + "a" * 64,
                                                 "brandme_simulated_merchant": "true"})


def test_wire_shape_canary_rejects_payment_method_types(stripe_mock_url):
    __doc__ = _DOC  # noqa: F841
    from brandme_core.domains.providers.payments.stripe_wire import WireError
    wire = _wire(stripe_mock_url)
    with pytest.raises(WireError) as e:  # proves the mock validates what it is sent
        wire.create_payment_intent({"amount": 100, "currency": "usd", "payment_method_types": ["card"],
                                    "automatic_payment_methods": {"enabled": True}}, idempotency_key=BASE + ":authorize")
    assert e.value.kind == "invalid_request"


def test_wire_shape_processor_calls_are_accepted(stripe_mock_url):
    """stripe-mock accepts every request the processor makes. No status or metadata assertions: canned fixtures."""
    from brandme_core.domains.providers.payments.stripe_wire import WireError
    wire = _wire(stripe_mock_url)
    p = _processor(wire)
    a = p.authorize(_auth())
    assert a.payment_ref.startswith("pi_") and a.test_mode
    for call in (lambda: p.capture(a.payment_ref, Money(9612, "USD"), idempotency_key=payment_key(BASE, "capture")),
                 lambda: p.void(a.payment_ref, idempotency_key=payment_key(BASE, "void")),
                 lambda: p.refund(a.payment_ref, Money(100, "USD"), idempotency_key=payment_key(BASE, "refund", 1)),
                 lambda: p.lookup(a.payment_ref),
                 lambda: p.operation_effect(a.payment_ref, payment_key(BASE, "refund", 1))):
        try:
            call()
        except ProviderError as e:  # mapped outcomes are fine; a refused request shape is not
            assert not isinstance(e.__cause__, WireError) or e.__cause__.kind != "invalid_request"
    wire.search_payment_intents(f"metadata['brandme_purpose_ref']:'{PURPOSE}'")
    wire.list_payment_intents(created_gte=1, starting_after=None)


def test_wire_headers_idempotency_version_single_attempt(stripe_mock_url):
    client = stripe_events.recording_client()
    wire = _wire(stripe_mock_url, http_client=client)
    pi = wire.create_payment_intent({"amount": 9612, "currency": "usd", "capture_method": "manual", "confirm": True,
                                     "payment_method": "pm_card_visa",
                                     "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"}},
                                    idempotency_key=BASE + ":authorize")
    wire.retrieve_payment_intent(pi["id"])
    wire.capture_payment_intent(pi["id"], {"amount_to_capture": 9612}, idempotency_key=BASE + ":capture")
    wire.list_refunds(pi["id"])
    methods = [m for m, _, _ in client.attempts]
    assert methods == ["POST", "GET", "POST", "GET"]  # exactly one attempt per call: no SDK retries
    for method, url, headers in client.attempts:
        assert url.startswith(stripe_mock_url)
        assert headers["stripe-version"] == "2026-09-30.endive"
        assert ("idempotency-key" in headers) == (method == "POST")
    assert [h["idempotency-key"] for m, _, h in client.attempts if m == "POST"] == [BASE + ":authorize",
                                                                                   BASE + ":capture"]
    assert all("x-stripe-client-telemetry" not in h for _, _, h in client.attempts)


def test_wire_lost_response_is_outcome_unknown(stripe_mock_url):
    client = stripe_events.lose_response_client()
    p = _processor(_wire(stripe_mock_url, http_client=client))
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth())
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN and e.value.transmitted
    assert client.lost == ["payment_intents"]  # the request was sent; only its answer was lost


def _offline_flow_calls():
    """Run the founder flow (and a decline, a void and a lost answer) on the semantics double; return its requests."""
    from brandme_core.domains.providers.local_atelier import Behavior
    from brandme_core.domains.providers.payments.stripe_test import StripeTestConfig, StripeTestPaymentProcessor
    from tests.fixtures.commerce.harness import line, world
    from tests.fixtures.providers.stripe_double import StripeSemanticsDouble
    holder = {}

    def rail(clock):
        holder["double"] = StripeSemanticsDouble(clock)
        return StripeTestPaymentProcessor(StripeTestConfig(SK_TEST), wire=holder["double"], environment="development",
                                          clock=clock, log=lambda r: None)
    w = world(payments=rail)

    def buy(*lines_, key):
        _, _, op = w.prepared(w.member, *lines_)
        return w.svc.execute_purchase(w.member, operation_id=op.id, approval_id=w.approve(op).id, idempotency_key=key)
    res = buy(line("overshirt"), line("bag"), key="wire-replay-buy-000001")
    ref = w.store.get("orders", res.order_id).provider_order_ref
    for h, b in w.provider.ship(ref):
        w.svc.handle_webhook("demo_atelier", h, b)
    w.provider.arm(Behavior.REFUND, source_variant_ref="demo-bag-m", quantity=1)
    w.provider.refund(ref)
    cancelled = buy(line("trousers"), key="wire-replay-buy-000002")
    w.svc.request_cancellation(w.member, cancelled.order_id, idempotency_key="wire-replay-cancel-0001")
    w.provider.arm(Behavior.REJECTED_AUTH)
    assert buy(line("dress"), key="wire-replay-buy-000003").state == "rejected"
    holder["double"].lose_next("create_payment_intent")
    holder["double"].search_lag = timedelta(minutes=30)  # search misses it; the list scan finds it
    lost = buy(line("jacket"), key="wire-replay-buy-000004")
    w.clock.advance(minutes=3)
    assert w.svc.reconcile(lost.id).state == "accepted"
    return holder["double"].calls


def test_wire_shape_every_request_of_the_offline_flow(stripe_mock_url):
    """Wire shape only: each request the processor made in the offline flow is replayed to stripe-mock.

    stripe-mock validates request shape against Stripe's OpenAPI spec and returns canned fixtures (status stays
    requires_payment_method, metadata comes back {}); this proves wire validity, not payment behaviour. No status
    or metadata is asserted; only that no request shape is refused."""
    from brandme_core.domains.providers.payments.stripe_wire import WireError
    wire = _wire(stripe_mock_url)
    calls = _offline_flow_calls()
    methods = {c[0] for c in calls}
    assert {"create_payment_intent", "capture_payment_intent", "cancel_payment_intent", "create_refund",
            "retrieve_payment_intent", "list_refunds", "search_payment_intents", "list_payment_intents"} <= methods
    ids = {}  # double object id -> stripe-mock object id
    refused = []
    for method, request, key in calls:
        try:
            if method == "create_payment_intent":
                out = wire.create_payment_intent(request, idempotency_key=key)
                ids.setdefault(f"#{len(ids)}", out["id"])
                continue
            if method in ("capture_payment_intent", "cancel_payment_intent"):
                pi, params = request
                getattr(wire, method)(ids.get(pi, _any(ids)), params, idempotency_key=key)
            elif method == "create_refund":
                wire.create_refund({**request, "payment_intent": _any(ids)}, idempotency_key=key)
            elif method in ("retrieve_payment_intent", "list_refunds"):
                getattr(wire, method)(_any(ids))
            elif method == "search_payment_intents":
                wire.search_payment_intents(request)
            elif method == "list_payment_intents":
                wire.list_payment_intents(created_gte=request["created_gte"], starting_after=None)
        except WireError as e:
            if e.kind == "invalid_request":
                refused.append((method, e.code))
            elif e.kind != "card_error":
                raise
    assert refused == [] and len(calls) > 20


def _any(ids):
    return next(iter(ids.values()))


def test_wire_canned_response_is_never_accepted(stripe_mock_url):
    """Wire shape only. stripe-mock's canned PaymentIntent carries none of the order's binding (metadata {}), so the
    merchant voids it and rejects the purchase: a canned or foreign object is never taken as this order's payment."""
    from brandme_core.domains.providers.payments.stripe_test import StripeTestPaymentProcessor
    from tests.fixtures.commerce.harness import line, world
    wire = _wire(stripe_mock_url)
    w = world(payments=lambda clock: StripeTestPaymentProcessor(StripeTestConfig(SK_TEST), wire=wire,
                                                                environment="development", clock=clock,
                                                                log=lambda r: None))
    stock = dict(w.provider._stock)
    _, _, op = w.prepared(w.member, line())
    res = w.svc.execute_purchase(w.member, operation_id=op.id, approval_id=w.approve(op).id,
                                 idempotency_key="wire-canned-00000001")
    assert (res.state, res.reason_code) == ("rejected", "payment_binding_mismatch")
    assert w.store.rows("orders") == [] and w.provider._stock == stock
    (rec,) = w.provider._orders.values()
    assert rec.release_reason == "binding_mismatch" and rec.pending == {}


def test_unreachable_processor_is_outcome_unknown_for_writes_and_transient_for_reads():
    p = _processor(_wire("http://127.0.0.1:9"))
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth())
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN and e.value.transmitted
    with pytest.raises(ProviderError) as e:
        p.lookup("pi_123")
    assert e.value.kind is ProviderErrorKind.TRANSIENT and not e.value.transmitted


def test_evidence_label_is_stated():
    assert LABEL == "wire shape only" and _DOC in __doc__.replace("\n", " ")
