"""Locally signed Stripe-shaped webhook events and HTTP clients that lose or record traffic.

Signatures are HMAC-SHA256 over ``f"{t}.{body}"`` with a ``whsec_`` secret the
test generates at runtime (no secret is committed). These build what Stripe's
signing scheme looks like; they are not Stripe.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any, Dict, List, Optional, Tuple


def webhook_secret() -> str:
    return "whsec_" + secrets.token_hex(16)


def event(event_type: str, obj: Dict[str, Any], *, created: int, livemode: bool = False,
          event_id: Optional[str] = None) -> Dict[str, Any]:
    return {"id": event_id or "evt_" + secrets.token_hex(12), "object": "event", "type": event_type,
            "livemode": livemode, "created": created, "data": {"object": obj}}


def signed(payload: Dict[str, Any], secret: str, at: int, *, extra_v1: Optional[str] = None) -> Tuple[Dict[str, str], bytes]:
    body = json.dumps(payload).encode()
    sig = hmac.new(secret.encode(), f"{at}.".encode() + body, hashlib.sha256).hexdigest()
    header = f"t={at},v1={sig}" + (f",v1={extra_v1}" if extra_v1 else "")
    return {"Stripe-Signature": header}, body


def payment_intent_event(pi: Dict[str, Any], event_type: str, secret: str, at: int, **kw) -> Tuple[Dict[str, str], bytes]:
    obj = {"id": pi["id"], "object": "payment_intent", "status": pi.get("status"),
           "metadata": dict(pi.get("metadata") or {}), "livemode": False}
    return signed(event(event_type, obj, created=at, **kw), secret, at)


def _client_base():
    from brandme_core.domains.providers.payments.stripe_wire import pinned_http_client_class
    return pinned_http_client_class()


def recording_client(timeout: float = 20.0):
    """A pinned egress client that records (method, url, headers) of every attempt."""
    base = _client_base()

    class Recording(base):
        def __init__(self):
            super().__init__(timeout=timeout)
            self.attempts: List[Tuple[str, str, Dict[str, str]]] = []

        def request(self, method, url, headers, post_data=None):
            self.attempts.append((method.upper(), url, {k.lower(): v for k, v in dict(headers).items()}))
            return super().request(method, url, headers, post_data)

    return Recording()


def lose_response_client(timeout: float = 20.0, *, lose: int = 1, methods: Tuple[str, ...] = ("post",)):
    """Sends the request, then raises a connection error instead of returning the response (``lose`` times)."""
    import stripe

    base = _client_base()

    class LoseResponse(base):
        def __init__(self):
            super().__init__(timeout=timeout)
            self.remaining = lose
            self.lost: List[str] = []

        def request(self, method, url, headers, post_data=None):
            out = super().request(method, url, headers, post_data)
            if self.remaining > 0 and method.lower() in methods:
                self.remaining -= 1
                self.lost.append(url.split("?")[0].rsplit("/", 1)[-1])
                raise stripe.APIConnectionError("response lost (test)")
            return out

    return LoseResponse()
