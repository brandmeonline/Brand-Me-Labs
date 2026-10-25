"""Bounded purchase authority, approvals, budgets and reconciliation (W07 exit evidence).

Runs against the deterministic simulated provider. These prove application
behavior, not any live retailer relationship.
"""

import threading
from dataclasses import replace
from datetime import timedelta

import pytest

from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.domains.commerce.errors import (
    ApprovalInvalid, BudgetExceeded, CommerceError, DelegationInvalid, Forbidden, IdempotencyConflict,
    InvalidQuote, NotFound, QuoteExpired,
)
from brandme_core.domains.commerce.money import Money
from brandme_core.domains.providers.contracts import ProviderError
from brandme_core.domains.providers.local_atelier import Behavior
from brandme_core.domains.providers.registry import SimulationInProductionError
from tests.fixtures.commerce.stores import commerce_store, _spanner_db  # noqa: F401  (fixtures)
from tests.fixtures.commerce.harness import (
    OTHER_MEMBER, agent, limits, line, member_session, world,
)


@pytest.fixture
def w(commerce_store):
    return world(store=commerce_store)


def _events(w, event_type):
    return [e for e in w.store.outbox() if e.event_type == event_type]


# --------------------------------------------------------------- research/prepare
def test_research_mode_can_search_but_not_build_or_buy(w):  # BM-COM-001
    d, ag = w.delegate(AssistanceMode.RESEARCH)
    assert w.provider.search("linen").items  # research works
    with pytest.raises(Forbidden):
        w.svc.create_cart(ag, provider_id="demo_atelier", merchant_id="fictional-demo-merchant", lines=[line()])


def test_prepare_mode_builds_cart_and_requests_but_cannot_execute(w):
    d, ag = w.delegate(AssistanceMode.PREPARE)
    _, quote, op = w.prepared(ag)
    assert op.state == "awaiting_approval"
    approval = w.approve(op)
    with pytest.raises(Forbidden):  # no commerce:purchase scope in prepare mode
        w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="k1-0000000000000")
    assert w.provider.submit_calls == []
    assert approval.delegation_ref is None  # the member, not the agent, completes a prepared purchase
    done = w.svc.execute_purchase(w.member, operation_id=op.id, approval_id=approval.id, idempotency_key="k2-0000000000000")
    assert done.state == "accepted"


def test_agent_cannot_open_challenge_or_approve(w):
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    with pytest.raises(Forbidden):
        w.svc.open_approval_challenge(ag, op.id)
    ch = w.svc.open_approval_challenge(w.member, op.id)
    with pytest.raises(Forbidden):
        w.svc.approve(ag, operation_id=op.id, challenge_id=ch.id, nonce=ch.nonce, displayed_quote_hash=ch.quote_hash)


def test_cannot_purchase_without_valid_approval(w):  # BM-COM-006
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    for bogus in ("approved", "true", "00000000-0000-4000-8000-000000000000"):
        with pytest.raises(ApprovalInvalid):
            w.svc.execute_purchase(ag, operation_id=op.id, approval_id=bogus, idempotency_key="k-00000000000000" + bogus)
    assert w.provider.submit_calls == []
    assert w.store.rows("reservations") == []  # no spend reservation consumed


def test_approval_requires_reauthentication(w):
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    weak = member_session(aal="aal1")
    ch = w.svc.open_approval_challenge(weak, op.id)
    with pytest.raises(ApprovalInvalid) as e:
        w.svc.approve(weak, operation_id=op.id, challenge_id=ch.id, nonce=ch.nonce, displayed_quote_hash=ch.quote_hash)
    assert e.value.code == "reauthentication_required"


def test_wrong_nonce_and_reused_challenge_rejected(w):
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    ch = w.svc.open_approval_challenge(w.member, op.id)
    with pytest.raises(ApprovalInvalid):
        w.svc.approve(w.member, operation_id=op.id, challenge_id=ch.id, nonce="guess", displayed_quote_hash=ch.quote_hash)
    w.svc.approve(w.member, operation_id=op.id, challenge_id=ch.id, nonce=ch.nonce, displayed_quote_hash=ch.quote_hash)
    with pytest.raises(ApprovalInvalid):
        w.svc.approve(w.member, operation_id=op.id, challenge_id=ch.id, nonce=ch.nonce, displayed_quote_hash=ch.quote_hash)


# ------------------------------------------------------------------- happy path
def test_full_purchase_binds_exact_terms_and_emits_wardrobe_incoming(w):  # BM-COM-004
    d, ag = w.delegate()
    _, quote, op = w.prepared(ag, line("overshirt", "m"), line("trousers", "s"))
    approval = w.approve(op)
    assert approval.quote_hash == quote.quote_hash == quote.compute_hash()
    assert approval.allowed_total == quote.total and approval.merchant_id == quote.merchant_id
    assert approval.nonce and approval.expires_at == quote.expires_at
    assert approval.materiality_rule == "brandme.quote.material.v1"
    done = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="buy-1-0000000000")
    assert done.state == "accepted"
    order = w.svc.get_order(w.member, done.order_id)
    assert order.payment_status == "unknown"  # acceptance is not payment
    assert [l.quantity_ordered for l in order.lines] == [1, 1]
    ev = _events(w, "commerce.order.observed")[-1]
    assert ev.payload["wardrobe_effect"] == "incoming"
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000 - quote.total.amount_minor, "USD")


def test_duplicate_execute_with_same_key_returns_same_operation(w):
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    approval = w.approve(op)
    a = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="same-00000000000")
    b = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="same-00000000000")
    assert a.id == b.id and len(w.provider.submit_calls) == 1
    with pytest.raises(IdempotencyConflict):
        w.svc.execute_purchase(ag, operation_id="other", approval_id=approval.id, idempotency_key="same-00000000000")
    with pytest.raises(ApprovalInvalid):  # approval consumed once
        w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="different-000000")


# ---------------------------------------------------------- material term changes
def test_price_change_after_approval_requires_new_quote(w):  # BM-COM-005 + failure: price change
    d, ag = w.delegate()
    cart, quote, op = w.prepared(ag)
    old = w.approve(op)
    w.provider.arm(Behavior.PRICE_CHANGE, source_variant_ref="demo-overshirt-m", new_price_minor=9900)
    new_quote = w.svc.quote_cart(ag, cart.id)
    assert new_quote.quote_hash != quote.quote_hash
    new_op = w.svc.request_purchase(ag, new_quote.id)
    with pytest.raises(ApprovalInvalid):  # old approval cannot buy the new terms
        w.svc.execute_purchase(ag, operation_id=new_op.id, approval_id=old.id, idempotency_key="x1-0000000000000")
    # Executing the old operation reaches the provider, which authoritatively refuses the stale price.
    res = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=old.id, idempotency_key="x2-0000000000000")
    assert res.state == "rejected" and res.reason_code == "price_changed"
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000, "USD")  # released


def test_agent_cannot_mutate_approved_terms(w):
    d, ag = w.delegate()
    _, quote, op = w.prepared(ag)
    approval = w.approve(op)
    # Simulate any write path that alters the stored quote after approval.
    member, q = w.store.get("quotes", quote.id)
    w.store.run(lambda tx: tx.put("quotes", quote.id, (member, replace(q, lines=(replace(
        q.lines[0], quantity=2, line_total=q.lines[0].unit_price.times(2)),)))))
    with pytest.raises(ApprovalInvalid) as e:
        w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="m1-0000000000000")
    assert e.value.code == "quote_changed" and w.provider.submit_calls == []


def test_quote_change_between_render_and_approve_rejected(w):
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    ch = w.svc.open_approval_challenge(w.member, op.id)
    with pytest.raises(ApprovalInvalid):
        w.svc.approve(w.member, operation_id=op.id, challenge_id=ch.id, nonce=ch.nonce,
                      displayed_quote_hash="sha256:" + "0" * 64)


def test_expired_quote(w):  # failure: expired quote
    d, ag = w.delegate()
    w.provider.arm(Behavior.EXPIRED_QUOTE)
    cart = w.svc.create_cart(ag, provider_id="demo_atelier", merchant_id="fictional-demo-merchant", lines=[line()])
    quote = w.svc.quote_cart(ag, cart.id)
    w.clock.advance(seconds=2)
    with pytest.raises(QuoteExpired):
        w.svc.request_purchase(ag, quote.id)


def test_expiry_between_approval_and_execution(w):
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    approval = w.approve(op)
    w.clock.advance(minutes=11)
    with pytest.raises(ApprovalInvalid):
        w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="late-00000000000")
    assert w.provider.submit_calls == []


def test_stock_loss_blocks_quote_without_substitution(w):  # failure: stock loss
    d, ag = w.delegate()
    cart = w.svc.create_cart(ag, provider_id="demo_atelier", merchant_id="fictional-demo-merchant",
                             lines=[line("overshirt", "m"), line("dress", "s")])
    w.provider.arm(Behavior.STOCK_LOSS, source_variant_ref="demo-dress-s")
    with pytest.raises(InvalidQuote) as e:
        w.svc.quote_cart(ag, cart.id)
    assert e.value.code == "cart_not_quotable"


def test_stock_loss_after_approval_rejected_by_provider(w):
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    approval = w.approve(op)
    w.provider.arm(Behavior.STOCK_LOSS, source_variant_ref="demo-overshirt-m")
    res = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="s-00000000000000")
    assert res.state == "rejected" and res.reason_code == "out_of_stock"


def test_rejected_authorization(w):  # failure: rejected auth
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    approval = w.approve(op)
    w.provider.arm(Behavior.REJECTED_AUTH)
    res = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="r-00000000000000")
    assert res.state == "rejected" and res.reason_code == "payment_authorization_declined"
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000, "USD")


# ------------------------------------------------------------------ grant limits
def test_per_order_limit_is_all_in(w):
    d, ag = w.delegate(lim=limits(per_order=8_900))  # subtotal fits, all-in total (with tax) does not
    cart = w.svc.create_cart(ag, provider_id="demo_atelier", merchant_id="fictional-demo-merchant", lines=[line()])
    quote = w.svc.quote_cart(ag, cart.id)
    with pytest.raises(BudgetExceeded):
        w.svc.request_purchase(ag, quote.id)


def test_currency_change_requires_new_grant(w):
    lim = limits()
    lim = replace(lim, currency="EUR", max_per_order=Money(50_000, "EUR"), max_cumulative=Money(50_000, "EUR"))
    d, ag = w.delegate(lim=lim)
    cart = w.svc.create_cart(ag, provider_id="demo_atelier", merchant_id="fictional-demo-merchant", lines=[line()])
    quote = w.svc.quote_cart(ag, cart.id)
    with pytest.raises(DelegationInvalid) as e:
        w.svc.request_purchase(ag, quote.id)
    assert e.value.code == "currency_mismatch"


def test_autonomous_grant_is_refused(w):
    with pytest.raises(DelegationInvalid) as e:
        limits(require_final_human_approval=False)
    assert e.value.code == "autonomous_not_supported"


def test_agent_cannot_create_delegation(w):
    d, ag = w.delegate()
    with pytest.raises(Forbidden):
        w.svc.create_delegation(ag, client_id="x", mode=AssistanceMode.BUY_WITHIN_RULES,
                                allowed_providers={"demo_atelier"}, limits=limits(),
                                expires_at=w.clock.now + timedelta(days=1))


def test_two_agents_cannot_overspend_shared_budget(w):  # BM-COM-007
    # One grant, two agent sessions (same delegation), 20 concurrent executions.
    d, ag = w.delegate(lim=limits(per_order=20_000, cumulative=30_000))
    ops = []
    for i in range(20):
        sizes = ["s", "m", "l"]
        slug = ["overshirt", "trousers", "dress", "jacket", "sneaker", "bag"][i % 6]
        _, _, op = w.prepared(ag, line(slug, sizes[(i // 6) % 3]))
        ops.append((op, w.approve(op)))
    results, errors = [], []

    def run(op, approval, i):
        try:
            results.append(w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id,
                                                  idempotency_key=f"concurrent-{i:06d}"))
        except CommerceError as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(op, a, i)) for i, (op, a) in enumerate(ops)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    spent = sum(e.amount.amount_minor for e in w.store.rows("reservations") if e.state in ("reserved", "consumed"))
    assert spent <= 30_000
    assert any(isinstance(e, BudgetExceeded) for e in errors)
    accepted = [r for r in results if r.state == "accepted"]
    assert sum(w.svc.get_order(w.member, r.order_id).total.amount_minor for r in accepted) <= 30_000


# -------------------------------------------------------------------- revocation
def test_revocation_before_submission_cancels_without_side_effect(w):  # BM-COM-008
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    approval = w.approve(op)
    w.svc.revoke_delegation(w.member, d.id)
    assert w.svc.get_operation(w.member, op.id).state == "cancelled"
    with pytest.raises(DelegationInvalid):
        w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="rv-0000000000000")
    assert w.provider.submit_calls == []


def test_revocation_racing_submission_stops_unsent_work(w):
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    approval = w.approve(op)
    original = w.svc._submit

    def revoke_then_submit(op_, quote, principal, *rest):
        # Revocation lands after reservation commit but before provider I/O.
        w.store.run(lambda tx: tx.put("delegations", d.id, replace(tx.get("delegations", d.id),
                                                                    revoked_at=w.clock.now)))
        return original(op_, quote, principal, *rest)

    w.svc._submit = revoke_then_submit
    res = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="race-00000000000")
    assert res.state == "cancelled" and res.reason_code == "delegation_revoked"
    assert w.provider.submit_calls == []
    assert all(e.state == "released" for e in w.store.rows("reservations"))


def test_wrong_principal_gets_404_not_leak(w):
    d, ag = w.delegate()
    _, quote, op = w.prepared(ag)
    other = member_session(member=OTHER_MEMBER)
    with pytest.raises(NotFound):
        w.svc.get_operation(other, op.id)
    with pytest.raises(NotFound):
        w.svc.get_quote(other, quote.id)
    forged = agent(d.id, d.scopes, member=OTHER_MEMBER)
    with pytest.raises(DelegationInvalid):
        w.svc.request_purchase(forged, quote.id)


# ---------------------------------------------------------- unknown outcome
def test_timeout_after_accept_reconciles_to_one_order(w):  # BM-COM-009 + failure: timeout-after-accept
    d, ag = w.delegate()
    _, quote, op = w.prepared(ag)
    approval = w.approve(op)
    w.provider.arm(Behavior.TIMEOUT_AFTER_ACCEPT)
    res = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="t-00000000000000")
    assert res.state == "outcome_unknown"
    # Budget stays reserved while unknown; the same quote cannot be bought again.
    assert [e.state for e in w.store.rows("reservations")] == ["reserved"]
    op2 = w.svc.request_purchase(ag, quote.id)
    a2 = w.approve(op2)
    with pytest.raises(IdempotencyConflict) as e:
        w.svc.execute_purchase(ag, operation_id=op2.id, approval_id=a2.id, idempotency_key="t2-0000000000000")
    assert e.value.code == "purchase_in_progress"
    done = w.svc.reconcile(op.id)
    assert done.state == "accepted"
    assert len(w.store.rows("orders")) == 1
    assert len(w.provider.submit_calls) == 1  # never re-sent
    assert [e.state for e in w.store.rows("reservations")] == ["consumed"]
    assert w.svc.reconcile(op.id).state == "accepted"  # idempotent


@pytest.mark.parametrize("drafter", ["agent", "member"])
def test_two_approved_requests_for_one_quote_never_block_each_other(w, drafter):
    """Review finding: an approved but unsent sibling counted as in flight, so two approved requests for one
    quote (a retried request, say) each refused the other forever. The first to execute is placed; then the
    other is refused because the quote is bought, never because both are merely approved."""
    d, ag = w.delegate()
    actor = ag if drafter == "agent" else w.member
    _, quote, op1 = w.prepared(actor)
    op2 = w.svc.request_purchase(actor, quote.id)
    a1, a2 = w.approve(op1), w.approve(op2)
    done = w.svc.execute_purchase(w.member, operation_id=op2.id, approval_id=a2.id, idempotency_key="pair-00000000001")
    assert done.state == "accepted" and len(w.provider.submit_calls) == 1
    with pytest.raises(IdempotencyConflict) as e:
        w.svc.execute_purchase(actor, operation_id=op1.id, approval_id=a1.id, idempotency_key="pair-00000000002")
    assert e.value.code == "purchase_in_progress" and len(w.provider.submit_calls) == 1  # never bought twice


@pytest.mark.parametrize("later", ["cancel_requested", "partially_fulfilled", "fulfilled", "partially_refunded",
                                   "refunded", "disputed", "cancelled"])
def test_a_placed_order_never_frees_its_quote_for_an_approved_sibling(w, later):
    """Review finding: once the first order left 'accepted' (a lost cancel reply, a shipment, a refund), the
    second approved request passed and the quote was bought twice. A placed order holds its quote for good."""
    d, ag = w.delegate()
    _, quote, op1 = w.prepared(ag)
    op2 = w.svc.request_purchase(ag, quote.id)
    a1, a2 = w.approve(op1), w.approve(op2)
    w.svc.execute_purchase(ag, operation_id=op1.id, approval_id=a1.id, idempotency_key="held-00000000001")
    placed = w.store.get("operations", op1.id)
    w.store.run(lambda tx: tx.put("operations", op1.id, replace(placed, state=later, version=placed.version + 1)))
    with pytest.raises(IdempotencyConflict) as e:
        w.svc.execute_purchase(ag, operation_id=op2.id, approval_id=a2.id, idempotency_key="held-00000000002")
    assert e.value.code == "purchase_in_progress" and len(w.provider.submit_calls) == 1


def test_a_sibling_being_sent_blocks_the_other_approved_request(w, monkeypatch):
    d, ag = w.delegate()
    _, quote, op1 = w.prepared(ag)
    op2 = w.svc.request_purchase(ag, quote.id)
    a1, a2 = w.approve(op1), w.approve(op2)
    real, raced = w.provider.submit, []

    def submit_while_the_sibling_executes(request):
        with pytest.raises(IdempotencyConflict) as e:  # op1 is 'submitting' right now
            w.svc.execute_purchase(w.member, operation_id=op2.id, approval_id=a2.id, idempotency_key="sent-00000000002")
        raced.append(e.value.code)
        return real(request)

    monkeypatch.setattr(w.provider, "submit", submit_while_the_sibling_executes)
    done = w.svc.execute_purchase(ag, operation_id=op1.id, approval_id=a1.id, idempotency_key="sent-00000000001")
    assert done.state == "accepted" and raced == ["purchase_in_progress"] and len(w.provider.submit_calls) == 1


# ------------------------------------------------------------------ webhooks
def _accepted_order(w, *lines_):
    d, ag = w.delegate()
    _, _, op = w.prepared(ag, *(lines_ or [line()]))
    approval = w.approve(op)
    res = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="o-00000000000000" + op.id)
    return d, res, w.store.get("orders", res.order_id)


def test_duplicate_webhook_applied_once(w):  # failure: duplicate webhook
    _, op, order = _accepted_order(w)
    w.provider.arm(Behavior.DUPLICATE_WEBHOOK)
    deliveries = w.provider.capture(order.provider_order_ref)
    assert len(deliveries) == 2 and deliveries[0] == deliveries[1]
    before = len(w.store.outbox())
    r1 = w.svc.handle_webhook("demo_atelier", *deliveries[0])
    r2 = w.svc.handle_webhook("demo_atelier", *deliveries[1])
    assert r1.event_id == r2.event_id and len(w.store.rows("webhook_receipts")) == 1
    assert len(w.store.outbox()) == before + 1
    assert w.store.get("orders", order.id).payment_status == "captured"


def test_invalid_or_stale_webhook_signature_rejected(w):
    _, _, order = _accepted_order(w)
    headers, body = w.provider.capture(order.provider_order_ref)[0]
    with pytest.raises(ProviderError):
        w.svc.handle_webhook("demo_atelier", headers, body.replace(b"payment", b"pAyment"))
    w.clock.advance(minutes=6)
    with pytest.raises(ProviderError):
        w.svc.handle_webhook("demo_atelier", headers, body)


def test_partial_fulfillment_then_full(w):  # BM-COM-011 + failure: partial fulfillment
    _, op, order = _accepted_order(w, line("overshirt", "m", 2), line("trousers", "m", 1))
    w.provider.arm(Behavior.PARTIAL_FULFILLMENT, source_variant_ref="demo-overshirt-m", quantity=1)
    w.svc.handle_webhook("demo_atelier", *w.provider.ship(order.provider_order_ref)[0])
    o = w.store.get("orders", order.id)
    assert o.fulfillment_status == "partially_fulfilled"
    assert {l.source_variant_ref: l.quantity_delivered for l in o.lines} == {"demo-overshirt-m": 1, "demo-trousers-m": 1}
    assert w.store.get("operations", op.id).state == "partially_fulfilled"
    assert _events(w, "commerce.order.observed")[-1].payload["wardrobe_effect"] == "arrived"
    w.svc.handle_webhook("demo_atelier", *w.provider.ship(order.provider_order_ref)[0])
    o = w.store.get("orders", order.id)
    assert o.fulfillment_status == "fulfilled" and w.store.get("operations", op.id).state == "fulfilled"


def test_refund_before_delayed_fulfillment_keeps_facts_independent(w):  # BM-COM-010 + failure: refund
    d, op, order = _accepted_order(w, line("overshirt", "m", 1), line("bag", "m", 1))
    w.provider.capture(order.provider_order_ref)
    w.provider.ship(order.provider_order_ref, deliver=False)  # shipped, event delayed
    w.provider.arm(Behavior.REFUND, source_variant_ref="demo-bag-m", quantity=1)
    refund_events = w.provider.refund(order.provider_order_ref)
    w.svc.handle_webhook("demo_atelier", *refund_events[0])  # refund webhook arrives first
    o = w.store.get("orders", order.id)
    assert o.payment_status == "partially_refunded"
    assert o.fulfillment_status == "partially_fulfilled"  # source re-read shows shipment too
    assert o.refunded_total.amount_minor == 12900 + 1032
    bag = next(l for l in o.lines if l.source_variant_ref == "demo-bag-m")
    assert bag.quantity_returned == 1
    assert _events(w, "commerce.order.observed")[-1].payload["wardrobe_effect"] == "returned"


def test_refund_credit_back_follows_grant_policy(w):
    d, ag = w.delegate(lim=limits(refund_credit_back=True))
    _, _, op = w.prepared(ag)
    res = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=w.approve(op).id, idempotency_key="cb-0000000000000")
    order = w.store.get("orders", res.order_id)
    w.svc.handle_webhook("demo_atelier", *w.provider.ship(order.provider_order_ref)[0])  # captures
    w.provider.arm(Behavior.REFUND)
    w.svc.handle_webhook("demo_atelier", *w.provider.refund(order.provider_order_ref)[0])
    assert w.svc.available_budget(w.store.get("delegations", d.id)) == Money(50_000, "USD")
    assert w.store.get("orders", order.id).payment_status == "refunded"


def test_return_request_is_not_a_refund(w):
    _, op, order = _accepted_order(w)
    w.svc.handle_webhook("demo_atelier", *w.provider.ship(order.provider_order_ref)[0])
    out = w.svc.request_return(w.member, order.id, "demo-overshirt-m", 1)
    assert out["status"] == "return_requested"
    o = w.store.get("orders", order.id)
    assert o.payment_status != "refunded" and o.refunded_total.amount_minor == 0


def test_simulation_provider_refused_in_production():
    with pytest.raises(SimulationInProductionError):
        world("production")
    with pytest.raises(SimulationInProductionError):
        world("sandbox")


def test_unclassified_submit_error_becomes_unknown_then_reconciles(w):
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    approval = w.approve(op)
    real_submit = w.provider.submit

    def flaky(request):
        real_submit(request)  # provider accepted ...
        raise ConnectionResetError("socket closed")  # ... but our side lost the response

    w.provider.submit = flaky
    res = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="u1-0000000000000")
    assert res.state == "outcome_unknown"
    w.provider.submit = real_submit
    assert w.svc.reconcile(op.id).state == "accepted" and len(w.store.rows("orders")) == 1


def test_stale_submitting_after_crash_is_reconciled(w):
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    approval = w.approve(op)
    w.svc._submit = lambda *a, **k: (_ for _ in ()).throw(SystemExit("crash before provider I/O"))
    with pytest.raises(SystemExit):
        w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="crash-0000000000")
    assert w.svc.get_operation(w.member, op.id).state == "submitting"
    assert w.svc.reconcile(op.id).state == "submitting"  # not stale yet
    w.clock.advance(minutes=3)
    res = w.svc.reconcile(op.id)
    assert res.state == "rejected" and res.reason_code == "not_found_at_provider"
    assert all(e.state == "released" for e in w.store.rows("reservations"))


def test_exchange_keeps_history_and_tracks_the_replacement(w):  # BM-COM-011 exchange case
    _, op, order = _accepted_order(w, line("overshirt", "m", 1))
    w.svc.handle_webhook("demo_atelier", *w.provider.capture(order.provider_order_ref)[0])
    w.svc.handle_webhook("demo_atelier", *w.provider.ship(order.provider_order_ref)[0])
    assert w.store.get("orders", order.id).fulfillment_status == "fulfilled"
    w.svc.handle_webhook("demo_atelier", *w.provider.exchange(order.provider_order_ref, "demo-overshirt-m",
                                                              "demo-overshirt-l")[0])
    o = w.store.get("orders", order.id)
    by_ref = {l.source_variant_ref: l for l in o.lines}
    assert by_ref["demo-overshirt-m"].quantity_returned == 1 and by_ref["demo-overshirt-m"].quantity_delivered == 1
    replacement = by_ref["demo-overshirt-l"]
    assert replacement.exchanged_from_ref == "demo-overshirt-m" and replacement.quantity_ordered == 1
    assert replacement.variant_id == w.provider.variant_id_for("demo-overshirt-l")
    assert o.payment_status == "captured" and o.refunded_total.amount_minor == 0  # an exchange moves no money
    assert o.fulfillment_status == "partially_fulfilled"  # the replacement is not delivered yet
    ev = _events(w, "commerce.order.observed")[-1].payload
    assert ev["wardrobe_effect"] == "exchanged"
    assert {l["source_variant_ref"]: l["exchanged_from_ref"] for l in ev["lines"]} == {
        "demo-overshirt-m": None, "demo-overshirt-l": "demo-overshirt-m"}
    assert ev["acquisition_evidence"]  # every observation carries provider evidence refs
    w.svc.handle_webhook("demo_atelier", *w.provider.ship(order.provider_order_ref)[0])
    o = w.store.get("orders", order.id)
    assert o.fulfillment_status == "fulfilled"
    assert {l.source_variant_ref: l.quantity_delivered for l in o.lines} == {"demo-overshirt-m": 1, "demo-overshirt-l": 1}
    assert _events(w, "commerce.order.observed")[-1].payload["wardrobe_effect"] == "arrived"


def test_uneven_or_undelivered_exchange_is_refused_by_the_provider(w):
    _, op, order = _accepted_order(w, line("overshirt", "m", 1))
    with pytest.raises(ProviderError):  # nothing delivered yet
        w.provider.exchange(order.provider_order_ref, "demo-overshirt-m", "demo-overshirt-l")
    w.svc.handle_webhook("demo_atelier", *w.provider.ship(order.provider_order_ref)[0])
    with pytest.raises(ProviderError):  # different price: a return plus a new purchase
        w.provider.exchange(order.provider_order_ref, "demo-overshirt-m", "demo-trousers-m")


def test_summary_paths_pass_through_one_allowed_state_and_never_infer_a_dispute():
    from brandme_core.domains.commerce.records import transition_path
    assert transition_path("cancel_requested", "refunded", prefer=("cancelled",)) == ("cancelled", "refunded")
    assert transition_path("cancel_requested", "partially_refunded", prefer=("accepted",)) == (
        "accepted", "partially_refunded")  # a partial cancellation: the order goes on
    assert transition_path("accepted", "fulfilled") == ("fulfilled",)
    assert transition_path("refunded", "partially_refunded") is None  # not through "disputed"
    assert transition_path("fulfilled", "cancelled") is None
    assert transition_path("accepted", "accepted") == ()
