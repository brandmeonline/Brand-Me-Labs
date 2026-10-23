"""Commerce personal-data categories for My Data, export and deletion (ch.03 §8).

Registered with the foundation registry so ``/me/data`` can list them and the
privacy jobs can call ``export(database, member_id)`` / ``delete(database,
member_id)`` against the V007 tables. Deletion is idempotent and retains
financial evidence: orders, the approvals and grants behind them, and anything
still settling with a provider. The jobs run in category order (grants, then
carts/quotes, then orders), which is the order ``data_categories()`` returns.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable

from brandme_core.domains.base import DataCategory, register_data_category


def _service(database):
    from brandme_core.config import get_mode
    from brandme_core.domains.providers.registry import ProviderRegistry

    from .service import CommerceService
    from .spanner_store import SpannerCommerceStore

    env = get_mode().value  # no default: a privacy job must know which environment it runs in
    return CommerceService(store=SpannerCommerceStore(database), registry=ProviderRegistry(env), environment=env)


def _exporter(*tables: str) -> Callable[[Any, str], Iterable[Dict[str, Any]]]:
    def export(database, member_id: str) -> Iterable[Dict[str, Any]]:
        from .spanner_store import iter_member_rows
        return list(iter_member_rows(database, member_id, tables))
    return export


def _deleter(method: str) -> Callable[[Any, str], None]:
    def delete(database, member_id: str) -> None:
        getattr(_service(database), method)(member_id)
    return delete


AGENT_GRANTS = register_data_category(DataCategory(
    name="commerce.agent_grants",
    domain="commerce",
    description="Assistant delegations you granted: mode, providers, spending limits, expiry and revocation.",
    supplied_by="member",
    visible_to="member; the named client only while the grant is active",
    retention=("Deleting revokes every active grant and cancels its unsent work. A grant behind an order or a "
               "purchase still settling is kept, revoked, as evidence of who authorized it; others are erased "
               "with their budget ledger."),
    tables=("AgentDelegations", "DelegationBudgetEntries"),
    export=_exporter("AgentDelegations", "DelegationBudgetEntries"),
    delete=_deleter("erase_agent_grants"),
))

CARTS_AND_QUOTES = register_data_category(DataCategory(
    name="commerce.carts_quotes",
    domain="commerce",
    description="Carts and checkout quotes prepared by you or your assistant, and approval challenges.",
    supplied_by="member and assistant (cart lines); provider (quoted prices and terms)",
    visible_to="member",
    retention=("Deleting erases carts and approval challenges, cancels purchases not yet sent, and erases "
               "their quotes. A quote behind an order or a purchase still settling is kept with the order."),
    tables=("Carts", "CartLines", "CheckoutQuotes", "QuoteLines", "ApprovalChallenges"),
    export=_exporter("Carts", "CartLines", "CheckoutQuotes", "QuoteLines", "ApprovalChallenges"),
    delete=_deleter("erase_carts_and_quotes"),
))

ORDERS = register_data_category(DataCategory(
    name="commerce.orders",
    domain="commerce",
    description="Purchases you approved and the order, payment, fulfillment and return status observed from providers.",
    supplied_by="member (approvals, AP2 device keys); provider (order, payment and fulfillment facts)",
    visible_to="member",
    retention=("Orders, their approvals and return requests are kept as financial evidence for as long as the "
               "jurisdiction and provider agreement require; Brand.Me does not control merchant-held records. "
               "Deleting erases AP2 device keys, purchases that ended without an order, and idempotency keys "
               "that no longer guard a purchase in flight."),
    tables=("PurchaseOperations", "PurchaseApprovals", "MemberSurfaceKeys", "Orders", "OrderLines",
            "ReturnRequests", "CommerceIdempotencyKeys"),
    export=_exporter("PurchaseOperations", "PurchaseApprovals", "MemberSurfaceKeys", "Orders", "OrderLines",
                     "ReturnRequests"),
    delete=_deleter("erase_order_side_data"),
))
