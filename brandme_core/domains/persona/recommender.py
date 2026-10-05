"""
Deterministic, explainable recommender (chapter 03 §7, chapter 01 §3.3/§4.5).

Works with no AI/LLM key: the ranking is pure arithmetic over declared/effective
persona values, occasion, wardrobe compatibility, member feedback and an
exploration preference. Every reason returned is generated from a feature that
actually contributed to the score, and references concrete evidence (axis keys,
wardrobe item ids, feedback categories). A model may later *rephrase* these
reasons; it may not add facts.

Pipeline:
  1. Hard filters: visibility, availability, region, explicit exclusions,
     dismissed products, hard budget (missing/incomparable price is excluded
     when a budget is set — it cannot be shown to be within budget).
  2. Score survivors with weights 0.35/0.20/0.20/0.15/0.10. Missing features
     are omitted and remaining weights renormalised (never fabricated).
  3. Diversity caps: <=2 per category, <=2 per brand, one per variant group.
  4. Sponsored candidates are labelled and receive no score boost; they pass
     the same hard filters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from .model import AXIS_KEYS, AXIS_LABELS, SRC_INFERRED

RULE_VERSION = "det-rec-v1"
WEIGHTS: Dict[str, float] = {
    "persona_similarity": 0.35,
    "occasion_fit": 0.20,
    "wardrobe_compatibility": 0.20,
    "feedback_affinity": 0.15,
    "exploration_diversity": 0.10,
}
REASON_THRESHOLD = 0.5
MAX_PER_CATEGORY = 2
MAX_PER_BRAND = 2
DECISIVE_DISTANCE = 15  # member value at least this far from neutral 50 to be cited
MATCH_DISTANCE = 15     # candidate within this many points to be cited as a match

SIMILARITY_AXES = tuple(k for k in AXIS_KEYS if k != "exploration")

AXIS_NOUN = {
    "temperature": "palette temperature",
    "sport_couture": "style direction",
    "expression": "expression",
    "fit_language": "silhouette",
    "detail": "level of detail",
    "novelty": "design sensibility",
    "color": "palette",
    "finish": "finish",
    "structure": "shape",
    "setting": "setting",
    "utility": "balance of function and decoration",
}

PAIRS: Dict[str, FrozenSet[str]] = {
    "top": frozenset({"bottom", "outerwear", "shoes", "accessory"}),
    "bottom": frozenset({"top", "outerwear", "shoes", "accessory"}),
    "dress": frozenset({"outerwear", "shoes", "accessory"}),
    "outerwear": frozenset({"top", "bottom", "dress", "shoes"}),
    "shoes": frozenset({"top", "bottom", "dress", "outerwear"}),
    "accessory": frozenset({"top", "bottom", "dress", "outerwear"}),
}


@dataclass(frozen=True)
class Candidate:
    product_id: str
    title: str
    brand: str
    category: str
    color_family: str  # "neutral" | "color"
    axes: Mapping[str, int] = field(default_factory=dict)
    materials: Tuple[str, ...] = ()
    occasions: FrozenSet[str] = frozenset()
    price_minor: Optional[int] = None
    currency: Optional[str] = None
    available: bool = True
    visible: bool = True
    regions: Optional[FrozenSet[str]] = None  # None = no regional restriction
    sponsored: bool = False
    variant_group: Optional[str] = None
    source_label: str = ""


@dataclass(frozen=True)
class WardrobeRef:
    item_id: str
    title: str
    category: str
    color_family: str


@dataclass(frozen=True)
class RecommendationRequest:
    effective: Mapping[str, Optional[int]]
    effective_sources: Mapping[str, str] = field(default_factory=dict)
    occasion: Optional[str] = None
    budget_ceiling_minor: Optional[int] = None
    budget_currency: Optional[str] = None
    excluded_brands: FrozenSet[str] = frozenset()
    excluded_materials: FrozenSet[str] = frozenset()
    excluded_categories: FrozenSet[str] = frozenset()
    dismissed_products: FrozenSet[str] = frozenset()
    region: Optional[str] = None
    wardrobe: Sequence[WardrobeRef] = ()
    feedback_by_category: Mapping[str, Sequence[int]] = field(default_factory=dict)
    limit: int = 6


@dataclass
class Recommendation:
    product_id: str
    title: str
    score: float
    components: Dict[str, Dict[str, float]]
    reasons: List[Dict[str, object]]
    labels: List[str]
    sponsored: bool

    def to_dict(self) -> Dict[str, object]:
        return {
            "product_id": self.product_id,
            "title": self.title,
            "score": self.score,
            "components": self.components,
            "reasons": self.reasons,
            "labels": self.labels,
            "sponsored": self.sponsored,
        }


@dataclass
class RecommendationResult:
    rule_version: str
    basis: str
    items: List[Recommendation]
    excluded: Dict[str, int]
    exclusions_honored: Dict[str, object]

    def to_dict(self) -> Dict[str, object]:
        return {
            "rule_version": self.rule_version,
            "basis": self.basis,
            "weights": dict(WEIGHTS),
            "items": [i.to_dict() for i in self.items],
            "excluded": dict(self.excluded),
            "exclusions_honored": self.exclusions_honored,
        }


def _norm(s: str) -> str:
    return s.strip().casefold()


def _hard_filter(c: Candidate, req: RecommendationRequest) -> Optional[str]:
    if not c.visible:
        return "not_visible"
    if not c.available:
        return "unavailable"
    if c.product_id in req.dismissed_products:
        return "dismissed"
    if req.region and c.regions is not None and req.region not in c.regions:
        return "region"
    if _norm(c.category) in {_norm(x) for x in req.excluded_categories}:
        return "excluded_category"
    if _norm(c.brand) in {_norm(x) for x in req.excluded_brands}:
        return "excluded_brand"
    excluded_mats = {_norm(x) for x in req.excluded_materials}
    if any(_norm(m) in excluded_mats for m in c.materials):
        return "excluded_material"
    if req.budget_ceiling_minor is not None:
        if c.price_minor is None:
            return "price_unknown"
        if c.currency != req.budget_currency:
            return "currency_mismatch"
        if c.price_minor > req.budget_ceiling_minor:
            return "over_budget"
    return None


def _persona_similarity(c: Candidate, req: RecommendationRequest) -> Optional[Tuple[float, List[str]]]:
    diffs = []
    overlap = []
    for k in SIMILARITY_AXES:
        e = req.effective.get(k)
        cv = c.axes.get(k)
        if e is None or cv is None:
            continue
        diffs.append(abs(e - cv))
        overlap.append(k)
    if not diffs:
        return None
    return 1.0 - (sum(diffs) / len(diffs)) / 100.0, overlap


def _wardrobe_matches(c: Candidate, req: RecommendationRequest) -> Optional[List[WardrobeRef]]:
    if not req.wardrobe:
        return None
    partners = PAIRS.get(c.category, frozenset())
    return [
        w
        for w in sorted(req.wardrobe, key=lambda w: w.item_id)
        if w.category in partners and (w.color_family == "neutral" or c.color_family == "neutral")
    ]


def _money(minor: int, currency: str) -> str:
    # Display only. USD/EUR/GBP exponent 2; other currencies shown as minor units.
    if currency in ("USD", "EUR", "GBP", "CAD", "AUD"):
        sym = {"USD": "$", "EUR": "€", "GBP": "£", "CAD": "CA$", "AUD": "A$"}[currency]
        whole, frac = divmod(minor, 100)
        return f"{sym}{whole}" if frac == 0 else f"{sym}{whole}.{frac:02d}"
    return f"{minor} {currency} minor units"


def recommend(candidates: Sequence[Candidate], req: RecommendationRequest) -> RecommendationResult:
    excluded: Dict[str, int] = {}
    survivors: List[Candidate] = []
    for c in sorted(candidates, key=lambda c: c.product_id):
        why = _hard_filter(c, req)
        if why:
            excluded[why] = excluded.get(why, 0) + 1
        else:
            survivors.append(c)

    exploration = req.effective.get("exploration")
    scored: List[Recommendation] = []
    used_inferred = False
    used_any_persona = False

    for c in survivors:
        features: Dict[str, float] = {}
        evidence: Dict[str, object] = {}

        ps = _persona_similarity(c, req)
        if ps is not None:
            features["persona_similarity"], overlap = ps
            evidence["persona_similarity"] = overlap
            used_any_persona = True
            if any(req.effective_sources.get(k) == SRC_INFERRED for k in overlap):
                used_inferred = True

        if req.occasion and c.occasions:
            features["occasion_fit"] = 1.0 if req.occasion in c.occasions else 0.0
            evidence["occasion_fit"] = req.occasion

        matches = _wardrobe_matches(c, req)
        if matches is not None:
            features["wardrobe_compatibility"] = min(1.0, len(matches) / 3.0)
            evidence["wardrobe_compatibility"] = matches

        signals = req.feedback_by_category.get(c.category)
        if signals:
            mean = sum(signals) / len(signals)
            features["feedback_affinity"] = (max(-1.0, min(1.0, mean)) + 1.0) / 2.0
            evidence["feedback_affinity"] = c.category

        if exploration is not None and ps is not None:
            e = exploration / 100.0
            d = 1.0 - ps[0]
            features["exploration_diversity"] = e * d + (1.0 - e) * (1.0 - d)
            evidence["exploration_diversity"] = {"exploration": exploration, "distance": round(d, 4)}

        total_w = sum(WEIGHTS[f] for f in features)
        components: Dict[str, Dict[str, float]] = {}
        score = 0.0
        for f, v in features.items():
            w = WEIGHTS[f] / total_w
            components[f] = {"value": round(v, 4), "weight": round(w, 4), "contribution": round(w * v, 4)}
            score += w * v

        reasons = _reasons(c, req, components, evidence)
        labels = []
        if c.sponsored:
            labels.append("sponsored")
            reasons.append({"feature": "sponsorship", "text": "A sponsored placement", "contribution": 0.0, "evidence": []})
        if req.budget_ceiling_minor is not None and c.price_minor is not None:
            reasons.append(
                {
                    "feature": "hard_budget",
                    "text": f"Within your {_money(req.budget_ceiling_minor, req.budget_currency or '')} limit",
                    "contribution": 0.0,
                    "evidence": [f"price:{c.price_minor}:{c.currency}"],
                }
            )
        scored.append(
            Recommendation(
                product_id=c.product_id,
                title=c.title,
                score=round(score, 6),
                components=components,
                reasons=reasons,
                labels=labels,
                sponsored=c.sponsored,
            )
        )

    scored.sort(key=lambda r: (-r.score, r.product_id))
    by_id = {c.product_id: c for c in survivors}
    picked: List[Recommendation] = []
    cat_count: Dict[str, int] = {}
    brand_count: Dict[str, int] = {}
    groups = set()
    for r in scored:
        c = by_id[r.product_id]
        if cat_count.get(c.category, 0) >= MAX_PER_CATEGORY:
            continue
        if brand_count.get(_norm(c.brand), 0) >= MAX_PER_BRAND:
            continue
        if c.variant_group and c.variant_group in groups:
            continue
        picked.append(r)
        cat_count[c.category] = cat_count.get(c.category, 0) + 1
        brand_count[_norm(c.brand)] = brand_count.get(_norm(c.brand), 0) + 1
        if c.variant_group:
            groups.add(c.variant_group)
        if len(picked) >= req.limit:
            break

    basis = "learned_and_declared" if used_inferred else ("declared_choices" if used_any_persona else "neutral_start")
    return RecommendationResult(
        rule_version=RULE_VERSION,
        basis=basis,
        items=picked,
        excluded=excluded,
        exclusions_honored={
            "brands": sorted(req.excluded_brands),
            "materials": sorted(req.excluded_materials),
            "categories": sorted(req.excluded_categories),
            "budget_ceiling_minor": None if req.budget_ceiling_minor is None else str(req.budget_ceiling_minor),
            "budget_currency": req.budget_currency,
        },
    )


def _reasons(c: Candidate, req: RecommendationRequest, components, evidence) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for f, comp in sorted(components.items(), key=lambda kv: (-kv[1]["contribution"], kv[0])):
        if comp["value"] < REASON_THRESHOLD:
            continue
        text = None
        ev: List[str] = []
        if f == "persona_similarity":
            cited = []
            for k in evidence[f]:
                e = req.effective[k]
                if abs(e - 50) >= DECISIVE_DISTANCE and abs(e - c.axes[k]) <= MATCH_DISTANCE:
                    cited.append((abs(e - 50), k))
            cited.sort(key=lambda t: (-t[0], t[1]))
            if cited:
                k = cited[0][1]
                side = AXIS_LABELS[k][0] if req.effective[k] < 50 else AXIS_LABELS[k][1]
                text = f"Uses your preferred {side.lower()} {AXIS_NOUN[k]}"
                ev = [f"axis:{k}" for _, k in cited[:2]]
            else:
                text = "Close to the style you described"
                ev = [f"axis:{k}" for k in evidence[f]]
        elif f == "occasion_fit":
            text = f"Suits {evidence[f]}"
            ev = [f"occasion:{evidence[f]}"]
        elif f == "wardrobe_compatibility":
            matches = evidence[f]
            n = len(matches)
            names = ", ".join(m.title for m in matches[:2])
            text = f"Pairs with {n} thing{'s' if n != 1 else ''} in your closet ({names})"
            ev = [f"wardrobe_item:{m.item_id}" for m in matches]
        elif f == "feedback_affinity":
            text = f"You've shown interest in {evidence[f]} pieces"
            ev = [f"feedback_category:{evidence[f]}"]
        elif f == "exploration_diversity":
            info = evidence[f]
            if info["exploration"] >= 60 and info["distance"] >= 0.2:
                text = "A step beyond your usual picks, as you asked"
            else:
                text = "Close to what you already like"
            ev = [f"axis:exploration"]
        out.append({"feature": f, "text": text, "contribution": comp["contribution"], "evidence": ev})
        if len(out) >= 3:
            break
    if not out and not components:
        out.append(
            {
                "feature": "neutral_start",
                "text": "A neutral starting point — adjust your style to personalise this",
                "contribution": 0.0,
                "evidence": [],
            }
        )
    return out
