"""Normalized checkout quotes and their canonical hash (ch.05 §5 "Exact quote binding").

The quote hash is SHA-256 over the RFC 8785 (JCS) encoding of a versioned,
domain-separated document containing every *material* term. Display-only text
(titles, image URLs, marketing copy) is excluded so harmless copy edits do not
force re-approval; any material change produces a different hash and therefore
invalidates approvals bound to the old one.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import rfc8785

from .errors import InvalidQuote, QuoteExpired
from .money import Money, MoneyError, sum_money

# Versioned hash domain. Changing what is hashed requires a new version.
QUOTE_HASH_DOMAIN = "brandme.checkout_quote"
QUOTE_HASH_VERSION = "1"
TERMS_HASH_DOMAIN = "brandme.checkout_terms"
# The rule deciding materiality is recorded with every approval (ch.05 §5).
MATERIALITY_RULE = "brandme.quote.material.v1"
MATERIAL_FIELDS: Tuple[str, ...] = (
    "environment", "provider_id", "merchant_id", "payee_ref", "cart_id", "cart_revision",
    "lines[].variant_id", "lines[].source_variant_ref", "lines[].quantity",
    "lines[].unit_price", "lines[].line_total", "subtotal", "discount", "tax", "shipping",
    "total", "currency", "delivery_ref", "terms_hash", "checkout_reference", "expires_at",
)


def _sha256_prefixed(doc: Dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(doc)).hexdigest()


def _iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        raise InvalidQuote("timestamps must be timezone-aware UTC")
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class CheckoutTerms:
    """Return/recurrence terms. Their digest is a material term."""

    returnable: bool
    return_window_days: Optional[int]
    policy_ref: Optional[str] = None  # provider policy document reference
    recurring: bool = False

    def digest(self) -> str:
        if self.recurring:
            # Default fashion scope forbids recurring charges (ch.05 §5).
            raise InvalidQuote("recurring charges are outside the default purchase scope")
        return _sha256_prefixed({
            "domain": TERMS_HASH_DOMAIN, "version": "1",
            "returnable": self.returnable,
            "return_window_days": self.return_window_days,
            "recurring": self.recurring,
            "policy_ref": self.policy_ref,
        })


@dataclass(frozen=True)
class QuoteLine:
    variant_id: str
    source_variant_ref: str
    quantity: int
    unit_price: Money
    line_total: Money
    title: str = ""  # display only, not hashed
    category: str = ""  # used by delegation policy; not a price term

    def material(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "source_variant_ref": self.source_variant_ref,
            "quantity": self.quantity,
            "unit_price": self.unit_price.to_wire(),
            "line_total": self.line_total.to_wire(),
        }


@dataclass(frozen=True)
class CheckoutQuote:
    id: str
    environment: str
    provider_id: str
    merchant_id: str
    payee_ref: str
    cart_id: str
    cart_revision: int
    lines: Tuple[QuoteLine, ...]
    subtotal: Money
    tax: Money
    shipping: Money
    discount: Money
    total: Money
    delivery_ref: str
    terms: CheckoutTerms
    checkout_reference: str
    issued_at: datetime
    expires_at: datetime
    # Populated by ``seal``; never accepted from a caller.
    terms_hash: str = ""
    quote_hash: str = ""
    source_evidence_ref: Optional[str] = None

    @property
    def currency(self) -> str:
        return self.total.currency

    # -- validation ---------------------------------------------------------
    def validate(self) -> None:
        if not self.lines:
            raise InvalidQuote("quote has no lines")
        if len(self.lines) > 100:
            raise InvalidQuote("quote has too many lines")
        currency = self.total.currency
        try:
            for m in (self.subtotal, self.tax, self.shipping, self.discount):
                if m.currency != currency:
                    raise InvalidQuote("all quote components must share one currency")
            seen = set()
            for line in self.lines:
                if not 1 <= line.quantity <= 99:
                    raise InvalidQuote("line quantity out of range")
                if line.unit_price.currency != currency or line.line_total.currency != currency:
                    raise InvalidQuote("all quote components must share one currency")
                if line.unit_price.times(line.quantity) != line.line_total:
                    raise InvalidQuote(f"line total mismatch for {line.source_variant_ref}")
                if line.variant_id in seen:
                    raise InvalidQuote("duplicate variant line")
                seen.add(line.variant_id)
            if sum_money((l.line_total for l in self.lines), currency) != self.subtotal:
                raise InvalidQuote("subtotal does not equal the sum of line totals")
            computed = (self.subtotal + self.tax + self.shipping) - self.discount
        except MoneyError as exc:
            raise InvalidQuote(str(exc)) from exc
        if computed != self.total:
            raise InvalidQuote("total != subtotal + tax + shipping - discount")
        if self.expires_at <= self.issued_at:
            raise InvalidQuote("expiry must be after issue time")
        if self.cart_revision < 0:
            raise InvalidQuote("cart revision must be nonnegative")

    # -- canonical hash -----------------------------------------------------
    def material_document(self) -> Dict[str, Any]:
        return {
            "domain": QUOTE_HASH_DOMAIN,
            "version": QUOTE_HASH_VERSION,
            "environment": self.environment,
            "provider_id": self.provider_id,
            "merchant_id": self.merchant_id,
            "payee_ref": self.payee_ref,
            "cart_id": self.cart_id,
            "cart_revision": str(self.cart_revision),
            # Order lines deterministically so provider ordering noise does not matter.
            "lines": sorted((l.material() for l in self.lines), key=lambda d: d["variant_id"]),
            "subtotal": self.subtotal.to_wire(),
            "discount": self.discount.to_wire(),
            "tax": self.tax.to_wire(),
            "shipping": self.shipping.to_wire(),
            "total": self.total.to_wire(),
            "currency": self.currency,
            "delivery_ref": self.delivery_ref,
            "terms_hash": self.terms.digest(),
            "checkout_reference": self.checkout_reference,
            "expires_at": _iso(self.expires_at),
        }

    def compute_hash(self) -> str:
        return _sha256_prefixed(self.material_document())

    def seal(self) -> "CheckoutQuote":
        """Validate and return a copy carrying computed terms/quote hashes."""
        self.validate()
        from dataclasses import replace
        return replace(self, terms_hash=self.terms.digest(), quote_hash=self.compute_hash())

    def verify_seal(self) -> None:
        if not self.quote_hash or self.quote_hash != self.compute_hash():
            raise InvalidQuote("quote hash does not match its material terms")

    def ensure_fresh(self, now: datetime) -> None:
        if now >= self.expires_at:
            raise QuoteExpired("quote has expired; request a fresh quote")

    def to_wire(self) -> Dict[str, Any]:
        """Matches ``CheckoutQuote`` in contracts/domain.schema.json."""
        return {
            "id": self.id,
            "environment": self.environment,
            "provider_id": self.provider_id,
            "merchant_id": self.merchant_id,
            "payee_ref": self.payee_ref,
            "cart_id": self.cart_id,
            "cart_revision": str(self.cart_revision),
            "lines": [
                {"variant_id": l.variant_id, "source_variant_ref": l.source_variant_ref,
                 "quantity": l.quantity, "unit_price": l.unit_price.to_wire(),
                 "line_total": l.line_total.to_wire()}
                for l in self.lines
            ],
            "subtotal": self.subtotal.to_wire(),
            "tax": self.tax.to_wire(),
            "shipping": self.shipping.to_wire(),
            "discount": self.discount.to_wire(),
            "total": self.total.to_wire(),
            "delivery_ref": self.delivery_ref,
            "terms_hash": self.terms_hash,
            "quote_hash": self.quote_hash,
            "issued_at": _iso(self.issued_at),
            "expires_at": _iso(self.expires_at),
        }


def material_diff(old: CheckoutQuote, new: CheckoutQuote) -> List[str]:
    """Names of material top-level fields that differ (for the re-review comparison UI)."""
    a, b = old.material_document(), new.material_document()
    return sorted(k for k in a if a[k] != b.get(k))
