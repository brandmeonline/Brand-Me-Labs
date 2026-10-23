"""Commerce My Data export and deletion (ch.03 §8) on main's privacy framework.

Deletion is idempotent, revokes authority, cancels unsent work and keeps
financial evidence (orders, the approvals/grants behind them, purchases still
settling). Erasure runs on both stores; the native ``CommercePrivacyHandler`` is
driven by the real ``MyDataService`` against the V009 tables on Spanner.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.domains.commerce.errors import DelegationInvalid, ProcessingRestricted
from brandme_core.domains.commerce.privacy_handler import AGENT_GRANTS, CARTS_QUOTES, HANDLER, ORDERS
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


# --------------------------------------------- My Data orchestrator (Spanner, V009 tables)
class _Objects:
    def __init__(self):
        self.objects = {}

    def put(self, key, data, content_type):
        self.objects[key] = data
        return f"mem://{key}"

    def delete(self, key):
        self.objects.pop(key, None)


def _real_now():
    return datetime.now(timezone.utc)  # MyDataService checks reauthentication against wall-clock time


@pytest.fixture
def my_data(_spanner_db, monkeypatch):
    from brandme_core.domains.privacy import PrivacyRegistry
    from brandme_core.domains.privacy.privacy import MyDataService
    from tests.fixtures.commerce.stores import wipe
    monkeypatch.setenv("BRANDME_MODE", "development")
    wipe(_spanner_db)
    reg = PrivacyRegistry()
    reg.register(HANDLER)
    w = world(store=SpannerCommerceStore(_spanner_db))
    return MyDataService(_spanner_db, _Objects(), reg, environment="development"), w


def test_commerce_registers_natively_with_my_data():
    import brandme_core.domains.commerce  # noqa: F401  (registers at package import)
    from brandme_core.domains import data_categories
    from brandme_core.domains.privacy import OnDelete, registry
    cats = {c.key: c for c in registry.categories() if c.domain == "commerce"}
    assert set(cats) == {AGENT_GRANTS, CARTS_QUOTES, ORDERS}
    assert all(registry.handler_for(k) is HANDLER for k in cats)
    assert cats[ORDERS].on_delete is OnDelete.RETAIN_LEGAL and "merchant" in cats[ORDERS].retention_basis
    # One registration path only: nothing for the foundation bridge to re-label as "erase".
    assert [c for c in data_categories() if c.domain == "commerce"] == []


def test_export_is_allowlisted_and_scoped_to_the_member(my_data):
    svc, w = my_data
    d, ag = w.delegate()
    _bought(w, ag)
    w.prepared(ag, line("dress"))
    w.svc.create_delegation(member_session(member=OTHER_MEMBER), client_id="client-x", mode=AssistanceMode.RESEARCH,
                            allowed_providers={"demo_atelier"}, limits=None, expires_at=w.clock.now.replace(year=2027))
    out = svc.export(MEMBER, _real_now())
    sections = out["package"]["categories"]
    kinds = {k: {r["type"] for r in v["records"]} for k, v in sections.items()}
    assert {"agent_grant", "budget_entry"} <= kinds[AGENT_GRANTS]
    assert {"cart", "cart_line", "quote", "quote_line", "approval_challenge"} <= kinds[CARTS_QUOTES]
    assert {"purchase", "approval", "order", "order_line"} <= kinds[ORDERS]
    text = json.dumps(out["package"], default=str)
    assert OTHER_MEMBER not in text
    for secret in ("nonce", "nonce_hash", "provider_idempotency_key", "idempotency_key", "checkout_reference",
                   "payee_ref", "provider_cart_ref", "material_document"):
        assert f'"{secret}"' not in text, secret
    assert sections[ORDERS]["notes"]  # truthful about the merchant's own copy


def test_export_shows_cancelled_units_on_order_lines(my_data):
    svc, w = my_data
    _, quote, op = w.prepared(w.member, line("overshirt"), line("bag"))
    res = w.svc.execute_purchase(w.member, operation_id=op.id, approval_id=w.approve(op).id,
                                 idempotency_key="privacy-cancel-buy-0001")
    order = w.store.get("orders", res.order_id)
    w.provider.arm(Behavior.PARTIAL_FULFILLMENT, source_variant_ref="demo-bag-m", quantity=0)
    for headers, body in w.provider.ship(order.provider_order_ref):  # the overshirt ships, the bag does not
        w.svc.handle_webhook("demo_atelier", headers, body)
    out = w.svc.request_cancellation(w.member, order.id, idempotency_key="privacy-cancel-key-0001")
    assert (out["status"], out["units_cancelled"]) == ("partially_cancelled", 1)
    records = svc.export(MEMBER, _real_now())["package"]["categories"][ORDERS]["records"]
    lines = {r["source_variant_ref"]: r for r in records if r["type"] == "order_line"}
    # Same facts as the order page: the bag was cancelled, not still owed.
    assert {ref: (r["quantity_ordered"], r["quantity_shipped"], r["quantity_cancelled"])
            for ref, r in lines.items()} == {"demo-overshirt-m": (1, 1, 0), "demo-bag-m": (1, 0, 1)}


def test_category_deletion_receipt_is_truthful_and_self_contained(my_data):
    svc, w = my_data
    d, ag = w.delegate()
    quote, bought = _bought(w, ag)
    _, open_quote, open_op = w.prepared(ag, line("trousers"))  # awaiting approval, never sent
    # Orders first, alone: it must cancel the open purchase itself, not rely on another category.
    receipt = svc.run_deletion(svc.request_deletion(MEMBER, _real_now(), [ORDERS]))
    assert receipt["categories"][ORDERS]["status"] == "retained"
    assert w.store.get("orders", bought.order_id) is not None
    assert w.store.get("operations", open_op.id) is None  # cancelled, then erased (no order behind it)
    job = svc.request_deletion(MEMBER, _real_now(), [AGENT_GRANTS, CARTS_QUOTES])
    receipt = svc.run_deletion(job)
    assert receipt["categories"][AGENT_GRANTS]["status"] == "exception"  # kept, revoked, behind the order
    assert "evidence" in receipt["categories"][AGENT_GRANTS]["reason"]
    assert receipt["categories"][CARTS_QUOTES]["status"] == "exception"  # the purchased quote stays
    assert w.store.get("quotes", quote.id) is not None and w.store.get("quotes", open_quote.id) is None
    assert w.store.get("delegations", d.id).revoked_at is not None
    with pytest.raises(DelegationInvalid):
        w.svc.bind(ag)
    # The revocation event committed in the orchestrator's transaction.
    assert any(e.event_type == "commerce.delegation.revoked" and e.actor_ref == "system:privacy"
               for e in w.store.outbox())
    assert svc.run_deletion(job) == receipt  # replay-safe


def test_purchase_still_settling_keeps_the_deletion_open(my_data):
    svc, w = my_data
    d, ag = w.delegate()
    w.provider.arm(Behavior.TIMEOUT_AFTER_ACCEPT)
    _, res = _bought(w, ag)
    assert res.state == "outcome_unknown"
    job = svc.request_deletion(MEMBER, _real_now(), [AGENT_GRANTS, ORDERS])
    receipt = svc.run_deletion(job)
    assert receipt["completed_at"] is None
    assert {receipt["categories"][k]["status"] for k in (AGENT_GRANTS, ORDERS)} == {"pending_records"}
    # Settlement is not blocked by the deletion freeze: it records what the provider did with money.
    assert w.svc.reconcile(res.id).state == "accepted"
    receipt = svc.run_deletion(job)
    assert receipt["completed_at"] is not None
    assert receipt["categories"][ORDERS]["status"] == "retained"
    assert receipt["categories"][AGENT_GRANTS]["status"] == "exception"


def test_member_and_agent_writes_are_refused_while_deletion_is_pending(my_data):
    svc, w = my_data
    d, ag = w.delegate(AssistanceMode.PREPARE)
    cart, _, _ = w.prepared(ag)
    svc.request_deletion(MEMBER, _real_now(), [CARTS_QUOTES])  # accepted, not yet run
    with pytest.raises(ProcessingRestricted):
        w.svc.create_cart(ag, provider_id="demo_atelier", merchant_id=cart.merchant_id, lines=[line("bag")])
    with pytest.raises(ProcessingRestricted):
        w.svc.quote_cart(ag, cart.id)
    # Other categories stay writable: this is not an account deletion. Revocation is always allowed.
    w.svc.revoke_delegation(w.member, d.id)
    w.svc.create_delegation(w.member, client_id="client-other", mode=AssistanceMode.RESEARCH,
                            allowed_providers={"demo_atelier"}, limits=None, expires_at=w.clock.now + timedelta(days=1))


def test_account_deletion_freezes_every_commerce_write(my_data):
    """Grant and cart writes here; every money path (request, approve, AP2, execute, return, cancel),
    on both stores, in tests/test_commerce_privacy_freeze.py."""
    svc, w = my_data
    svc.request_deletion(MEMBER, _real_now())  # whole account
    with pytest.raises(ProcessingRestricted):
        w.svc.create_delegation(w.member, client_id="client-x", mode=AssistanceMode.RESEARCH,
                                allowed_providers={"demo_atelier"}, limits=None,
                                expires_at=w.clock.now + timedelta(days=1))
    with pytest.raises(ProcessingRestricted):
        w.svc.create_cart(w.member, provider_id="demo_atelier", merchant_id="fictional-demo-merchant",
                          lines=[line()])


def test_queued_assistant_work_cannot_recreate_deleted_data(my_data):
    from brandme_core.domains.commerce.service import processing_basis
    svc, w = my_data
    d, ag = w.delegate(AssistanceMode.PREPARE)
    started = _real_now()  # an assistant task read its inputs here...
    svc.run_deletion(svc.request_deletion(MEMBER, _real_now(), [CARTS_QUOTES]))  # ...then the member deleted
    with processing_basis(started), pytest.raises(ProcessingRestricted):
        w.svc.create_cart(ag, provider_id="demo_atelier", merchant_id="fictional-demo-merchant", lines=[line()])


def test_privacy_job_requires_an_explicit_mode(my_data, monkeypatch):
    from brandme_core.config import ModeConfigurationError
    svc, _ = my_data
    job = svc.request_deletion(MEMBER, _real_now(), [AGENT_GRANTS])
    monkeypatch.delenv("BRANDME_MODE", raising=False)
    with pytest.raises(ModeConfigurationError):
        svc.run_deletion(job)


def test_in_memory_store_honours_the_processing_guard():
    from brandme_core.domains.commerce.store import InMemoryCommerceStore
    w = world(store=InMemoryCommerceStore())
    d, ag = w.delegate(AssistanceMode.PREPARE)
    w.store.freeze(MEMBER, CARTS_QUOTES)
    with pytest.raises(ProcessingRestricted):
        w.svc.create_cart(ag, provider_id="demo_atelier", merchant_id="fictional-demo-merchant", lines=[line()])
    w.store.unfreeze(MEMBER, CARTS_QUOTES)
    w.svc.create_cart(ag, provider_id="demo_atelier", merchant_id="fictional-demo-merchant", lines=[line()])
