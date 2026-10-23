"""
Looking Glass persona model: pure, deterministic domain logic (no I/O).

Chapter 01 §4 and chapter 03 §4. Four records are kept separate:
declared preference, inferred preference, context override and the derived
effective preference. ``None`` always means unknown/unanswered — it is never
silently converted to a neutral 50.

Precedence (ch.01 §4.2), highest first:
  1. an active, member-enabled context override for that axis
  2. a locked declared value
  3. an unlocked declared value (adaptation toward inference only via the
     bounded, member-visible weekly proposal flow — never a silent blend)
  4. an inference, only if learning is enabled and the axis permits inference
  5. unknown (None)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .kernel import ValidationFailed, require_strict_int

AXIS_KEYS: Tuple[str, ...] = (
    "temperature",
    "sport_couture",
    "expression",
    "fit_language",
    "detail",
    "novelty",
    "color",
    "finish",
    "structure",
    "setting",
    "exploration",
    "utility",
)

AXIS_LABELS: Dict[str, Tuple[str, str]] = {
    "temperature": ("Warm", "Cool"),
    "sport_couture": ("Sport", "Couture"),
    "expression": ("Understated", "Expressive"),
    "fit_language": ("Tailored", "Relaxed"),
    "detail": ("Minimal", "Ornate"),
    "novelty": ("Timeless", "Experimental"),
    "color": ("Neutral", "Colorful"),
    "finish": ("Matte", "Lustrous"),
    "structure": ("Structured", "Fluid"),
    "setting": ("Urban", "Outdoors"),
    "exploration": ("Familiar", "Exploratory"),
    "utility": ("Functional", "Decorative"),
}

PERSONA_SCHEMA_VERSION = 1
INFERENCE_MODEL_VERSION = "persona-infer-wmean-v1"
ADAPT_MAX_POINTS_PER_WEEK = 5
ADAPT_PERIOD = timedelta(days=7)
INFERENCE_PURPOSE = "personalization"

# Effective-value sources, exposed to the inspector ("Your choice is in control").
SRC_OVERRIDE = "context_override"
SRC_LOCKED = "declared_locked"
SRC_DECLARED = "declared"
SRC_INFERRED = "inferred"
SRC_UNKNOWN = "unknown"


def round_half_up(x: float) -> int:
    return int(Decimal(repr(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def validate_axis_key(key: object) -> str:
    if not isinstance(key, str) or key not in AXIS_KEYS:
        raise ValidationFailed(f"unknown persona axis {key!r}", extra={"field": "axis"})
    return key


def validate_axis_value(value: object, *, name: str = "value") -> Optional[int]:
    if value is None:
        return None
    return require_strict_int(value, name=name, lo=0, hi=100)


@dataclass(frozen=True)
class AxisState:
    key: str
    declared: Optional[int] = None
    locked: bool = False
    adapt_enabled: bool = False
    adapt_first_accepted: bool = False
    adapt_last_applied_at: Optional[datetime] = None
    inference_allowed: bool = True
    hidden: bool = False
    declared_revision: int = 0
    inferred: Optional[int] = None
    inferred_confidence: Optional[float] = None
    inferred_evidence_count: int = 0


@dataclass(frozen=True)
class ContextOverride:
    override_id: str
    label: str
    axes: Mapping[str, int]
    starts_at: datetime
    ends_at: datetime
    enabled: bool

    def active(self, now: datetime) -> bool:
        return self.enabled and self.starts_at <= now < self.ends_at


@dataclass(frozen=True)
class EffectiveAxis:
    value: Optional[int]
    source: str
    override_id: Optional[str] = None


def resolve_effective(
    axes: Mapping[str, AxisState],
    overrides: Sequence[ContextOverride],
    learning_enabled: bool,
    now: datetime,
) -> Dict[str, EffectiveAxis]:
    # Deterministic: if several active overrides cover one axis, the most
    # recently started wins; ties break by id.
    active = sorted(
        (o for o in overrides if o.active(now)),
        key=lambda o: (o.starts_at, o.override_id),
        reverse=True,
    )
    out: Dict[str, EffectiveAxis] = {}
    for key in AXIS_KEYS:
        st = axes.get(key) or AxisState(key=key)
        ov = next((o for o in active if key in o.axes), None)
        if ov is not None:
            out[key] = EffectiveAxis(ov.axes[key], SRC_OVERRIDE, ov.override_id)
        elif st.declared is not None and st.locked:
            out[key] = EffectiveAxis(st.declared, SRC_LOCKED)
        elif st.declared is not None:
            out[key] = EffectiveAxis(st.declared, SRC_DECLARED)
        elif learning_enabled and st.inference_allowed and st.inferred is not None:
            out[key] = EffectiveAxis(st.inferred, SRC_INFERRED)
        else:
            out[key] = EffectiveAxis(None, SRC_UNKNOWN)
    return out


# ---------------------------------------------------------------------------
# Evidence and inference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source_type: str
    source_ref: str
    purpose: str
    axis_contributions: Mapping[str, int]
    weight: float
    observed_at: datetime
    expires_at: Optional[datetime] = None
    consent_id: Optional[str] = None
    suppression_state: str = "active"

    @property
    def fingerprint(self) -> str:
        return source_fingerprint(self.source_type, self.source_ref)


EVIDENCE_SOURCE_TYPES = frozenset(
    {"onboarding_choice", "saved_look", "saved_product", "wardrobe_item", "recommendation_feedback", "outfit_worn"}
)


def source_fingerprint(source_type: str, source_ref: str) -> str:
    return hashlib.sha256(f"{source_type}\x1f{source_ref}".encode()).hexdigest()


def validate_contributions(raw: object) -> Dict[str, int]:
    if not isinstance(raw, Mapping) or not raw:
        raise ValidationFailed("axis_contributions must be a non-empty object")
    out: Dict[str, int] = {}
    for k, v in raw.items():
        out[validate_axis_key(k)] = require_strict_int(v, name=f"axis_contributions.{k}", lo=0, hi=100)
    return out


@dataclass(frozen=True)
class Inference:
    value: int
    confidence: float
    evidence_count: int


def evidence_eligible(
    ev: Evidence,
    *,
    now: datetime,
    suppressed_fingerprints: Set[str],
    revoked_consents: Set[str],
) -> bool:
    if ev.suppression_state != "active":
        return False
    if ev.fingerprint in suppressed_fingerprints:
        return False
    if ev.purpose != INFERENCE_PURPOSE:
        return False
    if ev.expires_at is not None and ev.expires_at <= now:
        return False
    if ev.consent_id is not None and ev.consent_id in revoked_consents:
        return False
    return True


def infer_axes(
    evidence: Iterable[Evidence],
    *,
    now: datetime,
    suppressed_fingerprints: Set[str] = frozenset(),
    revoked_consents: Set[str] = frozenset(),
) -> Dict[str, Optional[Inference]]:
    """Weighted mean of eligible evidence per axis; deterministic, explainable.

    Confidence = W / (W + 2) where W is the summed weight, so one weak
    observation yields low confidence and the value is shown with it.
    """
    sums: Dict[str, float] = {k: 0.0 for k in AXIS_KEYS}
    weights: Dict[str, float] = {k: 0.0 for k in AXIS_KEYS}
    counts: Dict[str, int] = {k: 0 for k in AXIS_KEYS}
    for ev in sorted(evidence, key=lambda e: e.evidence_id):
        if not evidence_eligible(ev, now=now, suppressed_fingerprints=suppressed_fingerprints, revoked_consents=revoked_consents):
            continue
        for axis, target in ev.axis_contributions.items():
            sums[axis] += ev.weight * target
            weights[axis] += ev.weight
            counts[axis] += 1
    out: Dict[str, Optional[Inference]] = {}
    for k in AXIS_KEYS:
        w = weights[k]
        if w <= 0:
            out[k] = None
        else:
            out[k] = Inference(
                value=max(0, min(100, round_half_up(sums[k] / w))),
                confidence=round(w / (w + 2.0), 4),
                evidence_count=counts[k],
            )
    return out


def apply_inference(axes: Mapping[str, AxisState], inferred: Mapping[str, Optional[Inference]]) -> Dict[str, AxisState]:
    """Write inference into the inferred slots only. Declared/locked fields are untouched,
    which is why an inference race can never overwrite a manual lock."""
    out = {}
    for k in AXIS_KEYS:
        st = axes.get(k) or AxisState(key=k)
        inf = inferred.get(k)
        if not st.inference_allowed or inf is None:
            out[k] = replace(st, inferred=None, inferred_confidence=None, inferred_evidence_count=0)
        else:
            out[k] = replace(st, inferred=inf.value, inferred_confidence=inf.confidence, inferred_evidence_count=inf.evidence_count)
    return out


# ---------------------------------------------------------------------------
# Bounded adaptation ("Let this adapt")
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdaptationProposal:
    axis: str
    current: int
    proposed: int
    inferred: int
    requires_confirmation: bool


def adaptation_proposals(axes: Mapping[str, AxisState], learning_enabled: bool, now: datetime) -> List[AdaptationProposal]:
    """Move an adapting (unlocked, adapt-enabled) declared value toward inference
    by at most 5 points per 7 days. The first move needs explicit acceptance."""
    if not learning_enabled:
        return []
    out = []
    for k in AXIS_KEYS:
        st = axes.get(k)
        if st is None or st.declared is None or st.locked or not st.adapt_enabled:
            continue
        if not st.inference_allowed or st.inferred is None or st.inferred == st.declared:
            continue
        if st.adapt_last_applied_at is not None and now - st.adapt_last_applied_at < ADAPT_PERIOD:
            continue
        delta = max(-ADAPT_MAX_POINTS_PER_WEEK, min(ADAPT_MAX_POINTS_PER_WEEK, st.inferred - st.declared))
        out.append(
            AdaptationProposal(
                axis=k,
                current=st.declared,
                proposed=st.declared + delta,
                inferred=st.inferred,
                requires_confirmation=not st.adapt_first_accepted,
            )
        )
    return out


def axis_labels(key: str, value: Optional[int]) -> str:
    left, right = AXIS_LABELS[key]
    if value is None:
        return "unanswered"
    if value <= 40:
        return left
    if value >= 60:
        return right
    return f"between {left} and {right}"
