"""Stripe payment processor — TEST MODE ONLY (no real money moves).

Uses PaymentIntents with manual capture: authorize when the merchant accepts the
order, capture on shipment, void if the order is cancelled before capture, refund
afterwards. Guards, in order of importance:

* Only test-mode keys (``sk_test_…`` or the least-privilege restricted ``rk_test_…``).
  Live and publishable keys are refused at construction, and every response must
  report ``livemode: false`` or the call is treated as a failure.
* Payment methods are Stripe test PaymentMethod ids (``pm_card_visa`` …). A card
  number can never be passed in: Brand.Me never handles card data.
* Every money-moving request carries the caller's persisted idempotency key, so a
  retry after a lost response returns the original result instead of charging
  twice. Stripe prunes idempotency keys after about 24 hours, so reconciliation
  after that uses the stored PaymentIntent id (``lookup``), not search.
* Errors become ``ProviderError`` kinds with fixed details; Stripe's message text is
  never passed on.

The key is read by the composition root from ``STRIPE_TEST_SECRET_KEY`` (a cloud
environment secret); it is never committed or logged.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from brandme_core.domains.commerce.money import Money

from ..contracts import ProviderError, ProviderErrorKind
from . import PaymentAuthorization, PaymentState

STRIPE_API_VERSION = "2026-09-30.endive"  # the version stripe==16.0.0 pins; set explicitly
_KEY_RE = re.compile(r"^(sk|rk)_test_[A-Za-z0-9]{16,247}$")
_PM_RE = re.compile(r"^pm_[A-Za-z0-9_]{3,64}$")
_REF_RE = re.compile(r"^[A-Za-z0-9_:.\-]{1,200}$")


def require_test_key(key: Optional[str]) -> str:
    if not isinstance(key, str) or not _KEY_RE.match(key):
        raise ValueError("a Stripe test-mode secret key (sk_test_… or rk_test_…) is required; live keys are refused")
    return key


class StripeTestPaymentProcessor:
    processor_id = "stripe_test"
    simulation = False
    label = "Stripe test mode — no real money moves."

    def __init__(self, api_key: str, *, base_url: Optional[str] = None, http_client: Any = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        import stripe  # optional dependency: imported only when Stripe test mode is configured

        self._stripe = stripe
        self._clock = clock
        opts: dict = {"stripe_version": STRIPE_API_VERSION, "max_network_retries": 0}
        if base_url:  # stripe-mock for wire-shape tests
            opts["base_addresses"] = {"api": base_url}
        if http_client is not None:
            opts["http_client"] = http_client
        self._client = stripe.StripeClient(require_test_key(api_key), **opts)

    # -- calls ---------------------------------------------------------------
    def authorize(self, request: PaymentAuthorization) -> PaymentState:
        if not _PM_RE.match(request.payment_token_ref or ""):
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "a Stripe test PaymentMethod id is required")
        for ref in (request.payee_ref, request.purpose_ref, *request.metadata.values()):
            if not _REF_RE.match(ref):
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "payment references must be opaque ids")
        params = {
            "amount": request.amount.amount_minor, "currency": request.amount.currency.lower(),
            "capture_method": "manual", "confirm": True, "payment_method": request.payment_token_ref,
            # No redirects: a hosted continuation is never treated as payment (BM-COM-012).
            "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
            "metadata": {"brandme_payee_ref": request.payee_ref, "brandme_purpose_ref": request.purpose_ref,
                         **dict(request.metadata)},
        }
        try:
            pi = self._client.v1.payment_intents.create(params=params,
                                                        options={"idempotency_key": request.idempotency_key})
        except self._stripe.CardError as exc:  # a definitive decline; the PaymentIntent exists
            intent = getattr(getattr(exc, "error", None), "payment_intent", None)
            if intent is not None:
                return self._state(intent, decline=getattr(exc, "code", None) or "card_declined")
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "payment declined") from None
        except Exception as exc:
            raise self._error(exc, transmitting=True) from None
        return self._state(pi)

    def capture(self, payment_ref: str, amount: Money, *, idempotency_key: str) -> PaymentState:
        try:
            pi = self._client.v1.payment_intents.capture(
                payment_ref, params={"amount_to_capture": amount.amount_minor},
                options={"idempotency_key": idempotency_key})
        except Exception as exc:
            raise self._error(exc, transmitting=True) from None
        return self._state(pi)

    def void(self, payment_ref: str, *, idempotency_key: str) -> PaymentState:
        try:
            pi = self._client.v1.payment_intents.cancel(payment_ref, params={"cancellation_reason": "abandoned"},
                                                        options={"idempotency_key": idempotency_key})
        except Exception as exc:
            raise self._error(exc, transmitting=True) from None
        return self._state(pi)

    def refund(self, payment_ref: str, amount: Money, *, idempotency_key: str) -> PaymentState:
        try:
            self._client.v1.refunds.create(params={"payment_intent": payment_ref, "amount": amount.amount_minor},
                                           options={"idempotency_key": idempotency_key})
        except Exception as exc:
            raise self._error(exc, transmitting=True) from None
        return self.lookup(payment_ref)

    def lookup(self, payment_ref: str) -> PaymentState:
        try:
            pi = self._client.v1.payment_intents.retrieve(payment_ref, params={"expand": ["latest_charge"]})
        except Exception as exc:
            raise self._error(exc, transmitting=False) from None
        return self._state(pi)

    def verify_webhook(self, headers: Mapping[str, str], body: bytes, secret: str) -> Any:
        """A Stripe-signed event (``whsec_…`` secret, 5-minute tolerance). It is a hint: callers re-read the source."""
        sig = {k.lower(): v for k, v in headers.items()}.get("stripe-signature")
        try:
            event = self._stripe.Webhook.construct_event(body, sig, secret, tolerance=300)
        except Exception:
            raise ProviderError(ProviderErrorKind.UNAUTHORIZED, "invalid webhook signature") from None
        if getattr(event, "livemode", True):
            raise ProviderError(ProviderErrorKind.UNAUTHORIZED, "live-mode event refused")
        return event

    # -- mapping -------------------------------------------------------------
    def _state(self, pi: Any, *, decline: Optional[str] = None) -> PaymentState:
        if getattr(pi, "livemode", True) is not False:
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "live-mode payment refused")
        cur = str(pi.currency).upper()
        authorized = int(pi.amount or 0)
        received = int(getattr(pi, "amount_received", 0) or 0)
        charge = getattr(pi, "latest_charge", None)
        refunded = int(getattr(charge, "amount_refunded", 0) or 0) if charge is not None and not isinstance(charge, str) else 0
        status = {"requires_capture": "authorized", "succeeded": "captured", "canceled": "voided",
                  "requires_payment_method": "failed"}.get(str(pi.status), "unknown")
        code = decline
        if status == "captured" and refunded:
            status = "refunded" if refunded >= received else "partially_refunded"
        elif status == "voided":
            code = "authorization_expired" if getattr(pi, "cancellation_reason", None) == "automatic" else "voided"
        elif status == "failed":
            err = getattr(pi, "last_payment_error", None)
            code = code or (getattr(err, "decline_code", None) or getattr(err, "code", None) or "payment_failed")
        return PaymentState(str(pi.id), status, Money(authorized, cur), Money(received, cur), Money(refunded, cur),
                            self._clock(), str(code)[:64] if code else None, True, f"stripe_test:pi:{pi.id}")

    def _error(self, exc: Exception, *, transmitting: bool) -> ProviderError:
        s = self._stripe
        if isinstance(exc, (s.AuthenticationError, s.PermissionError)):
            return ProviderError(ProviderErrorKind.UNAUTHORIZED, "processor refused the credential")
        if isinstance(exc, s.RateLimitError):
            return ProviderError(ProviderErrorKind.THROTTLED, "processor rate limited the request")
        if isinstance(exc, (s.InvalidRequestError, s.IdempotencyError)):
            return ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "processor rejected the request")
        if isinstance(exc, ProviderError):
            return exc
        # Connection failures, timeouts and 5xx: the request may have been processed.
        return ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN if transmitting else ProviderErrorKind.TRANSIENT,
                             "processor outcome unknown" if transmitting else "processor unavailable",
                             transmitted=transmitting)
