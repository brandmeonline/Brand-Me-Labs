"""Payment processor seam for merchant adapters (ch.05 §6; ch.05 §157 "payment processing remains with
approved merchants/payment providers").

A payment processor is an internal collaborator of a merchant adapter, never a
Brand.Me merchant of record: the payee is the merchant named in the quote. The
commerce service never talks to a processor; it sees the merchant's order and
its ``payment_status``. Swapping the simulated processor for a real one is a
dependency-injection choice at startup (``brandme_core.domains.commerce.composition``),
never a runtime fallback.

Rules every processor follows:
* No card data. ``payment_token_ref`` is a processor-held payment method
  reference (a Stripe test ``pm_card_visa``, a simulator token); never a PAN, and
  never shown to a model.
* Every money-moving call carries an idempotency key the caller persisted
  before the call. A call that may have reached the processor but got no answer
  raises ``ProviderError(OUTCOME_UNKNOWN, transmitted=True)``; it is reconciled by
  repeating the same call with the same key, or by ``lookup``, never by a new key.
* Amounts are integer minor units in the quote currency. Refunds are positive
  amounts; partial capture releases the uncaptured remainder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Optional, Protocol, runtime_checkable

from brandme_core.domains.commerce.money import Money

# Normalized processor states. ``voided``: the authorization was released before capture
# (cancelled order or expired hold); no money moved. ``requires_action``: the payment needs the
# cardholder (e.g. 3-D Secure); merchants here void it, because nothing may redirect the member.
PAYMENT_STATES = ("authorized", "captured", "partially_refunded", "refunded", "voided", "failed",
                  "requires_action", "unknown")

# Instruments both rails accept: Stripe's documented test PaymentMethod ids. The simulated
# processor answers them the way Stripe test mode does, so armed failures behave alike.
TEST_CARD = "pm_card_visa"
TEST_CARD_DECLINED = "pm_card_chargeDeclined"
TEST_CARD_NEEDS_AUTHENTICATION = "pm_card_authenticationRequired"


@dataclass(frozen=True)
class PaymentAuthorization:
    idempotency_key: str  # persisted before the call; reused on every retry of this authorization
    amount: Money
    payee_ref: str  # the merchant being paid (from the quote), never Brand.Me
    purpose_ref: str  # what is being paid for: the provider order / checkout reference
    payment_token_ref: str  # processor-held payment method reference; never card data
    metadata: Mapping[str, str] = field(default_factory=dict)  # opaque references only


@dataclass(frozen=True)
class PaymentState:
    payment_ref: str  # processor's reference (e.g. a PaymentIntent id)
    status: str  # one of PAYMENT_STATES
    authorized: Money
    captured: Money
    refunded: Money
    observed_at: datetime
    decline_code: Optional[str] = None  # processor decline code, sanitized (e.g. "card_declined")
    test_mode: bool = True  # never False in this build: no live money movement
    evidence_ref: Optional[str] = None  # redacted pointer, never a raw processor body

    def __post_init__(self) -> None:
        if self.status not in PAYMENT_STATES:
            raise ValueError(f"unknown payment state {self.status}")
        if not self.test_mode:
            raise ValueError("live payment state refused: this build never moves real money")


@runtime_checkable
class PaymentProcessor(Protocol):
    processor_id: str  # e.g. "simulated", "stripe_test"
    simulation: bool  # True for the deterministic in-process processor
    label: str  # shown to members and operators, e.g. "Stripe test mode — no real money moves"

    def authorize(self, request: PaymentAuthorization) -> PaymentState: ...

    def capture(self, payment_ref: str, amount: Money, *, idempotency_key: str) -> PaymentState: ...

    def void(self, payment_ref: str, *, idempotency_key: str) -> PaymentState: ...

    def refund(self, payment_ref: str, amount: Money, *, idempotency_key: str) -> PaymentState: ...

    def lookup(self, payment_ref: str) -> PaymentState: ...

    def find(self, purpose_ref: str) -> Optional[PaymentState]:
        """The payment made for ``purpose_ref``, if any — reconciliation after a lost response.

        Never re-sends an authorization. ``None`` may lag a just-created payment (Stripe search
        is not read-after-write); callers treat absence as final only after a settle window.
        """
        ...
