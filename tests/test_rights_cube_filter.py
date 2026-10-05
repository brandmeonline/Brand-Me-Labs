"""Field-level passport filtering applied by brandme-cube after face-level policy."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "passport_filter", Path(__file__).resolve().parents[1] / "brandme-cube/src/passport_filter.py")
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)


def test_nested_owner_references_removed_for_non_owner():
    data = {"brand": "X", "current_owner_id": "u1",
            "provenance": [{"event": "sold", "owner_id": "u0", "purchase_price": 120}],
            "ownership": {"ownership_history": ["u0", "u1"], "transfer_count": 2}}
    out = pf.filter_face_data(data, viewer_is_owner=False)
    assert out == {"brand": "X", "provenance": [{"event": "sold"}], "ownership": {"transfer_count": 2}}
    assert pf.filter_face_data(data, viewer_is_owner=True) == data


def test_fabricated_chain_refs_are_never_displayed():
    assert pf.chain_ref_for_display("cardano_tx_0123456789abcdef") is None
    assert pf.chain_ref_for_display("simulated_cardano_1700000000_abcd") is None
    assert pf.chain_ref_for_display("encrypted_" + "a" * 64) is None
    assert pf.chain_ref_for_display(None) is None
    real = "ab" * 32
    assert pf.chain_ref_for_display(real) == real
