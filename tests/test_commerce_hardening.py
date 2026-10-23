"""Regression tests for defects found by an independent review of the round-2 diff.

Each test names the failure it pins down. All run on the in-memory store and on Spanner.
"""

from dataclasses import replace
from datetime import timedelta

import pytest

from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.domains.commerce.errors import ApprovalInvalid, Forbidden, InvalidQuote
from brandme_core.domains.commerce.money import Money
from brandme_core.domains.providers.local_atelier import MERCHANT_ID, PROVIDER_ID, Behavior
from tests.fixtures.commerce.harness import AGENT_CLIENT, agent, line, member_session, world
from tests.fixtures.commerce.stores import _spanner_db, commerce_store  # noqa: F401  (fixtures)


@pytest.fixture
def w(commerce_store):
    return world(store=commerce_store)


def _buy(w, actor, *lines_, key="harden-buy-00000001"):
    _, quote, op = w.prepared(actor, *(lines_ or [line()]))
    approval = w.approve(op)
    return quote, w.svc.execute_purchase(actor, operation_id=op.id, approval_id=approval.id, idempotency_key=key)


# ---------------------------------------------------------- approved terms are what is bought
def test_cart_edited_after_approval_is_never_bought(w):
    d, ag = w.delegate(AssistanceMode.PREPARE)
    cart, quote, op = w.prepared(ag, line("overshirt", "m"))
    approval = w.approve(op)
    w.svc.update_cart(ag, cart.id, if_match=cart.revision, lines=[line("overshirt", "l")])
    with pytest.raises(ApprovalInvalid) as e:
        w.svc.execute_purchase(w.member, operation_id=op.id, approval_id=approval.id,
                               idempotency_key="harden-swap-0000001")
    assert e.value.code == "quote_changed" and w.provider.submit_calls == []


def test_provider_cart_changed_behind_our_back_is_refused_at_checkout(w):
    d, ag = w.delegate()
    cart, quote, op = w.prepared(ag, line("overshirt", "m"))
    approval = w.approve(op)
    w.provider.replace_cart(cart.provider_cart_ref, [line("overshirt", "l")])  # outside Brand.Me entirely
    res = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id,
                                 idempotency_key="harden-race-0000001")
    assert res.state == "rejected" and res.reason_code == "checkout_changed"
    assert w.store.rows("orders") == [] and w.provider._orders == {}
    assert all(e.state == "released" for e in w.store.rows("reservations"))


# ------------------------------------------------------------- grant limits on cart and return
def test_agent_cannot_touch_carts_it_did_not_build_or_outside_its_grant(w):
    member_cart = w.svc.create_cart(w.member, provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID, lines=[line()])
    d, ag = w.delegate(AssistanceMode.PREPARE)
    for fn in (lambda: w.svc.update_cart(ag, member_cart.id, if_match=1, lines=[line("trousers")]),
               lambda: w.svc.quote_cart(ag, member_cart.id)):
        with pytest.raises(Forbidden) as e:
            fn()
        assert e.value.code == "cart_not_yours"
    own = w.svc.create_cart(ag, provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID, lines=[line()])
    w.svc.revoke_delegation(w.member, d.id)
    narrow = w.svc.create_delegation(w.member, client_id=AGENT_CLIENT, mode=AssistanceMode.PREPARE,
                                     allowed_providers={"some_other_provider"}, limits=None,
                                     expires_at=w.clock.now + timedelta(days=1))
    with pytest.raises(Forbidden):  # the grant no longer covers this provider
        w.svc.quote_cart(agent(None, narrow.scopes), own.id)


def test_returns_need_purchase_authority_over_that_order(w):
    d, ag = w.delegate()
    _, own = _buy(w, ag)
    _, members = _buy(w, w.member, line("trousers"), key="harden-buy-00000002")
    w.svc.revoke_delegation(w.member, d.id)
    prep = w.svc.create_delegation(w.member, client_id="client-prep-agent", mode=AssistanceMode.PREPARE,
                                   allowed_providers={PROVIDER_ID}, limits=None,
                                   expires_at=w.clock.now + timedelta(days=1))
    with pytest.raises(Forbidden):  # prepare grants have no commerce:purchase
        w.svc.request_return(agent(None, prep.scopes, client="client-prep-agent"), own.order_id,
                             "demo-overshirt-m", 1)
    d2, ag2 = w.delegate()
    with pytest.raises(Forbidden) as e:  # a buy grant cannot return what it did not buy
        w.svc.request_return(ag2, members.order_id, "demo-trousers-m", 1)
    assert e.value.code == "order_not_yours"
    assert w.svc.request_return(w.member, members.order_id, "demo-trousers-m", 1)["status"] == "return_requested"


def test_return_requests_are_idempotent_and_counted_until_received(w):
    _, res = _buy(w, w.member)
    order = w.store.get("orders", res.order_id)
    w.svc.handle_webhook(PROVIDER_ID, *w.provider.ship(order.provider_order_ref)[0])
    first = [w.svc.request_return(w.member, order.id, "demo-overshirt-m", 1, idempotency_key="harden-ret-00000001")
             for _ in range(3)]
    assert len({r["return_id"] for r in first}) == 1
    assert len(w.provider.return_calls) == 1 and len(w.store.rows("returns")) == 1
    with pytest.raises(InvalidQuote):  # the only unit is already being returned
        w.svc.request_return(w.member, order.id, "demo-overshirt-m", 1, idempotency_key="harden-ret-00000002")
    w.provider.arm(Behavior.REFUND)
    w.svc.handle_webhook(PROVIDER_ID, *w.provider.refund(order.provider_order_ref)[0])
    assert [r.status for r in w.store.rows("returns")] == ["received"]


# ------------------------------------------------------------- execution and approval edges
def test_member_buys_its_approved_purchase_after_drafting_grant_expires(w):
    d, ag = w.delegate(AssistanceMode.PREPARE)
    _, _, op = w.prepared(ag)
    approval = w.approve(op)
    assert approval.delegation_ref is None  # the member, not the prepare agent, executes
    # The drafting grant expires while the quote is still fresh.
    w.clock.advance(minutes=1)
    w.store.run(lambda tx: tx.put("delegations", d.id, replace(tx.get("delegations", d.id), expires_at=w.clock.now)))
    res = w.svc.execute_purchase(w.member, operation_id=op.id, approval_id=approval.id,
                                 idempotency_key="harden-mine-0000001")
    assert res.state == "accepted"


def test_an_operation_cannot_be_approved_twice(w):
    _, _, op = w.prepared(w.member)
    a = w.svc.open_approval_challenge(w.member, op.id)
    b = w.svc.open_approval_challenge(w.member, op.id)
    w.svc.approve(w.member, operation_id=op.id, challenge_id=a.id, nonce=a.nonce, displayed_quote_hash=a.quote_hash)
    with pytest.raises(ApprovalInvalid):
        w.svc.approve(w.member, operation_id=op.id, challenge_id=b.id, nonce=b.nonce, displayed_quote_hash=b.quote_hash)
    assert len(w.store.rows("approvals")) == 1


def test_unchanged_multi_line_observation_emits_nothing(w):
    _, res = _buy(w, w.member, line("trousers"), line("bag"))
    order = w.store.get("orders", res.order_id)
    w.svc._apply_observation(order.id, w.provider.lookup(order.provider_order_ref), "system:reconciler")
    settled = w.store.get("orders", order.id)  # payment unknown -> authorized: one real change
    before = len([e for e in w.store.outbox() if e.event_type == "commerce.order.observed"])
    for _ in range(2):
        w.svc._apply_observation(order.id, w.provider.lookup(order.provider_order_ref), "system:reconciler")
    after = len([e for e in w.store.outbox() if e.event_type == "commerce.order.observed"])
    assert after == before and w.store.get("orders", order.id).version == settled.version


def test_zero_amount_reservation_writes_no_ledger_row(w):
    d, _ = w.delegate()
    w.store.run(lambda tx: w.svc._reserve_budget(tx, d, "op-zero", Money(0, "USD")))
    assert w.store.rows("reservations") == []


def test_surface_key_can_be_registered_again(w):
    from jwcrypto.jwk import JWK
    pub = JWK.generate(kty="EC", crv="P-256").export_public(as_dict=True)
    assert w.svc.register_surface_key(w.member, pub) == w.svc.register_surface_key(w.member, pub)
    assert len(w.store.surface_keys(w.member.member_id)) == 1


def test_refused_exchange_moves_no_stock(w):
    _, res = _buy(w, w.member, line("overshirt", "m"), line("overshirt", "l"))
    order = w.store.get("orders", res.order_id)
    w.provider.ship(order.provider_order_ref)
    stock = dict(w.provider._stock)
    from brandme_core.domains.providers.contracts import ProviderError
    with pytest.raises(ProviderError):
        w.provider.exchange(order.provider_order_ref, "demo-overshirt-m", "demo-overshirt-l")
    assert w.provider._stock == stock


# ------------------------------------------------------------------ assistant task access
def test_agent_without_the_tasks_grant_cannot_read_or_cancel_it():
    from brandme_core.mcp.authz import ExecutorAssertionVerifier
    from brandme_core.mcp.tools import McpToolExecutor
    from brandme_core.orchestrator import AssistantRuntime, DeterministicPlanner
    w = world()
    d, ag = w.delegate(AssistanceMode.RESEARCH)
    rt = AssistantRuntime(McpToolExecutor(commerce=w.svc, registry=w.registry, verifier=ExecutorAssertionVerifier(
        gateway_issuer="gw", keys={}, environment="development")), environment="development")
    task = rt.run(ag, rt.create(ag, "linen", AssistanceMode.RESEARCH).id, DeterministicPlanner())
    stranger = agent(None, {"commerce:research"}, client="client-without-grant")
    for fn in (lambda: rt.events_after(stranger, task.id, None), lambda: rt.cancel(stranger, task.id)):
        with pytest.raises(KeyError):
            fn()
    other = w.svc.create_delegation(w.member, client_id="client-other", mode=AssistanceMode.RESEARCH,
                                    allowed_providers={PROVIDER_ID}, limits=None,
                                    expires_at=w.clock.now + timedelta(days=1))
    with pytest.raises(KeyError):  # a different grant of the same member
        rt.events_after(agent(None, other.scopes, client="client-other"), task.id, None)
    assert rt.events_after(member_session(), task.id, None)  # the member sees their own task
    w.svc.revoke_delegation(w.member, d.id)
    with pytest.raises(KeyError):  # revoked: the agent loses access
        rt.events_after(ag, task.id, None)
    assert rt.events_after(member_session(), task.id, None)
