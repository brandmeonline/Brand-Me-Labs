"""Fulfillment behind the merchant adapter: the simulated warehouse, and swapping collaborators.

Deterministic app behaviour (simulation): nothing ships and no money moves. The
swap proofs run the same Demo Atelier merchant on a different fulfillment
provider and on a different payment processor with no other code change.
"""

import random
from datetime import datetime, timezone

import pytest

from brandme_core.domains.providers.contracts import CartLineRequest, ProviderError, ProviderErrorKind
from brandme_core.domains.providers.fulfillment import ExchangeRequest, FulfillmentProvider, FulfillmentRequest
from brandme_core.domains.providers.fulfillment.simulated import SimulatedFulfillment

T0 = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def _open(f, order="demo-order-1", **lines):
    lines = lines or {"demo-overshirt-m": 2, "demo-bag-m": 1}
    return f.open(FulfillmentRequest(f"{order}:fulfil", order,
                                     tuple(CartLineRequest("v", ref, q) for ref, q in lines.items()), "demo-delivery"))


def _by_ref(record):
    return {l.source_variant_ref: (l.ordered, l.shipped, l.delivered, l.returned, l.cancelled) for l in record.lines}


def test_simulated_fulfillment_is_a_fulfillment_provider():
    assert isinstance(SimulatedFulfillment(lambda: T0), FulfillmentProvider)


def test_simulated_fulfillment_invariants():
    """Random ship, cancel, return and exchange sequences never break a counter invariant or shrink a counter."""
    rng = random.Random(20261005)
    for trial in range(60):
        f = SimulatedFulfillment(lambda: T0)
        order = f"demo-order-{trial}"
        _open(f, order, **{"demo-overshirt-m": rng.randint(1, 4), "demo-bag-m": rng.randint(1, 3)})
        previous = _by_ref(f.record(order))
        for step in range(25):
            ref = rng.choice(["demo-overshirt-m", "demo-bag-m", "demo-overshirt-l"])
            action = rng.choice(["ship", "partial", "cancel", "return", "receive", "exchange"])
            try:
                if action == "ship":
                    f.ship(order, None, rng.random() < 0.7)
                elif action == "partial":
                    f.ship(order, {"source_variant_ref": ref, "quantity": rng.randint(0, 2)}, True)
                elif action == "cancel":
                    f.cancel_unshipped(order, ref if rng.random() < 0.5 else None, rng.choice([None, 1]),
                                       idempotency_key=f"{order}:cancel:{step}")
                elif action == "return":
                    f.authorize_return(order, ref, 1, idempotency_key=f"{order}:return:{step}")
                elif action == "receive":
                    f.receive_return(order, ref, 1)
                else:
                    f.request_exchange(ExchangeRequest(f"{order}:exchange:{step}", order, ref, "demo-overshirt-l", 1))
            except ProviderError as e:
                assert e.kind in (ProviderErrorKind.CONTRACT_RESTRICTED, ProviderErrorKind.MALFORMED_RESPONSE)
            rec = f.record(order)
            for l in rec.lines:
                l.check()
                assert l.cancelled + l.shipped <= l.ordered and l.delivered <= l.shipped and l.returned <= l.shipped
            now = _by_ref(rec)
            for k, before in previous.items():
                assert all(a >= b for a, b in zip(now[k], before)), (k, before, now[k])
            previous = now


def test_partial_shipment_per_line_and_quantity():
    f = SimulatedFulfillment(lambda: T0)
    _open(f)
    f.ship("demo-order-1", {"source_variant_ref": "demo-overshirt-m", "quantity": 1}, True)
    assert _by_ref(f.record("demo-order-1")) == {"demo-overshirt-m": (2, 1, 1, 0, 0), "demo-bag-m": (1, 1, 1, 0, 0)}
    f.ship("demo-order-1", None, False)  # the rest ships; delivery comes later
    assert _by_ref(f.record("demo-order-1"))["demo-overshirt-m"] == (2, 2, 1, 0, 0)
    f.ship("demo-order-1", None, True)
    assert _by_ref(f.record("demo-order-1"))["demo-overshirt-m"] == (2, 2, 2, 0, 0)
    assert f.record("demo-order-1").owed_units() == 3 and f.record("demo-order-1").shipped_any
    with pytest.raises(ProviderError) as e:
        f.record("demo-order-unknown")
    assert e.value.kind is ProviderErrorKind.MALFORMED_RESPONSE


def test_open_is_idempotent_on_its_key():
    f = SimulatedFulfillment(lambda: T0)
    assert _open(f) == _open(f)
    with pytest.raises(ProviderError):
        f.open(FulfillmentRequest("another-key", "demo-order-1", (CartLineRequest("v", "demo-bag-m", 1),), "d"))


def test_cancel_unshipped_only_and_reports_units():
    f = SimulatedFulfillment(lambda: T0)
    _open(f)
    f.ship("demo-order-1", {"source_variant_ref": "demo-overshirt-m", "quantity": 1}, True)  # the bag ships whole
    assert f.cancel_unshipped("demo-order-1", "demo-bag-m", None, idempotency_key="k0").cancelled == ()
    res = f.cancel_unshipped("demo-order-1", None, None, idempotency_key="k1")
    assert res.cancelled == (("demo-overshirt-m", 1),)
    assert f.cancel_unshipped("demo-order-1", None, None, idempotency_key="k1") == res  # replay
    assert f.cancel_unshipped("demo-order-1", None, None, idempotency_key="k2").cancelled == ()  # nothing left
    assert _by_ref(f.record("demo-order-1")) == {"demo-overshirt-m": (2, 1, 1, 0, 1), "demo-bag-m": (1, 1, 1, 0, 0)}
    f.ship("demo-order-1", None, True)  # cancelled units never ship
    assert _by_ref(f.record("demo-order-1"))["demo-overshirt-m"] == (2, 1, 1, 0, 1)
    assert f.record("demo-order-1").open_units() == 0 and f.record("demo-order-1").owed_units() == 2


def test_exchange_appends_or_grows_line_keeping_history():
    f = SimulatedFulfillment(lambda: T0)
    _open(f, **{"demo-overshirt-m": 1})
    with pytest.raises(ProviderError):  # nothing delivered yet
        f.request_exchange(ExchangeRequest("x1", "demo-order-1", "demo-overshirt-m", "demo-overshirt-l", 1))
    f.ship("demo-order-1", None, True)
    f.request_exchange(ExchangeRequest("x1", "demo-order-1", "demo-overshirt-m", "demo-overshirt-l", 1))
    f.request_exchange(ExchangeRequest("x1", "demo-order-1", "demo-overshirt-m", "demo-overshirt-l", 1))  # replay
    f.ship("demo-order-1", None, True)
    f.request_exchange(ExchangeRequest("x2", "demo-order-1", "demo-overshirt-l", "demo-overshirt-m", 1))
    rec = f.record("demo-order-1")
    assert _by_ref(rec) == {"demo-overshirt-m": (2, 1, 1, 1, 0), "demo-overshirt-l": (1, 1, 1, 1, 0)}
    assert rec.line("demo-overshirt-l").exchanged_from_ref == "demo-overshirt-m"
    assert rec.line("demo-overshirt-m").to_observed().quantity_returned == 1


def test_return_authorization_refused_beyond_owed_and_pending():
    f = SimulatedFulfillment(lambda: T0)
    _open(f, **{"demo-overshirt-m": 2})
    f.ship("demo-order-1", None, True)
    assert f.authorize_return("demo-order-1", "demo-overshirt-m", 2, idempotency_key="r1").status == "requested"
    assert f.authorize_return("demo-order-1", "demo-overshirt-m", 1, idempotency_key="r2").status == "refused"
    assert f.authorize_return("demo-order-1", "demo-unknown-m", 1, idempotency_key="r3").status == "refused"
    assert f.pending_returns("demo-order-1", "demo-overshirt-m") == 2
    with pytest.raises(ProviderError):  # units being returned cannot also be exchanged
        f.request_exchange(ExchangeRequest("x1", "demo-order-1", "demo-overshirt-m", "demo-overshirt-l", 1))
    f.receive_return("demo-order-1", "demo-overshirt-m", 2)
    assert f.pending_returns("demo-order-1", "demo-overshirt-m") == 0
    with pytest.raises(ProviderError):
        f.receive_return("demo-order-1", "demo-overshirt-m", 1)  # more back than went out


# ------------------------------------------------------------------- swap proofs
class Fake3PL:
    """A minimal third-party fulfillment provider: its own records, no shared code with the simulator."""

    fulfillment_id = "fake_3pl"

    def __init__(self, clock):
        self.clock = clock
        self.orders = {}  # order ref -> {variant ref: [ordered, shipped, delivered, returned, cancelled]}
        self.keys = {}

    def _rec(self, ref):
        from brandme_core.domains.providers.fulfillment import FulfillmentLine, FulfillmentRecord
        if ref not in self.orders:
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown order")
        return FulfillmentRecord(self.fulfillment_id, ref, tuple(FulfillmentLine(v, *c) for v, c in self.orders[ref].items()),
                                 self.clock(), f"3pl:{ref}")

    def open(self, request):
        if request.idempotency_key not in self.keys:
            self.keys[request.idempotency_key] = request.order_ref
            self.orders[request.order_ref] = {l.source_variant_ref: [l.quantity, 0, 0, 0, 0] for l in request.lines}
        return self._rec(request.order_ref)

    def record(self, order_ref):
        return self._rec(order_ref)

    def cancel_unshipped(self, order_ref, source_variant_ref, quantity, *, idempotency_key):
        from brandme_core.domains.providers.fulfillment import CancellationResult
        if idempotency_key in self.keys:
            return self.keys[idempotency_key]
        done = []
        for v, c in self.orders[order_ref].items():
            if source_variant_ref in (None, v):
                n = min(c[0] - c[1] - c[4], quantity or 99)
                if n > 0:
                    c[4] += n
                    done.append((v, n))
        self.keys[idempotency_key] = CancellationResult(order_ref, tuple(done), self.clock())
        return self.keys[idempotency_key]

    def authorize_return(self, order_ref, source_variant_ref, quantity, *, idempotency_key):
        from brandme_core.domains.providers.fulfillment import ReturnAuthorization
        c = self.orders[order_ref].get(source_variant_ref)
        ok = c is not None and 1 <= quantity <= c[0] - c[3] - c[4]
        return ReturnAuthorization(f"3pl-rma-{len(self.keys)}", order_ref, source_variant_ref, quantity,
                                   "requested" if ok else "refused", self.clock())

    def request_exchange(self, request):
        raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "this 3PL does not exchange")

    def verify_webhook(self, headers, body):
        return None

    # the merchant back office drives these (a real 3PL reports them itself)
    def ship(self, order_ref, partial=None, deliver=True):
        for c in self.orders[order_ref].values():
            c[1] = c[0] - c[4]
            c[2] = c[1] if deliver else c[2]
        return self._rec(order_ref)

    def receive_return(self, order_ref, source_variant_ref, quantity):
        self.orders[order_ref][source_variant_ref][3] += quantity
        return self._rec(order_ref)


class FakeProcessor:
    """A minimal non-simulator payment processor: authorize, capture, void, refund and reads, in memory."""

    processor_id = "fake_pay"
    simulation = True
    label = "Fake processor for the swap test — no real payment occurs."

    def __init__(self, clock):
        from brandme_core.domains.providers.payments import PaymentRailDescriptor
        self.clock = clock
        self.descriptor = PaymentRailDescriptor("fake_pay", "simulated", "development", self.label, "fake-payee")
        self.test_instruments = ("pm_card_visa", "pm_card_chargeDeclined")
        self.p = {}
        self.ops = set()

    def _state(self, ref):
        from brandme_core.domains.commerce.money import Money
        from brandme_core.domains.providers.payments import PaymentState
        x = self.p[ref]
        cur = x["auth"].currency
        status = x["status"]
        if status == "captured" and x["refunded"]:
            status = "refunded" if x["refunded"] >= x["captured"] else "partially_refunded"
        return PaymentState(ref, status, x["auth"], Money(x["captured"], cur), Money(x["refunded"], cur), self.clock(),
                            evidence_ref=f"fake:payment_for:{x['purpose']}", purpose_ref=x["purpose"],
                            payee_ref="fake-payee", environment="development", authorize_key=x["key"])

    def authorize(self, request):
        ref = "fake_" + request.idempotency_key[-20:]
        if ref not in self.p:
            self.p[ref] = {"auth": request.amount, "captured": 0, "refunded": 0, "purpose": request.purpose_ref,
                           "key": request.idempotency_key,
                           "status": "failed" if request.payment_token_ref.endswith("Declined") else "authorized"}
        return self._state(ref)

    def capture(self, payment_ref, amount, *, idempotency_key):
        if idempotency_key not in self.ops:
            self.ops.add(idempotency_key)
            self.p[payment_ref].update(status="captured", captured=amount.amount_minor)
        return self._state(payment_ref)

    def void(self, payment_ref, *, idempotency_key, reason="merchant_void"):
        self.ops.add(idempotency_key)
        self.p[payment_ref]["status"] = "voided"
        return self._state(payment_ref)

    def refund(self, payment_ref, amount, *, idempotency_key):
        if idempotency_key not in self.ops:
            self.ops.add(idempotency_key)
            self.p[payment_ref]["refunded"] += amount.amount_minor
        return self._state(payment_ref)

    def lookup(self, payment_ref):
        return self._state(payment_ref)

    def find(self, purpose_ref, *, settled):
        hit = [r for r, x in self.p.items() if x["purpose"] == purpose_ref]
        return self._state(hit[0]) if hit else None

    def operation_effect(self, payment_ref, idempotency_key):
        return "applied" if idempotency_key in self.ops else "absent"

    def verify_webhook(self, headers, body):
        return None


def _purchase_ship_return_refund(w):
    from brandme_core.domains.providers.local_atelier import Behavior
    from tests.fixtures.commerce.harness import line
    _, quote, op = w.prepared(w.member, line("overshirt"), line("bag"))
    res = w.svc.execute_purchase(w.member, operation_id=op.id, approval_id=w.approve(op).id,
                                 idempotency_key="swap-proof-0000000001")
    assert res.state == "accepted"
    order = w.store.get("orders", res.order_id)
    for headers, body in w.provider.ship(order.provider_order_ref):
        w.svc.handle_webhook("demo_atelier", headers, body)
    o = w.store.get("orders", order.id)
    assert (o.payment_status, o.fulfillment_status) == ("captured", "fulfilled")
    assert w.svc.request_return(w.member, order.id, "demo-bag-m", 1)["status"] == "return_requested"
    w.provider.arm(Behavior.REFUND, source_variant_ref="demo-bag-m", quantity=1)
    for headers, body in w.provider.refund(order.provider_order_ref):
        w.svc.handle_webhook("demo_atelier", headers, body)
    o = w.store.get("orders", order.id)
    from brandme_core.domains.commerce.money import Money
    assert o.payment_status == "partially_refunded" and o.refunded_total == Money(12900 + 1032, "USD")
    assert [r.status for r in w.store.rows("returns")] == ["received"]
    return o


def test_merchant_runs_on_a_different_fulfillment_provider():
    from tests.fixtures.commerce.harness import world
    w = world(fulfillment=Fake3PL)
    assert isinstance(w.provider.fulfillment, FulfillmentProvider) and w.provider.fulfillment.fulfillment_id == "fake_3pl"
    o = _purchase_ship_return_refund(w)
    assert {l.source_variant_ref: l.quantity_returned for l in o.lines} == {"demo-overshirt-m": 0, "demo-bag-m": 1}


def test_merchant_runs_on_a_different_payment_processor():
    """The swap proof: the same merchant code path, another PaymentProcessor, no other change."""
    from brandme_core.domains.providers.payments import PaymentProcessor
    from tests.fixtures.commerce.harness import world
    w = world(payments=FakeProcessor)
    assert isinstance(w.provider.payments, PaymentProcessor) and w.provider.payee_ref == "fake-payee"
    _purchase_ship_return_refund(w)
    assert sorted(x["status"] for x in w.provider.payments.p.values()) == ["captured"]
