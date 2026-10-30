"""Model spend ledger: reserve before a model call, settle after it (ch.03 §11; BM-OPS-005).

Every model call reserves an upper bound of its tokens and cost against the task, the member's
day and the environment's day *before* any I/O, so a cap is never exceeded by a call already in
flight. The call is then settled at actual usage, at the reservation when the provider may have
billed without saying how much (timeout, 5xx), or released when it certainly did not.

``InMemoryCostLedger`` is the dev form. Production needs the same three steps durably: a Spanner
reserve transaction that commits before the call, and a separate settle transaction after it.
The model is never called inside a transaction. Keys are keyed refs, never raw ids.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Protocol, Tuple

COST_BASES = ("usage", "reserved_upper_bound", "none")


@dataclass(frozen=True)
class Reservation:
    task_ref: str
    member_ref: str
    environment: str
    step: int
    day: str  # UTC day bucket, YYYY-MM-DD
    tokens: int
    cost_micro_usd: int


class BudgetRefused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class CostLedger(Protocol):
    def reserve(self, *, task_ref: str, member_ref: str, environment: str, step: int, tokens: int,
                cost_micro_usd: int, budget: Any) -> Reservation: ...

    def settle(self, r: Reservation, *, tokens: int, cost_micro_usd: int, basis: str) -> None: ...

    def release(self, r: Reservation) -> None: ...

    def task_totals(self, task_ref: str) -> Tuple[int, int]: ...

    def close_task(self, task_ref: str) -> Dict[str, int]: ...


class InMemoryCostLedger:
    """One lock; committed = settled + reserved. ``budget`` is a ``ModelBudget``."""

    def __init__(self, *, wall: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self._wall = wall
        self._lock = threading.Lock()
        self._steps: Dict[Tuple[str, int], Tuple[Reservation, str]] = {}  # -> (reservation, reserved|settled|released)
        self._task: Dict[str, list] = {}  # task_ref -> [tokens, cost]
        self._member_day: Dict[Tuple[str, str], list] = {}  # (member_ref, day) -> [tokens, cost]
        self._env_day: Dict[Tuple[str, str], int] = {}  # (environment, day) -> cost

    def reserve(self, *, task_ref: str, member_ref: str, environment: str, step: int, tokens: int,
                cost_micro_usd: int, budget: Any) -> Reservation:
        day = self._wall().astimezone(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            self._prune(day)
            prior = self._steps.get((task_ref, step))
            if prior is not None:
                if prior[1] == "reserved":
                    return prior[0]  # the same step asking again: one reservation, not two
                raise BudgetRefused("model_step_replayed")
            task = self._task.get(task_ref, [0, 0])
            if task[0] + tokens > budget.max_task_tokens:
                raise BudgetRefused("model_token_budget_exhausted")
            if task[1] + cost_micro_usd > budget.max_task_cost_micro_usd:
                raise BudgetRefused("model_cost_budget_exhausted")
            member = self._member_day.get((member_ref, day), [0, 0])
            env_cost = self._env_day.get((environment, day), 0)
            if (member[0] + tokens > budget.member_daily_tokens
                    or member[1] + cost_micro_usd > budget.member_daily_cost_micro_usd
                    or env_cost + cost_micro_usd > budget.environment_daily_cost_micro_usd):
                raise BudgetRefused("model_quota_exhausted")
            r = Reservation(task_ref, member_ref, environment, step, day, tokens, cost_micro_usd)
            self._apply(r, tokens, cost_micro_usd)
            self._steps[(task_ref, step)] = (r, "reserved")
            return r

    def settle(self, r: Reservation, *, tokens: int, cost_micro_usd: int, basis: str) -> None:
        if basis not in COST_BASES:
            raise ValueError("unknown cost basis")
        with self._lock:
            if self._steps.get((r.task_ref, r.step), (None, ""))[1] != "reserved":
                return
            self._apply(r, tokens - r.tokens, cost_micro_usd - r.cost_micro_usd)
            self._steps[(r.task_ref, r.step)] = (r, "settled")

    def release(self, r: Reservation) -> None:
        with self._lock:
            if self._steps.get((r.task_ref, r.step), (None, ""))[1] != "reserved":
                return
            self._apply(r, -r.tokens, -r.cost_micro_usd)
            self._steps[(r.task_ref, r.step)] = (r, "released")

    def task_totals(self, task_ref: str) -> Tuple[int, int]:
        with self._lock:
            tokens, cost = self._task.get(task_ref, [0, 0])
            return tokens, cost

    def close_task(self, task_ref: str) -> Dict[str, int]:
        """Totals for the task's end-of-run log line; per-step rows are dropped (daily totals stay)."""
        with self._lock:
            tokens, cost = self._task.pop(task_ref, [0, 0])
            for key in [k for k in self._steps if k[0] == task_ref]:
                del self._steps[key]
            return {"tokens_total": tokens, "cost_micro_usd_total": cost}

    # -- internals (lock held) ----------------------------------------------------
    def _apply(self, r: Reservation, tokens: int, cost: int) -> None:
        task = self._task.setdefault(r.task_ref, [0, 0])
        task[0] += tokens
        task[1] += cost
        member = self._member_day.setdefault((r.member_ref, r.day), [0, 0])
        member[0] += tokens
        member[1] += cost
        self._env_day[(r.environment, r.day)] = self._env_day.get((r.environment, r.day), 0) + cost

    def _prune(self, today: str) -> None:
        cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=2)).strftime("%Y-%m-%d")
        for key in [k for k in self._member_day if k[1] < cutoff]:
            del self._member_day[key]
        for key in [k for k in self._env_day if k[1] < cutoff]:
            del self._env_day[key]
