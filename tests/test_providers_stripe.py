"""FIXTURE DOUBLE — NOT STRIPE: proves adapter logic, not Stripe behaviour.

The real ``StripeTestPaymentProcessor`` runs over ``StripeSemanticsDouble``
(``tests/fixtures/providers/stripe_double.py``), an in-memory wire that follows
the Stripe test-mode semantics the adapter depends on. No network, no key.
Evidence label for everything here: "fixture double, not Stripe".
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from brandme_core.domains.commerce.money import Money
from brandme_core.domains.providers.contracts import ProviderError, ProviderErrorKind
from brandme_core.domains.providers.payments import PaymentAuthorization, payment_key
from brandme_core.domains.providers.payments.stripe_test import (
    HANDLED_EVENT_TYPES, StripeTestConfig, StripeTestPaymentProcessor,
)
from brandme_core.domains.providers.payments.stripe_wire import WireError
from brandme_core.domains.providers.redaction import (
    LOG_OPS, LOG_OUTCOMES, ProcessorLogFilter, install_processor_log_redaction, payment_log_record,
    redact_processor_text,
)
from tests.fixtures.providers import stripe_events
from tests.fixtures.providers.stripe_double import StripeSemanticsDouble

USD = lambda n: Money(n, "USD")  # noqa: E731
SK_TEST = "sk_" + "test_" + "0" * 24
BASE = "bm-" + "0123456789abcdef" * 2
PURPOSE = "demo-order-0123456789abcdef01234567"
LABEL = "fixture double, not Stripe"


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture
def rig():
    clock = Clock()
    double = StripeSemanticsDouble(clock)
    logs = []
    secret = stripe_events.webhook_secret()
    previous = stripe_events.webhook_secret()
    p = StripeTestPaymentProcessor(StripeTestConfig(SK_TEST, webhook_secrets=(secret, previous)), wire=double,
                                   environment="development", clock=clock, log=logs.append)
    p.test_secret, p.test_previous = secret, previous
    return clock, double, p, logs


def _auth(key=BASE, amount=9612, token="pm_card_visa", purpose=PURPOSE, **kw):
    md = kw.pop("metadata", {"brandme_provider": "demo_atelier", "brandme_merchant": "fictional-demo-merchant",
                             "brandme_quote_hash": "sha256:" + "a" * 64, "brandme_simulated_merchant": "true"})
    return PaymentAuthorization(payment_key(key, "authorize"), USD(amount), "demo-atelier-stripe-test", purpose, token,
                                md, **kw)


def test_create_params_exact_shape(rig):
    _, double, p, _ = rig
    a = p.authorize(_auth())
    assert a.status == "authorized" and a.payment_ref.startswith("pi_")
    (method, params, key), = double.mutating_calls()
    assert method == "create_payment_intent" and key == BASE + ":authorize"
    assert params == {
        "amount": 9612, "currency": "usd", "capture_method": "manual", "confirm": True,
        "payment_method": "pm_card_visa", "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
        "description": f"Brand.Me TEST MODE - Demo Atelier (fictional) - {PURPOSE}",
        "metadata": {"brandme_env": "development", "brandme_provider": "demo_atelier",
                     "brandme_merchant": "fictional-demo-merchant", "brandme_purpose_ref": PURPOSE,
                     "brandme_idem": BASE + ":authorize", "brandme_payee_ref": "demo-atelier-stripe-test",
                     "brandme_quote_hash": "sha256:" + "a" * 64, "brandme_simulated_merchant": "true"},
        "expand": ["latest_charge"]}
    for absent in ("payment_method_types", "customer", "receipt_email", "shipping"):
        assert absent not in params
    assert "TEST MODE" in params["description"]


@pytest.mark.parametrize("bad", [
    dict(token="4242424242424242"),
    dict(metadata={"note": "x"}),
    dict(metadata={"brandme_provider": "has spaces in it"}),
    dict(metadata={"brandme_provider": "quote'd"}),
    dict(capture="automatic"),
    dict(amount=10),
    dict(environment="demo"),
])
def test_card_number_cannot_reach_any_param(rig, bad):
    _, double, p, _ = rig
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth(**bad))
    assert e.value.kind in (ProviderErrorKind.CONTRACT_RESTRICTED, ProviderErrorKind.UNSUPPORTED)
    assert not e.value.transmitted and double.calls == []  # refused before any wire call


def test_payee_other_than_the_configured_test_account_is_refused(rig):
    _, double, p, _ = rig
    r = _auth()
    with pytest.raises(ProviderError) as e:
        p.authorize(PaymentAuthorization(r.idempotency_key, r.amount, "demo-payee", r.purpose_ref, "pm_card_visa"))
    assert e.value.detail == "payee_mismatch" and double.calls == []


@pytest.mark.parametrize("kind,expected,transmitted", [
    ("authentication", ProviderErrorKind.UNAUTHORIZED, False),
    ("permission", ProviderErrorKind.UNAUTHORIZED, False),
    ("rate_limit", ProviderErrorKind.THROTTLED, False),
    ("invalid_request", ProviderErrorKind.CONTRACT_RESTRICTED, False),
    ("idempotency", ProviderErrorKind.OUTCOME_UNKNOWN, True),
    ("connection", ProviderErrorKind.OUTCOME_UNKNOWN, True),
    ("api", ProviderErrorKind.OUTCOME_UNKNOWN, True),
    ("unknown", ProviderErrorKind.OUTCOME_UNKNOWN, True),
])
def test_wire_error_mapping_mutating(rig, kind, expected, transmitted):
    _, double, p, _ = rig
    a = p.authorize(_auth())
    for method, call in (("create_payment_intent", lambda: p.authorize(_auth("bm-" + "1" * 32, purpose="demo-o-2"))),
                         ("capture_payment_intent", lambda: p.capture(a.payment_ref, USD(9612),
                                                                      idempotency_key=payment_key(BASE, "capture"))),
                         ("cancel_payment_intent", lambda: p.void(a.payment_ref,
                                                                  idempotency_key=payment_key(BASE, "void")))):
        double.fail_next(method, WireError(kind))
        with pytest.raises(ProviderError) as e:
            call()
        assert (e.value.kind, e.value.transmitted) == (expected, transmitted), method
        assert "Stripe" not in e.value.detail or e.value.detail.startswith("Stripe")


def test_card_error_on_capture_is_restricted_and_decline_without_intent_is_a_result(rig):
    _, double, p, _ = rig
    a = p.authorize(_auth())
    double.fail_next("capture_payment_intent", WireError("card_error", code="card_declined"))
    with pytest.raises(ProviderError) as e:
        p.capture(a.payment_ref, USD(9612), idempotency_key=payment_key(BASE, "capture"))
    assert e.value.kind is ProviderErrorKind.CONTRACT_RESTRICTED and not e.value.transmitted
    double.fail_next("create_payment_intent", WireError("card_error", code="card_declined",
                                                        decline_code="insufficient_funds"))
    d = p.authorize(_auth("bm-" + "2" * 32, purpose="demo-order-decline-0001"))
    assert (d.payment_ref, d.status, d.decline_code) == ("", "failed", "insufficient_funds")


@pytest.mark.parametrize("kind,expected", [
    ("authentication", ProviderErrorKind.UNAUTHORIZED), ("rate_limit", ProviderErrorKind.THROTTLED),
    ("invalid_request", ProviderErrorKind.MALFORMED_RESPONSE), ("connection", ProviderErrorKind.TRANSIENT),
    ("api", ProviderErrorKind.TRANSIENT), ("unknown", ProviderErrorKind.TRANSIENT),
])
def test_wire_error_mapping_reads(rig, kind, expected):
    _, double, p, _ = rig
    a = p.authorize(_auth())
    double.fail_next("retrieve_payment_intent", WireError(kind))
    with pytest.raises(ProviderError) as e:
        p.lookup(a.payment_ref)
    assert e.value.kind is expected and not e.value.transmitted
    assert e.value.kind is not ProviderErrorKind.OUTCOME_UNKNOWN
    double.fail_next("search_payment_intents", WireError(kind))
    with pytest.raises(ProviderError) as e:
        p.find("demo-order-not-journaled", settled=True)
    assert e.value.kind is expected and not e.value.transmitted


def test_failure_after_send_is_outcome_unknown(rig):
    _, double, p, _ = rig
    a = p.authorize(_auth())
    p.capture(a.payment_ref, USD(9612), idempotency_key=payment_key(BASE, "capture"))
    double.fail_next("retrieve_payment_intent", WireError("connection"))  # the refund applied, the read fails
    with pytest.raises(ProviderError) as e:
        p.refund(a.payment_ref, USD(1000), idempotency_key=payment_key(BASE, "refund", 1))
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN and e.value.transmitted
    assert p.operation_effect(a.payment_ref, payment_key(BASE, "refund", 1)) == "applied"
    assert p.lookup(a.payment_ref).refunded == USD(1000)


def test_livemode_response_latches_processor(rig):
    _, double, p, _ = rig
    double.arm_livemode()
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth())
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN and e.value.transmitted
    before = len(double.calls)
    for call in (lambda: p.authorize(_auth("bm-" + "3" * 32, purpose="demo-o-3")), lambda: p.lookup("pi_123"),
                 lambda: p.find(PURPOSE, settled=True)):
        with pytest.raises(ProviderError) as e:
            call()
        assert e.value.kind is ProviderErrorKind.NOT_CONFIGURED
    assert len(double.calls) == before  # latched: nothing more is sent


def test_client_secret_never_leaves_observe(rig):
    clock, double, p, logs = rig
    a = p.authorize(_auth())
    assert any("_secret_" in pi["client_secret"] for pi in double.intents.values())
    states = [a, p.lookup(a.payment_ref), p.capture(a.payment_ref, USD(9612), idempotency_key=payment_key(BASE, "capture")),
              p.find(PURPOSE, settled=True)]
    headers, body = stripe_events.signed(stripe_events.event(
        "payment_intent.succeeded", double.intents[a.payment_ref], created=int(clock().timestamp())),
        p.test_secret, int(clock().timestamp()))
    ev = p.verify_webhook(headers, body)
    blob = repr(states) + repr(ev) + json.dumps(logs)
    assert "_secret_" not in blob and "4242" not in blob
    assert all(s.evidence_ref == f"stripe_test:payment_for:{PURPOSE}" for s in states)


@pytest.mark.parametrize("pi,refunds,status,extra", [
    ({"status": "requires_capture"}, [], "authorized", {}),
    ({"status": "succeeded", "amount_received": 9612}, [], "captured", {}),
    ({"status": "succeeded", "amount_received": 8000}, [], "captured",
     {"released": USD(1612), "release_reason": "partial_capture_remainder"}),
    ({"status": "succeeded", "amount_received": 9612}, [{"amount": 1000, "status": "succeeded"}],
     "partially_refunded", {"refunded": USD(1000)}),
    ({"status": "succeeded", "amount_received": 9612}, [{"amount": 9612, "status": "succeeded"}], "refunded", {}),
    ({"status": "canceled", "cancellation_reason": "automatic", "charge": {"status": "succeeded", "captured": False}},
     [], "voided", {"release_reason": "authorization_expired", "released": USD(9612)}),
    ({"status": "canceled", "cancellation_reason": "requested_by_customer",
      "charge": {"status": "succeeded", "captured": False}}, [], "voided", {"release_reason": "merchant_void"}),
    ({"status": "canceled", "cancellation_reason": "abandoned"}, [], "failed", {}),
    ({"status": "requires_payment_method", "last_payment_error": {"code": "card_declined",
                                                                  "decline_code": "expired_card"}},
     [], "failed", {"decline_code": "expired_card"}),
    ({"status": "requires_payment_method", "last_payment_error": {"code": "weird"}}, [], "failed",
     {"decline_code": "other"}),
    ({"status": "requires_payment_method"}, [], "unknown", {}),
    ({"status": "requires_confirmation"}, [], "unknown", {}),
    ({"status": "processing"}, [], "unknown", {}),
    ({"status": "requires_action"}, [], "requires_action", {}),
])
def test_observe_status_table(rig, pi, refunds, status, extra):
    _, _, p, _ = rig
    charge = pi.pop("charge", None)
    obj = {"id": "pi_abc123", "object": "payment_intent", "amount": 9612, "currency": "usd", "livemode": False,
           "metadata": {"brandme_purpose_ref": PURPOSE}, "latest_charge": charge, **pi}
    refunds = [dict(r, payment_intent="pi_abc123") for r in refunds]
    s = p._observe(obj, refunds)
    assert s.status == status
    for k, v in extra.items():
        assert getattr(s, k) == v, k


def test_refunds_count_only_succeeded(rig):
    _, double, p, _ = rig
    a = p.authorize(_auth())
    p.capture(a.payment_ref, USD(9612), idempotency_key=payment_key(BASE, "capture"))
    double.refund_status = "pending"
    pending = p.refund(a.payment_ref, USD(500), idempotency_key=payment_key(BASE, "refund", 1))
    assert pending.refunded == USD(0) and pending.status == "captured"
    assert double.intents[a.payment_ref]["latest_charge"]["amount_refunded"] == 500  # Stripe's own figure includes it
    double.refund_status = "failed"
    p.refund(a.payment_ref, USD(400), idempotency_key=payment_key(BASE, "refund", 2))
    double.refund_status = "succeeded"
    done = p.refund(a.payment_ref, USD(300), idempotency_key=payment_key(BASE, "refund", 3))
    assert done.refunded == USD(300) and done.status == "partially_refunded"


def test_capture_before_read_and_expired_capture_reads_back_voided(rig):
    clock, double, p, _ = rig
    a = p.authorize(_auth())
    assert a.capture_before == clock.now + timedelta(days=7)
    clock.advance(days=7, seconds=1)
    s = p.capture(a.payment_ref, USD(9612), idempotency_key=payment_key(BASE, "capture"))
    assert (s.status, s.release_reason, s.captured) == ("voided", "authorization_expired", USD(0))


def test_find_journal_then_search_then_list(rig):
    clock, double, p, _ = rig
    a = p.authorize(_auth())
    assert p.find(PURPOSE, settled=False).payment_ref == a.payment_ref  # this process's journal
    fresh = StripeTestPaymentProcessor(StripeTestConfig(SK_TEST), wire=double, environment="development", clock=clock)
    assert fresh.find(PURPOSE, settled=False).payment_ref == a.payment_ref  # search lags; the list scan finds it
    kinds = [c[0] for c in double.calls[-4:]]
    assert "search_payment_intents" in kinds and "list_payment_intents" in kinds
    clock.advance(minutes=2)
    n = len(double.calls)
    assert fresh.find(PURPOSE, settled=True).payment_ref == a.payment_ref
    assert "list_payment_intents" not in [c[0] for c in double.calls[n:]]  # search caught up


def test_search_lag_beyond_the_settle_window_is_covered_by_the_list_scan(rig):
    clock, double, p, _ = rig
    double.search_lag = timedelta(minutes=30)
    a = p.authorize(_auth())
    clock.advance(minutes=5)
    fresh = StripeTestPaymentProcessor(StripeTestConfig(SK_TEST), wire=double, environment="development", clock=clock)
    assert fresh.find(PURPOSE, settled=True).payment_ref == a.payment_ref


def test_find_scan_cap_raises_incomplete(rig):
    clock, double, p, _ = rig
    double.page_size = 2
    for i in range(12):
        p.authorize(_auth("bm-" + f"{i:032d}", purpose=f"demo-order-other-{i:04d}"))
    fresh = StripeTestPaymentProcessor(StripeTestConfig(SK_TEST, max_list_pages=3), wire=double,
                                       environment="development", clock=clock)
    with pytest.raises(ProviderError) as e:
        fresh.find(PURPOSE, settled=True)
    assert e.value.kind is ProviderErrorKind.TRANSIENT and e.value.detail == "payment_lookup_incomplete"


def test_find_unsettled_vs_settled(rig):
    _, _, p, _ = rig
    with pytest.raises(ProviderError) as e:
        p.find("demo-order-never-made", settled=False)
    assert e.value.detail == "payment_lookup_unsettled" and e.value.kind is ProviderErrorKind.TRANSIENT
    assert p.find("demo-order-never-made", settled=True) is None


def test_find_ignores_other_environments_and_refuses_duplicates(rig):
    clock, double, p, _ = rig
    other = StripeTestPaymentProcessor(StripeTestConfig(SK_TEST), wire=double, environment="demo", clock=clock)
    other.authorize(_auth("bm-" + "8" * 32, environment="demo"))  # same purpose, another environment, same account
    clock.advance(minutes=5)
    assert p.find(PURPOSE, settled=True) is None
    p.authorize(_auth())
    p.authorize(_auth("bm-" + "9" * 32))  # a second payment for one purpose: never expected
    clock.advance(minutes=5)
    fresh = StripeTestPaymentProcessor(StripeTestConfig(SK_TEST), wire=double, environment="development", clock=clock)
    with pytest.raises(ProviderError) as e:
        fresh.find(PURPOSE, settled=True)
    assert e.value.kind is ProviderErrorKind.MALFORMED_RESPONSE


def test_search_query_refuses_unsafe_purpose(rig):
    _, double, p, _ = rig
    for bad in ("demo-order-'x", "a b", ""):
        with pytest.raises(ProviderError) as e:
            p.find(bad, settled=True)
        assert e.value.kind is ProviderErrorKind.CONTRACT_RESTRICTED
    assert double.calls == []


def test_operation_effect_matches_refund_by_idempotency_metadata(rig):
    _, double, p, _ = rig
    a = p.authorize(_auth())
    assert p.operation_effect(a.payment_ref, payment_key(BASE, "capture")) == "absent"
    p.capture(a.payment_ref, USD(9612), idempotency_key=payment_key(BASE, "capture"))
    assert p.operation_effect(a.payment_ref, payment_key(BASE, "capture")) == "applied"
    double.lose_next("create_refund", before=True)
    with pytest.raises(ProviderError):
        p.refund(a.payment_ref, USD(700), idempotency_key=payment_key(BASE, "refund", 1))
    assert p.operation_effect(a.payment_ref, payment_key(BASE, "refund", 1)) == "absent"
    p.refund(a.payment_ref, USD(700), idempotency_key=payment_key(BASE, "refund", 1))
    assert p.operation_effect(a.payment_ref, payment_key(BASE, "refund", 1)) == "applied"
    assert p.operation_effect(a.payment_ref, payment_key(BASE, "refund", 2)) == "absent"
    double.fail_next("retrieve_payment_intent", WireError("api"))
    with pytest.raises(ProviderError) as e:
        p.operation_effect(a.payment_ref, payment_key(BASE, "void"))
    assert e.value.kind is ProviderErrorKind.TRANSIENT


def test_lost_authorize_response_is_found_without_a_second_create(rig):
    clock, double, p, _ = rig
    double.lose_next("create_payment_intent")
    with pytest.raises(ProviderError) as e:
        p.authorize(_auth())
    assert e.value.kind is ProviderErrorKind.OUTCOME_UNKNOWN and e.value.transmitted
    found = p.find(PURPOSE, settled=False)  # not in the journal (no answer came back): the list scan finds it
    assert found.status == "authorized" and len(double.intents_for(PURPOSE)) == 1
    assert [c[0] for c in double.mutating_calls()] == ["create_payment_intent"]


# ------------------------------------------------------------------------- webhooks
def _evt(p, double, clock, a, *, at=None, secret=None, **kw):
    at = int(clock().timestamp()) if at is None else at
    return stripe_events.signed(stripe_events.event("payment_intent.amount_capturable_updated",
                                                    double.intents[a.payment_ref], created=at, **kw),
                                secret or p.test_secret, at)


def test_stripe_webhook_valid_rotated_tampered_wrong_secret_stale_future_live(rig):
    pytest.importorskip("stripe")
    clock, double, p, _ = rig
    a = p.authorize(_auth())
    now = int(clock().timestamp())
    ev = p.verify_webhook(*_evt(p, double, clock, a))
    assert (ev.payment_ref, ev.purpose_ref, ev.environment, ev.authorize_key) == (
        a.payment_ref, PURPOSE, "development", BASE + ":authorize")
    assert ev.event_type == "payment_intent.amount_capturable_updated" and ev.event_id.startswith("evt_")
    assert p.verify_webhook(*_evt(p, double, clock, a, secret=p.test_previous)).payment_ref == a.payment_ref
    headers, body = _evt(p, double, clock, a)
    bad = [({"Stripe-Signature": headers["Stripe-Signature"]}, body + b" "),
           _evt(p, double, clock, a, secret=stripe_events.webhook_secret()),
           _evt(p, double, clock, a, at=now - 301),
           _evt(p, double, clock, a, at=now + 301),
           ({"Stripe-Signature": "t=abc"}, body)]
    for h, b in bad:
        with pytest.raises(ProviderError) as e:
            p.verify_webhook(h, b)
        assert e.value.kind is ProviderErrorKind.UNAUTHORIZED
    assert p.lookup(a.payment_ref).status == "authorized"  # none of those latched anything
    with pytest.raises(ProviderError) as e:
        p.verify_webhook(*_evt(p, double, clock, a, livemode=True))
    assert e.value.kind is ProviderErrorKind.UNAUTHORIZED
    with pytest.raises(ProviderError) as e:  # a signed live-mode event latches the processor
        p.lookup(a.payment_ref)
    assert e.value.kind is ProviderErrorKind.NOT_CONFIGURED


def test_stripe_webhook_without_secret_not_configured(rig):
    clock, double, _, _ = rig
    p = StripeTestPaymentProcessor(StripeTestConfig(SK_TEST), wire=double, environment="development", clock=clock)
    assert p.verify_webhook({"x-demo-signature": "v1=00"}, b"{}") is None  # not this processor's scheme
    with pytest.raises(ProviderError) as e:
        p.verify_webhook({"stripe-signature": "t=1,v1=00"}, b"{}")
    assert e.value.kind is ProviderErrorKind.NOT_CONFIGURED


def test_unhandled_event_type_has_no_payment_ref(rig):
    pytest.importorskip("stripe")
    clock, double, p, _ = rig
    at = int(clock().timestamp())
    ev = p.verify_webhook(*stripe_events.signed(stripe_events.event(
        "customer.created", {"id": "cus_123456789", "object": "customer"}, created=at), p.test_secret, at))
    assert ev.payment_ref is None and ev.purpose_ref is None and ev.event_type == "customer.created"
    assert "customer.created" not in HANDLED_EVENT_TYPES


def test_refund_event_resolves_its_payment_through_metadata_or_a_read(rig):
    pytest.importorskip("stripe")
    clock, double, p, _ = rig
    a = p.authorize(_auth())
    p.capture(a.payment_ref, USD(9612), idempotency_key=payment_key(BASE, "capture"))
    p.refund(a.payment_ref, USD(100), idempotency_key=payment_key(BASE, "refund", 1))
    refund = next(iter(double.refunds.values()))
    at = int(clock().timestamp())
    ev = p.verify_webhook(*stripe_events.signed(stripe_events.event("refund.updated", refund, created=at),
                                                p.test_secret, at))
    assert (ev.payment_ref, ev.purpose_ref) == (a.payment_ref, PURPOSE)
    charge = dict(double.intents[a.payment_ref]["latest_charge"], metadata={})
    ev = p.verify_webhook(*stripe_events.signed(stripe_events.event("charge.refunded", charge, created=at),
                                                p.test_secret, at))
    assert (ev.payment_ref, ev.purpose_ref) == (a.payment_ref, PURPOSE)  # metadata read from the PaymentIntent


# -------------------------------------------------------------------------- logging
def test_payment_log_records_fixed_vocabulary(rig):
    clock, double, p, logs = rig
    a = p.authorize(_auth())
    p.capture(a.payment_ref, USD(9612), idempotency_key=payment_key(BASE, "capture"))
    p.authorize(_auth("bm-" + "4" * 32, token="pm_card_chargeDeclined", purpose="demo-order-decl-0001"))
    with pytest.raises(ProviderError):
        p.find("demo-order-not-there", settled=False)
    assert logs and {tuple(sorted(r)) for r in logs} == {
        ("component", "duration_ms", "environment", "kind", "op", "outcome", "processor", "ts")}
    assert {r["op"] for r in logs} <= set(LOG_OPS) and {r["outcome"] for r in logs} <= set(LOG_OUTCOMES)
    assert {"declined", "unsettled", "ok"} <= {r["outcome"] for r in logs}
    blob = json.dumps(logs)
    for leak in ("pi_", "pm_", "sk_", "whsec_", "9612", "4242", PURPOSE, BASE):
        assert leak not in blob, leak
    with pytest.raises(ValueError):
        payment_log_record("stripe_test", "authorize", "free text", None, 1, "development")


def test_processor_log_filter_redacts_keys_secrets_ids_pans(caplog):
    install_processor_log_redaction()
    install_processor_log_redaction()  # idempotent
    for name in ("stripe", "httpx", "httpcore"):
        assert sum(isinstance(f, ProcessorLogFilter) for f in logging.getLogger(name).filters) == 1
    planted = ("auth %s secret %s client %s pi %s card %s", SK_TEST, "whsec_" + "b" * 24,
               "pi_3Abc12345_secret_zzzz", "pi_3Abc1234567", "4242 4242 4242 4242")
    with caplog.at_level(logging.WARNING):
        logging.getLogger("stripe").warning(*planted)
        logging.getLogger("httpx").warning(*planted)
    text = caplog.text
    assert caplog.records and len(caplog.records) == 2
    for leak in (SK_TEST, "whsec_bbbb", "_secret_zzzz", "pi_3Abc1234567", "4242 4242"):
        assert leak not in text, leak
    assert "pi_…" in text and "[card number removed]" in text
    assert redact_processor_text("rk_" + "live_" + "x" * 20) == "[processor key removed]"


def test_sdk_wire_pins_version_disables_telemetry_installs_redaction(monkeypatch):
    stripe = pytest.importorskip("stripe")
    from brandme_core.domains.providers.payments.stripe_wire import SdkStripeWire, pinned_http_client_class
    monkeypatch.setattr(stripe, "enable_telemetry", True)
    monkeypatch.setattr(stripe, "log", "debug")
    wire = SdkStripeWire(StripeTestConfig(SK_TEST), api_base="http://127.0.0.1:9")
    assert stripe.enable_telemetry is False and stripe.log is None
    assert logging.getLogger("stripe").level == logging.WARNING
    assert wire._c is not None
    client = pinned_http_client_class()(timeout=5)  # what the wire uses unless a test injects a client
    assert client._client._trust_env is False and client._client.follow_redirects is False
    for bad in ("https://evil.example", "http://10.0.0.1:12111"):
        with pytest.raises(ValueError):
            SdkStripeWire(StripeTestConfig(SK_TEST), api_base=bad)
    monkeypatch.setattr(stripe, "api_version", "2020-01-01")
    with pytest.raises(ValueError, match="stripe_api_version_unverified"):
        SdkStripeWire(StripeTestConfig(SK_TEST))


def test_evidence_label_is_stated():
    assert LABEL == "fixture double, not Stripe" and "NOT STRIPE" in __doc__
