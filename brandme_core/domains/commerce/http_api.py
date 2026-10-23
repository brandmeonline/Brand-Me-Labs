"""Internal HTTP API of the commerce domain — UNMOUNTED (lane: opus-commerce-agents).

``POST /internal/commerce/v1/{operation}`` is what the gateway's ``/api/v1``
routers forward to (``brandme-gateway/src/routes/v1/commerceClient.ts``).
Nothing starts this app yet: wiring it into a service and docker-compose is
integration work.

* **Authentication:** ``Authorization: Bearer <gateway assertion>``. ES256,
  ``aud`` ``brandme:commerce-domain``, at most 60 s, single-use ``jti``,
  carrying the gateway-resolved principal. A first-party session principal is
  valid on this hop and never on the MCP hop. Provider webhooks use a
  principal-less service assertion, and the domain then verifies the
  provider's own signature.
* **Request:** a JSON object with exactly the operation's arguments (no
  identity fields), plus ``Idempotency-Key`` / ``If-Match`` headers where the
  operation needs them.
* **Errors:** ``application/problem+json`` from ``DomainError`` (status, code,
  detail). Stack traces and provider bodies are never returned.
"""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from brandme_core.domains.base import DomainError
from brandme_core.domains.providers.catalog import search_catalog, untrusted_text
from brandme_core.domains.providers.contracts import CartLineRequest, ProviderError
from brandme_core.domains.providers.registry import RegistryError
from brandme_core.domains.providers.setup import SETUP_UPDATE_FIELDS, ProviderSetupService
from brandme_core.mcp.authz import DOMAIN_AUDIENCE, AuthError, ExecutorAssertionVerifier
from brandme_core.orchestrator.runtime import IdempotencyReuse, TaskConstraints

from .delegation import AssistanceMode, DelegationLimits
from .errors import AssistantBusy, Forbidden, IdempotencyConflict, InvalidRequest, NotFound
from .money import Money, MoneyError
from .principal import Principal, is_first_party
from .records import ApprovalChallenge, Cart, Order, PurchaseApproval, PurchaseOperation
from .service import CommerceService, _uuid_or_none, correlation

PREFIX = "/internal/commerce/v1"
ASSISTANT_CLIENT_ID = "brandme-assistant"  # Brand.Me's own assistant acts only under a grant to this client
PROVIDER_ADMIN_SCOPE = "provider:admin"


def _iso(ts) -> Optional[str]:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


def problem_body(status: int, code: str, detail: str, **extra: Any) -> Dict[str, Any]:
    return {"type": f"https://brand.me/problems/{code}", "title": code.replace("_", " "), "status": status,
            "code": code, "detail": detail, "retryable": status in (429, 503), **extra}


def _problem(status: int, code: str, detail: str, headers: Optional[Dict[str, str]] = None, **extra: Any) -> Response:
    return JSONResponse(problem_body(status, code, detail, **extra), status_code=status,
                        media_type="application/problem+json", headers=headers)


# ------------------------------------------------------------------- wire shapes
def cart_wire(c: Cart) -> Dict[str, Any]:
    return {"id": c.id, "provider_id": c.provider_id, "merchant_id": c.merchant_id, "status": c.status,
            "revision": str(c.revision),
            "lines": [{"variant_id": l.variant_id, "source_variant_ref": l.source_variant_ref, "quantity": l.quantity}
                      for l in c.lines]}


def operation_wire(o: PurchaseOperation) -> Dict[str, Any]:
    out = {"id": o.id, "state": o.state, "quote_id": o.quote_id, "quote_hash": o.quote_hash,
           "provider_id": o.provider_id, "approval_id": o.approval_id, "order_id": o.order_id,
           "delegation_id": o.delegation_id, "reason_code": o.reason_code, "version": str(o.version),
           "updated_at": _iso(o.updated_at)}
    if o.state == "outcome_unknown":
        out["message"] = "We are checking whether the retailer accepted this order."
    return out


def challenge_wire(c: ApprovalChallenge) -> Dict[str, Any]:
    # The trusted surface needs the plaintext nonce exactly once, to post it back with the approval.
    return {"id": c.id, "operation_id": c.operation_id, "quote_id": c.quote_id, "quote_hash": c.quote_hash,
            "nonce": c.nonce, "expires_at": _iso(c.expires_at)}


def approval_wire(a: PurchaseApproval) -> Dict[str, Any]:
    return {"id": a.id, "quote_id": a.quote_id, "quote_hash": a.quote_hash, "merchant_id": a.merchant_id,
            "allowed_total": a.allowed_total.to_wire(), "expires_at": _iso(a.expires_at), "method": a.method,
            "assurance_level": a.assurance_level, "materiality_rule": a.materiality_rule, "state": a.state,
            "delegation_ref": a.delegation_ref}


def order_wire(o: Order) -> Dict[str, Any]:
    return {"id": o.id, "operation_id": o.operation_id, "provider_id": o.provider_id, "merchant_id": o.merchant_id,
            "order_status": o.order_status, "payment_status": o.payment_status,
            "fulfillment_status": o.fulfillment_status, "total": o.total.to_wire(),
            "refunded_total": o.refunded_total.to_wire(), "last_observed_at": _iso(o.last_observed_at),
            "lines": [{"variant_id": l.variant_id, "source_variant_ref": l.source_variant_ref,
                       "ordered": l.quantity_ordered, "shipped": l.quantity_shipped,
                       "delivered": l.quantity_delivered, "returned": l.quantity_returned,
                       "exchanged_from_ref": l.exchanged_from_ref} for l in o.lines],
            "version": str(o.version)}


def delegation_wire(d) -> Dict[str, Any]:
    lim = d.limits
    return {"id": d.id, "client_id": d.client_id, "mode": d.mode.value, "scopes": sorted(d.scopes),
            "allowed_providers": sorted(d.allowed_providers), "created_at": _iso(d.created_at),
            "expires_at": _iso(d.expires_at), "revoked_at": _iso(d.revoked_at), "version": str(d.version),
            "limits": None if lim is None else {
                "currency": lim.currency, "max_per_order": lim.max_per_order.to_wire(),
                "max_cumulative": lim.max_cumulative.to_wire(), "window_seconds": lim.window_seconds,
                "allowed_merchants": sorted(lim.allowed_merchants), "allowed_categories": sorted(lim.allowed_categories),
                "delivery_ref": lim.delivery_ref, "require_returnable": lim.require_returnable,
                "refund_credit_back": lim.refund_credit_back,
                "require_final_human_approval": lim.require_final_human_approval}}


def _summary_state(conn, capability: str) -> str:
    st = conn.capability(capability).state
    if st in ("verified",):
        return "available"
    if st == "sandbox":
        return "simulated" if conn.simulation else "available"
    if st == "degraded":
        return "degraded"
    if st == "unsupported":
        return "unsupported"
    return "unconfigured"  # unconfigured | suspended


# ------------------------------------------------------------------- operations
Handler = Callable[[Principal, Dict[str, Any], Mapping[str, str]], Tuple[int, Any]]


class CommerceHttpApi:
    def __init__(self, *, service: CommerceService, verifier: ExecutorAssertionVerifier,
                 runtime: Any = None, planner_factory: Optional[Callable[[], Any]] = None,
                 setup_store: Any = None, task_runner: Any = None):
        if verifier.audience != DOMAIN_AUDIENCE or not verifier.allow_session:
            raise ValueError("the commerce domain hop needs a verifier for brandme:commerce-domain with sessions")
        self.svc = service
        self.verifier = verifier
        self.runtime = runtime
        self.planner_factory = planner_factory
        # Runs planners marked ``runs_in_background`` (model runs) off the request (``BackgroundRunner``).
        self.task_runner = task_runner
        # Operator setup and connection tests; the store defaults to in-memory (InMemoryProviderSetupStore).
        self.setup = ProviderSetupService(service.registry, setup_store, clock=service.clock)
        # operation -> (allowed argument names, handler)
        self.ops: Dict[str, Tuple[frozenset, Handler]] = {
            "cart.create": (frozenset({"provider_id", "merchant_id", "lines"}), self._cart_create),
            "cart.update": (frozenset({"cart_id", "lines"}), self._cart_update),
            "cart.quote": (frozenset({"cart_id"}), self._cart_quote),
            "purchase.request": (frozenset({"quote_id"}), self._purchase_request),
            "approval.challenge": (frozenset({"operation_id"}), self._approval_challenge),
            "approval.create": (frozenset({"operation_id", "challenge_id", "nonce", "displayed_quote_hash"}),
                                self._approval_create),
            "purchase.execute": (frozenset({"quote_id", "approval_id", "delegation_id"}), self._purchase_execute),
            "operation.get": (frozenset({"operation_id"}), self._operation_get),
            "order.get": (frozenset({"order_id"}), self._order_get),
            "order.return": (frozenset({"order_id", "source_variant_ref", "quantity"}), self._order_return),
            "order.cancel": (frozenset({"order_id"}), self._order_cancel),
            "delegation.list": (frozenset(), self._delegation_list),
            "delegation.create": (frozenset({"client_id", "mode", "allowed_providers", "expires_at", "limits"}),
                                  self._delegation_create),
            "delegation.revoke": (frozenset({"delegation_id"}), self._delegation_revoke),
            "catalog.search": (frozenset({"q", "provider", "cursor", "limit"}), self._catalog_search),
            "catalog.product": (frozenset({"product_id"}), self._catalog_product),
            "capabilities.effective": (frozenset(), self._capabilities),
            "provider.list": (frozenset(), self._provider_list),
            "provider.get": (frozenset({"provider_id"}), self._provider_get),
            "provider.health": (frozenset({"provider_id"}), self._provider_health),
            "provider.setup.get": (frozenset({"provider_id"}), self._provider_setup_get),
            "provider.setup.update": (frozenset({"provider_id"}) | SETUP_UPDATE_FIELDS, self._provider_setup_update),
            "provider.verify": (frozenset({"provider_id", "capability", "mode"}), self._provider_verify),
            "provider.runs": (frozenset({"provider_id", "capability", "limit"}), self._provider_runs),
            "commerce.ops.queue": (frozenset(), lambda p, a, h: (200, self.svc.operator_queue(p))),
            "assistant.task.create": (frozenset({"goal", "assistance_mode", "budget_hint"}), self._task_create),
            "assistant.task.cancel": (frozenset({"task_id"}), self._task_cancel),
            "assistant.task.events": (frozenset({"task_id", "after"}), self._task_events),
        }

    # -- dispatch ------------------------------------------------------------
    def dispatch(self, operation: str, authorization: Optional[str], body: bytes,
                 headers: Mapping[str, str]) -> Tuple[int, Any, Dict[str, str]]:
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthError(401, "invalid_token", "gateway assertion required")
        principal = self.verifier.verify(authorization[7:])
        if operation not in self.ops:
            return 404, problem_body(404, "unknown_operation", "unknown commerce operation"), {}
        allowed, handler = self.ops[operation]
        try:
            args = json.loads(body or b"{}")
        except ValueError:
            raise InvalidRequest("request body is not valid JSON") from None
        if not isinstance(args, dict):
            raise InvalidRequest("request body must be a JSON object")
        if allowed is not None and set(args) - allowed:
            # Identity, scope and approval never come from request fields.
            raise InvalidRequest(f"unexpected fields: {sorted(set(args) - allowed)}", code="unexpected_field")
        with correlation(headers.get("x-request-id")):  # the gateway's request id, when it is a UUID
            status, payload = handler(principal, args, headers)
        extra = {"ETag": f'"{payload["revision"]}"'} if isinstance(payload, dict) and "revision" in payload else {}
        return status, payload, extra

    def receive_webhook(self, provider_id: str, authorization: Optional[str], body: bytes) -> Tuple[int, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthError(401, "invalid_token", "gateway service assertion required")
        self.verifier.verify_service(authorization[7:])
        envelope = json.loads(body or b"{}")
        raw = base64.b64decode(envelope.get("body_b64", ""), validate=True)
        provider_headers = {str(k).lower(): str(v) for k, v in (envelope.get("headers") or {}).items()}
        receipt = self.svc.handle_webhook(provider_id, provider_headers, raw)
        return 200, {"received": True, "state": receipt.state}

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _need(args: Dict[str, Any], *names: str) -> None:
        missing = [n for n in names if n not in args]
        if missing:
            raise InvalidRequest(f"missing fields: {missing}")

    @staticmethod
    def _lines(raw: Any):
        if not isinstance(raw, list):
            raise InvalidRequest("lines must be an array")
        try:
            return [CartLineRequest(str(l["variant_id"]), str(l["source_variant_ref"]), int(l["quantity"])) for l in raw]
        except (KeyError, TypeError, ValueError):
            raise InvalidRequest("each line needs variant_id, source_variant_ref and an integer quantity") from None

    @staticmethod
    def _if_match(headers: Mapping[str, str]) -> int:
        from brandme_core.domains.base import parse_if_match
        return parse_if_match(headers.get("if-match"))

    def _require_admin(self, p: Principal) -> None:
        if p.environment != self.svc.environment:
            raise Forbidden("principal environment mismatch")
        if PROVIDER_ADMIN_SCOPE not in p.scopes:  # an operator role; never implied by a member session
            raise Forbidden(f"scope {PROVIDER_ADMIN_SCOPE} required", code="insufficient_scope")

    def _connection(self, provider_id: str):
        try:
            return self.svc.registry.get(provider_id)
        except RegistryError:
            raise NotFound("provider not found") from None

    # -- commerce ------------------------------------------------------------
    def _cart_create(self, p, a, h):
        self._need(a, "provider_id", "merchant_id", "lines")
        cart = self.svc.create_cart(p, provider_id=str(a["provider_id"]), merchant_id=str(a["merchant_id"]),
                                    lines=self._lines(a["lines"]), idempotency_key=h.get("idempotency-key"))
        return 201, cart_wire(cart)

    def _cart_update(self, p, a, h):
        self._need(a, "cart_id", "lines")
        cart = self.svc.update_cart(p, str(a["cart_id"]), if_match=self._if_match(h), lines=self._lines(a["lines"]))
        return 200, cart_wire(cart)

    def _cart_quote(self, p, a, h):
        self._need(a, "cart_id")
        q = self.svc.quote_cart(p, str(a["cart_id"]))
        return 200, q.to_wire()

    def _purchase_request(self, p, a, h):
        self._need(a, "quote_id")
        return 201, operation_wire(self.svc.request_purchase(p, str(a["quote_id"])))

    def _approval_challenge(self, p, a, h):
        self._need(a, "operation_id")
        return 201, challenge_wire(self.svc.open_approval_challenge(p, str(a["operation_id"])))

    def _approval_create(self, p, a, h):
        self._need(a, "operation_id", "challenge_id", "nonce", "displayed_quote_hash")
        approval = self.svc.approve(p, operation_id=str(a["operation_id"]), challenge_id=str(a["challenge_id"]),
                                    nonce=str(a["nonce"]), displayed_quote_hash=str(a["displayed_quote_hash"]))
        return 201, approval_wire(approval)

    def _purchase_execute(self, p, a, h):
        self._need(a, "quote_id", "approval_id", "delegation_id")
        op = self.svc.execute_approved_quote(p, quote_id=str(a["quote_id"]), approval_id=str(a["approval_id"]),
                                             delegation_id=a["delegation_id"],
                                             idempotency_key=h.get("idempotency-key") or "")
        return (202 if op.state in ("submitting", "outcome_unknown") else 200), operation_wire(op)

    def _operation_get(self, p, a, h):
        self._need(a, "operation_id")
        return 200, operation_wire(self.svc.get_operation(p, str(a["operation_id"])))

    def _order_get(self, p, a, h):
        self._need(a, "order_id")
        return 200, order_wire(self.svc.get_order(p, str(a["order_id"])))

    def _order_return(self, p, a, h):
        self._need(a, "order_id", "source_variant_ref", "quantity")
        return 202, self.svc.request_return(p, str(a["order_id"]), str(a["source_variant_ref"]), int(a["quantity"]),
                                            idempotency_key=h.get("idempotency-key"))

    def _order_cancel(self, p, a, h):
        self._need(a, "order_id")
        return 202, self.svc.request_cancellation(p, str(a["order_id"]), idempotency_key=h.get("idempotency-key"))

    # -- delegations ----------------------------------------------------------
    def _delegation_list(self, p, a, h):
        return 200, {"items": [delegation_wire(d) for d in self.svc.list_delegations(p)], "next_cursor": None}

    def _delegation_create(self, p, a, h):
        from datetime import datetime
        self._need(a, "client_id", "allowed_providers", "expires_at")
        try:
            mode = AssistanceMode(a.get("mode", "research"))
            expires_at = datetime.fromisoformat(str(a["expires_at"]).replace("Z", "+00:00"))
        except ValueError:
            raise InvalidRequest("invalid mode or expires_at") from None
        if expires_at.tzinfo is None:
            raise InvalidRequest("expires_at must carry a UTC offset")
        limits = None
        if a.get("limits") is not None:
            l = a["limits"]
            try:
                cur = l["currency"]
                limits = DelegationLimits(
                    currency=cur, max_per_order=Money.from_wire(l["max_per_order"]),
                    max_cumulative=Money.from_wire(l["max_cumulative"]), window_seconds=int(l["window_seconds"]),
                    allowed_merchants=frozenset(l["allowed_merchants"]),
                    allowed_categories=frozenset(l.get("allowed_categories", [])),
                    delivery_ref=l.get("delivery_ref"), payment_instrument_ref=l.get("payment_instrument_ref"),
                    require_returnable=bool(l.get("require_returnable", True)),
                    refund_credit_back=bool(l.get("refund_credit_back", False)),
                    require_final_human_approval=bool(l.get("require_final_human_approval", True)),
                    allow_substitution=bool(l.get("allow_substitution", False)))
            except (KeyError, TypeError, ValueError):  # MoneyError is a ValueError; DelegationInvalid propagates
                raise InvalidRequest("invalid delegation limits") from None
        d = self.svc.create_delegation(p, client_id=str(a["client_id"]), mode=mode,
                                       allowed_providers=[str(x) for x in a["allowed_providers"]],
                                       limits=limits, expires_at=expires_at)
        return 201, delegation_wire(d)

    def _delegation_revoke(self, p, a, h):
        self._need(a, "delegation_id")
        return 200, delegation_wire(self.svc.revoke_delegation(p, str(a["delegation_id"])))

    # -- catalog / capabilities ---------------------------------------------------
    def _catalog_search(self, p, a, h):
        self._need(a, "q")
        self.svc._authorize(p, "commerce:research")
        limit = int(a.get("limit", 24))
        if not 1 <= limit <= 100:
            raise InvalidRequest("limit must be 1-100")
        return 200, search_catalog(self.svc.registry, self.svc.clock(), str(a["q"])[:200],
                                   provider_ids=[a["provider"]] if a.get("provider") else (), limit=limit)

    def _catalog_product(self, p, a, h):
        """``product_id`` is ``{provider_id}:{source_product_id}``; detail comes from the provider, as data."""
        self._need(a, "product_id")
        self.svc._authorize(p, "commerce:research")
        provider_id, _, source_product_id = str(a["product_id"]).partition(":")
        conn = self._connection(provider_id)
        if not source_product_id or not conn.can_execute("catalog.detail"):
            raise NotFound("product not found")
        variants = conn.adapter.detail(source_product_id)
        if not variants:
            raise NotFound("product not found")
        return 200, {"provider_id": provider_id, "source_product_id": source_product_id,
                     "simulation": conn.simulation, "disclosure": conn.disclosure,
                     "variants": [{"source_variant_ref": v.source_variant_id, "size_label": v.size_label,
                                   "title": untrusted_text(v.title, f"provider:{provider_id}"),
                                   "availability": v.availability,
                                   "observed_price": v.price.to_wire() if v.price else None,
                                   "price_is_quote": False} for v in variants]}

    def _capabilities(self, p, a, h):
        if p.environment != self.svc.environment:  # any authenticated principal may read the sanitized summary
            raise Forbidden("principal environment mismatch")
        items = []
        conns = self.svc.registry.all()
        for conn in conns:
            for cap in ("catalog.search", "price.quote", "checkout.submit", "checkout.handoff", "orders.webhook",
                        "returns.request"):
                items.append({"name": f"{conn.provider_id}/{cap}"[:80], "state": _summary_state(conn, cap),
                              "reason_code": conn.capability(cap).reason_code,
                              "simulation_label": conn.disclosure if conn.simulation else None})
        # Aggregate entry the member UI shows next to identity/persistence (see gateway me.ts).
        submit = [c for c in conns if c.can_execute("checkout.submit")]
        if any(not c.simulation for c in submit):
            agg = ("available", "provider_checkout_verified", None)
        elif submit:
            agg = ("simulated", "simulated_provider_only", submit[0].disclosure)
        elif any(c.can_execute("checkout.handoff") for c in conns):
            agg = ("unconfigured", "handoff_only", None)
        else:
            agg = ("unconfigured", "no_checkout_provider", None)
        items.insert(0, {"name": "commerce.checkout", "state": agg[0], "reason_code": agg[1],
                         "simulation_label": agg[2]})
        return 200, {"items": items, "next_cursor": None}

    # -- operator console (provider:admin) -------------------------------------------
    def _provider_list(self, p, a, h):
        self._require_admin(p)
        return 200, {"items": [dict(c.to_public(), access_level=c.access_level, simulation=c.simulation)
                               for c in self.svc.registry.all()], "next_cursor": None}

    def _provider_get(self, p, a, h):
        self._require_admin(p)
        c = self._connection(str(a.get("provider_id", "")))
        return 200, dict(c.to_public(), access_level=c.access_level, simulation=c.simulation,
                         protocols=dict(c.protocols), allowed_redirect_hosts=list(c.allowed_redirect_hosts),
                         credential_configured=c.credential_ref is not None, version=str(c.version))

    def _provider_health(self, p, a, h):
        self._require_admin(p)
        c = self._connection(str(a.get("provider_id", "")))
        caps = [c.capabilities[k] for k in sorted(c.capabilities)]
        return 200, {"provider_id": c.provider_id, "environment": c.environment,
                     "capabilities": [dict(s.to_public(), evidence_kind=s.evidence_kind) for s in caps],
                     "executable": sorted(s.name for s in caps if c.can_execute(s.name)),
                     "simulation": c.simulation}

    def _provider_setup_get(self, p, a, h):
        self._require_admin(p)
        return 200, self.setup.get_setup(p, str(a.get("provider_id", "")))

    def _provider_setup_update(self, p, a, h):
        """Partial save, or ``{"activate": capability}`` alone. Saving never changes a capability state."""
        self._require_admin(p)
        if_match = self._if_match(h) if h.get("if-match") else None  # optional lost-update guard
        fields = {k: v for k, v in a.items() if k != "provider_id"}
        return 200, self.setup.update_setup(p, str(a.get("provider_id", "")), fields, if_match=if_match)

    def _provider_verify(self, p, a, h):
        self._require_admin(p)
        self._need(a, "capability", "mode")
        return 201, self.setup.run_verification(p, str(a.get("provider_id", "")), a["capability"], a["mode"])

    def _provider_runs(self, p, a, h):
        self._require_admin(p)
        try:
            limit = int(a.get("limit", 20))
        except (TypeError, ValueError):
            raise InvalidRequest("limit must be an integer") from None
        capability = a.get("capability")
        return 200, self.setup.list_runs(p, str(a.get("provider_id", "")),
                                         capability=str(capability) if capability else None, limit=limit)

    # -- assistant -------------------------------------------------------------------
    def _assistant_principal(self, p: Principal) -> Principal:
        """A member session drives Brand.Me's assistant only through their grant to ASSISTANT_CLIENT_ID."""
        if self.runtime is None:
            raise InvalidRequest("assistant runtime not configured", code="assistant_unavailable")
        if not is_first_party(p):
            return self.svc.bind(p)  # an agent acts only under its own active grant
        d = self.svc._active_delegation(self.svc.store, p.member_id, ASSISTANT_CLIENT_ID, self.svc.clock())
        if d is None:
            raise Forbidden("grant the Brand.Me assistant first", code="delegation_required")
        return replace(p, session_id=None, client_id=ASSISTANT_CLIENT_ID, scopes=frozenset(d.scopes),
                       delegation_id=d.id)

    @staticmethod
    def _budget_hint(raw: Any) -> Optional[Money]:
        """``budget_hint`` is the member's all-in price ceiling: same currency, no FX (None: no ceiling)."""
        if raw is None:
            return None
        try:
            return Money.from_wire(raw)
        except MoneyError:
            raise InvalidRequest("budget_hint must be {amount_minor, currency}", code="invalid_budget_hint") from None

    def _task_create(self, p, a, h):
        """Every create answers 202 (the task runs inline or in the background); a retried create
        of the same task answers 200 and never runs or submits it twice."""
        self._need(a, "goal")
        agent = self._assistant_principal(p)
        key = h.get("idempotency-key")
        rid = _uuid_or_none(h.get("x-request-id"))
        ceiling = self._budget_hint(a.get("budget_hint"))
        planner = self.planner_factory() if self.planner_factory is not None else None
        label = getattr(planner, "label", "custom") if planner is not None else "deterministic"
        background = planner is not None and bool(getattr(planner, "runs_in_background", False))
        if background and self.task_runner is None:
            raise InvalidRequest("this planner needs a background task runner", code="assistant_unavailable")
        if background and not self.task_runner.has_capacity():
            raise AssistantBusy("the assistant is busy; retry shortly")  # no task is created
        try:
            mode = AssistanceMode(a.get("assistance_mode", "research"))
            task = self.runtime.create(agent, str(a["goal"]), mode, idempotency_key=key,
                                       constraints=TaskConstraints(price_ceiling=ceiling), request_id=rid,
                                       planner_label=label)
        except IdempotencyReuse as exc:
            raise IdempotencyConflict(str(exc)) from None
        except (ValueError, PermissionError) as exc:
            raise Forbidden(str(exc) or "task refused", code="task_refused") from None
        body = {"id": task.id, "state": task.state, "mode": task.mode.value, "planner": task.planner_label}
        if task.state != "queued" or not self.runtime.mark_submitted(task.id):
            return 200, body  # a retried create: the task already ran, is running or is queued
        if planner is None:
            return 202, body
        if background:
            try:
                self.task_runner.submit(agent, task.id, planner)
            except AssistantBusy:
                self.runtime.fail(task.id, "assistant_busy")
                raise
            return 202, dict(body, state="queued")
        task = self.runtime.run(agent, task.id, planner)
        return 202, dict(body, state=task.state)

    def _task_reader(self, p: Principal) -> Principal:
        """Members read and cancel their own tasks; the runtime checks an agent against its grant."""
        if self.runtime is None:
            raise InvalidRequest("assistant runtime not configured", code="assistant_unavailable")
        if p.environment != self.svc.environment:
            raise Forbidden("principal environment mismatch")
        return p

    def _task_cancel(self, p, a, h):
        self._need(a, "task_id")
        try:
            task = self.runtime.cancel(self._task_reader(p), str(a["task_id"]))
        except KeyError:
            raise NotFound("task not found") from None
        return 200, {"id": task.id, "state": task.state, "cancel_requested": True}

    def _task_events(self, p, a, h):
        self._need(a, "task_id")
        after = a.get("after")
        try:
            events = self.runtime.events_after(self._task_reader(p), str(a["task_id"]),
                                               int(after) if after not in (None, "") else None)
        except KeyError:
            raise NotFound("task not found") from None
        return 200, {"events": [{"seq": e.seq, "type": e.type, "data": e.data} for e in events]}


def create_commerce_app(api: CommerceHttpApi) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.post(PREFIX + "/webhooks/{provider_id}")
    async def webhook(provider_id: str, request: Request) -> Response:
        body = await request.body()
        try:
            status, payload = await run_in_threadpool(api.receive_webhook, provider_id,
                                                      request.headers.get("authorization"), body)
        except AuthError as e:
            return _problem(e.status, e.error, e.description, {"WWW-Authenticate": e.www_authenticate()})
        except DomainError as e:
            return _problem(e.status, e.code, e.detail)
        except (ProviderError, ValueError):
            # Signature, replay-window or envelope failure: say nothing about why.
            return _problem(400, "webhook_rejected", "webhook not accepted")
        return JSONResponse(payload, status_code=status)

    @app.post(PREFIX + "/{operation}")
    async def invoke(operation: str, request: Request) -> Response:
        body = await request.body()
        headers = {k.lower(): v for k, v in request.headers.items()}
        try:
            status, payload, extra = await run_in_threadpool(api.dispatch, operation,
                                                             request.headers.get("authorization"), body, headers)
        except AuthError as e:
            return _problem(e.status, e.error, e.description, {"WWW-Authenticate": e.www_authenticate()})
        except DomainError as e:
            return _problem(e.status, e.code, e.detail)
        except ProviderError as e:
            return _problem(503, f"provider_{e.kind.value}", "provider unavailable for this operation")
        if status >= 400:
            return JSONResponse(payload, status_code=status, media_type="application/problem+json")
        return JSONResponse(payload, status_code=status, headers={"Cache-Control": "private, no-store", **extra})

    return app
