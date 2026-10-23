"""Payment processors behind the merchant adapter: simulated, and Stripe test mode.

Three kinds of evidence, kept apart:
* simulated processor tests prove payment *behaviour* in the app (deterministic);
* stripe-mock tests prove only that the Stripe adapter sends requests Stripe's
  OpenAPI spec accepts and maps its response shapes (stripe-mock answers with
  canned fixtures, so they say nothing about real payment outcomes);
* the live suite (``STRIPE_TEST_SECRET_KEY``) runs against Stripe test mode and is
  skipped, reported ``not_run``, when the key is absent.
"""

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from brandme_core.domains.commerce.money import Money
from brandme_core.domains.providers.contracts import ProviderError, ProviderErrorKind
from brandme_core.domains.providers.payments import PaymentAuthorization, PaymentState
from brandme_core.domains.providers.payments.simulated import (
    HOLD_TTL, SIMULATED_TOKEN, PaymentBehavior, SimulatedPaymentProcessor,
)
from tests.fixtures.providers.stripe_mock import stripe_mock_url  # noqa: F401  (fixture)

USD = lambda n: Money(n, "USD")  # noqa: E731


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def _auth(key="pay-key-0000000001", amount=9612, token=SIMULATED_TOKEN, **kw):
    return PaymentAuthorization(key, USD(amount), "demo-payee", "demo-order-1", token, **kw)


# ----------------------------------------------------------------- simulated processor
def test_simulated_authorization_is_idempotent_and_never_charges_twice():
    p = SimulatedPaymentProcessor(Clock())
    a = p.authorize(_auth())
    assert (a.status, a.authorized, a.captured) == ("authorized", USD(9612), USD(0))
    assert p.authorize(_auth()).payment_ref == a.payment_ref
    assert [c for c in p.calls if c[0] == "authorize"] == [("authorize", "pay-key-0000000001")] * 2


def test_simulated_decline_and_lost_response():
    p = SimulatedPaymentProcessor(Clock())
    p.arm(PaymentBehavior.DECLINE)
    d = p.authorize(_auth("pay-key-decline-0001"))
    assert d.status == "failed" and d.decline_code == "card_declined"
    p.arm(PaymentBehavior.TIMEOUT_AFTER_ACCEPT)
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth("pay-key-timeout-0001"))
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN and e.value.transmitted
    # Reconciling with the same key finds the payment the lost response belonged to.
    assert p.authorize(_auth("pay-key-timeout-0001")).status == "authorized"


def test_simulated_capture_void_refund_and_expiry():
    clock = Clock()
    p = SimulatedPaymentProcessor(clock)
    a = p.authorize(_auth())
    c = p.capture(a.payment_ref, USD(8900), idempotency_key="cap-key-0000000001")  # one line cancelled first
    assert (c.status, c.captured) == ("captured", USD(8900))
    assert p.capture(a.payment_ref, USD(8900), idempotency_key="cap-key-0000000001") == p.lookup(a.payment_ref)
    r = p.refund(a.payment_ref, USD(1000), idempotency_key="ref-key-0000000001")
    assert (r.status, r.refunded) == ("partially_refunded", USD(1000))
    with pytest.raises(ProviderError):  # cannot refund more than was captured
        p.refund(a.payment_ref, USD(8000), idempotency_key="ref-key-0000000002")
    assert p.refund(a.payment_ref, USD(7900), idempotency_key="ref-key-0000000003").status == "refunded"
    v = p.authorize(_auth("pay-key-0000000002"))
    assert p.void(v.payment_ref, idempotency_key="void-key-000000001").status == "voided"
    with pytest.raises(ProviderError):
        p.capture(v.payment_ref, USD(1), idempotency_key="cap-key-0000000002")
    e = p.authorize(_auth("pay-key-0000000003"))
    clock.now += HOLD_TTL
    expired = p.lookup(e.payment_ref)
    assert (expired.status, expired.decline_code) == ("voided", "authorization_expired")


def test_card_numbers_are_never_payment_tokens():
    with pytest.raises(ProviderError):
        SimulatedPaymentProcessor(Clock()).authorize(_auth(token="4242424242424242"))


def test_live_payment_state_is_unrepresentable():
    with pytest.raises(ValueError):
        PaymentState("pi_x", "captured", USD(1), USD(1), USD(0), Clock()(), test_mode=False)


# ------------------------------------------------------------------- Stripe key guard
@pytest.mark.parametrize("key", ["sk_live_" + "a" * 24, "rk_live_" + "a" * 24, "pk_test_" + "a" * 24,
                                 "pk_live_" + "a" * 24, "sk_test_short", "", " sk_test_" + "a" * 24,
                                 "whsec_" + "a" * 24])
def test_stripe_adapter_refuses_anything_but_a_test_secret_key(key):
    stripe_test = pytest.importorskip("brandme_core.domains.providers.payments.stripe_test")
    with pytest.raises(ValueError):
        stripe_test.StripeTestPaymentProcessor(key)


@pytest.mark.parametrize("key", ["sk_test_" + "a" * 24, "rk_test_" + "A1" * 12])
def test_stripe_adapter_accepts_test_keys(key):
    stripe_test = pytest.importorskip("brandme_core.domains.providers.payments.stripe_test")
    assert stripe_test.require_test_key(key) == key


# ---------------------------------------------------- Stripe wire shape (stripe-mock)
@pytest.fixture
def stripe_wire(stripe_mock_url):
    from brandme_core.domains.providers.payments.stripe_test import StripeTestPaymentProcessor
    return StripeTestPaymentProcessor("sk_test_" + "0" * 24, base_url=stripe_mock_url)


def test_wire_shape_authorize_capture_void_refund_lookup(stripe_wire):
    """stripe-mock accepts every request; its canned PaymentIntent reads requires_payment_method."""
    a = stripe_wire.authorize(_auth(token="pm_card_visa", metadata={"brandme_operation_ref": "op-1"}))
    assert a.payment_ref.startswith("pi_") and a.test_mode and a.evidence_ref.startswith("stripe_test:pi:")
    assert a.status == "failed"  # canned fixture status mapped, not a real decline
    for state in (stripe_wire.capture(a.payment_ref, USD(9612), idempotency_key="cap-wire-000000001"),
                  stripe_wire.void(a.payment_ref, idempotency_key="void-wire-00000001"),
                  stripe_wire.refund(a.payment_ref, USD(100), idempotency_key="ref-wire-000000001"),
                  stripe_wire.lookup(a.payment_ref)):
        assert isinstance(state, PaymentState) and state.payment_ref.startswith("pi_")


def test_wire_shape_refuses_card_numbers_and_free_text_before_sending(stripe_wire):
    for bad in (_auth(token="4242424242424242"), _auth(token="pm_card_visa", metadata={"note": "ship to 1 Main St"})):
        with pytest.raises(ProviderError) as e:
            stripe_wire.authorize(bad)
        assert e.value.kind is ProviderErrorKind.CONTRACT_RESTRICTED


def test_unreachable_processor_is_outcome_unknown_for_writes_and_transient_for_reads():
    pytest.importorskip("stripe")
    from brandme_core.domains.providers.payments.stripe_test import StripeTestPaymentProcessor
    p = StripeTestPaymentProcessor("sk_test_" + "0" * 24, base_url="http://127.0.0.1:9")
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth(token="pm_card_visa"))
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN and e.value.transmitted
    with pytest.raises(ProviderError) as e:
        p.lookup("pi_123")
    assert e.value.kind is ProviderErrorKind.TRANSIENT and not e.value.transmitted


def _signed(payload: dict, secret: str, at: int):
    body = json.dumps(payload).encode()
    sig = hmac.new(secret.encode(), f"{at}.".encode() + body, hashlib.sha256).hexdigest()
    return {"Stripe-Signature": f"t={at},v1={sig}"}, body


def test_stripe_webhook_signatures_are_verified_and_live_events_refused():
    pytest.importorskip("stripe")
    from brandme_core.domains.providers.payments.stripe_test import StripeTestPaymentProcessor
    p = StripeTestPaymentProcessor("sk_test_" + "0" * 24, base_url="http://127.0.0.1:9")
    secret = "whsec_" + "1" * 32
    event = {"id": "evt_1", "object": "event", "type": "payment_intent.succeeded", "livemode": False,
             "data": {"object": {"id": "pi_1", "object": "payment_intent"}}}
    headers, body = _signed(event, secret, int(time.time()))
    assert p.verify_webhook(headers, body, secret).id == "evt_1"
    for h, b in (({"Stripe-Signature": headers["Stripe-Signature"]}, body + b" "),  # tampered
                 _signed(event, "whsec_" + "2" * 32, int(time.time())),  # wrong secret
                 _signed(event, secret, int(time.time()) - 3600),  # outside the replay window
                 _signed({**event, "livemode": True}, secret, int(time.time()))):  # live mode
        with pytest.raises(ProviderError) as e:
            p.verify_webhook(h, b, secret)
        assert e.value.kind is ProviderErrorKind.UNAUTHORIZED


# --------------------------------------------------------------- LIVE: Stripe test mode
live = pytest.mark.skipif(not os.environ.get("STRIPE_TEST_SECRET_KEY"),
                          reason="STRIPE_TEST_SECRET_KEY not set: Stripe test-mode run not_run")


@pytest.fixture
def stripe_live():
    from brandme_core.domains.providers.payments.stripe_test import StripeTestPaymentProcessor
    return StripeTestPaymentProcessor(os.environ["STRIPE_TEST_SECRET_KEY"])


@live
def test_live_test_mode_authorize_capture_refund_void_decline(stripe_live):
    run = os.urandom(6).hex()
    a = stripe_live.authorize(_auth(f"bm-live-auth-{run}", 1500, token="pm_card_visa"))
    assert a.status == "authorized" and a.test_mode
    assert stripe_live.authorize(_auth(f"bm-live-auth-{run}", 1500, token="pm_card_visa")).payment_ref == a.payment_ref
    c = stripe_live.capture(a.payment_ref, USD(1000), idempotency_key=f"bm-live-cap-{run}")
    assert (c.status, c.captured) == ("captured", USD(1000))  # the remaining 500 is released
    r = stripe_live.refund(a.payment_ref, USD(400), idempotency_key=f"bm-live-ref-{run}")
    assert (r.status, r.refunded) == ("partially_refunded", USD(400))
    v = stripe_live.authorize(_auth(f"bm-live-void-{run}", 700, token="pm_card_visa"))
    assert stripe_live.void(v.payment_ref, idempotency_key=f"bm-live-vd-{run}").status == "voided"
    d = stripe_live.authorize(_auth(f"bm-live-decl-{run}", 700, token="pm_card_chargeDeclined"))
    assert d.status == "failed" and d.decline_code
