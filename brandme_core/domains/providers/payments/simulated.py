"""Deterministic in-process payment processor — SIMULATION ONLY.

Moves no money and talks to nothing. It keeps the same contract as a real
processor so the simulator merchant exercises every payment path: idempotent
authorization (a reused key with different terms is refused like Stripe's
idempotency error), a definitive decline, lost requests and lost responses,
partial capture, voids, partial and full refunds, and authorization expiry.
Absence is authoritative only once the caller says it is settled, as for Stripe.
"""

from __future__ import annotations

import enum
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from brandme_core.domains.commerce.money import Money

from ..contracts import ProviderError, ProviderErrorKind
from ..registry import SimulationInProductionError
from . import (RELEASE_REASONS, TEST_CARD, TEST_CARD_DECLINED, TEST_CARD_NEEDS_AUTHENTICATION, PaymentAuthorization,
               PaymentEvent, PaymentRailDescriptor, PaymentState, base_of)

# Card holds are not permanent; Stripe's manual-capture holds last about 7 days.
HOLD_TTL = timedelta(days=7)
SIMULATED_PAYMENT_LABEL = "Simulated payment — no real payment occurs."
_INSTRUMENTS = {TEST_CARD: None, "pm_card_mastercard": None, TEST_CARD_DECLINED: "card_declined",
                "pm_card_chargeDeclinedInsufficientFunds": "insufficient_funds",
                TEST_CARD_NEEDS_AUTHENTICATION: "authentication_required"}


class PaymentBehavior(str, enum.Enum):
    TIMEOUT_AFTER_ACCEPT = "timeout_after_accept"  # next authorization succeeds, its response is lost
    # Next call never arrives; nothing is applied. ``op`` (default "authorize") picks the call.
    LOST_BEFORE_PROCESSING = "lost_before_processing"
    RESPONSE_LOST = "response_lost"  # next capture/void/refund (``op``) is applied, then its response is lost
    AMOUNT_MISMATCH = "amount_mismatch"  # next authorization holds one minor unit more than requested


@dataclass
class _Payment:
    ref: str
    key: str
    purpose_ref: str
    payee_ref: str
    environment: str
    amount: Money
    status: str
    authorized_at: datetime
    captured: int = 0
    refunds: List[Tuple[str, int]] = field(default_factory=list)  # (idempotency key, amount); all succeeded
    decline_code: Optional[str] = None
    release_reason: Optional[str] = None
    requested: int = 0  # the amount the caller asked for (AMOUNT_MISMATCH holds one unit more)

    @property
    def refunded(self) -> int:
        return sum(a for _, a in self.refunds)


class SimulatedPaymentProcessor:
    processor_id = "simulated"
    simulation = True
    label = SIMULATED_PAYMENT_LABEL

    def __init__(self, clock: Callable[[], datetime], *, environment: str = "development",
                 payee_ref: str = "demo-payee"):
        if environment not in ("demo", "development"):
            raise SimulationInProductionError(f"simulated payment processor refused in {environment}")
        self._clock = clock
        self._environment = environment
        self.descriptor = PaymentRailDescriptor("simulated", "simulated", environment, SIMULATED_PAYMENT_LABEL,
                                                payee_ref, frozenset({"USD"}))
        self.test_instruments: Tuple[str, str] = (TEST_CARD, TEST_CARD_DECLINED)
        self._lock = threading.RLock()
        self._by_ref: Dict[str, _Payment] = {}
        self._by_key: Dict[str, str] = {}
        self._by_purpose: Dict[str, str] = {}
        # capture/void/refund idempotency key -> (payment ref, op, amount); recorded only after success
        self._ops: Dict[str, Tuple[str, str, int]] = {}
        self._armed: Dict[PaymentBehavior, dict] = {}
        self.calls: list = []  # (operation, key) — test evidence

    def arm(self, behavior: PaymentBehavior, **params) -> None:
        with self._lock:
            self._armed[behavior] = params

    def _take(self, behavior: PaymentBehavior, op: str) -> bool:
        params = self._armed.get(behavior)
        if params is None or params.get("op", "authorize") != op:
            return False
        del self._armed[behavior]
        return True

    @staticmethod
    def _lost(detail: str) -> ProviderError:
        return ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN, detail, transmitted=True)

    # -- state ---------------------------------------------------------------
    def _expire(self, p: _Payment) -> None:
        if p.status == "authorized" and self._clock() >= p.authorized_at + HOLD_TTL:
            p.status, p.release_reason = "voided", "authorization_expired"  # the processor releases the hold

    def _state(self, p: _Payment) -> PaymentState:
        self._expire(p)
        cur = p.amount.currency
        released = None
        if p.status == "voided":
            released = p.amount
        elif p.status in ("captured", "partially_refunded", "refunded") and p.captured < p.amount.amount_minor:
            released = Money(p.amount.amount_minor - p.captured, cur)
        reason = p.release_reason if p.status == "voided" else (
            "partial_capture_remainder" if released is not None else None)
        held = p.status in ("authorized", "captured", "partially_refunded", "refunded", "voided")
        return PaymentState(
            p.ref, p.status, p.amount, Money(p.captured, cur), Money(p.refunded, cur), self._clock(), p.decline_code,
            True, f"sim:payment_for:{p.purpose_ref}", released, reason,
            p.authorized_at + HOLD_TTL if held else None, p.purpose_ref, p.payee_ref, p.environment, p.key)

    def _get(self, ref: str) -> _Payment:
        p = self._by_ref.get(ref)
        if p is None:
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown payment")
        self._expire(p)
        return p

    def _replayed(self, key: str, ref: str, op: str, amount: int) -> bool:
        """True if this key already succeeded for exactly this call; a different call under it is refused."""
        prior = self._ops.get(key)
        if prior is None:
            return False
        if prior != (ref, op, amount):
            raise self._lost("idempotency key reused with different parameters")  # as Stripe's idempotency error
        return True

    # -- calls ---------------------------------------------------------------
    def authorize(self, request: PaymentAuthorization) -> PaymentState:
        with self._lock:
            self.calls.append(("authorize", request.idempotency_key))
            ref = self._by_key.get(request.idempotency_key)
            if ref:  # same key, same payment: never a second charge
                p = self._by_ref[ref]
                if (p.requested, p.amount.currency, p.purpose_ref, p.payee_ref, p.environment) != (
                        request.amount.amount_minor, request.amount.currency, request.purpose_ref, request.payee_ref,
                        request.environment):
                    raise self._lost("idempotency key reused with different parameters")
                return self._state(p)
            if self._take(PaymentBehavior.LOST_BEFORE_PROCESSING, "authorize"):
                raise self._lost("request lost in transit")
            if request.capture != "manual":
                raise ProviderError(ProviderErrorKind.UNSUPPORTED, "only manual capture is supported")
            if request.payee_ref != self.descriptor.payee_ref:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "payee_mismatch")
            if request.environment != self._environment:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "environment_mismatch")
            if request.amount.currency not in self.descriptor.currencies or request.amount.amount_minor <= 0:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "amount or currency not allowed")
            if request.payment_token_ref not in _INSTRUMENTS:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "unknown test payment method")
            amount = request.amount
            if self._take(PaymentBehavior.AMOUNT_MISMATCH, "authorize"):
                amount = Money(amount.amount_minor + 1, amount.currency)
            p = _Payment("simpay_" + secrets.token_hex(8), request.idempotency_key, request.purpose_ref,
                         request.payee_ref, request.environment, amount, "authorized", self._clock(),
                         requested=request.amount.amount_minor)
            outcome = _INSTRUMENTS[request.payment_token_ref]
            if outcome == "authentication_required":
                p.status = "requires_action"
            elif outcome:
                p.status, p.decline_code = "failed", outcome
            self._by_ref[p.ref], self._by_key[request.idempotency_key] = p, p.ref
            self._by_purpose[request.purpose_ref] = p.ref
            if self._armed.pop(PaymentBehavior.TIMEOUT_AFTER_ACCEPT, None) is not None:
                raise self._lost("payment response lost after acceptance")
            return self._state(p)

    def capture(self, payment_ref: str, amount: Money, *, idempotency_key: str) -> PaymentState:
        with self._lock:
            self.calls.append(("capture", idempotency_key))
            p = self._get(payment_ref)
            if self._replayed(idempotency_key, payment_ref, "capture", amount.amount_minor):
                return self._state(p)
            if self._take(PaymentBehavior.LOST_BEFORE_PROCESSING, "capture"):
                raise self._lost("request lost in transit")
            if p.status != "authorized":
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, f"cannot capture a {p.status} payment")
            if amount.currency != p.amount.currency or not 0 < amount.amount_minor <= p.amount.amount_minor:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "capture amount out of range")
            p.captured, p.status = amount.amount_minor, "captured"  # the uncaptured remainder is released
            self._ops[idempotency_key] = (payment_ref, "capture", amount.amount_minor)
            if self._take(PaymentBehavior.RESPONSE_LOST, "capture"):
                raise self._lost("capture response lost")
            return self._state(p)

    def void(self, payment_ref: str, *, idempotency_key: str, reason: str = "merchant_void") -> PaymentState:
        if reason not in RELEASE_REASONS:
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "unknown release reason")
        with self._lock:
            self.calls.append(("void", idempotency_key))
            p = self._get(payment_ref)
            if self._replayed(idempotency_key, payment_ref, "void", 0):
                return self._state(p)
            if self._take(PaymentBehavior.LOST_BEFORE_PROCESSING, "void"):
                raise self._lost("request lost in transit")
            if p.status != "voided":
                if p.status not in ("authorized", "requires_action"):
                    raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, f"cannot void a {p.status} payment")
                p.status, p.release_reason = "voided", reason
            self._ops[idempotency_key] = (payment_ref, "void", 0)
            if self._take(PaymentBehavior.RESPONSE_LOST, "void"):
                raise self._lost("void response lost")
            return self._state(p)

    def refund(self, payment_ref: str, amount: Money, *, idempotency_key: str) -> PaymentState:
        with self._lock:
            self.calls.append(("refund", idempotency_key))
            p = self._get(payment_ref)
            if self._replayed(idempotency_key, payment_ref, "refund", amount.amount_minor):
                return self._state(p)
            if self._take(PaymentBehavior.LOST_BEFORE_PROCESSING, "refund"):
                raise self._lost("request lost in transit")
            if p.status not in ("captured", "partially_refunded"):
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, f"cannot refund a {p.status} payment")
            if amount.currency != p.amount.currency or not 0 < amount.amount_minor <= p.captured - p.refunded:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "refund amount out of range")
            p.refunds.append((idempotency_key, amount.amount_minor))
            p.status = "refunded" if p.refunded >= p.captured else "partially_refunded"
            self._ops[idempotency_key] = (payment_ref, "refund", amount.amount_minor)
            if self._take(PaymentBehavior.RESPONSE_LOST, "refund"):
                raise self._lost("refund response lost")
            return self._state(p)

    # -- reads ---------------------------------------------------------------
    def lookup(self, payment_ref: str) -> PaymentState:
        with self._lock:
            return self._state(self._get(payment_ref))

    def find(self, purpose_ref: str, *, settled: bool) -> Optional[PaymentState]:
        with self._lock:
            ref = self._by_purpose.get(purpose_ref)
            if ref:
                return self._state(self._by_ref[ref])
        if not settled:
            raise ProviderError(ProviderErrorKind.TRANSIENT, "payment_lookup_unsettled")
        return None

    def operation_effect(self, payment_ref: str, idempotency_key: str) -> str:
        with self._lock:
            self._get(payment_ref)
            if base_of(idempotency_key) is None:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "not a payment operation key")
            prior = self._ops.get(idempotency_key)
            return "applied" if prior is not None and prior[0] == payment_ref else "absent"

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> Optional[PaymentEvent]:
        return None  # the simulated merchant's own signer covers simulated events

    def advance_hold(self, payment_ref: str) -> None:
        """Test control: age a hold past its expiry."""
        with self._lock:
            p = self._get(payment_ref)
            p.authorized_at = self._clock() - HOLD_TTL
