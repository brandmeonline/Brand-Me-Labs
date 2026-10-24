"""Brand.Me MCP tools and the principal-bound tool executor (ch.05 §4 "MCP surface").

Replaces the v9 manifest whose handlers returned fabricated results (random
"mandate" UUIDs, ``status: completed`` checkouts, ``esg_verified: True``,
"Sample Garment" cubes). Those names are retired: they are no longer listed and
return a documented ``tool_retired`` problem with the replacement, if any.

Identity is never taken from tool arguments. The executor receives a verified
``Principal`` (see ``authz.ExecutorAssertionVerifier``) and every argument
object is closed (``additionalProperties: false``).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import jsonschema

from brandme_core.domains.commerce.errors import CommerceError
from brandme_core.domains.commerce.principal import Principal
from brandme_core.domains.commerce.service import CommerceService, correlation
from brandme_core.domains.providers.contracts import CartLineRequest, ProviderError
from brandme_core.domains.providers.catalog import UNTRUSTED_TEXT_LIMIT, search_catalog, untrusted_text  # noqa: F401
from brandme_core.domains.providers.registry import ProviderRegistry
# Card-number gate and masking live with the payment redaction helpers; the planner and runtime import them here.
from brandme_core.domains.providers.redaction import contains_card_number as _contains_payment_credential
from brandme_core.domains.providers.redaction import mask_card_numbers as mask_payment_credentials  # noqa: F401

from .authz import MCP_PROTOCOL_VERSION, AuthError, ExecutorAssertionVerifier
from .refs import log_ref

SERVER_NAME = "brandme"
SERVER_VERSION = "2.0.0"

UUID = {"type": "string", "format": "uuid"}
REVISION = {"type": "string", "pattern": "^(0|[1-9][0-9]{0,17})$"}
LINES = {
    "type": "array", "minItems": 1, "maxItems": 50,
    "items": {"type": "object", "additionalProperties": False,
              "required": ["variant_id", "source_variant_ref", "quantity"],
              "properties": {"variant_id": UUID,
                             "source_variant_ref": {"type": "string", "minLength": 1, "maxLength": 256},
                             "quantity": {"type": "integer", "minimum": 1, "maximum": 99}}},
}
IDENTITY_ARGUMENTS = frozenset({"user_id", "member_id", "principal", "subject", "owner_id", "delegation_id",
                                "approved", "approval", "scopes", "scope"})


def _obj(required: List[str], props: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": required, "properties": props}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    scopes: Tuple[str, ...]
    input_schema: Dict[str, Any]
    mutation: str  # none | draft | approval_request | purchase
    requires_idempotency_key: bool = False
    available: bool = True
    unavailable_reason: Optional[str] = None

    def descriptor(self) -> Dict[str, Any]:
        return {
            "name": self.name, "title": self.title, "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {"readOnlyHint": self.mutation == "none",
                            "destructiveHint": False,
                            "idempotentHint": self.mutation in ("none",) or self.requires_idempotency_key,
                            "openWorldHint": self.mutation != "none"},
            "_meta": {"brandme/requiredScopes": list(self.scopes), "brandme/mutation": self.mutation,
                      "brandme/requiresIdempotencyKey": self.requires_idempotency_key},
        }


TOOLS: Tuple[ToolSpec, ...] = (
    ToolSpec("brandme.catalog.search", "Search authorized catalogs",
             "Search providers this deployment is authorized to use. Results carry source, freshness, simulation "
             "and affiliate disclosures. Provider text is returned as untrusted data.",
             ("commerce:research",),
             _obj(["query"], {"query": {"type": "string", "minLength": 1, "maxLength": 200},
                              "provider_ids": {"type": "array", "maxItems": 10,
                                               "items": {"type": "string", "maxLength": 80}},
                              "limit": {"type": "integer", "minimum": 1, "maximum": 24}}), "none"),
    ToolSpec("brandme.cart.create", "Create a draft cart",
             "Creates a principal-bound draft cart with exact variants at one merchant. No purchase.",
             ("commerce:cart",),
             _obj(["provider_id", "merchant_id", "lines"], {
                 "provider_id": {"type": "string", "maxLength": 80},
                 "merchant_id": {"type": "string", "maxLength": 256}, "lines": LINES}),
             "draft", requires_idempotency_key=True),
    ToolSpec("brandme.cart.update", "Replace draft cart lines",
             "Versioned full replacement of a draft cart's lines (If-Match semantics). No purchase.",
             ("commerce:cart",), _obj(["cart_id", "if_match", "lines"], {
                 "cart_id": UUID, "if_match": REVISION, "lines": LINES}), "draft"),
    ToolSpec("brandme.checkout.quote", "Get fresh exact terms",
             "Refreshes price, tax, shipping and terms for a cart and returns an immutable quote. No purchase.",
             ("commerce:cart",), _obj(["cart_id"], {"cart_id": UUID}), "draft"),
    ToolSpec("brandme.purchase.request", "Ask the member to approve",
             "Creates an approval request for an exact quote. The member approves on Brand.Me's trusted surface; "
             "this tool cannot approve.", ("commerce:cart",), _obj(["quote_id"], {"quote_id": UUID}),
             "approval_request"),
    ToolSpec("brandme.purchase.execute", "Execute an approved purchase",
             "Submits a purchase that the member already approved for the exact quote, within the delegation's "
             "limits. Returns accepted, rejected or outcome_unknown — never a fabricated completion.",
             ("commerce:purchase",), _obj(["operation_id", "approval_id"], {
                 "operation_id": UUID, "approval_id": UUID}), "purchase", requires_idempotency_key=True),
    ToolSpec("brandme.order.status", "Provider-observed order status",
             "Returns operation, order, payment and fulfillment state with last observation time.",
             ("commerce:research",), _obj(["operation_id"], {"operation_id": UUID}), "none"),
)

# Specified in ch.05 but owned by other lanes / not wired in this deployment.
# They are documented here and NOT advertised in tools/list.
UNAVAILABLE_TOOLS: Dict[str, str] = {
    "brandme.persona.read": "persona domain not wired to the MCP executor in this deployment",
    "brandme.persona.propose_update": "persona domain not wired to the MCP executor in this deployment",
    "brandme.wardrobe.search": "wardrobe domain not wired to the MCP executor in this deployment",
    "brandme.outfits.suggest": "outfit domain not wired to the MCP executor in this deployment",
    "brandme.social.request_decision": "requires separate communication authority; not wired",
    "brandme.rights.transfer_request": "Midnight rights workflow not wired",
    "brandme.reprint.quote": "reprint workflow not wired",
    "brandme.reprint.request": "reprint workflow not wired",
}

# Old names → replacement (None = no successor). Fake implementations retired.
RETIRED_TOOLS: Dict[str, Optional[str]] = {
    "ap2.create_intent_mandate": None,
    "ap2.mandate.create_intent": None,
    "ap2.mandate.confirm_cart": "brandme.purchase.request",
    "ap2.mandate.issue_payment": None,
    "acp.cart.create": "brandme.cart.create",
    "acp.cart.update": "brandme.cart.update",
    "acp.checkout.complete": "brandme.purchase.execute",
    "search_wardrobe": "brandme.wardrobe.search",
    "get_cube_details": None,
    "suggest_outfit": "brandme.outfits.suggest",
    "initiate_rental": None,
    "list_for_resale": None,
    "request_repair": None,
    "request_dissolve": None,
}
RETIRED_REASON = {
    "ap2.create_intent_mandate": "Internal shopping intents are not AP2 credentials. AP2 v0.2 defines Checkout and "
                                 "Payment mandates only; see brandme_core.domains.commerce.ap2.",
    "ap2.mandate.create_intent": "Internal shopping intents are not AP2 credentials. AP2 v0.2 defines Checkout and "
                                 "Payment mandates only; see brandme_core.domains.commerce.ap2.",
    "ap2.mandate.issue_payment": "Payment mandates are produced only by a member-controlled trusted surface.",
}

_SPECS = {t.name: t for t in TOOLS}


@dataclass(frozen=True)
class ToolOutcome:
    request_id: str
    tool: str
    status: str  # ok | error
    structured_content: Optional[Dict[str, Any]] = None
    problem: Optional[Dict[str, Any]] = None

    def to_wire(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"request_id": self.request_id, "tool": self.tool, "status": self.status}
        if self.structured_content is not None:
            out["structured_content"] = self.structured_content
        if self.problem is not None:
            out["problem"] = self.problem
        return out


def _problem(status: int, code: str, detail: str, **extra: Any) -> Dict[str, Any]:
    p = {"type": f"https://brand.me/problems/{code}", "title": code.replace("_", " "), "status": status,
         "code": code, "detail": detail, "retryable": status in (429, 503)}
    p.update(extra)
    return p


AuditSink = Callable[[Dict[str, Any]], None]

# Audit references are keyed (``refs.log_ref``): they correlate records, and a short argument
# (say, a two-word catalog query) cannot be recovered by hashing guesses. The assistant run log
# uses the same refs, so its lines join to these records.

# -- assistant runtime support ---------------------------------------------------
# Every name a proposal may carry into events and audit records; anything else becomes UNKNOWN_TOOL.
KNOWN_TOOL_NAMES = frozenset(_SPECS) | frozenset(RETIRED_TOOLS) | frozenset(UNAVAILABLE_TOOLS)
UNKNOWN_TOOL = "unknown_tool"
contains_payment_credential = _contains_payment_credential
# A label ("cvv", "CVC2", "c.v.v.", "security code", "card verification value", ...) followed within 20
# non-digit characters by exactly 3-4 digits: "cvv123", "CVV is 123", "my security code is 1234".
_CSC_RE = re.compile(
    r"(?i)\b(?:c\.?v\.?[vc]\.?2?|cvn2?|cav2|csc|cid|security\s*(?:code|number)s?"
    r"|card\s*verification(?:\s*(?:value|code|number))?)(?![a-z])\D{0,20}?(?<!\d)\d{3,4}(?!\d)")


def contains_card_security_code(value: Any) -> bool:
    """A card security code near its label ("cvv 123", "cvv123", "my security code is 1234"); the
    number alone is not detectable."""
    if isinstance(value, str):
        return bool(_CSC_RE.search(value))
    if isinstance(value, Mapping):
        return any(contains_card_security_code(k) or contains_card_security_code(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_card_security_code(v) for v in value)
    return False


def mask_card_security_codes(text: str) -> str:
    """``text`` with each labelled security code (label and digits) replaced."""
    return _CSC_RE.sub("[card security code removed]", text)


class McpToolExecutor:
    def __init__(self, *, commerce: CommerceService, registry: ProviderRegistry,
                 verifier: ExecutorAssertionVerifier, audit: Optional[AuditSink] = None):
        self.commerce = commerce
        self.registry = registry
        self.verifier = verifier
        self.audit = audit or (lambda record: None)
        self._invocation_schema = json.loads(_INVOCATION_SCHEMA)
        self._handlers: Dict[str, Callable[[Principal, Dict[str, Any], Optional[str]], Dict[str, Any]]] = {
            "brandme.catalog.search": self._catalog_search,
            "brandme.cart.create": self._cart_create,
            "brandme.cart.update": self._cart_update,
            "brandme.checkout.quote": self._checkout_quote,
            "brandme.purchase.request": self._purchase_request,
            "brandme.purchase.execute": self._purchase_execute,
            "brandme.order.status": self._order_status,
        }

    # -- discovery -----------------------------------------------------------
    @staticmethod
    def list_tools() -> Dict[str, Any]:
        """``tools/list`` result: only tools that actually work in this deployment."""
        return {"tools": [t.descriptor() for t in TOOLS if t.available]}

    @staticmethod
    def server_discover() -> Dict[str, Any]:
        return {"supportedVersions": [MCP_PROTOCOL_VERSION],
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "capabilities": {"tools": {"listChanged": False}}}

    # -- invocation ----------------------------------------------------------
    def invoke(self, assertion: str, invocation: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Returns (http_status, body). Authorization failures carry ``www_authenticate``."""
        try:
            principal = self.verifier.verify(assertion)
        except AuthError as e:
            return e.status, {"problem": _problem(e.status, e.error, e.description),
                              "www_authenticate": e.www_authenticate()}
        request_id = invocation.get("request_id") if isinstance(invocation, dict) else None
        status, outcome = self.call(principal, invocation, correlation_id=request_id, origin="mcp")
        return status, outcome.to_wire()

    def call(self, principal: Principal, invocation: Dict[str, Any], *, correlation_id: Optional[str] = None,
             task_id: Optional[str] = None, origin: str = "mcp", step: Optional[int] = None) -> Tuple[int, ToolOutcome]:
        """The one audited path into the tools, for external MCP clients and the assistant runtime alike.

        Validates the invocation envelope, dispatches under the verified principal, and writes one
        audit record: codes, timings and keyed references only, never arguments or raw identifiers.
        Commerce events emitted by the call carry ``correlation_id``. ``step`` is the assistant
        planning step that proposed the call. A handler that raises anything else (a store deadline
        after commit, a bug) still gets its record, ``status: error`` with the fixed code
        ``internal_error`` and never the exception text, and the exception propagates.
        """
        started = time.monotonic()
        request_id = str(invocation.get("request_id", "")) if isinstance(invocation, dict) else ""
        tool = str(invocation.get("tool", "")) if isinstance(invocation, dict) else ""

        def audit(status: str, code: Optional[str]) -> None:
            self._audit(principal, request_id=request_id, origin=origin, tool=tool, task_id=task_id, step=step,
                        status=status, code=code, duration_ms=int((time.monotonic() - started) * 1000),
                        arguments=invocation.get("arguments") if isinstance(invocation, dict) else None)

        try:
            jsonschema.Draft202012Validator(self._invocation_schema,
                                            format_checker=jsonschema.FormatChecker()).validate(invocation)
        except jsonschema.ValidationError as e:
            status, outcome = 400, ToolOutcome(request_id, tool, "error",
                                               problem=_problem(400, "malformed_invocation", e.message[:300]))
        else:
            try:
                with correlation(correlation_id):
                    status, outcome = self._dispatch(principal, invocation)
            except BaseException:
                audit("error", "internal_error")  # the call may have had side effects: it is still on record
                raise
        audit(outcome.status, (outcome.problem or {}).get("code"))
        return status, outcome

    def audit_refusal(self, principal: Principal, *, tool: str, arguments: Any, code: str, task_id: str,
                      step: int, origin: str = "assistant") -> None:
        """The audit record for a proposal the assistant runtime refused before dispatch (same shape
        as ``call``'s, ``status: refused``): every proposal leaves exactly one record."""
        self._audit(principal, request_id=None, origin=origin, tool=tool, task_id=task_id, step=step,
                    status="refused", code=code, duration_ms=0, arguments=arguments)

    def _audit(self, principal: Principal, *, request_id: Optional[str], origin: str, tool: str,
               task_id: Optional[str], step: Optional[int], status: str, code: Optional[str], duration_ms: int,
               arguments: Any) -> None:
        try:
            principal = self.commerce.bind(principal)  # audit the resolved delegation
        except Exception:  # unbound or store unavailable: the record is still written, as presented
            pass
        self.audit({
            "request_id": request_id, "origin": origin, "tool": tool, "client_id": principal.client_id,
            "member_ref": log_ref("member", principal.member_id), "delegation_id": principal.delegation_id,
            "task_ref": log_ref("task", task_id) if task_id else None, "step": step, "status": status,
            "code": code, "duration_ms": duration_ms,
            # Arguments are never logged; only a keyed digest for correlation.
            "arguments_digest": log_ref("args", arguments),
        })

    def _dispatch(self, principal: Principal, inv: Dict[str, Any]) -> Tuple[int, ToolOutcome]:
        rid, tool, args = inv["request_id"], inv["tool"], inv["arguments"]
        if inv["protocol_version"] != MCP_PROTOCOL_VERSION:
            return 400, ToolOutcome(rid, tool, "error", problem=_problem(
                400, "unsupported_protocol_version", "unsupported MCP protocol version",
                supported=[MCP_PROTOCOL_VERSION]))
        if inv["environment"] != principal.environment:
            return 403, ToolOutcome(rid, tool, "error", problem=_problem(403, "environment_mismatch",
                                                                         "invocation environment mismatch"))
        if tool in RETIRED_TOOLS:
            return 410, ToolOutcome(rid, tool, "error", problem=_problem(
                410, "tool_retired", RETIRED_REASON.get(tool, "This tool returned simulated results and was retired."),
                replacement=RETIRED_TOOLS[tool]))
        if tool in UNAVAILABLE_TOOLS:
            return 501, ToolOutcome(rid, tool, "error", problem=_problem(501, "tool_unavailable", UNAVAILABLE_TOOLS[tool]))
        spec = _SPECS.get(tool)
        if spec is None:
            return 404, ToolOutcome(rid, tool, "error", problem=_problem(404, "unknown_tool", "unknown tool"))
        if isinstance(args, dict) and IDENTITY_ARGUMENTS & set(args):
            return 400, ToolOutcome(rid, tool, "error", problem=_problem(
                400, "identity_argument_rejected",
                "identity, scope and approval come from authentication, not tool arguments"))
        if _contains_payment_credential(args):
            return 400, ToolOutcome(rid, tool, "error", problem=_problem(
                400, "payment_credential_rejected", "payment card data is never accepted by Brand.Me tools"))
        if contains_card_security_code(args):  # a security code is card data too (BM-COM-018)
            return 400, ToolOutcome(rid, tool, "error", problem=_problem(
                400, "payment_credential_rejected", "payment card data is never accepted by Brand.Me tools"))
        try:
            jsonschema.Draft202012Validator(spec.input_schema, format_checker=jsonschema.FormatChecker()).validate(args)
        except jsonschema.ValidationError as e:
            return 400, ToolOutcome(rid, tool, "error", problem=_problem(400, "invalid_arguments", e.message[:300]))
        try:
            principal = self.commerce.bind(principal)  # resolve the caller's one active delegation
        except CommerceError as e:
            return e.status, ToolOutcome(rid, tool, "error", problem=_problem(e.status, e.code, e.detail))
        delegation = self.commerce.store.get("delegations", principal.delegation_id or "")
        if delegation is None:  # first-party sessions use the trusted UI, never this hop
            return 403, ToolOutcome(rid, tool, "error", problem=_problem(
                403, "delegation_required", "MCP tools run only under a member-granted delegation"))
        missing = sorted(set(spec.scopes) - (principal.scopes & delegation.scopes))
        if missing:
            err = AuthError(403, "insufficient_scope", "additional scope required", scope=" ".join(spec.scopes))
            return 403, ToolOutcome(rid, tool, "error", problem=_problem(
                403, "insufficient_scope", "additional scope required", required_scopes=list(spec.scopes),
                www_authenticate=err.www_authenticate()))
        key = inv.get("idempotency_key")
        if spec.requires_idempotency_key and not key:
            return 400, ToolOutcome(rid, tool, "error", problem=_problem(400, "idempotency_key_required",
                                                                         "this tool requires an idempotency key"))
        try:
            content = self._handlers[tool](principal, args, key)
        except CommerceError as e:
            return e.status, ToolOutcome(rid, tool, "error", problem=_problem(e.status, e.code, e.detail))
        except ProviderError as e:
            return 503, ToolOutcome(rid, tool, "error", problem=_problem(503, f"provider_{e.kind.value}",
                                                                         "provider unavailable for this operation"))
        return 200, ToolOutcome(rid, tool, "ok", structured_content=content)

    # -- handlers --------------------------------------------------------------
    def _catalog_search(self, p: Principal, a: Dict[str, Any], _key: Optional[str]) -> Dict[str, Any]:
        out = search_catalog(self.registry, self.commerce.clock(), a["query"],
                             provider_ids=a.get("provider_ids") or (), limit=a.get("limit", 12))
        out["note"] = "Prices are observations; call brandme.checkout.quote for purchasable terms."
        return out

    def _cart_create(self, p: Principal, a: Dict[str, Any], key: Optional[str]) -> Dict[str, Any]:
        cart = self.commerce.create_cart(p, provider_id=a["provider_id"], merchant_id=a["merchant_id"],
                                         lines=[CartLineRequest(**l) for l in a["lines"]], idempotency_key=key)
        return {"cart_id": cart.id, "revision": str(cart.revision), "status": cart.status}

    def _cart_update(self, p: Principal, a: Dict[str, Any], _key: Optional[str]) -> Dict[str, Any]:
        cart = self.commerce.update_cart(p, a["cart_id"], if_match=int(a["if_match"]),
                                         lines=[CartLineRequest(**l) for l in a["lines"]])
        return {"cart_id": cart.id, "revision": str(cart.revision), "status": cart.status}

    def _checkout_quote(self, p: Principal, a: Dict[str, Any], _key: Optional[str]) -> Dict[str, Any]:
        q = self.commerce.quote_cart(p, a["cart_id"])
        return {"quote": q.to_wire(), "display_total": q.total.display(),
                "purchase": "not_started", "simulation": self.registry.get(q.provider_id).simulation}

    def _purchase_request(self, p: Principal, a: Dict[str, Any], _key: Optional[str]) -> Dict[str, Any]:
        op = self.commerce.request_purchase(p, a["quote_id"])
        return {"operation_id": op.id, "state": op.state,
                "next": "The member reviews and approves on Brand.Me's trusted approval screen.",
                "approval_surface": f"/approvals/{op.id}"}

    def _purchase_execute(self, p: Principal, a: Dict[str, Any], key: Optional[str]) -> Dict[str, Any]:
        op = self.commerce.execute_purchase(p, operation_id=a["operation_id"], approval_id=a["approval_id"],
                                            idempotency_key=key or "")
        return self._op_status(p, op)

    def _order_status(self, p: Principal, a: Dict[str, Any], _key: Optional[str]) -> Dict[str, Any]:
        return self._op_status(p, self.commerce.get_operation(p, a["operation_id"]))

    def _op_status(self, p: Principal, op) -> Dict[str, Any]:
        out: Dict[str, Any] = {"operation_id": op.id, "state": op.state, "reason_code": op.reason_code}
        if op.state == "outcome_unknown":
            out["message"] = "We are checking whether the retailer accepted this order."
        if op.order_id:
            o = self.commerce.get_order(p, op.order_id)
            out["order"] = {"order_id": o.id, "order_status": o.order_status, "payment_status": o.payment_status,
                            "fulfillment_status": o.fulfillment_status,
                            "last_observed_at": o.last_observed_at.strftime("%Y-%m-%dT%H:%M:%SZ")}
        return out




def _load_invocation_schema() -> str:
    from pathlib import Path
    return (Path(__file__).with_name("schemas") / "tool_invocation.schema.json").read_text()


_INVOCATION_SCHEMA = _load_invocation_schema()
