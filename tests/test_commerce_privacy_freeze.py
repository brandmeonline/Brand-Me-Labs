"""The My Data processing guard on every member and agent money path (ch.03 §8).

While a deletion of the member's data in a category is pending, each write that
category guards is refused inside its own transaction, before any provider I/O, and
leaves no trace: no provider call, no budget row, no state change, no event. Every
case runs on the in-memory store (``freeze``) and on Spanner, where the freeze is a
deletion request accepted by the real ``MyDataService`` (V009 tables).
"""

import pytest
from jwcrypto.jwk import JWK

from brandme_core.domains.commerce.errors import ProcessingRestricted
from brandme_core.domains.commerce.privacy_handler import CARTS_QUOTES, ORDERS
from brandme_core.domains.commerce.store import InMemoryCommerceStore
from brandme_core.domains.providers.contracts import ProviderError, ProviderErrorKind
from brandme_core.domains.providers.local_atelier import MERCHANT_ID, PROVIDER_ID
from tests.fixtures.commerce.harness import MEMBER, line, world
from tests.fixtures.commerce.stores import _spanner_db  # noqa: F401  (fixture)
from tests.test_commerce_privacy import _real_now, my_data  # noqa: F401  (fixture)

ACCOUNT = None  # the whole account


@pytest.fixture(params=["memory", "spanner"])
def fw(request):
    """(world, freeze): ``freeze(category)`` makes a deletion of that category (or the account) pending."""
    if request.param == "memory":
        w = world(store=InMemoryCommerceStore())
        return w, lambda category: w.store.freeze(MEMBER, category or "*")
    svc, w = request.getfixturevalue("my_data")
    return w, lambda category: svc.request_deletion(MEMBER, _real_now(), [category] if category else None)


def _trace(w):
    """Everything a refused write must leave untouched."""
    rows = lambda table: w.store.rows(table)  # noqa: E731
    return {
        "provider": (len(w.provider.submit_calls), len(w.provider.return_calls), len(w.provider._cancellations)),
        "operations": sorted((o.id, o.state, o.version) for o in rows("operations")),
        "approvals": sorted((a.id, a.state) for a in rows("approvals")),
        "budget": sorted((e.id, e.kind, e.state) for e in rows("reservations")),
        "orders": sorted((o.id, o.order_status, o.payment_status, o.version) for o in rows("orders")),
        "returns": sorted(r.id for r in rows("returns")),
        "challenges": sorted((c.id, c.used) for c in rows("challenges")),
        "idempotency": len(rows("idempotency")),
        "surface_keys": len(rows("surface_keys")),
        "events": len(w.store.outbox()),
    }


def _actor(w, who):
    return w.member if who == "member" else w.delegate()[1]


def _quoted(w, actor):
    cart = w.svc.create_cart(actor, provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID, lines=[line()])
    return w.svc.quote_cart(actor, cart.id)


def _bought(w, actor, ship=False):
    _, _, op = w.prepared(actor)
    res = w.svc.execute_purchase(actor, operation_id=op.id, approval_id=w.approve(op).id,
                                 idempotency_key="freeze-guard-buy-0001")
    order = w.store.get("orders", res.order_id)
    if ship:
        for headers, body in w.provider.ship(order.provider_order_ref):
            w.svc.handle_webhook(PROVIDER_ID, headers, body)
    return order


# Each arrange step runs before the freeze and returns the guarded write to attempt after it.
def _request(w, who):
    actor = _actor(w, who)
    quote = _quoted(w, actor)
    return lambda: w.svc.request_purchase(actor, quote.id)


def _challenge(w, who):
    _, _, op = w.prepared(_actor(w, who))
    return lambda: w.svc.open_approval_challenge(w.member, op.id)


def _approve(w, who):
    _, _, op = w.prepared(_actor(w, who))
    ch = w.svc.open_approval_challenge(w.member, op.id)
    return lambda: w.svc.approve(w.member, operation_id=op.id, challenge_id=ch.id, nonce=ch.nonce,
                                 displayed_quote_hash=ch.quote_hash)


def _approve_ap2(w, who):
    from tests.fixtures.commerce.ap2_issuer import closed_checkout_mandate, closed_payment_mandate, merchant_checkout_jwt
    actor = _actor(w, who)
    _, quote, op = w.prepared(actor)
    user = JWK.generate(kty="EC", crv="P-256")
    w.svc.register_surface_key(w.member, user.export_public(as_dict=True))
    cjwt = merchant_checkout_jwt(w.provider, quote)
    now, exp = int(w.clock.now.timestamp()), int(quote.expires_at.timestamp())
    cm = closed_checkout_mandate(user, cjwt, iat=now, exp=exp)
    pm = closed_payment_mandate(user, cjwt, quote, iat=now, exp=exp)
    return lambda: w.svc.approve_with_ap2(actor, operation_id=op.id, checkout_mandate=cm, payment_mandate=pm)


def _register_key(w, who):
    public = JWK.generate(kty="EC", crv="P-256").export_public(as_dict=True)
    return lambda: w.svc.register_surface_key(w.member, public)


def _execute(w, who):
    actor = _actor(w, who)
    _, _, op = w.prepared(actor)
    approval = w.approve(op)
    return lambda: w.svc.execute_purchase(actor, operation_id=op.id, approval_id=approval.id,
                                          idempotency_key="freeze-guard-exec-001")


def _return(w, who):
    actor = _actor(w, who)
    order = _bought(w, actor, ship=True)
    return lambda: w.svc.request_return(actor, order.id, "demo-overshirt-m", 1,
                                        idempotency_key="freeze-guard-return-1")


def _cancel(w, who):
    actor = _actor(w, who)
    order = _bought(w, actor)
    return lambda: w.svc.request_cancellation(actor, order.id, idempotency_key="freeze-guard-cancel-1")


CASES = [
    ("purchase.request", _request, ("member", "agent"), ORDERS),
    ("approval.challenge", _challenge, ("member", "agent"), CARTS_QUOTES),
    ("approve", _approve, ("member", "agent"), ORDERS),
    ("approve.ap2", _approve_ap2, ("agent",), ORDERS),
    ("surface_key.register", _register_key, ("member",), ORDERS),
    ("purchase.execute", _execute, ("member", "agent"), ORDERS),
    ("order.return", _return, ("member", "agent"), ORDERS),
    ("order.cancel", _cancel, ("member", "agent"), ORDERS),
]
PARAMS = [pytest.param(arrange, who, category, id=f"{name}-{who}")
          for name, arrange, whos, category in CASES for who in whos]


@pytest.mark.parametrize("arrange,who,category", PARAMS)
def test_a_pending_category_deletion_refuses_the_money_path(fw, arrange, who, category):
    w, freeze = fw
    act = arrange(w, who)
    freeze(category)
    before = _trace(w)
    with pytest.raises(ProcessingRestricted):
        act()
    assert _trace(w) == before


@pytest.mark.parametrize("arrange,who,category", PARAMS)
def test_a_pending_account_deletion_refuses_the_money_path(fw, arrange, who, category):
    w, freeze = fw
    act = arrange(w, who)
    freeze(ACCOUNT)
    before = _trace(w)
    with pytest.raises(ProcessingRestricted):
        act()
    assert _trace(w) == before


@pytest.mark.parametrize("who", ["member", "agent"])
def test_a_retried_cancellation_is_not_re_sent_while_deletion_is_pending(fw, who, monkeypatch):
    w, freeze = fw
    actor = _actor(w, who)
    order = _bought(w, actor)
    real = w.provider.request_cancellation

    def lost(ref, *, idempotency_key):  # the merchant cancels; the answer never arrives
        real(ref, idempotency_key=idempotency_key)
        raise ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN, "response lost", transmitted=True)
    monkeypatch.setattr(w.provider, "request_cancellation", lost)
    with pytest.raises(ProviderError):
        w.svc.request_cancellation(actor, order.id, idempotency_key="freeze-guard-cancel-1")
    freeze(ORDERS)
    before = _trace(w)
    with pytest.raises(ProcessingRestricted):
        w.svc.request_cancellation(actor, order.id, idempotency_key="freeze-guard-cancel-1")
    assert _trace(w) == before

