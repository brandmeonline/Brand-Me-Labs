"""A merchant adapter whose payment processor and fulfillment provider are injected collaborators.

``ComposedMerchantAdapter`` implements ``CheckoutProvider.submit``,
``OrderProvider``, ``ReturnsProvider`` and ``OrderCancellationProvider``. The
commerce service sees only those; the processor and the fulfillment provider
stay inside the merchant, and their effects reach Brand.Me only as the
``OrderObservation`` it returns. A concrete merchant (``LocalAtelierProvider``)
adds its catalog and implements a few pure hooks (checkout validation, stock,
line value, exchange rules, variant ids).

Money rules:

* Authorize at submit (manual capture), after every merchant-side check, so a
  price, stock or cart change never reaches the processor.
* Every authorization is bound to the order: amount, purpose (order ref),
  environment, payee and key are echoed back and checked. A mismatch, 3-D
  Secure, or any non-authorized answer is voided before the stock is released.
* Capture once, at the first shipment, for the total minus the value of units
  cancelled before capture. Void when every unit is cancelled before capture,
  or when the hold expires. Refund only after capture, for units no longer owed.
* An authorization is never re-sent: an unknown one is found by reads. A
  capture, void or refund whose answer was lost stays a pending money op
  (recorded before the call) and is settled by reading its effect; it is
  re-sent with the same key only when the effect is absent after the settle
  window and the key is still inside the processor's idempotency retention.
* No processor or fulfillment call is made while the ledger lock is held.
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import json
import re
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from brandme_core.domains.commerce.money import Money

from .contracts import (
    CartLineRequest, OrderObservation, ProviderError, ProviderErrorKind, ProviderResult, SubmitAck, SubmitRequest,
    WebhookEvent,
)
from .fulfillment import CancellationResult, ExchangeRequest, FulfillmentProvider, FulfillmentRecord, FulfillmentRequest
from .payments import PaymentAuthorization, PaymentEvent, PaymentProcessor, PaymentState, base_of, payment_key

# Absence of a payment is final only after this long (== the service's stale-submitting window, and longer
# than the processor client timeout plus processing). Stripe Search lags writes; the List scan does not.
SETTLE_WINDOW = timedelta(minutes=2)
# A lost capture/void/refund is re-sent under its key only inside Stripe's ~24 h idempotency retention.
RESEND_HORIZON = timedelta(hours=23)
WEBHOOK_TOLERANCE = timedelta(minutes=5)
ORDER_REF_RE = re.compile(r"^demo-order-[0-9a-f]{24}$")
_HELD = ("captured", "partially_refunded", "refunded")


def order_ref_for(base: str) -> str:
    """The merchant order reference is a pure function of the commerce operation's provider key."""
    return "demo-order-" + hashlib.sha256(base.encode()).hexdigest()[:24]


def _units(lines: Sequence[CartLineRequest]) -> List[Tuple[str, int]]:
    return [(l.source_variant_ref, l.quantity) for l in lines]


def _unknown(detail: str) -> ProviderError:
    return ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN, detail, transmitted=True)


@dataclass
class PendingMoneyOp:
    kind: str  # "capture" | "void" | "refund"
    key: str  # payment_key(base, kind[, seq])
    amount_minor: int  # 0 for a void
    reason: str  # a release reason, or first_shipment | return_received | cancelled_units | orphan_capture
    first_sent_at: datetime
    last_sent_at: datetime


@dataclass
class MerchantOrder:
    ref: str
    idempotency_key: str  # the commerce operation's provider key; every processor key derives from it
    lines: Tuple[CartLineRequest, ...]  # as ordered; per-line progress lives with the fulfillment provider
    total: Money
    order_status: str  # pending | voiding | accepted | rejected | cancelled
    created_at: datetime
    payment_ref: Optional[str] = None
    cancelled_value: int = 0  # value of units cancelled before capture, released at capture
    refund_seq: int = 0
    reason: Optional[str] = None
    release_reason: Optional[str] = None
    fulfillment_opened: bool = False
    pending: Dict[str, PendingMoneyOp] = field(default_factory=dict)  # written before processor I/O
    cancel_seq: int = 0
    exchange_seq: int = 0


class ComposedMerchantAdapter:
    provider_id: str = ""
    merchant_id: str = ""
    simulation: bool = True
    delivery_ref: str = "demo-delivery"

    def __init__(self, clock: Callable[[], datetime], *, payments: PaymentProcessor,
                 fulfillment: FulfillmentProvider, environment: str):
        if payments.descriptor.environment != environment:
            raise ValueError("payment_rail_environment_mismatch")
        self._clock = clock
        self.payments = payments
        self.fulfillment = fulfillment
        self.environment = environment
        self._lock = threading.RLock()
        # Generated per process; never committed. Signs this merchant's simulated webhooks only.
        self._webhook_secret = secrets.token_bytes(32)
        self._orders: Dict[str, MerchantOrder] = {}
        self._by_key: Dict[str, str] = {}
        self._by_payment: Dict[str, str] = {}  # processor payment ref -> order ref
        self._cancellations: Dict[str, str] = {}  # cancellation idempotency key -> outcome
        self._restocked: Set[str] = set()  # fulfillment cancel keys whose units went back to stock
        self._armed: Dict[str, dict] = {}
        self._event_seq = 0
        self._counters = {"orphans_voided": 0, "webhooks_ignored": 0, "money_ops_refused": 0}
        self.submit_calls: List[str] = []  # idempotency keys received (test evidence)
        self.return_calls: List[Tuple[str, str, int]] = []  # return requests received (test evidence)

    @property
    def payee_ref(self) -> str:
        """The party paid for a quote (bound into its hash). Brand.Me is never the payee."""
        return self.payments.descriptor.payee_ref

    # -- hooks the concrete merchant implements (pure or in-process; no network) ------
    def validate_checkout(self, request: SubmitRequest) -> Tuple[Optional[str], Tuple[CartLineRequest, ...]]:
        raise NotImplementedError

    def reserve(self, units: Sequence[Tuple[str, int]]) -> None:
        raise NotImplementedError

    def release(self, units: Sequence[Tuple[str, int]]) -> None:
        raise NotImplementedError

    def line_value_minor(self, source_variant_ref: str, quantity: int) -> int:
        raise NotImplementedError

    def check_exchange(self, order_ref: str, from_ref: str, to_ref: str, quantity: int) -> None:
        raise NotImplementedError

    def move_exchange_stock(self, from_ref: str, to_ref: str, quantity: int) -> None:
        raise NotImplementedError

    def variant_id_for(self, source_variant_ref: str) -> str:
        raise NotImplementedError

    # -- armed behaviours ------------------------------------------------------------
    def _take(self, behavior) -> Optional[dict]:
        name = behavior.value if isinstance(behavior, enum.Enum) else str(behavior)
        with self._lock:
            return self._armed.pop(name, None)

    def rail_health(self) -> Dict[str, int]:
        """Process-local counters for operators. Stuck money ops show here, never as order facts."""
        now = self._clock()
        with self._lock:
            ops = [op for rec in self._orders.values() for op in rec.pending.values()]
            return {"pending_money_ops": len(ops),
                    "needs_operator": sum(1 for op in ops if now - op.first_sent_at >= RESEND_HORIZON),
                    **self._counters}

    # -- helpers ---------------------------------------------------------------------
    def _order_evidence(self, ref: str) -> str:
        return f"sim:{self.provider_id}:order:{ref}"

    def _rec(self, order_ref: str) -> MerchantOrder:
        with self._lock:
            rec = self._orders.get(order_ref)
        if rec is None:
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown order")
        return rec

    def _live(self, order_ref: str) -> MerchantOrder:
        rec = self._rec(order_ref)
        if rec.order_status not in ("accepted", "cancelled"):
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown order")
        return rec

    def _reject(self, rec: MerchantOrder, reason: str) -> None:
        with self._lock:
            if rec.order_status in ("pending", "voiding"):
                self.release(_units(rec.lines))
                rec.order_status, rec.reason = "rejected", reason

    def _binding_ok(self, rec: MerchantOrder, pay: PaymentState) -> bool:
        return (pay.purpose_ref == rec.ref and pay.environment == self.environment and pay.payee_ref == self.payee_ref
                and pay.authorize_key == payment_key(rec.idempotency_key, "authorize"))

    def _metadata(self, request: SubmitRequest) -> Dict[str, str]:
        return {"brandme_provider": self.provider_id, "brandme_merchant": self.merchant_id,
                "brandme_quote_hash": request.quote_hash,
                "brandme_simulated_merchant": "true" if self.simulation else "false"}

    # -- money ops ---------------------------------------------------------------------
    def _send(self, rec: MerchantOrder, op: PendingMoneyOp) -> PaymentState:
        """Record the op, call the processor with the lock released, and settle the record by the answer."""
        with self._lock:
            op.last_sent_at = self._clock()
            rec.pending[op.key] = op
            cur = rec.total.currency
        try:
            if op.kind == "capture":
                state = self.payments.capture(rec.payment_ref, Money(op.amount_minor, cur), idempotency_key=op.key)
            elif op.kind == "void":
                state = self.payments.void(rec.payment_ref, idempotency_key=op.key, reason=op.reason)
            else:
                state = self.payments.refund(rec.payment_ref, Money(op.amount_minor, cur), idempotency_key=op.key)
        except ProviderError as exc:
            if exc.transmitted or exc.kind is ProviderErrorKind.OUTCOME_UNKNOWN:
                raise _unknown("payment outcome unknown") from None  # stays pending; settled by reading it
            with self._lock:
                rec.pending.pop(op.key, None)
                self._counters["money_ops_refused"] += 1
            raise
        except Exception:
            raise _unknown("payment outcome unknown") from None
        with self._lock:
            rec.pending.pop(op.key, None)
            if op.kind == "void":
                rec.release_reason = op.reason
        return state

    def _settle_pending(self, rec: MerchantOrder) -> None:
        with self._lock:
            ops = list(rec.pending.values())
        for op in ops:
            try:
                effect = self.payments.operation_effect(rec.payment_ref, op.key)
            except ProviderError:
                continue  # unreadable now; try again on the next read
            now = self._clock()
            if effect == "applied":
                with self._lock:
                    rec.pending.pop(op.key, None)
                    if op.kind == "void":
                        rec.release_reason = op.reason
            elif now - op.last_sent_at >= SETTLE_WINDOW and now - op.first_sent_at < RESEND_HORIZON:
                try:
                    self._send(rec, op)  # the same key and amount: never a second effect
                except ProviderError:
                    pass  # still unknown (kept) or refused (counted)
            # absent beyond the horizon: kept for an operator (rail_health.needs_operator)

    def _op(self, kind: str, key: str, amount: int, reason: str) -> PendingMoneyOp:
        now = self._clock()
        return PendingMoneyOp(kind, key, amount, reason, now, now)

    def _void(self, rec: MerchantOrder, reason: str) -> PaymentState:
        return self._send(rec, self._op("void", payment_key(rec.idempotency_key, "void"), 0, reason))

    # -- fulfillment ---------------------------------------------------------------------
    def _open_fulfillment(self, rec: MerchantOrder) -> None:
        if rec.fulfillment_opened:
            return
        self.fulfillment.open(FulfillmentRequest(f"{rec.idempotency_key}:fulfil", rec.ref, rec.lines, self.delivery_ref))
        with self._lock:
            rec.fulfillment_opened = True

    def _record(self, rec: MerchantOrder) -> FulfillmentRecord:
        self._open_fulfillment(rec)  # retried with the same key if the first open failed
        return self.fulfillment.record(rec.ref)

    def _cancel_units(self, rec: MerchantOrder, ref: Optional[str], qty: Optional[int], key: str) -> CancellationResult:
        """Cancel unshipped units at the fulfillment provider; their stock comes back exactly once per key."""
        self._open_fulfillment(rec)
        res = self.fulfillment.cancel_unshipped(rec.ref, ref, qty, idempotency_key=key)
        with self._lock:
            if key not in self._restocked:
                self._restocked.add(key)
                self.release(list(res.cancelled))
        return res

    # -- CheckoutProvider.submit --------------------------------------------------------
    def submit(self, request: SubmitRequest) -> SubmitAck:
        now = self._clock()
        base = request.idempotency_key
        with self._lock:
            self.submit_calls.append(base)
            ref = self._by_key.get(base)
            rec = self._orders.get(ref) if ref else None
            if rec is not None:  # merchant-side idempotency: same key, same order, never a second charge
                if rec.order_status in ("accepted", "cancelled"):
                    return SubmitAck(True, rec.ref, None, now, self._order_evidence(rec.ref))
                if rec.order_status in ("pending", "voiding"):
                    raise _unknown("submission in flight")
                return SubmitAck(False, None, rec.reason, now)
            if base_of(f"{base}:authorize") is None:
                return SubmitAck(False, None, "invalid_idempotency_key", now)
            if request.payee_ref is not None and request.payee_ref != self.payee_ref:
                return SubmitAck(False, None, "payee_changed", now)  # never pay someone the member did not approve
            # Every merchant-side check runs before any payment I/O.
            reason, lines = self.validate_checkout(request)
            if reason:
                return SubmitAck(False, None, reason, now)
            # The merchant's own intent is recorded (and stock held) before the network call.
            self.reserve(_units(lines))
            rec = MerchantOrder(order_ref_for(base), base, tuple(lines), request.expected_total, "pending", now)
            self._orders[rec.ref], self._by_key[base] = rec, rec.ref
            approves, declines = self.payments.test_instruments
            # An armed decline replaces only the merchant's default test card, never a supplied one.
            instrument = request.payment_token_ref or (
                declines if self._armed.pop("rejected_auth", None) is not None else approves)
        try:
            pay = self.payments.authorize(PaymentAuthorization(
                payment_key(base, "authorize"), request.expected_total, self.payee_ref, rec.ref, instrument,
                self._metadata(request), self.environment))
        except ProviderError as exc:
            if exc.transmitted or exc.kind is ProviderErrorKind.OUTCOME_UNKNOWN:
                raise _unknown("payment outcome unknown") from None  # stays pending; reconcile resolves it
            self._reject(rec, exc.kind.value)
            raise ProviderError(exc.kind, exc.detail) from None
        except Exception:
            raise _unknown("payment outcome unknown") from None
        ack = self._settle(rec, pay)
        if ack.accepted and self._take("timeout_after_accept") is not None:
            raise _unknown("response timed out after transmission")
        return ack

    def _settle(self, rec: MerchantOrder, pay: PaymentState) -> SubmitAck:
        """Accept on a bound authorization; otherwise void what is held, then release the order."""
        now = self._clock()
        if pay.payment_ref and not self._binding_ok(rec, pay):
            reason, release = "payment_binding_mismatch", "binding_mismatch"
        elif pay.status == "failed":
            self._reject(rec, "payment_authorization_declined")  # a decline holds nothing
            return SubmitAck(False, None, "payment_authorization_declined", now, pay.evidence_ref)
        elif pay.status == "authorized" and pay.authorized != rec.total:
            reason, release = "payment_binding_mismatch", "binding_mismatch"
        elif pay.status == "requires_action":
            reason, release = "payment_authentication_required", "authentication_required"  # never redirected
        elif pay.status != "authorized":
            reason, release = "payment_not_authorized", "not_authorized"
        else:
            reason = release = None
        with self._lock:
            if pay.payment_ref:
                rec.payment_ref = pay.payment_ref
                self._by_payment[pay.payment_ref] = rec.ref
            if reason is None:
                rec.order_status = "accepted"
        if reason is None:
            try:
                self._open_fulfillment(rec)
            except ProviderError:
                pass  # lookup opens it with the same key
            return SubmitAck(True, rec.ref, None, now, self._order_evidence(rec.ref))
        if pay.payment_ref:
            try:
                self._void(rec, release)
            except ProviderError:
                with self._lock:  # the stock stays held until the void resolves
                    rec.order_status, rec.reason = "voiding", reason
                raise _unknown("payment void outcome unknown") from None
        with self._lock:
            rec.release_reason = release
        self._reject(rec, reason)
        return SubmitAck(False, None, reason, now, pay.evidence_ref)

    # -- OrderProvider -------------------------------------------------------------------
    def lookup_by_idempotency_key(self, idempotency_key: str) -> Optional[OrderObservation]:
        base = idempotency_key
        with self._lock:
            ref = self._by_key.get(base)
            rec = self._orders.get(ref) if ref else None
        if rec is not None and rec.order_status in ("accepted", "cancelled"):
            return self.lookup(rec.ref)
        if rec is not None and rec.order_status == "rejected":
            if rec.reason == "payment_not_found":
                self._void_orphan(order_ref_for(base))  # a payment that surfaced late is released
            return None  # authoritatively no order for this key
        if rec is not None and rec.order_status == "voiding":
            return self._resolve_voiding(rec)
        settled = rec is None or self._clock() - rec.created_at >= SETTLE_WINDOW
        # The authorization's answer was lost: find it by purpose. Never re-send it.
        pay = self.payments.find(order_ref_for(base), settled=settled)  # TRANSIENT/THROTTLED propagate
        if rec is None:  # this merchant lost its ledger (restart): what it holds is released
            if pay is not None:
                self._release_orphan(pay, base)
            return None
        if pay is None:
            self._reject(rec, "payment_not_found")
            return None
        return self.lookup(rec.ref) if self._settle(rec, pay).accepted else None

    def _resolve_voiding(self, rec: MerchantOrder) -> Optional[OrderObservation]:
        self._settle_pending(rec)
        pay = self.payments.lookup(rec.payment_ref)
        if pay.status in ("authorized", "requires_action", "unknown"):
            try:
                pay = self._void(rec, rec.release_reason or "not_authorized")
            except ProviderError:
                raise ProviderError(ProviderErrorKind.TRANSIENT, "payment void pending") from None
        with self._lock:
            if rec.pending:
                raise ProviderError(ProviderErrorKind.TRANSIENT, "payment void pending")
        self._reject(rec, rec.reason or "payment_not_authorized")
        return None

    def _void_orphan(self, purpose_ref: str) -> None:
        try:
            pay = self.payments.find(purpose_ref, settled=True)
        except ProviderError:
            return
        if pay is not None:
            self._release_orphan(pay, base_of(pay.authorize_key) or purpose_ref, swallow=True)

    def _release_orphan(self, pay: PaymentState, base: str, *, swallow: bool = False) -> None:
        """Release a payment no order holds: void a hold, refund what was collected (seq 999)."""
        try:
            if pay.status in ("authorized", "requires_action"):
                self.payments.void(pay.payment_ref, idempotency_key=payment_key(base, "void"),
                                   reason="orphan_authorization")
                with self._lock:
                    self._counters["orphans_voided"] += 1
            elif pay.status in ("captured", "partially_refunded") and pay.captured > pay.refunded:
                self.payments.refund(pay.payment_ref, pay.captured - pay.refunded,
                                     idempotency_key=payment_key(base, "refund", 999))
        except ProviderError:
            if not swallow:
                raise ProviderError(ProviderErrorKind.TRANSIENT, "orphan_void_pending") from None

    def lookup(self, provider_order_ref: str) -> OrderObservation:
        with self._lock:
            rec = self._orders.get(provider_order_ref)
        if rec is None:
            return self._lost_ledger_observation(provider_order_ref)
        if rec.order_status not in ("accepted", "cancelled"):
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown order")
        self._settle_pending(rec)
        fr = self._record(rec)
        pay = self.payments.lookup(rec.payment_ref)  # a ProviderError keeps the receipt pending_reconcile
        pay = self._expiry_policy(rec, pay, fr)
        return self._observation(rec, pay, self.fulfillment.record(rec.ref))

    def _lost_ledger_observation(self, order_ref: str) -> OrderObservation:
        pay = self.payments.find(order_ref, settled=True)
        if pay is None:
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown order")
        self._release_orphan(pay, base_of(pay.authorize_key) or order_ref)
        after = self.payments.lookup(pay.payment_ref)
        status = after.status if after.status not in ("requires_action", "unknown") else "unknown"
        cur = after.authorized.currency
        return OrderObservation(order_ref, "cancelled", status, (),
                                Money(min(after.refunded.amount_minor, after.authorized.amount_minor), cur),
                                self._clock(), self._order_evidence(order_ref),
                                after.captured if status in _HELD else None)

    def _expiry_policy(self, rec: MerchantOrder, pay: PaymentState, fr: FulfillmentRecord) -> PaymentState:
        """No capture after a hold expires: void it and cancel what has not shipped. Idempotent."""
        now = self._clock()
        if fr.shipped_any:
            return pay
        if pay.status == "authorized" and pay.capture_before is not None and now >= pay.capture_before:
            pay = self._void(rec, "authorization_expired")
            self._cancel_units(rec, None, None, f"{rec.idempotency_key}:cancel:expiry")
            with self._lock:
                rec.order_status = "cancelled"
        elif pay.status == "voided" and rec.order_status == "accepted":  # released before anything shipped
            self._cancel_units(rec, None, None, f"{rec.idempotency_key}:cancel:released")
            with self._lock:
                rec.order_status = "cancelled"
                rec.release_reason = pay.release_reason or rec.release_reason or "merchant_void"
        return pay

    def _observation(self, rec: MerchantOrder, pay: PaymentState, fr: FulfillmentRecord) -> OrderObservation:
        status = pay.status if pay.status not in ("requires_action", "unknown") else "unknown"
        cur = rec.total.currency
        return OrderObservation(
            rec.ref, "cancelled" if rec.order_status == "cancelled" else "accepted", status,
            tuple(l.to_observed() for l in fr.lines), Money(min(pay.refunded.amount_minor, rec.total.amount_minor), cur),
            self._clock(), self._order_evidence(rec.ref), pay.captured if status in _HELD else None)

    # -- ReturnsProvider / OrderCancellationProvider ---------------------------------------
    def request_return(self, provider_order_ref: str, source_variant_ref: str, quantity: int) -> ProviderResult:
        rec = self._live(provider_order_ref)
        with self._lock:
            self.return_calls.append((provider_order_ref, source_variant_ref, quantity))
            n = len(self.return_calls)
        self._open_fulfillment(rec)
        ra = self.fulfillment.authorize_return(provider_order_ref, source_variant_ref, quantity,
                                               idempotency_key=f"{rec.idempotency_key}:return:{source_variant_ref}:{n}")
        if ra.status != "requested":
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "return refused")
        # A return request is not a refund: no money moves until the units come back.
        return ProviderResult(self.provider_id, "simulation", str(uuid.uuid4()), ra.return_ref, self._clock(), None,
                              "requested")

    def request_cancellation(self, provider_order_ref: str, *, idempotency_key: str) -> ProviderResult:
        """Member-requested cancellation: every unshipped unit, at once. Replays under the same key."""
        with self._lock:
            rec = self._orders.get(provider_order_ref)
            done = self._cancellations.get(idempotency_key)
        if rec is None or rec.order_status not in ("accepted", "cancelled"):
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown order")
        if done is None:
            key = f"{rec.idempotency_key}:cancel:m{hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]}"
            try:
                self._cancel(rec, None, None, key)
                done = "cancelled"
            except ProviderError as exc:
                if exc.kind is not ProviderErrorKind.CONTRACT_RESTRICTED:
                    raise  # unknown outcome: the same key re-sends the same cancellation
                done = "nothing_to_cancel"
            with self._lock:
                self._cancellations[idempotency_key] = done
        return ProviderResult(self.provider_id, "simulation", idempotency_key, f"demo-cancel-{provider_order_ref}",
                              self._clock(), None, done)

    # -- back office (simulator controls; a real merchant does these itself) ----------------
    def capture(self, order_ref: str) -> List[Tuple[Dict[str, str], bytes]]:
        rec = self._live(order_ref)
        self._settle_pending(rec)
        pay = self.payments.lookup(rec.payment_ref)
        if pay.status == "authorized" and rec.total.amount_minor - rec.cancelled_value > 0:
            self._capture(rec)
        return self._webhook(order_ref, "payment.captured")

    def _capture(self, rec: MerchantOrder) -> PaymentState:
        """The capture point: once, for the value of the units still owed; the processor releases the rest."""
        return self._send(rec, self._op("capture", payment_key(rec.idempotency_key, "capture"),
                                        rec.total.amount_minor - rec.cancelled_value, "first_shipment"))

    def ship(self, order_ref: str, *, deliver: bool = True) -> List[Tuple[Dict[str, str], bytes]]:
        rec = self._live(order_ref)
        partial = self._take("partial_fulfillment")
        self._settle_pending(rec)
        fr = self._record(rec)
        pay = self.payments.lookup(rec.payment_ref)
        now = self._clock()
        if pay.status == "voided" or (pay.status == "authorized" and pay.capture_before is not None
                                      and now >= pay.capture_before and not fr.shipped_any):
            self._expiry_policy(rec, pay, fr)  # the hold expired or was released: nothing ships
            return self._webhook(order_ref, "order.cancelled")
        if pay.status == "authorized" and rec.total.amount_minor - rec.cancelled_value > 0:
            pay = self._capture(rec)  # an unknown outcome re-raises: nothing ships until it is settled
        if pay.status not in _HELD:
            raise ProviderError(ProviderErrorKind.TRANSIENT, "payment not captured; nothing shipped")
        self.fulfillment.ship(order_ref, partial, deliver)
        return self._webhook(order_ref, "fulfillment.updated")

    def _cancel(self, rec: MerchantOrder, ref: Optional[str], qty: Optional[int], key: str) -> None:
        self._settle_pending(rec)
        pay = self.payments.lookup(rec.payment_ref)
        res = self._cancel_units(rec, ref, qty, key)
        value = sum(self.line_value_minor(r, u) for r, u in res.cancelled)
        if value == 0:
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "no unshipped units to cancel")
        self._release(rec, pay, value, "cancelled_units")

    def cancel(self, order_ref: str, source_variant_ref: Optional[str] = None,
               quantity: Optional[int] = None) -> List[Tuple[Dict[str, str], bytes]]:
        """The merchant cancels units that have not shipped (all of them by default)."""
        rec = self._live(order_ref)
        with self._lock:
            rec.cancel_seq += 1
            key = f"{rec.idempotency_key}:cancel:{rec.cancel_seq}"
        self._cancel(rec, source_variant_ref, quantity, key)
        return self._webhook(order_ref, "fulfillment.cancelled")

    def _release(self, rec: MerchantOrder, pay: PaymentState, value: int, reason: str) -> None:
        """Money for units no longer owed: void or reduce the uncaptured hold, or refund after capture."""
        if value <= 0:
            return
        owed = self.fulfillment.record(rec.ref).owed_units()
        if pay.status == "authorized":
            if owed == 0:
                self._void(rec, "merchant_void")
                with self._lock:
                    rec.order_status = "cancelled"
            else:
                with self._lock:
                    rec.cancelled_value += value  # released at capture
        elif pay.status in ("captured", "partially_refunded"):
            remaining = pay.captured.amount_minor - pay.refunded.amount_minor
            amount = remaining if owed == 0 else min(value, remaining)  # the last units return exactly the rest
            if amount > 0:
                with self._lock:  # the sequence is taken before I/O, so a lost answer never reuses it
                    rec.refund_seq += 1
                    seq = rec.refund_seq
                self._send(rec, self._op("refund", payment_key(rec.idempotency_key, "refund", seq), amount, reason))

    def refund(self, order_ref: str) -> List[Tuple[Dict[str, str], bytes]]:
        """Refund units (armed ``REFUND``): unshipped ones are cancelled, shipped ones returned."""
        params = self._take("refund")
        if params is None:
            raise RuntimeError("arm Behavior.REFUND first")
        rec = self._live(order_ref)
        self._settle_pending(rec)
        fr = self._record(rec)
        pay = self.payments.lookup(rec.payment_ref)
        ref = params.get("source_variant_ref")
        qty = int(params.get("quantity", 0))
        value = 0
        with self._lock:
            rec.cancel_seq += 1
            n = rec.cancel_seq
        for line in fr.lines:
            if ref is not None and line.source_variant_ref != ref:
                continue
            q = qty or (line.ordered - line.returned - line.cancelled)
            unshipped = min(q, line.open_units)
            if unshipped:
                self._cancel_units(rec, line.source_variant_ref, unshipped,
                                   f"{rec.idempotency_key}:cancel:{n}:{line.source_variant_ref}")
            if q - unshipped:
                self.fulfillment.receive_return(order_ref, line.source_variant_ref, q - unshipped)
            value += self.line_value_minor(line.source_variant_ref, q)
        self._release(rec, pay, value, "return_received")  # a lost answer re-raises; the next lookup settles it
        return self._webhook(order_ref, "refund.completed")

    def exchange(self, order_ref: str, source_variant_ref: str, new_source_variant_ref: str,
                 quantity: int = 1) -> List[Tuple[Dict[str, str], bytes]]:
        """An even exchange: the original units are returned, the replacement is added. No money moves."""
        rec = self._live(order_ref)
        self.check_exchange(order_ref, source_variant_ref, new_source_variant_ref, quantity)
        with self._lock:
            rec.exchange_seq += 1
            key = f"{rec.idempotency_key}:exchange:{rec.exchange_seq}"
        self._open_fulfillment(rec)
        self.fulfillment.request_exchange(ExchangeRequest(key, order_ref, source_variant_ref, new_source_variant_ref,
                                                          quantity))
        with self._lock:
            self.move_exchange_stock(source_variant_ref, new_source_variant_ref, quantity)
        return self._webhook(order_ref, "exchange.created")

    def expire_authorization(self, order_ref: str) -> None:
        """Simulated rail only: age the order's hold past expiry (demo scenario ``authorization_expired``)."""
        if self.payments.descriptor.mode != "simulated":
            raise ProviderError(ProviderErrorKind.UNSUPPORTED, "a Stripe test-mode hold cannot be aged")
        self.payments.advance_hold(self._live(order_ref).payment_ref)

    # -- webhooks ------------------------------------------------------------------------------
    def _webhook(self, order_ref: str, event_type: str) -> List[Tuple[Dict[str, str], bytes]]:
        with self._lock:
            self._event_seq += 1
            event_id = f"demo-evt-{self._event_seq:06d}"
            dup = self._armed.pop("duplicate_webhook", None) is not None
        return [self._signed(event_id, event_type, order_ref)] * (2 if dup else 1)

    def _signed(self, event_id: str, event_type: str, order_ref: str) -> Tuple[Dict[str, str], bytes]:
        ts = str(int(self._clock().timestamp()))
        body = json.dumps({"id": event_id, "type": event_type, "order_ref": order_ref,
                           "simulation": True}, sort_keys=True).encode()
        sig = hmac.new(self._webhook_secret, ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        return {"x-demo-timestamp": ts, "x-demo-signature": f"v1={sig}"}, body

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent:
        """A signed hint to re-read the order; the service dedupes it and never trusts its payload."""
        h = {str(k).lower(): v for k, v in headers.items()}
        if "stripe-signature" in h and "x-demo-signature" in h:
            raise ProviderError(ProviderErrorKind.UNAUTHORIZED, "ambiguous signature scheme")
        pev = self.payments.verify_webhook(h, body)  # raises on a bad signature, a replay or no secret
        if pev is not None:
            return self._payment_event(pev)
        fev = self.fulfillment.verify_webhook(h, body)
        if fev is not None:
            return WebhookEvent(self.provider_id, f"{fev.fulfillment_id}:{fev.event_id}"[:256],
                                f"fulfillment.{fev.event_type}"[:80], fev.order_ref, fev.occurred_at,
                                {"source": fev.fulfillment_id})
        ts, sig = h.get("x-demo-timestamp"), h.get("x-demo-signature", "")
        if not ts or not ts.isdigit() or not sig.startswith("v1="):
            raise ProviderError(ProviderErrorKind.UNAUTHORIZED, "missing webhook signature")
        expected = hmac.new(self._webhook_secret, ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig[3:]):
            raise ProviderError(ProviderErrorKind.UNAUTHORIZED, "invalid webhook signature")
        sent = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        if abs(self._clock() - sent) > WEBHOOK_TOLERANCE:
            raise ProviderError(ProviderErrorKind.UNAUTHORIZED, "webhook outside replay window")
        data = json.loads(body)
        return WebhookEvent(self.provider_id, data["id"], data["type"], data["order_ref"], sent, data)

    def _payment_event(self, pev: PaymentEvent) -> WebhookEvent:
        event_id = f"{pev.processor_id}:{pev.event_id}"[:256]
        event_type = f"payment.{pev.event_type}"[:80]
        source = {"source": pev.processor_id}
        with self._lock:
            ref = self._by_payment.get(pev.payment_ref) if pev.payment_ref else None
            if ref is None and pev.purpose_ref in self._orders:
                ref = pev.purpose_ref
            rec = self._orders.get(ref) if ref else None
        if rec is not None and rec.order_status != "rejected":
            return WebhookEvent(self.provider_id, event_id, event_type, rec.ref, pev.occurred_at, source)
        if pev.environment == self.environment and pev.purpose_ref and ORDER_REF_RE.match(pev.purpose_ref):
            # This merchant's kind of payment, but no live order holds it (rejected as not found, or the
            # ledger was lost): release a hold it still has, then acknowledge the event as not ours to apply.
            self._void_orphan(pev.purpose_ref)
            return WebhookEvent(self.provider_id, event_id, event_type, pev.purpose_ref, pev.occurred_at, source,
                                relevant=False)
        with self._lock:  # another app or environment on the same processor account
            self._counters["webhooks_ignored"] += 1
        return WebhookEvent(self.provider_id, event_id, event_type, "", pev.occurred_at, source, relevant=False)
