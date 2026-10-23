"""Anthropic Messages API adapter for the model planner (dev form; ``anthropic==0.125.0``).

The SDK is imported inside ``AnthropicAdapter.__init__`` only, so no-key paths never load it.

Egress is pinned (the base URL is also the allowlist):

* only ``https://api.anthropic.com:443`` is reachable; a request hook refuses anything else, on
  every request and every redirect hop, and redirects are not followed;
* SDK retries are 0, so one planning step is exactly one request;
* no ambient proxy, ``.netrc`` or CA settings: the transport is built with ``trust_env=False``
  and only the explicit ``egress_proxy`` / ``ca_bundle`` arguments (``BRANDME_ASSISTANT_*``) apply;
* headers are allowlisted, which drops anything ``ANTHROPIC_CUSTOM_HEADERS`` merges in, and the
  key and API version are set to this adapter's own values;
* the ``anthropic``, ``httpx`` and ``httpcore`` loggers are held at WARNING, so ``ANTHROPIC_LOG``
  cannot log request options or URLs.

An explicit ``api_key`` and ``base_url`` stop the SDK reading ``ANTHROPIC_API_KEY``,
``ANTHROPIC_AUTH_TOKEN``, ``ANTHROPIC_BASE_URL`` and credential profiles.

Request shape for Claude Opus 5.5: thinking is always on (no ``thinking`` parameter), effort is
sent explicitly, ``tool_choice`` is ``auto`` with parallel tool use disabled (forced tool choice
is refused on this model), tools are strict, and no sampling parameters are sent. Text and
thinking blocks in a response are counted and discarded here.
"""

from __future__ import annotations

import json
import logging
import re
from typing import AbstractSet, Any, Mapping, Optional

from brandme_core.mcp.tools import KNOWN_TOOL_NAMES

from .model_adapter import (
    UNKNOWN_TOOL, Billing, EncodedRequest, ModelCallError, ModelPrice, ModelProfile, ModelUsage, PlanRequest,
    PlanResponse, PlannerConfigError, ProposedToolUse, StopKind, mcp_name,
)

ANTHROPIC_API = "https://api.anthropic.com"
ANTHROPIC_HOST = "api.anthropic.com"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-opus-5-5"
EFFORTS = ("low", "medium", "high")
DEFAULT_EFFORT = "medium"
MODEL_PROFILES = {
    # $4 / $20 per MTok; 5-minute cache write 1.25x input; cache read $0.20 (checked 2026-10-23).
    "claude-opus-5-5": ModelProfile("claude-opus-5-5",
                                    ModelPrice(input=4_000, output=20_000, cache_write=5_000, cache_read=200),
                                    input_overhead_tokens=2_048, max_output_tokens_cap=128_000),
}
_ALLOWED_HEADERS = frozenset({"host", "accept", "accept-encoding", "connection", "content-type", "content-length",
                              "user-agent", "x-api-key", "anthropic-version"})  # plus any x-stainless-*
_REFUSAL_CATEGORIES = frozenset({"cyber", "bio", "frontier_llm", "reasoning_extraction", "general_harms"})
_STOP_REASONS = frozenset({"end_turn", "max_tokens", "stop_sequence", "tool_use", "pause_turn", "refusal",
                           "model_context_window_exceeded"})
MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}$")
REQUEST_ID_RE = re.compile(r"^req_[A-Za-z0-9]{1,64}$")
MAX_ARGUMENT_CHARS = 16_384
_QUIET_LOGGERS = ("anthropic", "httpx", "httpcore")
# JSON Schema keywords strict tool use does not accept; the executor re-validates the full schema.
_UNSUPPORTED = frozenset({"minLength", "maxLength", "pattern", "minimum", "maximum", "exclusiveMinimum",
                          "exclusiveMaximum", "multipleOf", "minItems", "maxItems", "uniqueItems",
                          "minProperties", "maxProperties"})
_FORMATS = frozenset({"date-time", "time", "date", "duration", "email", "hostname", "uri", "ipv4", "ipv6", "uuid"})


class EgressRefused(Exception):
    """A request to anywhere but the Anthropic API. Never carries the URL."""


def require_dev_key(key: Optional[str]) -> str:
    """An Anthropic API key (``sk-ant-api…``); admin and other keys are refused. Never echoed."""
    if not isinstance(key, str) or not key.startswith("sk-ant-api") or len(key) < 40 or any(c.isspace() for c in key):
        raise PlannerConfigError("model_key_invalid")
    return key


def strict_schema(schema: Any) -> Any:
    """The tool schema as strict tool use accepts it (unsupported keywords removed)."""
    if isinstance(schema, dict):
        out = {}
        for k, v in schema.items():
            if k in _UNSUPPORTED or (k == "format" and v not in _FORMATS):
                continue
            out[k] = strict_schema(v)
        if out.get("type") == "object":
            out["additionalProperties"] = False
        return out
    if isinstance(schema, list):
        return [strict_schema(v) for v in schema]
    return schema


def _quiet_sdk_loggers() -> None:
    for name in list(logging.root.manager.loggerDict):
        if name.split(".")[0] in _QUIET_LOGGERS and logging.getLogger(name).level < logging.WARNING:
            logging.getLogger(name).setLevel(logging.WARNING)
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def _cause_chain(exc: BaseException):
    seen = 0
    while exc is not None and seen < 10:
        yield exc
        exc, seen = exc.__cause__ or exc.__context__, seen + 1


class AnthropicAdapter:
    provider = "anthropic"
    api_version = API_VERSION

    def __init__(self, *, api_key: str, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT,
                 transport: Optional[Any] = None, egress_proxy: Optional[str] = None,
                 ca_bundle: Optional[str] = None, known_tools: AbstractSet[str] = KNOWN_TOOL_NAMES):
        import anthropic  # optional dependency: loaded only when a model planner is configured
        import httpx

        if model not in MODEL_PROFILES:
            raise PlannerConfigError("model_not_supported")
        if effort not in EFFORTS:
            raise PlannerConfigError("model_effort_invalid")
        key = require_dev_key(api_key)
        self.model, self.effort, self.profile = model, effort, MODEL_PROFILES[model]
        self._known = frozenset(known_tools)
        self._anthropic = anthropic
        self._key = key
        if transport is None:  # tests pass a mock transport; never an http client
            transport = httpx.HTTPTransport(
                verify=ca_bundle or True, trust_env=False, retries=0,
                proxy=httpx.Proxy(egress_proxy) if egress_proxy else None,
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=2))
        # Passing a transport skips the SDK's own proxy mounting from HTTPS_PROXY.
        self._http = anthropic.DefaultHttpxClient(
            transport=transport, trust_env=False, follow_redirects=False,
            event_hooks={"request": [self._egress_guard]},
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2))
        self._client = anthropic.Anthropic(api_key=key, base_url=ANTHROPIC_API, max_retries=0, http_client=self._http)
        _quiet_sdk_loggers()
        self.sdk_version = anthropic.__version__

    # -- egress -----------------------------------------------------------------
    def _egress_guard(self, request: Any) -> None:
        url = request.url
        if url.scheme != "https" or url.host != ANTHROPIC_HOST or url.port not in (None, 443):
            raise EgressRefused()
        for name in list(request.headers.keys()):
            low = name.lower()
            if low not in _ALLOWED_HEADERS and not low.startswith("x-stainless-"):
                del request.headers[name]
        # Ambient custom headers may also carry these names; only this adapter's values go out.
        request.headers["x-api-key"] = self._key
        request.headers["anthropic-version"] = API_VERSION
        request.headers["host"] = ANTHROPIC_HOST

    # -- requests ---------------------------------------------------------------
    def encode(self, request: PlanRequest) -> EncodedRequest:
        body = {
            "model": self.model,
            "max_tokens": min(request.max_output_tokens, self.profile.max_output_tokens_cap),
            "system": [{"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}],
            "tools": [{"name": t.wire, "description": t.description[:1024],
                       "input_schema": strict_schema(dict(t.input_schema)), "strict": True} for t in request.tools],
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
            "output_config": {"effort": self.effort},
            "messages": [{"role": "user", "content": [{"type": "text", "text": request.task_block},
                                                      {"type": "text", "text": request.record_block}]}],
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return EncodedRequest(body=body, canonical=canonical, size_bytes=len(canonical.encode("utf-8")))

    def send(self, encoded: EncodedRequest, *, timeout_s: float) -> PlanResponse:
        a = self._anthropic
        try:
            resp = self._client.messages.create(**encoded.body,
                                                timeout=a.Timeout(timeout_s, connect=min(5.0, timeout_s)))
        except Exception as exc:  # map to a fixed code; provider text never leaves here
            code, billing = self._classify(exc)
            raise ModelCallError(code, billing) from None
        return self._parse(resp)

    def close(self) -> None:
        self._client.close()

    # -- responses --------------------------------------------------------------
    def _classify(self, exc: Exception):
        a = self._anthropic
        if isinstance(exc, a.APITimeoutError):  # a subclass of APIConnectionError: check it first
            return "model_timeout", Billing.UNKNOWN
        if isinstance(exc, a.APIConnectionError):
            if any(isinstance(e, EgressRefused) for e in _cause_chain(exc)):
                return "model_egress_refused", Billing.NONE
            return "model_unavailable", Billing.UNKNOWN
        if isinstance(exc, a.APIResponseValidationError):
            return "model_response_invalid", Billing.UNKNOWN
        if isinstance(exc, a.APIStatusError):
            s = exc.status_code
            if 300 <= s < 400:
                return "model_redirect_refused", Billing.NONE
            fixed = {400: "model_request_rejected", 409: "model_request_rejected", 422: "model_request_rejected",
                     401: "model_auth_failed", 403: "model_forbidden", 404: "model_not_found",
                     413: "model_request_too_large", 429: "model_rate_limited"}
            if s in fixed:
                return fixed[s], Billing.NONE
            if 400 <= s < 500:
                return "model_request_rejected", Billing.NONE
            if s == 529:
                return "model_overloaded", Billing.UNKNOWN
            return "model_unavailable", Billing.UNKNOWN
        return "model_failed", Billing.UNKNOWN

    def _parse(self, resp: Any) -> PlanResponse:
        try:
            return self._parse_message(resp)
        except Exception:  # a malformed response is never an exception path out of here
            return PlanResponse(StopKind.INCONSISTENT, "other", (), ModelUsage(), "unrecognized", None, None, 0, 0, 0)

    def _parse_message(self, resp: Any) -> PlanResponse:
        blocks = list(getattr(resp, "content", None) or [])
        kinds = [getattr(b, "type", None) for b in blocks]
        tool_blocks = [b for b, k in zip(blocks, kinds) if k == "tool_use"]
        text_blocks = kinds.count("text")  # their text, like thinking, is dropped unread
        names = [mcp_name(getattr(b, "name", None), self._known) for b in tool_blocks]
        stop = getattr(resp, "stop_reason", None)
        raw = stop if stop in _STOP_REASONS else "other"
        calls = ()
        category = None
        if stop == "tool_use":
            kind = StopKind.INCONSISTENT
            if len(tool_blocks) == 1 and isinstance(tool_blocks[0].input, Mapping):
                args = dict(tool_blocks[0].input)
                if len(json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)) <= MAX_ARGUMENT_CHARS:
                    kind, calls = StopKind.TOOL_CALL, (ProposedToolUse(names[0], args),)
        elif stop == "end_turn":
            kind = StopKind.DONE if not tool_blocks else StopKind.UNEXPECTED
        elif stop == "max_tokens":
            kind = StopKind.TRUNCATED
        elif stop == "refusal":
            kind = StopKind.REFUSAL
            c = getattr(getattr(resp, "stop_details", None), "category", None)  # the explanation is never read
            category = c if c in _REFUSAL_CATEGORIES else "other"
        elif stop == "pause_turn":
            kind = StopKind.PAUSED
        elif stop == "model_context_window_exceeded":
            kind = StopKind.CONTEXT_EXCEEDED
        else:  # stop_sequence (none are sent), None, or a reason this SDK does not know
            kind = StopKind.UNEXPECTED
        u = getattr(resp, "usage", None)
        details = getattr(u, "output_tokens_details", None)
        thinking = getattr(details, "thinking_tokens", None)
        usage = ModelUsage(input_tokens=int(getattr(u, "input_tokens", 0) or 0),
                           output_tokens=int(getattr(u, "output_tokens", 0) or 0),
                           cache_read_input_tokens=int(getattr(u, "cache_read_input_tokens", 0) or 0),
                           cache_creation_input_tokens=int(getattr(u, "cache_creation_input_tokens", 0) or 0),
                           thinking_tokens=int(thinking) if isinstance(thinking, int) else None)
        served = getattr(resp, "model", None)
        rid = getattr(resp, "_request_id", None)
        return PlanResponse(
            stop=kind, raw_stop_reason=raw, calls=calls, usage=usage,
            model_served=served if isinstance(served, str) and MODEL_ID_RE.match(served) else "unrecognized",
            provider_request_id=rid if isinstance(rid, str) and REQUEST_ID_RE.match(rid) else None,
            refusal_category=category, tool_use_blocks=len(tool_blocks), text_blocks=text_blocks,
            unknown_tools=sum(1 for n in names if n == UNKNOWN_TOOL))
