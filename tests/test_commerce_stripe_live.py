"""LIVE: Stripe test mode (sandbox evidence). No real money moves; only Stripe test cards are used.

Gated on ``STRIPE_TEST_SECRET_KEY``. Absent, every test is skipped with a reason
that starts ``not_run`` — never reported as passed. A key that is set but is not
a test key (``sk_test_…`` or restricted ``rk_test_…``) fails; it does not skip.

Egress: the adapter ignores ambient proxy and CA settings. Behind a proxy, set
``BRANDME_STRIPE_EGRESS_PROXY`` and ``BRANDME_STRIPE_CA_BUNDLE`` explicitly.
"""

import os
import uuid

import pytest

from brandme_core.domains.commerce.money import Money
from brandme_core.domains.providers.payments import PaymentAuthorization, payment_key

KEY = os.environ.get("STRIPE_TEST_SECRET_KEY")
pytestmark = pytest.mark.skipif(not KEY, reason="not_run: STRIPE_TEST_SECRET_KEY absent (live Stripe test mode)")
USD = lambda n: Money(n, "USD")  # noqa: E731
LABEL = "sandbox evidence"


@pytest.fixture
def run_tag():
    return "run-" + uuid.uuid4().hex[:16]


@pytest.fixture
def live_processor(run_tag):
    from datetime import datetime, timezone
    from brandme_core.domains.providers.payments.stripe_test import (
        StripeTestConfig, StripeTestPaymentProcessor, require_test_secret_key,
    )
    from brandme_core.domains.providers.payments.stripe_wire import SdkStripeWire
    require_test_secret_key(KEY)  # a set non-test key fails here instead of skipping
    env = {k: v for k, v in os.environ.items() if k in ("STRIPE_TEST_SECRET_KEY", "BRANDME_STRIPE_EGRESS_PROXY",
                                                        "BRANDME_STRIPE_CA_BUNDLE")}
    base = StripeTestConfig.from_env(env)
    cfg = StripeTestConfig(base.secret_key, egress_proxy=base.egress_proxy, ca_bundle=base.ca_bundle, run_tag=run_tag)
    return StripeTestPaymentProcessor(cfg, wire=SdkStripeWire(cfg), environment="development",
                                      clock=lambda: datetime.now(timezone.utc), log=lambda r: None)


def _auth(base, amount, token="pm_card_visa"):
    return PaymentAuthorization(payment_key(base, "authorize"), USD(amount), "demo-atelier-stripe-test",
                                f"demo-order-live-{base[-12:]}", token)


def test_live_processor_authorize_capture_refund_void_decline(live_processor, record_property):
    base = "bm-live-" + uuid.uuid4().hex
    a = live_processor.authorize(_auth(base, 1500))
    assert a.status == "authorized" and a.test_mode and a.capture_before is not None
    assert live_processor.authorize(_auth(base, 1500)).payment_ref == a.payment_ref  # same key: same PaymentIntent
    c = live_processor.capture(a.payment_ref, USD(1000), idempotency_key=payment_key(base, "capture"))
    assert (c.status, c.captured) == ("captured", USD(1000))  # the remaining 500 is released
    r = live_processor.refund(a.payment_ref, USD(400), idempotency_key=payment_key(base, "refund", 1))
    assert (r.status, r.refunded) == ("partially_refunded", USD(400))
    vbase = "bm-live-" + uuid.uuid4().hex
    v = live_processor.authorize(_auth(vbase, 700))
    assert live_processor.void(v.payment_ref, idempotency_key=payment_key(vbase, "void")).status == "voided"
    d = live_processor.authorize(_auth("bm-live-" + uuid.uuid4().hex, 700, token="pm_card_chargeDeclined"))
    assert d.status == "failed" and d.decline_code
    record_property("statuses", [a.status, c.status, r.status, "voided", d.status])
