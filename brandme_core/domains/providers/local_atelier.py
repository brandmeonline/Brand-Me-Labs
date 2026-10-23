"""Deterministic local commerce provider — SIMULATION ONLY (ch.05 §10).

"Demo Atelier — fictional" sells the six fictional demo garments from
``contracts/demo-scenario.json``. It exists to prove application behavior
under every required failure mode. It is not a retailer, nothing ships, and
the registry refuses it outside ``demo``/``development``.

Payments go through an injected ``PaymentProcessor`` (``providers.payments``):
the deterministic ``SimulatedPaymentProcessor`` by default, or Stripe **test
mode**, chosen at startup by ``commerce.composition``. Either way the merchant
authorizes at submit (manual capture), captures once at the first shipment for
the value of the units still owed, voids if every unit is cancelled before
capture, and refunds after capture. No real money moves on either rail.

Failure behaviors are armed explicitly and deterministically:

=====================  ======================================================
behavior               effect
=====================  ======================================================
STOCK_LOSS             variant becomes unavailable; quote omits/refuses it
PRICE_CHANGE           unit price changes for the next quote
REJECTED_AUTH          submit is answered with a definitive payment decline
TIMEOUT_AFTER_ACCEPT   order is created, then the response is lost (timeout)
DUPLICATE_WEBHOOK      the next webhook is delivered twice (same event id)
PARTIAL_FULFILLMENT    ship/deliver only part of an order's quantity
REFUND                 refund all or part of an order (with return evidence)
EXPIRED_QUOTE          next quote expires almost immediately
=====================  ======================================================

``exchange()`` simulates an even exchange (same price, e.g. another size): the
original line records the return, a new line records the replacement with
``exchanged_from_ref``, and no money moves. A different-priced exchange is
refused; that is a return plus a new purchase. ``cancel()`` cancels units that
have not shipped, and ``expire_authorization()`` (simulated rail) ages the hold
past expiry, as for the demo scenario's ``authorization_expired``.

``probe()`` is the setup console's connection test: read-only exercises of this
simulator's own surface (search, detail, inventory, a scratch-cart quote that is
never submitted, a signed webhook round trip). Armed behaviors apply to it, so
``STOCK_LOSS`` on ``PROBE_VARIANT`` fails the quote test and an armed
``EXPIRED_QUOTE`` is consumed by it. Its evidence is ``conformance_suite``,
which the registry records as ``sandbox`` for a simulation, never ``verified``.
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import json
import secrets
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from brandme_core.domains.commerce.money import Money
from brandme_core.domains.commerce.quote import CheckoutTerms

from .contracts import (
    CartLineRequest, CatalogPage, HandoffLink, InventoryObservation, ObservedLine,
    OrderObservation, ProbeResult, ProviderCart, ProviderError, ProviderErrorKind, ProviderQuote,
    ProviderResult, QuotedLine, SetupProfile, SourceVariant, SubmitAck, SubmitRequest, WebhookEvent,
)
from .payments import (TEST_CARD, TEST_CARD_DECLINED, PaymentAuthorization, PaymentProcessor,
                       PaymentState)
from .payments.simulated import SimulatedPaymentProcessor
from .registry import CapabilityStatus, ProviderConnection

PROVIDER_ID = "demo_atelier"
MERCHANT_ID = "fictional-demo-merchant"
SIMULATION_LABEL = "Simulated provider — Demo Atelier is fictional; no real order or payment occurs."
STRIPE_TEST_LABEL = ("Simulated provider — Demo Atelier is fictional and nothing ships. Payment runs in Stripe "
                     "test mode: no real money moves; only Stripe test cards are used.")
# Reconciliation treats "no payment found" as final only after this long (Stripe search lags writes).
PAYMENT_SETTLE_WINDOW = timedelta(minutes=2)
_NS = uuid.UUID("6f1c2a0e-6c38-5d43-9a4e-6e0b9a1d2c11")  # fixed namespace for deterministic ids
WEBHOOK_TOLERANCE = timedelta(minutes=5)
TAX_BPS = 800  # fictional 8% demo tax, integer basis points
PROBE_VARIANT = "demo-overshirt-m"  # fixed, so a test can arm a deterministic probe failure
_PROBE_NOTE = "Simulation: fictional data; no real retailer, order or payment was involved."
SETUP_PROFILE = SetupProfile(
    summary=(SIMULATION_LABEL + " It exercises catalog, quote, checkout, order, webhook and return flows against "
             "fictional data so application behavior can be shown and tested. It proves nothing about a real "
             "retailer and never reaches verified."),
    fixed_rows=(
        ("prerequisites", "simulation_mode", "Runs only in demo or development", "done",
         "Selected at startup; the registry refuses this adapter in sandbox and production."),
        ("credentials", "credential", "No credential", "not_needed",
         "The simulation has no account or secret; nothing is entered here."),
    ))


class Behavior(str, enum.Enum):
    STOCK_LOSS = "stock_loss"
    PRICE_CHANGE = "price_change"
    REJECTED_AUTH = "rejected_auth"
    TIMEOUT_AFTER_ACCEPT = "timeout_after_accept"
    DUPLICATE_WEBHOOK = "duplicate_webhook"
    PARTIAL_FULFILLMENT = "partial_fulfillment"
    REFUND = "refund"
    EXPIRED_QUOTE = "expired_quote"


# (product uuid, slug, title, category, base price minor) — from demo-scenario.json
_PRODUCTS: Tuple[Tuple[str, str, str, str, int], ...] = (
    ("a4036cb0-7ab2-54b5-9238-ee5ffb378771", "overshirt", "Field Linen Overshirt", "top", 8900),
    ("6b4ee94a-4998-55d8-8298-c8f81a40b7aa", "trousers", "Soft Pleat Trousers", "bottom", 11900),
    ("9572fdc7-31e0-5b80-be82-147ef4a5e69c", "dress", "Evening Fluid Dress", "dress", 15900),
    ("5a0ccc0d-d627-52fa-ab80-de662ef92b1b", "jacket", "Structured Field Jacket", "outerwear", 17900),
    ("bdbff281-45f2-5887-b09b-6db9151126f6", "sneaker", "Everyday Low Sneaker", "shoes", 9900),
    ("21e655b5-f16d-57c8-bf99-c7af6e942c6f", "bag", "Sculpted Everyday Bag", "accessory", 12900),
)
_SIZES = ("s", "m", "l")


def variant_uuid(source_variant_ref: str) -> str:
    return str(uuid.uuid5(_NS, f"{PROVIDER_ID}:{source_variant_ref}"))


@dataclass
class _Order:
    ref: str
    idempotency_key: str  # the commerce operation's provider idempotency key; payment keys derive from it
    lines: List[ObservedLine]
    total: Money
    order_status: str  # pending (payment in flight) | accepted | rejected | cancelled
    created_at: datetime
    payment_ref: Optional[str] = None
    cancelled_value: int = 0  # value of units cancelled before capture, released at capture
    refund_seq: int = 0
    reason: Optional[str] = None


def payment_key(base: str, op: str, seq: Optional[int] = None) -> str:
    """Processor idempotency keys are a pure function of the persisted operation key."""
    return f"{base}:{op}" if seq is None else f"{base}:{op}:{seq}"


class _ProbeFailed(Exception):
    def __init__(self, detail: str, reason_code: str):
        super().__init__(detail)
        self.reason_code = reason_code


class LocalAtelierProvider:
    """Implements Catalog/Feed/Inventory/Cart/Checkout/Order/Returns protocols and ``VerifiableProvider``."""

    provider_id = PROVIDER_ID
    simulation = True
    setup_profile = SETUP_PROFILE

    def __init__(self, clock: Callable[[], datetime], *, quote_ttl: timedelta = timedelta(minutes=10),
                 payments: Optional[PaymentProcessor] = None, environment: str = "development"):
        self._clock = clock
        self.environment = environment
        self.payments: PaymentProcessor = payments or SimulatedPaymentProcessor(clock, environment=environment)
        # The party paid for a quote (bound into its hash). Brand.Me is never the payee.
        self.payee_ref = self.payments.descriptor.payee_ref
        self._lock = threading.RLock()
        self._quote_ttl = quote_ttl
        # Generated per process; never committed. Signs this simulator's webhooks only.
        self._webhook_secret = secrets.token_bytes(32)
        # Simulated merchant checkout-signing key (AP2 Checkout JWT, ES256). Per process, never committed.
        self._merchant_key = ec.generate_private_key(ec.SECP256R1())
        self._stock: Dict[str, int] = {}
        self._price: Dict[str, int] = {}
        self._variants: Dict[str, SourceVariant] = {}
        self._carts: Dict[str, Tuple[CartLineRequest, ...]] = {}
        self._orders: Dict[str, _Order] = {}
        self._by_key: Dict[str, str] = {}
        self._by_payment: Dict[str, str] = {}  # processor payment ref -> order ref
        self._pending_returns: Dict[Tuple[str, str], int] = {}  # (order ref, variant ref) -> units requested
        self._cancellations: Dict[str, str] = {}  # cancellation idempotency key -> outcome
        self._armed: Dict[Behavior, dict] = {}
        self._event_seq = 0
        self.submit_calls: List[str] = []  # idempotency keys received (test evidence)
        self.return_calls: List[Tuple[str, str, int]] = []  # return requests received (test evidence)
        epoch = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
        for pid, slug, title, category, price in _PRODUCTS:
            for size in _SIZES:
                ref = f"demo-{slug}-{size}"
                self._stock[ref] = 5
                self._price[ref] = price
                self._variants[ref] = SourceVariant(
                    provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID, source_product_id=pid,
                    source_variant_id=ref, brand="Demo Atelier", title=f"{title} — fictional demo",
                    category=category, size_system="alpha", size_label=size.upper(), color=None,
                    gtin=None, product_url=f"https://demo-atelier.example.invalid/p/{slug}?size={size}",
                    image_urls=(f"/demo/garments/{slug}/poster.webp",), price=Money(price, "USD"),
                    availability="in_stock", source_updated_at=epoch,
                    rights_policy_ref="original_demo_asset", description=f"{title}. Fictional demo garment.")

    @property
    def merchant_public_key(self):
        return self._merchant_key.public_key()

    def ucp_checkout(self, quote) -> dict:
        """UCP checkout document for a quote (what an AP2 merchant signs)."""
        return {
            "id": quote.checkout_reference,
            "merchant": {"id": MERCHANT_ID, "name": "Demo Atelier (simulated, fictional)"},
            "line_items": [{"id": f"li-{i}", "quantity": l.quantity,
                            "item": {"id": l.source_variant_ref, "title": l.title or l.source_variant_ref,
                                     "price": l.unit_price.amount_minor},
                            "totals": [{"type": "subtotal", "amount": l.line_total.amount_minor}]}
                           for i, l in enumerate(quote.lines)],
            "status": "ready_for_complete", "currency": quote.currency,
            "totals": [{"type": "subtotal", "amount": quote.subtotal.amount_minor},
                       {"type": "tax", "amount": quote.tax.amount_minor},
                       {"type": "fulfillment", "amount": quote.shipping.amount_minor},
                       {"type": "total", "amount": quote.total.amount_minor}],
            "links": [],
        }

    def signed_checkout_jwt(self, quote, **override) -> str:
        doc = self.ucp_checkout(quote)
        doc.update(override)
        return jwt.encode(doc, self._merchant_key, algorithm="ES256", headers={"kid": "demo-merchant-1"})

    def variant_id_for(self, source_variant_ref: str) -> str:
        return variant_uuid(source_variant_ref)

    # -- test/operator controls ----------------------------------------------
    def arm(self, behavior: Behavior, **params) -> None:
        with self._lock:
            self._armed[behavior] = params
            if behavior is Behavior.STOCK_LOSS:
                self._stock[params["source_variant_ref"]] = 0
            elif behavior is Behavior.PRICE_CHANGE:
                self._price[params["source_variant_ref"]] = int(params["new_price_minor"])

    def _take(self, behavior: Behavior) -> Optional[dict]:
        return self._armed.pop(behavior, None)

    def set_description(self, ref: str, text: str) -> None:
        """Lets security tests inject hostile provider text."""
        with self._lock:
            self._variants[ref] = replace(self._variants[ref], description=text)

    # -- catalog ---------------------------------------------------------------
    def _current(self, ref: str) -> SourceVariant:
        v = self._variants[ref]
        return replace(v, price=Money(self._price[ref], "USD"),
                       availability="in_stock" if self._stock[ref] > 0 else "out_of_stock")

    def search(self, query: str, *, cursor: Optional[str] = None, limit: int = 24) -> CatalogPage:
        q = (query or "").lower()
        refs = sorted(r for r, v in self._variants.items()
                      if not q or q in v.title.lower() or q in v.category)
        start = int(cursor or 0)
        page = refs[start:start + limit]
        nxt = str(start + limit) if start + limit < len(refs) else None
        return CatalogPage(tuple(self._current(r) for r in page), nxt)

    def detail(self, source_product_id: str) -> Tuple[SourceVariant, ...]:
        return tuple(self._current(r) for r in sorted(self._variants)
                     if self._variants[r].source_product_id == source_product_id)

    def feed_page(self, cursor: Optional[str]) -> CatalogPage:
        return self.search("", cursor=cursor, limit=6)

    def check(self, source_variant_ids: Sequence[str]) -> Tuple[InventoryObservation, ...]:
        now = self._clock()
        return tuple(InventoryObservation(r, self._stock.get(r, 0), now) for r in source_variant_ids)

    def handoff(self, source_product_id: str, source_variant_id: Optional[str]) -> HandoffLink:
        slug = next(s for p, s, *_ in _PRODUCTS if p == source_product_id)
        return HandoffLink(f"https://demo-atelier.example.invalid/p/{slug}", "Continue at Demo Atelier",
                           SIMULATION_LABEL, affiliate=False)

    # -- cart / checkout -------------------------------------------------------
    def create_cart(self, merchant_id: str, lines: Sequence[CartLineRequest]) -> ProviderCart:
        if merchant_id != MERCHANT_ID:
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "unknown merchant")
        self._validate_lines(lines)
        ref = "demo-cart-" + secrets.token_hex(8)
        with self._lock:
            self._carts[ref] = tuple(lines)
        return ProviderCart(ref, merchant_id, tuple(lines))

    def replace_cart(self, provider_cart_ref: str, lines: Sequence[CartLineRequest]) -> ProviderCart:
        self._validate_lines(lines)
        with self._lock:
            if provider_cart_ref not in self._carts:
                raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown cart")
            self._carts[provider_cart_ref] = tuple(lines)
        return ProviderCart(provider_cart_ref, MERCHANT_ID, tuple(lines))

    def _validate_lines(self, lines: Sequence[CartLineRequest]) -> None:
        for l in lines:
            if l.source_variant_ref not in self._variants or l.variant_id != variant_uuid(l.source_variant_ref):
                raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown variant")

    def quote(self, cart: ProviderCart) -> ProviderQuote:
        now = self._clock()
        with self._lock:
            lines = self._carts.get(cart.provider_cart_ref)
            if lines is None:
                raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown cart")
            quoted = []
            for l in lines:
                if self._stock[l.source_variant_ref] < l.quantity:
                    continue  # stock loss: the line cannot be quoted
                v = self._variants[l.source_variant_ref]
                quoted.append(QuotedLine(l.variant_id, l.source_variant_ref, l.quantity,
                                         Money(self._price[l.source_variant_ref], "USD"), v.title, v.category))
            subtotal = sum(q.unit_price.amount_minor * q.quantity for q in quoted)
            ttl = timedelta(seconds=1) if self._take(Behavior.EXPIRED_QUOTE) is not None else self._quote_ttl
            if not quoted:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "no purchasable lines (out of stock)")
            return ProviderQuote(
                merchant_id=MERCHANT_ID, payee_ref=self.payee_ref, lines=tuple(quoted),
                tax=Money(subtotal * TAX_BPS // 10_000, "USD"), shipping=Money(0, "USD"),
                discount=Money(0, "USD"), delivery_ref="demo-delivery",
                terms=CheckoutTerms(returnable=True, return_window_days=30, policy_ref="demo-returns-v1"),
                checkout_reference=f"demo-checkout-{cart.provider_cart_ref}-{subtotal}",
                expires_at=now + ttl, observed_at=now, evidence_ref=f"sim:{PROVIDER_ID}:quote")

    def submit(self, request: SubmitRequest) -> SubmitAck:
        now = self._clock()
        base = request.idempotency_key
        with self._lock:
            self.submit_calls.append(base)
            existing = self._by_key.get(base)
            if existing:  # provider-side idempotency: same key, same order, no second charge
                o = self._orders[existing]
                if o.order_status == "pending":
                    raise ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN, "submission in flight", transmitted=True)
                return SubmitAck(o.order_status == "accepted", o.ref if o.order_status == "accepted" else None,
                                 o.reason, now, f"sim:{PROVIDER_ID}:order:{o.ref}")
            # Every merchant-side check runs before any payment I/O.
            cart_ref = request.checkout_reference.split("demo-checkout-", 1)[-1].rsplit("-", 1)[0]
            lines = self._carts.get(cart_ref)
            if lines is None:
                return SubmitAck(False, None, "unknown_checkout", now)
            exact = lambda ls: sorted((l.source_variant_ref, l.quantity) for l in ls)  # noqa: E731
            if exact(lines) != exact(request.lines):
                return SubmitAck(False, None, "checkout_changed", now)  # never buy what was not approved
            for l in lines:
                if self._stock[l.source_variant_ref] < l.quantity:
                    return SubmitAck(False, None, "out_of_stock", now)
            expected = sum(self._price[l.source_variant_ref] * l.quantity for l in lines)
            expected += expected * TAX_BPS // 10_000
            if expected != request.expected_total.amount_minor:
                return SubmitAck(False, None, "price_changed", now)
            # The merchant's own intent is recorded (and stock held) before the network call.
            for l in lines:
                self._stock[l.source_variant_ref] -= l.quantity
            ref = "demo-order-" + hashlib.sha256(base.encode()).hexdigest()[:24]
            o = _Order(ref, base, [ObservedLine(l.source_variant_ref, l.quantity) for l in lines],
                       request.expected_total, "pending", now)
            self._orders[ref], self._by_key[base] = o, ref
            # An armed decline replaces only the merchant's default test card, never a supplied one.
            instrument = request.payment_token_ref or (
                TEST_CARD_DECLINED if self._take(Behavior.REJECTED_AUTH) is not None else TEST_CARD)
        try:
            pay = self.payments.authorize(PaymentAuthorization(
                payment_key(base, "authorize"), request.expected_total, self.payee_ref, ref, instrument,
                {"brandme_merchant": MERCHANT_ID, "brandme_simulated_merchant": "true"}, self.environment))
        except ProviderError as exc:
            if exc.transmitted or exc.kind is ProviderErrorKind.OUTCOME_UNKNOWN:
                raise ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN, "payment outcome unknown",
                                    transmitted=True) from None  # stays pending; reconcile resolves it
            self._settle(o, None, exc.kind.value)
            raise ProviderError(exc.kind, exc.detail) from None
        ack = self._settle(o, pay, None)
        if ack.accepted and self._take(Behavior.TIMEOUT_AFTER_ACCEPT) is not None:
            raise ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN,
                                "response timed out after transmission", transmitted=True)
        return ack

    def _settle(self, o: _Order, pay: Optional[PaymentState], failure: Optional[str]) -> SubmitAck:
        """Accept the pending order on a good authorization; otherwise release it (voiding what needs it)."""
        now = self._clock()
        reason = failure
        if pay is not None and failure is None:
            if pay.status == "authorized" and (pay.authorized != o.total):
                reason = "payment_binding_mismatch"
            elif pay.status == "requires_action":
                reason = "payment_authentication_required"  # nothing may redirect the member
            elif pay.status != "authorized":
                reason = "payment_authorization_declined"
            if reason and pay.status in ("authorized", "requires_action"):
                self.payments.void(pay.payment_ref, idempotency_key=payment_key(o.idempotency_key, "void"))
        with self._lock:
            if pay is not None:
                o.payment_ref = pay.payment_ref
                self._by_payment[pay.payment_ref] = o.ref
            if reason:
                for l in o.lines:
                    self._stock[l.source_variant_ref] += l.quantity_ordered
                o.order_status, o.reason = "rejected", reason
                return SubmitAck(False, None, reason, now, pay.evidence_ref if pay else None)
            o.order_status = "accepted"
            return SubmitAck(True, o.ref, None, now, f"sim:{PROVIDER_ID}:order:{o.ref}")

    # -- orders ----------------------------------------------------------------
    def _payment(self, o: _Order) -> Optional[PaymentState]:
        return self.payments.lookup(o.payment_ref) if o.payment_ref else None  # outside the lock: may be I/O

    def _observe(self, o: _Order, pay: Optional[PaymentState] = None) -> OrderObservation:
        pay = pay if pay is not None else self._payment(o)
        cur = o.total.currency
        if pay is not None and pay.status == "voided" and o.order_status == "accepted":
            with self._lock:  # an expired or released hold before anything shipped cancels the order
                if not any(l.quantity_shipped for l in o.lines):
                    self._cancel_units(o, None, None)
                    o.order_status = "cancelled"
        status = pay.status if pay is not None else "unknown"
        if status == "requires_action":
            status = "unknown"
        captured = pay.captured if pay is not None and status in ("captured", "partially_refunded", "refunded") else None
        refunded = min(pay.refunded.amount_minor, o.total.amount_minor) if pay is not None else 0
        evidence = f"sim:{PROVIDER_ID}:order:{o.ref}" + (f"|{pay.evidence_ref}" if pay and pay.evidence_ref else "")
        return OrderObservation(o.ref, o.order_status if o.order_status != "pending" else "accepted", status,
                                tuple(o.lines), Money(refunded, cur), self._clock(), evidence[:256], captured)

    def lookup_by_idempotency_key(self, idempotency_key: str) -> Optional[OrderObservation]:
        with self._lock:
            ref = self._by_key.get(idempotency_key)
            o = self._orders.get(ref) if ref else None
        if o is None or o.order_status == "rejected":
            return None  # authoritatively no order for this key
        if o.order_status == "pending":
            # The payment response was lost: find it by purpose. Never re-send the authorization.
            pay = self.payments.find(o.ref, settled=self._clock() - o.created_at >= PAYMENT_SETTLE_WINDOW)
            if pay is None:
                self._settle(o, None, "payment_not_found")
                return None
            if not self._settle(o, pay, None).accepted:
                return None
        return self._observe(o)

    def lookup(self, provider_order_ref: str) -> OrderObservation:
        with self._lock:
            o = self._orders.get(provider_order_ref)
        if o is None or o.order_status in ("pending", "rejected"):
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown order")
        return self._observe(o)

    def request_return(self, provider_order_ref: str, source_variant_ref: str, quantity: int) -> ProviderResult:
        now = self._clock()
        with self._lock:
            self.return_calls.append((provider_order_ref, source_variant_ref, quantity))
            slot = (provider_order_ref, source_variant_ref)
            self._pending_returns[slot] = self._pending_returns.get(slot, 0) + quantity
        return ProviderResult(PROVIDER_ID, "simulation", str(uuid.uuid4()),
                              f"demo-return-{provider_order_ref}-{source_variant_ref}", now, None, "requested")

    # -- simulated provider-side events (produce signed webhooks) -------------
    def _line_value(self, ref: str, qty: int) -> int:
        unit = self._price[ref] * qty
        return unit + unit * TAX_BPS // 10_000

    def _capture(self, o: _Order, pay: Optional[PaymentState]) -> Optional[PaymentState]:
        """Capture point: once, for the value of the units still owed; the processor releases the rest."""
        if pay is None or pay.status != "authorized" or o.cancelled_value >= o.total.amount_minor:
            return pay
        amount = Money(o.total.amount_minor - o.cancelled_value, o.total.currency)
        return self.payments.capture(o.payment_ref, amount, idempotency_key=payment_key(o.idempotency_key, "capture"))

    def capture(self, order_ref: str) -> List[Tuple[Dict[str, str], bytes]]:
        o = self._orders[order_ref]
        self._capture(o, self._payment(o))
        return self._webhook(order_ref, "payment.captured")

    def ship(self, order_ref: str, *, deliver: bool = True) -> List[Tuple[Dict[str, str], bytes]]:
        partial = self._take(Behavior.PARTIAL_FULFILLMENT)
        o = self._orders[order_ref]
        pay = self._payment(o)
        if pay is not None and pay.status == "voided":  # the hold expired or was released: nothing ships
            self._observe(o, pay)
            return self._webhook(order_ref, "order.cancelled")
        pay = self._capture(o, pay)
        if pay is not None and pay.status not in ("captured", "partially_refunded", "refunded"):
            raise ProviderError(ProviderErrorKind.TRANSIENT, "payment not captured; nothing shipped")
        with self._lock:
            new = []
            for l in o.lines:
                qty = l.quantity_ordered - l.quantity_cancelled  # cancelled units never ship
                if partial is not None and l.source_variant_ref == partial.get("source_variant_ref", l.source_variant_ref):
                    qty = min(qty, int(partial.get("quantity", 1)))
                new.append(replace(l, quantity_shipped=max(l.quantity_shipped, qty),
                                   quantity_delivered=max(l.quantity_delivered, qty if deliver else 0)))
            o.lines = new
        return self._webhook(order_ref, "fulfillment.updated")

    def _cancel_units(self, o: _Order, ref: Optional[str], qty: Optional[int]) -> int:
        """Cancel unshipped units (caller holds the lock); returns their value and restocks them."""
        value, new = 0, []
        for l in o.lines:
            if ref is None or l.source_variant_ref == ref:
                open_ = l.quantity_ordered - l.quantity_shipped - l.quantity_cancelled
                n = min(open_, qty) if qty else open_
                if n > 0:
                    value += self._line_value(l.source_variant_ref, n)
                    self._stock[l.source_variant_ref] += n
                    l = replace(l, quantity_cancelled=l.quantity_cancelled + n)
            new.append(l)
        o.lines = new
        return value

    def _release(self, o: _Order, pay: Optional[PaymentState], value: int) -> None:
        """Money for units no longer owed: void or reduce the uncaptured hold, or refund after capture."""
        if pay is None or value <= 0:
            return
        owed = sum(l.quantity_ordered - l.quantity_cancelled - l.quantity_returned for l in o.lines)
        if pay.status == "authorized":
            if owed == 0:
                self.payments.void(o.payment_ref, idempotency_key=payment_key(o.idempotency_key, "void"))
                with self._lock:
                    o.order_status = "cancelled"
            else:
                with self._lock:
                    o.cancelled_value += value  # released at capture
        elif pay.status in ("captured", "partially_refunded"):
            remaining = pay.captured.amount_minor - pay.refunded.amount_minor
            amount = remaining if owed == 0 else min(value, remaining)
            if amount > 0:
                with self._lock:
                    o.refund_seq += 1
                    seq = o.refund_seq
                self.payments.refund(o.payment_ref, Money(amount, o.total.currency),
                                     idempotency_key=payment_key(o.idempotency_key, "refund", seq))

    def cancel(self, order_ref: str, source_variant_ref: Optional[str] = None,
               quantity: Optional[int] = None) -> List[Tuple[Dict[str, str], bytes]]:
        """The merchant cancels units that have not shipped (all of them by default)."""
        o = self._orders[order_ref]
        pay = self._payment(o)
        with self._lock:
            value = self._cancel_units(o, source_variant_ref, quantity)
        if value == 0:
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "no unshipped units to cancel")
        self._release(o, pay, value)
        return self._webhook(order_ref, "fulfillment.cancelled")

    def request_cancellation(self, provider_order_ref: str, *, idempotency_key: str) -> ProviderResult:
        """Member-requested cancellation: the simulated merchant cancels every unshipped unit at once."""
        with self._lock:
            o = self._orders.get(provider_order_ref)
            done = self._cancellations.get(idempotency_key)
        if o is None or o.order_status not in ("accepted", "cancelled"):
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown order")
        if done is None:
            try:
                self.cancel(provider_order_ref)
                done = "cancelled"
            except ProviderError:
                done = "nothing_to_cancel"
            with self._lock:
                self._cancellations[idempotency_key] = done
        return ProviderResult(PROVIDER_ID, "simulation", idempotency_key, f"demo-cancel-{provider_order_ref}",
                              self._clock(), None, done)

    def expire_authorization(self, order_ref: str) -> None:
        """Simulated rail only: age the order's hold past expiry (demo scenario ``authorization_expired``)."""
        if not isinstance(self.payments, SimulatedPaymentProcessor):
            raise RuntimeError("a Stripe test-mode hold cannot be aged; use the simulated rail")
        self.payments.advance_hold(self._orders[order_ref].payment_ref)

    def exchange(self, order_ref: str, source_variant_ref: str, new_source_variant_ref: str,
                 quantity: int = 1) -> List[Tuple[Dict[str, str], bytes]]:
        with self._lock:
            o = self._orders[order_ref]
            original = next((l for l in o.lines if l.source_variant_ref == source_variant_ref), None)
            pending = self._pending_returns.get((order_ref, source_variant_ref), 0)  # units already being returned
            if original is None or not 1 <= quantity <= original.quantity_delivered - original.quantity_returned - pending:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "only delivered, unreturned units exchange")
            if new_source_variant_ref not in self._variants:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "unknown replacement variant")
            if self._price[new_source_variant_ref] != self._price[source_variant_ref]:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED,
                                    "uneven exchange: return and buy the replacement instead")
            if self._stock[new_source_variant_ref] < quantity:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "replacement out of stock")
            existing = next((l for l in o.lines if l.source_variant_ref == new_source_variant_ref), None)
            if existing is not None and existing.quantity_ordered + quantity > 99:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "replacement quantity out of range")
            self._stock[new_source_variant_ref] -= quantity
            self._stock[source_variant_ref] += quantity
            new = []
            for l in o.lines:
                if l.source_variant_ref == source_variant_ref:
                    l = replace(l, quantity_returned=l.quantity_returned + quantity)
                elif l.source_variant_ref == new_source_variant_ref:
                    # Back into a variant already on the order (e.g. M -> L -> M): the line grows; its
                    # earlier history (including its own return) is kept.
                    l = replace(l, quantity_ordered=l.quantity_ordered + quantity)
                new.append(l)
            if existing is None:
                new.append(ObservedLine(new_source_variant_ref, quantity, exchanged_from_ref=source_variant_ref))
            o.lines = new
        return self._webhook(order_ref, "exchange.created")

    def refund(self, order_ref: str) -> List[Tuple[Dict[str, str], bytes]]:
        """Refund units (armed ``REFUND``): unshipped ones are cancelled, shipped ones returned."""
        params = self._take(Behavior.REFUND)
        if params is None:
            raise RuntimeError("arm Behavior.REFUND first")
        o = self._orders[order_ref]
        pay = self._payment(o)
        ref = params.get("source_variant_ref")
        qty = int(params.get("quantity", 0))
        value = 0
        with self._lock:
            new = []
            for l in o.lines:
                if ref is None or l.source_variant_ref == ref:
                    q = qty or (l.quantity_ordered - l.quantity_returned - l.quantity_cancelled)
                    unshipped = min(q, l.quantity_ordered - l.quantity_shipped - l.quantity_cancelled)
                    value += self._line_value(l.source_variant_ref, q)
                    self._stock[l.source_variant_ref] += unshipped
                    l = replace(l, quantity_cancelled=l.quantity_cancelled + unshipped,
                                quantity_returned=l.quantity_returned + (q - unshipped))
                    slot = (order_ref, l.source_variant_ref)
                    if self._pending_returns.get(slot):  # requested returns that have now been received
                        self._pending_returns[slot] = max(0, self._pending_returns[slot] - (q - unshipped))
                new.append(l)
            o.lines = new
        self._release(o, pay, value)
        return self._webhook(order_ref, "refund.completed")

    def _webhook(self, order_ref: str, event_type: str) -> List[Tuple[Dict[str, str], bytes]]:
        with self._lock:
            self._event_seq += 1
            event_id = f"demo-evt-{self._event_seq:06d}"
            dup = self._take(Behavior.DUPLICATE_WEBHOOK) is not None
        return [self._signed(event_id, event_type, order_ref)] * (2 if dup else 1)

    def _signed(self, event_id: str, event_type: str, order_ref: str) -> Tuple[Dict[str, str], bytes]:
        ts = str(int(self._clock().timestamp()))
        body = json.dumps({"id": event_id, "type": event_type, "order_ref": order_ref,
                           "simulation": True}, sort_keys=True).encode()
        sig = hmac.new(self._webhook_secret, ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        return {"x-demo-timestamp": ts, "x-demo-signature": f"v1={sig}"}, body

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent:
        h = {k.lower(): v for k, v in headers.items()}
        if "stripe-signature" in h:
            return self._verify_payment_event(h, body)
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
        return WebhookEvent(PROVIDER_ID, data["id"], data["type"], data["order_ref"], sent, data)

    def _verify_payment_event(self, h: Mapping[str, str], body: bytes) -> WebhookEvent:
        """A payment processor's signed event for one of this merchant's payments. It is only a hint:
        the service dedupes it on its event id and re-reads the order, never trusting the payload."""
        if "x-demo-signature" in h:
            raise ProviderError(ProviderErrorKind.UNAUTHORIZED, "ambiguous signature scheme")
        verify = getattr(self.payments, "verify_webhook", None)
        if verify is None:
            raise ProviderError(ProviderErrorKind.UNAUTHORIZED, "this payment rail sends no webhooks")
        event = verify(h, body)
        if event is None:
            raise ProviderError(ProviderErrorKind.UNAUTHORIZED, "this payment rail sends no webhooks")
        with self._lock:
            order_ref = self._by_payment.get(event.payment_ref) if event.payment_ref else None
        if order_ref is None:
            raise ProviderError(ProviderErrorKind.UNSUPPORTED, "event for a payment this merchant does not hold")
        return WebhookEvent(PROVIDER_ID, f"{event.processor_id}:{event.event_id}"[:256],
                            f"payment.{event.event_type}"[:80], order_ref, event.occurred_at,
                            {"source": event.processor_id})


    # -- connection tests (operator setup console) -------------------------------
    _PROBES = {"catalog.search": "_probe_search", "catalog.detail": "_probe_detail",
               "inventory.read": "_probe_inventory", "price.quote": "_probe_quote",
               "orders.webhook": "_probe_webhook"}

    def probe(self, capability: str, mode: str, now: datetime) -> ProbeResult:
        """Read-only exercise of one capability. Never submits, captures, ships or returns anything."""
        if mode != "read_only_test":
            return ProbeResult("blocked", "none", f"blocked:{mode}_not_built",
                               f"The simulation has no {mode.replace('_', ' ')} test; run the read-only test.",
                               f"{mode}_not_built")
        method = self._PROBES.get(capability)
        if method is None:
            return ProbeResult("blocked", "none", "blocked:no_read_only_probe",
                               f"{capability} has no read-only test in the simulation: exercising it would create "
                               "or change a cart, order or return.", "no_read_only_probe")
        ref = f"sim:{PROVIDER_ID}:probe:{capability}:{now.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}"
        try:
            observed = getattr(self, method)()
        except ProviderError as e:
            return ProbeResult("failed", "conformance_suite", ref, f"The simulated {capability} call answered "
                               f"{e.kind.value}. {_PROBE_NOTE}", f"simulation_{e.kind.value}")
        except _ProbeFailed as e:
            return ProbeResult("failed", "conformance_suite", ref, f"{e} {_PROBE_NOTE}", e.reason_code)
        return ProbeResult("passed", "conformance_suite", ref, f"{observed} {_PROBE_NOTE}")

    def _probe_search(self) -> str:
        page = self.search("overshirt", limit=3)
        if not page.items or any(v.provider_id != PROVIDER_ID or not v.product_url.startswith("https://")
                                 for v in page.items):
            raise _ProbeFailed("Search returned no usable variants.", "search_empty")
        return f"Search returned {len(page.items)} fictional variants."

    def _probe_detail(self) -> str:
        variants = self.detail(self._variants[PROBE_VARIANT].source_product_id)
        if len(variants) != len(_SIZES):
            raise _ProbeFailed("Product detail did not return every variant.", "detail_incomplete")
        return f"Product detail returned {len(variants)} variants of one fictional product."

    def _probe_inventory(self) -> str:
        obs = self.check([PROBE_VARIANT])
        if len(obs) != 1 or obs[0].source_variant_id != PROBE_VARIANT or obs[0].available_quantity is None:
            raise _ProbeFailed("Inventory read returned no stock level.", "inventory_unreadable")
        return "Inventory read returned a stock level for one fictional variant."

    def _probe_quote(self) -> str:
        cart = self.create_cart(MERCHANT_ID, [CartLineRequest(variant_uuid(PROBE_VARIANT), PROBE_VARIANT, 1)])
        try:
            q = self.quote(cart)
        finally:
            with self._lock:  # scratch cart: quoted, never submitted, then discarded
                self._carts.pop(cart.provider_cart_ref, None)
        if q.expires_at - q.observed_at < timedelta(minutes=1):
            raise _ProbeFailed("The quote expired almost immediately.", "quote_expires_immediately")
        line = q.lines[0]
        return (f"Quoted a one-line scratch cart at {line.unit_price.amount_minor} {line.unit_price.currency} "
                "minor units; it was discarded without submitting.")

    def _probe_webhook(self) -> str:
        headers, body = self._signed("demo-evt-probe", "probe.ping", "demo-order-probe")
        if self.verify_webhook(headers, body).event_id != "demo-evt-probe":
            raise _ProbeFailed("A signed webhook did not round-trip.", "webhook_round_trip_failed")
        try:
            self.verify_webhook(headers, body.replace(b"probe.ping", b"probe.pong"))
        except ProviderError:
            return "Signed a webhook, verified it, and refused a tampered copy."
        raise _ProbeFailed("A tampered webhook was accepted.", "webhook_tamper_accepted")


PAYMENT_CAPABILITIES = ("checkout.submit", "orders.read", "orders.webhook", "refunds.read")


def local_atelier_connection(provider: LocalAtelierProvider, environment: str,
                             checked_at: datetime) -> ProviderConnection:
    """The merchant stays a simulation on either payment rail, so it is refused outside demo/development
    and can never be ``verified``. On the Stripe test rail, payment-touching capabilities say so and carry
    no evidence until a run exercises them."""
    stripe_rail = not provider.payments.simulation
    caps = {}
    for name in ("catalog.search", "catalog.detail", "catalog.feed", "inventory.read", "price.quote",
                 "cart.create", "cart.update", "checkout.submit", "orders.read", "orders.webhook",
                 "returns.request", "refunds.read", "checkout.handoff"):
        if stripe_rail and name in PAYMENT_CAPABILITIES:
            caps[name] = CapabilityStatus(name, "sandbox", "simulated_merchant_stripe_test_payments", checked_at)
            continue
        # Simulation never reaches "verified": it proves app behavior only.
        caps[name] = CapabilityStatus(name, "sandbox", "deterministic_local_simulation",
                                      checked_at, f"sim:{PROVIDER_ID}:{name}", "conformance_suite")
    return ProviderConnection(
        provider_id=PROVIDER_ID,
        display_name="Demo Atelier (simulated, fictional)" + (" · Stripe test mode" if stripe_rail else ""),
        environment=environment, simulation=True, country_codes=("US",),
        disclosure=STRIPE_TEST_LABEL if stripe_rail else SIMULATION_LABEL, capabilities=caps,
        access_level="simulation_stripe_test" if stripe_rail else "simulation",
        credential_ref="env:STRIPE_TEST_SECRET_KEY" if stripe_rail else None,
        data_use={"display_images": True, "cache_prices": True, "derive_3d": True},
        allowed_redirect_hosts=("demo-atelier.example.invalid",), adapter=provider,
        protocols={"ap2": "0.2"},  # simulated merchant; proves codec/flow behavior only
        merchant_public_keys={MERCHANT_ID: provider.merchant_public_key})
