"""Stripe payment processor — TEST MODE ONLY (no real money moves).

PaymentIntents with manual capture: the merchant authorizes when it accepts
the order, captures once at the first shipment, voids if every unit is
cancelled before capture or the hold expires, and refunds after capture. This
module holds the guards, the configuration and the payment semantics; the SDK
lives behind ``stripe_wire.StripeWire`` and is never imported here.

Guards, in order of importance:

* Only test-mode secret keys: ``sk_test_…``, or the least-privilege restricted
  ``rk_test_…``. Live, publishable and webhook-signing secrets and malformed
  keys are refused with a fixed code that never contains the key.
* Every object read must report ``livemode: false``; one that does not latches
  the processor shut (``not_configured`` from then on).
* Outbound fields are allowlisted: the instrument is a Stripe test PaymentMethod
  id (``pm_card_…``), metadata keys are a fixed set with opaque values, the
  description is a fixed template and amounts are integers. A card number
  cannot reach any parameter, and nothing about the member is sent.
* Every money-moving request carries the caller's persisted idempotency key. An
  authorization is never re-sent: a lost response is resolved by reads (this
  process's journal, then Search, then a consistent List scan). A capture, void
  or refund with an unknown outcome is resolved by ``operation_effect``.
* Errors become ``ProviderError`` kinds with fixed details. Stripe's message
  text, object ids, amounts and ``client_secret`` never reach a log, an
  evidence reference or an event.

Webhooks: ``stripe-signature`` over the raw body with the configured
``whsec_…`` secrets (current, then previous, for rotation), and an explicit
replay window that refuses stale **and** future timestamps.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, FrozenSet, List, Mapping, Optional, Tuple

from brandme_core.domains.commerce.money import Money

from ..contracts import ProviderError, ProviderErrorKind
from ..redaction import PaymentLogSink, default_payment_log, payment_log_record
from . import (DECLINE_CODES, TEST_CARD, TEST_CARD_DECLINED, PaymentAuthorization, PaymentEvent,
               PaymentRailDescriptor, PaymentState, base_of)
from .stripe_wire import StripeWire, WireError

STRIPE_API_VERSION = "2026-09-30.endive"  # the version stripe==16.0.0 pins; set explicitly on every request
STRIPE_API_BASE = "https://api.stripe.com"
STRIPE_TEST_LABEL = "Stripe test mode — no real money moves."
ENV_NAMES = ("STRIPE_TEST_SECRET_KEY", "STRIPE_TEST_WEBHOOK_SECRET", "STRIPE_TEST_WEBHOOK_SECRET_PREVIOUS",
             "BRANDME_STRIPE_EGRESS_PROXY", "BRANDME_STRIPE_CA_BUNDLE")
_TEST_SECRET = re.compile(r"^(?:sk|rk)_test_[0-9A-Za-z]{16,247}$")
_WHSEC = re.compile(r"^whsec_[0-9A-Za-z]{16,256}$")
TEST_INSTRUMENT = re.compile(r"^pm_card_[A-Za-z0-9_]{2,64}$")
_OPAQUE = re.compile(r"^[A-Za-z0-9_:.\-]{1,200}$")
_PI_ID = re.compile(r"^pi_[A-Za-z0-9]{1,250}$")
_EVENT_ID = re.compile(r"^evt_[A-Za-z0-9]+$")
_LOOPBACK = re.compile(r"^http://(127\.0\.0\.1|localhost):\d{1,5}$")
_PROXY = re.compile(r"^https?://(?:[^\s/@]+@)?[A-Za-z0-9.\-]+(?::\d{1,5})?/?$")
CALLER_METADATA_KEYS = frozenset({"brandme_provider", "brandme_merchant", "brandme_quote_hash",
                                  "brandme_simulated_merchant"})
MIN_AMOUNT, MAX_AMOUNT = 50, 99_999_999
# Configure the Stripe endpoint's enabled_events to exactly these. Others are acknowledged and ignored.
HANDLED_EVENT_TYPES = ("payment_intent.amount_capturable_updated", "payment_intent.succeeded",
                       "payment_intent.canceled", "payment_intent.payment_failed", "payment_intent.requires_action",
                       "charge.refunded", "refund.created", "refund.updated", "refund.failed")
# Voids for reasons Stripe would call "abandoned"; everything else is the customer's (member's) request.
_ABANDONED = frozenset({"orphan_authorization", "binding_mismatch", "authentication_required", "not_authorized",
                        "authorization_expired"})


class StripeKeyRefused(ValueError):
    """A refused Stripe credential or setting. ``str``/``repr`` carry the fixed code only, never the value."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code

    def __repr__(self) -> str:
        return f"StripeKeyRefused({self.code!r})"


def require_test_secret_key(key: object) -> str:
    if not isinstance(key, str) or not key:
        raise StripeKeyRefused("stripe_key_missing")
    if key != key.strip():
        raise StripeKeyRefused("stripe_key_malformed")
    if key.startswith(("sk_live_", "rk_live_")):
        raise StripeKeyRefused("stripe_live_key_refused")
    if key.startswith("pk_"):
        raise StripeKeyRefused("stripe_publishable_key_refused")
    if not _TEST_SECRET.match(key):  # whsec_ secrets, other prefixes and malformed keys
        raise StripeKeyRefused("stripe_key_not_test_secret")
    return key


def require_webhook_secret(secret: object) -> str:
    if not isinstance(secret, str) or not _WHSEC.match(secret):
        raise StripeKeyRefused("stripe_webhook_secret_refused")
    return secret


def require_api_base(url: str) -> str:
    """The Stripe API itself, or a loopback stripe-mock (tests). Nothing else ever receives the key."""
    if url == STRIPE_API_BASE or (isinstance(url, str) and _LOOPBACK.match(url)):
        return url
    raise StripeKeyRefused("stripe_api_base_refused")


def require_loopback_api_base(url: str) -> str:
    if isinstance(url, str) and _LOOPBACK.match(url):
        return url
    raise StripeKeyRefused("stripe_api_base_refused")


@dataclass(frozen=True)
class StripeTestConfig:
    secret_key: str = field(repr=False)
    webhook_secrets: Tuple[str, ...] = field(default=(), repr=False)  # current, then previous (rotation)
    payment_method: str = TEST_CARD
    decline_payment_method: str = TEST_CARD_DECLINED
    payee_ref: str = "demo-atelier-stripe-test"  # the Stripe test account standing in for the fictional merchant
    merchant_label: str = "Demo Atelier (fictional)"
    currencies: FrozenSet[str] = frozenset({"USD"})
    timeout_seconds: float = 20.0
    webhook_tolerance_seconds: int = 300
    lookback: timedelta = timedelta(days=8)  # longer than a hold lives
    max_list_pages: int = 5
    egress_proxy: Optional[str] = field(default=None, repr=False)  # may carry proxy credentials
    ca_bundle: Optional[str] = None
    run_tag: Optional[str] = None  # live suite only: tags every PaymentIntent with brandme_run for teardown

    def __post_init__(self) -> None:
        require_test_secret_key(self.secret_key)
        for s in self.webhook_secrets:
            require_webhook_secret(s)
        for pm in (self.payment_method, self.decline_payment_method):
            if not TEST_INSTRUMENT.match(pm):
                raise StripeKeyRefused("stripe_test_instrument_refused")
        if not _OPAQUE.match(self.payee_ref) or not self.currencies:
            raise StripeKeyRefused("stripe_config_refused")
        if not 1 <= self.webhook_tolerance_seconds <= 600 or not 0 < self.timeout_seconds <= 60 \
                or not 1 <= self.max_list_pages <= 20:
            raise StripeKeyRefused("stripe_config_refused")
        if self.egress_proxy is not None and not _PROXY.match(self.egress_proxy):
            raise StripeKeyRefused("stripe_egress_proxy_refused")
        if self.ca_bundle is not None and not (self.ca_bundle.startswith("/") and ".." not in self.ca_bundle):
            raise StripeKeyRefused("stripe_ca_bundle_refused")
        if self.run_tag is not None and not _OPAQUE.match(self.run_tag):
            raise StripeKeyRefused("stripe_config_refused")

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "StripeTestConfig":
        """Reads only ``ENV_NAMES``; never ``STRIPE_SECRET_KEY``, ``STRIPE_API_KEY`` or ambient proxy settings."""
        view = {k: env[k] for k in ENV_NAMES if k in env}
        secrets_ = tuple(s for s in (view.get("STRIPE_TEST_WEBHOOK_SECRET"),
                                     view.get("STRIPE_TEST_WEBHOOK_SECRET_PREVIOUS")) if s)
        return cls(view.get("STRIPE_TEST_SECRET_KEY") or "", webhook_secrets=secrets_,
                   egress_proxy=view.get("BRANDME_STRIPE_EGRESS_PROXY") or None,
                   ca_bundle=view.get("BRANDME_STRIPE_CA_BUNDLE") or None)


class _Refusal(Exception):
    """Internal: a live-mode object was seen."""


def _err(kind: ProviderErrorKind, detail: str, *, transmitted: bool = False) -> ProviderError:
    return ProviderError(kind, detail, transmitted=transmitted)


class StripeTestPaymentProcessor:
    processor_id = "stripe_test"
    simulation = False
    label = STRIPE_TEST_LABEL

    def __init__(self, config: StripeTestConfig, *, wire: StripeWire, environment: str,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 log: Optional[PaymentLogSink] = None):
        if environment not in ("demo", "development", "sandbox"):
            raise ValueError("stripe_test_not_allowed")
        self.config = config
        self._wire = wire
        self._env = environment
        self._clock = clock
        self._log = log or default_payment_log
        self.descriptor = PaymentRailDescriptor("stripe_test", "sandbox", environment, STRIPE_TEST_LABEL,
                                                config.payee_ref, config.currencies, STRIPE_API_VERSION,
                                                bool(config.webhook_secrets))
        self.test_instruments: Tuple[str, str] = (config.payment_method, config.decline_payment_method)
        self._lock = threading.Lock()
        self._latched = False  # set by any live-mode object: the processor refuses everything after it
        self._journal: Dict[str, str] = {}  # purpose ref -> PaymentIntent id (this process's own writes)
        self._purposes: Dict[str, str] = {}  # PaymentIntent id -> purpose ref (from its metadata)
        self._release_reasons: Dict[str, str] = {}  # PaymentIntent id -> why this process voided it

    # -- logging -------------------------------------------------------------
    def _emit(self, op: str, outcome: str, kind: Optional[ProviderErrorKind], started: float) -> None:
        try:
            self._log(payment_log_record(self.processor_id, op, outcome, kind.value if kind else None,
                                         int((time.monotonic() - started) * 1000), self._env))
        except Exception:
            pass  # a broken log sink never changes a payment outcome

    def _run(self, op: str, fn: Callable[[], Any], outcome_of: Callable[[Any], str] = lambda r: "ok") -> Any:
        started = time.monotonic()
        try:
            result = fn()
        except ProviderError as e:
            self._emit(op, "unknown" if e.transmitted else (
                "unsettled" if e.detail == "payment_lookup_unsettled" else "refused"), e.kind, started)
            raise
        except Exception:
            self._emit(op, "error", None, started)
            raise
        self._emit(op, outcome_of(result), None, started)
        return result

    # -- guards --------------------------------------------------------------
    def _open(self) -> None:
        if self._latched:
            raise _err(ProviderErrorKind.NOT_CONFIGURED, "processor latched after a live-mode object")

    def _latch(self) -> None:
        with self._lock:
            self._latched = True

    @staticmethod
    def _check_pi(payment_ref: str) -> None:
        if not isinstance(payment_ref, str) or not _PI_ID.match(payment_ref):
            raise _err(ProviderErrorKind.CONTRACT_RESTRICTED, "not a PaymentIntent reference")

    def _check_amount(self, amount: Money, *, minimum: int = 1) -> int:
        if amount.currency not in self.config.currencies or not minimum <= amount.amount_minor <= MAX_AMOUNT:
            raise _err(ProviderErrorKind.CONTRACT_RESTRICTED, "amount or currency not allowed")
        return amount.amount_minor

    @staticmethod
    def _check_key(key: str) -> None:
        if base_of(key) is None:
            raise _err(ProviderErrorKind.CONTRACT_RESTRICTED, "not a payment operation key")

    # -- error mapping (§ "WireError -> ProviderError") ------------------------
    @staticmethod
    def _mutating_error(e: Exception) -> ProviderError:
        kind = e.kind if isinstance(e, WireError) else "unknown"
        if kind in ("authentication", "permission"):
            return _err(ProviderErrorKind.UNAUTHORIZED, "processor refused the credential")
        if kind == "rate_limit":  # Stripe does not execute a rate-limited request
            return _err(ProviderErrorKind.THROTTLED, "processor rate limited the request")
        if kind in ("invalid_request", "card_error"):
            return _err(ProviderErrorKind.CONTRACT_RESTRICTED, "processor rejected the request")
        # idempotency, connection, 5xx, unknown: the request may have been processed.
        return _err(ProviderErrorKind.OUTCOME_UNKNOWN, "processor outcome unknown", transmitted=True)

    @staticmethod
    def _read_error(e: Exception) -> ProviderError:
        kind = e.kind if isinstance(e, WireError) else "unknown"
        if kind in ("authentication", "permission"):
            return _err(ProviderErrorKind.UNAUTHORIZED, "processor refused the credential")
        if kind == "rate_limit":
            return _err(ProviderErrorKind.THROTTLED, "processor rate limited the request")
        if kind in ("invalid_request", "card_error", "idempotency"):
            return _err(ProviderErrorKind.MALFORMED_RESPONSE, "processor refused the read")
        return _err(ProviderErrorKind.TRANSIENT, "processor unavailable")

    # -- observation (§ "Stripe -> processor state") ---------------------------
    @staticmethod
    def _at(ts: Any) -> Optional[datetime]:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc) if isinstance(ts, (int, float)) and ts > 0 else None

    @staticmethod
    def _decline(code: Optional[str], decline_code: Optional[str]) -> str:
        for c in (decline_code, code):
            if c in DECLINE_CODES:
                return c
        return "other"

    def _observe(self, pi: Mapping[str, Any], refunds: List[Mapping[str, Any]],
                 decline: Optional[str] = None) -> PaymentState:
        """Reads whitelisted fields only. ``client_secret`` is never read, stored or logged."""
        if not isinstance(pi, Mapping) or pi.get("object") != "payment_intent":
            raise ValueError("not a payment intent")
        if pi.get("livemode") is not False:
            self._latch()
            raise _Refusal()
        pi_id = str(pi["id"])
        if not _PI_ID.match(pi_id):
            raise ValueError("bad payment intent id")
        cur = str(pi["currency"]).upper()
        amount = int(pi["amount"])
        received = int(pi.get("amount_received") or 0)
        md = pi.get("metadata") or {}
        md = md if isinstance(md, Mapping) else {}
        echo = {k: (str(md[k]) if isinstance(md.get(k), str) and _OPAQUE.match(md[k]) else None)
                for k in ("brandme_purpose_ref", "brandme_payee_ref", "brandme_env", "brandme_idem")}
        purpose = echo["brandme_purpose_ref"]
        if purpose:
            with self._lock:
                self._purposes[pi_id] = purpose
        charge = pi.get("latest_charge") if isinstance(pi.get("latest_charge"), Mapping) else None
        card = ((charge or {}).get("payment_method_details") or {}).get("card") or {}
        capture_before = self._at(card.get("capture_before")) if isinstance(card, Mapping) else None
        refunded = sum(int(r.get("amount") or 0) for r in refunds
                       if r.get("status") == "succeeded" and r.get("payment_intent") in (None, pi_id))
        raw = pi.get("status")
        released: Optional[int] = None
        reason: Optional[str] = None
        code = decline
        if raw == "requires_capture":
            status = "authorized"
        elif raw == "succeeded":
            status = "captured"
            if received < amount:
                released, reason = amount - received, "partial_capture_remainder"
            if refunded > 0:
                status = "refunded" if refunded >= received else "partially_refunded"
        elif raw == "canceled":
            if charge is not None and charge.get("status") == "succeeded" and not charge.get("captured"):
                status, released = "voided", amount
                with self._lock:
                    recorded = self._release_reasons.get(pi_id)
                reason = ("authorization_expired" if pi.get("cancellation_reason") in ("automatic", "expired")
                          else recorded or "merchant_void")
            else:
                status = "failed"
        elif raw == "requires_payment_method":
            err = pi.get("last_payment_error")
            if isinstance(err, Mapping):
                status = "failed"
                code = code or self._decline(err.get("code"), err.get("decline_code"))
            else:
                status = "unknown"
        elif raw == "requires_action":
            status = "requires_action"
        else:  # requires_confirmation, processing, anything new
            status = "unknown"
        z = Money(0, cur)
        return PaymentState(
            pi_id, status, Money(amount, cur), Money(received, cur) if status in (
                "captured", "partially_refunded", "refunded") else z, Money(refunded, cur), self._clock(),
            code if status == "failed" else None, True,
            f"stripe_test:payment_for:{purpose or 'unknown'}", Money(released, cur) if released is not None else None,
            reason, capture_before, purpose, echo["brandme_payee_ref"], echo["brandme_env"], echo["brandme_idem"])

    def _observe_sent(self, pi: Any, refunds: List[Mapping[str, Any]], decline: Optional[str] = None) -> PaymentState:
        """Observation of a mutating call's response: anything wrong with it leaves the outcome unknown."""
        try:
            return self._observe(pi, refunds, decline)
        except _Refusal:
            raise _err(ProviderErrorKind.OUTCOME_UNKNOWN, "live_mode_object_refused", transmitted=True) from None
        except (KeyError, TypeError, ValueError):
            raise _err(ProviderErrorKind.OUTCOME_UNKNOWN, "unreadable processor response", transmitted=True) from None

    def _observe_read(self, pi: Any, refunds: List[Mapping[str, Any]]) -> PaymentState:
        try:
            return self._observe(pi, refunds)
        except _Refusal:
            raise _err(ProviderErrorKind.NOT_CONFIGURED, "processor latched after a live-mode object") from None
        except (KeyError, TypeError, ValueError):
            raise _err(ProviderErrorKind.MALFORMED_RESPONSE, "unexpected processor response") from None

    # -- reads ---------------------------------------------------------------
    def _read_pi(self, payment_ref: str) -> PaymentState:
        try:
            pi = self._wire.retrieve_payment_intent(payment_ref)
            refunds = self._wire.list_refunds(payment_ref)
        except Exception as e:
            raise self._read_error(e) from None
        return self._observe_read(pi, refunds)

    def lookup(self, payment_ref: str) -> PaymentState:
        def _do():
            self._open()
            self._check_pi(payment_ref)
            return self._read_pi(payment_ref)
        return self._run("lookup", _do)

    def find(self, purpose_ref: str, *, settled: bool) -> Optional[PaymentState]:
        def _do():
            self._open()
            if not isinstance(purpose_ref, str) or not _OPAQUE.match(purpose_ref):
                raise _err(ProviderErrorKind.CONTRACT_RESTRICTED, "payment references must be opaque ids")
            with self._lock:
                hit = self._journal.get(purpose_ref)
            if hit:
                return self._read_pi(hit)
            try:  # Search is eventually consistent: it only speeds things up
                rows = self._wire.search_payment_intents(f"metadata['brandme_purpose_ref']:'{purpose_ref}'")
            except Exception as e:
                raise self._read_error(e) from None
            mine = [r for r in rows if self._is_for(r, purpose_ref)]
            if len(mine) > 1:
                raise _err(ProviderErrorKind.MALFORMED_RESPONSE, "more than one payment for one purpose")
            if mine:
                return self._read_pi(str(mine[0]["id"]))
            # The consistent List scan is the read that decides absence.
            gte = int((self._clock() - self.config.lookback).timestamp())
            cursor: Optional[str] = None
            found: List[Mapping[str, Any]] = []
            more = False
            for _ in range(self.config.max_list_pages):
                try:
                    page, more = self._wire.list_payment_intents(created_gte=gte, starting_after=cursor)
                except Exception as e:
                    raise self._read_error(e) from None
                found += [r for r in page if self._is_for(r, purpose_ref)]
                if found or not more or not page:
                    break
                cursor = str(page[-1]["id"])
            if len(found) > 1:
                raise _err(ProviderErrorKind.MALFORMED_RESPONSE, "more than one payment for one purpose")
            if found:
                return self._read_pi(str(found[0]["id"]))
            if more:
                raise _err(ProviderErrorKind.TRANSIENT, "payment_lookup_incomplete")
            if not settled:
                raise _err(ProviderErrorKind.TRANSIENT, "payment_lookup_unsettled")
            return None
        return self._run("find", _do, lambda r: "ok" if r is not None else "not_found")

    def _is_for(self, row: Mapping[str, Any], purpose_ref: str) -> bool:
        md = row.get("metadata") if isinstance(row, Mapping) else None
        return isinstance(md, Mapping) and md.get("brandme_purpose_ref") == purpose_ref \
            and md.get("brandme_env") == self._env

    def operation_effect(self, payment_ref: str, idempotency_key: str) -> str:
        def _do():
            self._open()
            self._check_pi(payment_ref)
            self._check_key(idempotency_key)
            op = idempotency_key.split(":")[1]
            try:
                pi = self._wire.retrieve_payment_intent(payment_ref)
                refunds = self._wire.list_refunds(payment_ref) if op == "refund" else []
            except Exception:
                raise _err(ProviderErrorKind.TRANSIENT, "payment effect unreadable") from None
            if not isinstance(pi, Mapping) or pi.get("livemode") is not False:
                if isinstance(pi, Mapping) and pi.get("livemode") is not False:
                    self._latch()
                raise _err(ProviderErrorKind.TRANSIENT, "payment effect unreadable")
            status = pi.get("status")
            if op == "capture":
                return "applied" if status == "succeeded" else "absent"
            if op == "void":
                return "applied" if status == "canceled" else "absent"
            if op == "refund":
                return "applied" if any((r.get("metadata") or {}).get("brandme_idem") == idempotency_key
                                        and r.get("status") in ("pending", "succeeded", "requires_action")
                                        for r in refunds) else "absent"
            raise _err(ProviderErrorKind.CONTRACT_RESTRICTED, "an authorization has no separate effect")
        return self._run("effect", _do)

    # -- mutating calls --------------------------------------------------------
    def _create_params(self, r: PaymentAuthorization) -> Dict[str, Any]:
        if r.capture != "manual":
            raise _err(ProviderErrorKind.UNSUPPORTED, "only manual capture is supported")
        if r.payee_ref != self.config.payee_ref:
            raise _err(ProviderErrorKind.CONTRACT_RESTRICTED, "payee_mismatch")
        if r.environment != self._env:
            raise _err(ProviderErrorKind.CONTRACT_RESTRICTED, "environment_mismatch")
        self._check_amount(r.amount, minimum=MIN_AMOUNT)
        if not isinstance(r.payment_token_ref, str) or not TEST_INSTRUMENT.match(r.payment_token_ref):
            raise _err(ProviderErrorKind.CONTRACT_RESTRICTED, "a Stripe test PaymentMethod id is required")
        if base_of(r.idempotency_key) is None or not r.idempotency_key.endswith(":authorize"):
            raise _err(ProviderErrorKind.CONTRACT_RESTRICTED, "not an authorization key")
        if set(r.metadata) - CALLER_METADATA_KEYS:
            raise _err(ProviderErrorKind.CONTRACT_RESTRICTED, "metadata key not allowed")
        for v in (r.purpose_ref, *r.metadata.values()):
            if not isinstance(v, str) or not _OPAQUE.match(v):
                raise _err(ProviderErrorKind.CONTRACT_RESTRICTED, "payment references must be opaque ids")
        metadata = {**{k: r.metadata[k] for k in sorted(r.metadata)}, "brandme_env": self._env,
                    "brandme_purpose_ref": r.purpose_ref, "brandme_idem": r.idempotency_key,
                    "brandme_payee_ref": r.payee_ref}
        if self.config.run_tag:
            metadata["brandme_run"] = self.config.run_tag
        return {
            "amount": r.amount.amount_minor, "currency": r.amount.currency.lower(), "capture_method": "manual",
            "confirm": True, "payment_method": r.payment_token_ref,
            # No redirects: a hosted continuation is never treated as payment (BM-COM-012).
            "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
            "description": f"Brand.Me TEST MODE - {self.config.merchant_label} - {r.purpose_ref}",
            "metadata": metadata, "expand": ["latest_charge"],
        }

    def authorize(self, request: PaymentAuthorization) -> PaymentState:
        def _do():
            self._open()
            params = self._create_params(request)
            try:
                pi = self._wire.create_payment_intent(params, idempotency_key=request.idempotency_key)
            except WireError as e:
                if e.kind != "card_error":
                    raise self._mutating_error(e) from None
                code = self._decline(e.code, e.decline_code)
                if e.payment_intent is not None:  # a definitive decline; the PaymentIntent exists
                    return self._observe_sent(e.payment_intent, [], decline=code)
                z = Money(0, request.amount.currency)
                return PaymentState("", "failed", request.amount, z, z, self._clock(), code, True,
                                    f"stripe_test:payment_for:{request.purpose_ref}", purpose_ref=request.purpose_ref,
                                    payee_ref=request.payee_ref, environment=self._env,
                                    authorize_key=request.idempotency_key)
            except Exception as e:
                raise self._mutating_error(e) from None
            state = self._observe_sent(pi, [])
            with self._lock:
                self._journal[request.purpose_ref] = state.payment_ref
            return state
        return self._run("authorize", _do, lambda s: {"failed": "declined", "requires_action": "requires_action"}
                         .get(s.status, "ok"))

    def _send(self, op: str, payment_ref: str, send: Callable[[], Any], reread_codes: FrozenSet[str]) -> PaymentState:
        try:
            response = send()
        except WireError as e:
            if e.kind == "invalid_request" and e.code in reread_codes:
                return self._read_pi(payment_ref)  # the call was refused definitively: read the state
            raise self._mutating_error(e) from None
        except Exception as e:
            raise self._mutating_error(e) from None
        if not isinstance(response, Mapping):
            raise _err(ProviderErrorKind.OUTCOME_UNKNOWN, "unreadable processor response", transmitted=True)
        if "livemode" in response and response["livemode"] is not False:  # refunds carry no livemode; their
            self._latch()                                                  # PaymentIntent is read just below
            raise _err(ProviderErrorKind.OUTCOME_UNKNOWN, "live_mode_object_refused", transmitted=True)
        try:  # any failure after the send leaves the outcome unknown, including the follow-up read
            return self._read_pi(payment_ref)
        except ProviderError:
            raise _err(ProviderErrorKind.OUTCOME_UNKNOWN, "processor outcome unknown", transmitted=True) from None

    def capture(self, payment_ref: str, amount: Money, *, idempotency_key: str) -> PaymentState:
        def _do():
            self._open()
            self._check_pi(payment_ref)
            self._check_key(idempotency_key)
            n = self._check_amount(amount)
            return self._send("capture", payment_ref, lambda: self._wire.capture_payment_intent(
                payment_ref, {"amount_to_capture": n}, idempotency_key=idempotency_key),
                frozenset({"charge_expired_for_capture", "payment_intent_unexpected_state"}))
        return self._run("capture", _do)

    def void(self, payment_ref: str, *, idempotency_key: str, reason: str = "merchant_void") -> PaymentState:
        def _do():
            self._open()
            self._check_pi(payment_ref)
            self._check_key(idempotency_key)
            with self._lock:  # recorded before the send, so the read after it carries the reason
                self._release_reasons.setdefault(payment_ref, reason)
            return self._send("void", payment_ref, lambda: self._wire.cancel_payment_intent(
                payment_ref, {"cancellation_reason": "abandoned" if reason in _ABANDONED else "requested_by_customer"},
                idempotency_key=idempotency_key), frozenset({"payment_intent_unexpected_state"}))
        return self._run("void", _do)

    def refund(self, payment_ref: str, amount: Money, *, idempotency_key: str) -> PaymentState:
        def _do():
            self._open()
            self._check_pi(payment_ref)
            self._check_key(idempotency_key)
            n = self._check_amount(amount)
            with self._lock:
                purpose = self._purposes.get(payment_ref)
            if purpose is None:  # learn it by reading (never by guessing)
                purpose = self._read_pi(payment_ref).purpose_ref
            if not purpose:
                raise _err(ProviderErrorKind.CONTRACT_RESTRICTED, "payment carries no purpose reference")
            params = {"payment_intent": payment_ref, "amount": n, "reason": "requested_by_customer",
                      "metadata": {"brandme_env": self._env, "brandme_purpose_ref": purpose,
                                   "brandme_idem": idempotency_key}}
            return self._send("refund", payment_ref, lambda: self._wire.create_refund(
                params, idempotency_key=idempotency_key), frozenset())
        return self._run("refund", _do)

    # -- webhooks --------------------------------------------------------------
    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> Optional[PaymentEvent]:
        h = {str(k).lower(): v for k, v in headers.items()}
        sig = h.get("stripe-signature")
        if sig is None:
            return None

        def _do():
            if not self.config.webhook_secrets:
                raise _err(ProviderErrorKind.NOT_CONFIGURED, "Stripe webhooks are not configured")
            from stripe import WebhookSignature  # lazy: only a configured Stripe rail verifies Stripe events

            for secret in self.config.webhook_secrets:  # current first, then previous (rotation)
                try:
                    WebhookSignature.verify_header(body, sig, secret, tolerance=None)
                    break
                except Exception:
                    continue
            else:
                raise _err(ProviderErrorKind.UNAUTHORIZED, "invalid webhook signature")
            stamps = [p[2:] for p in str(sig).split(",") if p.startswith("t=")]
            if len(stamps) != 1 or not stamps[0].isdigit():
                raise _err(ProviderErrorKind.UNAUTHORIZED, "invalid webhook signature")
            if abs(self._clock().timestamp() - int(stamps[0])) > self.config.webhook_tolerance_seconds:
                raise _err(ProviderErrorKind.UNAUTHORIZED, "webhook outside replay window")  # stale or future
            try:
                evt = json.loads(body)
            except ValueError:
                raise _err(ProviderErrorKind.MALFORMED_RESPONSE, "unreadable event") from None
            if not isinstance(evt, dict) or evt.get("object") != "event" or not _EVENT_ID.match(str(evt.get("id"))):
                raise _err(ProviderErrorKind.MALFORMED_RESPONSE, "not a Stripe event")
            if evt.get("livemode") is not False:
                self._latch()
                raise _err(ProviderErrorKind.UNAUTHORIZED, "live-mode event refused")
            etype = str(evt.get("type") or "")[:80]
            occurred = self._at(evt.get("created")) or self._clock()
            if etype not in HANDLED_EVENT_TYPES:
                return PaymentEvent(self.processor_id, str(evt["id"]), etype, None, None, None, None, occurred)
            obj = (evt.get("data") or {}).get("object") or {}
            if not isinstance(obj, Mapping):
                raise _err(ProviderErrorKind.MALFORMED_RESPONSE, "event without an object")
            if obj.get("object") == "payment_intent":
                ref, md = obj.get("id"), obj.get("metadata") or {}
            else:  # a charge or a refund
                ref, md = obj.get("payment_intent"), obj.get("metadata") or {}
                if isinstance(ref, str) and _PI_ID.match(ref) and not (
                        isinstance(md, Mapping) and md.get("brandme_purpose_ref")):
                    try:
                        md = self._wire.retrieve_payment_intent(ref).get("metadata") or {}
                    except Exception as e:
                        raise self._read_error(e) from None
            ref = ref if isinstance(ref, str) and _PI_ID.match(ref) else None
            md = md if isinstance(md, Mapping) else {}
            clean = {k: (md[k] if isinstance(md.get(k), str) and _OPAQUE.match(md[k]) else None)
                     for k in ("brandme_purpose_ref", "brandme_env", "brandme_idem")}
            return PaymentEvent(self.processor_id, str(evt["id"]), etype, ref, clean["brandme_purpose_ref"],
                                clean["brandme_env"], clean["brandme_idem"], occurred)
        return self._run("webhook", _do, lambda e: "ok" if e.payment_ref else "ignored")
