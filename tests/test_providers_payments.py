"""Payment processors behind the merchant adapter: the simulated rail, and the Stripe test-mode guards.

Evidence kinds, kept apart (each module says which it is):
* this module: the deterministic simulated processor (app behaviour) and the
  Stripe key, secret and endpoint guards (no network, no SDK needed);
* ``test_providers_stripe.py``: the real Stripe processor over a FIXTURE DOUBLE,
  NOT STRIPE (adapter logic only);
* ``test_providers_stripe_wire.py``: stripe-mock, WIRE SHAPE ONLY;
* ``test_commerce_stripe_live.py``: Stripe test mode itself, ``not_run`` without
  ``STRIPE_TEST_SECRET_KEY``.
"""

from datetime import datetime, timedelta, timezone

import pytest

from brandme_core.domains.commerce.money import Money
from brandme_core.domains.providers.contracts import ProviderError, ProviderErrorKind
from brandme_core.domains.providers.payments import (
    PAYMENT_OPS, RAIL_MODES, TEST_CARD, TEST_CARD_DECLINED, TEST_CARD_NEEDS_AUTHENTICATION, PaymentAuthorization,
    PaymentRailDescriptor, PaymentState, assert_payment_rail_allowed, base_of, payment_key,
)
from brandme_core.domains.providers.payments.simulated import (
    HOLD_TTL, PaymentBehavior, SimulatedPaymentProcessor,
)
from brandme_core.domains.providers.payments.stripe_test import (
    StripeKeyRefused, StripeTestConfig, require_api_base, require_loopback_api_base, require_test_secret_key,
    require_webhook_secret,
)
from brandme_core.domains.providers.registry import SimulationInProductionError

USD = lambda n: Money(n, "USD")  # noqa: E731
SK_TEST = "sk_" + "test_" + "0" * 24  # built at runtime: no key-shaped literal in the repo


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def _auth(key="pay-key-0000000001:authorize", amount=9612, token=TEST_CARD, purpose="demo-order-1", **kw):
    return PaymentAuthorization(key, USD(amount), "demo-payee", purpose, token, **kw)


# ----------------------------------------------------------------- simulated processor
def test_simulated_authorization_is_idempotent_and_never_charges_twice():
    p = SimulatedPaymentProcessor(Clock())
    a = p.authorize(_auth())
    assert (a.status, a.authorized, a.captured) == ("authorized", USD(9612), USD(0))
    assert p.authorize(_auth()).payment_ref == a.payment_ref
    assert [c for c in p.calls if c[0] == "authorize"] == [("authorize", "pay-key-0000000001:authorize")] * 2


def test_simulated_decline_and_lost_response():
    p = SimulatedPaymentProcessor(Clock())
    ok = p.authorize(_auth("pay-key-ok-000000001:authorize", purpose="demo-order-ok"))
    d = p.authorize(_auth("pay-key-decline-0001:authorize", token=TEST_CARD_DECLINED, purpose="demo-order-dc"))
    assert d.status == "failed" and d.decline_code == "card_declined"
    sca = p.authorize(_auth("pay-key-sca-00000001:authorize", token=TEST_CARD_NEEDS_AUTHENTICATION,
                            purpose="demo-order-sca"))
    assert sca.status == "requires_action"
    assert p.void(sca.payment_ref, idempotency_key="pay-key-sca-00000001:void").status == "voided"
    assert p.find("demo-order-ok", settled=True).payment_ref == ok.payment_ref
    assert p.find("demo-order-none", settled=True) is None
    p.arm(PaymentBehavior.TIMEOUT_AFTER_ACCEPT)
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth("pay-key-timeout-0001:authorize"))
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN and e.value.transmitted
    # Reconciling with the same key finds the payment the lost response belonged to.
    assert p.authorize(_auth("pay-key-timeout-0001:authorize")).status == "authorized"


def test_simulated_capture_void_refund_and_expiry():
    clock = Clock()
    p = SimulatedPaymentProcessor(clock)
    a = p.authorize(_auth())
    c = p.capture(a.payment_ref, USD(8900), idempotency_key="pay-key-0000000001:capture")  # one line cancelled first
    assert (c.status, c.captured) == ("captured", USD(8900))
    assert (c.released, c.release_reason) == (USD(712), "partial_capture_remainder")
    assert p.capture(a.payment_ref, USD(8900), idempotency_key="pay-key-0000000001:capture") == p.lookup(a.payment_ref)
    r = p.refund(a.payment_ref, USD(1000), idempotency_key="pay-key-0000000001:refund:1")
    assert (r.status, r.refunded) == ("partially_refunded", USD(1000))
    with pytest.raises(ProviderError):  # cannot refund more than was captured
        p.refund(a.payment_ref, USD(8000), idempotency_key="pay-key-0000000001:refund:2")
    assert p.refund(a.payment_ref, USD(7900), idempotency_key="pay-key-0000000001:refund:3").status == "refunded"
    v = p.authorize(_auth("pay-key-0000000002:authorize", purpose="demo-order-2"))
    voided = p.void(v.payment_ref, idempotency_key="pay-key-0000000002:void")
    assert (voided.status, voided.released, voided.release_reason) == ("voided", USD(9612), "merchant_void")
    with pytest.raises(ProviderError):
        p.capture(v.payment_ref, USD(1), idempotency_key="pay-key-0000000002:capture")
    e = p.authorize(_auth("pay-key-0000000003:authorize", purpose="demo-order-3"))
    assert e.capture_before == clock.now + HOLD_TTL
    clock.now += HOLD_TTL
    expired = p.lookup(e.payment_ref)
    assert (expired.status, expired.release_reason) == ("voided", "authorization_expired")


def test_card_numbers_are_never_payment_tokens():
    with pytest.raises(ProviderError):
        SimulatedPaymentProcessor(Clock()).authorize(_auth(token="4242424242424242"))


def test_live_payment_state_is_unrepresentable():
    with pytest.raises(ValueError):
        PaymentState("pi_x", "captured", USD(1), USD(1), USD(0), Clock()(), test_mode=False)


def test_simulated_processor_refused_outside_dev():
    for env in ("sandbox", "production"):
        with pytest.raises(SimulationInProductionError):
            SimulatedPaymentProcessor(Clock(), environment=env)


def test_simulated_authorize_echoes_binding_and_replays_key():
    p = SimulatedPaymentProcessor(Clock(), environment="demo")
    a = p.authorize(_auth(environment="demo"))
    assert (a.purpose_ref, a.payee_ref, a.environment, a.authorize_key) == (
        "demo-order-1", "demo-payee", "demo", "pay-key-0000000001:authorize")
    assert a.evidence_ref == "sim:payment_for:demo-order-1" and "simpay_" not in a.evidence_ref
    assert p.authorize(_auth(environment="demo")).payment_ref == a.payment_ref
    with pytest.raises(ProviderError) as e:  # same key, different amount: refused like Stripe's idempotency error
        p.authorize(_auth(amount=9613, environment="demo"))
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN and e.value.transmitted
    with pytest.raises(ProviderError) as e:  # the processor only pays its own payee
        p.authorize(PaymentAuthorization("pay-key-0000000009:authorize", USD(100), "someone-else", "demo-order-9",
                                         TEST_CARD, environment="demo"))
    assert e.value.kind is ProviderErrorKind.CONTRACT_RESTRICTED and e.value.detail == "payee_mismatch"
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth("pay-key-0000000010:authorize", purpose="demo-order-10", environment="demo",
                          capture="automatic"))
    assert e.value.kind is ProviderErrorKind.UNSUPPORTED


def test_simulated_refused_op_does_not_poison_its_key():
    p = SimulatedPaymentProcessor(Clock())
    a = p.authorize(_auth())
    with pytest.raises(ProviderError) as e:
        p.capture(a.payment_ref, USD(99_999), idempotency_key="pay-key-0000000001:capture")
    assert e.value.kind is ProviderErrorKind.CONTRACT_RESTRICTED
    assert p.capture(a.payment_ref, USD(9612), idempotency_key="pay-key-0000000001:capture").status == "captured"
    with pytest.raises(ProviderError) as e:  # a key that succeeded cannot be reused for a different call
        p.capture(a.payment_ref, USD(100), idempotency_key="pay-key-0000000001:capture")
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN and e.value.transmitted


@pytest.mark.parametrize("op", ["capture", "void", "refund"])
def test_simulated_response_lost_applies_effect_then_operation_effect_applied(op):
    p = SimulatedPaymentProcessor(Clock())
    a = p.authorize(_auth())
    if op == "refund":
        p.capture(a.payment_ref, USD(9612), idempotency_key="pay-key-0000000001:capture")
    key = payment_key("pay-key-0000000001", op, 1 if op == "refund" else None)
    assert p.operation_effect(a.payment_ref, key) == "absent"
    p.arm(PaymentBehavior.RESPONSE_LOST, op=op)
    call = {"capture": lambda: p.capture(a.payment_ref, USD(9612), idempotency_key=key),
            "void": lambda: p.void(a.payment_ref, idempotency_key=key),
            "refund": lambda: p.refund(a.payment_ref, USD(500), idempotency_key=key)}[op]
    with pytest.raises(ProviderError) as e:
        call()
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN and e.value.transmitted
    assert p.operation_effect(a.payment_ref, key) == "applied"
    assert p.lookup(a.payment_ref).status == {"capture": "captured", "void": "voided",
                                              "refund": "partially_refunded"}[op]
    call()  # the same key re-sent is a replay, not a second effect
    assert p.lookup(a.payment_ref).refunded == USD(500 if op == "refund" else 0)


def test_simulated_lost_before_processing_leaves_the_effect_absent():
    p = SimulatedPaymentProcessor(Clock())
    a = p.authorize(_auth())
    p.arm(PaymentBehavior.LOST_BEFORE_PROCESSING, op="capture")
    with pytest.raises(ProviderError):
        p.capture(a.payment_ref, USD(9612), idempotency_key="pay-key-0000000001:capture")
    assert p.operation_effect(a.payment_ref, "pay-key-0000000001:capture") == "absent"
    assert p.lookup(a.payment_ref).status == "authorized"


def test_simulated_find_unsettled_raises_transient_settled_returns_none():
    p = SimulatedPaymentProcessor(Clock())
    with pytest.raises(ProviderError) as e:
        p.find("demo-order-nothing", settled=False)
    assert e.value.kind is ProviderErrorKind.TRANSIENT and e.value.detail == "payment_lookup_unsettled"
    assert p.find("demo-order-nothing", settled=True) is None


def test_simulated_amount_mismatch_holds_a_different_amount():
    p = SimulatedPaymentProcessor(Clock())
    p.arm(PaymentBehavior.AMOUNT_MISMATCH)
    a = p.authorize(_auth())
    assert a.authorized == USD(9613) and p.authorize(_auth()).payment_ref == a.payment_ref


def test_payment_key_shape_and_base_of_roundtrip():
    base = "bm-" + "a" * 32
    assert payment_key(base, "authorize") == base + ":authorize"
    assert payment_key(base, "refund", 999) == base + ":refund:999" and len(payment_key(base, "refund", 999)) <= 160
    for op in PAYMENT_OPS:
        assert base_of(payment_key(base, op)) == base
    assert base_of(payment_key(base, "refund", 7)) == base
    for bad in ("short", "has space in it here", "x" * 129):
        with pytest.raises(ValueError):
            payment_key(bad, "capture")
    with pytest.raises(ValueError):
        payment_key(base, "charge")
    for seq in (0, 1000, True):
        with pytest.raises(ValueError):
            payment_key(base, "refund", seq)
    for bad in (None, "nocolon", base + ":charge", base + ":refund:0", "short:capture", base + ":capture:1:2"):
        assert base_of(bad) is None


def test_rail_descriptors_labels_modes_and_allowed_environments():
    def rail(mode, env, label="Simulated payment — no real payment occurs."):
        return PaymentRailDescriptor("p", mode, env, label, "demo-payee")
    assert RAIL_MODES == ("simulated", "sandbox")
    for env in ("demo", "development"):
        assert_payment_rail_allowed(env, rail("simulated", env))
        assert_payment_rail_allowed(env, rail("sandbox", env))
    assert_payment_rail_allowed("sandbox", rail("sandbox", "sandbox"))
    with pytest.raises(SimulationInProductionError):
        assert_payment_rail_allowed("sandbox", rail("simulated", "sandbox"))
    with pytest.raises(SimulationInProductionError):
        assert_payment_rail_allowed("production", rail("simulated", "production"))
    with pytest.raises(ValueError, match="payment_rail_not_allowed"):
        assert_payment_rail_allowed("production", rail("sandbox", "production"))
    with pytest.raises(ValueError, match="payment_rail_environment_mismatch"):
        assert_payment_rail_allowed("development", rail("simulated", "demo"))
    for label in ("", "   ", "x" * 201):
        with pytest.raises(ValueError):
            rail("simulated", "demo", label)
    with pytest.raises(ValueError):
        rail("live", "production")
    sim = SimulatedPaymentProcessor(Clock()).descriptor
    assert sim.to_operator() == {"processor_id": "simulated", "mode": "simulated",
                                 "label": "Simulated payment — no real payment occurs.", "currencies": ["USD"],
                                 "api_version": None, "webhooks_configured": False}


# ------------------------------------------------------------------- Stripe key guard
def _k(prefix, body="a" * 24):
    return prefix + body


@pytest.mark.parametrize("key,code", [
    (_k("sk_" + "live_"), "stripe_live_key_refused"),
    (_k("rk_" + "live_"), "stripe_live_key_refused"),
    (_k("pk_" + "test_"), "stripe_publishable_key_refused"),
    (_k("pk_" + "live_"), "stripe_publishable_key_refused"),
    ("", "stripe_key_missing"),
    (None, "stripe_key_missing"),
    (" " + _k("sk_" + "test_"), "stripe_key_malformed"),
    (_k("sk_" + "test_") + "\n", "stripe_key_malformed"),
    ("sk_" + "test_short", "stripe_key_not_test_secret"),
    (_k("whsec_"), "stripe_key_not_test_secret"),
    (_k("sk_" + "test_", "a" * 20 + "-" + "b" * 4), "stripe_key_not_test_secret"),
])
def test_stripe_key_guard_refuses_live_publishable_webhook_and_malformed_keys(key, code):
    with pytest.raises(StripeKeyRefused) as e:
        require_test_secret_key(key)
    assert e.value.code == code and str(e.value) == code
    if key:
        assert key.strip() not in str(e.value) and key.strip() not in repr(e.value)


@pytest.mark.parametrize("key", ["sk_" + "test_" + "0" * 24, "rk_" + "test_" + "A1" * 12])
def test_stripe_key_guard_accepts_runtime_built_test_keys(key):
    """sk_test_, and the least-privilege restricted rk_test_ (founder decision: keep restricted test keys)."""
    assert require_test_secret_key(key) == key


def test_stripe_config_repr_hides_secrets():
    whsec = "whsec_" + "9" * 24
    cfg = StripeTestConfig(SK_TEST, webhook_secrets=(whsec,), egress_proxy="http://user:pw@proxy.internal:3128")
    text = repr(cfg) + str(cfg)
    assert SK_TEST not in text and whsec not in text and "pw@" not in text


def test_webhook_secret_guard():
    assert require_webhook_secret("whsec_" + "a" * 32)
    for bad in ("", None, "whsec_short", "sk_" + "test_" + "a" * 24, " whsec_" + "a" * 32):
        with pytest.raises(StripeKeyRefused) as e:
            require_webhook_secret(bad)
        assert e.value.code == "stripe_webhook_secret_refused"


def test_loopback_api_base_only():
    for bad in ("https://evil.example", "http://10.0.0.1:12111", "http://127.0.0.1:12111/v1", "https://api.stripe.com/"):
        with pytest.raises(StripeKeyRefused):
            require_api_base(bad)
    assert require_api_base("http://127.0.0.1:12111") == "http://127.0.0.1:12111"
    assert require_api_base("https://api.stripe.com") == "https://api.stripe.com"
    with pytest.raises(StripeKeyRefused):
        require_loopback_api_base("https://api.stripe.com")


def test_stripe_config_reads_only_its_env_names():
    with pytest.raises(StripeKeyRefused) as e:
        StripeTestConfig.from_env({"STRIPE_SECRET_KEY": SK_TEST, "STRIPE_API_KEY": SK_TEST,
                                   "ANTHROPIC_API_KEY": "x", "HTTPS_PROXY": "http://proxy:1"})
    assert e.value.code == "stripe_key_missing"
    cfg = StripeTestConfig.from_env({"STRIPE_TEST_SECRET_KEY": SK_TEST, "HTTPS_PROXY": "http://ambient:1",
                                     "SSL_CERT_FILE": "/ambient.pem"})
    assert cfg.egress_proxy is None and cfg.ca_bundle is None  # ambient proxy and CA settings are never read
    cfg = StripeTestConfig.from_env({"STRIPE_TEST_SECRET_KEY": SK_TEST,
                                     "BRANDME_STRIPE_EGRESS_PROXY": "http://proxy.internal:3128",
                                     "BRANDME_STRIPE_CA_BUNDLE": "/etc/ssl/brandme-stripe.pem"})
    assert (cfg.egress_proxy, cfg.ca_bundle) == ("http://proxy.internal:3128", "/etc/ssl/brandme-stripe.pem")
    for name, value, code in (("BRANDME_STRIPE_EGRESS_PROXY", "socks5://x:1", "stripe_egress_proxy_refused"),
                              ("BRANDME_STRIPE_CA_BUNDLE", "relative.pem", "stripe_ca_bundle_refused"),
                              ("STRIPE_TEST_WEBHOOK_SECRET", "nope", "stripe_webhook_secret_refused")):
        with pytest.raises(StripeKeyRefused) as e:
            StripeTestConfig.from_env({"STRIPE_TEST_SECRET_KEY": SK_TEST, name: value})
        assert e.value.code == code


def test_stripe_rail_needs_a_test_environment():
    from brandme_core.domains.providers.payments.stripe_test import StripeTestPaymentProcessor
    from tests.fixtures.providers.stripe_double import StripeSemanticsDouble
    clock = Clock()
    with pytest.raises(ValueError, match="stripe_test_not_allowed"):
        StripeTestPaymentProcessor(StripeTestConfig(SK_TEST), wire=StripeSemanticsDouble(clock),
                                   environment="production", clock=clock)
    p = StripeTestPaymentProcessor(StripeTestConfig(SK_TEST), wire=StripeSemanticsDouble(clock),
                                   environment="sandbox", clock=clock)
    assert p.descriptor.mode == "sandbox" and p.descriptor.api_version == "2026-09-30.endive"
    assert p.descriptor.label == "Stripe test mode — no real money moves." and not p.descriptor.webhooks_configured
    assert p.test_instruments == (TEST_CARD, TEST_CARD_DECLINED)
    assert timedelta(days=8) == StripeTestConfig(SK_TEST).lookback
