"""Runs assistant tasks off the request thread (dev form; in-process, not durable).

A model-planned task outlives the gateway's domain-call timeout, so the HTTP create answers
202 with the task id and the client follows the task's events. The pool is bounded: when it is
full, ``submit`` raises ``AssistantBusy`` (503, retryable) instead of queueing without limit.
Each job carries the request's context (its correlation id). A job that raises leaves its task
failed with a fixed code, never "running".

Production needs a durable queue (Cloud Tasks or a Pub/Sub worker) with cross-process claim and
cancel; this runner keeps the same contract for the dev composition.
"""

from __future__ import annotations

import contextvars
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from brandme_core.domains.commerce.errors import AssistantBusy
from brandme_core.domains.commerce.principal import Principal

from .runtime import AssistantRuntime, Planner

_log = logging.getLogger("brandme.assistant")


class BackgroundRunner:
    def __init__(self, runtime: AssistantRuntime, *, max_workers: int = 2, max_pending: int = 8):
        self.runtime = runtime
        self.max_pending = max_pending
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="assistant-run")
        self._idle = threading.Condition()
        self._pending = 0  # submitted and not yet finished

    def has_capacity(self) -> bool:
        with self._idle:
            return self._pending < self.max_pending

    def submit(self, principal: Principal, task_id: str, planner: Planner) -> None:
        with self._idle:
            if self._pending >= self.max_pending:
                raise AssistantBusy("the assistant is busy; retry shortly")
            self._pending += 1
        try:
            self._pool.submit(contextvars.copy_context().run, self._job, principal, task_id, planner)
        except BaseException:
            self._done()
            raise

    def drain(self, timeout_s: float) -> bool:
        """Wait until nothing is pending or running (tests). True when idle."""
        with self._idle:
            return self._idle.wait_for(lambda: self._pending == 0, timeout=timeout_s)

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)

    def _job(self, principal: Principal, task_id: str, planner: Planner) -> Any:
        try:
            return self.runtime.run(principal, task_id, planner)
        except Exception as exc:  # the task is marked failed; keep the worker alive, keep the text out
            _log.warning("assistant task failed (%s)", type(exc).__name__)
            self.runtime.fail(task_id, "planner_failed")
            return None
        finally:
            self._done()

    def _done(self) -> None:
        with self._idle:
            self._pending -= 1
            self._idle.notify_all()


TaskRunner = BackgroundRunner  # the name the HTTP layer and earlier tests use
