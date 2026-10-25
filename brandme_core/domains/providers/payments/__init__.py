"""Payment processor seam for merchant adapters (ch.05 §6; ch.05 §157 "payment processing remains with
approved merchants/payment providers").

A payment processor is an internal collaborator of a merchant adapter, never a
Brand.Me merchant of record: the payee is the merchant named in the quote. The
commerce service never talks to a processor; it sees the merchant's order and
its ``payment_status``. Swapping the simulated processor for a real one is a
dependency-injection choice at startup (``brandme_core.domains.commerce.composition``),
never a runtime fallback. No capability name exists for a processor: the closed
capability vocabulary stays as it is.

Rules every processor follows:
* No card data. ``payment_token_ref`` is a processor-held payment method
  reference (a Stripe test ``pm_card_visa``, a simulator token); never a PAN, and
  never shown to a model.
* Every money-moving call carries an idempotency key that is a pure function of
  the operation key the caller persisted before the call (``payment_key``). A call
  that may have reached the processor but got no answer raises
  ``ProviderError(OUTCOME_UNKNOWN, transmitted=True)``. An authorization is then
  resolved by reads only (``find``); a capture, void or refund by reading its
  effect (``operation_effect``) and, only if it is absent, re-sending the same key.
* Amounts are integer minor units in the quote currency. Refunds are positive
  amounts; a capture below the authorized amount releases the remainder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, FrozenSet, Mapping, Optional, Protocol, Tuple, runtime_checkable

from brandme_core.domains.commerce.money import Money

from ..registry import SimulationInProductionError

# Normalized processor states. ``voided``: the authorization was released before capture
# (cancelled order or expired hold); no money moved. ``requires_action``: the payment needs the
# cardholder (e.g. 3-D Secure); merchants here void it, because nothing may redirect the member.
PAYMENT_STATES = ("authorized", "captured", "partially_refunded", "refunded", "voided", "failed",
                  "requires_action", "unknown")
# Why held money was released without being taken.
RELEASE_REASONS = ("merchant_void", "authorization_expired", "orphan_authorization", "binding_mismatch",
                   "authentication_required", "not_authorized", "partial_capture_remainder")
PAYMENT_OPS = ("authorize", "capture", "void", "refund")
# How a processor was built. "live" is not representable in this build: no real money moves.
RAIL_MODES = ("simulated", "sandbox")
# Normalized decline codes; internal to the processor and merchant, never sent to a model or event.
DECLINE_CODES = ("card_declined", "insufficient_funds", "expired_card", "incorrect_cvc", "processing_error",
                 "authentication_required", "generic_decline", "other")

# Instruments both rails accept: Stripe's documented test PaymentMethod ids. The simulated
# processor answers them the way Stripe test mode does, so armed failures behave alike.
TEST_CARD = "pm_card_visa"
TEST_CARD_DECLINED = "pm_card_chargeDeclined"
TEST_CARD_NEEDS_AUTHENTICATION = "pm_card_authenticationRequired"

_BASE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_LABEL_MAX = 200


def payment_key(base: str, op: str, seq: Optional[int] = None) -> str:
    """Processor idempotency keys are a pure function of the persisted operation key."""
    if not isinstance(base, str) or not _BASE_RE.match(base):
        raise ValueError("payment key base must be 16-128 characters of [A-Za-z0-9_-]")
    if op not in PAYMENT_OPS:
        raise ValueError(f"unknown payment operation {op!r}")
    if seq is None:
        return f"{base}:{op}"
    if isinstance(seq, bool) or not isinstance(seq, int) or not 1 <= seq <= 999:
        raise ValueError("payment key sequence must be 1..999")
    return f"{base}:{op}:{seq}"


def base_of(key: Optional[str]) -> Optional[str]:
    """The operation key a payment key was derived from (``"bm-…:authorize"`` -> ``"bm-…"``)."""
    if not isinstance(key, str):
        return None
    parts = key.split(":")
    if len(parts) not in (2, 3) or not _BASE_RE.match(parts[0]) or parts[1] not in PAYMENT_OPS:
        return None
    if len(parts) == 3 and not (parts[2].isdigit() and 1 <= int(parts[2]) <= 999):
        return None
    return parts[0]


@dataclass(frozen=True)
class PaymentRailDescriptor:
    """What a merchant's payment rail is, for startup checks and operators. Never keys, secrets or accounts."""

    processor_id: str  # "simulated" | "stripe_test"
    mode: str  # RAIL_MODES
    environment: str
    label: str  # visible to members and operators
    payee_ref: str  # the party paid for a quote; bound into every quote hash
    currencies: FrozenSet[str] = frozenset({"USD"})
    api_version: Optional[str] = None
    webhooks_configured: bool = False

    def __post_init__(self) -> None:
        if self.mode not in RAIL_MODES:
            raise ValueError(f"unknown payment rail mode {self.mode!r}")
        if not isinstance(self.label, str) or not self.label.strip() or len(self.label) > _LABEL_MAX:
            raise ValueError("a payment rail needs a visible label of at most 200 characters")

    def to_operator(self) -> Dict[str, Any]:
        return {"processor_id": self.processor_id, "mode": self.mode, "label": self.label,
                "currencies": sorted(self.currencies), "api_version": self.api_version,
                "webhooks_configured": self.webhooks_configured}


def assert_payment_rail_allowed(environment: str, rail: PaymentRailDescriptor) -> None:
    """Startup check: a process refuses a rail its environment forbids. Never falls back."""
    if rail.environment != environment:
        raise ValueError("payment_rail_environment_mismatch")
    if rail.mode == "simulated" and environment not in ("demo", "development"):
        raise SimulationInProductionError(f"simulated payment rail refused in {environment}")
    if rail.mode == "sandbox" and environment not in ("demo", "development", "sandbox"):
        raise ValueError("payment_rail_not_allowed")


@dataclass(frozen=True)
class PaymentAuthorization:
    idempotency_key: str  # payment_key(base, "authorize"); reused on every retry of this authorization
    amount: Money  # the quote's all-in total (SubmitRequest.expected_total)
    payee_ref: str  # the merchant being paid (from the quote), never Brand.Me
    purpose_ref: str  # what is being paid for: the merchant order reference
    # Processor-held test PaymentMethod id; never PAN/CVV and never shown to a model.
    payment_token_ref: str = field(repr=False)
    metadata: Mapping[str, str] = field(default_factory=dict)  # allowlisted opaque references only
    environment: str = "development"  # bound into the payment and echoed back
    capture: str = "manual"  # authorize now, capture at shipment; nothing else is supported


@dataclass(frozen=True)
class PaymentState:
    payment_ref: str  # processor object id; "" when a decline created none
    status: str  # one of PAYMENT_STATES
    authorized: Money
    captured: Money
    refunded: Money  # succeeded refunds only
    observed_at: datetime
    decline_code: Optional[str] = None  # DECLINE_CODES; internal only
    test_mode: bool = True  # never False in this build: no live money movement
    # Constant per purpose ("stripe_test:payment_for:<order ref>"); never a processor object id.
    evidence_ref: Optional[str] = None
    released: Optional[Money] = None  # held and never taken
    release_reason: Optional[str] = None  # RELEASE_REASONS
    capture_before: Optional[datetime] = None  # the hold expires then; no capture after it
    # Echoes of what the authorization was bound to, as the processor recorded them.
    purpose_ref: Optional[str] = None
    payee_ref: Optional[str] = None
    environment: Optional[str] = None
    authorize_key: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in PAYMENT_STATES:
            raise ValueError(f"unknown payment state {self.status}")
        if not self.test_mode:
            raise ValueError("live payment state refused: this build never moves real money")
        if self.release_reason is not None and self.release_reason not in RELEASE_REASONS:
            raise ValueError(f"unknown release reason {self.release_reason}")


@dataclass(frozen=True)
class PaymentEvent:
    """A processor webhook after signature, replay and mode checks. Never a raw body; only a hint to re-read."""

    processor_id: str
    event_id: str
    event_type: str
    payment_ref: Optional[str]
    purpose_ref: Optional[str]
    environment: Optional[str]
    authorize_key: Optional[str]
    occurred_at: datetime


@runtime_checkable
class PaymentProcessor(Protocol):
    processor_id: str  # e.g. "simulated", "stripe_test"
    simulation: bool  # True for the deterministic in-process processor
    label: str  # == descriptor.label

    @property
    def descriptor(self) -> PaymentRailDescriptor: ...

    @property
    def test_instruments(self) -> Tuple[str, str]: ...  # (approves, declines)

    def authorize(self, request: PaymentAuthorization) -> PaymentState:
        """A decline is a result with status ``failed``; 3-D Secure is ``requires_action``."""
        ...

    def capture(self, payment_ref: str, amount: Money, *, idempotency_key: str) -> PaymentState: ...

    def void(self, payment_ref: str, *, idempotency_key: str, reason: str = "merchant_void") -> PaymentState: ...

    def refund(self, payment_ref: str, amount: Money, *, idempotency_key: str) -> PaymentState: ...

    def lookup(self, payment_ref: str) -> PaymentState: ...

    def find(self, purpose_ref: str, *, settled: bool) -> Optional[PaymentState]:
        """The payment made for ``purpose_ref`` — reconciliation after a lost response. Never re-sends.

        ``None`` only when absence is authoritative (``settled``). Absence before the settle
        window raises ``ProviderError(TRANSIENT, "payment_lookup_unsettled")``.
        """
        ...

    def operation_effect(self, payment_ref: str, idempotency_key: str) -> str:
        """``"applied"`` or ``"absent"`` for a capture, void or refund key; unreadable raises TRANSIENT."""
        ...

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> Optional[PaymentEvent]:
        """``None``: no signature in this processor's scheme. Bad signature or replay: UNAUTHORIZED.
        No webhook secret configured: NOT_CONFIGURED."""
        ...
