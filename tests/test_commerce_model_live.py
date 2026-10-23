"""LIVE: an assistant task planned by the real Anthropic API (dev key), executed against the simulator.

Runs only when ``BRANDME_DEV_ANTHROPIC_API_KEY`` is set; otherwise it is skipped and must be
reported ``not_run``, never ``passed``. It spends a few thousand tokens. The provider is the
deterministic Demo Atelier, so no order, payment or retailer is involved.
"""

import json
import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("BRANDME_DEV_ANTHROPIC_API_KEY"),
                                reason="BRANDME_DEV_ANTHROPIC_API_KEY not set: live model run not_run")


def test_research_task_planned_by_the_live_model():
    from brandme_core.domains.commerce.delegation import AssistanceMode
    from brandme_core.mcp.authz import ExecutorAssertionVerifier
    from brandme_core.mcp.tools import McpToolExecutor
    from brandme_core.orchestrator import AssistantRuntime
    from brandme_core.orchestrator.model_planner import ModelPlanner, planner_from_env
    from tests.fixtures.commerce.harness import world

    w = world()
    d, ag = w.delegate(AssistanceMode.RESEARCH)
    audit, logs = [], []
    rt = AssistantRuntime(McpToolExecutor(commerce=w.svc, registry=w.registry, audit=audit.append,
                                          verifier=ExecutorAssertionVerifier(gateway_issuer="gw", keys={},
                                                                             environment="development")),
                          environment="development")
    planner = planner_from_env({"BRANDME_DEV_ANTHROPIC_API_KEY": os.environ["BRANDME_DEV_ANTHROPIC_API_KEY"],
                                "BRANDME_MODE": "development"}, log=logs.append)
    assert isinstance(planner, ModelPlanner)
    task = rt.run(ag, rt.create(ag, "Find me a linen overshirt in size M", AssistanceMode.RESEARCH).id, planner)
    print(json.dumps({"state": task.state, "events": [e.type for e in task.events], "audit": audit, "logs": logs}))
    assert task.state == "completed", [e.data for e in task.events if e.type == "error"]
    assert any(r["tool"] == "brandme.catalog.search" and r["status"] == "ok" for r in audit)
    assert all(r["tool"] in ("brandme.catalog.search", "brandme.order.status") for r in audit)
    assert w.store.rows("carts") == [] and w.provider.submit_calls == []
    assert logs and all(l["code"] == "ok" and l["input_tokens"] > 0 for l in logs)
    assert "linen" not in json.dumps(logs)
