"""Cost-meter and telemetry tests for the ported observability module.

Lux ships `services/observability.py` without a dedicated test module. The
port changed two things that need cover:

  * the broker lookup is injected (`install_broker_lookup`) instead of
    lazy-importing Lux's gateway, and
  * the spend categories are Brand.Me's (model / zk_proof / chain_anchor).

The invariants carried over from Lux and asserted here: the meter never
raises into a caller's hot path, it fires the ceiling alert at most once per
owner per day, and no owner's spend is ever visible to another.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from brandme_foundation.observability import (
    CATEGORIES,
    DAILY_COST_CEILING_USD,
    CostMeter,
    category_cost,
    install_broker_lookup,
)


class _RecordingBroker:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, dict]] = []

    def publish(self, topic: str, owner_id: str, payload: dict) -> None:
        self.published.append((topic, owner_id, payload))


@pytest.fixture(autouse=True)
def _no_ambient_broker():
    install_broker_lookup(None)
    yield
    install_broker_lookup(None)


def _meter(broker=None, day="2026-08-31") -> CostMeter:
    clock = lambda: datetime.fromisoformat(day).replace(tzinfo=timezone.utc)  # noqa: E731
    return CostMeter(broker_lookup=(lambda: broker), clock=clock)


# ---- categories were retargeted to Brand.Me surfaces --------------------


def test_categories_are_brandme_surfaces() -> None:
    assert CATEGORIES == ("model", "zk_proof", "chain_anchor")


def test_category_cost_is_linear_in_quantity() -> None:
    assert category_cost("chain_anchor", 4) == pytest.approx(1.0)
    assert category_cost("zk_proof", 100) == pytest.approx(2.0)


def test_unknown_category_costs_nothing_rather_than_raising() -> None:
    assert category_cost("gpu", 1_000_000) == 0.0


# ---- tenant isolation ---------------------------------------------------


def test_one_owners_spend_never_surfaces_to_another() -> None:
    meter = _meter()
    meter.record_spend("owner-a", "chain_anchor", 10)
    assert meter.totals("owner-a", 1)["total_usd"] > 0
    assert meter.totals("owner-b", 1)["total_usd"] == 0


def test_spend_without_an_owner_is_dropped() -> None:
    """The tenant key is mandatory; an untenanted decrement is not recorded."""
    meter = _meter()
    meter.record_spend("", "chain_anchor", 10)
    assert meter.totals("", 1)["total_usd"] == 0


# ---- the meter never raises into the hot path ---------------------------


@pytest.mark.parametrize(
    "args",
    [
        ("owner-a", "not-a-category", 5),
        ("owner-a", "chain_anchor", -1),
        ("owner-a", "chain_anchor", 0),
    ],
)
def test_bad_input_is_swallowed(args) -> None:
    meter = _meter()
    meter.record_spend(*args)
    assert meter.totals("owner-a", 1)["total_usd"] == 0


def test_a_raising_broker_does_not_propagate() -> None:
    class _Boom:
        def publish(self, *a, **k):
            raise RuntimeError("broker down")

    meter = _meter(broker=_Boom())
    meter.record_spend("owner-a", "chain_anchor", 1000)  # far over the ceiling
    assert meter.totals("owner-a", 1)["total_usd"] > DAILY_COST_CEILING_USD


# ---- ceiling alert ------------------------------------------------------


def test_crossing_the_ceiling_fires_the_alert_once() -> None:
    broker = _RecordingBroker()
    meter = _meter(broker=broker)
    over = (DAILY_COST_CEILING_USD / 0.25) + 4  # anchors needed to cross
    meter.record_spend("owner-a", "chain_anchor", over)
    meter.record_spend("owner-a", "chain_anchor", over)  # already over: no re-fire

    assert [t for t, _, _ in broker.published] == ["on_high_risk_alert"]
    _, owner, payload = broker.published[0]
    assert owner == "owner-a"
    assert payload["reason"] == "daily_cost_ceiling_crossed"
    assert payload["category"] == "chain_anchor"


def test_alert_dedupe_holds_independently_of_the_crossing_guard() -> None:
    """`record_spend` only fires on the ceiling *crossing*, so the (day, owner)
    dedupe set is a second, independent guard. Exercise it directly — otherwise
    removing the dedupe passes every other test in this module."""
    broker = _RecordingBroker()
    meter = _meter(broker=broker)
    for _ in range(3):
        meter._fire_ceiling_alert("2026-08-31", "owner-a", 99.0, "chain_anchor")

    assert len(broker.published) == 1


def test_alert_dedupe_is_per_owner_and_per_day() -> None:
    broker = _RecordingBroker()
    meter = _meter(broker=broker)
    meter._fire_ceiling_alert("2026-08-31", "owner-a", 99.0, "chain_anchor")
    meter._fire_ceiling_alert("2026-08-31", "owner-b", 99.0, "chain_anchor")
    meter._fire_ceiling_alert("2026-09-01", "owner-a", 99.0, "chain_anchor")

    assert len(broker.published) == 3
    assert [owner for _, owner, _ in broker.published] == [
        "owner-a", "owner-b", "owner-a"]


def test_staying_under_the_ceiling_fires_nothing() -> None:
    broker = _RecordingBroker()
    meter = _meter(broker=broker)
    meter.record_spend("owner-a", "zk_proof", 1)
    assert broker.published == []


def test_the_alert_topic_exists_so_the_alert_is_not_dead() -> None:
    """Regression guard: the meter publishes on_high_risk_alert. If that topic
    is missing from topics.yaml the broker refuses it and the autonomy signal
    silently never arrives."""
    from brandme_foundation.hooks import topic_names

    assert "on_high_risk_alert" in topic_names()


# ---- broker injection replaces Lux's gateway import ---------------------


def test_no_installed_lookup_means_no_broker_and_no_error() -> None:
    meter = CostMeter(
        clock=lambda: datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    meter.record_spend("owner-a", "chain_anchor", 10_000)
    assert meter.totals("owner-a", 1)["total_usd"] > 0


def test_installed_lookup_is_used_by_default() -> None:
    broker = _RecordingBroker()
    install_broker_lookup(lambda: broker)
    meter = CostMeter(clock=lambda: datetime(2026, 8, 31, tzinfo=timezone.utc))
    meter.record_spend("owner-a", "chain_anchor", 10_000)
    assert [t for t, _, _ in broker.published] == ["on_high_risk_alert"]
