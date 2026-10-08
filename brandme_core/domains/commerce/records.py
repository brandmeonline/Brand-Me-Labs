"""Commerce aggregate records and the purchase state machine (ch.05 §6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, FrozenSet, Optional, Tuple

from .errors import InvalidTransition
from .money import Money
from brandme_core.domains.providers.contracts import CartLineRequest

PURCHASE_STATES = (
    "draft", "quoting", "awaiting_approval", "approved", "submitting", "outcome_unknown",
    "accepted", "rejected", "cancel_requested", "cancelled", "partially_fulfilled",
    "fulfilled", "return_requested", "partially_refunded", "refunded", "disputed",
)

_T: Dict[str, FrozenSet[str]] = {
    "draft": frozenset({"quoting", "cancelled"}),
    "quoting": frozenset({"awaiting_approval", "cancelled"}),
    "awaiting_approval": frozenset({"approved", "cancelled"}),
    "approved": frozenset({"submitting", "cancelled"}),
    "submitting": frozenset({"accepted", "rejected", "outcome_unknown"}),
    "outcome_unknown": frozenset({"accepted", "rejected"}),
    "accepted": frozenset({"cancel_requested", "partially_fulfilled", "fulfilled",
                           "partially_refunded", "refunded", "disputed", "cancelled"}),
    "cancel_requested": frozenset({"cancelled", "accepted", "partially_fulfilled", "fulfilled"}),
    "partially_fulfilled": frozenset({"partially_fulfilled", "fulfilled", "return_requested",
                                      "partially_refunded", "refunded", "disputed"}),
    "fulfilled": frozenset({"return_requested", "partially_refunded", "refunded", "disputed"}),
    "return_requested": frozenset({"partially_refunded", "refunded", "fulfilled", "disputed"}),
    "partially_refunded": frozenset({"partially_refunded", "refunded", "return_requested", "disputed",
                                     "partially_fulfilled", "fulfilled"}),
    "refunded": frozenset({"disputed"}),
    "rejected": frozenset(),
    "cancelled": frozenset({"refunded"}),
    "disputed": frozenset({"refunded", "partially_refunded", "fulfilled"}),
}
TERMINAL_PRE_ORDER = frozenset({"rejected", "cancelled"})
IN_FLIGHT = frozenset({"approved", "submitting", "outcome_unknown"})


def check_transition(current: str, new: str) -> None:
    if new == current:
        return
    if new not in _T.get(current, frozenset()):
        raise InvalidTransition(f"purchase cannot move from {current} to {new}")


@dataclass(frozen=True)
class Cart:
    id: str
    member_id: str
    provider_id: str
    merchant_id: str
    provider_cart_ref: str
    lines: Tuple[CartLineRequest, ...]
    revision: int
    created_by_client: str
    status: str = "draft"  # draft | quoted | abandoned


@dataclass(frozen=True)
class ApprovalChallenge:
    id: str
    member_id: str
    quote_id: str
    quote_hash: str
    nonce: str
    delegation_ref: Optional[str]
    issued_at: datetime
    expires_at: datetime
    used: bool = False


@dataclass(frozen=True)
class PurchaseApproval:
    id: str
    member_id: str
    delegation_ref: Optional[str]
    quote_id: str
    quote_hash: str
    merchant_id: str
    allowed_total: Money
    nonce: str
    issued_at: datetime
    expires_at: datetime
    assurance_level: str
    method: str  # "trusted_surface" | "ap2_mandate"
    materiality_rule: str
    state: str = "issued"  # issued | consumed | void
    protocol_payload_hash: Optional[str] = None  # set when backed by an AP2 mandate


@dataclass(frozen=True)
class BudgetEntry:
    id: str
    delegation_id: str
    operation_id: str
    amount: Money
    kind: str  # reservation | credit
    state: str  # reserved | consumed | released | credited
    created_at: datetime


@dataclass(frozen=True)
class PurchaseOperation:
    id: str
    member_id: str
    delegation_id: Optional[str]
    client_id: str
    quote_id: str
    quote_hash: str
    approval_id: Optional[str]
    provider_id: str
    state: str
    provider_idempotency_key: str
    created_at: datetime
    updated_at: datetime
    order_id: Optional[str] = None
    reason_code: Optional[str] = None
    attempts: int = 0
    version: int = 1


@dataclass(frozen=True)
class OrderLine:
    variant_id: Optional[str]
    source_variant_ref: str
    quantity_ordered: int
    quantity_shipped: int = 0
    quantity_delivered: int = 0
    quantity_returned: int = 0
    exchanged_from_ref: Optional[str] = None


@dataclass(frozen=True)
class Order:
    id: str
    member_id: str
    operation_id: str
    provider_id: str
    merchant_id: str
    provider_order_ref: str
    quote_hash: str
    idempotency_key: str
    order_status: str
    payment_status: str
    fulfillment_status: str
    lines: Tuple[OrderLine, ...]
    total: Money
    refunded_total: Money
    last_observed_at: datetime
    evidence_refs: Tuple[str, ...] = ()
    version: int = 1


@dataclass(frozen=True)
class IdempotencyRecord:
    scope: Tuple[str, str, str, str, str]  # member, environment, operation, delegation|"-", key
    request_digest: str
    result_ref: str
    created_at: datetime


@dataclass(frozen=True)
class WebhookReceipt:
    provider_id: str
    event_id: str
    event_type: str
    received_at: datetime
    state: str  # applied | pending_reconcile | ignored
