"""LIVE: assistant tasks planned by the real Anthropic API (dev key), executed against the simulator.

Runs only when ``BRANDME_DEV_ANTHROPIC_API_KEY`` is set; otherwise every test is skipped and must
be reported ``not_run``, never ``passed``. Each test spends a few thousand tokens. The provider is
the deterministic Demo Atelier on the simulated payment rail: no real order, payment or retailer.

The environment is built here, by the test: the app reads only Brand.Me variables, so this
container's agent proxy and CA bundle are passed explicitly as ``BRANDME_ASSISTANT_EGRESS_PROXY``
and ``BRANDME_ASSISTANT_CA_BUNDLE``. The app itself never reads ``HTTPS_PROXY``.
"""

import json
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("BRANDME_DEV_ANTHROPIC_API_KEY"),
                                reason="not_run: the model run needs BRANDME_DEV_ANTHROPIC_API_KEY, which is absent")

RESEARCH_TOOLS = {"brandme.catalog.search", "brandme.order.status"}


def _env():
    env = {"BRANDME_MODE": "development", "BRANDME_ASSISTANT_PLANNER": "anthropic",
           "BRANDME_DEV_ANTHROPIC_API_KEY": os.environ["BRANDME_DEV_ANTHROPIC_API_KEY"]}
    if os.environ.get("HTTPS_PROXY"):
        env["BRANDME_ASSISTANT_EGRESS_PROXY"] = os.environ["HTTPS_PROXY"]
    if os.environ.get("SSL_CERT_FILE"):
        env["BRANDME_ASSISTANT_CA_BUNDLE"] = os.environ["SSL_CERT_FILE"]
    return env


def _compose(w):
    from brandme_core.mcp.authz import ExecutorAssertionVerifier
    from brandme_core.orchestrator.composition import compose_assistant
    from brandme_core.orchestrator.runlog import MemoryRunLog
    log = MemoryRunLog(strict=True)
    audit = []
    wiring = compose_assistant(env=_env(), commerce=w.svc, registry=w.registry, run_log=log,
                               verifier=ExecutorAssertionVerifier(gateway_issuer="gw", keys={}, environment="development"))
    sink = wiring.executor.audit
    wiring.executor.audit = lambda r: (audit.append(r), sink(r))
    return wiring, log, audit


def _summary(task, log, audit):
    """Counts and codes only: no goal, arguments or provider text."""
    calls = log.events("assistant.model_call")
    return json.dumps({"state": task.state, "events": [e.type for e in task.events],
                       "audit": [(r["tool"], r["status"], r["code"]) for r in audit],
                       "model_calls": [(l["code"], l["input_tokens"], l["output_tokens"], l["cost_micro_usd"])
                                       for l in calls]})


def _check_lines(log):
    key = os.environ["BRANDME_DEV_ANTHROPIC_API_KEY"]
    text = json.dumps(log.lines)
    assert key not in text
    for line in log.events("assistant.model_call"):
        assert line["code"] == "ok" and line["input_tokens"] > 0
        assert 0 < line["cost_micro_usd"] <= line["reserved_cost_micro_usd"]
        assert line["model_served"].startswith("claude-opus-5-5")
    return text


def test_live_research_task_against_demo_atelier():
    from brandme_core.domains.commerce.delegation import AssistanceMode
    from tests.fixtures.commerce.harness import world
    w = world()
    d, ag = w.delegate(AssistanceMode.RESEARCH)
    wiring, log, audit = _compose(w)
    try:
        rt = wiring.runtime
        task = rt.run(ag, rt.create(ag, "Find me a linen overshirt in size M", AssistanceMode.RESEARCH).id,
                      wiring.planner_factory())
        print(_summary(task, log, audit))
        assert task.state == "completed", [e.data for e in task.events if e.type == "error"]
        assert {r["tool"] for r in audit} <= RESEARCH_TOOLS
        assert any(r["tool"] == "brandme.catalog.search" and r["status"] == "ok" for r in audit)
        assert w.store.rows("carts") == [] and w.provider.submit_calls == []
        assert "linen" not in _check_lines(log)
    finally:
        wiring.close()


def test_live_prepare_task_stops_at_member_approval():
    from brandme_core.domains.commerce.delegation import AssistanceMode
    from tests.fixtures.commerce.harness import world
    w = world()
    d, ag = w.delegate(AssistanceMode.PREPARE)
    wiring, log, audit = _compose(w)
    try:
        rt = wiring.runtime
        task = rt.run(ag, rt.create(ag, "Prepare a linen overshirt in size M for me to approve",
                                    AssistanceMode.PREPARE).id, wiring.planner_factory())
        print(_summary(task, log, audit))
        assert task.state in ("awaiting_approval", "completed"), [e.data for e in task.events if e.type == "error"]
        assert w.provider.submit_calls == []
        _check_lines(log)
        if task.state != "awaiting_approval":
            pytest.skip("not_run: the model finished before asking for approval (reported, not passed)")
        ok = [r["tool"] for r in audit if r["status"] == "ok"]
        assert ok[-3:] == ["brandme.cart.create", "brandme.checkout.quote", "brandme.purchase.request"]
    finally:
        wiring.close()


def test_live_buy_mode_prepared_by_model_then_member_approves():
    from brandme_core.domains.commerce.delegation import AssistanceMode
    from brandme_core.mcp.authz import MCP_PROTOCOL_VERSION
    from tests.fixtures.commerce.harness import limits, world
    w = world()
    d, ag = w.delegate(AssistanceMode.BUY_WITHIN_RULES, limits())
    wiring, log, audit = _compose(w)
    try:
        rt = wiring.runtime
        task = rt.run(ag, rt.create(ag, "Buy me a linen overshirt in size M", AssistanceMode.BUY_WITHIN_RULES).id,
                      wiring.planner_factory())
        print(_summary(task, log, audit))
        _check_lines(log)
        if task.state != "awaiting_approval":
            pytest.skip("not_run: the model did not reach the approval request (reported, not passed)")
        model_calls = len(log.events("assistant.model_call"))
        op_id = next(e.data["operation_id"] for e in task.events if e.type == "approval_requested")
        approval = w.approve(w.svc.get_operation(w.member, op_id))  # the member, on the trusted surface
        inv = {"request_id": str(uuid.uuid4()), "protocol_version": MCP_PROTOCOL_VERSION, "environment": "development",
               "tool": "brandme.purchase.execute", "arguments": {"operation_id": op_id, "approval_id": approval.id},
               "idempotency_key": "live-buy-exec-000001"}
        status, outcome = wiring.executor.call(ag, inv, origin="assistant", task_id=task.id)
        assert status in (200, 202) and outcome.structured_content["state"] in ("accepted", "submitting",
                                                                                 "outcome_unknown")
        assert len(w.provider.submit_calls) == 1  # simulated rail: no money moves
        assert len(log.events("assistant.model_call")) == model_calls  # no model request after approval
    finally:
        wiring.close()
