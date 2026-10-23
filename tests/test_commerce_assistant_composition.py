"""Assistant startup composition: planner choice, run-log wiring, background runner, refusals to boot."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.mcp.authz import ExecutorAssertionVerifier
from brandme_core.orchestrator import DeterministicPlanner
from brandme_core.orchestrator.composition import compose_assistant
from brandme_core.orchestrator.model_adapter import PlannerConfigError
from brandme_core.orchestrator.runlog import MemoryRunLog
from tests.fixtures.commerce.harness import world

REPO = Path(__file__).resolve().parents[1]
KEY = "sk-ant-api03-" + "x" * 40  # fake


def _verifier():
    return ExecutorAssertionVerifier(gateway_issuer="gw", keys={}, environment="development")


def _compose(env, w=None, **kw):
    w = w or world()
    log = kw.pop("run_log", None) or MemoryRunLog(strict=True)
    return w, log, compose_assistant(env=env, commerce=w.svc, registry=w.registry, verifier=_verifier(), run_log=log,
                                     **kw)


def test_compose_deterministic_default_and_sdk_not_imported():
    code = ("import sys\n"
            "from brandme_core.mcp.authz import ExecutorAssertionVerifier\n"
            "from brandme_core.orchestrator.composition import compose_assistant\n"
            "from brandme_core.orchestrator.runlog import MemoryRunLog\n"
            "from tests.fixtures.commerce.harness import world\n"
            "w = world()\n"
            "c = compose_assistant(env={'BRANDME_MODE': 'development'}, commerce=w.svc, registry=w.registry,\n"
            "    verifier=ExecutorAssertionVerifier(gateway_issuer='gw', keys={}, environment='development'),\n"
            "    run_log=MemoryRunLog())\n"
            "print(type(c.planner).__name__, c.background, 'anthropic' in sys.modules)\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=120)
    assert out.stdout.strip() == "DeterministicPlanner None False", out.stderr[-800:]
    w, log, c = _compose({"BRANDME_MODE": "development"})
    assert isinstance(c.planner, DeterministicPlanner) and c.planner_factory() is c.planner
    selected = log.events("assistant.planner_selected")
    assert len(selected) == 1 and selected[0]["planner"] == "deterministic" and selected[0]["reason"] == "default"


def test_compose_wires_audit_to_run_log_and_background_for_model():
    pytest.importorskip("anthropic")
    from tests.fixtures.commerce.fake_anthropic import FakeMessagesApi, call, done
    import httpx
    api = FakeMessagesApi([call(1, "brandme.catalog.search", {"query": "linen"}), done()])
    w, log, c = _compose({"BRANDME_MODE": "development", "BRANDME_ASSISTANT_PLANNER": "anthropic",
                          "BRANDME_DEV_ANTHROPIC_API_KEY": KEY}, transport=httpx.MockTransport(api))
    try:
        assert c.background is not None and c.planner.label == "model:anthropic"
        d, ag = w.delegate(AssistanceMode.RESEARCH)
        task = c.runtime.create(ag, "linen", AssistanceMode.RESEARCH, planner_label=c.planner.label)
        assert c.runtime.mark_submitted(task.id)
        c.background.submit(ag, task.id, c.planner_factory())
        assert c.background.drain(10) and task.state == "completed"
        tool = log.events("mcp.tool_call")
        model = log.events("assistant.model_call")
        assert len(tool) == 1 and len(model) == 2 and tool[0]["task_ref"] == model[0]["task_ref"]
        assert log.events("assistant.task_end")[0]["planner"] == "model:anthropic"
        sel = log.events("assistant.planner_selected")[0]
        assert (sel["provider"], sel["model"], sel["effort"], sel["reason"]) == ("anthropic", "claude-opus-5-5",
                                                                                 "medium", "configured")
    finally:
        c.close()


def test_dev_key_outside_dev_refuses_boot():
    for env, code in (({"BRANDME_MODE": "production", "BRANDME_ASSISTANT_PLANNER": "anthropic",
                        "BRANDME_DEV_ANTHROPIC_API_KEY": KEY}, "model_planner_dev_only"),
                      ({"BRANDME_DEV_ANTHROPIC_API_KEY": KEY}, "mode_required"),
                      ({"BRANDME_MODE": "development", "BRANDME_LOG_REF_KEY": "short"}, "log_ref_key_invalid")):
        with pytest.raises(PlannerConfigError) as e:
            _compose(env)
        assert e.value.code == code and KEY not in str(e.value)


def test_planner_selected_line_has_no_secret():
    pytest.importorskip("anthropic")
    import httpx
    from tests.fixtures.commerce.fake_anthropic import FakeMessagesApi
    w, log, c = _compose({"BRANDME_MODE": "development", "BRANDME_DEV_ANTHROPIC_API_KEY": KEY,
                          "BRANDME_ASSISTANT_EGRESS_PROXY": "http://user:proxy-secret@proxy.invalid:3128"},
                         transport=httpx.MockTransport(FakeMessagesApi([])))
    text = json.dumps(log.lines)
    assert KEY not in text and "proxy-secret" not in text and "proxy.invalid" not in text
    assert log.events("assistant.planner_selected")[0]["sdk_version"] == "0.125.0"
    c.close()


def test_environment_mismatch_refuses_boot():
    pytest.importorskip("anthropic")
    with pytest.raises(PlannerConfigError) as e:
        _compose({"BRANDME_MODE": "demo", "BRANDME_DEV_ANTHROPIC_API_KEY": KEY}, w=world("development"))
    assert e.value.code == "environment_mismatch"
