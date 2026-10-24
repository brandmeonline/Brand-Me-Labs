"""Stateless model planner for assistant tasks (dev form; ch.03 §11 "LLM execution").

The model only *proposes* tool calls. The runtime still decides what runs: its guards (approval
stop, proposal cap, mode allowlist, duplicates, identifier provenance, price ceiling) and the
audited executor path (identity arguments, card scan, closed schemas, delegation scopes,
idempotency) are unchanged, so a model gains no authority a deterministic planner lacks.

* **Stateless.** Every step is one fresh request built from the task's observations
  (``transcript.build_plan_request``): one ``user`` message, no replayed assistant turn or
  thinking block. One ``ModelPlanner`` serves every task and thread; its only mutable state is
  the cost ledger (keyed refs) and an immutable per-tool-set cache.
* **Nothing the model writes persists** except its proposal: the adapter drops text and
  thinking, and ``PlanResponse`` has no text field. At most one proposal per step.
* **Fails closed.** Any stop but a single tool call or a plain finish fails the task with a
  fixed code. There is no deterministic fallback inside a task.
* **Budgets** are reserved before any I/O and settled after (``budget.py``): model calls per
  task, tokens and cost per task, member and environment daily quotas, wall clock and a
  per-call timeout. No model call is made inside a store transaction.
* **Run log** (``runlog.py``): one closed-schema line per attempted call and per task, joined to
  the audit log by keyed task refs. Never prompts, goal text, model text, arguments, URLs, keys
  or raw ids.
* **Credentials and egress** (``planner_from_env``): ``BRANDME_DEV_ANTHROPIC_API_KEY`` only, the
  explicit base URL, and the explicit ``BRANDME_ASSISTANT_EGRESS_PROXY`` /
  ``BRANDME_ASSISTANT_CA_BUNDLE``. Brand.Me code never reads ``ANTHROPIC_*`` or ambient proxy
  settings, and what the SDK reads on its own never reaches the wire (``anthropic_adapter``).
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, List, Mapping, NoReturn, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from brandme_core.domains.commerce.store import in_store_transaction
from brandme_core.mcp.refs import canonical_json, log_ref
from brandme_core.mcp.tools import SERVER_VERSION, McpToolExecutor

from .anthropic_adapter import (  # noqa: F401  (re-exported)
    DEFAULT_EFFORT, DEFAULT_MODEL, EFFORTS, MODEL_PROFILES, require_dev_key, strict_schema,
)
from .budget import BudgetRefused, CostLedger, InMemoryCostLedger
from .model_adapter import (  # noqa: F401  (re-exported)
    Billing, ModelAdapter, ModelCallError, PlannerConfigError, PlanResponse, StopKind, ToolDef, mcp_name, wire_name,
)
from .runlog import NullRunLog, RunLog
from .runtime import DeterministicPlanner, Planner, PlannerError, ProposedCall, TaskView
from .transcript import PROMPT_VERSION, build_plan_request

KEY_ENV = "BRANDME_DEV_ANTHROPIC_API_KEY"
PLANNER_ENV = "BRANDME_ASSISTANT_PLANNER"
MODEL_ENV = "BRANDME_ASSISTANT_MODEL"
EFFORT_ENV = "BRANDME_ASSISTANT_EFFORT"
PROXY_ENV = "BRANDME_ASSISTANT_EGRESS_PROXY"
CA_ENV = "BRANDME_ASSISTANT_CA_BUNDLE"
DEV_MODES = ("development", "demo")
# purchase.execute needs the member's approval id, which only exists after the task stops.
MODEL_WITHHELD_TOOLS = frozenset({"brandme.purchase.execute"})

# A plain finish or one tool call proceed; every other stop fails the task with its code.
STOP_CODES = {
    StopKind.TOOL_CALL: "ok", StopKind.DONE: "ok", StopKind.REFUSAL: "model_refused",
    StopKind.TRUNCATED: "model_output_truncated", StopKind.PAUSED: "model_turn_paused",
    StopKind.CONTEXT_EXCEEDED: "model_context_exhausted", StopKind.INCONSISTENT: "model_response_inconsistent",
    StopKind.UNEXPECTED: "model_stop_unexpected",
}


@dataclass(frozen=True)
class ModelBudget:
    max_model_calls: int = 6
    max_output_tokens: int = 16_000  # thinking counts toward max_tokens on this model
    max_request_bytes: int = 64_000
    max_task_tokens: int = 300_000  # committed = settled + reserved; input (cached or not) + output
    max_task_cost_micro_usd: int = 1_000_000  # $1.00
    member_daily_tokens: int = 2_000_000
    member_daily_cost_micro_usd: int = 5_000_000  # $5.00
    environment_daily_cost_micro_usd: int = 50_000_000  # $50.00
    per_call_timeout_s: float = 60.0
    min_call_seconds: float = 5.0
    max_task_seconds: float = 240.0  # the runtime caps any planner at HARD_MAX_SECONDS


def derived_idempotency_key(task_id: str, tool: str, arguments: Mapping[str, Any]) -> str:
    """The same proposal in the same task always carries the same key (39 characters)."""
    digest = hashlib.sha256(f"{task_id}\n{tool}\n{canonical_json(arguments)}".encode()).hexdigest()
    return "bmtask-" + digest[:32]


class ModelPlanner:
    """``Planner`` whose proposals come from one fresh model request per step."""

    runs_in_background = True  # a model run outlives an HTTP request: the HTTP create answers 202

    def __init__(self, adapter: ModelAdapter, *, budget: ModelBudget = ModelBudget(),
                 ledger: Optional[CostLedger] = None, run_log: Optional[RunLog] = None, environment: str,
                 clock: Callable[[], float] = time.monotonic,
                 in_transaction: Callable[[], bool] = in_store_transaction):
        self.adapter = adapter
        self.budget = budget
        self.ledger = ledger if ledger is not None else InMemoryCostLedger()
        self.run_log = run_log if run_log is not None else NullRunLog()
        self.environment = environment
        self.clock = clock
        self.label = f"model:{adapter.provider}"
        self.max_seconds = budget.max_task_seconds
        self._in_transaction = in_transaction
        self._advertised = {t["name"]: t for t in McpToolExecutor.list_tools()["tools"]}
        self._needs_key = frozenset(n for n, t in self._advertised.items()
                                    if t["_meta"]["brandme/requiresIdempotencyKey"])
        self._tooldefs: Dict[FrozenSet[str], Tuple[ToolDef, ...]] = {}  # immutable per tool set
        self._lock = threading.Lock()

    # -- planning ---------------------------------------------------------------
    def next_calls(self, task: TaskView, observations: Sequence[Mapping[str, Any]]) -> List[ProposedCall]:
        b, profile = self.budget, self.adapter.profile
        ctx = _Call(task, log_ref("task", task.id), log_ref("member", task.member_id))
        if task.step > b.max_model_calls:
            raise PlannerError("model_call_budget_exhausted")  # task_end records it
        if self._in_transaction():
            self._fail(ctx, "model_call_in_transaction")
        remaining = task.deadline - self.clock()
        if remaining < b.min_call_seconds:
            self._fail(ctx, "task_time_budget_exhausted")
        req = build_plan_request(mode=task.mode, goal=task.goal, constraints=task.constraints,
                                 steps_left=b.max_model_calls - task.step, tool_calls_left=task.tool_calls_left,
                                 observations=observations, tools=self._tools(task.tools),
                                 max_output_tokens=b.max_output_tokens)
        ctx.enc = enc = self.adapter.encode(req)
        if enc.size_bytes > b.max_request_bytes:
            self._fail(ctx, "model_prompt_too_large")
        # Upper bounds before any I/O: a token is at least one byte of the request, plus framing.
        input_upper = enc.size_bytes + profile.input_overhead_tokens
        tokens_upper = input_upper + b.max_output_tokens
        cost_upper = profile.price.upper_bound_micro_usd(input_upper, b.max_output_tokens)
        try:
            ctx.res = self.ledger.reserve(task_ref=ctx.task_ref, member_ref=ctx.member_ref,
                                          environment=self.environment, step=task.step, tokens=tokens_upper,
                                          cost_micro_usd=cost_upper, budget=b)
        except BudgetRefused as exc:
            self._fail(ctx, exc.code)  # nothing is sent
        started = self.clock()
        try:
            resp = self.adapter.send(enc, timeout_s=min(b.per_call_timeout_s, remaining - 1.0))
        except Exception as exc:
            ctx.duration_ms = self._ms(started)
            err = exc if isinstance(exc, ModelCallError) else ModelCallError("model_failed", Billing.UNKNOWN)
            if err.billing is Billing.UNKNOWN:  # it may have been billed: charge the reservation
                self.ledger.settle(ctx.res, tokens=tokens_upper, cost_micro_usd=cost_upper,
                                   basis="reserved_upper_bound")
                ctx.cost, ctx.basis = cost_upper, "reserved_upper_bound"
            else:
                self.ledger.release(ctx.res)
            self._fail(ctx, err.code)
        ctx.duration_ms, ctx.resp = self._ms(started), resp
        u = resp.usage
        ctx.cost, ctx.basis = profile.price.cost_micro_usd(u), "usage"
        self.ledger.settle(ctx.res, tokens=u.total_input + u.output_tokens, cost_micro_usd=ctx.cost, basis="usage")
        if u.total_input > input_upper or u.output_tokens > b.max_output_tokens:
            self._fail(ctx, "model_reservation_exceeded")  # the bound did not hold: run nothing
        code = STOP_CODES.get(resp.stop, "model_stop_unexpected")
        if code != "ok":
            self._fail(ctx, code)
        if resp.stop is StopKind.DONE:
            self._log(ctx, "ok")
            return []
        call = resp.calls[0]
        ctx.proposed = call.tool
        self._log(ctx, "ok")
        key = derived_idempotency_key(task.id, call.tool, call.arguments) if call.tool in self._needs_key else None
        return [ProposedCall(call.tool, dict(call.arguments), idempotency_key=key)]

    def on_task_end(self, task: TaskView, state: str) -> Dict[str, int]:
        return self.ledger.close_task(log_ref("task", task.id))

    def close(self) -> None:
        self.adapter.close()

    # -- internals ----------------------------------------------------------------
    def _tools(self, names: Sequence[str]) -> Tuple[ToolDef, ...]:
        key = frozenset(names)
        with self._lock:
            cached = self._tooldefs.get(key)
            if cached is None:
                cached = tuple(sorted((ToolDef(n, self._advertised[n]["description"], self._advertised[n]["inputSchema"])
                                       for n in key if n in self._advertised and n not in MODEL_WITHHELD_TOOLS),
                                      key=lambda t: t.name))
                self._tooldefs[key] = cached
            return cached

    def _ms(self, started: float) -> int:
        return max(0, int((self.clock() - started) * 1000))

    def _fail(self, ctx: "_Call", code: str) -> NoReturn:
        self._log(ctx, code)
        raise PlannerError(code) from None

    def _log(self, ctx: "_Call", code: str) -> None:
        resp, res, enc = ctx.resp, ctx.res, ctx.enc
        u = resp.usage if resp is not None else None
        tokens_total, cost_total = self.ledger.task_totals(ctx.task_ref)
        a = self.adapter
        self.run_log.model_call(
            request_id=ctx.task.request_id, task_ref=ctx.task_ref, member_ref=ctx.member_ref,
            mode=ctx.task.mode.value, step=ctx.task.step, provider=a.provider, model=a.model,
            model_served=resp.model_served if resp else None, sdk_version=a.sdk_version, api_version=a.api_version,
            prompt_version=PROMPT_VERSION, tool_schema_version=SERVER_VERSION, effort=a.effort,
            prompt_ref=log_ref("prompt", enc.canonical) if enc is not None else None,
            provider_request_id=resp.provider_request_id if resp else None, duration_ms=ctx.duration_ms,
            input_tokens=u.input_tokens if u else 0, output_tokens=u.output_tokens if u else 0,
            cache_read_input_tokens=u.cache_read_input_tokens if u else 0,
            cache_creation_input_tokens=u.cache_creation_input_tokens if u else 0,
            thinking_tokens=u.thinking_tokens if u else None,
            reserved_tokens=res.tokens if res else 0, reserved_cost_micro_usd=res.cost_micro_usd if res else 0,
            cost_micro_usd=ctx.cost, cost_basis=ctx.basis, task_tokens_total=tokens_total,
            task_cost_micro_usd_total=cost_total, stop_reason=resp.raw_stop_reason if resp else None,
            refusal_category=resp.refusal_category if resp else None,
            tool_use_blocks=resp.tool_use_blocks if resp else 0, text_blocks=resp.text_blocks if resp else 0,
            unknown_tools=resp.unknown_tools if resp else 0, tool_calls=1 if ctx.proposed else 0,
            proposed_tool=ctx.proposed, code=code)


class _Call:
    """Per-call values for the run-log line (never kept on the planner)."""

    def __init__(self, task: TaskView, task_ref: str, member_ref: str):
        self.task, self.task_ref, self.member_ref = task, task_ref, member_ref
        self.enc: Any = None
        self.res: Any = None
        self.resp: Optional[PlanResponse] = None
        self.duration_ms = 0
        self.cost = 0
        self.basis = "none"
        self.proposed: Optional[str] = None


# ------------------------------------------------------------------- selection
def _mode(env: Mapping[str, str]) -> Optional[str]:
    from brandme_core.config import ModeConfigurationError, get_mode
    try:
        return get_mode(env).value
    except ModeConfigurationError:
        return None


def _valid_proxy(url: str) -> bool:
    try:
        parts = urlsplit(url)
        port_ok = parts.port is None or 0 < parts.port < 65536
    except ValueError:
        return False
    return (parts.scheme in ("http", "https") and bool(parts.hostname) and port_ok
            and parts.path in ("", "/") and not parts.query and not parts.fragment)


def planner_from_env(env: Optional[Mapping[str, str]] = None, *, run_log: Optional[RunLog] = None,
                     ledger: Optional[CostLedger] = None, transport: Any = None,
                     clock: Callable[[], float] = time.monotonic) -> Planner:
    """The planner for this process, decided once at startup (reuse it: it holds the SDK client).

    * A dev key belongs in development or demo only. Set with ``BRANDME_MODE`` unset it refuses
      to boot (``mode_required``); set in sandbox or production it refuses to boot
      (``model_planner_dev_only``), whatever the planner choice, so a misplaced key is surfaced.
    * ``BRANDME_ASSISTANT_PLANNER`` unset: the deterministic planner, unless a dev key is set in
      development or demo, which selects the model planner.
    * ``deterministic``: the deterministic planner.
    * ``anthropic``: the model planner, development/demo only; anything missing refuses to boot.

    Reads only Brand.Me variables: the key, ``BRANDME_MODE``, ``BRANDME_ASSISTANT_PLANNER``,
    ``_MODEL``, ``_EFFORT``, ``_EGRESS_PROXY`` and ``_CA_BUNDLE``. Errors carry fixed codes only.
    """
    env = os.environ if env is None else env
    choice = (env.get(PLANNER_ENV) or "").strip().lower()
    key = env.get(KEY_ENV) or ""
    if choice not in ("", "deterministic", "anthropic"):
        raise PlannerConfigError("planner_unknown")
    mode_set = bool((env.get("BRANDME_MODE") or "").strip())
    if key:
        if not mode_set:
            raise PlannerConfigError("mode_required")
        if _mode(env) not in DEV_MODES:
            raise PlannerConfigError("model_planner_dev_only")
    if choice == "deterministic":
        return DeterministicPlanner()
    if not mode_set:
        if choice == "anthropic":
            raise PlannerConfigError("mode_required")
        return DeterministicPlanner()
    mode = _mode(env)
    if choice == "":
        if not key:
            return DeterministicPlanner()
    elif mode not in DEV_MODES:
        raise PlannerConfigError("model_planner_dev_only")
    elif not key:
        raise PlannerConfigError("model_key_missing")
    require_dev_key(key)
    model = env.get(MODEL_ENV) or DEFAULT_MODEL
    if model not in MODEL_PROFILES:
        raise PlannerConfigError("model_not_supported")
    effort = env.get(EFFORT_ENV) or DEFAULT_EFFORT
    if effort not in EFFORTS:
        raise PlannerConfigError("model_effort_invalid")
    proxy = env.get(PROXY_ENV) or None
    if proxy is not None and not _valid_proxy(proxy):
        raise PlannerConfigError("model_egress_proxy_invalid")
    ca_bundle = env.get(CA_ENV) or None
    if ca_bundle is not None and not os.path.isfile(ca_bundle):
        raise PlannerConfigError("model_ca_bundle_invalid")
    from .anthropic_adapter import AnthropicAdapter  # the SDK loads only on this branch
    adapter = AnthropicAdapter(api_key=key, model=model, effort=effort, transport=transport,
                               egress_proxy=proxy, ca_bundle=ca_bundle)
    return ModelPlanner(adapter, ledger=ledger, run_log=run_log, environment=mode, clock=clock)
