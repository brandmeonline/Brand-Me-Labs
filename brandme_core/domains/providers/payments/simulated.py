"""Deterministic in-process payment processor — SIMULATION ONLY.

Moves no money and talks to nothing. It keeps the same contract as a real
processor so the simulator merchant exercises every payment path: idempotent
authorization, a definitive decline, a lost response after acceptance, partial
capture, voids, partial and full refunds, and authorization expiry.
"""

from __future__ import annotations

import enum
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional

from brandme_core.domains.commerce.money import Money

from ..contracts import ProviderError, ProviderErrorKind
from . import (TEST_CARD, TEST_CARD_DECLINED, TEST_CARD_NEEDS_AUTHENTICATION, PaymentAuthorization,
               PaymentState)

# Card holds are not permanent; Stripe's manual-capture holds last about 7 days.
HOLD_TTL = timedelta(days=7)
_INSTRUMENTS = {TEST_CARD: None, "pm_card_mastercard": None, TEST_CARD_DECLINED: "card_declined",
                "pm_card_chargeDeclinedInsufficientFunds": "insufficient_funds",
                TEST_CARD_NEEDS_AUTHENTICATION: "authentication_required"}


class PaymentBehavior(str, enum.Enum):
    TIMEOUT_AFTER_ACCEPT = "timeout_after_accept"  # next authorization succeeds, its response is lost
    LOST_BEFORE_PROCESSING = "lost_before_processing"  # next authorization never arrives; no payment exists


@dataclass
class _Payment:
    ref: str
    key: str
    purpose_ref: str
    amount: Money
    status: str
    captured: int
    refunded: int
    authorized_at: datetime
    decline_code: Optional[str] = None


class SimulatedPaymentProcessor:
    processor_id = "simulated"
    simulation = True
    label = "Simulated payment — no real payment occurs."

    def __init__(self, clock: Callable[[], datetime]):
        self._clock = clock
        self._lock = threading.RLock()
        self._by_ref: Dict[str, _Payment] = {}
        self._by_key: Dict[str, str] = {}
        self._by_purpose: Dict[str, str] = {}
        self._ops: Dict[str, str] = {}  # capture/void/refund idempotency key -> payment ref
        self._armed: Dict[PaymentBehavior, dict] = {}
        self.calls: list = []  # (operation, key) — test evidence

    def arm(self, behavior: PaymentBehavior, **params) -> None:
        with self._lock:
            self._armed[behavior] = params

    def _state(self, p: _Payment) -> PaymentState:
        self._expire(p)
        cur = p.amount.currency
        return PaymentState(p.ref, p.status, p.amount, Money(p.captured, cur), Money(p.refunded, cur),
                            self._clock(), p.decline_code, True, f"sim:payment:{p.ref}")

    def _expire(self, p: _Payment) -> None:
        if p.status == "authorized" and self._clock() - p.authorized_at >= HOLD_TTL:
            p.status, p.decline_code = "voided", "authorization_expired"

    def authorize(self, request: PaymentAuthorization) -> PaymentState:
        with self._lock:
            self.calls.append(("authorize", request.idempotency_key))
            ref = self._by_key.get(request.idempotency_key)
            if ref:  # same key, same payment: never a second charge
                return self._state(self._by_ref[ref])
            if self._armed.pop(PaymentBehavior.LOST_BEFORE_PROCESSING, None) is not None:
                raise ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN, "request lost in transit", transmitted=True)
            if request.payment_token_ref not in _INSTRUMENTS:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "unknown test payment method")
            p = _Payment("simpay_" + secrets.token_hex(8), request.idempotency_key, request.purpose_ref,
                         request.amount, "authorized", 0, 0, self._clock())
            outcome = _INSTRUMENTS[request.payment_token_ref]
            if outcome == "authentication_required":
                p.status, p.decline_code = "requires_action", outcome
            elif outcome:
                p.status, p.decline_code = "failed", outcome
            self._by_ref[p.ref], self._by_key[request.idempotency_key] = p, p.ref
            self._by_purpose[request.purpose_ref] = p.ref
            if self._armed.pop(PaymentBehavior.TIMEOUT_AFTER_ACCEPT, None) is not None:
                raise ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN, "payment response lost after acceptance",
                                    transmitted=True)
            return self._state(p)

    def _once(self, key: str, ref: str, op: str) -> bool:
        """True if this operation key already ran for this payment."""
        self.calls.append((op, key))
        prior = self._ops.get(key)
        if prior is not None and prior != ref:
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "idempotency key reused for another payment")
        self._ops[key] = ref
        return prior is not None

    def _get(self, ref: str) -> _Payment:
        p = self._by_ref.get(ref)
        if p is None:
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown payment")
        self._expire(p)
        return p

    def capture(self, payment_ref: str, amount: Money, *, idempotency_key: str) -> PaymentState:
        with self._lock:
            p = self._get(payment_ref)
            if self._once(idempotency_key, payment_ref, "capture"):
                return self._state(p)
            if p.status != "authorized":
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, f"cannot capture a {p.status} payment")
            if amount.currency != p.amount.currency or not 0 < amount.amount_minor <= p.amount.amount_minor:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "capture amount out of range")
            p.captured, p.status = amount.amount_minor, "captured"  # the uncaptured remainder is released
            return self._state(p)

    def void(self, payment_ref: str, *, idempotency_key: str) -> PaymentState:
        with self._lock:
            p = self._get(payment_ref)
            if self._once(idempotency_key, payment_ref, "void") or p.status == "voided":
                return self._state(p)
            if p.status not in ("authorized", "requires_action"):
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, f"cannot void a {p.status} payment")
            p.status = "voided"
            return self._state(p)

    def refund(self, payment_ref: str, amount: Money, *, idempotency_key: str) -> PaymentState:
        with self._lock:
            p = self._get(payment_ref)
            if self._once(idempotency_key, payment_ref, "refund"):
                return self._state(p)
            if p.status not in ("captured", "partially_refunded"):
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, f"cannot refund a {p.status} payment")
            if amount.currency != p.amount.currency or not 0 < amount.amount_minor <= p.captured - p.refunded:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "refund amount out of range")
            p.refunded += amount.amount_minor
            p.status = "refunded" if p.refunded >= p.captured else "partially_refunded"
            return self._state(p)

    def lookup(self, payment_ref: str) -> PaymentState:
        with self._lock:
            return self._state(self._get(payment_ref))

    def find(self, purpose_ref: str) -> Optional[PaymentState]:
        with self._lock:
            ref = self._by_purpose.get(purpose_ref)
            return self._state(self._by_ref[ref]) if ref else None

    def advance_hold(self, payment_ref: str) -> None:
        """Test control: age a hold past its expiry."""
        with self._lock:
            p = self._get(payment_ref)
            p.authorized_at = self._clock() - HOLD_TTL
