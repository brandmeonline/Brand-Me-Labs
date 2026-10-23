"""S9: commerce My Data export and deletion (ch.03 §8).

Deletion is idempotent, revokes authority, cancels unsent work and keeps
financial evidence (orders, the approvals/grants behind them, purchases still
settling). Erasure runs on both stores; the registered ``DataCategory``
export/delete callables run against Spanner.
"""

import json

import pytest

from brandme_core.domains.base import data_categories
from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.domains.commerce.errors import DelegationInvalid
from brandme_core.domains.commerce.spanner_store import SpannerCommerceStore
from brandme_core.domains.providers.local_atelier import Behavior
from tests.fixtures.commerce.harness import MEMBER, OTHER_MEMBER, line, member_session, world
from tests.fixtures.commerce.stores import _spanner_db, commerce_store  # noqa: F401  (fixtures)


@pytest.fixture
def w(commerce_store):
    return world(store=commerce_store)


def _bought(w, ag, slug="overshirt"):
    _, quote, op = w.prepared(ag, line(slug))
    approval = w.approve(op)
    return quote, w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id,
                                         idempotency_key=f"privacy-{slug}-000000")


def _erase_all(w):
    w.svc.erase_agent_grants(MEMBER)
    w.svc.erase_carts_and_quotes(MEMBER)
    w.svc.erase_order_side_data(MEMBER)


def test_erasure_keeps_financial_evidence_and_drops_the_rest(w):
    from jwcrypto.jwk import JWK
    d, ag = w.delegate()
    quote, bought = _bought(w, ag)
    assert bought.state == "accepted"
    _, pending_quote, pending = w.prepared(ag, line("trousers"))  # awaiting approval, never sent
    w.svc.register_surface_key(w.member, JWK.generate(kty="EC", crv="P-256").export_public(as_dict=True))
    other_d = w.svc.create_delegation(member_session(member=OTHER_MEMBER), client_id="client-x",
                                      mode=AssistanceMode.RESEARCH, allowed_providers={"demo_atelier"}, limits=None,
                                      expires_at=w.clock.now.replace(year=2027))

    _erase_all(w)

    # Authority is gone: the grant is revoked and the agent can no longer act.
    with pytest.raises(DelegationInvalid):
        w.svc.bind(ag)
    kept = w.store.get("delegations", d.id)
    assert kept is not None and kept.revoked_at is not None  # behind an order: kept as evidence
    # Evidence retained.
    assert w.store.get("orders", bought.order_id) is not None
    assert w.store.get("quotes", quote.id) is not None
    assert w.store.get("approvals", w.store.get("operations", bought.id).approval_id) is not None
    # Everything else erased.
    assert w.store.get("operations", pending.id) is None
    assert w.store.get("quotes", pending_quote.id) is None
    assert [c for c in w.store.rows("carts") if c.member_id == MEMBER] == []
    assert [c for c in w.store.rows("challenges") if c.member_id == MEMBER] == []
    assert w.store.surface_keys(MEMBER) == []
    assert [r for r in w.store.rows("idempotency") if r.scope[0] == MEMBER] == []
    # Another member is untouched.
    assert w.store.get("delegations", other_d.id).revoked_at is None
    # Revocation is observable downstream.
    assert any(e.event_type == "commerce.delegation.revoked" and e.actor_ref == "system:privacy"
               for e in w.store.outbox())


def test_erasure_is_idempotent(w):
    d, ag = w.delegate(AssistanceMode.PREPARE)
    w.prepared(ag)
    _erase_all(w)
    first = (len(w.store.rows("delegations")), len(w.store.rows("operations")), len(w.store.rows("carts")))
    assert first == (0, 0, 0)  # nothing was purchased, so nothing is evidence
    _erase_all(w)
    assert (len(w.store.rows("delegations")), len(w.store.rows("operations")), len(w.store.rows("carts"))) == first


def test_in_flight_purchase_keeps_its_idempotency_key(w):
    d, ag = w.delegate()
    w.provider.arm(Behavior.TIMEOUT_AFTER_ACCEPT)
    _, res = _bought(w, ag)
    assert res.state == "outcome_unknown"
    _erase_all(w)
    # Still settling with the provider: operation, quote and its idempotency key stay.
    assert w.store.get("operations", res.id).state == "outcome_unknown"
    assert [r.result_ref for r in w.store.rows("idempotency")] == [res.id]
    assert w.svc.reconcile(res.id).state == "accepted"


# ------------------------------------------------- registered callables (Spanner)
@pytest.fixture
def spanner_world(_spanner_db, monkeypatch):
    from tests.fixtures.commerce.stores import wipe
    monkeypatch.setenv("BRANDME_MODE", "development")
    wipe(_spanner_db)
    return _spanner_db, world(store=SpannerCommerceStore(_spanner_db))


def test_data_category_export_and_delete_on_spanner(spanner_world):
    db, w = spanner_world
    d, ag = w.delegate()
    _, bought = _bought(w, ag)
    w.prepared(ag, line("dress"))
    cats = {c.name: c for c in data_categories() if c.domain == "commerce"}

    exported = {name: c.export(db, MEMBER) for name, c in cats.items()}
    json.dumps(exported)  # JSON-safe
    tables = {name: {r["table"] for r in rows} for name, rows in exported.items()}
    assert {"AgentDelegations", "DelegationBudgetEntries"} <= tables["commerce.agent_grants"]
    assert {"Carts", "CartLines", "CheckoutQuotes", "QuoteLines", "ApprovalChallenges"} <= tables["commerce.carts_quotes"]
    assert {"PurchaseOperations", "PurchaseApprovals", "Orders", "OrderLines"} <= tables["commerce.orders"]
    for rows in exported.values():
        assert all(r["row"].get("member_id", MEMBER) == MEMBER for r in rows)
        assert "nonce" not in {k for r in rows if r["table"] == "ApprovalChallenges" for k in r["row"]}
    assert OTHER_MEMBER not in json.dumps(exported)

    for c in sorted(cats.values(), key=lambda c: c.name):
        c.delete(db, MEMBER)
    for c in sorted(cats.values(), key=lambda c: c.name):
        c.delete(db, MEMBER)  # idempotent
    after = {name: {r["table"] for r in c.export(db, MEMBER)} for name, c in cats.items()}
    assert after["commerce.carts_quotes"] == {"CheckoutQuotes", "QuoteLines"}  # only the purchased quote
    assert {"Orders", "OrderLines", "PurchaseOperations", "PurchaseApprovals"} <= after["commerce.orders"]
    assert "MemberSurfaceKeys" not in after["commerce.orders"]
    assert w.store.get("orders", bought.order_id).member_id == MEMBER


def test_privacy_job_requires_an_explicit_mode(_spanner_db, monkeypatch):
    from brandme_core.config import ModeConfigurationError
    monkeypatch.delenv("BRANDME_MODE", raising=False)
    cat = next(c for c in data_categories() if c.name == "commerce.agent_grants")
    with pytest.raises(ModeConfigurationError):
        cat.delete(_spanner_db, MEMBER)
