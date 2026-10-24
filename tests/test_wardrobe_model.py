"""Wardrobe intake rules, duplicate suggestions and order-unit reduction (pure)."""

import pytest

from brandme_core.domains.persona.kernel import ValidationFailed
from brandme_core.domains.wardrobe.model import (
    ExistingItem,
    can_merge,
    duplicate_candidates,
    order_unit_states,
    parse_intake,
    tag_serial_hash,
)

P = "a4036cb0-7ab2-54b5-9238-ee5ffb378771"


def test_catalog_save_defaults_to_want_and_never_ownership():
    i = parse_intake({"source": "catalog", "title": "Overshirt", "category": "top", "product_id": P, "variant_ref": "v-M"})
    assert (i.collection, i.claim_level, i.evidence_status) == ("want", "self_reported", "none")
    with pytest.raises(ValidationFailed):
        parse_intake({"source": "catalog", "title": "x", "category": "top"})  # catalog needs product_id


def test_manual_owned_is_self_reported_and_receipt_units_are_distinct():
    m = parse_intake({"source": "manual", "title": "Old denim", "category": "bottom"})
    assert (m.collection, m.claim_level) == ("owned", "self_reported")
    r = parse_intake({"source": "receipt", "title": "Tee", "category": "top", "receipt": {"receipt_ref": "R-77", "line_ref": "3", "units": 2}})
    assert r.units == 2 and r.receipt_line_ref == "R-77#3" and r.evidence_status == "receipt_pending_review"
    assert r.claim_level == "self_reported"  # receipt-backed only after review


@pytest.mark.parametrize(
    "extra",
    [{"claim_level": "issuer_attested"}, {"asset_instance_id": P}, {"member_id": P}, {"worn_count": 3}, {"acquisition_source": "order"}],
)
def test_factual_fields_cannot_be_supplied_at_intake(extra):
    with pytest.raises(ValidationFailed) as e:
        parse_intake({"source": "manual", "title": "x", "category": "top", **extra})
    assert list(extra)[0] in e.value.extra["rejected_fields"]


def test_no_invented_size_and_strict_validation():
    i = parse_intake({"source": "photo", "title": "x", "category": "top"})
    assert i.size_label is None
    for bad in ({"category": "hat"}, {"collection": "on_the_way"}, {"price": {"amount_minor": "12.5", "currency": "USD"}},
                {"receipt": {"receipt_ref": "r", "line_ref": "1"}}, {"source": "agent"}):
        with pytest.raises(ValidationFailed):
            parse_intake({"source": "manual", "title": "x", "category": "top", **bad})


def test_tag_serials_normalize_and_identify_one_unit():
    assert tag_serial_hash(" ab 12-cd ") == tag_serial_hash("AB12-CD")
    with pytest.raises(ValidationFailed):
        parse_intake({"source": "receipt", "title": "x", "category": "top", "tag_serial": "AB12CD",
                      "receipt": {"receipt_ref": "R", "line_ref": "1", "units": 2}})


def _e(i, **kw):
    base = dict(item_id=i, product_id=None, variant_ref=None, receipt_line_ref=None, unit_index=None, tag_serial_hash=None, collection="owned", duplicate_of=None)
    base.update(kw)
    return ExistingItem(**base)


def test_duplicates_are_suggestions_and_distinct_serials_never_merge():
    new = parse_intake({"source": "catalog", "title": "x", "category": "top", "product_id": P, "variant_ref": "v-M", "collection": "owned", "tag_serial": "SER-0002"})
    existing = [
        _e("a", product_id=P, variant_ref="v-M", tag_serial_hash=tag_serial_hash("SER-0001")),
        _e("b", product_id=P, variant_ref="v-M"),
        _e("c", product_id=P, variant_ref="v-M", collection="archive"),
    ]
    cands = {c.item_id: c for c in duplicate_candidates(new, existing)}
    assert set(cands) == {"a", "b"} and all(c.strength == "suggestion" for c in cands.values())
    assert cands["a"].mergeable is False and cands["b"].mergeable is True
    assert can_merge(_e("x", tag_serial_hash="1"), _e("y", tag_serial_hash="2")) == (False, "distinct_physical_instances")
    assert can_merge(_e("x", receipt_line_ref="R#1", unit_index=0), _e("y", receipt_line_ref="R#1", unit_index=1)) == (False, "distinct_receipt_units")
    assert can_merge(_e("x", product_id=P), _e("y", product_id=P)) == (True, "ok")


def test_order_units_partial_delivery_return_and_cancel():
    s = [(u.collection, u.acquisition_status) for u in order_unit_states(3, 2, 1, False)]
    assert s == [("archive", "returned"), ("owned", "delivered"), ("on_the_way", "ordered")]
    assert [u.collection for u in order_unit_states(2, 0, 0, True)] == ["archive", "archive"]
    assert [u.collection for u in order_unit_states(2, 5, 9, False)] == ["archive", "archive"]  # clamped, never negative
    with pytest.raises(ValidationFailed):
        order_unit_states(-1, 0, 0, False)
