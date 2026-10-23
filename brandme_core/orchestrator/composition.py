"""Startup composition for Brand.Me's assistant: planner, executor, runtime, runner, run log.

Decided once at startup from configuration (``model_planner.planner_from_env``); a bad choice
refuses to boot with a fixed ``PlannerConfigError`` code. The executor's audit records go to the
run log as ``mcp.tool_call`` lines, so tool calls and model calls join on the same keyed refs.
A model planner runs tasks on a ``BackgroundRunner``; the deterministic one runs inline.

Without a dev key the Anthropic SDK is never imported (BM-ONB-007).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from brandme_core.mcp import refs
from brandme_core.mcp.authz import ExecutorAssertionVerifier
from brandme_core.mcp.tools import McpToolExecutor

from .background import BackgroundRunner
from .model_adapter import PlannerConfigError
from .model_planner import PLANNER_ENV, ModelPlanner, planner_from_env
from .runlog import JsonLineRunLog, RunLog
from .runtime import AssistantRuntime, Planner


@dataclass(frozen=True)
class AssistantWiring:
    runtime: AssistantRuntime
    executor: McpToolExecutor
    planner: Planner
    background: Optional[BackgroundRunner]
    run_log: RunLog

    def planner_factory(self) -> Planner:
        return self.planner  # one shared, stateless planner

    def close(self) -> None:
        if self.background is not None:
            self.background.shutdown(wait=False)
        close = getattr(self.planner, "close", None)
        if close is not None:
            close()


def compose_assistant(*, env: Mapping[str, str], commerce: Any, registry: Any, verifier: ExecutorAssertionVerifier,
                      run_log: Optional[RunLog] = None, transport: Any = None,
                      monotonic: Callable[[], float] = time.monotonic) -> AssistantWiring:
    try:
        refs.configure_from_env(env)
    except refs.LogRefKeyError as exc:
        raise PlannerConfigError(exc.code) from None
    run_log = run_log if run_log is not None else JsonLineRunLog(environment=commerce.environment)
    planner = planner_from_env(env, run_log=run_log, transport=transport, clock=monotonic)
    model = planner if isinstance(planner, ModelPlanner) else None
    if model is not None and model.environment != commerce.environment:
        raise PlannerConfigError("environment_mismatch")
    executor = McpToolExecutor(commerce=commerce, registry=registry, verifier=verifier, audit=run_log.tool_call)
    runtime = AssistantRuntime(executor, environment=commerce.environment, run_log=run_log, monotonic=monotonic)
    background = BackgroundRunner(runtime) if getattr(planner, "runs_in_background", False) else None
    adapter = model.adapter if model is not None else None
    run_log.planner_selected(
        planner=getattr(planner, "label", "custom"), provider=adapter.provider if adapter else None,
        model=adapter.model if adapter else None, effort=adapter.effort if adapter else None,
        sdk_version=adapter.sdk_version if adapter else None, api_version=adapter.api_version if adapter else None,
        reason="configured" if (env.get(PLANNER_ENV) or model is not None) else "default")
    return AssistantWiring(runtime, executor, planner, background, run_log)
