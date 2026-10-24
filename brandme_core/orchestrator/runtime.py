"""Structured assistant task runtime.

The planner (deterministic, or the stateless model planner in ``model_planner``) only
*proposes* typed tool calls. The runtime decides what runs:

* the tools a planner is offered are the mode's allowlist intersected with the scopes both
  the principal and its delegation grant, fixed for the run;
* runtime guards come first: nothing more after an approval request, a per-step proposal cap,
  the mode allowlist, no repeats of a call that already ran, identifiers must come from earlier
  results (or, for order status, from the member's own goal), and the member's price ceiling;
* every remaining call goes through ``McpToolExecutor.call`` with the task's authenticated
  principal — the same validation, policy and audit record as external MCP clients,
  correlated by the task id. A refused proposal is audited too: one record per proposal;
* tool results go back to the planner as data (a private copy); text inside them can never add
  tools, scopes or approvals;
* per-task call, refusal and wall-clock budgets; cancellation stops new side effects. A planner
  or executor failure marks the task failed with a fixed code, never exception text;
* every call runs under the task's processing basis (its creation time): a My Data deletion of a
  category that completes after the task was created refuses the task's next write there, and the
  task stops with ``processing_restricted`` rather than rebuild the data from what it read before.

Task events expose goals, findings, proposed actions, refusals, approval requests and
outcomes — not model reasoning. Every ``tool`` in an event is a known tool name or
``unknown_tool``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Tuple

from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.domains.commerce.errors import CommerceError
from brandme_core.domains.commerce.money import Money, MoneyError
from brandme_core.domains.commerce.principal import Principal, is_first_party
from brandme_core.domains.commerce.service import processing_basis
from brandme_core.mcp.authz import MCP_PROTOCOL_VERSION
from brandme_core.mcp.refs import canonical_json, log_ref
from brandme_core.mcp.tools import (
    KNOWN_TOOL_NAMES, UNKNOWN_TOOL, McpToolExecutor, contains_card_security_code, contains_payment_credential,
)

from .runlog import NullRunLog, RunLog

MODE_TOOLS = {
    AssistanceMode.RESEARCH: frozenset({"brandme.catalog.search", "brandme.order.status"}),
    AssistanceMode.PREPARE: frozenset({"brandme.catalog.search", "brandme.order.status", "brandme.cart.create",
                                       "brandme.cart.update", "brandme.checkout.quote", "brandme.purchase.request"}),
    AssistanceMode.BUY_WITHIN_RULES: frozenset({"brandme.catalog.search", "brandme.order.status",
                                                "brandme.cart.create", "brandme.cart.update",
                                                "brandme.checkout.quote", "brandme.purchase.request",
                                                "brandme.purchase.execute"}),
}
MAX_CALLS = 12  # executed tool calls per task
MAX_REFUSALS = 12  # refused proposals per task
MAX_PROPOSALS_PER_STEP = 4
MAX_SECONDS = 30.0  # wall clock for a planner that does not say
HARD_MAX_SECONDS = 300.0  # no planner may ask for more
KNOWN_TOOLS = KNOWN_TOOL_NAMES
_ADVERTISED = {t["name"]: t for t in McpToolExecutor.list_tools()["tools"]}
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_PLANNER_LABELS = frozenset({"deterministic", "model:anthropic", "custom"})
_log = logging.getLogger("brandme.assistant")


class IdempotencyReuse(PermissionError):
    """The same idempotency key was used for a different task."""


class PlannerError(Exception):
    """A planner cannot continue; ``code`` is a fixed, member-safe reason code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TaskConstraints:
    """Member-set limits a task carries. ``price_ceiling`` is the all-in total the member will
    consider (``budget_hint``): same currency, no FX, enforced by the runtime at ``purchase.request``."""
    price_ceiling: Optional[Money] = None


@dataclass(frozen=True)
class ProposedCall:
    tool: str
    arguments: Dict[str, Any]
    idempotency_key: Optional[str] = None


@dataclass(frozen=True)
class TaskEvent:
    seq: int
    type: str  # goal | finding | proposed_action | action_refused | approval_requested | outcome | error | cancelled
    data: Dict[str, Any]


@dataclass
class AssistantTask:
    id: str
    member_id: str
    delegation_id: Optional[str]
    mode: AssistanceMode
    goal: str
    state: str = "queued"  # queued | running | awaiting_approval | completed | cancelled | failed
    events: List[TaskEvent] = field(default_factory=list)
    cancel_requested: bool = False
    constraints: TaskConstraints = TaskConstraints()
    request_id: Optional[str] = None  # the gateway request id the task was created under (a UUID)
    planner_label: str = "deterministic"
    submitted: bool = False  # handed to a background runner (set once)
    # When the task was created, on the commerce service's clock (set by ``create``). Everything
    # the task reads is read after this, so it is the processing basis of every write it makes.
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class TaskView:
    """What a planner sees of a task at one step: a frozen copy, never the task itself."""
    id: str
    member_id: str
    delegation_id: Optional[str]
    mode: AssistanceMode
    goal: str
    constraints: TaskConstraints
    request_id: Optional[str]
    environment: str
    tools: Tuple[str, ...]  # exposed MCP tool names, sorted, fixed for the run
    step: int
    tool_calls_made: int
    tool_calls_left: int
    deadline: float  # on the runtime's monotonic clock


class Planner(Protocol):
    """Optional attributes: ``label``, ``runs_in_background``, ``max_seconds``,
    ``on_task_end(view, state) -> totals`` and ``close()``."""

    def next_calls(self, task: TaskView, observations: List[Dict[str, Any]]) -> List[ProposedCall]: ...


class DeterministicPlanner:
    """No-AI planner: search → (prepare) cart for the top in-stock result → quote → approval request."""

    label = "deterministic"
    runs_in_background = False
    max_seconds = MAX_SECONDS

    def next_calls(self, task: TaskView, observations: List[Dict[str, Any]]) -> List[ProposedCall]:
        if not observations:
            return [ProposedCall("brandme.catalog.search", {"query": task.goal[:200], "limit": 6})]
        last = observations[-1]
        if task.mode is AssistanceMode.RESEARCH or last.get("status") != "ok":
            return []
        content = last.get("structured_content") or {}
        tool = last.get("tool")
        if tool == "brandme.catalog.search":
            ceiling = getattr(getattr(task, "constraints", None), "price_ceiling", None)
            items = [i for i in content.get("items", []) if i.get("availability") == "in_stock" and i.get("variant_id")
                     and _within(i.get("observed_price"), ceiling)]
            if not items:
                return []
            top = items[0]
            return [ProposedCall("brandme.cart.create", {
                "provider_id": top["provider_id"], "merchant_id": top["merchant_id"],
                "lines": [{"variant_id": top["variant_id"], "source_variant_ref": top["source_variant_ref"],
                           "quantity": 1}]}, idempotency_key=f"task-{task.id}-cart")]
        if tool == "brandme.cart.create":
            return [ProposedCall("brandme.checkout.quote", {"cart_id": content["cart_id"]})]
        if tool == "brandme.checkout.quote":
            return [ProposedCall("brandme.purchase.request", {"quote_id": content["quote"]["id"]})]
        return []


def _within(price: Any, ceiling: Optional[Money]) -> bool:
    if ceiling is None:
        return True
    try:
        return isinstance(price, dict) and price.get("currency") == ceiling.currency and \
            int(price.get("amount_minor")) <= ceiling.amount_minor
    except (TypeError, ValueError):
        return False


def _uuid_or_none(value: Optional[str]) -> Optional[str]:
    try:
        return str(uuid.UUID(str(value))) if value else None
    except ValueError:
        return None


@dataclass
class _Run:
    steps: int = 0
    calls: int = 0
    refused: int = 0
    view: Optional[TaskView] = None


class AssistantRuntime:
    def __init__(self, executor: McpToolExecutor, *, environment: str, run_log: Optional[RunLog] = None,
                 monotonic: Callable[[], float] = time.monotonic):
        self.executor = executor
        self.environment = environment
        self.run_log = run_log if run_log is not None else NullRunLog()
        self._monotonic = monotonic
        self._tasks: Dict[str, AssistantTask] = {}
        # (member, delegation, idempotency key) -> (request digest, task id): a retried create is the same task.
        self._by_key: Dict[Tuple[str, str, str], Tuple[str, str]] = {}
        self._lock = threading.RLock()

    def create(self, principal: Principal, goal: str, mode: AssistanceMode, *,
               idempotency_key: Optional[str] = None, constraints: TaskConstraints = TaskConstraints(),
               request_id: Optional[str] = None, planner_label: str = "deterministic") -> AssistantTask:
        """Create a task. With an ``idempotency_key``, a retry returns the original task (``replayed``)."""
        if principal.environment != self.environment:
            raise PermissionError("environment mismatch")
        principal = self._bind(principal)
        delegation = self.executor.commerce.store.get("delegations", principal.delegation_id)
        if delegation.mode is not mode:
            raise PermissionError("task mode differs from the delegation's mode")
        if contains_payment_credential(goal) or contains_card_security_code(goal):
            # Card data never enters task events, logs or a model prompt (ch.05 §6, BM-COM-018).
            raise PermissionError("remove payment card details from the request")
        ceiling = constraints.price_ceiling
        hint = json.dumps(ceiling.to_wire(), sort_keys=True) if ceiling else "-"
        digest = hashlib.sha256(f"{mode.value}\n{goal[:1000]}\n{hint}".encode()).hexdigest()
        slot = (principal.member_id, principal.delegation_id, idempotency_key) if idempotency_key else None
        label = planner_label if planner_label in _PLANNER_LABELS else "custom"
        with self._lock:
            if slot and slot in self._by_key:
                prior_digest, task_id = self._by_key[slot]
                if prior_digest != digest:
                    raise IdempotencyReuse("idempotency key reused for a different task")
                return self._tasks[task_id]
            task = AssistantTask(str(uuid.uuid4()), principal.member_id, principal.delegation_id, mode, goal[:1000],
                                 constraints=constraints, request_id=_uuid_or_none(request_id), planner_label=label,
                                 created_at=self.executor.commerce.clock())
            self._emit(task, "goal", {"goal": task.goal, "mode": mode.value, "planner": label,
                                      "price_ceiling": ceiling.to_wire() if ceiling else None})
            self._tasks[task.id] = task
            if slot:
                self._by_key[slot] = (digest, task.id)
        return task

    def _bind(self, principal: Principal) -> Principal:
        """Tasks run only as an agent under the member's active delegation."""
        if is_first_party(principal):
            raise PermissionError("assistant tasks run under a delegation, not a member session")
        try:
            return self.executor.commerce.bind(principal)
        except CommerceError as exc:
            raise PermissionError(exc.detail) from None

    def get(self, principal: Principal, task_id: str) -> AssistantTask:
        """The member's own session sees their tasks; an agent only the tasks of its active grant."""
        task = self._tasks.get(task_id)
        if task is None or task.member_id != principal.member_id:
            raise KeyError("task not found")
        if not is_first_party(principal):
            try:
                bound = self._bind(principal)
            except PermissionError:
                raise KeyError("task not found") from None
            if bound.delegation_id != task.delegation_id:
                raise KeyError("task not found")
        return task

    def cancel(self, principal: Principal, task_id: str) -> AssistantTask:
        task = self.get(principal, task_id)
        task.cancel_requested = True
        return task

    def events_after(self, principal: Principal, task_id: str, after: Optional[int]) -> List[TaskEvent]:
        return [e for e in self.get(principal, task_id).events if after is None or e.seq > after]

    def mark_submitted(self, task_id: str) -> bool:
        """Test-and-set: true only for the first caller, so a retried create never submits twice."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.submitted:
                return False
            task.submitted = True
            return True

    def fail(self, task_id: str, code: str) -> None:
        """Fail a task that has not finished (queued or running) with a fixed code."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.state not in ("queued", "running"):
                return
            task.state = "failed"
            self._emit(task, "error", {"code": code if _CODE_RE.match(code or "") else "planner_failed"})

    def run(self, principal: Principal, task_id: str, planner: Planner) -> AssistantTask:
        principal = self._bind(principal)
        task = self.get(principal, task_id)
        if principal.delegation_id != task.delegation_id:
            raise PermissionError("task bound to a different delegation")
        with self._lock:  # claim it: a task runs once, however many times its create is retried
            if task.state != "queued":
                return task
            task.state = "running"
        started = self._monotonic()
        run = _Run()
        try:
            # Set here, in the thread that runs the task, so inline and background runs both carry it.
            with processing_basis(task.created_at):
                self._loop(principal, task, planner, run, started)
        except BaseException:
            # Never leave a task "running" that nothing is running: it could not be retried or cancelled.
            self.fail(task.id, "runtime_failed")
            raise
        finally:
            self._finish(task, planner, run, started)
        return task

    # -- the loop ----------------------------------------------------------------
    def _loop(self, principal: Principal, task: AssistantTask, planner: Planner, run: _Run, started: float) -> None:
        exposed = self._exposed_tools(principal, task.mode)
        deadline = started + min(float(getattr(planner, "max_seconds", MAX_SECONDS)), HARD_MAX_SECONDS)
        run.view = self._view(task, exposed, 0, 0, deadline)
        observations: List[Dict[str, Any]] = []
        while True:
            if task.cancel_requested:
                with self._lock:
                    task.state = "cancelled"
                    self._emit(task, "cancelled",
                               {"detail": "No new actions will be taken; sent actions keep reconciling."})
                return
            if task.state == "awaiting_approval":
                break  # the member decides next; nothing more to plan
            if run.calls >= MAX_CALLS or run.refused >= MAX_REFUSALS or self._monotonic() > deadline:
                self.fail(task.id, "task_budget_exhausted")
                return
            run.steps += 1
            view = run.view = self._view(task, exposed, run.steps, run.calls, deadline)
            try:
                proposals = planner.next_calls(view, copy.deepcopy(observations))
            except PlannerError as exc:
                self.fail(task.id, exc.code)
                return
            except Exception as exc:  # a planner bug: fixed code, no exception text anywhere
                _log.warning("assistant planner failed (%s)", type(exc).__name__)
                self.fail(task.id, "planner_failed")
                return
            if not proposals:
                break
            if not isinstance(proposals, (list, tuple)):
                self.fail(task.id, "planner_failed")
                return
            for i, p in enumerate(proposals):
                if task.cancel_requested:
                    break
                if run.calls >= MAX_CALLS or self._monotonic() > deadline:
                    self.fail(task.id, "task_budget_exhausted")
                    return
                self._one(principal, task, view, i, p, observations, run)
                if task.state == "failed":
                    return
            if len(observations) > 4 * MAX_CALLS:
                self.fail(task.id, "task_budget_exhausted")
                return
        with self._lock:
            if task.state == "running":
                task.state = "completed"

    def _one(self, principal: Principal, task: AssistantTask, view: TaskView, i: int, p: Any,
             observations: List[Dict[str, Any]], run: _Run) -> None:
        raw_tool = getattr(p, "tool", None)
        tool = raw_tool if isinstance(raw_tool, str) and raw_tool in KNOWN_TOOLS else UNKNOWN_TOOL
        raw_args = getattr(p, "arguments", None)
        args = copy.deepcopy(raw_args) if isinstance(raw_args, dict) else {}
        self._emit(task, "proposed_action", {"tool": tool})  # never the planner's own string
        code = self._guard(task, tool, args, i, observations)
        if code:
            self._emit(task, "action_refused", {"tool": tool, "code": code})
            self.executor.audit_refusal(principal, tool=tool, arguments=args, code=code, task_id=task.id,
                                        step=view.step)
            observations.append({"seq": len(observations) + 1, "step": view.step, "tool": tool, "arguments": args,
                                 "status": "error", "problem": {"code": code}})
            run.refused += 1
            return
        run.calls += 1
        inv = {"request_id": str(uuid.uuid4()), "protocol_version": MCP_PROTOCOL_VERSION,
               "environment": self.environment, "tool": tool, "arguments": args,
               "idempotency_key": getattr(p, "idempotency_key", None)}
        status, outcome = self.executor.call(principal, inv, correlation_id=task.id, task_id=task.id,
                                             origin="assistant", step=view.step)
        observations.append({"seq": len(observations) + 1, "step": view.step, "arguments": copy.deepcopy(args),
                             **outcome.to_wire(), "tool": tool})
        if outcome.status != "ok":
            code = (outcome.problem or {}).get("code")
            self._emit(task, "action_refused", {"tool": tool, "code": code})
            if code == "processing_restricted":
                # The member deleted or restricted this data after the task read its inputs (or a
                # deletion is pending): nothing more is built from them.
                self.fail(task.id, "processing_restricted")
            return
        content = outcome.structured_content or {}
        if tool == "brandme.catalog.search":
            self._emit(task, "finding", {"count": len(content.get("items", [])),
                                         "unavailable_providers": content.get("unavailable_providers", [])})
        elif tool == "brandme.purchase.request":
            with self._lock:
                task.state = "awaiting_approval"
                self._emit(task, "approval_requested", {"operation_id": content["operation_id"],
                                                        "approval_surface": content["approval_surface"]})
        else:
            self._emit(task, "outcome", {"tool": tool, "result": _summary(content)})

    # -- guards ------------------------------------------------------------------
    def _guard(self, task: AssistantTask, tool: str, args: Dict[str, Any], i: int,
               observations: List[Dict[str, Any]]) -> Optional[str]:
        if task.state == "awaiting_approval":
            return "stopped_for_approval"  # a later proposal in the same batch
        if i >= MAX_PROPOSALS_PER_STEP:
            return "too_many_proposals"
        if tool not in MODE_TOOLS[task.mode]:
            return "tool_not_allowed_in_mode"
        key = (tool, canonical_json(args))
        for o in observations:
            if "request_id" in o and (o.get("tool"), canonical_json(o.get("arguments"))) == key:
                if o.get("status") == "ok" or not (o.get("problem") or {}).get("retryable"):
                    return "duplicate_call"
        refs, totals = _trusted(task, observations)
        if not _provenance_ok(tool, args, refs):
            return "argument_not_from_results"
        ceiling = task.constraints.price_ceiling
        if tool == "brandme.purchase.request" and ceiling is not None:
            total = totals.get(args.get("quote_id"))
            if total is not None and total.currency != ceiling.currency:
                return "quote_currency_differs_from_hint"
            if total is None or total > ceiling:
                return "quote_exceeds_price_ceiling"
        return None

    def _exposed_tools(self, principal: Principal, mode: AssistanceMode) -> Tuple[str, ...]:
        delegation = self.executor.commerce.store.get("delegations", principal.delegation_id or "")
        granted = principal.scopes & (delegation.scopes if delegation is not None else frozenset())
        return tuple(sorted(n for n in MODE_TOOLS[mode]
                            if n in _ADVERTISED and set(_ADVERTISED[n]["_meta"]["brandme/requiredScopes"]) <= granted))

    def _view(self, task: AssistantTask, exposed: Tuple[str, ...], step: int, calls: int, deadline: float) -> TaskView:
        return TaskView(id=task.id, member_id=task.member_id, delegation_id=task.delegation_id, mode=task.mode,
                        goal=task.goal, constraints=task.constraints, request_id=task.request_id,
                        environment=self.environment, tools=exposed, step=step, tool_calls_made=calls,
                        tool_calls_left=MAX_CALLS - calls, deadline=deadline)

    # -- end of run --------------------------------------------------------------
    def _finish(self, task: AssistantTask, planner: Planner, run: _Run, started: float) -> None:
        totals: Dict[str, Any] = {}
        end = getattr(planner, "on_task_end", None)
        if end is not None and run.view is not None:
            try:
                totals = end(run.view, task.state) or {}
            except Exception:
                totals = {}
        code = {"completed": "ok", "awaiting_approval": "awaiting_approval", "cancelled": "cancelled"}.get(task.state)
        if code is None:
            errors = [e.data.get("code") for e in task.events if e.type == "error"]
            code = errors[-1] if errors and isinstance(errors[-1], str) else "runtime_failed"
        label = getattr(planner, "label", None)
        self.run_log.task_end(
            request_id=task.request_id, task_ref=log_ref("task", task.id), member_ref=log_ref("member", task.member_id),
            mode=task.mode.value, planner=label if label in _PLANNER_LABELS else "custom", state=task.state,
            code=code, model_steps=run.steps, tool_calls=run.calls, refused_calls=run.refused,
            duration_ms=max(0, int((self._monotonic() - started) * 1000)),
            tokens_total=_count(totals.get("tokens_total")), cost_micro_usd_total=_count(totals.get("cost_micro_usd_total")))

    def _emit(self, task: AssistantTask, type_: str, data: Dict[str, Any]) -> None:
        with self._lock:
            task.events.append(TaskEvent(len(task.events) + 1, type_, data))


def _count(v: Any) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0


def _str(*parts: Any) -> bool:
    return all(isinstance(p, str) and p for p in parts)


def _trusted(task: AssistantTask, observations: List[Dict[str, Any]]) -> Tuple[Set[tuple], Dict[str, Money]]:
    """Identifiers earlier results vouch for: structural fields of executed, ok observations only.
    Values inside ``untrusted_text`` never count."""
    refs: Set[tuple] = set()
    totals: Dict[str, Money] = {}
    for u in _UUID_RE.findall(task.goal):  # an order the member named; the executor still checks ownership
        refs.add(("goal_operation", u))
        refs.add(("goal_operation", u.lower()))
    for o in observations:
        if "request_id" not in o or o.get("status") != "ok":
            continue
        c = o.get("structured_content") or {}
        tool = o.get("tool")
        if tool == "brandme.catalog.search":
            for item in c.get("items") or []:
                vid, ref = item.get("variant_id"), item.get("source_variant_ref")
                if _str(vid, ref):
                    refs.add(("variant", vid, ref))
                    if _str(item.get("provider_id"), item.get("merchant_id")):
                        refs.add(("merchant", item["provider_id"], item["merchant_id"]))
        elif tool in ("brandme.cart.create", "brandme.cart.update"):
            if _str(c.get("cart_id")):
                refs.add(("cart", c["cart_id"]))
        elif tool == "brandme.checkout.quote":
            q = c.get("quote") or {}
            if _str(q.get("id")):
                refs.add(("quote", q["id"]))
                try:
                    totals[q["id"]] = Money.from_wire(q.get("total"))
                except (MoneyError, TypeError):
                    pass
        elif tool in ("brandme.purchase.request", "brandme.order.status", "brandme.purchase.execute"):
            if _str(c.get("operation_id")):
                refs.add(("operation", c["operation_id"]))
    return refs, totals


def _has(refs: Set[tuple], *ref: Any) -> bool:
    return _str(*ref[1:]) and ref in refs  # a missing or non-string value is never trusted


def _provenance_ok(tool: str, a: Dict[str, Any], refs: Set[tuple]) -> bool:
    def lines_ok() -> bool:
        lines = a.get("lines")
        if not isinstance(lines, list):
            return True  # the executor's schema check rejects it
        return all(isinstance(l, dict) and _has(refs, "variant", l.get("variant_id"), l.get("source_variant_ref"))
                   for l in lines)

    if tool == "brandme.cart.create":
        return _has(refs, "merchant", a.get("provider_id"), a.get("merchant_id")) and lines_ok()
    if tool == "brandme.cart.update":
        return _has(refs, "cart", a.get("cart_id")) and lines_ok()
    if tool == "brandme.checkout.quote":
        return _has(refs, "cart", a.get("cart_id"))
    if tool == "brandme.purchase.request":
        return _has(refs, "quote", a.get("quote_id"))
    if tool == "brandme.purchase.execute":
        # Needs the member's approval id, which only exists after the task stops: never in-task.
        return _has(refs, "operation", a.get("operation_id")) and _has(refs, "approval", a.get("approval_id"))
    if tool == "brandme.order.status":
        return _has(refs, "operation", a.get("operation_id")) or _has(refs, "goal_operation", a.get("operation_id"))
    return True


def _summary(content: Dict[str, Any]) -> Dict[str, Any]:
    keep = ("cart_id", "revision", "operation_id", "state", "display_total", "purchase", "simulation")
    return {k: content[k] for k in keep if k in content}
