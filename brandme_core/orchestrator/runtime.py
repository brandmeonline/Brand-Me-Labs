"""Structured assistant task runtime.

The planner (deterministic, or a provider-neutral structured-output model
adapter) only *proposes* typed tool calls. The runtime decides what runs:

* a per-mode tool allowlist intersected with the principal's scopes;
* every call goes through ``McpToolExecutor._dispatch`` with the task's
  authenticated principal — identical policy to external MCP clients;
* tool results are passed back to the planner as data; text inside them can
  never add tools, scopes or approvals;
* per-task call and wall-clock budgets; cancellation stops new side effects.

Task events expose goals, findings, proposed actions, refusals, approval
requests and outcomes — not model reasoning.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple

from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.domains.commerce.principal import Principal
from brandme_core.mcp.authz import MCP_PROTOCOL_VERSION
from brandme_core.mcp.tools import McpToolExecutor

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
        self._lock = threading.Lock()

    def create(self, principal: Principal, goal: str, mode: AssistanceMode) -> AssistantTask:
        if principal.environment != self.environment:
            raise PermissionError("environment mismatch")
        task = AssistantTask(str(uuid.uuid4()), principal.member_id, principal.delegation_id, mode, goal[:1000])
        self._emit(task, "goal", {"goal": task.goal, "mode": mode.value})
        with self._lock:
            self._tasks[task.id] = task
        return task

    def get(self, principal: Principal, task_id: str) -> AssistantTask:
        task = self._tasks.get(task_id)
        if task is None or task.member_id != principal.member_id:
            raise KeyError("task not found")
        return task

    def cancel(self, principal: Principal, task_id: str) -> AssistantTask:
        task = self.get(principal, task_id)
        task.cancel_requested = True
        return task

    def events_after(self, principal: Principal, task_id: str, after: Optional[int]) -> List[TaskEvent]:
        return [e for e in self.get(principal, task_id).events if after is None or e.seq > after]

    def run(self, principal: Principal, task_id: str, planner: Planner) -> AssistantTask:
        task = self.get(principal, task_id)
        if principal.delegation_id != task.delegation_id:
            raise PermissionError("task bound to a different delegation")
        task.state = "running"
        allowed = MODE_TOOLS[task.mode]
        observations: List[Dict[str, Any]] = []
        calls, started = 0, time.monotonic()
        while True:
            if task.cancel_requested:
                task.state = "cancelled"
                self._emit(task, "cancelled", {"detail": "No new actions will be taken; sent actions keep reconciling."})
                return task
            proposals = planner.next_calls(task, observations)
            if not proposals:
                break
            for p in proposals:
                if calls >= MAX_CALLS or time.monotonic() - started > MAX_SECONDS:
                    task.state = "failed"
                    self._emit(task, "error", {"code": "task_budget_exhausted"})
                    return task
                if task.cancel_requested:
                    break
                self._emit(task, "proposed_action", {"tool": p.tool})
                if p.tool not in allowed:
                    self._emit(task, "action_refused", {"tool": p.tool, "code": "tool_not_allowed_in_mode"})
                    observations.append({"tool": p.tool, "status": "error", "problem": {"code": "tool_not_allowed_in_mode"}})
                    continue
                calls += 1
                inv = {"request_id": str(uuid.uuid4()), "protocol_version": MCP_PROTOCOL_VERSION,
                       "environment": self.environment, "tool": p.tool, "arguments": p.arguments,
                       "idempotency_key": p.idempotency_key}
                status, outcome = self.executor._dispatch(principal, inv)
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
