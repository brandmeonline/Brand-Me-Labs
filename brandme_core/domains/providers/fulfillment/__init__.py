"""Fulfillment provider seam for merchant adapters (ch.05 §6).

Like a payment processor, a fulfillment provider (a 3PL, a warehouse system,
the simulator) is an internal collaborator of a merchant adapter. The commerce
service never calls it, and no capability name exists for it: its effects
reach Brand.Me only as the merchant's ``OrderObservation`` lines.

The fulfillment record is the source of truth per line. Counters only grow;
``cancelled + shipped <= ordered``, ``delivered <= shipped`` and ``returned <=
shipped`` (a shipped unit refused at the door is returned without being
delivered). An exchange grows an existing replacement line or appends one with
``exchanged_from_ref`` and returns the original units; a variant is never edited
in place (ch.05 §155).

Errors are ``ProviderError`` kinds: an unknown order is MALFORMED_RESPONSE, a
refused cancel, exchange or return is CONTRACT_RESTRICTED, and a mutating call
sent without an answer is OUTCOME_UNKNOWN with ``transmitted=True``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Optional, Protocol, Tuple, runtime_checkable

from ..contracts import CartLineRequest, ObservedLine


@dataclass(frozen=True)
class FulfillmentLine:
    source_variant_ref: str
    ordered: int
    shipped: int = 0
    delivered: int = 0
    returned: int = 0
    cancelled: int = 0  # never shipped and no longer owed
    exchanged_from_ref: Optional[str] = None

    def to_observed(self) -> ObservedLine:
        return ObservedLine(self.source_variant_ref, self.ordered, self.shipped, self.delivered, self.returned,
                            self.exchanged_from_ref, self.cancelled)

    @property
    def open_units(self) -> int:  # not shipped and not cancelled
        return self.ordered - self.shipped - self.cancelled

    def check(self) -> None:
        if min(self.ordered, self.shipped, self.delivered, self.returned, self.cancelled) < 0:
            raise ValueError("negative fulfillment counter")
        if self.cancelled + self.shipped > self.ordered or self.delivered > self.shipped \
                or self.returned > self.shipped or self.ordered > 99:
            raise ValueError("fulfillment counters out of order")


@dataclass(frozen=True)
class FulfillmentRecord:
    fulfillment_id: str
    order_ref: str
    lines: Tuple[FulfillmentLine, ...]
    observed_at: datetime
    evidence_ref: str

    @property
    def shipped_any(self) -> bool:
        return any(l.shipped for l in self.lines)

    def open_units(self, ref: Optional[str] = None) -> int:
        return sum(l.open_units for l in self.lines if ref is None or l.source_variant_ref == ref)

    def owed_units(self) -> int:
        return sum(l.ordered - l.cancelled - l.returned for l in self.lines)

    def line(self, ref: str) -> Optional[FulfillmentLine]:
        return next((l for l in self.lines if l.source_variant_ref == ref), None)


@dataclass(frozen=True)
class FulfillmentRequest:
    idempotency_key: str
    order_ref: str
    lines: Tuple[CartLineRequest, ...]
    delivery_ref: str  # an opaque delivery reference; never an address


@dataclass(frozen=True)
class CancellationResult:
    order_ref: str
    cancelled: Tuple[Tuple[str, int], ...]  # (source_variant_ref, units actually cancelled)
    observed_at: datetime


@dataclass(frozen=True)
class ReturnAuthorization:
    return_ref: str
    order_ref: str
    source_variant_ref: str
    quantity: int
    status: str  # "requested" | "refused"
    observed_at: datetime


@dataclass(frozen=True)
class ExchangeRequest:
    idempotency_key: str
    order_ref: str
    from_ref: str
    to_ref: str
    quantity: int


@dataclass(frozen=True)
class FulfillmentEvent:
    fulfillment_id: str
    event_id: str
    event_type: str
    order_ref: str
    occurred_at: datetime


@runtime_checkable
class FulfillmentProvider(Protocol):
    fulfillment_id: str

    def open(self, request: FulfillmentRequest) -> FulfillmentRecord:
        """Idempotent on ``request.idempotency_key``."""
        ...

    def record(self, order_ref: str) -> FulfillmentRecord: ...

    def cancel_unshipped(self, order_ref: str, source_variant_ref: Optional[str], quantity: Optional[int], *,
                         idempotency_key: str) -> CancellationResult:
        """``None``/``None`` cancels every open unit. Idempotent on the key."""
        ...

    def authorize_return(self, order_ref: str, source_variant_ref: str, quantity: int, *,
                         idempotency_key: str) -> ReturnAuthorization: ...

    def request_exchange(self, request: ExchangeRequest) -> FulfillmentRecord: ...

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> Optional[FulfillmentEvent]:
        """``None``: no signature in this provider's scheme."""
        ...
