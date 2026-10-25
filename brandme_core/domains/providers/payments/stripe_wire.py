"""The Stripe wire: the only module that imports the ``stripe`` SDK (lazily, when Stripe test mode is built).

``StripeWire`` is plain dicts in and out and raises only ``WireError``; the
payment semantics live in ``stripe_test.StripeTestPaymentProcessor``, which
tests drive over a fixture double. ``SdkStripeWire`` is the real wire:

* API version pinned (``2026-09-30.endive``); a different SDK pin refuses to build.
* No SDK retries (``max_network_retries=0``): a call is sent once, and an
  unanswered mutating call becomes ``outcome_unknown`` for the caller to reconcile.
* Egress ignores the process environment: the httpx client is built with
  ``trust_env=False`` and ``follow_redirects=False``, so no ambient
  ``HTTPS_PROXY``, ``SSL_CERT_FILE`` or netrc applies. A proxy comes only from
  ``StripeTestConfig.egress_proxy`` (``BRANDME_STRIPE_EGRESS_PROXY``) and a CA bundle
  only from ``StripeTestConfig.ca_bundle`` (``BRANDME_STRIPE_CA_BUNDLE``; default:
  the SDK's bundled CA file).
* The API base is ``https://api.stripe.com`` or a loopback stripe-mock, nothing else.
* SDK telemetry is off (process-wide) and the processor log redaction is installed.
* Errors keep a kind and Stripe's machine codes, never Stripe's message text.
"""

from __future__ import annotations

import functools
import ssl
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Protocol, Tuple

from ..redaction import install_processor_log_redaction

if TYPE_CHECKING:  # stripe_test imports this module; its guards are imported where the wire is built
    from .stripe_test import StripeTestConfig

WIRE_ERROR_KINDS = ("card_error", "authentication", "permission", "rate_limit", "invalid_request",
                    "idempotency", "connection", "api", "unknown")


class WireError(Exception):
    """A failed wire call. Carries Stripe's machine codes only; never its message text or a body."""

    def __init__(self, kind: str, *, code: Optional[str] = None, decline_code: Optional[str] = None,
                 http_status: Optional[int] = None, payment_intent: Optional[Dict[str, Any]] = None):
        if kind not in WIRE_ERROR_KINDS:
            kind = "unknown"
        super().__init__(kind)
        self.kind = kind
        self.code = str(code)[:64] if code else None
        self.decline_code = str(decline_code)[:64] if decline_code else None
        self.http_status = http_status
        self.payment_intent = payment_intent

    def __repr__(self) -> str:
        return f"WireError({self.kind!r}, code={self.code!r})"


class StripeWire(Protocol):
    def create_payment_intent(self, params: Mapping[str, Any], *, idempotency_key: str) -> Dict[str, Any]: ...

    def capture_payment_intent(self, pi_id: str, params: Mapping[str, Any], *,
                               idempotency_key: str) -> Dict[str, Any]: ...

    def cancel_payment_intent(self, pi_id: str, params: Mapping[str, Any], *,
                              idempotency_key: str) -> Dict[str, Any]: ...

    def retrieve_payment_intent(self, pi_id: str) -> Dict[str, Any]: ...  # latest_charge expanded

    def search_payment_intents(self, query: str) -> List[Dict[str, Any]]: ...  # at most 10

    def list_payment_intents(self, *, created_gte: int,
                             starting_after: Optional[str]) -> Tuple[List[Dict[str, Any]], bool]: ...  # 100 a page

    def create_refund(self, params: Mapping[str, Any], *, idempotency_key: str) -> Dict[str, Any]: ...

    def list_refunds(self, pi_id: str) -> List[Dict[str, Any]]: ...  # every page, at most 10


@functools.lru_cache(maxsize=1)
def pinned_http_client_class() -> type:
    """``stripe.HTTPXClient`` with a sync httpx client that reads nothing from the environment."""
    import anyio
    import httpx
    import stripe

    class PinnedEgressHttpClient(stripe.HTTPXClient):
        def __init__(self, *, timeout: float, proxy: Optional[str] = None, ca_bundle: Optional[str] = None):
            stripe.HTTPClient.__init__(self)  # no SDK-level proxy: it is fixed on the httpx client below
            self.httpx = httpx
            self.anyio = anyio
            context = ssl.create_default_context(cafile=ca_bundle or stripe.ca_bundle_path)
            extra = {"proxies": proxy} if proxy else {}
            self._client = httpx.Client(verify=context, trust_env=False, follow_redirects=False, timeout=timeout,
                                        **extra)
            self._client_async = None
            self._timeout = timeout

        def _get_request_args_kwargs(self, method, url, headers, post_data):
            kwargs: Dict[str, Any] = {"headers": headers, "timeout": self._timeout}
            if post_data:
                kwargs["content"] = post_data  # the form-encoded body, sent as is
            return [(method, url), kwargs]

        async def request_async(self, *args, **kwargs):  # pragma: no cover - this adapter is synchronous
            raise RuntimeError("asynchronous Stripe calls are not used")

        def close(self) -> None:
            self._client.close()

    return PinnedEgressHttpClient


class SdkStripeWire:
    def __init__(self, config: "StripeTestConfig", *, api_base: Optional[str] = None, http_client: Any = None):
        import stripe

        from .stripe_test import STRIPE_API_BASE, STRIPE_API_VERSION, require_api_base, require_test_secret_key

        if stripe.api_version != STRIPE_API_VERSION:
            raise ValueError("stripe_api_version_unverified")
        stripe.enable_telemetry = False  # process-wide: no request timings are sent back to Stripe
        install_processor_log_redaction()
        self._stripe = stripe
        hc = http_client or pinned_http_client_class()(timeout=config.timeout_seconds, proxy=config.egress_proxy,
                                                       ca_bundle=config.ca_bundle)
        self._c = stripe.StripeClient(
            require_test_secret_key(config.secret_key), stripe_version=STRIPE_API_VERSION,
            base_addresses={"api": require_api_base(api_base or STRIPE_API_BASE)},
            max_network_retries=0, http_client=hc)  # the SDK never re-sends for us

    # -- calls ---------------------------------------------------------------
    def create_payment_intent(self, params, *, idempotency_key):
        return self._call(lambda: self._c.v1.payment_intents.create(
            params=dict(params), options={"idempotency_key": idempotency_key}))

    def capture_payment_intent(self, pi_id, params, *, idempotency_key):
        return self._call(lambda: self._c.v1.payment_intents.capture(
            pi_id, params=dict(params), options={"idempotency_key": idempotency_key}))

    def cancel_payment_intent(self, pi_id, params, *, idempotency_key):
        return self._call(lambda: self._c.v1.payment_intents.cancel(
            pi_id, params=dict(params), options={"idempotency_key": idempotency_key}))

    def retrieve_payment_intent(self, pi_id):
        return self._call(lambda: self._c.v1.payment_intents.retrieve(pi_id, params={"expand": ["latest_charge"]}))

    def search_payment_intents(self, query):
        page = self._call(lambda: self._c.v1.payment_intents.search(params={"query": query, "limit": 10}),
                          as_dict=False)
        return [o.to_dict() for o in (page.data or [])]

    def list_payment_intents(self, *, created_gte, starting_after):
        params: Dict[str, Any] = {"created": {"gte": int(created_gte)}, "limit": 100}
        if starting_after:
            params["starting_after"] = starting_after
        page = self._call(lambda: self._c.v1.payment_intents.list(params=params), as_dict=False)
        return [o.to_dict() for o in (page.data or [])], bool(page.has_more)

    def create_refund(self, params, *, idempotency_key):
        return self._call(lambda: self._c.v1.refunds.create(
            params=dict(params), options={"idempotency_key": idempotency_key}))

    def list_refunds(self, pi_id):
        out: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        for _ in range(10):
            params: Dict[str, Any] = {"payment_intent": pi_id, "limit": 100}
            if cursor:
                params["starting_after"] = cursor
            page = self._call(lambda: self._c.v1.refunds.list(params=params), as_dict=False)
            rows = [o.to_dict() for o in (page.data or [])]
            out.extend(rows)
            if not page.has_more or not rows:
                return out
            cursor = rows[-1]["id"]
        raise WireError("unknown", code="refund_list_too_long")

    # -- errors --------------------------------------------------------------
    def _call(self, fn, *, as_dict: bool = True):
        try:
            result = fn()
        except WireError:
            raise
        except Exception as exc:
            raise self._translate(exc) from None
        return result.to_dict() if as_dict else result

    def _translate(self, exc: Exception) -> WireError:
        s = self._stripe
        status = getattr(exc, "http_status", None)
        if isinstance(exc, s.CardError):
            err = getattr(exc, "error", None)
            intent = getattr(err, "payment_intent", None)
            return WireError("card_error", code=getattr(exc, "code", None),
                             decline_code=getattr(err, "decline_code", None), http_status=status,
                             payment_intent=intent.to_dict() if hasattr(intent, "to_dict") else None)
        for cls, kind in ((s.IdempotencyError, "idempotency"), (s.InvalidRequestError, "invalid_request"),
                          (s.AuthenticationError, "authentication"), (s.PermissionError, "permission"),
                          (s.RateLimitError, "rate_limit"), (s.APIConnectionError, "connection"),
                          (s.APIError, "api")):
            if isinstance(exc, cls):
                return WireError(kind, code=getattr(exc, "code", None), http_status=status)
        return WireError("unknown", http_status=status)
