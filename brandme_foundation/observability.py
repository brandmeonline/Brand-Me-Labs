"""Observability — per-owner telemetry exporter.

Stdout structured-logs exporter that any service can call. Same
schema OpenTelemetry will consume in Phase 5 (pending-actions item 28).

P9 Cluster D adds a per-owner cost & latency meter (`CostMeter`). It is
the aggregation point for the budget decrements the MCP servers already
record: at each decrement site (policy-governance token spend, staging
GPU render, elevenlabs TTS chars) the server calls `record_spend(...)`,
and the meter rolls the raw quantity into a per-owner / per-day /
per-category bucket. Costs are derived from those quantities via a fixed
unit-cost table. A owner crossing the daily cost ceiling fires
`on_high_risk_alert` (the existing topic) exactly once per day — the
autonomy dial (Cluster C) reads that to auto-downgrade a runaway owner.

Observability is always on: there is NO feature flag. The meter never
raises into the hot path — every record/publish is defensive.
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator


def _emit(record: dict[str, Any]) -> None:
    record.setdefault("ts", datetime.now(timezone.utc).isoformat())
    sys.stderr.write(json.dumps(record) + "\n")
    sys.stderr.flush()


def log(owner_id: str, event: str, **fields: Any) -> None:
    _emit({"owner_id": owner_id, "event": event, **fields})


@contextmanager
def trace(owner_id: str, span: str, **fields: Any) -> Iterator[None]:
    start = time.monotonic()
    _emit({"owner_id": owner_id, "event": f"{span}.start", **fields})
    try:
        yield
    finally:
        duration_ms = (time.monotonic() - start) * 1000.0
        _emit({"owner_id": owner_id, "event": f"{span}.end",
               "duration_ms": duration_ms, **fields})
        # Feed the latency meter so p95-per-surface is always-on wherever a
        # span is traced. Defensive — telemetry never breaks the traced path.
        try:
            meter().record_latency(owner_id, span, duration_ms)
        except Exception:  # noqa: S110 — observability must never raise
            pass


# ===========================================================================
# P9 Cluster D — per-owner cost & latency meter
# ===========================================================================

# Spend categories, in fixed order (also the categorical chart order).
# Retargeted from Lux's (model, gpu, tts) to Brand.Me's metered surfaces.
CATEGORIES: tuple[str, ...] = ("model", "zk_proof", "chain_anchor")

# Unit-cost table (USD). Deterministic, config-free defaults; the real rate
# card swaps in behind these constants without touching call sites.
#   model → per 1K tokens · zk_proof → per generated proof
#   chain_anchor → per submitted Cardano anchoring transaction
UNIT_COSTS: dict[str, float] = {
    "model": 0.01 / 1000.0,   # $0.01 / 1K tokens
    "zk_proof": 0.02,         # $0.02 / proof generation
    "chain_anchor": 0.25,     # $0.25 / anchoring transaction
}

# Per-owner daily cost ceiling (USD). Crossing it fires on_high_risk_alert
# once per owner per day; the autonomy dial reads that alert.
DAILY_COST_CEILING_USD = 25.0

# Reference daily caps for the dashboard's cap-utilization meters. These
# MIRROR the per-service budget constants once those land in the Brand.Me
# services (identity ZK proof cap, chain anchoring cap) — duplicated here (not
# imported) so observability stays a leaf every service can import without a
# cycle. Enforcement lives in the services; these are display denominators.
REF_CAPS: dict[str, int] = {
    "model": 50_000,       # tokens / agent / day (per-agent; shown as reference)
    "zk_proof": 500,       # proof generations / owner / day
    "chain_anchor": 100,   # anchoring transactions / owner / day
}

# The raw-quantity unit each category counts (for the UI legend/table).
CATEGORY_UNITS: dict[str, str] = {
    "model": "tokens", "zk_proof": "proofs", "chain_anchor": "transactions"}


def category_cost(category: str, quantity: float) -> float:
    """USD cost of `quantity` raw units in `category`."""
    return float(quantity) * UNIT_COSTS.get(category, 0.0)


BrokerLookup = Callable[[], Any]


_BROKER_LOOKUP: BrokerLookup | None = None


def install_broker_lookup(lookup: BrokerLookup | None) -> None:
    """Register the process-wide broker lookup.

    Lux resolved this by lazy-importing its gateway module. Brand.Me services
    are separate processes with no shared gateway, so the lookup is injected
    at startup instead — observability stays import-safe everywhere.
    """
    global _BROKER_LOOKUP
    _BROKER_LOOKUP = lookup


def _installed_broker() -> Any:
    """Resolve the installed broker, or None when nothing registered one."""
    if _BROKER_LOOKUP is None:
        return None
    try:
        return _BROKER_LOOKUP()
    except Exception:  # pragma: no cover — never raise into the hot path
        return None


class CostMeter:
    """Per-owner, per-day, per-category spend + per-surface latency.

    Buckets key on (utc-date, owner_id, category) so they reset at UTC
    midnight simply by keying — the same pattern the MCP budget stores use.
    Every method keys on owner_id: one tenant's spend never surfaces to
    another (tenant isolation).
    """

    def __init__(
        self,
        *,
        broker_lookup: BrokerLookup | None = None,
        clock: Callable[[], datetime] | None = None,
        ceiling_usd: float = DAILY_COST_CEILING_USD,
    ) -> None:
        self._broker_lookup = broker_lookup or _installed_broker
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._ceiling = ceiling_usd
        # (date, owner_id, category) → raw quantity
        self._spend: dict[tuple[str, str, str], float] = defaultdict(float)
        # (date, owner_id, surface) → latency samples (ms)
        self._latency: dict[tuple[str, str, str], list[float]] = defaultdict(list)
        # (date, owner_id) already alerted this day → dedupe the alert
        self._alerted: set[tuple[str, str]] = set()

    # ---- clock -----------------------------------------------------------

    def _today(self) -> str:
        return self._clock().date().isoformat()

    def _recent_days(self, days: int) -> list[str]:
        """Oldest → newest list of the last `days` UTC dates (inclusive)."""
        from datetime import timedelta
        today = self._clock().date()
        return [(today - timedelta(days=n)).isoformat()
                for n in range(days - 1, -1, -1)]

    # ---- recording (called from the servers' decrement sites) ------------

    def record_spend(
        self,
        owner_id: str,
        category: str,
        quantity: float,
        *,
        agent: str | None = None,
        surface: str | None = None,
    ) -> None:
        """Roll a budget decrement into today's per-owner category bucket.

        Always-on and defensive: never raises into the caller's hot path.
        Fires on_high_risk_alert once/day/owner when the day's total cost
        crosses the ceiling on this decrement.
        """
        try:
            if not owner_id or category not in UNIT_COSTS or quantity <= 0:
                return
            day = self._today()
            before = self._daily_cost(day, owner_id)
            self._spend[(day, owner_id, category)] += float(quantity)
            after = self._daily_cost(day, owner_id)
            if before < self._ceiling <= after:
                self._fire_ceiling_alert(day, owner_id, after, category)
        except Exception:  # noqa: S110 — observability must never raise
            pass

    def record_latency(self, owner_id: str, surface: str, ms: float) -> None:
        """Record one latency sample (ms) for a surface. Defensive."""
        try:
            if not owner_id or not surface:
                return
            self._latency[(self._today(), owner_id, surface)].append(float(ms))
        except Exception:  # noqa: S110 — observability must never raise
            pass

    # ---- alert seam ------------------------------------------------------

    def _fire_ceiling_alert(
        self, day: str, owner_id: str, cost_usd: float, category: str,
    ) -> None:
        """Publish on_high_risk_alert (existing topic) once/day/owner.

        Defensive publish (P6 pattern): the topic row is owned by Cluster A;
        TopicNotConfigured and any broker error are swallowed so the meter
        ships ahead of / independent of the alert wiring."""
        key = (day, owner_id)
        if key in self._alerted:
            return
        self._alerted.add(key)
        broker = self._broker_lookup()
        if broker is None:
            return
        try:
            from brandme_foundation.hooks.broker import TopicNotConfigured
            try:
                broker.publish("on_high_risk_alert", owner_id, {
                    "source": "cost_meter",
                    "reason": "daily_cost_ceiling_crossed",
                    "owner_id": owner_id,
                    "date": day,
                    "cost_usd": round(cost_usd, 4),
                    "ceiling_usd": self._ceiling,
                    "category": category,
                })
            except TopicNotConfigured:
                return  # topic row not merged yet — alert activates then
        except Exception:  # noqa: S110 — never raise from the meter
            return

    # ---- aggregation / queries -------------------------------------------

    def _daily_cost(self, day: str, owner_id: str) -> float:
        return sum(
            category_cost(cat, self._spend.get((day, owner_id, cat), 0.0))
            for cat in CATEGORIES
        )

    def daily_series(self, owner_id: str, days: int) -> list[dict[str, Any]]:
        """Oldest→newest daily rows for one owner: raw quantities + USD."""
        rows: list[dict[str, Any]] = []
        for day in self._recent_days(days):
            row: dict[str, Any] = {"date": day}
            total = 0.0
            for cat in CATEGORIES:
                qty = self._spend.get((day, owner_id, cat), 0.0)
                cost = category_cost(cat, qty)
                total += cost
                row[f"{cat}_qty"] = qty
                row[f"{cat}_usd"] = round(cost, 4)
            row["total_usd"] = round(total, 4)
            row["over_ceiling"] = total >= self._ceiling
            rows.append(row)
        return rows

    def totals(self, owner_id: str, days: int) -> dict[str, float]:
        rows = self.daily_series(owner_id, days)
        out = {f"{cat}_usd": round(sum(r[f"{cat}_usd"] for r in rows), 4)
               for cat in CATEGORIES}
        out["total_usd"] = round(sum(r["total_usd"] for r in rows), 4)
        return out

    def cap_utilization(self, owner_id: str, day: str | None = None) -> dict[str, Any]:
        """Today's (or `day`'s) usage against the reference caps + ceiling."""
        day = day or self._today()
        per_cat: dict[str, Any] = {}
        for cat in CATEGORIES:
            used = self._spend.get((day, owner_id, cat), 0.0)
            cap = REF_CAPS[cat]
            per_cat[cat] = {
                "unit": CATEGORY_UNITS[cat],
                "used": used,
                "cap": cap,
                "pct": round(100.0 * used / cap, 2) if cap else 0.0,
                "usd": round(category_cost(cat, used), 4),
            }
        cost = self._daily_cost(day, owner_id)
        return {
            "date": day,
            "cost": {
                "used_usd": round(cost, 4),
                "ceiling_usd": self._ceiling,
                "pct": round(100.0 * cost / self._ceiling, 2) if self._ceiling else 0.0,
                "over_ceiling": cost >= self._ceiling,
            },
            "categories": per_cat,
        }

    def latency_p95(self, owner_id: str, days: int) -> list[dict[str, Any]]:
        """p95 latency (ms) per surface over the window, sorted by surface."""
        by_surface: dict[str, list[float]] = defaultdict(list)
        window = set(self._recent_days(days))
        for (day, rid, surface), samples in self._latency.items():
            if rid == owner_id and day in window:
                by_surface[surface].extend(samples)
        out: list[dict[str, Any]] = []
        for surface in sorted(by_surface):
            samples = sorted(by_surface[surface])
            out.append({
                "surface": surface,
                "p95_ms": round(_percentile(samples, 95.0), 3),
                "samples": len(samples),
            })
        return out

    def reset_for_test(self) -> None:
        """Test-only — clear every bucket."""
        self._spend.clear()
        self._latency.clear()
        self._alerted.clear()


def _percentile(sorted_samples: list[float], pct: float) -> float:
    """Nearest-rank percentile of a pre-sorted list (empty → 0.0)."""
    if not sorted_samples:
        return 0.0
    import math
    rank = max(1, math.ceil(pct / 100.0 * len(sorted_samples)))
    return sorted_samples[min(rank, len(sorted_samples)) - 1]


# Process-wide singleton — the servers and the gateway share one meter.
_METER: CostMeter | None = None


def meter() -> CostMeter:
    global _METER
    if _METER is None:
        _METER = CostMeter()
    return _METER


def set_meter(m: CostMeter | None) -> None:
    """Test hook — swap (or reset) the process-wide meter."""
    global _METER
    _METER = m


def record_spend(
    owner_id: str,
    category: str,
    quantity: float,
    *,
    agent: str | None = None,
    surface: str | None = None,
) -> None:
    """Module-level convenience: record a decrement on the shared meter."""
    meter().record_spend(owner_id, category, quantity, agent=agent, surface=surface)


def cost_summary(owner_id: str, days: int) -> dict[str, Any]:
    """The /api/ops/cost response body for one owner over `days`."""
    m = meter()
    return {
        "owner_id": owner_id,
        "days": days,
        "ceiling_usd": m._ceiling,
        "unit_costs": {
            "model_per_1k_tokens": round(UNIT_COSTS["model"] * 1000, 6),
            "gpu_per_job": UNIT_COSTS["gpu"],
            "tts_per_1k_chars": round(UNIT_COSTS["tts"] * 1000, 6),
        },
        "category_units": dict(CATEGORY_UNITS),
        "series": m.daily_series(owner_id, days),
        "totals": m.totals(owner_id, days),
        "cap_utilization": m.cap_utilization(owner_id),
        "latency_p95": m.latency_p95(owner_id, days),
    }
