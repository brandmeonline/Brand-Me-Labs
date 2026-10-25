"""BM-COM-011 across the lane boundary: the ``commerce.order.observed`` payloads the simulator flows emit,
reduced by the wardrobe's own unit reducer, give the wardrobe quantities ch.05 §6 describes.

Read-only use of ``brandme_core.domains.wardrobe.model.order_unit_states`` (consumer-domains lane).
Commerce owns the payload; the wardrobe owns the reduction. One case the reducer does not cover yet,
units cancelled while the order goes on (a per-line ``cancelled`` count), is checked only on the
commerce side here and recorded in the S13 fidelity checklist as a wardrobe-side follow-up.
"""

from collections import Counter

import pytest

from brandme_core.domains.providers.local_atelier import Behavior
from brandme_core.domains.wardrobe.model import order_unit_states
from tests.fixtures.commerce.harness import line, world
from tests.test_commerce_payments_flow import _buy, _hook, _order


@pytest.fixture
def w():
    return world()


def _last_observation(w):
    return [e for e in w.store.outbox() if e.event_type == "commerce.order.observed"][-1].payload


def _wardrobe(payload):
    """Per variant: how many units the wardrobe reducer files under each (collection, status)."""
    cancelled = payload["order_status"] == "cancelled"
    return {ln["source_variant_ref"]: Counter((u.collection, u.acquisition_status) for u in order_unit_states(
        ln["ordered"], ln["delivered"], ln["returned"], cancelled)) for ln in payload["lines"]}


ON_THE_WAY, OWNED = ("on_the_way", "ordered"), ("owned", "delivered")
RETURNED, CANCELLED = ("archive", "returned"), ("archive", "cancelled")


def test_accepted_order_files_every_unit_on_the_way_with_evidence(w):
    _, res = _buy(w, w.member, line("overshirt", "m", 2))
    _order(w, res)  # acceptance, then the authorization re-read
    first, last = [e.payload for e in w.store.outbox() if e.event_type == "commerce.order.observed"]
    assert (first["wardrobe_effect"], last["wardrobe_effect"]) == ("incoming", "updated")
    assert first["acquisition_evidence"] and last["acquisition_evidence"]
    assert _wardrobe(first) == _wardrobe(last) == {"demo-overshirt-m": Counter({ON_THE_WAY: 2})}


def test_partial_shipment_moves_only_the_delivered_units(w):
    _, res = _buy(w, w.member, line("overshirt", "m", 2), line("trousers", "m", 1))
    order = _order(w, res)
    w.provider.arm(Behavior.PARTIAL_FULFILLMENT, source_variant_ref="demo-overshirt-m", quantity=1)
    _hook(w, w.provider.ship(order.provider_order_ref))
    p = _last_observation(w)
    assert p["wardrobe_effect"] == "arrived" and p["fulfillment_status"] == "partially_fulfilled"
    assert _wardrobe(p) == {"demo-overshirt-m": Counter({OWNED: 1, ON_THE_WAY: 1}),
                            "demo-trousers-m": Counter({OWNED: 1})}
    _hook(w, w.provider.ship(order.provider_order_ref))
    assert _wardrobe(_last_observation(w)) == {"demo-overshirt-m": Counter({OWNED: 2}),
                                               "demo-trousers-m": Counter({OWNED: 1})}


def test_exchange_archives_the_original_unit_and_tracks_the_replacement(w):
    _, res = _buy(w, w.member, line("overshirt", "m", 1))
    order = _order(w, res)
    _hook(w, w.provider.ship(order.provider_order_ref))
    _hook(w, w.provider.exchange(order.provider_order_ref, "demo-overshirt-m", "demo-overshirt-l"))
    p = _last_observation(w)
    assert p["wardrobe_effect"] == "exchanged"
    assert {ln["source_variant_ref"]: ln["exchanged_from_ref"] for ln in p["lines"]} == {
        "demo-overshirt-m": None, "demo-overshirt-l": "demo-overshirt-m"}  # the variant relationship
    assert _wardrobe(p) == {"demo-overshirt-m": Counter({RETURNED: 1}), "demo-overshirt-l": Counter({ON_THE_WAY: 1})}
    _hook(w, w.provider.ship(order.provider_order_ref))
    assert _wardrobe(_last_observation(w)) == {"demo-overshirt-m": Counter({RETURNED: 1}),
                                               "demo-overshirt-l": Counter({OWNED: 1})}


def test_refund_of_a_delivered_unit_archives_it_as_returned(w):
    _, res = _buy(w, w.member, line("overshirt", "m", 1), line("bag", "m", 1))
    order = _order(w, res)
    _hook(w, w.provider.ship(order.provider_order_ref))
    w.provider.arm(Behavior.REFUND, source_variant_ref="demo-bag-m", quantity=1)
    _hook(w, w.provider.refund(order.provider_order_ref))
    p = _last_observation(w)
    assert p["wardrobe_effect"] == "returned" and p["payment_status"] == "partially_refunded"
    assert _wardrobe(p) == {"demo-overshirt-m": Counter({OWNED: 1}), "demo-bag-m": Counter({RETURNED: 1})}


def test_a_cancelled_order_archives_every_unit_as_cancelled(w):
    _, res = _buy(w, w.member, line("overshirt", "m", 2))
    order = _order(w, res)
    w.svc.request_cancellation(w.member, order.id, idempotency_key="contract-cancel-0001")
    p = _last_observation(w)
    assert p["wardrobe_effect"] == "cancelled" and p["order_status"] == "cancelled"
    assert _wardrobe(p) == {"demo-overshirt-m": Counter({CANCELLED: 2})}


@pytest.mark.parametrize("how", ["member_cancels_the_unshipped_line", "refund_before_shipment"])
def test_units_cancelled_while_the_order_goes_on_are_carried_per_line(w, how):
    """Commerce side only: the payload says exactly which units will never arrive. The wardrobe reducer
    reads the order-level status, so these units would stay "on the way" (S13 checklist, wardrobe follow-up)."""
    _, res = _buy(w, w.member, line("overshirt", "m", 1), line("bag", "m", 1))
    order = _order(w, res)
    w.provider.arm(Behavior.PARTIAL_FULFILLMENT, source_variant_ref="demo-bag-m", quantity=0)
    _hook(w, w.provider.ship(order.provider_order_ref))  # the bag has not shipped
    if how == "member_cancels_the_unshipped_line":
        w.svc.request_cancellation(w.member, order.id, idempotency_key="contract-cancel-0002")
    else:
        w.provider.arm(Behavior.REFUND, source_variant_ref="demo-bag-m", quantity=1)
        _hook(w, w.provider.refund(order.provider_order_ref))
    p = _last_observation(w)
    bag = next(ln for ln in p["lines"] if ln["source_variant_ref"] == "demo-bag-m")
    assert p["order_status"] == "accepted" and p["fulfillment_status"] == "fulfilled"
    assert (bag["ordered"], bag["shipped"], bag["delivered"], bag["returned"], bag["cancelled"]) == (1, 0, 0, 0, 1)
