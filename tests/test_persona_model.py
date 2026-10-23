"""Pure domain tests for persona precedence, inference, suppression and
bounded adaptation (no database)."""

from datetime import datetime, timedelta, timezone

import pytest

from brandme_core.domains.persona.kernel import ValidationFailed
from brandme_core.domains.persona.model import (
    AXIS_KEYS,
    SRC_DECLARED,
    SRC_INFERRED,
    SRC_LOCKED,
    SRC_OVERRIDE,
    SRC_UNKNOWN,
    AxisState,
    ContextOverride,
    Evidence,
    adaptation_proposals,
    apply_inference,
    infer_axes,
    resolve_effective,
    source_fingerprint,
    validate_axis_value,
)

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def axes(**kw):
    out = {k: AxisState(key=k) for k in AXIS_KEYS}
    for k, v in kw.items():
        out[k] = AxisState(key=k, **v)
    return out


def test_twelve_axes_exact_vocabulary():
    assert len(AXIS_KEYS) == 12 and len(set(AXIS_KEYS)) == 12


def test_unknown_is_none_not_neutral():
    eff = resolve_effective(axes(), [], True, NOW)
    assert all(e.value is None and e.source == SRC_UNKNOWN for e in eff.values())


def test_precedence_override_then_locked_then_declared_then_inferred():
    st = axes(
        expression={"declared": 78, "locked": True, "inferred": 20},
        color={"declared": 40, "locked": False, "inferred": 90},
        detail={"inferred": 33},
        finish={"declared": 10, "locked": True},
    )
    ov = ContextOverride("o1", "Trip", {"finish": 80}, NOW - timedelta(hours=1), NOW + timedelta(days=2), True)
    eff = resolve_effective(st, [ov], True, NOW)
    assert (eff["finish"].value, eff["finish"].source) == (80, SRC_OVERRIDE)
    assert (eff["expression"].value, eff["expression"].source) == (78, SRC_LOCKED)
    # unlocked declared is NOT silently blended with inference
    assert (eff["color"].value, eff["color"].source) == (40, SRC_DECLARED)
    assert (eff["detail"].value, eff["detail"].source) == (33, SRC_INFERRED)


def test_disabled_or_expired_override_is_ignored():
    st = axes(finish={"declared": 10, "locked": True})
    disabled = ContextOverride("o1", "x", {"finish": 80}, NOW - timedelta(hours=1), NOW + timedelta(hours=1), False)
    expired = ContextOverride("o2", "y", {"finish": 90}, NOW - timedelta(days=3), NOW, True)  # end is exclusive
    eff = resolve_effective(st, [disabled, expired], True, NOW)
    assert eff["finish"].source == SRC_LOCKED


def test_learning_disabled_and_do_not_infer_hide_inference():
    st = axes(detail={"inferred": 33}, color={"inferred": 70, "inference_allowed": False})
    assert resolve_effective(st, [], False, NOW)["detail"].source == SRC_UNKNOWN
    assert resolve_effective(st, [], True, NOW)["color"].source == SRC_UNKNOWN


def ev(eid, ref, contrib, **kw):
    return Evidence(eid, "saved_look", ref, kw.pop("purpose", "personalization"), contrib, kw.pop("weight", 1.0), NOW - timedelta(days=1), **kw)


def test_inference_weighted_mean_and_exclusions():
    evs = [
        ev("e1", "look-1", {"expression": 60}),
        ev("e2", "look-2", {"expression": 81}, weight=2.0),
        ev("e3", "look-3", {"expression": 0}, suppression_state="suppressed"),
        ev("e4", "look-4", {"expression": 0}, expires_at=NOW),
        ev("e5", "look-5", {"expression": 0}, consent_id="c-revoked"),
        ev("e6", "look-6", {"expression": 0}, purpose="advertising"),
        ev("e7", "look-7", {"expression": 0}),
    ]
    inf = infer_axes(
        evs,
        now=NOW,
        suppressed_fingerprints={source_fingerprint("saved_look", "look-7")},
        revoked_consents={"c-revoked"},
    )
    assert inf["expression"].value == 74  # (60 + 2*81)/3 = 74.0
    assert inf["expression"].evidence_count == 2
    assert inf["color"] is None


def test_inference_rounding_is_half_up_and_deterministic():
    evs = [ev("a", "1", {"color": 50}), ev("b", "2", {"color": 51})]
    assert infer_axes(evs, now=NOW)["color"].value == 51
    assert infer_axes(list(reversed(evs)), now=NOW)["color"].value == 51


def test_apply_inference_never_touches_declared_or_lock():
    st = axes(expression={"declared": 78, "locked": True, "declared_revision": 4})
    inf = infer_axes([ev("e", "x", {"expression": 5})], now=NOW)
    out = apply_inference(st, inf)
    assert out["expression"].declared == 78 and out["expression"].locked and out["expression"].declared_revision == 4
    assert out["expression"].inferred == 5
    assert resolve_effective(out, [], True, NOW)["expression"].value == 78


def test_adaptation_bounded_and_needs_first_confirmation():
    st = axes(color={"declared": 40, "adapt_enabled": True, "inferred": 90})
    [p] = adaptation_proposals(st, True, NOW)
    assert (p.current, p.proposed, p.requires_confirmation) == (40, 45, True)
    st2 = axes(color={"declared": 45, "adapt_enabled": True, "adapt_first_accepted": True, "inferred": 90, "adapt_last_applied_at": NOW - timedelta(days=3)})
    assert adaptation_proposals(st2, True, NOW) == []  # within the 7-day period
    st3 = axes(color={"declared": 45, "adapt_enabled": True, "adapt_first_accepted": True, "inferred": 43, "adapt_last_applied_at": NOW - timedelta(days=8)})
    [p3] = adaptation_proposals(st3, True, NOW)
    assert (p3.proposed, p3.requires_confirmation) == (43, False)
    locked = axes(color={"declared": 40, "locked": True, "adapt_enabled": True, "inferred": 90})
    assert adaptation_proposals(locked, True, NOW) == []
    assert adaptation_proposals(st, False, NOW) == []


@pytest.mark.parametrize("bad", [72.5, True, -1, 101, "72", float("nan")])
def test_axis_values_must_be_integers_in_range(bad):
    with pytest.raises(ValidationFailed):
        validate_axis_value(bad)
