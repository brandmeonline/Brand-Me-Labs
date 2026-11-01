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

Connect: every PaymentIntent and refund lives on one account (``None`` is the platform,
``acct_…`` a connected account, as the ``Stripe-Account`` header selects). An object is
invisible from any other account (``resource_missing``), Search and List are per account,
and idempotency keys are scoped per account, as Stripe scopes them. ``call_accounts`` records
the account of every call, in step with ``calls``. Accounts v2 objects are modelled only as far
as the Connect onboarding service reads them (dashboard, responsibilities, merchant
capabilities, requirements); ``set_capability`` stands in for Stripe's verification.
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
        self._corrupt: Dict[str, Any] = {}
        self.refund_status = "succeeded"
        self.call_accounts: List[Optional[str]] = []  # the Stripe-Account of each entry in ``calls``
        self.accounts: Dict[str, Dict[str, Any]] = {}
        self.links: List[Dict[str, Any]] = []
        self.sessions: List[Dict[str, Any]] = []

    # -- controls --------------------------------------------------------------
    def lose_next(self, method: str, *, before: bool = False) -> None:
        """The next ``method`` call raises a connection error, after processing it (default) or before."""
        self._lose[method] = before

    def fail_next(self, method: str, error: WireError) -> None:
        self._fail[method] = error

    def arm_livemode(self) -> None:
        self._livemode_next = True

    def corrupt_next_create(self, **fields: Any) -> None:
        """The next created PaymentIntent is stored and answered with these fields changed (e.g. amount)."""
        self._corrupt = fields

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
        out = {k: copy.deepcopy(v) for k, v in obj.items() if not k.startswith("_")}
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

    def _record(self, method: str, request: Any, key: Optional[str], account: Optional[str]) -> None:
        self.calls.append((method, copy.deepcopy(request), key))
        self.call_accounts.append(account)

    def _intent(self, pi_id: str, account: Optional[str] = None) -> Dict[str, Any]:
        pi = self.intents.get(pi_id)
        if pi is None or pi["_account"] != account:
            raise WireError("invalid_request", code="resource_missing", http_status=404)
        self._expire(pi)
        return pi

    def _idempotent(self, method: str, key: Optional[str], request: Any,
                    run: Callable[[], Dict[str, Any]], account: Optional[str] = None) -> Dict[str, Any]:
        self._record(method, request, key, account)
        lose = self._gate(method)
        if lose is True:
            raise WireError("connection")
        scoped = None if key is None else f"{account or ''}|{key}"  # Stripe scopes keys per account
        if scoped is not None and scoped in self._keys:
            m, req, resp = self._keys[scoped]
            if (m, req) != (method, request):
                raise WireError("idempotency", http_status=400)
            if isinstance(resp, WireError):
                raise resp
            out = self._out(resp)
        else:
            try:
                resp = run()
            except WireError as e:
                if scoped is not None and e.kind in ("card_error", "invalid_request"):
                    self._keys[scoped] = (method, copy.deepcopy(request), e)  # an executed request's error replays
                raise
            if scoped is not None:
                self._keys[scoped] = (method, copy.deepcopy(request), copy.deepcopy(resp))
            out = self._out(resp)
        if lose is False:
            raise WireError("connection")  # processed; the response never arrived
        return out

    # -- StripeWire ----------------------------------------------------------------
    def create_payment_intent(self, params: Mapping[str, Any], *, idempotency_key: str,
                              stripe_account: Optional[str] = None) -> Dict[str, Any]:
        def run():
            p = dict(params)
            fee = p.get("application_fee_amount")
            if fee is not None and (stripe_account is None or not isinstance(fee, int) or not 0 <= fee <= p.get(
                    "amount", 0)):  # an application fee exists only on a charge made on a connected account
                raise WireError("invalid_request", code="parameter_invalid", http_status=400)
            if stripe_account is not None:
                self._ready(stripe_account)
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
                  "last_payment_error": None, "latest_charge": None, "status": "requires_payment_method",
                  "application_fee_amount": fee, "_account": stripe_account}
            outcome = _PMS[pm]
            if outcome == "authentication_required":
                pi["status"] = "requires_action"
            elif outcome:
                pi["last_payment_error"] = {"type": "card_error", "code": "card_declined", "decline_code": outcome}
                self.intents[pi_id] = pi
                raise WireError("card_error", code="card_declined", decline_code=outcome, http_status=402,
                                payment_intent=self._out(pi))
            else:
                pi["status"], pi["amount_capturable"] = "requires_capture", p["amount"]
                pi["latest_charge"] = {
                    "id": "ch_" + secrets.token_hex(12), "object": "charge", "amount": p["amount"],
                    "amount_captured": 0, "amount_refunded": 0, "captured": False, "status": "succeeded",
                    "payment_intent": pi_id, "livemode": False,
                    "payment_method_details": {"type": "card", "card": {"capture_before": now + int(HOLD.total_seconds()),
                                                                         "last4": "4242", "brand": "visa"}}}
            if self._corrupt:
                pi.update(self._corrupt)
                if "amount" in self._corrupt and pi["status"] == "requires_capture":
                    pi["amount_capturable"] = pi["amount"]
                self._corrupt = {}
            self.intents[pi_id] = pi
            return pi
        return self._idempotent("create_payment_intent", idempotency_key, dict(params), run, stripe_account)

    def capture_payment_intent(self, pi_id: str, params: Mapping[str, Any], *, idempotency_key: str,
                               stripe_account: Optional[str] = None):
        def run():
            pi = self._intent(pi_id, stripe_account)
            if pi["status"] == "canceled" and pi["cancellation_reason"] == "automatic":
                raise WireError("invalid_request", code="charge_expired_for_capture", http_status=400)
            if pi["status"] != "requires_capture":
                raise WireError("invalid_request", code="payment_intent_unexpected_state", http_status=400)
            n = int(params.get("amount_to_capture", pi["amount_capturable"]))
            if not 0 < n <= pi["amount_capturable"]:
                raise WireError("invalid_request", code="amount_too_large", http_status=400)
            fee = params.get("application_fee_amount", pi["application_fee_amount"])
            if fee is not None and (stripe_account is None or not isinstance(fee, int) or not 0 <= fee <= n):
                raise WireError("invalid_request", code="parameter_invalid", http_status=400)
            pi.update(status="succeeded", amount_received=n, amount_capturable=0, application_fee_amount=fee)
            pi["latest_charge"].update(captured=True, amount_captured=n)
            return pi
        return self._idempotent("capture_payment_intent", idempotency_key, (pi_id, dict(params)), run,
                                stripe_account)

    def cancel_payment_intent(self, pi_id: str, params: Mapping[str, Any], *, idempotency_key: str,
                              stripe_account: Optional[str] = None):
        def run():
            pi = self._intent(pi_id, stripe_account)
            if pi["status"] not in ("requires_capture", "requires_action", "requires_payment_method",
                                    "requires_confirmation"):
                raise WireError("invalid_request", code="payment_intent_unexpected_state", http_status=400)
            pi.update(status="canceled", cancellation_reason=params.get("cancellation_reason"),
                      amount_capturable=0, canceled_at=self._now())
            return pi
        return self._idempotent("cancel_payment_intent", idempotency_key, (pi_id, dict(params)), run,
                                stripe_account)

    def retrieve_payment_intent(self, pi_id: str, *, stripe_account: Optional[str] = None) -> Dict[str, Any]:
        self._record("retrieve_payment_intent", pi_id, None, stripe_account)
        if self._gate("retrieve_payment_intent") is not None:
            raise WireError("connection")
        return self._out(self._intent(pi_id, stripe_account))

    def search_payment_intents(self, query: str, *, stripe_account: Optional[str] = None) -> List[Dict[str, Any]]:
        self._record("search_payment_intents", query, None, stripe_account)
        if self._gate("search_payment_intents") is not None:
            raise WireError("connection")
        m = _SEARCH.match(query)
        if not m:
            raise WireError("invalid_request", code="parameter_invalid", http_status=400)
        visible = self._now() - int(self.search_lag.total_seconds())
        rows = [pi for pi in self.intents.values()
                if pi["metadata"].get("brandme_purpose_ref") == m.group(1) and pi["created"] <= visible
                and pi["_account"] == stripe_account]
        return [self._out(pi) for pi in rows[:10]]

    def list_payment_intents(self, *, created_gte: int, starting_after: Optional[str],
                             stripe_account: Optional[str] = None):
        self._record("list_payment_intents", {"created_gte": created_gte, "starting_after": starting_after}, None,
                     stripe_account)
        if self._gate("list_payment_intents") is not None:
            raise WireError("connection")
        rows = sorted((pi for pi in self.intents.values()
                       if pi["created"] >= created_gte and pi["_account"] == stripe_account),
                      key=lambda pi: (pi["created"], pi["id"]), reverse=True)  # newest first, like Stripe
        if starting_after:
            ids = [pi["id"] for pi in rows]
            rows = rows[ids.index(starting_after) + 1:] if starting_after in ids else []
        page = rows[:self.page_size]
        return [self._out(pi) for pi in page], len(rows) > self.page_size

    def create_refund(self, params: Mapping[str, Any], *, idempotency_key: str,
                      stripe_account: Optional[str] = None) -> Dict[str, Any]:
        def run():
            pi = self._intent(str(params.get("payment_intent")), stripe_account)
            if "refund_application_fee" in params and stripe_account is None:
                raise WireError("invalid_request", code="parameter_invalid", http_status=400)
            if pi["status"] != "succeeded":
                raise WireError("invalid_request", code="charge_not_refundable", http_status=400)
            open_ = sum(r["amount"] for r in self.refunds.values()
                        if r["payment_intent"] == pi["id"] and r["status"] in ("pending", "succeeded"))
            n = int(params.get("amount") or 0)
            if not 0 < n <= pi["amount_received"] - open_:
                raise WireError("invalid_request", code="amount_too_large", http_status=400)
            ref = {"id": "re_" + secrets.token_hex(12), "object": "refund", "amount": n,
                   "payment_intent": pi["id"], "status": self.refund_status, "reason": params.get("reason"),
                   "metadata": dict(params.get("metadata") or {}), "created": self._now(),
                   "_refund_application_fee": bool(params.get("refund_application_fee"))}
            self.refunds[ref["id"]] = ref
            pi["latest_charge"]["amount_refunded"] = open_ + n  # includes pending refunds, as Stripe's does
            return ref
        return self._idempotent("create_refund", idempotency_key, dict(params), run, stripe_account)

    def list_refunds(self, pi_id: str, *, stripe_account: Optional[str] = None) -> List[Dict[str, Any]]:
        self._record("list_refunds", pi_id, None, stripe_account)
        if self._gate("list_refunds") is not None:
            raise WireError("connection")
        pi = self.intents.get(pi_id)
        if pi is not None and pi["_account"] != stripe_account:
            return []  # another account's refunds are not visible
        return [self._out(r) for r in self.refunds.values() if r["payment_intent"] == pi_id]

    # -- Connect: Accounts v2 (StripeConnectWire) --------------------------------------
    def _ready(self, account_id: str) -> None:
        acct = self.accounts.get(account_id)
        if acct is None:
            raise WireError("permission", code="account_invalid", http_status=403)
        if acct["configuration"]["merchant"]["capabilities"]["card_payments"]["status"] != "active":
            raise WireError("invalid_request", code="account_capability_not_active", http_status=400)

    def create_account(self, params: Mapping[str, Any], *, idempotency_key: str) -> Dict[str, Any]:
        def run():
            p = copy.deepcopy(dict(params))
            if "type" in p or p.get("dashboard") not in ("express", "full", "none"):
                raise WireError("invalid_request", code="parameter_invalid", http_status=400)
            resp = (p.get("defaults") or {}).get("responsibilities") or {}
            requested = (((p.get("configuration") or {}).get("merchant") or {}).get("capabilities") or {})
            acct_id = "acct_" + secrets.token_hex(8)
            pending = "pending" if (requested.get("card_payments") or {}).get("requested") else "unsupported"
            self.accounts[acct_id] = {
                "id": acct_id, "object": "v2.core.account", "livemode": False, "dashboard": p["dashboard"],
                "display_name": p.get("display_name"), "metadata": dict(p.get("metadata") or {}),
                "applied_configurations": ["merchant"] if requested else [],
                "defaults": {"currency": (p.get("defaults") or {}).get("currency"), "responsibilities": resp},
                "identity": {"country": (p.get("identity") or {}).get("country")},
                "configuration": {"merchant": {"capabilities": {
                    "card_payments": {"status": pending}, "stripe_balance": {"payouts": {"status": pending}}}}},
                "requirements": {"entries": [{"description": "business_profile"},
                                             {"description": "external_account"}]}}
            return self._account_view(self.accounts[acct_id], p.get("include") or [])
        return self._idempotent("create_account", idempotency_key, copy.deepcopy(dict(params)), run)

    @staticmethod
    def _account_view(acct: Dict[str, Any], include: List[str]) -> Dict[str, Any]:
        out = {k: copy.deepcopy(v) for k, v in acct.items() if k not in ("configuration", "defaults", "requirements")}
        out["configuration"] = ({"merchant": copy.deepcopy(acct["configuration"]["merchant"])}
                                if "configuration.merchant" in include else None)
        out["defaults"] = copy.deepcopy(acct["defaults"]) if "defaults" in include else None
        out["requirements"] = copy.deepcopy(acct["requirements"]) if "requirements" in include else None
        return out

    def retrieve_account(self, account_id: str, *, include: List[str]) -> Dict[str, Any]:
        self._record("retrieve_account", (account_id, list(include)), None, None)
        if self._gate("retrieve_account") is not None:
            raise WireError("connection")
        acct = self.accounts.get(account_id)
        if acct is None:
            raise WireError("invalid_request", code="resource_missing", http_status=404)
        return self._out(self._account_view(acct, include))

    def create_account_link(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        self._record("create_account_link", dict(params), None, None)
        if self._gate("create_account_link") is not None:
            raise WireError("connection")
        if params.get("account") not in self.accounts:
            raise WireError("invalid_request", code="resource_missing", http_status=404)
        link = {"object": "v2.core.account_link", "account": params["account"], "livemode": False,
                "url": "https://connect.stripe.com/setup/test/" + secrets.token_hex(8),
                "expires_at": self._now() + 300, "use_case": copy.deepcopy(params.get("use_case"))}
        self.links.append(link)
        return copy.deepcopy(link)

    def create_account_session(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        self._record("create_account_session", dict(params), None, None)
        if self._gate("create_account_session") is not None:
            raise WireError("connection")
        if params.get("account") not in self.accounts:
            raise WireError("invalid_request", code="resource_missing", http_status=404)
        sess = {"object": "account_session", "account": params["account"], "livemode": False,
                "client_secret": "accs_secret__" + secrets.token_hex(12), "expires_at": self._now() + 1800,
                "components": copy.deepcopy(params.get("components"))}
        self.sessions.append(sess)
        return copy.deepcopy(sess)

    # -- Connect test controls ------------------------------------------------------------
    def set_capability(self, account_id: str, status: str, *, payouts: Optional[str] = None) -> None:
        """Stands in for Stripe finishing (or reversing) verification of a connected account."""
        caps = self.accounts[account_id]["configuration"]["merchant"]["capabilities"]
        caps["card_payments"]["status"] = status
        caps["stripe_balance"]["payouts"]["status"] = payouts or status
        if status == "active":
            self.accounts[account_id]["requirements"]["entries"] = []

    def add_account(self, *, dashboard: str = "full", fees_collector: str = "stripe", losses_collector: str = "stripe",
                    card_payments: str = "active", livemode: bool = False) -> str:
        """A connected account that already exists on the platform (onboarded outside this test)."""
        acct_id = "acct_" + secrets.token_hex(8)
        self.accounts[acct_id] = {
            "id": acct_id, "object": "v2.core.account", "livemode": livemode, "dashboard": dashboard,
            "display_name": "fixture brand", "metadata": {}, "applied_configurations": ["merchant"],
            "defaults": {"currency": "usd", "responsibilities": {"fees_collector": fees_collector,
                                                                  "losses_collector": losses_collector}},
            "identity": {"country": "us"},
            "configuration": {"merchant": {"capabilities": {
                "card_payments": {"status": card_payments}, "stripe_balance": {"payouts": {"status": card_payments}}}}},
            "requirements": {"entries": []}}
        return acct_id


    # -- test reads ------------------------------------------------------------------
    def intents_for(self, purpose_ref: str) -> List[Dict[str, Any]]:
        return [pi for pi in self.intents.values() if pi["metadata"].get("brandme_purpose_ref") == purpose_ref]

    def mutating_calls(self) -> List[Tuple[str, Any, Optional[str]]]:
        return [c for c in self.calls if c[2] is not None]
