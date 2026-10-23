"""Structured assistant task runtime.

The planner (deterministic, or a provider-neutral structured-output model
adapter) only *proposes* typed tool calls. The runtime decides what runs:

* a per-mode tool allowlist intersected with the principal's scopes;
* every call goes through ``McpToolExecutor.call`` with the task's
  authenticated principal — the same validation, policy and audit record as
  external MCP clients, correlated by the task id;
* tool results are passed back to the planner as data; text inside them can
  never add tools, scopes or approvals;
* per-task call and wall-clock budgets; cancellation stops new side effects.

Task events expose goals, findings, proposed actions, refusals, approval
requests and outcomes — not model reasoning.
"""

from __future__ import annotations

import contextvars
import hashlib
import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple

from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.domains.commerce.errors import CommerceError
from brandme_core.domains.commerce.money import Money
from brandme_core.domains.commerce.principal import Principal, is_first_party
from brandme_core.mcp.authz import MCP_PROTOCOL_VERSION
from brandme_core.mcp.tools import McpToolExecutor, _contains_payment_credential

MODE_TOOLS = {
    AssistanceMode.RESEARCH: frozenset({"brandme.catalog.search", "brandme.order.status"}),
    AssistanceMode.PREPARE: frozenset({"brandme.catalog.search", "brandme.order.status", "brandme.cart.create",
                                       "brandme.cart.update", "brandme.checkout.quote", "brandme.purchase.request"}),
    AssistanceMode.BUY_WITHIN_RULES: frozenset({"brandme.catalog.search", "brandme.order.status",
                                                "brandme.cart.create", "brandme.cart.update",
                                                "brandme.checkout.quote", "brandme.purchase.request",
                                                "brandme.purchase.execute"}),
}
MAX_CALLS = 12
MAX_SECONDS = 30.0
_KNOWN_TOOLS = frozenset(t["name"] for t in McpToolExecutor.list_tools()["tools"])
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


class Planner(Protocol):
    def next_calls(self, task: AssistantTask, observations: List[Dict[str, Any]]) -> List[ProposedCall]: ...


class DeterministicPlanner:
    """No-AI planner: search → (prepare) cart for the top in-stock result → quote → approval request."""

    def next_calls(self, task: AssistantTask, observations: List[Dict[str, Any]]) -> List[ProposedCall]:
        if not observations:
            return [ProposedCall("brandme.catalog.search", {"query": task.goal[:200], "limit": 6})]
        last = observations[-1]
        if task.mode is AssistanceMode.RESEARCH or last.get("status") != "ok":
            return []
        content = last.get("structured_content") or {}
        tool = last.get("tool")
        if tool == "brandme.catalog.search":
            items = [i for i in content.get("items", []) if i.get("availability") == "in_stock" and i.get("variant_id")]
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


class AssistantRuntime:
    def __init__(self, executor: McpToolExecutor, *, environment: str):
        self.executor = executor
        self.environment = environment
        self._tasks: Dict[str, AssistantTask] = {}
        # (member, delegation, idempotency key) -> (request digest, task id): a retried create is the same task.
        self._by_key: Dict[Tuple[str, str, str], Tuple[str, str]] = {}
        self._lock = threading.Lock()

    def create(self, principal: Principal, goal: str, mode: AssistanceMode, *,
               idempotency_key: Optional[str] = None) -> AssistantTask:
        """Create a task. With an ``idempotency_key``, a retry returns the original task (``replayed``)."""
        if principal.environment != self.environment:
            raise PermissionError("environment mismatch")
        principal = self._bind(principal)
        delegation = self.executor.commerce.store.get("delegations", principal.delegation_id)
        if delegation.mode is not mode:
            raise PermissionError("task mode differs from the delegation's mode")
        if _contains_payment_credential(goal):
            # Card data never enters task events, logs or a model prompt (ch.05 §6, BM-COM-018).
            raise PermissionError("remove payment card details from the request")
        digest = hashlib.sha256(f"{mode.value}\n{goal[:1000]}".encode()).hexdigest()
        slot = (principal.member_id, principal.delegation_id, idempotency_key) if idempotency_key else None
        with self._lock:
            if slot and slot in self._by_key:
                prior_digest, task_id = self._by_key[slot]
                if prior_digest != digest:
                    raise IdempotencyReuse("idempotency key reused for a different task")
                return self._tasks[task_id]
            task = AssistantTask(str(uuid.uuid4()), principal.member_id, principal.delegation_id, mode, goal[:1000])
            self._emit(task, "goal", {"goal": task.goal, "mode": mode.value})
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

    def run(self, principal: Principal, task_id: str, planner: Planner) -> AssistantTask:
        principal = self._bind(principal)
        task = self.get(principal, task_id)
        if principal.delegation_id != task.delegation_id:
            raise PermissionError("task bound to a different delegation")
        with self._lock:  # claim it: a task runs once, however many times its create is retried
            if task.state != "queued":
                return task
            task.state = "running"
        try:
            return self._loop(principal, task, planner)
        except BaseException:
            # Never leave a task "running" that nothing is running: it could not be retried or cancelled.
            if task.state in ("running", "queued"):
                task.state = "failed"
                self._emit(task, "error", {"code": "runtime_failed"})
            raise
        finally:
            close = getattr(planner, "close", None)
            if close is not None:
                close(task.id)

    def _loop(self, principal: Principal, task: AssistantTask, planner: Planner) -> AssistantTask:
        allowed = MODE_TOOLS[task.mode]
        max_seconds = float(getattr(planner, "max_seconds", MAX_SECONDS))
        observations: List[Dict[str, Any]] = []
        calls, started = 0, time.monotonic()
        while True:
            if task.cancel_requested:
                task.state = "cancelled"
                self._emit(task, "cancelled", {"detail": "No new actions will be taken; sent actions keep reconciling."})
                return task
            if task.state == "awaiting_approval":
                break  # the member decides next; nothing more to plan
            try:
                proposals = planner.next_calls(task, observations)
            except PlannerError as exc:
                task.state = "failed"
                self._emit(task, "error", {"code": exc.code})
                return task
            except Exception:  # a planner bug: fixed code, no exception text in member events
                _log.exception("assistant planner failed")
                task.state = "failed"
                self._emit(task, "error", {"code": "planner_failed"})
                return task
            if not proposals:
                break
            for p in proposals:
                if calls >= MAX_CALLS or time.monotonic() - started > max_seconds:
                    task.state = "failed"
                    self._emit(task, "error", {"code": "task_budget_exhausted"})
                    return task
                if task.cancel_requested or task.state == "awaiting_approval":
                    break  # the rest of the batch never runs; the planner reports it as not executed
                shown = p.tool if p.tool in _KNOWN_TOOLS else "unknown_tool"  # no model text in events
                self._emit(task, "proposed_action", {"tool": shown})
                if p.tool not in allowed:
                    self._emit(task, "action_refused", {"tool": shown, "code": "tool_not_allowed_in_mode"})
                    observations.append({"tool": p.tool, "status": "error", "problem": {"code": "tool_not_allowed_in_mode"}})
                    continue
                calls += 1
                inv = {"request_id": str(uuid.uuid4()), "protocol_version": MCP_PROTOCOL_VERSION,
                       "environment": self.environment, "tool": p.tool, "arguments": p.arguments,
                       "idempotency_key": p.idempotency_key}
                status, outcome = self.executor.call(principal, inv, correlation_id=task.id, task_id=task.id,
                                                     origin="assistant")
                wire = outcome.to_wire()
                observations.append(wire)
                if outcome.status != "ok":
                    self._emit(task, "action_refused", {"tool": p.tool, "code": outcome.problem.get("code")})
                    continue
                content = outcome.structured_content or {}
                if p.tool == "brandme.catalog.search":
                    self._emit(task, "finding", {"count": len(content.get("items", [])),
                                                 "unavailable_providers": content.get("unavailable_providers", [])})
                elif p.tool == "brandme.purchase.request":
                    task.state = "awaiting_approval"
                    self._emit(task, "approval_requested", {"operation_id": content["operation_id"],
                                                            "approval_surface": content["approval_surface"]})
                else:
                    self._emit(task, "outcome", {"tool": p.tool, "result": _summary(content)})
            if len(observations) > 4 * MAX_CALLS:
                break
        if task.state == "running":
            task.state = "completed"
        return task

    def _emit(self, task: AssistantTask, type_: str, data: Dict[str, Any]) -> None:
        task.events.append(TaskEvent(len(task.events) + 1, type_, data))


def _summary(content: Dict[str, Any]) -> Dict[str, Any]:
    keep = ("cart_id", "revision", "operation_id", "state", "display_total", "purchase", "simulation")
    return {k: content[k] for k in keep if k in content}


class TaskRunner:
    """Runs tasks off the request thread for planners that take longer than an HTTP request
    (a model run outlives the gateway's domain-call timeout). The caller answers 202 and the
    client follows the task's events. Context (the request correlation id) goes with the task."""

    def __init__(self, runtime: AssistantRuntime, *, max_workers: int = 2):
        self.runtime = runtime
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="assistant-task")

    def submit(self, principal: Principal, task_id: str, planner: Planner) -> Future:
        return self._pool.submit(contextvars.copy_context().run, self._run, principal, task_id, planner)

    def _run(self, principal: Principal, task_id: str, planner: Planner) -> Optional[AssistantTask]:
        try:
            return self.runtime.run(principal, task_id, planner)
        except Exception:  # the task is already marked failed; keep the worker alive
            _log.exception("assistant task failed")
            return None

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)
