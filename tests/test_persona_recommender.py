"""Deterministic recommender: works with no AI key, honours hard constraints,
and every reason maps to a feature that actually contributed to the score."""

import json
import os
import random
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from brandme_core.domains.persona.model import AXIS_KEYS, SRC_DECLARED
from brandme_core.domains.persona.recommender import (
    WEIGHTS,
    Candidate,
    RecommendationRequest,
    WardrobeRef,
    recommend,
)

FIXTURE = Path(__file__).parent / "fixtures" / "persona" / "catalog_candidates.json"
DEMO = Path(__file__).resolve().parents[1] / "docs/design/brandme/contracts/demo-scenario.json"


def load_candidates():
    out = []
    for c in json.loads(FIXTURE.read_text())["candidates"]:
        out.append(
            Candidate(
                product_id=c["product_id"],
                title=c["title"],
                brand=c["brand"],
                category=c["category"],
                color_family=c["color_family"],
                axes=c["axes"],
                materials=tuple(c["materials"]),
                occasions=frozenset(c["occasions"]),
                price_minor=c["price_minor"],
                currency=c["currency"],
                available=c.get("available", True),
                sponsored=c.get("sponsored", False),
            )
        )
    return out


def alex_effective():
    declared = json.loads(DEMO.read_text())["initial_declared_axes"]
    return {k: declared[k] for k in AXIS_KEYS}


def req(**kw):
    eff = kw.pop("effective", alex_effective())
    return RecommendationRequest(effective=eff, effective_sources={k: SRC_DECLARED for k in eff}, **kw)


def test_runs_with_no_ai_key_in_a_clean_process():
    """BM-ONB-007: import and rank in a subprocess with every model key removed."""
    env = {k: v for k, v in os.environ.items() if not any(s in k for s in ("ANTHROPIC", "OPENAI", "GEMINI", "VERTEX", "API_KEY"))}
    code = (
        "import sys; sys.path.insert(0, '.');"
        "from brandme_core.domains.persona.recommender import recommend, RecommendationRequest, Candidate;"
        "r = recommend([Candidate('p1','T','B','top','neutral',{'expression':70})], RecommendationRequest(effective={'expression':72}));"
        "assert r.items and r.rule_version == 'det-rec-v1'; print('ok')"
    )
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, "-c", code], cwd=root, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"


def test_deterministic_and_input_order_invariant():
    cands = load_candidates()
    a = recommend(cands, req(occasion="work")).to_dict()
    shuffled = cands[:]
    random.Random(7).shuffle(shuffled)
    b = recommend(shuffled, req(occasion="work")).to_dict()
    assert a == b


def test_hard_budget_and_exclusions_are_never_violated():
    """BM-PER-010."""
    r = recommend(
        load_candidates(),
        req(budget_ceiling_minor=15000, budget_currency="USD", excluded_materials=frozenset({"Leather"}), excluded_brands=frozenset({"demo outfitters"})),
    )
    ids = {i.product_id for i in r.items}
    by_id = {c.product_id: c for c in load_candidates()}
    for pid in ids:
        c = by_id[pid]
        assert c.currency == "USD" and c.price_minor <= 15000
        assert "leather" not in c.materials
        assert c.brand != "Demo Outfitters"
    assert r.excluded["excluded_material"] >= 1 and r.excluded["excluded_brand"] >= 1
    budget_only = recommend(load_candidates(), req(budget_ceiling_minor=15000, budget_currency="USD"))
    assert budget_only.excluded == {"over_budget": 3, "currency_mismatch": 1, "price_unknown": 1, "unavailable": 1}
    assert "0f6f5c1e-7b9a-5d2c-9d1e-0a1b2c3d4e01" not in ids  # sponsored cannot bypass the budget
    for item in r.items:
        assert any(x["feature"] == "hard_budget" and x["text"] == "Within your $150 limit" for x in item.reasons)


def test_reasons_reference_actual_scoring_evidence():
    wardrobe = [
        WardrobeRef("w-trousers", "Cream trousers", "bottom", "neutral"),
        WardrobeRef("w-sneaker", "White sneakers", "shoes", "neutral"),
    ]
    r = recommend(load_candidates(), req(wardrobe=wardrobe, occasion="work"))
    assert r.items
    wardrobe_ids = {w.item_id for w in wardrobe}
    eff = alex_effective()
    for item in r.items:
        total_weight = sum(c["weight"] for c in item.components.values())
        assert total_weight == pytest.approx(1.0, abs=1e-3)  # renormalised over present features
        assert item.score == pytest.approx(sum(c["contribution"] for c in item.components.values()), abs=1e-3)
        for reason in item.reasons:
            f = reason["feature"]
            if f in ("hard_budget", "sponsorship", "neutral_start"):
                continue
            assert f in item.components, "reason cites a feature that did not score"
            assert item.components[f]["value"] >= 0.5
            assert reason["contribution"] == item.components[f]["contribution"]
            if f == "wardrobe_compatibility":
                cited = {e.split(":", 1)[1] for e in reason["evidence"]}
                assert cited and cited <= wardrobe_ids
            if f == "persona_similarity" and reason["text"].startswith("Uses your preferred"):
                for e in reason["evidence"]:
                    k = e.split(":", 1)[1]
                    assert abs(eff[k] - 50) >= 15
    top = r.items[0]
    assert top.reasons[0]["contribution"] == max(c["contribution"] for c in top.components.values()) or top.reasons[0]["feature"] in top.components


def test_no_wardrobe_means_no_wardrobe_reason():
    r = recommend(load_candidates(), req())
    for item in r.items:
        assert "wardrobe_compatibility" not in item.components
        assert all(x["feature"] != "wardrobe_compatibility" for x in item.reasons)


def test_neutral_start_is_honest():
    """BM-ONB-003: 'None of these' -> no fabricated confidence."""
    r = recommend(load_candidates(), RecommendationRequest(effective={k: None for k in AXIS_KEYS}))
    assert r.basis == "neutral_start"
    for item in r.items:
        assert item.components == {}
        assert [x["feature"] for x in item.reasons] in (["neutral_start"], ["neutral_start", "sponsorship"])


def test_sponsorship_is_labelled_and_never_boosts_score():
    cands = load_candidates()
    knit = next(c for c in cands if c.sponsored)
    plain = replace(knit, sponsored=False)
    s1 = recommend([knit], req()).items[0]
    s2 = recommend([plain], req()).items[0]
    assert s1.score == s2.score
    assert "sponsored" in s1.labels and not s2.labels


def test_diversity_caps():
    base = load_candidates()[0]
    many = [replace(base, product_id=f"00000000-0000-0000-0000-00000000000{i}", brand=f"B{i}") for i in range(5)]
    r = recommend(many, req())
    assert len(r.items) == 2  # max two per category


def test_declared_preference_changes_ranking():
    cands = load_candidates()
    low = alex_effective() | {"expression": 10, "sport_couture": 10, "structure": 30}
    high = alex_effective() | {"expression": 90, "sport_couture": 90, "structure": 90}
    a = [i.product_id for i in recommend(cands, req(effective=low)).items]
    b = [i.product_id for i in recommend(cands, req(effective=high)).items]
    assert a != b
