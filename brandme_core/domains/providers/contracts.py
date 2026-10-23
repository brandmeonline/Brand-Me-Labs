"""Narrow typed provider interfaces and the common result/error model (ch.05 §1).

Each adapter implements only the protocols it actually supports. Unsupported
operations are absent, not success-shaped no-ops. These definitions are the
Python source for the future ``packages/provider-contracts`` TypeScript package.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple, runtime_checkable

from brandme_core.domains.commerce.money import Money
from brandme_core.domains.commerce.quote import CheckoutTerms

CAPABILITIES: Tuple[str, ...] = (
    "catalog.search", "catalog.detail", "catalog.feed", "catalog.images", "catalog.3d",
    "inventory.read", "price.quote", "cart.create", "cart.update", "checkout.handoff",
    "checkout.submit", "orders.read", "orders.webhook", "returns.request", "refunds.read",
    "affiliate.attribution", "receipts.import", "tryon.photo", "tryon.live", "rights.issue",
    "rights.transfer", "rights.reprint", "manufacture.quote", "manufacture.submit",
)
CAPABILITY_STATES: Tuple[str, ...] = (
    "unconfigured", "sandbox", "verified", "degraded", "suspended", "unsupported",
)
# States in which an operation may actually be executed.
EXECUTABLE_STATES = frozenset({"sandbox", "verified", "degraded"})


class ProviderErrorKind(str, enum.Enum):
    UNSUPPORTED = "unsupported"
    NOT_CONFIGURED = "not_configured"
    UNAUTHORIZED = "unauthorized"
    CONTRACT_RESTRICTED = "contract_restricted"
    THROTTLED = "throttled"
    TRANSIENT = "transient"
    MALFORMED_RESPONSE = "malformed_response"
    OUTCOME_UNKNOWN = "outcome_unknown"


class ProviderError(Exception):
    def __init__(self, kind: ProviderErrorKind, detail: str, *,
                 evidence_ref: Optional[str] = None, transmitted: bool = False):
        super().__init__(f"{kind.value}: {detail}")
        self.kind = kind
        self.detail = detail
        self.evidence_ref = evidence_ref  # redacted provider evidence pointer
        # True when the request may have reached the provider. Any such error
        # makes the outcome unknown; it must be reconciled, never blindly retried.
        self.transmitted = transmitted


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    environment: str
    operation_id: str
    source_reference: str
    observed_at: datetime
    expires_at: Optional[datetime]
    status: str
    warnings: Tuple[str, ...] = ()
    data: Any = None


# --- catalog / inventory ------------------------------------------------------

@dataclass(frozen=True)
class SourceVariant:
    provider_id: str
    merchant_id: str
    source_product_id: str
    source_variant_id: str
    brand: str
    title: str
    category: str
    size_system: Optional[str]
    size_label: Optional[str]
    color: Optional[str]
    gtin: Optional[str]
    product_url: str
    image_urls: Tuple[str, ...]
    price: Optional[Money]  # last observed price; a feed price is never a quote
    availability: str  # "in_stock" | "out_of_stock" | "unknown" | "discontinued"
    source_updated_at: datetime
    rights_policy_ref: str
    description: str = ""  # untrusted provider text: data, never instructions


@dataclass(frozen=True)
class CatalogPage:
    items: Tuple[SourceVariant, ...]
    next_cursor: Optional[str]
    tombstones: Tuple[Tuple[str, str], ...] = ()  # (source_product_id, source_variant_id)


@runtime_checkable
class CatalogProvider(Protocol):
    provider_id: str

    def search(self, query: str, *, cursor: Optional[str] = None, limit: int = 24) -> CatalogPage: ...

    def detail(self, source_product_id: str) -> Tuple[SourceVariant, ...]: ...


@runtime_checkable
class CatalogFeedProvider(Protocol):
    provider_id: str

    def feed_page(self, cursor: Optional[str]) -> CatalogPage: ...


@dataclass(frozen=True)
class InventoryObservation:
    source_variant_id: str
    available_quantity: Optional[int]
    observed_at: datetime


@runtime_checkable
class InventoryProvider(Protocol):
    provider_id: str

    def check(self, source_variant_ids: Sequence[str]) -> Tuple[InventoryObservation, ...]: ...


# --- cart / checkout ----------------------------------------------------------

@dataclass(frozen=True)
class CartLineRequest:
    variant_id: str  # internal UUID
    source_variant_ref: str
    quantity: int


@dataclass(frozen=True)
class ProviderCart:
    provider_cart_ref: str
    merchant_id: str
    lines: Tuple[CartLineRequest, ...]


@runtime_checkable
class CartProvider(Protocol):
    provider_id: str

    def create_cart(self, merchant_id: str, lines: Sequence[CartLineRequest]) -> ProviderCart: ...

    # Providers that only support full replacement are normalized behind this call.
    def replace_cart(self, provider_cart_ref: str, lines: Sequence[CartLineRequest]) -> ProviderCart: ...


@dataclass(frozen=True)
class QuotedLine:
    variant_id: str
    source_variant_ref: str
    quantity: int
    unit_price: Money
    title: str = ""
    category: str = ""


@dataclass(frozen=True)
class ProviderQuote:
    """A fresh provider quote. Commerce normalizes and hashes it."""

    merchant_id: str
    payee_ref: str
    lines: Tuple[QuotedLine, ...]
    tax: Money
    shipping: Money
    discount: Money
    delivery_ref: str
    terms: CheckoutTerms
    checkout_reference: str
    expires_at: datetime
    observed_at: datetime
    evidence_ref: Optional[str] = None


@dataclass(frozen=True)
class SubmitRequest:
    idempotency_key: str  # persisted before network I/O and reused on retry
    checkout_reference: str
    quote_hash: str
    expected_total: Money
    payment_token_ref: Optional[str]  # scoped provider token reference; never PAN/CVV


@dataclass(frozen=True)
class SubmitAck:
    accepted: bool
    provider_order_ref: Optional[str]
    reason_code: Optional[str]
    observed_at: datetime
    evidence_ref: Optional[str] = None


@runtime_checkable
class CheckoutProvider(Protocol):
    provider_id: str

    def quote(self, cart: ProviderCart) -> ProviderQuote: ...

    def submit(self, request: SubmitRequest) -> SubmitAck: ...


@dataclass(frozen=True)
class HandoffLink:
    url: str
    label: str  # e.g. "Continue at Nordstrom"
    disclosure: str
    affiliate: bool


@runtime_checkable
class CheckoutHandoffProvider(Protocol):
    provider_id: str

    def handoff(self, source_product_id: str, source_variant_id: Optional[str]) -> HandoffLink: ...


# --- orders -------------------------------------------------------------------

@dataclass(frozen=True)
class ObservedLine:
    source_variant_ref: str
    quantity_ordered: int
    quantity_shipped: int = 0
    quantity_delivered: int = 0
    quantity_returned: int = 0
    exchanged_from_ref: Optional[str] = None


@dataclass(frozen=True)
class OrderObservation:
    provider_order_ref: str
    order_status: str  # accepted | rejected | cancelled
    payment_status: str  # authorized | captured | partially_refunded | refunded | failed | unknown
    lines: Tuple[ObservedLine, ...]
    refunded_total: Money
    observed_at: datetime
    evidence_ref: Optional[str] = None


@dataclass(frozen=True)
class WebhookEvent:
    provider_id: str
    event_id: str
    event_type: str
    provider_order_ref: str
    occurred_at: datetime
    payload: Mapping[str, Any]


@runtime_checkable
class OrderProvider(Protocol):
    provider_id: str

    def lookup_by_idempotency_key(self, idempotency_key: str) -> Optional[OrderObservation]: ...

    def lookup(self, provider_order_ref: str) -> OrderObservation: ...

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent: ...


@runtime_checkable
class ReturnsProvider(Protocol):
    provider_id: str

    def request_return(self, provider_order_ref: str, source_variant_ref: str, quantity: int) -> ProviderResult: ...


# --- declared for completeness; implemented by other lanes / later stages -----

class ReceiptImporter(Protocol):
    provider_id: str

    def import_receipt(self, file_ref: str) -> ProviderResult: ...


class TryOnProvider(Protocol):
    provider_id: str

    def create_job(self, consent_id: str, media_ref: str, variant_ref: str) -> ProviderResult: ...


class RightsIssuer(Protocol):
    provider_id: str

    def issue(self, request: Mapping[str, Any]) -> ProviderResult: ...


class ManufacturingProvider(Protocol):
    provider_id: str

    def quote(self, request: Mapping[str, Any]) -> ProviderResult: ...


class ContextProvider(Protocol):
    provider_id: str

    def context(self, request: Mapping[str, Any]) -> ProviderResult: ...
