"""StripeSemanticsDouble — FIXTURE DOUBLE, NOT STRIPE.

An in-memory ``StripeWire`` that follows the documented Stripe test-mode
semantics the adapter depends on, so the real ``StripeTestPaymentProcessor``
can be driven end to end without a network or a key. Passing tests over it
prove adapter logic, never Stripe behaviour; that is the live suite's job.

Modelled: PaymentIntent lifecycle with manual capture (``requires_capture`` ->
``succeeded`` / ``canceled``), test PaymentMethods (``pm_card_visa`` approves,
``pm_card_chargeDeclined`` declines with a PaymentIntent, ``pm_card_authenticationRequired``
needs action), idempotent replay and the mismatch error, ``capture_before`` and
automatic cancellation once a hold expires, refunds that are ``succeeded`` or
(when armed) ``pending``, Search that lags writes by ``search_lag`` on the
injected clock, and a read-after-write List. ``lose_next`` loses a request or
its response, ``arm_livemode`` returns a live-mode object, ``fail_next`` raises a
chosen ``WireError``, and ``calls`` records every request for wire replay.
"""

from __future__ import annotations

import copy
import re
import secrets
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from brandme_core.domains.providers.payments.stripe_wire import WireError

HOLD = timedelta(days=7)
_SEARCH = re.compile(r"^metadata\['brandme_purpose_ref'\]:'([A-Za-z0-9_:.\-]{1,200})'$")
_PMS = {"pm_card_visa": None, "pm_card_mastercard": None, "pm_card_chargeDeclined": "generic_decline",
        "pm_card_chargeDeclinedInsufficientFunds": "insufficient_funds",
        "pm_card_authenticationRequired": "authentication_required"}


class StripeSemanticsDouble:
    def __init__(self, clock: Callable[[], datetime], *, search_lag: timedelta = timedelta(seconds=60),
                 page_size: int = 100):
        self._clock = clock
        self.search_lag = search_lag
        self.page_size = page_size
        self.intents: Dict[str, Dict[str, Any]] = {}
        self.refunds: Dict[str, Dict[str, Any]] = {}
        self._keys: Dict[str, Tuple[str, Any, Dict[str, Any]]] = {}  # idempotency key -> (method, request, response)
        self.calls: List[Tuple[str, Any, Optional[str]]] = []  # (method, request, idempotency key)
        self._lose: Dict[str, bool] = {}  # method -> lose before processing?
        self._fail: Dict[str, WireError] = {}
        self._livemode_next = False
        self.refund_status = "succeeded"

    # -- controls --------------------------------------------------------------
    def lose_next(self, method: str, *, before: bool = False) -> None:
        """The next ``method`` call raises a connection error, after processing it (default) or before."""
        self._lose[method] = before

    def fail_next(self, method: str, error: WireError) -> None:
        self._fail[method] = error

    def arm_livemode(self) -> None:
        self._livemode_next = True

    def __call__(self, config) -> "StripeSemanticsDouble":  # usable as a composition stripe_wire_factory
        return self

    # -- helpers -----------------------------------------------------------------
    def _now(self) -> int:
        return int(self._clock().timestamp())

    def _gate(self, method: str) -> Optional[bool]:
        if method in self._fail:
            raise self._fail.pop(method)
        return self._lose.pop(method, None)

    def _out(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        out = copy.deepcopy(obj)
        if self._livemode_next:
            self._livemode_next = False
            out["livemode"] = True
        return out

    def _expire(self, pi: Dict[str, Any]) -> None:
        charge = pi.get("latest_charge")
        if pi["status"] == "requires_capture" and charge and \
                self._now() >= charge["payment_method_details"]["card"]["capture_before"]:
            pi["status"], pi["cancellation_reason"], pi["amount_capturable"] = "canceled", "automatic", 0
            pi["canceled_at"] = self._now()

    def _intent(self, pi_id: str) -> Dict[str, Any]:
        pi = self.intents.get(pi_id)
        if pi is None:
            raise WireError("invalid_request", code="resource_missing", http_status=404)
        self._expire(pi)
        return pi

    def _idempotent(self, method: str, key: Optional[str], request: Any,
                    run: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        self.calls.append((method, copy.deepcopy(request), key))
        lose = self._gate(method)
        if lose is True:
            raise WireError("connection")
        if key is not None and key in self._keys:
            m, req, resp = self._keys[key]
            if (m, req) != (method, request):
                raise WireError("idempotency", http_status=400)
            if isinstance(resp, WireError):
                raise resp
            out = self._out(resp)
        else:
            try:
                resp = run()
            except WireError as e:
                if key is not None and e.kind in ("card_error", "invalid_request"):
                    self._keys[key] = (method, copy.deepcopy(request), e)  # an executed request's error replays
                raise
            if key is not None:
                self._keys[key] = (method, copy.deepcopy(request), copy.deepcopy(resp))
            out = self._out(resp)
        if lose is False:
            raise WireError("connection")  # processed; the response never arrived
        return out

    # -- StripeWire ----------------------------------------------------------------
    def create_payment_intent(self, params: Mapping[str, Any], *, idempotency_key: str) -> Dict[str, Any]:
        def run():
            p = dict(params)
            if "payment_method_types" in p or p.get("capture_method") != "manual" or not p.get("confirm"):
                raise WireError("invalid_request", code="parameter_invalid", http_status=400)
            if not isinstance(p.get("amount"), int) or p["amount"] < 50:
                raise WireError("invalid_request", code="amount_too_small", http_status=400)
            pm = p.get("payment_method")
            if pm not in _PMS:
                raise WireError("invalid_request", code="resource_missing", http_status=400)
            now = self._now()
            pi_id = "pi_" + secrets.token_hex(12)
            pi = {"id": pi_id, "object": "payment_intent", "amount": p["amount"], "amount_capturable": 0,
                  "amount_received": 0, "currency": p["currency"], "capture_method": "manual",
                  "cancellation_reason": None, "canceled_at": None, "created": now, "livemode": False,
                  "client_secret": f"{pi_id}_secret_{secrets.token_hex(8)}", "description": p.get("description"),
                  "metadata": dict(p.get("metadata") or {}), "payment_method": "pm_" + secrets.token_hex(8),
                  "last_payment_error": None, "latest_charge": None, "status": "requires_payment_method"}
            outcome = _PMS[pm]
            if outcome == "authentication_required":
                pi["status"] = "requires_action"
            elif outcome:
                pi["last_payment_error"] = {"type": "card_error", "code": "card_declined", "decline_code": outcome}
                self.intents[pi_id] = pi
                raise WireError("card_error", code="card_declined", decline_code=outcome, http_status=402,
                                payment_intent=copy.deepcopy(pi))
            else:
                pi["status"], pi["amount_capturable"] = "requires_capture", p["amount"]
                pi["latest_charge"] = {
                    "id": "ch_" + secrets.token_hex(12), "object": "charge", "amount": p["amount"],
                    "amount_captured": 0, "amount_refunded": 0, "captured": False, "status": "succeeded",
                    "payment_intent": pi_id, "livemode": False,
                    "payment_method_details": {"type": "card", "card": {"capture_before": now + int(HOLD.total_seconds()),
                                                                         "last4": "4242", "brand": "visa"}}}
            self.intents[pi_id] = pi
            return pi
        return self._idempotent("create_payment_intent", idempotency_key, dict(params), run)

    def capture_payment_intent(self, pi_id: str, params: Mapping[str, Any], *, idempotency_key: str):
        def run():
            pi = self._intent(pi_id)
            if pi["status"] == "canceled" and pi["cancellation_reason"] == "automatic":
                raise WireError("invalid_request", code="charge_expired_for_capture", http_status=400)
            if pi["status"] != "requires_capture":
                raise WireError("invalid_request", code="payment_intent_unexpected_state", http_status=400)
            n = int(params.get("amount_to_capture", pi["amount_capturable"]))
            if not 0 < n <= pi["amount_capturable"]:
                raise WireError("invalid_request", code="amount_too_large", http_status=400)
            pi.update(status="succeeded", amount_received=n, amount_capturable=0)
            pi["latest_charge"].update(captured=True, amount_captured=n)
            return pi
        return self._idempotent("capture_payment_intent", idempotency_key, (pi_id, dict(params)), run)

    def cancel_payment_intent(self, pi_id: str, params: Mapping[str, Any], *, idempotency_key: str):
        def run():
            pi = self._intent(pi_id)
            if pi["status"] not in ("requires_capture", "requires_action", "requires_payment_method",
                                    "requires_confirmation"):
                raise WireError("invalid_request", code="payment_intent_unexpected_state", http_status=400)
            pi.update(status="canceled", cancellation_reason=params.get("cancellation_reason"),
                      amount_capturable=0, canceled_at=self._now())
            return pi
        return self._idempotent("cancel_payment_intent", idempotency_key, (pi_id, dict(params)), run)

    def retrieve_payment_intent(self, pi_id: str) -> Dict[str, Any]:
        self.calls.append(("retrieve_payment_intent", pi_id, None))
        if self._gate("retrieve_payment_intent") is not None:
            raise WireError("connection")
        return self._out(self._intent(pi_id))

    def search_payment_intents(self, query: str) -> List[Dict[str, Any]]:
        self.calls.append(("search_payment_intents", query, None))
        if self._gate("search_payment_intents") is not None:
            raise WireError("connection")
        m = _SEARCH.match(query)
        if not m:
            raise WireError("invalid_request", code="parameter_invalid", http_status=400)
        visible = self._now() - int(self.search_lag.total_seconds())
        rows = [pi for pi in self.intents.values()
                if pi["metadata"].get("brandme_purpose_ref") == m.group(1) and pi["created"] <= visible]
        return [self._out(pi) for pi in rows[:10]]

    def list_payment_intents(self, *, created_gte: int, starting_after: Optional[str]):
        self.calls.append(("list_payment_intents", {"created_gte": created_gte, "starting_after": starting_after},
                           None))
        if self._gate("list_payment_intents") is not None:
            raise WireError("connection")
        rows = sorted((pi for pi in self.intents.values() if pi["created"] >= created_gte),
                      key=lambda pi: (pi["created"], pi["id"]), reverse=True)  # newest first, like Stripe
        if starting_after:
            ids = [pi["id"] for pi in rows]
            rows = rows[ids.index(starting_after) + 1:] if starting_after in ids else []
        page = rows[:self.page_size]
        return [self._out(pi) for pi in page], len(rows) > self.page_size

    def create_refund(self, params: Mapping[str, Any], *, idempotency_key: str) -> Dict[str, Any]:
        def run():
            pi = self._intent(str(params.get("payment_intent")))
            if pi["status"] != "succeeded":
                raise WireError("invalid_request", code="charge_not_refundable", http_status=400)
            open_ = sum(r["amount"] for r in self.refunds.values()
                        if r["payment_intent"] == pi["id"] and r["status"] in ("pending", "succeeded"))
            n = int(params.get("amount") or 0)
            if not 0 < n <= pi["amount_received"] - open_:
                raise WireError("invalid_request", code="amount_too_large", http_status=400)
            ref = {"id": "re_" + secrets.token_hex(12), "object": "refund", "amount": n,
                   "payment_intent": pi["id"], "status": self.refund_status, "reason": params.get("reason"),
                   "metadata": dict(params.get("metadata") or {}), "created": self._now()}
            self.refunds[ref["id"]] = ref
            pi["latest_charge"]["amount_refunded"] = open_ + n  # includes pending refunds, as Stripe's does
            return ref
        return self._idempotent("create_refund", idempotency_key, dict(params), run)

    def list_refunds(self, pi_id: str) -> List[Dict[str, Any]]:
        self.calls.append(("list_refunds", pi_id, None))
        if self._gate("list_refunds") is not None:
            raise WireError("connection")
        return [copy.deepcopy(r) for r in self.refunds.values() if r["payment_intent"] == pi_id]

    # -- test reads ------------------------------------------------------------------
    def intents_for(self, purpose_ref: str) -> List[Dict[str, Any]]:
        return [pi for pi in self.intents.values() if pi["metadata"].get("brandme_purpose_ref") == purpose_ref]

    def mutating_calls(self) -> List[Tuple[str, Any, Optional[str]]]:
        return [c for c in self.calls if c[2] is not None]
