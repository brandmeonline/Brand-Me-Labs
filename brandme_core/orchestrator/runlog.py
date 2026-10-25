"""Assistant run log: one fixed-schema JSON line per record on stdout (ch.03 §11 "LLM execution").

Lines follow the foundation worker pattern (``events/worker.py``): a closed field set per event,
validated before writing, so a new field cannot leak by accident. A line that fails validation
is replaced by ``assistant.runlog_rejected`` carrying only the event name. Logging never fails a
task: write errors are counted in ``dropped``.

What a line may hold: fixed codes, counts, durations, versions, keyed refs (``mcp.refs.log_ref``)
and two correlation keys logged raw on purpose, the gateway request id and the provider's request
id. What it never holds: prompts, the goal, model text or thinking, refusal explanations, tool
arguments or results, provider text, exception text, URLs, hosts, headers, keys, the proxy URL,
or raw member, task, delegation and event ids.

The platform log pipeline routes on ``retention``: ``request_log_30d`` and ``security_audit_180d``
are the spec's proposed classes (ch.03 §11); enforcing them is deployment work.
"""

from __future__ import annotations

import io
import json
import re
import sys
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, TextIO, Tuple

from brandme_core.domains.commerce import autonomy as _autonomy
from brandme_core.domains.providers import tiers as _tiers
from brandme_core.domains.providers.contracts import CAPABILITIES
from brandme_core.mcp.refs import log_ref
from brandme_core.mcp.tools import KNOWN_TOOL_NAMES, UNKNOWN_TOOL

SCHEMA = "brandme.assistant.run_log.v1"
UNRECOGNIZED = "unrecognized"

_REF16 = re.compile(r"^[0-9a-f]{16}$")
_CODE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}$")
_PROVIDER_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_API_VERSION = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PROMPT_VERSION = re.compile(r"^[0-9a-f]{12}$")
_CLIENT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_OPERATION = re.compile(r"^[a-z]+(?:\.[a-z_]+){1,2}$")

STOP_REASONS = frozenset({"end_turn", "max_tokens", "stop_sequence", "tool_use", "pause_turn", "refusal",
                          "model_context_window_exceeded", "other"})
REFUSAL_CATEGORIES = frozenset({"cyber", "bio", "frontier_llm", "reasoning_extraction", "general_harms", "other"})
PLANNER_LABELS = frozenset({"deterministic", "model:anthropic", "custom"})
TASK_STATES = frozenset({"queued", "running", "awaiting_approval", "completed", "cancelled", "failed"})


def _uuid(v: Any) -> bool:
    try:
        return isinstance(v, str) and str(uuid.UUID(v)) == v
    except ValueError:
        return False


def _count(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _rx(pattern: "re.Pattern[str]") -> Callable[[Any], bool]:
    return lambda v: isinstance(v, str) and bool(pattern.match(v))


def _one_of(values) -> Callable[[Any], bool]:
    allowed = frozenset(values)
    return lambda v: isinstance(v, str) and v in allowed


def _model(v: Any) -> bool:
    return v == UNRECOGNIZED or _rx(_MODEL_ID)(v)


def _proposal_tool(v: Any) -> bool:
    return isinstance(v, str) and (v in KNOWN_TOOL_NAMES or v == UNKNOWN_TOOL)


def _audited_tool(v: Any) -> bool:
    return _proposal_tool(v) or v == UNRECOGNIZED


def _operation(v: Any) -> bool:
    return v == UNRECOGNIZED or _rx(_OPERATION)(v)


def _decision_codes(v: Any) -> bool:
    return (isinstance(v, list) and 1 <= len(v) <= 4 and all(isinstance(c, str) and c in _autonomy.CODES for c in v)
            and len(set(v)) == len(v))  # strings first: an unhashable item is a malformed line, never a crash


_LEVELS = tuple(lv.value for lv in _autonomy.AutonomyLevel)


_MODES = ("research", "prepare", "buy_within_rules")
# field -> (validator, nullable)
Spec = Dict[str, Tuple[Callable[[Any], bool], bool]]
EVENTS: Dict[str, Tuple[str, Spec]] = {
    "assistant.planner_selected": ("request_log_30d", {
        "planner": (_one_of(PLANNER_LABELS), False), "provider": (_one_of({"anthropic"}), True),
        "model": (_model, True), "effort": (_one_of({"low", "medium", "high"}), True),
        "sdk_version": (_rx(_SEMVER), True), "api_version": (_rx(_API_VERSION), True),
        "reason": (_one_of({"configured", "default"}), False),
    }),
    "assistant.model_call": ("request_log_30d", {
        "request_id": (_uuid, True), "task_ref": (_rx(_REF16), False), "member_ref": (_rx(_REF16), False),
        "mode": (_one_of(_MODES), False), "step": (_count, False),
        "provider": (_one_of({"anthropic"}), False), "model": (_model, False), "model_served": (_model, True),
        "sdk_version": (_rx(_SEMVER), False), "api_version": (_rx(_API_VERSION), False),
        "prompt_version": (_rx(_PROMPT_VERSION), False), "tool_schema_version": (_rx(_SEMVER), False),
        "effort": (_one_of({"low", "medium", "high"}), False), "prompt_ref": (_rx(_REF16), True),
        "provider_request_id": (_rx(_PROVIDER_REQUEST_ID), True), "duration_ms": (_count, False),
        "input_tokens": (_count, False), "output_tokens": (_count, False),
        "cache_read_input_tokens": (_count, False), "cache_creation_input_tokens": (_count, False),
        "thinking_tokens": (_count, True), "reserved_tokens": (_count, False),
        "reserved_cost_micro_usd": (_count, False), "cost_micro_usd": (_count, False),
        "cost_basis": (_one_of({"usage", "reserved_upper_bound", "none"}), False),
        "task_tokens_total": (_count, False), "task_cost_micro_usd_total": (_count, False),
        "stop_reason": (_one_of(STOP_REASONS), True), "refusal_category": (_one_of(REFUSAL_CATEGORIES), True),
        "tool_use_blocks": (_count, False), "text_blocks": (_count, False), "unknown_tools": (_count, False),
        "tool_calls": (_count, False), "proposed_tool": (_proposal_tool, True), "code": (_rx(_CODE), False),
    }),
    "assistant.task_end": ("request_log_30d", {
        "request_id": (_uuid, True), "task_ref": (_rx(_REF16), False), "member_ref": (_rx(_REF16), False),
        "mode": (_one_of(_MODES), False), "planner": (_one_of(PLANNER_LABELS), False),
        "state": (_one_of(TASK_STATES), False), "code": (_rx(_CODE), False), "model_steps": (_count, False),
        "tool_calls": (_count, False), "refused_calls": (_count, False), "duration_ms": (_count, False),
        "tokens_total": (_count, False), "cost_micro_usd_total": (_count, False),
    }),
    "mcp.tool_call": ("security_audit_180d", {
        "request_id": (_uuid, True), "tool": (_audited_tool, False), "client_id": (_rx(_CLIENT_ID), True),
        "member_ref": (_rx(_REF16), True), "task_ref": (_rx(_REF16), True), "delegation_ref": (_rx(_REF16), True),
        "step": (_count, True), "status": (_one_of({"ok", "error", "refused"}), False),
        "code": (_rx(_CODE), True), "origin": (_one_of({"mcp", "assistant"}), False),
        "duration_ms": (_count, False), "arguments_digest": (_rx(_REF16), False),
    }),
    # One autonomy decision on a buy grant (``CommerceService``, ``autonomy.evaluate``): the agent placing an
    # approved order, at execute and at the last gate before provider I/O. Codes and a cap-ratio band, and
    # ``committed``: whether the deciding transaction returned (a store raising on an unknown commit outcome
    # reports false although the write may have applied). Never amounts, caps, merchant ids, variant refs, raw
    # ids or the member's own actions: who an approval binds to is recorded on the approval, not as a timed line.
    "commerce.autonomy_decision": ("security_audit_180d", {
        "request_id": (_uuid, True), "origin": (_one_of({"mcp", "assistant", "api", "service"}), False),
        "task_ref": (_rx(_REF16), True), "step": (_count, True), "member_ref": (_rx(_REF16), False),
        "delegation_ref": (_rx(_REF16), False), "client_id": (_rx(_CLIENT_ID), False),
        "mode": (_one_of(_MODES), False), "action": (_one_of(a.value for a in _autonomy.Action), False),
        "outcome": (_one_of(o.value for o in _autonomy.Outcome), False),
        "autonomy_level": (_one_of(_LEVELS), False), "required_autonomy_level": (_one_of(_LEVELS), False),
        "scope": (_one_of(_autonomy.SCOPES), False), "codes": (_decision_codes, False),
        "cap_bucket": (_one_of(_autonomy.CAP_BUCKETS), False), "rule_count": (_count, False),
        "boundary_version": (_count, False), "evaluator": (_rx(_SEMVER), False),
        "client_kind": (_one_of({"assistant", "external"}), False), "quote_ref": (_rx(_REF16), True),
        "simulation": (lambda v: isinstance(v, bool), False), "committed": (lambda v: isinstance(v, bool), False),
    }),
    # One partner-tier decision (``providers/tiers.py``): codes, keyed provider and operator refs, unit counts;
    # never prices, decision records or raw ids.
    "provider.tier_decision": ("security_audit_180d", {
        "request_id": (_uuid, True), "origin": (_one_of(_tiers.ORIGINS), False),
        "dimension": (_one_of(_tiers.DIMENSIONS), False), "outcome": (_one_of({"allow", "refuse", "partial"}), False),
        "code": (_one_of(_tiers.CODES), False), "provider_ref": (_rx(_REF16), False), "actor_ref": (_rx(_REF16), True),
        "tier_id": (_rx(_tiers.TIER_ID_RE), True), "tier_source": (_one_of(_tiers.SOURCES), False),
        "placeholder": (lambda v: isinstance(v, bool), False),
        "table_version": (_rx(_tiers.TABLE_VERSION_RE), False), "capability": (_one_of(CAPABILITIES), True),
        "units_requested": (_count, True), "units_refused": (_count, True),
    }),
    # An agent's request to the commerce domain's HTTP API (``CommerceHttpApi``): operation and outcome only.
    "commerce.agent_request": ("security_audit_180d", {
        "request_id": (_uuid, True), "operation": (_operation, False), "client_id": (_rx(_CLIENT_ID), True),
        "member_ref": (_rx(_REF16), True), "delegation_ref": (_rx(_REF16), True),
        "status": (_one_of({"ok", "error", "refused"}), False), "code": (_rx(_CODE), True),
        "duration_ms": (_count, False),
    }),
}
# Cross-field rules. A tool call with no member is only an external invocation refused before any
# principal was verified; every other record names its member.
RULES: Dict[str, Callable[[Mapping[str, Any]], bool]] = {
    "mcp.tool_call": lambda f: f["member_ref"] is not None or (
        f["origin"] == "mcp" and f["status"] == "refused" and f["client_id"] is None
        and f["delegation_ref"] is None and f["task_ref"] is None),
    "commerce.agent_request": lambda f: f["member_ref"] is not None or (
        f["status"] == "refused" and f["client_id"] is None and f["delegation_ref"] is None),
    # allow carries an allow code; partial is only an ingestion page with some, not all, additions refused;
    # ingestion and hydration have no operator, operator actions always name one; a tier id only when assigned.
    "provider.tier_decision": lambda f: (
        (f["outcome"] == "allow") == (f["code"] in _tiers.ALLOW_CODES)
        and (f["outcome"] != "partial" or (f["origin"] == "ingestion" and f["units_refused"] is not None
                                           and f["units_requested"] is not None
                                           and 0 < f["units_refused"] < f["units_requested"]))
        and (f["units_refused"] is None or f["units_requested"] is None or f["units_refused"] <= f["units_requested"])
        and (f["origin"] != "ingestion" or (f["actor_ref"] is None and f["units_requested"] is not None))
        and (f["origin"] != "hydrate" or f["actor_ref"] is None)
        and (f["origin"] not in ("assignment", "activation", "verification") or f["actor_ref"] is not None)
        and (f["dimension"] != "assignment" or f["origin"] == "assignment")
        and (f["code"] != "no_new_listings" or f["dimension"] == "shelf_variants")
        and ((f["tier_id"] is not None) == (f["tier_source"] == "assigned"))
        # an entitlement is only ever allowed under an assigned tier; hydration and tests only ever refuse
        and (f["outcome"] != "allow" or f["code"] in ("no_new_listings", "tier_cleared")
             or f["tier_source"] == "assigned")
        and (f["origin"] not in ("hydrate", "verification") or f["outcome"] == "refuse")
        and (f["dimension"] != "customization" or f["capability"] is not None)),
    # Only the agent's execute is logged: allow carries exactly within_boundary at the buy level, a refusal
    # never does; a binding-only code never appears; an assistant decision names its task; no boundary (or an
    # unreadable one) means no rules and no cap.
    "commerce.autonomy_decision": lambda f: (
        f["mode"] == "buy_within_rules" and f["action"] == "execute" and f["outcome"] in ("allow", "refuse")
        and (f["outcome"] == "allow") == (f["codes"] == ["within_boundary"])
        and (f["outcome"] == "allow" or "within_boundary" not in f["codes"])
        and (f["outcome"] != "allow" or f["autonomy_level"] == f["required_autonomy_level"] == "buy_after_approval")
        and not set(f["codes"]) & set(_autonomy.BINDING_ONLY_CODES)
        and (f["origin"] != "assistant" or f["task_ref"] is not None)
        and (f["scope"] not in ("no_boundary", "unreadable")
             or (f["rule_count"] == 0 and f["cap_bucket"] in ("no_cap", "no_total")))),
}
REJECTED = "assistant.runlog_rejected"
_ENVIRONMENTS = frozenset({"demo", "development", "sandbox", "production"})


class RunLogViolation(ValueError):
    """Raised by a strict ``MemoryRunLog`` (tests) instead of writing ``runlog_rejected``. Decision sinks
    that swallow operational failures let this one through (``strict_violation``): a malformed line is a bug."""

    strict_violation = True


class RunLog(Protocol):
    def planner_selected(self, **fields: Any) -> None: ...

    def model_call(self, **fields: Any) -> None: ...

    def task_end(self, **fields: Any) -> None: ...

    def tool_call(self, audit_record: Mapping[str, Any]) -> None: ...

    def agent_request(self, audit_record: Mapping[str, Any]) -> None: ...

    def autonomy_decision(self, record: Mapping[str, Any]) -> None: ...

    def tier_decision(self, record: Mapping[str, Any]) -> None: ...


def _level(event: str, f: Mapping[str, Any]) -> str:
    if event == "assistant.model_call":
        return "info" if f.get("code") == "ok" else "warning"
    if event == "assistant.task_end":
        return "warning" if f.get("state") == "failed" else "info"
    if event in ("mcp.tool_call", "commerce.agent_request"):
        return "info" if f.get("status") == "ok" else "warning"
    if event in ("commerce.autonomy_decision", "provider.tier_decision"):
        return "warning" if f.get("outcome") in ("refuse", "partial") else "info"
    return "warning" if event == REJECTED else "info"


def tool_call_fields(record: Mapping[str, Any]) -> Dict[str, Any]:
    """The audit record as a run-log line. Sanitized before validation: an external MCP client's
    malformed request id or tool name becomes null / ``unrecognized``, so its audit line is
    never dropped."""
    tool = record.get("tool")
    code = record.get("code")
    client = record.get("client_id")
    delegation = record.get("delegation_id")
    step = record.get("step")
    return {
        "request_id": record.get("request_id") if _uuid(record.get("request_id")) else None,
        "tool": tool if _proposal_tool(tool) else UNRECOGNIZED,
        "client_id": None if client is None else (client if _rx(_CLIENT_ID)(client) else UNRECOGNIZED),
        "member_ref": record.get("member_ref"), "task_ref": record.get("task_ref"),
        "delegation_ref": log_ref("delegation", delegation) if isinstance(delegation, str) and delegation else None,
        "step": step if _count(step) else None, "status": record.get("status"),
        "code": None if code is None else (code if _rx(_CODE)(code) else UNRECOGNIZED),
        "origin": record.get("origin"), "duration_ms": record.get("duration_ms"),
        "arguments_digest": record.get("arguments_digest"),
    }


def agent_request_fields(record: Mapping[str, Any]) -> Dict[str, Any]:
    """A ``CommerceHttpApi`` audit record as a run-log line, sanitized like ``tool_call_fields``."""
    operation, code, client = record.get("operation"), record.get("code"), record.get("client_id")
    delegation = record.get("delegation_id")
    return {
        "request_id": record.get("request_id") if _uuid(record.get("request_id")) else None,
        "operation": operation if _rx(_OPERATION)(operation) else UNRECOGNIZED,
        "client_id": None if client is None else (client if _rx(_CLIENT_ID)(client) else UNRECOGNIZED),
        "member_ref": record.get("member_ref"),
        "delegation_ref": log_ref("delegation", delegation) if isinstance(delegation, str) and delegation else None,
        "status": record.get("status"),
        "code": None if code is None else (code if _rx(_CODE)(code) else UNRECOGNIZED),
        "duration_ms": record.get("duration_ms"),
    }


def autonomy_decision_fields(record: Mapping[str, Any]) -> Dict[str, Any]:
    """A ``CommerceService`` autonomy decision as a run-log line; ids become keyed refs or are dropped."""
    delegation, client, rid = record.get("delegation_id"), record.get("client_id"), record.get("request_id")
    out = {k: record.get(k) for k in ("origin", "task_ref", "step", "member_ref", "mode", "action", "outcome",
                                       "autonomy_level", "required_autonomy_level", "scope", "codes", "cap_bucket",
                                       "rule_count", "boundary_version", "evaluator", "client_kind", "quote_ref",
                                       "simulation", "committed")}
    out["request_id"] = rid if _uuid(rid) else None
    out["delegation_ref"] = log_ref("delegation", delegation) if isinstance(delegation, str) and delegation else None
    out["client_id"] = client if _rx(_CLIENT_ID)(client) else UNRECOGNIZED
    return out


def tier_decision_fields(record: Mapping[str, Any]) -> Dict[str, Any]:
    """A ``tiers.decision_record`` as a run-log line: exactly the closed fields, the request id a UUID or None."""
    out = {k: record.get(k) for k in ("origin", "dimension", "outcome", "code", "provider_ref", "actor_ref", "tier_id",
                                       "tier_source", "placeholder", "table_version", "capability", "units_requested",
                                       "units_refused")}
    out["request_id"] = record.get("request_id") if _uuid(record.get("request_id")) else None
    return out


class JsonLineRunLog:
    def __init__(self, *, environment: str, stream: Optional[TextIO] = None,
                 wall: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        if environment not in _ENVIRONMENTS:
            raise ValueError("unknown environment")
        self.environment = environment
        self._stream = stream  # None: sys.stdout at write time
        self._wall = wall
        self._lock = threading.Lock()
        self.dropped = 0

    # -- events ------------------------------------------------------------------
    def planner_selected(self, **fields: Any) -> None:
        self._emit("assistant.planner_selected", fields)

    def model_call(self, **fields: Any) -> None:
        self._emit("assistant.model_call", fields)

    def task_end(self, **fields: Any) -> None:
        self._emit("assistant.task_end", fields)

    def tool_call(self, audit_record: Mapping[str, Any]) -> None:
        """An ``McpToolExecutor`` audit sink."""
        try:
            fields = tool_call_fields(audit_record)
        except Exception:
            fields = {}
        self._emit("mcp.tool_call", fields)

    def agent_request(self, audit_record: Mapping[str, Any]) -> None:
        """A ``CommerceHttpApi`` audit sink."""
        try:
            fields = agent_request_fields(audit_record)
        except Exception:
            fields = {}
        self._emit("commerce.agent_request", fields)

    def autonomy_decision(self, record: Mapping[str, Any]) -> None:
        """A ``CommerceService`` autonomy sink (``add_autonomy_sink``)."""
        try:
            fields = autonomy_decision_fields(record)
        except Exception:
            fields = {}
        self._emit("commerce.autonomy_decision", fields)

    def tier_decision(self, record: Mapping[str, Any]) -> None:
        """A partner-tier sink (``ProviderSetupService`` ``tier_audit``)."""
        try:
            fields = tier_decision_fields(record)
        except Exception:
            fields = {}
        self._emit("provider.tier_decision", fields)

    # -- emission ----------------------------------------------------------------
    def _emit(self, event: str, fields: Mapping[str, Any]) -> None:
        retention, spec = EVENTS[event]
        if not self._valid(spec, fields) or not RULES.get(event, lambda f: True)(fields):
            self._violation(event)
            return
        self._write(self._line(event, retention, dict(fields)))

    @staticmethod
    def _valid(spec: Spec, fields: Mapping[str, Any]) -> bool:
        if set(fields) != set(spec):
            return False
        for name, (check, nullable) in spec.items():
            v = fields[name]
            if v is None:
                if not nullable:
                    return False
            elif not check(v):
                return False
        return True

    def _violation(self, event: str) -> None:
        self._write(self._line(REJECTED, "request_log_30d",
                               {"rejected_event": event, "code": "runlog_schema_violation"}))

    def _line(self, event: str, retention: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        return {"schema": SCHEMA, "event": event, "ts": self._wall().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "retention": retention, "environment": self.environment, "level": _level(event, fields), **fields}

    def _write(self, line: Dict[str, Any]) -> None:
        text = json.dumps(line, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        try:
            with self._lock:
                stream = self._stream if self._stream is not None else sys.stdout
                stream.write(text)
                stream.flush()
        except Exception:  # logging never fails a task
            self.dropped += 1


class MemoryRunLog(JsonLineRunLog):
    """Same validation; ``lines`` holds the parsed dicts. ``strict`` raises on a violation."""

    def __init__(self, *, environment: str = "development", strict: bool = False,
                 wall: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        super().__init__(environment=environment, stream=io.StringIO(), wall=wall)
        self.strict = strict
        self.lines: List[Dict[str, Any]] = []

    def _violation(self, event: str) -> None:
        if self.strict:
            raise RunLogViolation(event)
        super()._violation(event)

    def _write(self, line: Dict[str, Any]) -> None:
        super()._write(line)
        self.lines.append(json.loads(json.dumps(line)))

    def events(self, name: str) -> List[Dict[str, Any]]:
        return [line for line in self.lines if line["event"] == name]


class NullRunLog:
    def planner_selected(self, **fields: Any) -> None:
        pass

    def model_call(self, **fields: Any) -> None:
        pass

    def task_end(self, **fields: Any) -> None:
        pass

    def tool_call(self, audit_record: Mapping[str, Any]) -> None:
        pass

    def agent_request(self, audit_record: Mapping[str, Any]) -> None:
        pass

    def autonomy_decision(self, record: Mapping[str, Any]) -> None:
        pass

    def tier_decision(self, record: Mapping[str, Any]) -> None:
        pass
