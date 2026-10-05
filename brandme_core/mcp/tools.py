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

import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Tuple

import jsonschema

from brandme_core.domains.commerce.errors import CommerceError
from brandme_core.domains.commerce.principal import Principal
from brandme_core.domains.commerce.service import CommerceService
from brandme_core.domains.providers.contracts import CartLineRequest, ProviderError
from brandme_core.domains.providers.ingestion import price_freshness
from brandme_core.domains.providers.registry import ProviderRegistry

from .authz import MCP_PROTOCOL_VERSION, AuthError, ExecutorAssertionVerifier

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
UNTRUSTED_TEXT_LIMIT = 2000


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
_PAN_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


def _contains_payment_credential(value: Any) -> bool:
    if isinstance(value, str):
        # Identifiers are not card data: remove UUIDs so their digit runs cannot
        # chain across hyphens into a Luhn-valid 13-19 digit sequence.
        value = _UUID_RE.sub(" ", value)
        for m in _PAN_RE.finditer(value):
            d = re.sub(r"\D", "", m.group())
            if 13 <= len(d) <= 19 and _luhn(d):
                return True
        return False
    if isinstance(value, Mapping):
        return any(_contains_payment_credential(k) or _contains_payment_credential(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_payment_credential(v) for v in value)
    return False


def untrusted_text(text: str, origin: str) -> Dict[str, str]:
    """Provider/retrieved text is data: normalized, control chars stripped, length-capped, labeled."""
    clean = "".join(ch for ch in unicodedata.normalize("NFKC", text or "")
                    if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    return {"type": "untrusted_text", "origin": origin, "text": clean[:UNTRUSTED_TEXT_LIMIT]}


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
        started = time.monotonic()
        request_id = str(invocation.get("request_id", "")) if isinstance(invocation, dict) else ""
        try:
            principal = self.verifier.verify(assertion)
        except AuthError as e:
            return e.status, {"problem": _problem(e.status, e.error, e.description),
                              "www_authenticate": e.www_authenticate()}
        try:
            jsonschema.Draft202012Validator(self._invocation_schema,
                                            format_checker=jsonschema.FormatChecker()).validate(invocation)
        except jsonschema.ValidationError as e:
            return 400, ToolOutcome(request_id, str(invocation.get("tool", "")) if isinstance(invocation, dict) else "",
                                    "error", problem=_problem(400, "malformed_invocation", e.message[:300])).to_wire()
        tool = invocation["tool"]
        status, outcome = self._dispatch(principal, invocation)
        self.audit({
            "request_id": request_id, "tool": tool, "client_id": principal.client_id,
            "member_ref": hashlib.sha256(principal.member_id.encode()).hexdigest()[:16],
            "delegation_id": principal.delegation_id, "status": outcome.status,
            "code": (outcome.problem or {}).get("code"), "duration_ms": int((time.monotonic() - started) * 1000),
            # Arguments are never logged; only a digest for correlation.
            "arguments_digest": hashlib.sha256(json.dumps(invocation.get("arguments"), sort_keys=True,
                                                          default=str).encode()).hexdigest()[:16],
        })
        return status, outcome.to_wire()

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
        try:
            jsonschema.Draft202012Validator(spec.input_schema, format_checker=jsonschema.FormatChecker()).validate(args)
        except jsonschema.ValidationError as e:
            return 400, ToolOutcome(rid, tool, "error", problem=_problem(400, "invalid_arguments", e.message[:300]))
        missing = sorted(set(spec.scopes) - principal.scopes)
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
        self.commerce.require_active_delegation(p)
        wanted = set(a.get("provider_ids") or [])
        now = self.commerce.clock()
        items, unavailable = [], []
        for conn in self.registry.all():
            if wanted and conn.provider_id not in wanted:
                continue
            if not conn.can_execute("catalog.search"):
                unavailable.append({"provider_id": conn.provider_id,
                                    "reason_code": conn.capability("catalog.search").reason_code,
                                    "handoff": conn.capability("checkout.handoff").state})
                continue
            page = conn.adapter.search(a["query"], limit=a.get("limit", 12))
            for v in page.items:
                fresh = price_freshness(v, now)
                items.append({
                    "provider_id": v.provider_id, "merchant_id": v.merchant_id,
                    "source_product_id": v.source_product_id, "source_variant_ref": v.source_variant_id,
                    "variant_id": _variant_id(conn, v.source_variant_id),
                    "title": untrusted_text(v.title, f"provider:{v.provider_id}"),
                    "description": untrusted_text(v.description, f"provider:{v.provider_id}"),
                    "category": v.category, "size_label": v.size_label, "availability": v.availability,
                    "observed_price": v.price.to_wire() if v.price else None,
                    "price_is_quote": False, "price_freshness": fresh.state,
                    "checked_at": fresh.checked_at.strftime("%Y-%m-%dT%H:%M:%SZ") if fresh.checked_at else None,
                    "simulation": conn.simulation, "disclosure": conn.disclosure,
                })
        return {"items": items, "unavailable_providers": unavailable,
                "note": "Prices are observations; call brandme.checkout.quote for purchasable terms."}

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
        self.commerce.require_active_delegation(p)
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


def _variant_id(conn, source_variant_ref: str) -> Optional[str]:
    fn = getattr(conn.adapter, "variant_id_for", None)
    return fn(source_variant_ref) if fn is not None else None


def _load_invocation_schema() -> str:
    from pathlib import Path
    return (Path(__file__).with_name("schemas") / "tool_invocation.schema.json").read_text()


_INVOCATION_SCHEMA = _load_invocation_schema()
