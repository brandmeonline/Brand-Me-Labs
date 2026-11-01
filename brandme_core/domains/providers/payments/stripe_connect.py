"""Stripe Connect for brands and ateliers — TEST MODE ONLY (no real money moves).

Plan: ``docs/build/stripe-connect-plan.md`` (Flow 1). A brand is a Connect connected
account created through **Accounts v2** (``/v2/core/accounts``; no legacy account ``type``):

* ``dashboard: "full"``: the brand runs its own Stripe Dashboard.
* ``defaults.responsibilities.fees_collector: "stripe"``: Stripe bills the brand for processing.
* ``defaults.responsibilities.losses_collector: "stripe"``: Stripe holds negative balance liability.
* ``configuration.merchant`` with ``card_payments`` requested: the brand is merchant of record.

Payments are **direct charges**. ``StripeTestPaymentProcessor`` created with a
``ConnectedMerchant`` sends every PaymentIntent and refund call to the brand's account
(``Stripe-Account``). Brand.Me's revenue is ``application_fee_amount``, computed here. Brand.Me
is never the payee (``providers/merchant.py``): the member pays the brand.

Readiness is read from the v2 capability paths, never v1 ``charges_enabled`` / ``payouts_enabled``:
``configuration.merchant.capabilities.card_payments.status`` must be ``active`` before an
authorization is sent. An account whose dashboard or responsibilities differ from the plan is
refused as misconfigured. Any other configuration could leave Brand.Me liable for losses it did
not agree to take.

Onboarding: ``StripeConnectAccounts`` creates the account, then issues either an Account Session
(``client_secret`` for the embedded components ``account_onboarding``, ``notification_banner``,
``account_management``, ``payments``, ``payouts``) or a Stripe-hosted Account Link, used for
operator-run test onboarding. Neither secret nor URL is ever logged or put in ``repr``.

Not here (see the plan): member resale (separate charges and transfers), Accounts v2 thin events,
and the console/gateway routes that serve Account Sessions to a browser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from ..contracts import ProviderError, ProviderErrorKind
from .stripe_wire import StripeConnectWire, WireError

ACCOUNT_ID = re.compile(r"^acct_[A-Za-z0-9]{1,250}$")
_OPAQUE = re.compile(r"^[A-Za-z0-9_:.\-]{1,200}$")
_ACCOUNT_KEY = re.compile(r"^[A-Za-z0-9_-]{16,128}:connect_account$")
_COUNTRY = re.compile(r"^[A-Za-z]{2}$")
_CURRENCY = re.compile(r"^[A-Za-z]{3}$")
_EMAIL = re.compile(r"^[^\s@]{1,64}@[A-Za-z0-9.\-]{1,190}\.[A-Za-z]{2,24}$")
_RETURN_URL = re.compile(r"^(https://[A-Za-z0-9.\-]+(:\d{1,5})?|http://(127\.0\.0\.1|localhost):\d{1,5})(/[^\s]*)?$")

# The brands-flow configuration (plan Flow 1 §A). Anything else is refused as misconfigured.
BRAND_DASHBOARD = "full"
BRAND_FEES_COLLECTOR = "stripe"
BRAND_LOSSES_COLLECTOR = "stripe"
ACCOUNT_INCLUDE = ("configuration.merchant", "defaults", "requirements")
# Plan Flow 1 §H: 5-15%; the bound is wider so a negotiated rate is a config change, not a code change.
MIN_FEE_BPS, MAX_FEE_BPS = 1, 3000
CAPABILITY_STATUSES = ("active", "pending", "rejected", "restricted", "unsupported")


def require_account_id(account_id: object) -> str:
    if not isinstance(account_id, str) or not ACCOUNT_ID.match(account_id):
        raise ValueError("stripe_connect_account_refused")
    return account_id


@dataclass(frozen=True)
class ConnectedMerchant:
    """One brand on direct charges. ``payee_ref`` is the opaque party bound into quotes; the account id
    is the processor's routing detail and is never shown to members, models or events."""

    payee_ref: str
    account_id: str = field(repr=False)
    application_fee_bps: int = 1000
    refund_application_fee: bool = True  # a member refund returns Brand.Me's fee pro rata, not just the brand's share

    def __post_init__(self) -> None:
        if not isinstance(self.payee_ref, str) or not _OPAQUE.match(self.payee_ref):
            raise ValueError("stripe_connect_config_refused")
        require_account_id(self.account_id)
        if isinstance(self.application_fee_bps, bool) or not isinstance(self.application_fee_bps, int) \
                or not MIN_FEE_BPS <= self.application_fee_bps <= MAX_FEE_BPS:
            raise ValueError("stripe_connect_fee_refused")

    def application_fee(self, amount_minor: int) -> int:
        """Brand.Me's fee on ``amount_minor``, rounded down. The brand pays Stripe's processing fee itself
        (``fees_collector: "stripe"``), so this is the platform fee only, never a pass-through estimate."""
        if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor < 0:
            raise ValueError("amount must be a non-negative integer of minor units")
        return amount_minor * self.application_fee_bps // 10_000


@dataclass(frozen=True)
class AccountReadiness:
    """What the v2 account says about taking direct charges. Never carries requirement text or identity data."""

    account_id: str = field(repr=False)
    card_payments: str  # CAPABILITY_STATUSES, or "unknown"
    payouts: str
    requirements_due: int
    configured_as_planned: bool  # dashboard + responsibilities match the brands flow

    @property
    def ready(self) -> bool:
        return self.configured_as_planned and self.card_payments == "active"

    def to_operator(self) -> Dict[str, Any]:
        return {"card_payments": self.card_payments, "payouts": self.payouts,
                "requirements_due": self.requirements_due, "configured_as_planned": self.configured_as_planned,
                "ready": self.ready}


@dataclass(frozen=True)
class ComponentSession:
    """An Account Session for the embedded components. The ``client_secret`` goes to the brand's browser only."""

    client_secret: str = field(repr=False)
    expires_at: Optional[int] = None
    components: Tuple[str, ...] = ()


# Embedded components (plan §E). Capture stays with Brand.Me's order flow (capture at first shipment),
# so the payments component may refund and manage disputes but never capture.
EMBEDDED_COMPONENTS: Mapping[str, Dict[str, Any]] = {
    "account_onboarding": {"enabled": True},
    "notification_banner": {"enabled": True},  # required: keeps the account enabled as requirements change
    "account_management": {"enabled": True},
    "payments": {"enabled": True, "features": {"capture_payments": False, "refund_management": True,
                                               "dispute_management": True}},
    "payouts": {"enabled": True},
}


def _status(node: Any, *path: str) -> str:
    for p in path:
        node = node.get(p) if isinstance(node, Mapping) else None
    return node if isinstance(node, str) and node in CAPABILITY_STATUSES else "unknown"


def readiness_of(account: Mapping[str, Any]) -> AccountReadiness:
    """Reads only the fields listed here. Raises ``ValueError`` on a live-mode or unreadable account."""
    if not isinstance(account, Mapping) or account.get("object") != "v2.core.account":
        raise ValueError("not a v2 account")
    if account.get("livemode") is not False:
        raise ValueError("live_mode_account_refused")
    acct_id = require_account_id(account.get("id"))
    caps = ((account.get("configuration") or {}).get("merchant") or {}).get("capabilities") or {}
    resp = ((account.get("defaults") or {}).get("responsibilities") or {})
    entries = (account.get("requirements") or {}).get("entries") or []
    planned = (account.get("dashboard") == BRAND_DASHBOARD and resp.get("fees_collector") == BRAND_FEES_COLLECTOR
               and resp.get("losses_collector") == BRAND_LOSSES_COLLECTOR)
    return AccountReadiness(acct_id, _status(caps, "card_payments", "status"),
                            _status(caps, "stripe_balance", "payouts", "status"),
                            len(entries) if isinstance(entries, list) else 0, planned)


def _read_error(e: Exception) -> ProviderError:
    kind = e.kind if isinstance(e, WireError) else "unknown"
    if kind in ("authentication", "permission"):
        return ProviderError(ProviderErrorKind.UNAUTHORIZED, "processor refused the credential")
    if kind == "rate_limit":
        return ProviderError(ProviderErrorKind.THROTTLED, "processor rate limited the request")
    if kind in ("invalid_request", "card_error", "idempotency"):
        return ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "processor refused the read")
    return ProviderError(ProviderErrorKind.TRANSIENT, "processor unavailable")


def read_readiness(wire: StripeConnectWire, account_id: str) -> AccountReadiness:
    try:
        account = wire.retrieve_account(account_id, include=list(ACCOUNT_INCLUDE))
    except Exception as e:
        raise _read_error(e) from None
    try:
        r = readiness_of(account)
    except ValueError as e:
        raise ProviderError(ProviderErrorKind.NOT_CONFIGURED if str(e) == "live_mode_account_refused"
                            else ProviderErrorKind.MALFORMED_RESPONSE, "unexpected connected account") from None
    if r.account_id != account_id:
        raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unexpected connected account")
    return r


class StripeConnectAccounts:
    """Creates and onboards brand connected accounts (test mode). Network I/O only through the wire."""

    def __init__(self, wire: StripeConnectWire, *, environment: str):
        if environment not in ("demo", "development", "sandbox"):
            raise ValueError("stripe_test_not_allowed")
        self._wire = wire
        self._env = environment

    def create_brand_account(self, *, payee_ref: str, display_name: str, country: str, currency: str,
                             idempotency_key: str, contact_email: Optional[str] = None) -> AccountReadiness:
        """One brand, one account: the caller persists ``idempotency_key`` (``<base>:connect_account``)
        before calling, and reuses it on every retry, so a lost response never makes a second account."""
        if not isinstance(payee_ref, str) or not _OPAQUE.match(payee_ref):
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "payee references must be opaque ids")
        if not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 100:
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "display name not allowed")
        if not isinstance(country, str) or not _COUNTRY.match(country) \
                or not isinstance(currency, str) or not _CURRENCY.match(currency):
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "country or currency not allowed")
        if not isinstance(idempotency_key, str) or not _ACCOUNT_KEY.match(idempotency_key):
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "not a connect account key")
        if contact_email is not None and (not isinstance(contact_email, str) or not _EMAIL.match(contact_email)):
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "contact email not allowed")
        params: Dict[str, Any] = {
            "dashboard": BRAND_DASHBOARD,
            "display_name": display_name.strip(),
            "identity": {"country": country.lower(), "entity_type": "company"},
            "configuration": {"merchant": {"capabilities": {"card_payments": {"requested": True}}}},
            "defaults": {"currency": currency.lower(),
                         "responsibilities": {"fees_collector": BRAND_FEES_COLLECTOR,
                                              "losses_collector": BRAND_LOSSES_COLLECTOR}},
            "metadata": {"brandme_payee_ref": payee_ref, "brandme_env": self._env},
            "include": list(ACCOUNT_INCLUDE),
        }
        if contact_email is not None:
            params["contact_email"] = contact_email
        try:
            account = self._wire.create_account(params, idempotency_key=idempotency_key)
        except WireError as e:
            if e.kind in ("authentication", "permission"):
                raise ProviderError(ProviderErrorKind.UNAUTHORIZED, "processor refused the credential") from None
            if e.kind == "rate_limit":
                raise ProviderError(ProviderErrorKind.THROTTLED, "processor rate limited the request") from None
            if e.kind == "invalid_request":
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "processor rejected the request") from None
            raise ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN, "processor outcome unknown",
                                transmitted=True) from None
        except Exception:
            raise ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN, "processor outcome unknown",
                                transmitted=True) from None
        try:
            return readiness_of(account)
        except ValueError:  # it was created, but the answer cannot be trusted: retry with the same key to read it
            raise ProviderError(ProviderErrorKind.OUTCOME_UNKNOWN, "unreadable processor response",
                                transmitted=True) from None

    def readiness(self, account_id: str) -> AccountReadiness:
        try:
            require_account_id(account_id)
        except ValueError:
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "not a connected account reference") from None
        return read_readiness(self._wire, account_id)

    def component_session(self, account_id: str) -> ComponentSession:
        """A short-lived secret for the embedded components; created on each page load, never stored."""
        try:
            require_account_id(account_id)
        except ValueError:
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "not a connected account reference") from None
        try:
            sess = self._wire.create_account_session(
                {"account": account_id, "components": {k: dict(v) for k, v in EMBEDDED_COMPONENTS.items()}})
        except Exception as e:
            raise _read_error(e) from None  # creating a session moves no money: a failure is simply retried
        secret = sess.get("client_secret") if isinstance(sess, Mapping) else None
        if not isinstance(secret, str) or not secret or sess.get("livemode") is not False \
                or sess.get("account") != account_id:
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unexpected account session")
        expires = sess.get("expires_at")
        return ComponentSession(secret, int(expires) if isinstance(expires, int) else None,
                                tuple(sorted(EMBEDDED_COMPONENTS)))

    def onboarding_link(self, account_id: str, *, refresh_url: str, return_url: str) -> str:
        """Stripe-hosted onboarding for operator-run test onboarding. The URL is single-use; never log it."""
        try:
            require_account_id(account_id)
        except ValueError:
            raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "not a connected account reference") from None
        for u in (refresh_url, return_url):
            if not isinstance(u, str) or not _RETURN_URL.match(u):
                raise ProviderError(ProviderErrorKind.CONTRACT_RESTRICTED, "redirect URL not allowed")
        try:
            link = self._wire.create_account_link({"account": account_id, "use_case": {
                "type": "account_onboarding",
                "account_onboarding": {"refresh_url": refresh_url, "return_url": return_url}}})
        except Exception as e:
            raise _read_error(e) from None
        url = link.get("url") if isinstance(link, Mapping) else None
        if not isinstance(url, str) or not url.startswith("https://") or link.get("livemode") is not False:
            raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, "unexpected account link")
        return url
