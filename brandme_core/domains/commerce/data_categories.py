"""Commerce personal-data categories for My Data, export and deletion (ch.03 §8).

Registered with the foundation registry so ``/me/data`` can list them. The
``export``/``delete`` callables are attached by the Spanner store (S9), which
owns the V007 tables; until then the inventory is truthful but the jobs are
not wired, and the status file says so.
"""

from __future__ import annotations

from brandme_core.domains.base import DataCategory, register_data_category

AGENT_GRANTS = register_data_category(DataCategory(
    name="commerce.agent_grants",
    domain="commerce",
    description="Assistant delegations you granted: mode, providers, spending limits, expiry and revocation.",
    supplied_by="member",
    visible_to="member; the named client only while the grant is active",
    retention="Kept while active and through the reconciliation horizon of any purchase made under it.",
    tables=("AgentDelegations", "DelegationBudgetEntries"),
))

CARTS_AND_QUOTES = register_data_category(DataCategory(
    name="commerce.carts_quotes",
    domain="commerce",
    description="Carts and checkout quotes prepared by you or your assistant, and approval challenges.",
    supplied_by="member and assistant (cart lines); provider (quoted prices and terms)",
    visible_to="member",
    retention="Unpurchased carts and quotes are deleted on request; a quote behind an order follows the order.",
    tables=("Carts", "CartLines", "CheckoutQuotes", "QuoteLines", "ApprovalChallenges"),
))

ORDERS = register_data_category(DataCategory(
    name="commerce.orders",
    domain="commerce",
    description="Purchases you approved and the order, payment, fulfillment and return status observed from providers.",
    supplied_by="member (approvals, AP2 device keys); provider (order, payment and fulfillment facts)",
    visible_to="member",
    retention=("Financial and contract evidence is kept as long as the jurisdiction and provider agreement "
               "require; deletion removes the member link where allowed. Merchant-held records are outside "
               "Brand.Me's control."),
    tables=("PurchaseOperations", "PurchaseApprovals", "MemberSurfaceKeys", "Ap2UsedMandates", "Orders",
            "OrderLines", "ReturnRequests", "CommerceIdempotencyKeys"),
))
