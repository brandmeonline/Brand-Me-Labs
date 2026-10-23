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
