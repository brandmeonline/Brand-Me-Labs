"""Stripe Connect, brands flow (direct charges) — FIXTURE DOUBLE, NOT STRIPE, plus SDK wire shape.

Plan: ``docs/build/stripe-connect-plan.md`` Flow 1. The real ``StripeTestPaymentProcessor`` and
``StripeConnectAccounts`` run over ``StripeSemanticsDouble``. That proves adapter logic only: the
account configuration it sends, the readiness gate, routing every call to the connected account,
fee math, and webhook scoping. The last tests check the real ``SdkStripeWire`` against a loopback
server that records requests: the ``Stripe-Account`` header and the v2 paths. They are not Stripe.
Nothing here has run against Stripe test mode.
"""

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from brandme_core.domains.commerce.money import Money
from brandme_core.domains.providers.contracts import ProviderError, ProviderErrorKind
from brandme_core.domains.providers.payments import PaymentAuthorization, payment_key
from brandme_core.domains.providers.payments.stripe_connect import (
    EMBEDDED_COMPONENTS, ConnectedMerchant, StripeConnectAccounts,
)
from brandme_core.domains.providers.payments.stripe_test import StripeTestConfig, StripeTestPaymentProcessor
from tests.fixtures.providers import stripe_events
from tests.fixtures.providers.stripe_double import StripeSemanticsDouble

SK_TEST = "sk_" + "test_" + "0" * 24
BASE = "bm-" + "0123456789abcdef" * 2
PURPOSE = "demo-order-0123456789abcdef01234567"
PAYEE = "demo-atelier-stripe-test"
ACCOUNT_KEY = "bm-brand-0123456789abcdef:connect_account"
USD = lambda n: Money(n, "USD")  # noqa: E731


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture
def rig():
    clock = Clock()
    double = StripeSemanticsDouble(clock)
    connect_secret, platform_secret = stripe_events.webhook_secret(), stripe_events.webhook_secret()
    acct = double.add_account()
    cfg = StripeTestConfig(SK_TEST, webhook_secrets=(platform_secret,), connect_webhook_secrets=(connect_secret,))
    p = StripeTestPaymentProcessor(cfg, wire=double, environment="development", clock=clock, log=lambda r: None,
                                   connected=ConnectedMerchant(PAYEE, acct, application_fee_bps=1000))
    return clock, double, p, acct, connect_secret, platform_secret


def _auth(amount=9612, key=BASE, purpose=PURPOSE, payee=PAYEE):
    return PaymentAuthorization(payment_key(key, "authorize"), USD(amount), payee, purpose, "pm_card_visa",
                                {"brandme_provider": "demo_atelier"}, "development")


# -- configuration and fee math ------------------------------------------------------------------

def test_fee_is_platform_fee_only_rounded_down_and_bounded():
    m = ConnectedMerchant(PAYEE, "acct_123", application_fee_bps=1000)
    assert m.application_fee(9612) == 961 and m.application_fee(9) == 0 and m.application_fee(0) == 0
    assert ConnectedMerchant(PAYEE, "acct_123", application_fee_bps=500).application_fee(10_000) == 500
    for bps in (0, 3001, True, 10.0):
        with pytest.raises(ValueError):
            ConnectedMerchant(PAYEE, "acct_123", application_fee_bps=bps)
    for acct in ("acct_", "cus_123", "", None):
        with pytest.raises(ValueError):
            ConnectedMerchant(PAYEE, acct)
    assert "acct_123" not in repr(m)  # the routing id is not shown anywhere a repr lands


def test_descriptor_names_the_brand_as_payee_and_the_connect_webhooks(rig):
    _, _, p, _, _, _ = rig
    assert p.descriptor.payee_ref == PAYEE and p.descriptor.webhooks_configured
    assert "acct_" not in json.dumps(p.descriptor.to_operator())


# -- onboarding: Accounts v2 -----------------------------------------------------------------------

def test_brand_account_is_v2_full_dashboard_stripe_fees_and_losses_merchant_config():
    double = StripeSemanticsDouble(Clock())
    accounts = StripeConnectAccounts(double, environment="development")
    r = accounts.create_brand_account(payee_ref=PAYEE, display_name="Fixture Atelier", country="US", currency="USD",
                                      idempotency_key=ACCOUNT_KEY)
    (method, params, key), = [c for c in double.calls if c[0] == "create_account"]
    assert key == ACCOUNT_KEY and "type" not in params  # no legacy account type
    assert params["dashboard"] == "full"
    assert params["defaults"]["responsibilities"] == {"fees_collector": "stripe", "losses_collector": "stripe"}
    assert params["configuration"] == {"merchant": {"capabilities": {"card_payments": {"requested": True}}}}
    assert "recipient" not in params["configuration"]  # brands are merchants of record, not recipients
    assert params["identity"] == {"country": "us", "entity_type": "company"} and params["defaults"]["currency"] == "usd"
    assert params["metadata"] == {"brandme_payee_ref": PAYEE, "brandme_env": "development"}
    assert (r.card_payments, r.configured_as_planned, r.ready) == ("pending", True, False)
    assert r.requirements_due == 2
    # A retry under the same key returns the same account, never a second one.
    again = accounts.create_brand_account(payee_ref=PAYEE, display_name="Fixture Atelier", country="US",
                                          currency="USD", idempotency_key=ACCOUNT_KEY)
    assert again.account_id == r.account_id and len(double.accounts) == 1


@pytest.mark.parametrize("kw", [{"idempotency_key": "short:connect_account"}, {"country": "USA"},
                                {"currency": "US"}, {"payee_ref": "has space"}, {"display_name": " "},
                                {"contact_email": "not-an-email"}])
def test_brand_account_refuses_bad_input_before_any_call(kw):
    double = StripeSemanticsDouble(Clock())
    args = dict(payee_ref=PAYEE, display_name="Fixture Atelier", country="US", currency="USD",
                idempotency_key=ACCOUNT_KEY)
    args.update(kw)
    with pytest.raises(ProviderError) as e:
        StripeConnectAccounts(double, environment="development").create_brand_account(**args)
    assert e.value.kind is ProviderErrorKind.CONTRACT_RESTRICTED and double.calls == []


def test_lost_account_create_is_outcome_unknown_and_the_same_key_recovers_it():
    double = StripeSemanticsDouble(Clock())
    accounts = StripeConnectAccounts(double, environment="development")
    args = dict(payee_ref=PAYEE, display_name="Fixture Atelier", country="US", currency="USD",
                idempotency_key=ACCOUNT_KEY)
    double.lose_next("create_account")
    with pytest.raises(ProviderError) as e:
        accounts.create_brand_account(**args)
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN and e.value.transmitted
    r = accounts.create_brand_account(**args)
    assert len(double.accounts) == 1 and r.account_id in double.accounts


def test_readiness_follows_v2_capability_status_never_v1_flags():
    double = StripeSemanticsDouble(Clock())
    accounts = StripeConnectAccounts(double, environment="development")
    r = accounts.create_brand_account(payee_ref=PAYEE, display_name="Fixture Atelier", country="US", currency="USD",
                                      idempotency_key=ACCOUNT_KEY)
    double.set_capability(r.account_id, "active")
    now = accounts.readiness(r.account_id)
    assert now.ready and now.payouts == "active" and now.requirements_due == 0
    assert now.to_operator() == {"card_payments": "active", "payouts": "active", "requirements_due": 0,
                                 "configured_as_planned": True, "ready": True}
    (_, (acct, include), _), = [c for c in double.calls if c[0] == "retrieve_account"]
    assert acct == r.account_id and set(include) == {"configuration.merchant", "defaults", "requirements"}
    double.set_capability(r.account_id, "restricted")
    assert not accounts.readiness(r.account_id).ready


@pytest.mark.parametrize("kw", [{"dashboard": "express"}, {"losses_collector": "application"},
                                {"fees_collector": "application"}])
def test_an_account_configured_otherwise_is_never_ready(kw):
    double = StripeSemanticsDouble(Clock())
    acct = double.add_account(**kw)
    r = StripeConnectAccounts(double, environment="development").readiness(acct)
    assert r.card_payments == "active" and not r.configured_as_planned and not r.ready


def test_a_live_mode_account_is_refused():
    double = StripeSemanticsDouble(Clock())
    acct = double.add_account(livemode=True)
    with pytest.raises(ProviderError) as e:
        StripeConnectAccounts(double, environment="development").readiness(acct)
    assert e.value.kind is ProviderErrorKind.NOT_CONFIGURED


def test_component_session_enables_the_planned_components_and_never_capture():
    double = StripeSemanticsDouble(Clock())
    acct = double.add_account()
    s = StripeConnectAccounts(double, environment="development").component_session(acct)
    sent = double.sessions[0]["components"]
    assert set(sent) == {"account_onboarding", "notification_banner", "account_management", "payments", "payouts"}
    assert all(c["enabled"] for c in sent.values()) and sent == {k: dict(v) for k, v in EMBEDDED_COMPONENTS.items()}
    assert sent["payments"]["features"]["capture_payments"] is False  # capture stays with the order flow
    assert s.client_secret.startswith("accs_secret__") and s.client_secret not in repr(s)


def test_onboarding_link_only_redirects_to_https_or_loopback():
    double = StripeSemanticsDouble(Clock())
    acct = double.add_account()
    accounts = StripeConnectAccounts(double, environment="development")
    url = accounts.onboarding_link(acct, refresh_url="https://console.brandme.test/connect/refresh",
                                   return_url="http://127.0.0.1:3002/connect/done")
    assert url.startswith("https://") and double.links[0]["use_case"]["type"] == "account_onboarding"
    for bad in ("http://evil.example/x", "javascript:alert(1)", "https://"):
        with pytest.raises(ProviderError) as e:
            accounts.onboarding_link(acct, refresh_url=bad, return_url="https://console.brandme.test/done")
        assert e.value.kind is ProviderErrorKind.CONTRACT_RESTRICTED
    assert len(double.links) == 1


def test_connect_onboarding_refuses_production():
    with pytest.raises(ValueError):
        StripeConnectAccounts(StripeSemanticsDouble(Clock()), environment="production")


# -- direct charges ---------------------------------------------------------------------------------

def test_direct_charge_lifecycle_runs_on_the_connected_account_with_the_platform_fee(rig):
    clock, double, p, acct, _, _ = rig
    a = p.authorize(_auth())
    assert a.status == "authorized" and a.payee_ref == PAYEE
    (_, params, _), = [c for c in double.calls if c[0] == "create_payment_intent"]
    assert params["application_fee_amount"] == 961 and "transfer_data" not in params and "on_behalf_of" not in params
    # Partial capture: the fee follows the amount taken.
    c = p.capture(a.payment_ref, USD(5000), idempotency_key=payment_key(BASE, "capture"))
    assert c.status == "captured" and double.intents[a.payment_ref]["application_fee_amount"] == 500
    r = p.refund(a.payment_ref, USD(1000), idempotency_key=payment_key(BASE, "refund", 1))
    assert r.status == "partially_refunded"
    (_, rparams, _), = [c for c in double.calls if c[0] == "create_refund"]
    assert rparams["refund_application_fee"] is True
    assert p.find(PURPOSE, settled=True).payment_ref == a.payment_ref
    assert p.operation_effect(a.payment_ref, payment_key(BASE, "refund", 1)) == "applied"
    # Every PaymentIntent and refund call went to the brand's account; only account reads went to the platform.
    for (method, _, _), on in zip(double.calls, double.call_accounts):
        assert on == (None if method == "retrieve_account" else acct), method
    # And the charge does not exist on the platform account.
    with pytest.raises(ProviderError):
        StripeTestPaymentProcessor(StripeTestConfig(SK_TEST), wire=double, environment="development",
                                   clock=clock, log=lambda r: None).lookup(a.payment_ref)


def test_a_lost_authorization_on_the_connected_account_is_found_by_reads(rig):
    clock, double, p, acct, _, _ = rig
    double.lose_next("create_payment_intent")
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth())
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN
    clock.now += timedelta(minutes=5)
    found = p.find(PURPOSE, settled=True)
    assert found is not None and found.status == "authorized"
    assert [c[0] for c in double.mutating_calls()].count("create_payment_intent") == 1  # never re-sent


@pytest.mark.parametrize("status", ["pending", "restricted", "rejected"])
def test_nothing_is_sent_to_an_account_that_cannot_take_the_charge(rig, status):
    _, double, p, acct, _, _ = rig
    double.set_capability(acct, status)
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth())
    assert (e.value.kind, e.value.detail, e.value.transmitted) == (
        ProviderErrorKind.NOT_CONFIGURED, "connected_account_not_ready", False)
    assert double.mutating_calls() == []


def test_nothing_is_sent_to_a_misconfigured_account():
    clock = Clock()
    double = StripeSemanticsDouble(clock)
    acct = double.add_account(losses_collector="application")  # would leave Brand.Me liable for negative balances
    p = StripeTestPaymentProcessor(StripeTestConfig(SK_TEST), wire=double, environment="development", clock=clock,
                                   log=lambda r: None, connected=ConnectedMerchant(PAYEE, acct))
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth())
    assert e.value.detail == "connected_account_misconfigured" and double.mutating_calls() == []


def test_an_unreadable_account_is_transient_and_sends_nothing(rig):
    _, double, p, _, _, _ = rig
    double.lose_next("retrieve_account", before=True)
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth())
    assert e.value.kind is ProviderErrorKind.TRANSIENT and not e.value.transmitted
    assert double.mutating_calls() == []


def test_the_payee_is_still_bound(rig):
    _, double, p, _, _, _ = rig
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth(payee="someone-else"))
    assert e.value.detail == "payee_mismatch" and double.calls == []


def test_platform_processor_sends_no_connect_fields():
    clock = Clock()
    double = StripeSemanticsDouble(clock)
    p = StripeTestPaymentProcessor(StripeTestConfig(SK_TEST), wire=double, environment="development", clock=clock,
                                   log=lambda r: None)
    a = p.authorize(_auth())
    p.capture(a.payment_ref, USD(9612), idempotency_key=payment_key(BASE, "capture"))
    p.refund(a.payment_ref, USD(100), idempotency_key=payment_key(BASE, "refund", 1))
    for method, params, _ in double.mutating_calls():
        body = params[1] if isinstance(params, tuple) else params
        assert "application_fee_amount" not in body and "refund_application_fee" not in body, method
    assert set(double.call_accounts) == {None}


# -- webhooks ---------------------------------------------------------------------------------------

def _pi_event(double, a, secret, at, **kw):
    return stripe_events.payment_intent_event(double.intents[a.payment_ref], "payment_intent.succeeded", secret, at,
                                              **kw)


def test_connect_webhooks_count_only_for_this_connected_account(rig):
    clock, double, p, acct, connect_secret, platform_secret = rig
    a = p.authorize(_auth())
    at = int(clock.now.timestamp())
    ev = p.verify_webhook(*_pi_event(double, a, connect_secret, at, account=acct))
    assert ev.payment_ref == a.payment_ref and ev.purpose_ref == PURPOSE
    other = p.verify_webhook(*_pi_event(double, a, connect_secret, at, account="acct_someoneelse"))
    assert other.payment_ref is None  # acknowledged, ignored
    platform = p.verify_webhook(*_pi_event(double, a, connect_secret, at))
    assert platform.payment_ref is None  # a platform event never moves a brand's payment
    with pytest.raises(ProviderError) as e:  # the platform endpoint's secret does not sign Connect events
        p.verify_webhook(*_pi_event(double, a, platform_secret, at, account=acct))
    assert e.value.kind is ProviderErrorKind.UNAUTHORIZED


def test_platform_processor_ignores_connect_events():
    clock = Clock()
    double = StripeSemanticsDouble(clock)
    secret = stripe_events.webhook_secret()
    p = StripeTestPaymentProcessor(StripeTestConfig(SK_TEST, webhook_secrets=(secret,)), wire=double,
                                   environment="development", clock=clock, log=lambda r: None)
    a = p.authorize(_auth())
    at = int(clock.now.timestamp())
    assert p.verify_webhook(*_pi_event(double, a, secret, at)).payment_ref == a.payment_ref
    assert p.verify_webhook(*_pi_event(double, a, secret, at, account="acct_123")).payment_ref is None


def test_connected_processor_without_connect_secrets_refuses_webhooks():
    clock = Clock()
    double = StripeSemanticsDouble(clock)
    secret = stripe_events.webhook_secret()
    p = StripeTestPaymentProcessor(StripeTestConfig(SK_TEST, webhook_secrets=(secret,)), wire=double,
                                   environment="development", clock=clock, log=lambda r: None,
                                   connected=ConnectedMerchant(PAYEE, double.add_account()))
    assert not p.descriptor.webhooks_configured
    with pytest.raises(ProviderError) as e:
        p.verify_webhook({"stripe-signature": "t=1,v1=00"}, b"{}")
    assert e.value.kind is ProviderErrorKind.NOT_CONFIGURED


# -- composition ------------------------------------------------------------------------------------

def _env(**kw):
    env = {"BRANDME_COMMERCE_PAYMENTS": "stripe_test", "STRIPE_TEST_SECRET_KEY": SK_TEST}
    env.update(kw)
    return env


def test_composition_builds_a_direct_charge_rail_from_config():
    from brandme_core.domains.commerce.composition import build_providers
    clock = Clock()
    double = StripeSemanticsDouble(clock)
    acct = double.add_account()
    secret = stripe_events.webhook_secret()
    providers = build_providers("development", env=_env(
        BRANDME_STRIPE_CONNECT_ACCOUNT=acct, BRANDME_STRIPE_CONNECT_FEE_BPS="750",
        STRIPE_TEST_CONNECT_WEBHOOK_SECRET=secret), clock=clock, stripe_wire_factory=double)
    c = providers.payments.connected
    assert (c.account_id, c.application_fee_bps, c.payee_ref) == (acct, 750, providers.demo_atelier.payee_ref)
    assert providers.payments.descriptor.webhooks_configured
    unset = build_providers("development", env=_env(), clock=clock, stripe_wire_factory=double)
    assert unset.payments.connected is None  # unset keeps the platform account standing in, as before


_ACCT, _FEE = "BRANDME_STRIPE_CONNECT_ACCOUNT", "BRANDME_STRIPE_CONNECT_FEE_BPS"


@pytest.mark.parametrize("extra", [{_FEE: "1000"},  # a fee without an account
                                   {_ACCT: "acct_123", _FEE: "10%"}, {_ACCT: "acct_123", _FEE: "0"},
                                   {_ACCT: "cus_123"}])
def test_composition_refuses_connect_misconfiguration(extra):
    from brandme_core.domains.commerce.composition import CompositionError, build_providers
    with pytest.raises(CompositionError) as e:
        build_providers("development", env=_env(**extra), stripe_wire_factory=StripeSemanticsDouble(Clock()))
    assert e.value.code == "stripe_connect_config_refused"


# -- SDK wire: headers and paths against a recording loopback server (not Stripe) -------------------

def _recording_stripe(responses):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def _answer(self):
            raw = self.rfile.read(int(self.headers.get("content-length") or 0))
            seen.append((self.command, self.path.split("?")[0], {k.lower(): v for k, v in self.headers.items()},
                         raw.decode()))
            body = json.dumps(responses(self.path)).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _answer

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


def _canned(path):
    if path.startswith("/v2/core/accounts"):
        return {"id": "acct_123", "object": "v2.core.account", "livemode": False, "dashboard": "full"}
    if path.startswith("/v1/account_sessions"):
        return {"object": "account_session", "account": "acct_123", "client_secret": "accs_secret__x",
                "expires_at": 1, "livemode": False, "components": {}}
    return {"id": "pi_123", "object": "payment_intent", "livemode": False, "amount": 100, "currency": "usd",
            "status": "requires_capture", "metadata": {}}


def test_sdk_wire_sends_stripe_account_header_only_for_connected_calls():
    pytest.importorskip("stripe")
    from brandme_core.domains.providers.payments.stripe_wire import SdkStripeWire
    server, seen = _recording_stripe(_canned)
    try:
        wire = SdkStripeWire(StripeTestConfig(SK_TEST), api_base=f"http://127.0.0.1:{server.server_port}")
        wire.create_payment_intent({"amount": 100, "currency": "usd", "application_fee_amount": 10},
                                   idempotency_key=BASE + ":authorize", stripe_account="acct_123")
        wire.retrieve_payment_intent("pi_123", stripe_account="acct_123")
        wire.retrieve_payment_intent("pi_123")
    finally:
        server.shutdown()
        server.server_close()
    (m1, p1, h1, b1), (m2, p2, h2, _), (m3, p3, h3, _) = seen
    assert (m1, p1, h1.get("stripe-account"), h1.get("idempotency-key")) == (
        "POST", "/v1/payment_intents", "acct_123", BASE + ":authorize")
    assert "application_fee_amount=10" in b1
    assert (m2, h2.get("stripe-account")) == ("GET", "acct_123")
    assert "stripe-account" not in h3  # a platform call carries no Stripe-Account header


def test_sdk_wire_uses_accounts_v2_and_account_sessions():
    pytest.importorskip("stripe")
    from brandme_core.domains.providers.payments.stripe_wire import SdkStripeWire
    server, seen = _recording_stripe(_canned)
    try:
        wire = SdkStripeWire(StripeTestConfig(SK_TEST), api_base=f"http://127.0.0.1:{server.server_port}")
        wire.create_account({"dashboard": "full", "include": ["defaults"]}, idempotency_key=ACCOUNT_KEY)
        wire.retrieve_account("acct_123", include=["configuration.merchant", "defaults"])
        wire.create_account_session({"account": "acct_123", "components": {"notification_banner": {"enabled": True}}})
    finally:
        server.shutdown()
        server.server_close()
    (m1, p1, h1, b1), (m2, p2, _, _), (m3, p3, _, _) = seen
    assert (m1, p1, h1.get("idempotency-key")) == ("POST", "/v2/core/accounts", ACCOUNT_KEY)
    assert h1.get("content-type", "").startswith("application/json") and json.loads(b1)["dashboard"] == "full"
    assert h1.get("stripe-version") == "2026-09-30.endive"
    assert (m2, p2) == ("GET", "/v2/core/accounts/acct_123")
    assert (m3, p3) == ("POST", "/v1/account_sessions")
