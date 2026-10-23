"""Commerce registration with the My Data framework (ch.03 §8; ``brandme_core.domains.privacy``).

A native ``DomainPrivacyHandler``: the privacy orchestrator passes its own
snapshot to ``export`` and its own read/write transaction to ``delete``, so the
deletion of commerce rows, the tombstone and commerce's own events commit
together. Each category's deletion is self-contained (categories run in request
order, and restores replay tombstones in any order).

Receipts are truthful. Financial evidence is retained: orders (``commerce.orders``
is ``retain_legal``), and the grant and quote behind an order (reported as an
exception of their ``erase`` category). A purchase still settling with a provider
keeps its rows and reports ``done=False``, so the deletion job stays open and the
freeze stays on until it settles, exactly like rights' pending broadcasts.
"""

from __future__ import annotations

from typing import Any, Dict, List

from google.cloud.spanner_v1 import param_types as pt

from brandme_core.domains.privacy.deletion import (
    DataCategory, DeletionOutcome, ExportSection, OnDelete, PrivacyRegistry, SubjectContext, Supplier, Tombstone,
    register_domain,
)

AGENT_GRANTS = "commerce.agent_grants"
CARTS_QUOTES = "commerce.carts_quotes"
ORDERS = "commerce.orders"

ORDERS_RETENTION_BASIS = (
    "Orders, the approvals behind them and return requests are financial records kept for tax, payment-dispute "
    "and consumer-protection obligations for as long as the jurisdiction and provider agreement require. "
    "Brand.Me does not control the merchant's own copy of the order.")

# Exported columns per table: allowlisted, never SELECT *. Excluded on purpose: approval nonces and
# nonce hashes (anti-replay material), provider idempotency keys, provider cart/checkout references,
# payee references and the canonical material document (internal; the quote hash identifies it).
_EXPORT_SQL: Dict[str, Dict[str, str]] = {
    AGENT_GRANTS: {
        "agent_grant": """SELECT delegation_id, client_id, mode, scopes, allowed_providers, limits, created_at,
            expires_at, revoked_at FROM AgentDelegations WHERE member_id = @s ORDER BY created_at""",
        "budget_entry": """SELECT e.delegation_id, e.operation_id, e.kind, e.state, e.amount_minor, e.currency,
            e.created_at FROM DelegationBudgetEntries e JOIN AgentDelegations d ON e.delegation_id = d.delegation_id
            WHERE d.member_id = @s ORDER BY e.created_at""",
    },
    CARTS_QUOTES: {
        "cart": """SELECT cart_id, provider_id, merchant_id, revision, status, created_by_client, created_at,
            updated_at FROM Carts WHERE member_id = @s ORDER BY created_at""",
        "cart_line": """SELECT l.cart_id, l.source_variant_ref, l.quantity FROM CartLines l
            JOIN Carts c ON l.cart_id = c.cart_id WHERE c.member_id = @s""",
        "quote": """SELECT quote_id, provider_id, merchant_id, cart_id, currency, subtotal_minor, tax_minor,
            shipping_minor, discount_minor, total_minor, terms, quote_hash, issued_at, expires_at
            FROM CheckoutQuotes WHERE member_id = @s ORDER BY issued_at""",
        "quote_line": """SELECT l.quote_id, l.source_variant_ref, l.quantity, l.unit_price_minor, l.line_total_minor,
            l.category FROM QuoteLines l JOIN CheckoutQuotes q ON l.quote_id = q.quote_id WHERE q.member_id = @s""",
        "approval_challenge": """SELECT challenge_id, operation_id, quote_id, issued_at, expires_at, used
            FROM ApprovalChallenges WHERE member_id = @s ORDER BY issued_at""",
    },
    ORDERS: {
        "purchase": """SELECT operation_id, client_id, quote_id, quote_hash, provider_id, state, order_id,
            reason_code, created_at, updated_at FROM PurchaseOperations WHERE member_id = @s ORDER BY created_at""",
        "approval": """SELECT approval_id, quote_id, quote_hash, merchant_id, allowed_total_minor, currency, method,
            assurance_level, state, issued_at, expires_at FROM PurchaseApprovals WHERE member_id = @s
            ORDER BY issued_at""",
        "signing_key": """SELECT key_thumbprint, registered_at, revoked_at FROM MemberSurfaceKeys
            WHERE member_id = @s ORDER BY registered_at""",
        "order": """SELECT order_id, operation_id, provider_id, merchant_id, provider_order_ref, order_status,
            payment_status, fulfillment_status, currency, total_minor, refunded_minor, last_observed_at, created_at
            FROM Orders WHERE member_id = @s ORDER BY created_at""",
        "order_line": """SELECT l.order_id, l.source_variant_ref, l.quantity_ordered, l.quantity_shipped,
            l.quantity_delivered, l.quantity_returned, l.exchanged_from_ref FROM OrderLines l
            JOIN Orders o ON l.order_id = o.order_id WHERE o.member_id = @s""",
        "return_request": """SELECT return_id, order_id, source_variant_ref, quantity, provider_reference, status,
            requested_at FROM ReturnRequests WHERE member_id = @s ORDER BY requested_at""",
    },
}

_NOTES = {
    ORDERS: ["The merchant keeps its own record of each order; use provider_order_ref when contacting them."],
}


def _service():
    """A commerce service for the privacy job's environment; its store is unused (deletion runs in ``txn``)."""
    from brandme_core.config import get_mode
    from brandme_core.domains.providers.registry import ProviderRegistry

    from .service import CommerceService

    env = get_mode().value  # no default: a privacy job must know which environment it runs in
    return CommerceService(store=None, registry=ProviderRegistry(env), environment=env)


class CommercePrivacyHandler:
    domain = "commerce"

    def categories(self) -> List[DataCategory]:
        return [
            DataCategory(
                AGENT_GRANTS, "commerce", "Assistant permissions you granted", Supplier.MEMBER,
                ("member", "client:while_active"),
                "Until you revoke or delete them; a grant behind an order is kept, revoked, as evidence of who "
                "authorized it", "Revoke or replace the grant; an assistant can never widen it", OnDelete.ERASE),
            DataCategory(
                CARTS_QUOTES, "commerce", "Carts, checkout quotes and approval prompts", Supplier.MEMBER, ("member",),
                "Until deleted; a quote behind an order is kept with the order",
                "Carts are edited by replacing their lines; quotes are never edited, only re-quoted",
                OnDelete.ERASE),
            DataCategory(
                ORDERS, "commerce", "Purchases, orders, payment, fulfillment and returns", Supplier.PROVIDER,
                ("member",), "For as long as the financial record must be kept",
                "Order facts come from the provider and cannot be edited", OnDelete.RETAIN_LEGAL,
                retention_basis=ORDERS_RETENTION_BASIS),
        ]

    # ------------------------------------------------------------------ export
    def export(self, snapshot: Any, ctx: SubjectContext, category: str) -> ExportSection:
        from .spanner_store import _plain

        records: List[Dict[str, Any]] = []
        for kind, sql in _EXPORT_SQL[category].items():
            result = snapshot.execute_sql(sql, params={"s": ctx.subject_ref}, param_types={"s": pt.STRING})
            rows = list(result)
            names = [f.name for f in result.fields]
            records.extend({"type": kind, **{n: _plain(v) for n, v in zip(names, r)}} for r in rows)
        return ExportSection(category, records, notes=list(_NOTES.get(category, [])))

    # ------------------------------------------------------------------ delete
    def delete(self, txn: Any, ctx: SubjectContext, category: str) -> DeletionOutcome:
        from .spanner_store import SpannerCommerceStore

        svc = _service()
        erase = {AGENT_GRANTS: svc._erase_agent_grants, CARTS_QUOTES: svc._erase_carts_and_quotes,
                 ORDERS: svc._erase_order_side_data}[category]
        counts = SpannerCommerceStore.within(txn, lambda tx: erase(tx, ctx.subject_ref))
        return outcome_for(category, counts)

    def purge_derived(self, ctx: SubjectContext, category: str) -> DeletionOutcome:
        return DeletionOutcome(category, 0)  # commerce keeps no projections, caches or media

    def reapply_tombstone(self, txn: Any, tombstone: Tombstone) -> int:
        outcome = self.delete(txn, SubjectContext(tombstone.subject_ref, tombstone.deletion_job_id,
                                                  tombstone.created_at), tombstone.category)
        if not outcome.done:
            raise RuntimeError("commerce purchases are still settling; reconcile them before restore can serve data")
        return outcome.rows_affected


def outcome_for(category: str, counts: Dict[str, int]) -> DeletionOutcome:
    """Map erasure counts to a truthful outcome. ``settling`` keeps the job open; ``kept`` is permanent."""
    rows = sum(v for k, v in counts.items() if k not in ("kept", "settling", "retained"))
    settling, kept = counts.get("settling", 0), counts.get("kept", 0)
    detail = (f"{settling} purchase(s) are still settling with a provider; their records are removed or kept "
              "once the provider's outcome is known") if settling else None
    if category == ORDERS:
        retained = counts.get("retained", 0)
        if not detail and retained:
            detail = f"{retained} order(s) retained as financial records"
        return DeletionOutcome(category, rows, done=not settling, detail=detail)
    what = "grant(s) kept, revoked," if category == AGENT_GRANTS else "quote(s) kept"
    exception = f"{kept} {what} as evidence of an order" if kept else None
    return DeletionOutcome(category, rows, done=not settling, exception=exception, detail=detail)


HANDLER = CommercePrivacyHandler()


def register(reg: PrivacyRegistry | None = None) -> None:
    """Register into ``reg`` (the process-wide registry by default); repeating it is a no-op."""
    register_domain(HANDLER, reg)
