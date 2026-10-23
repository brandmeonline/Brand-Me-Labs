"""Cloud Spanner implementation of the commerce store (V006/V007 tables).

``run(fn)`` wraps ``database.run_in_transaction``. Each attempt gets a fresh
``_SpannerTx``: reads go through the transaction (so they take Spanner's
read locks and serialize conflicting writers), writes are buffered mutations
plus an in-transaction overlay so ``fn`` reads its own writes, and emitted
events are written with foundation ``write_events`` in the same commit. A
retried attempt starts over with an empty overlay and no events, so only the
committed attempt's rows and events exist.

Named queries are SQL over the V007 indexes; their results are merged with the
overlay using the same predicates the in-memory store uses (``store.QUERIES``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, TypeVar

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject, KeyRange, KeySet, param_types

from brandme_core.domains.providers.contracts import CartLineRequest
from brandme_core.events import EventEnvelope, write_events

from .delegation import AgentDelegation, AssistanceMode, DelegationLimits
from .errors import QuoteExpired
from .money import Money
from .quote import QUOTE_HASH_VERSION, CheckoutQuote, CheckoutTerms, QuoteLine
from .records import (
    ApprovalChallenge, BudgetEntry, Cart, IdempotencyRecord, Order, OrderLine, PurchaseApproval,
    PurchaseOperation, ReturnRequest, WebhookReceipt,
)
from .store import QUERIES, QueryMixin

T = TypeVar("T")
_MISSING = object()


def _json(value: Any) -> Dict[str, Any]:
    if value is None:
        return None  # type: ignore[return-value]
    if isinstance(value, dict):
        return dict(value)
    return json.loads(value.serialize() if hasattr(value, "serialize") else str(value))


def _param_type(value: Any):
    if isinstance(value, bool):
        return param_types.BOOL
    if isinstance(value, int):
        return param_types.INT64
    if isinstance(value, datetime):
        return param_types.TIMESTAMP
    return param_types.STRING


def _key_list(key: Any) -> list:
    return list(key) if isinstance(key, tuple) else [key]


# ------------------------------------------------------------------ codecs
@dataclass(frozen=True)
class _Codec:
    """Maps one logical table to its Spanner table(s)."""
    table: str
    pk: Tuple[str, ...]
    load: Callable[[Any, Any], Any]          # (reader, key) -> row | None
    save: Callable[[Any, Any, Any, bool], None]  # (transaction, key, row, exists)


def _read_one(reader, table: str, columns: Sequence[str], key: Any) -> Optional[Dict[str, Any]]:
    rows = list(reader.read(table, columns=columns, keyset=KeySet(keys=[_key_list(key)])))
    return dict(zip(columns, rows[0])) if rows else None


def _read_children(reader, table: str, columns: Sequence[str], parent_key: str) -> List[Dict[str, Any]]:
    ks = KeySet(ranges=[KeyRange(start_closed=[parent_key], end_closed=[parent_key])])
    return [dict(zip(columns, r)) for r in reader.read(table, columns=columns, keyset=ks)]


def _replace_children(tx, table: str, columns: Sequence[str], parent_key: str, values: list) -> None:
    tx.delete(table, KeySet(ranges=[KeyRange(start_closed=[parent_key], end_closed=[parent_key])]))
    if values:
        tx.insert(table, columns=columns, values=values)


def _write(tx, table: str, exists: bool, row: Dict[str, Any], insert_only: Sequence[str] = ()) -> None:
    if exists:
        cols = [c for c in row if c not in insert_only]
        tx.update(table, columns=cols, values=[[row[c] for c in cols]])
    else:
        cols = list(row)
        tx.insert(table, columns=cols, values=[[row[c] for c in cols]])


# carts --------------------------------------------------------------------
_CART_COLS = ("cart_id", "member_id", "provider_id", "merchant_id", "provider_cart_ref", "revision", "status",
              "created_by_client")
_CART_LINE_COLS = ("cart_id", "variant_id", "source_variant_ref", "quantity")


def _load_cart(r, key):
    row = _read_one(r, "Carts", _CART_COLS, key)
    if row is None:
        return None
    lines = tuple(CartLineRequest(l["variant_id"], l["source_variant_ref"], l["quantity"])
                  for l in _read_children(r, "CartLines", _CART_LINE_COLS, key))
    return Cart(id=row["cart_id"], member_id=row["member_id"], provider_id=row["provider_id"],
                merchant_id=row["merchant_id"], provider_cart_ref=row["provider_cart_ref"], lines=lines,
                revision=row["revision"], created_by_client=row["created_by_client"], status=row["status"])


def _save_cart(tx, key, c: Cart, exists):
    _write(tx, "Carts", exists, {
        "cart_id": c.id, "member_id": c.member_id, "provider_id": c.provider_id, "merchant_id": c.merchant_id,
        "provider_cart_ref": c.provider_cart_ref, "revision": c.revision, "status": c.status,
        "created_by_client": c.created_by_client, "created_at": COMMIT_TIMESTAMP, "updated_at": COMMIT_TIMESTAMP,
    }, insert_only=("created_at",))
    _replace_children(tx, "CartLines", _CART_LINE_COLS, c.id,
                      [[c.id, l.variant_id, l.source_variant_ref, l.quantity] for l in c.lines])


# quotes (stored as (member_id, CheckoutQuote)) ---------------------------------
_QUOTE_COLS = ("quote_id", "member_id", "environment", "provider_id", "merchant_id", "payee_ref", "cart_id",
               "cart_revision", "currency", "subtotal_minor", "tax_minor", "shipping_minor", "discount_minor",
               "total_minor", "delivery_ref", "checkout_reference", "terms", "terms_hash", "quote_hash",
               "hash_domain_version", "material_document", "source_evidence_ref", "issued_at", "expires_at")
_QUOTE_LINE_COLS = ("quote_id", "variant_id", "source_variant_ref", "quantity", "unit_price_minor",
                    "line_total_minor", "category")


def _load_quote(r, key):
    row = _read_one(r, "CheckoutQuotes", _QUOTE_COLS, key)
    if row is None:
        return None
    cur = row["currency"]
    m = lambda v: Money(v, cur)  # noqa: E731
    lines = tuple(QuoteLine(l["variant_id"], l["source_variant_ref"], l["quantity"], m(l["unit_price_minor"]),
                            m(l["line_total_minor"]), "", l["category"] or "")
                  for l in _read_children(r, "QuoteLines", _QUOTE_LINE_COLS, key))
    t = _json(row["terms"])
    if "returnable" not in t:  # written before V015 recorded terms: those terms are unknown, never approvable
        raise QuoteExpired("this quote predates recorded checkout terms; request a new quote")
    quote = CheckoutQuote(
        id=row["quote_id"], environment=row["environment"], provider_id=row["provider_id"],
        merchant_id=row["merchant_id"], payee_ref=row["payee_ref"], cart_id=row["cart_id"],
        cart_revision=row["cart_revision"], lines=lines, subtotal=m(row["subtotal_minor"]), tax=m(row["tax_minor"]),
        shipping=m(row["shipping_minor"]), discount=m(row["discount_minor"]), total=m(row["total_minor"]),
        delivery_ref=row["delivery_ref"],
        terms=CheckoutTerms(t["returnable"], t["return_window_days"], t.get("policy_ref"), t.get("recurring", False)),
        checkout_reference=row["checkout_reference"], issued_at=row["issued_at"], expires_at=row["expires_at"],
        terms_hash=row["terms_hash"], quote_hash=row["quote_hash"], source_evidence_ref=row["source_evidence_ref"])
    return row["member_id"], quote


def _save_quote(tx, key, value, exists):
    member_id, q = value
    t = q.terms
    _write(tx, "CheckoutQuotes", exists, {
        "quote_id": q.id, "member_id": member_id, "environment": q.environment, "provider_id": q.provider_id,
        "merchant_id": q.merchant_id, "payee_ref": q.payee_ref, "cart_id": q.cart_id,
        "cart_revision": q.cart_revision, "currency": q.currency, "subtotal_minor": q.subtotal.amount_minor,
        "tax_minor": q.tax.amount_minor, "shipping_minor": q.shipping.amount_minor,
        "discount_minor": q.discount.amount_minor, "total_minor": q.total.amount_minor,
        "delivery_ref": q.delivery_ref, "checkout_reference": q.checkout_reference,
        "terms": JsonObject({"returnable": t.returnable, "return_window_days": t.return_window_days,
                             "policy_ref": t.policy_ref, "recurring": t.recurring}),
        "terms_hash": q.terms_hash, "quote_hash": q.quote_hash, "hash_domain_version": QUOTE_HASH_VERSION,
        "material_document": JsonObject(q.material_document()), "source_evidence_ref": q.source_evidence_ref,
        "issued_at": q.issued_at, "expires_at": q.expires_at,
    })
    _replace_children(tx, "QuoteLines", _QUOTE_LINE_COLS, q.id, [
        [q.id, l.variant_id, l.source_variant_ref, l.quantity, l.unit_price.amount_minor,
         l.line_total.amount_minor, l.category or None] for l in q.lines])


# delegations ------------------------------------------------------------------
_DELEGATION_COLS = ("delegation_id", "member_id", "client_id", "mode", "scopes", "allowed_providers", "limits",
                    "created_at", "expires_at", "revoked_at", "version")


def _limits_to_json(l: Optional[DelegationLimits]):
    if l is None:
        return None
    return JsonObject({
        "currency": l.currency, "max_per_order_minor": l.max_per_order.amount_minor,
        "max_cumulative_minor": l.max_cumulative.amount_minor, "window_seconds": l.window_seconds,
        "allowed_merchants": sorted(l.allowed_merchants), "allowed_categories": sorted(l.allowed_categories),
        "allowed_variant_refs": sorted(l.allowed_variant_refs), "delivery_ref": l.delivery_ref,
        "payment_instrument_ref": l.payment_instrument_ref, "require_returnable": l.require_returnable,
        "allow_substitution": l.allow_substitution, "require_final_human_approval": l.require_final_human_approval,
        "refund_credit_back": l.refund_credit_back,
        "totals_include_tax_and_shipping": l.totals_include_tax_and_shipping,
    })


def _limits_from_json(v) -> Optional[DelegationLimits]:
    if v is None:
        return None
    d = _json(v)
    cur = d["currency"]
    return DelegationLimits(
        currency=cur, max_per_order=Money(d["max_per_order_minor"], cur),
        max_cumulative=Money(d["max_cumulative_minor"], cur), window_seconds=d["window_seconds"],
        allowed_merchants=frozenset(d["allowed_merchants"]), allowed_categories=frozenset(d["allowed_categories"]),
        allowed_variant_refs=frozenset(d["allowed_variant_refs"]), delivery_ref=d["delivery_ref"],
        payment_instrument_ref=d["payment_instrument_ref"], require_returnable=d["require_returnable"],
        allow_substitution=d["allow_substitution"], require_final_human_approval=d["require_final_human_approval"],
        refund_credit_back=d["refund_credit_back"],
        totals_include_tax_and_shipping=d["totals_include_tax_and_shipping"])


def _load_delegation(r, key):
    row = _read_one(r, "AgentDelegations", _DELEGATION_COLS, key)
    if row is None:
        return None
    return AgentDelegation(
        id=row["delegation_id"], member_id=row["member_id"], client_id=row["client_id"],
        mode=AssistanceMode(row["mode"]), scopes=frozenset(row["scopes"]),
        allowed_providers=frozenset(row["allowed_providers"]), limits=_limits_from_json(row["limits"]),
        created_at=row["created_at"], expires_at=row["expires_at"], revoked_at=row["revoked_at"],
        version=row["version"])


def _save_delegation(tx, key, d: AgentDelegation, exists):
    _write(tx, "AgentDelegations", exists, {
        "delegation_id": d.id, "member_id": d.member_id, "client_id": d.client_id, "mode": d.mode.value,
        "scopes": sorted(d.scopes), "allowed_providers": sorted(d.allowed_providers),
        "limits": _limits_to_json(d.limits), "created_at": d.created_at, "expires_at": d.expires_at,
        "revoked_at": d.revoked_at, "version": d.version})


# challenges ---------------------------------------------------------------------
_CHALLENGE_COLS = ("challenge_id", "member_id", "operation_id", "quote_id", "quote_hash", "nonce_hash",
                   "delegation_ref", "issued_at", "expires_at", "used")


def _load_challenge(r, key):
    row = _read_one(r, "ApprovalChallenges", _CHALLENGE_COLS, key)
    if row is None:
        return None
    return ApprovalChallenge(id=row["challenge_id"], member_id=row["member_id"], operation_id=row["operation_id"],
                             quote_id=row["quote_id"], quote_hash=row["quote_hash"], nonce_hash=row["nonce_hash"],
                             delegation_ref=row["delegation_ref"], issued_at=row["issued_at"],
                             expires_at=row["expires_at"], used=row["used"])


def _save_challenge(tx, key, c: ApprovalChallenge, exists):
    _write(tx, "ApprovalChallenges", exists, {
        "challenge_id": c.id, "member_id": c.member_id, "operation_id": c.operation_id, "quote_id": c.quote_id,
        "quote_hash": c.quote_hash, "nonce_hash": c.nonce_hash, "delegation_ref": c.delegation_ref,
        "issued_at": c.issued_at, "expires_at": c.expires_at, "used": c.used})  # the plaintext nonce is never stored


# approvals ----------------------------------------------------------------------
_APPROVAL_COLS = ("approval_id", "member_id", "delegation_ref", "quote_id", "quote_hash", "merchant_id",
                  "allowed_total_minor", "currency", "nonce", "issued_at", "expires_at", "assurance_level", "method",
                  "materiality_rule", "protocol_payload_hash", "state")


def _load_approval(r, key):
    row = _read_one(r, "PurchaseApprovals", _APPROVAL_COLS, key)
    if row is None:
        return None
    return PurchaseApproval(
        id=row["approval_id"], member_id=row["member_id"], delegation_ref=row["delegation_ref"],
        quote_id=row["quote_id"], quote_hash=row["quote_hash"], merchant_id=row["merchant_id"],
        allowed_total=Money(row["allowed_total_minor"], row["currency"]), nonce=row["nonce"],
        issued_at=row["issued_at"], expires_at=row["expires_at"], assurance_level=row["assurance_level"],
        method=row["method"], materiality_rule=row["materiality_rule"], state=row["state"],
        protocol_payload_hash=row["protocol_payload_hash"])


def _save_approval(tx, key, a: PurchaseApproval, exists):
    _write(tx, "PurchaseApprovals", exists, {
        "approval_id": a.id, "member_id": a.member_id, "delegation_ref": a.delegation_ref, "quote_id": a.quote_id,
        "quote_hash": a.quote_hash, "merchant_id": a.merchant_id, "allowed_total_minor": a.allowed_total.amount_minor,
        "currency": a.allowed_total.currency, "nonce": a.nonce, "issued_at": a.issued_at,
        "expires_at": a.expires_at, "assurance_level": a.assurance_level, "method": a.method,
        "materiality_rule": a.materiality_rule, "protocol_payload_hash": a.protocol_payload_hash,
        "state": a.state})


# budget entries (key: (delegation_id, entry_id)) --------------------------------
_BUDGET_COLS = ("delegation_id", "entry_id", "operation_id", "kind", "state", "amount_minor", "currency", "created_at")


def _load_budget(r, key):
    row = _read_one(r, "DelegationBudgetEntries", _BUDGET_COLS, key)
    if row is None:
        return None
    return BudgetEntry(row["entry_id"], row["delegation_id"], row["operation_id"],
                       Money(row["amount_minor"], row["currency"]), row["kind"], row["state"], row["created_at"])


def _save_budget(tx, key, e: BudgetEntry, exists):
    _write(tx, "DelegationBudgetEntries", exists, {
        "delegation_id": e.delegation_id, "entry_id": e.id, "operation_id": e.operation_id, "kind": e.kind,
        "state": e.state, "amount_minor": e.amount.amount_minor, "currency": e.amount.currency,
        "created_at": e.created_at})


# operations ---------------------------------------------------------------------
_OP_COLS = ("operation_id", "member_id", "delegation_id", "client_id", "quote_id", "quote_hash", "approval_id",
            "provider_id", "state", "provider_idempotency_key", "order_id", "reason_code", "attempts", "version",
            "created_at", "updated_at")


def _load_operation(r, key):
    row = _read_one(r, "PurchaseOperations", _OP_COLS, key)
    if row is None:
        return None
    return PurchaseOperation(
        id=row["operation_id"], member_id=row["member_id"], delegation_id=row["delegation_id"],
        client_id=row["client_id"], quote_id=row["quote_id"], quote_hash=row["quote_hash"],
        approval_id=row["approval_id"], provider_id=row["provider_id"], state=row["state"],
        provider_idempotency_key=row["provider_idempotency_key"], created_at=row["created_at"],
        updated_at=row["updated_at"], order_id=row["order_id"], reason_code=row["reason_code"],
        attempts=row["attempts"], version=row["version"])


def _save_operation(tx, key, o: PurchaseOperation, exists):
    _write(tx, "PurchaseOperations", exists, {
        "operation_id": o.id, "member_id": o.member_id, "delegation_id": o.delegation_id, "client_id": o.client_id,
        "quote_id": o.quote_id, "quote_hash": o.quote_hash, "approval_id": o.approval_id,
        "provider_id": o.provider_id, "state": o.state, "provider_idempotency_key": o.provider_idempotency_key,
        "order_id": o.order_id, "reason_code": o.reason_code, "attempts": o.attempts, "version": o.version,
        "created_at": o.created_at, "updated_at": o.updated_at})


# orders -------------------------------------------------------------------------
_ORDER_COLS = ("order_id", "member_id", "operation_id", "provider_id", "merchant_id", "provider_order_ref",
               "quote_hash", "idempotency_key", "order_status", "payment_status", "fulfillment_status", "currency",
               "total_minor", "refunded_minor", "evidence_refs", "last_observed_at", "version")
_ORDER_LINE_COLS = ("order_id", "source_variant_ref", "variant_id", "quantity_ordered", "quantity_shipped",
                    "quantity_delivered", "quantity_returned", "exchanged_from_ref")


def _load_order(r, key):
    row = _read_one(r, "Orders", _ORDER_COLS, key)
    if row is None:
        return None
    cur = row["currency"]
    lines = tuple(OrderLine(l["variant_id"], l["source_variant_ref"], l["quantity_ordered"], l["quantity_shipped"],
                            l["quantity_delivered"], l["quantity_returned"], l["exchanged_from_ref"])
                  for l in _read_children(r, "OrderLines", _ORDER_LINE_COLS, key))
    return Order(
        id=row["order_id"], member_id=row["member_id"], operation_id=row["operation_id"],
        provider_id=row["provider_id"], merchant_id=row["merchant_id"], provider_order_ref=row["provider_order_ref"],
        quote_hash=row["quote_hash"], idempotency_key=row["idempotency_key"], order_status=row["order_status"],
        payment_status=row["payment_status"], fulfillment_status=row["fulfillment_status"], lines=lines,
        total=Money(row["total_minor"], cur), refunded_total=Money(row["refunded_minor"], cur),
        last_observed_at=row["last_observed_at"], evidence_refs=tuple(row["evidence_refs"]), version=row["version"])


def _save_order(tx, key, o: Order, exists):
    _write(tx, "Orders", exists, {
        "order_id": o.id, "member_id": o.member_id, "operation_id": o.operation_id, "provider_id": o.provider_id,
        "merchant_id": o.merchant_id, "provider_order_ref": o.provider_order_ref, "quote_hash": o.quote_hash,
        "idempotency_key": o.idempotency_key, "order_status": o.order_status, "payment_status": o.payment_status,
        "fulfillment_status": o.fulfillment_status, "currency": o.total.currency, "total_minor": o.total.amount_minor,
        "refunded_minor": o.refunded_total.amount_minor, "evidence_refs": list(o.evidence_refs),
        "last_observed_at": o.last_observed_at, "created_at": COMMIT_TIMESTAMP, "version": o.version,
    }, insert_only=("created_at",))
    # Lines are only ever added or advanced (exchange history is retained), never removed.
    tx.insert_or_update("OrderLines", columns=_ORDER_LINE_COLS, values=[
        [o.id, l.source_variant_ref, l.variant_id, l.quantity_ordered, l.quantity_shipped, l.quantity_delivered,
         l.quantity_returned, l.exchanged_from_ref] for l in o.lines])


# idempotency (key: (member, environment, operation, delegation|"-", key)) ------------
_IDEM_COLS = ("member_id", "environment", "operation", "delegation_scope", "idempotency_key", "request_digest",
              "result_ref", "created_at")


def _load_idem(r, key):
    row = _read_one(r, "CommerceIdempotencyKeys", _IDEM_COLS, key)
    if row is None:
        return None
    return IdempotencyRecord(tuple(key), row["request_digest"], row["result_ref"], row["created_at"])


def _save_idem(tx, key, rec: IdempotencyRecord, exists):
    member, env, op, scope, k = key
    _write(tx, "CommerceIdempotencyKeys", exists, {
        "member_id": member, "environment": env, "operation": op, "delegation_scope": scope, "idempotency_key": k,
        "request_digest": rec.request_digest, "result_ref": rec.result_ref, "created_at": rec.created_at})


# webhook receipts (V006) ------------------------------------------------------------
_WEBHOOK_COLS = ("provider_id", "event_id", "event_type", "received_at", "state")


def _load_webhook(r, key):
    row = _read_one(r, "ProviderWebhookReceipts", _WEBHOOK_COLS, key)
    if row is None:
        return None
    return WebhookReceipt(row["provider_id"], row["event_id"], row["event_type"], row["received_at"], row["state"])


def _save_webhook(tx, key, w: WebhookReceipt, exists):
    _write(tx, "ProviderWebhookReceipts", exists, {
        "provider_id": w.provider_id, "event_id": w.event_id, "event_type": w.event_type,
        "received_at": w.received_at, "state": w.state})


# surface keys (key: (member_id, kid); value: public JWK) -------------------------------
def _load_surface_key(r, key):
    row = _read_one(r, "MemberSurfaceKeys", ("member_id", "key_thumbprint", "public_jwk", "revoked_at"), key)
    if row is None or row["revoked_at"] is not None:
        return None
    return _json(row["public_jwk"])


def _save_surface_key(tx, key, jwk, exists):
    member_id, kid = key
    # A revoked key reads as absent but its row remains: re-registration reactivates it.
    tx.insert_or_update("MemberSurfaceKeys", columns=("member_id", "key_thumbprint", "public_jwk", "registered_at",
                                                      "revoked_at"),
                        values=[(member_id, kid, JsonObject(dict(jwk)), COMMIT_TIMESTAMP, None)])


# used AP2 mandates ------------------------------------------------------------------------
def _load_ap2_used(r, key):
    row = _read_one(r, "Ap2UsedMandates", ("mandate_digest", "approval_id"), key)
    return None if row is None else row["approval_id"]


def _save_ap2_used(tx, key, approval_id, exists):
    _write(tx, "Ap2UsedMandates", exists, {"mandate_digest": key, "approval_id": approval_id,
                                            "used_at": COMMIT_TIMESTAMP}, insert_only=("used_at",))


# return requests ------------------------------------------------------------------------
_RETURN_COLS = ("return_id", "order_id", "member_id", "source_variant_ref", "quantity", "provider_reference",
                "status", "requested_at")


def _load_return(r, key):
    row = _read_one(r, "ReturnRequests", _RETURN_COLS, key)
    if row is None:
        return None
    return ReturnRequest(id=row["return_id"], order_id=row["order_id"], member_id=row["member_id"],
                         source_variant_ref=row["source_variant_ref"], quantity=row["quantity"],
                         status=row["status"], requested_at=row["requested_at"],
                         provider_reference=row["provider_reference"])


def _save_return(tx, key, rr: ReturnRequest, exists):
    _write(tx, "ReturnRequests", exists, {
        "return_id": rr.id, "order_id": rr.order_id, "member_id": rr.member_id,
        "source_variant_ref": rr.source_variant_ref, "quantity": rr.quantity,
        "provider_reference": rr.provider_reference, "status": rr.status, "requested_at": rr.requested_at})


CODECS: Dict[str, _Codec] = {
    "carts": _Codec("Carts", ("cart_id",), _load_cart, _save_cart),
    "quotes": _Codec("CheckoutQuotes", ("quote_id",), _load_quote, _save_quote),
    "delegations": _Codec("AgentDelegations", ("delegation_id",), _load_delegation, _save_delegation),
    "challenges": _Codec("ApprovalChallenges", ("challenge_id",), _load_challenge, _save_challenge),
    "approvals": _Codec("PurchaseApprovals", ("approval_id",), _load_approval, _save_approval),
    "reservations": _Codec("DelegationBudgetEntries", ("delegation_id", "entry_id"), _load_budget, _save_budget),
    "operations": _Codec("PurchaseOperations", ("operation_id",), _load_operation, _save_operation),
    "orders": _Codec("Orders", ("order_id",), _load_order, _save_order),
    "idempotency": _Codec("CommerceIdempotencyKeys",
                          ("member_id", "environment", "operation", "delegation_scope", "idempotency_key"),
                          _load_idem, _save_idem),
    "webhook_receipts": _Codec("ProviderWebhookReceipts", ("provider_id", "event_id"), _load_webhook, _save_webhook),
    "surface_keys": _Codec("MemberSurfaceKeys", ("member_id", "key_thumbprint"), _load_surface_key,
                           _save_surface_key),
    "ap2_used": _Codec("Ap2UsedMandates", ("mandate_digest",), _load_ap2_used, _save_ap2_used),
    "returns": _Codec("ReturnRequests", ("return_id",), _load_return, _save_return),
}

# Named query -> SQL returning primary-key columns of the logical table.
QUERY_SQL: Dict[str, str] = {
    "active_delegations": """SELECT delegation_id FROM AgentDelegations
        WHERE member_id = @member_id AND client_id = @client_id AND revoked_at IS NULL AND expires_at > @now""",
    "operations_for_delegation": """SELECT operation_id FROM PurchaseOperations
        WHERE delegation_id = @delegation_id""",
    "operations_for_quote_hash": "SELECT operation_id FROM PurchaseOperations WHERE quote_hash = @quote_hash",
    "operations_in_state": """SELECT operation_id FROM PurchaseOperations
        WHERE state = @state AND provider_id = @provider_id ORDER BY updated_at""",
    "orders_by_provider_ref": """SELECT order_id FROM Orders
        WHERE provider_id = @provider_id AND provider_order_ref = @provider_order_ref""",
    "budget_entries": """SELECT delegation_id, entry_id FROM DelegationBudgetEntries
        WHERE delegation_id = @delegation_id""",
    "budget_entries_for_operation": """SELECT delegation_id, entry_id FROM DelegationBudgetEntries
        WHERE operation_id = @operation_id""",
    "surface_keys": """SELECT member_id, key_thumbprint FROM MemberSurfaceKeys
        WHERE member_id = @member_id AND revoked_at IS NULL""",
    "operations_by_state": """SELECT operation_id FROM PurchaseOperations@{FORCE_INDEX=PurchaseOperationsByState}
        WHERE state = @state ORDER BY updated_at LIMIT 200""",
    "webhook_receipts_pending": """SELECT provider_id, event_id FROM ProviderWebhookReceipts
        WHERE state = 'pending_reconcile' ORDER BY received_at LIMIT 200""",
    "returns_for_order": "SELECT return_id FROM ReturnRequests WHERE order_id = @order_id",
    "delegations_for_member": "SELECT delegation_id FROM AgentDelegations WHERE member_id = @member_id",
    "operations_for_member": "SELECT operation_id FROM PurchaseOperations WHERE member_id = @member_id",
    "carts_for_member": "SELECT cart_id FROM Carts WHERE member_id = @member_id",
    "quotes_for_member": "SELECT quote_id FROM CheckoutQuotes WHERE member_id = @member_id",
    "challenges_for_member": "SELECT challenge_id FROM ApprovalChallenges WHERE member_id = @member_id",
    "approvals_for_member": "SELECT approval_id FROM PurchaseApprovals WHERE member_id = @member_id",
    "idempotency_for_member": """SELECT member_id, environment, operation, delegation_scope, idempotency_key
        FROM CommerceIdempotencyKeys WHERE member_id = @member_id""",
}


# ------------------------------------------------------------------ readers
class _Reader(QueryMixin):
    """Reads through a Spanner snapshot or read/write transaction."""

    def __init__(self, reader) -> None:
        self._r = reader
        self._overlay: Dict[Tuple[str, Any], Any] = {}

    def get(self, table: str, key: Any) -> Any:
        hit = self._overlay.get((table, key), _MISSING)
        if hit is not _MISSING:
            return hit
        return CODECS[table].load(self._r, key)

    def _sql_keys(self, name: str, params: Dict[str, Any]) -> List[Any]:
        rows = self._r.execute_sql(QUERY_SQL[name], params=params,
                                   param_types={k: _param_type(v) for k, v in params.items()})
        return [tuple(r) if len(r) > 1 else r[0] for r in rows]

    def _query(self, name: str, **params: Any) -> List[Any]:
        table, factory = QUERIES[name]
        pred = factory(**params)
        out: Dict[Any, Any] = {}
        for key in self._sql_keys(name, params):
            row = self.get(table, key)
            if row is None:
                continue
            item = (key[0], key[1], row) if table == "surface_keys" else row
            if pred(key if table == "surface_keys" else row):
                out[key] = item
        for (t, key), row in self._overlay.items():  # rows written or deleted earlier in this transaction
            if t != table:
                continue
            if row is None:
                out.pop(key, None)
                continue
            probe = key if table == "surface_keys" else row
            if pred(probe):
                out[key] = (key[0], key[1], row) if table == "surface_keys" else row
            else:
                out.pop(key, None)
        return list(out.values())


class _SpannerTx(_Reader):
    def __init__(self, transaction) -> None:
        super().__init__(transaction)
        self._exists: Dict[Tuple[str, Any], bool] = {}
        self.events: List[EventEnvelope] = []
        self.touched = False  # a callback that neither read nor wrote still has to commit cleanly

    def get(self, table: str, key: Any) -> Any:
        self.touched = True
        return super().get(table, key)

    def _sql_keys(self, name: str, params: Dict[str, Any]) -> List[Any]:
        self.touched = True
        return super()._sql_keys(name, params)

    def put(self, table: str, key: Any, row: Any) -> None:
        self.touched = True
        slot = (table, key)
        exists = self._exists.get(slot)
        if exists is None:
            exists = CODECS[table].load(self._r, key) is not None
        CODECS[table].save(self._r, key, row, exists)
        self._overlay[slot] = row
        self._exists[slot] = True

    def delete(self, table: str, key: Any) -> None:
        """Delete a row; interleaved children cascade (CartLines, QuoteLines) or are removed first."""
        self.touched = True
        codec = CODECS[table]
        if table == "orders":
            raise ValueError("orders are financial evidence and are never deleted by the commerce store")
        self._r.delete(codec.table, KeySet(keys=[_key_list(key)]))
        self._overlay[(table, key)] = None
        self._exists[(table, key)] = False

    def emit(self, event: EventEnvelope) -> None:
        event.validate()  # fail inside the callback, before commit
        self.events.append(event)


class SpannerCommerceStore(QueryMixin):
    def __init__(self, database) -> None:
        self.database = database

    def run(self, fn: Callable[[_SpannerTx], T]) -> T:
        def attempt(transaction):
            tx = _SpannerTx(transaction)  # fresh overlay/events per attempt
            result = fn(tx)
            if not tx.touched and not tx.events:
                list(transaction.execute_sql("SELECT 1"))  # begin it; an empty commit is refused
            write_events(transaction, tx.events)
            return result
        return self.database.run_in_transaction(attempt)

    def get(self, table: str, key: Any) -> Any:
        with self.database.snapshot(multi_use=True) as snap:
            return _Reader(snap).get(table, key)

    def _query(self, name: str, **params: Any) -> List[Any]:
        with self.database.snapshot(multi_use=True) as snap:
            return _Reader(snap)._query(name, **params)

    # -- introspection (tests, ops tooling); domain code uses named queries --
    def rows(self, table: str) -> List[Any]:
        codec = CODECS[table]
        with self.database.snapshot(multi_use=True) as snap:
            keys = [tuple(r) if len(r) > 1 else r[0]
                    for r in snap.execute_sql(f"SELECT {', '.join(codec.pk)} FROM {codec.table}")]
            reader = _Reader(snap)
            return [row for row in (reader.get(table, k) for k in keys) if row is not None]

    def outbox(self) -> List[EventEnvelope]:
        cols = ("event_id", "event_type", "schema_version", "aggregate_type", "aggregate_id", "aggregate_version",
                "occurred_at", "environment", "actor_ref", "correlation_id", "causation_id", "privacy_class",
                "payload")
        with self.database.snapshot() as snap:
            rows = snap.execute_sql(f"SELECT {', '.join(cols)} FROM OutboxEvents "
                                    "WHERE aggregate_type IN UNNEST(@types) ORDER BY created_at, occurred_at",
                                    params={"types": list(COMMERCE_AGGREGATES)},
                                    param_types={"types": param_types.Array(param_types.STRING)})
            return [EventEnvelope.from_row(dict(zip(cols, r))) for r in rows]


COMMERCE_AGGREGATES = ("AgentDelegation", "CheckoutQuote", "PurchaseOperation", "Order")


MEMBER_TABLES = {
    "AgentDelegations": "member_id", "DelegationBudgetEntries": None, "Carts": "member_id", "CartLines": None,
    "CheckoutQuotes": "member_id", "QuoteLines": None, "ApprovalChallenges": "member_id",
    "PurchaseApprovals": "member_id", "MemberSurfaceKeys": "member_id", "PurchaseOperations": "member_id",
    "Orders": "member_id", "OrderLines": None, "ReturnRequests": "member_id", "CommerceIdempotencyKeys": "member_id",
}
# Child/ledger rows are selected through their parent's member column.
_CHILD_SQL = {
    "DelegationBudgetEntries": """SELECT e.* FROM DelegationBudgetEntries e JOIN AgentDelegations d
        ON e.delegation_id = d.delegation_id WHERE d.member_id = @m""",
    "CartLines": "SELECT l.* FROM CartLines l JOIN Carts c ON l.cart_id = c.cart_id WHERE c.member_id = @m",
    "QuoteLines": """SELECT l.* FROM QuoteLines l JOIN CheckoutQuotes q ON l.quote_id = q.quote_id
        WHERE q.member_id = @m""",
    "OrderLines": "SELECT l.* FROM OrderLines l JOIN Orders o ON l.order_id = o.order_id WHERE o.member_id = @m",
}


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, JsonObject) or hasattr(value, "serialize"):
        return _json(value)
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def iter_member_rows(database, member_id: str, tables: Sequence[str]) -> Iterable[Dict[str, Any]]:
    """The member's rows in ``tables`` as JSON-safe dicts, for My Data export."""
    with database.snapshot(multi_use=True) as snap:
        for table in tables:
            col = MEMBER_TABLES[table]
            sql = _CHILD_SQL[table] if col is None else f"SELECT * FROM {table} WHERE {col} = @m"
            result = snap.execute_sql(sql, params={"m": member_id}, param_types={"m": param_types.STRING})
            rows = list(result)
            names = [f.name for f in result.fields]
            for r in rows:
                yield {"table": table, "row": {n: _plain(v) for n, v in zip(names, r)}}
