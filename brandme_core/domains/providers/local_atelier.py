"""Deterministic local commerce provider — SIMULATION ONLY (ch.05 §10).

"Demo Atelier — fictional" sells the six fictional demo garments from
``contracts/demo-scenario.json``. It exists to prove application behavior
under every required failure mode. It is not a retailer, it never moves
money, and the registry refuses it outside ``demo``/``development``.

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
    OrderObservation, ProviderCart, ProviderError, ProviderErrorKind, ProviderQuote,
    ProviderResult, QuotedLine, SourceVariant, SubmitAck, SubmitRequest, WebhookEvent,
)
from .registry import CapabilityStatus, ProviderConnection

PROVIDER_ID = "demo_atelier"
MERCHANT_ID = "fictional-demo-merchant"
SIMULATION_LABEL = "Simulated provider — Demo Atelier is fictional; no real order or payment occurs."
_NS = uuid.UUID("6f1c2a0e-6c38-5d43-9a4e-6e0b9a1d2c11")  # fixed namespace for deterministic ids
WEBHOOK_TOLERANCE = timedelta(minutes=5)
TAX_BPS = 800  # fictional 8% demo tax, integer basis points


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
    idempotency_key: str
    lines: List[ObservedLine]
    total: Money
    order_status: str
    payment_status: str
    refunded: int
    created_at: datetime


class LocalAtelierProvider:
    """Implements Catalog/Feed/Inventory/Cart/Checkout/Order/Returns protocols."""

    provider_id = PROVIDER_ID
    simulation = True

    def __init__(self, clock: Callable[[], datetime], *, quote_ttl: timedelta = timedelta(minutes=10)):
        self._clock = clock
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
        self._armed: Dict[Behavior, dict] = {}
        self._event_seq = 0
        self.submit_calls: List[str] = []  # idempotency keys received (test evidence)
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
                merchant_id=MERCHANT_ID, payee_ref="demo-payee", lines=tuple(quoted),
                tax=Money(subtotal * TAX_BPS // 10_000, "USD"), shipping=Money(0, "USD"),
                discount=Money(0, "USD"), delivery_ref="demo-delivery",
                terms=CheckoutTerms(returnable=True, return_window_days=30, policy_ref="demo-returns-v1"),
                checkout_reference=f"demo-checkout-{cart.provider_cart_ref}-{subtotal}",
                expires_at=now + ttl, observed_at=now, evidence_ref=f"sim:{PROVIDER_ID}:quote")

    def submit(self, request: SubmitRequest) -> SubmitAck:
        now = self._clock()
        with self._lock:
            self.submit_calls.append(request.idempotency_key)
            existing = self._by_key.get(request.idempotency_key)
            if existing:  # provider-side idempotency: same key, same order, no second charge
                o = self._orders[existing]
                return SubmitAck(o.order_status == "accepted", o.ref, None, now, f"sim:{PROVIDER_ID}:order")
            if self._take(Behavior.REJECTED_AUTH) is not None:
                return SubmitAck(False, None, "payment_authorization_declined", now, f"sim:{PROVIDER_ID}:decline")
            cart_ref = request.checkout_reference.split("demo-checkout-", 1)[-1].rsplit("-", 1)[0]
            lines = self._carts.get(cart_ref)
            if lines is None:
                return SubmitAck(False, None, "unknown_checkout", now)
            for l in lines:
                if self._stock[l.source_variant_ref] < l.quantity:
                    return SubmitAck(False, None, "out_of_stock", now)
            expected = sum(self._price[l.source_variant_ref] * l.quantity for l in lines)
            expected += expected * TAX_BPS // 10_000
            if expected != request.expected_total.amount_minor:
                return SubmitAck(False, None, "price_changed", now)
            for l in lines:
                self._stock[l.source_variant_ref] -= l.quantity
            ref = "demo-order-" + secrets.token_hex(6)
            self._orders[ref] = _Order(ref, request.idempotency_key,
                                       [ObservedLine(l.source_variant_ref, l.quantity) for l in lines],
                                       request.expected_total, "accepted", "authorized", 0, now)
            self._by_key[request.idempotency_key] = ref
            if self._take(Behavior.TIMEOUT_AFTER_ACCEPT) is not None:
                raise ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN,
                                    "response timed out after transmission", transmitted=True)
            return SubmitAck(True, ref, None, now, f"sim:{PROVIDER_ID}:order:{ref}")

    # -- orders ----------------------------------------------------------------
    def _observe(self, o: _Order) -> OrderObservation:
        return OrderObservation(o.ref, o.order_status, o.payment_status, tuple(o.lines),
                                Money(o.refunded, "USD"), self._clock(), f"sim:{PROVIDER_ID}:order:{o.ref}")

    def lookup_by_idempotency_key(self, idempotency_key: str) -> Optional[OrderObservation]:
        with self._lock:
            ref = self._by_key.get(idempotency_key)
            return self._observe(self._orders[ref]) if ref else None

    def lookup(self, provider_order_ref: str) -> OrderObservation:
        with self._lock:
            o = self._orders.get(provider_order_ref)
            if o is None:
                raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unknown order")
            return self._observe(o)

    def request_return(self, provider_order_ref: str, source_variant_ref: str, quantity: int) -> ProviderResult:
        now = self._clock()
        return ProviderResult(PROVIDER_ID, "simulation", str(uuid.uuid4()),
                              f"demo-return-{provider_order_ref}-{source_variant_ref}", now, None, "requested")

    # -- simulated provider-side events (produce signed webhooks) -------------
    def capture(self, order_ref: str) -> List[Tuple[Dict[str, str], bytes]]:
        with self._lock:
            o = self._orders[order_ref]
            o.payment_status = "captured"
        return self._webhook(order_ref, "payment.captured")

    def ship(self, order_ref: str, *, deliver: bool = True) -> List[Tuple[Dict[str, str], bytes]]:
        partial = self._take(Behavior.PARTIAL_FULFILLMENT)
        with self._lock:
            o = self._orders[order_ref]
            new = []
            for l in o.lines:
                qty = l.quantity_ordered
                if partial is not None and l.source_variant_ref == partial.get("source_variant_ref", l.source_variant_ref):
                    qty = min(qty, int(partial.get("quantity", 1)))
                new.append(replace(l, quantity_shipped=max(l.quantity_shipped, qty),
                                   quantity_delivered=max(l.quantity_delivered, qty if deliver else 0)))
            o.lines = new
        return self._webhook(order_ref, "fulfillment.updated")

    def refund(self, order_ref: str) -> List[Tuple[Dict[str, str], bytes]]:
        params = self._take(Behavior.REFUND)
        if params is None:
            raise RuntimeError("arm Behavior.REFUND first")
        with self._lock:
            o = self._orders[order_ref]
            ref = params.get("source_variant_ref")
            qty = int(params.get("quantity", 0))
            amount = 0
            new = []
            for l in o.lines:
                if ref is None or l.source_variant_ref == ref:
                    q = qty or (l.quantity_ordered - l.quantity_returned)
                    unit = self._price[l.source_variant_ref]
                    amount += (unit * q) + (unit * q * TAX_BPS // 10_000)
                    l = replace(l, quantity_returned=l.quantity_returned + q)
                new.append(l)
            o.lines = new
            o.refunded = min(o.total.amount_minor, o.refunded + amount)
            o.payment_status = "refunded" if o.refunded >= o.total.amount_minor else "partially_refunded"
        return self._webhook(order_ref, "refund.completed")

    def _webhook(self, order_ref: str, event_type: str) -> List[Tuple[Dict[str, str], bytes]]:
        with self._lock:
            self._event_seq += 1
            event_id = f"demo-evt-{self._event_seq:06d}"
            dup = self._take(Behavior.DUPLICATE_WEBHOOK) is not None
        ts = str(int(self._clock().timestamp()))
        body = json.dumps({"id": event_id, "type": event_type, "order_ref": order_ref,
                           "simulation": True}, sort_keys=True).encode()
        sig = hmac.new(self._webhook_secret, ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        headers = {"x-demo-timestamp": ts, "x-demo-signature": f"v1={sig}"}
        return [(headers, body)] * (2 if dup else 1)

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent:
        h = {k.lower(): v for k, v in headers.items()}
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


def local_atelier_connection(provider: LocalAtelierProvider, environment: str,
                             checked_at: datetime) -> ProviderConnection:
    caps = {}
    for name in ("catalog.search", "catalog.detail", "catalog.feed", "inventory.read", "price.quote",
                 "cart.create", "cart.update", "checkout.submit", "orders.read", "orders.webhook",
                 "returns.request", "refunds.read", "checkout.handoff"):
        # Simulation never reaches "verified": it proves app behavior only.
        caps[name] = CapabilityStatus(name, "sandbox", "deterministic_local_simulation",
                                      checked_at, f"sim:{PROVIDER_ID}:{name}", "conformance_suite")
    return ProviderConnection(
        provider_id=PROVIDER_ID, display_name="Demo Atelier (simulated, fictional)",
        environment=environment, simulation=True, country_codes=("US",),
        disclosure=SIMULATION_LABEL, capabilities=caps, access_level="simulation",
        data_use={"display_images": True, "cache_prices": True, "derive_3d": True},
        allowed_redirect_hosts=("demo-atelier.example.invalid",), adapter=provider,
        protocols={"ap2": "0.2"},  # simulated merchant; proves codec/flow behavior only
        merchant_public_keys={MERCHANT_ID: provider.merchant_public_key})
