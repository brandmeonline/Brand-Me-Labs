"""Deterministic local commerce provider — SIMULATION ONLY (ch.05 §10).

"Demo Atelier — fictional" sells the six fictional demo garments from
``contracts/demo-scenario.json``. It exists to prove application behavior
under every required failure mode. It is not a retailer, nothing ships, and
the registry refuses it outside ``demo``/``development``.

It is a ``ComposedMerchantAdapter`` (``providers.merchant``): payments go through
an injected ``PaymentProcessor`` — the deterministic ``SimulatedPaymentProcessor``
by default, or Stripe **test mode** — and fulfillment through an injected
``FulfillmentProvider`` (``SimulatedFulfillment`` by default), both chosen at
startup by ``commerce.composition``. The merchant authorizes at submit (manual
capture), captures once at the first shipment for the value of the units still
owed, voids if every unit is cancelled before capture or the hold expires, and
refunds after capture. No real money moves on either rail.

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

STOCK_LOSS, PRICE_CHANGE and EXPIRED_QUOTE act on the catalog, before any
payment I/O. REJECTED_AUTH swaps the merchant's default test card for the
processor's declining one (on Stripe test mode, Stripe declines a real test
PaymentIntent). PARTIAL_FULFILLMENT goes to the fulfillment simulator.

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
Payment capabilities have no read-only test: a probe never moves test money.
"""

from __future__ import annotations

import enum
import secrets
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional, Sequence, Tuple

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from brandme_core.domains.commerce.money import Money
from brandme_core.domains.commerce.quote import CheckoutTerms

from .contracts import (
    CartLineRequest, CatalogPage, HandoffLink, InventoryObservation, ProbeResult, ProviderCart, ProviderError,
    ProviderErrorKind, ProviderQuote, QuotedLine, SetupProfile, SourceVariant, SubmitRequest,
)
from .fulfillment import FulfillmentProvider
from .fulfillment.simulated import SimulatedFulfillment
from .merchant import SETTLE_WINDOW, ComposedMerchantAdapter
from .payments import PaymentProcessor, payment_key  # noqa: F401  (payment_key re-exported for callers)
from .payments.simulated import SimulatedPaymentProcessor
from .registry import CapabilityStatus, ProviderConnection

PROVIDER_ID = "demo_atelier"
MERCHANT_ID = "fictional-demo-merchant"
SIMULATION_LABEL = "Simulated provider — Demo Atelier is fictional; no real order or payment occurs."
STRIPE_TEST_LABEL = ("Simulated provider — Demo Atelier is fictional and nothing ships. Payment runs in Stripe "
                     "test mode: no real money moves; only Stripe test cards are used.")
assert len(STRIPE_TEST_LABEL) <= 200 and len(SIMULATION_LABEL) <= 200
STRIPE_TEST_OPERATOR_NOTICE = ("Payments use Stripe test mode. No real money moves; only Stripe test cards are used. "
                               "Capability state is sandbox, never verified.")
# Reconciliation treats "no payment found" as final only after this long (Stripe search lags writes).
PAYMENT_SETTLE_WINDOW = SETTLE_WINDOW
_NS = uuid.UUID("6f1c2a0e-6c38-5d43-9a4e-6e0b9a1d2c11")  # fixed namespace for deterministic ids
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
STRIPE_TEST_SETUP_PROFILE = SetupProfile(
    summary=SETUP_PROFILE.summary + " " + STRIPE_TEST_LABEL,
    fixed_rows=(
        SETUP_PROFILE.fixed_rows[0],
        ("credentials", "credential", "Stripe test-mode secret key", "done",
         "Read from STRIPE_TEST_SECRET_KEY at startup; sk_test_ or restricted rk_test_ only; never displayed."),
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


class _ProbeFailed(Exception):
    def __init__(self, detail: str, reason_code: str):
        super().__init__(detail)
        self.reason_code = reason_code


class LocalAtelierProvider(ComposedMerchantAdapter):
    """Catalog/Feed/Inventory/Cart/Checkout/Order/Returns/Cancellation protocols and ``VerifiableProvider``."""

    provider_id = PROVIDER_ID
    merchant_id = MERCHANT_ID
    simulation = True

    def __init__(self, clock: Callable[[], datetime], *, quote_ttl: timedelta = timedelta(minutes=10),
                 payments: Optional[PaymentProcessor] = None, fulfillment: Optional[FulfillmentProvider] = None,
                 environment: str = "development"):
        super().__init__(clock, payments=payments or SimulatedPaymentProcessor(clock, environment=environment),
                         fulfillment=fulfillment or SimulatedFulfillment(clock), environment=environment)
        self._quote_ttl = quote_ttl
        # Simulated merchant checkout-signing key (AP2 Checkout JWT, ES256). Per process, never committed.
        self._merchant_key = ec.generate_private_key(ec.SECP256R1())
        self._stock: Dict[str, int] = {}
        self._price: Dict[str, int] = {}
        self._variants: Dict[str, SourceVariant] = {}
        self._carts: Dict[str, Tuple[CartLineRequest, ...]] = {}
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
    def setup_profile(self) -> SetupProfile:
        return SETUP_PROFILE if self.payments.descriptor.mode == "simulated" else STRIPE_TEST_SETUP_PROFILE

    @property
    def disclosure(self) -> str:
        """The member-facing label for this rail (catalog items, capabilities, handoff)."""
        return SIMULATION_LABEL if self.payments.descriptor.mode == "simulated" else STRIPE_TEST_LABEL

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
        return variant_uuid(source_variant_ref)  # pure: called inside commerce transactions

    # -- test/operator controls ----------------------------------------------
    def arm(self, behavior: Behavior, **params) -> None:
        behavior = Behavior(behavior)
        with self._lock:
            self._armed[behavior.value] = params
            if behavior is Behavior.STOCK_LOSS:
                self._stock[params["source_variant_ref"]] = 0
            elif behavior is Behavior.PRICE_CHANGE:
                self._price[params["source_variant_ref"]] = int(params["new_price_minor"])

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
                           self.disclosure, affiliate=False)

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

    # -- merchant hooks (in-process, no network) ---------------------------------
    def validate_checkout(self, request: SubmitRequest) -> Tuple[Optional[str], Tuple[CartLineRequest, ...]]:
        """Every merchant-side check before any payment I/O: cart, exact lines, stock, price."""
        cart_ref = request.checkout_reference.split("demo-checkout-", 1)[-1].rsplit("-", 1)[0]
        lines = self._carts.get(cart_ref)
        if lines is None:
            return "unknown_checkout", ()
        exact = lambda ls: sorted((l.source_variant_ref, l.quantity) for l in ls)  # noqa: E731
        if exact(lines) != exact(request.lines):
            return "checkout_changed", ()  # never buy what was not approved
        for l in lines:
            if self._stock[l.source_variant_ref] < l.quantity:
                return "out_of_stock", ()
        expected = sum(self._price[l.source_variant_ref] * l.quantity for l in lines)
        expected += expected * TAX_BPS // 10_000
        if expected != request.expected_total.amount_minor:
            return "price_changed", ()
        return None, tuple(lines)

    def reserve(self, units: Sequence[Tuple[str, int]]) -> None:
        for ref, qty in units:
            self._stock[ref] -= qty

    def release(self, units: Sequence[Tuple[str, int]]) -> None:
        for ref, qty in units:
            self._stock[ref] += qty

    def line_value_minor(self, source_variant_ref: str, quantity: int) -> int:
        unit = self._price[source_variant_ref] * quantity
        return unit + unit * TAX_BPS // 10_000

    def check_exchange(self, order_ref: str, from_ref: str, to_ref: str, quantity: int) -> None:
        with self._lock:
            if from_ref not in self._variants or to_ref not in self._variants:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "unknown replacement variant")
            if self._price[to_ref] != self._price[from_ref]:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED,
                                    "uneven exchange: return and buy the replacement instead")
            if not 1 <= quantity <= 99 or self._stock[to_ref] < quantity:
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "replacement out of stock")

    def move_exchange_stock(self, from_ref: str, to_ref: str, quantity: int) -> None:
        self._stock[to_ref] -= quantity
        self._stock[from_ref] += quantity

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
    rail = provider.payments.descriptor
    stripe_rail = rail.mode != "simulated"
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
        disclosure=provider.disclosure, capabilities=caps,
        access_level="simulation_stripe_test" if stripe_rail else "simulation",
        credential_ref="env:STRIPE_TEST_SECRET_KEY" if stripe_rail else None,
        data_use={"display_images": True, "cache_prices": True, "derive_3d": True},
        allowed_redirect_hosts=("demo-atelier.example.invalid",), adapter=provider,
        protocols={"ap2": "0.2"},  # simulated merchant; proves codec/flow behavior only
        merchant_public_keys={MERCHANT_ID: provider.merchant_public_key}, payment_rail=rail)
