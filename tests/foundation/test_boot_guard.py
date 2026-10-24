"""In-process boot guard: legacy entry modules refuse strict modes at import (BM-BASE-002).

Before this guard only the compose `preflight` command refused, so an image
CMD or `uvicorn main:app` with BRANDME_MODE=production served a fabricated
`cardano_tx_` hash. These tests start the real entrypoints in subprocesses.

CI gate (production refusal): `python -m pytest tests/foundation/test_boot_guard.py -m production_refusal`
"""
import importlib.util
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from brandme_core.boot import EXIT_REFUSED, BootRefused, guard

REPO = Path(__file__).resolve().parents[2]

# (working directory, import name, guard service name)
ENTRY_MODULES = [
    ("brandme-core/brain", "main", "brain"),
    ("brandme-core/policy", "main", "policy"),
    ("brandme-core/orchestrator", "main", "orchestrator"),
    ("brandme-core/orchestrator", "worker", "orchestrator"),  # what compose serves on :8002
    ("brandme-governance/governance_console", "main", "governance"),
    ("brandme-cube", "src.main", "cube"),
    ("brandme-agents/compliance", "src.main", "compliance"),
    ("brandme-agents/knowledge", "src.main", "knowledge"),
    # brandme-agents/identity also guards at import, but its module cannot import in any mode
    # (pre-existing: ProofType is missing from brandme_core.zk), so it has no local-mode case here.
]
IDS = [f"{d}:{m}" for d, m, _ in ENTRY_MODULES]


def _env(mode):
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
    if mode:
        env["BRANDME_MODE"] = mode
    return env


def _import(workdir, module, mode):
    code = f"import {module}; print('APP', type({module}.app).__name__)"
    return subprocess.run([sys.executable, "-c", code], cwd=REPO / workdir, env=_env(mode),
                          capture_output=True, text=True, timeout=120)


@pytest.mark.production_refusal
@pytest.mark.parametrize("mode", ["production", "sandbox"])
@pytest.mark.parametrize("workdir,module,service", ENTRY_MODULES, ids=IDS)
def test_strict_mode_import_exits_with_refusal(workdir, module, service, mode):
    result = _import(workdir, module, mode)
    assert result.returncode == EXIT_REFUSED, result.stderr
    assert f"[brandme boot] {service}: REFUSED — BRANDME_MODE={mode} refuses to boot; trust-path violations:" in result.stderr
    assert "simulated, not allowed in " + mode in result.stderr
    assert "APP" not in result.stdout
    assert "Traceback" not in result.stderr


@pytest.mark.production_refusal
@pytest.mark.parametrize("workdir,module,service", ENTRY_MODULES, ids=IDS)
def test_missing_mode_import_exits_with_refusal(workdir, module, service):
    result = _import(workdir, module, None)
    assert result.returncode == EXIT_REFUSED, result.stderr
    assert f"[brandme boot] {service}: REFUSED — BRANDME_MODE is not set" in result.stderr
    assert "APP" not in result.stdout


@pytest.mark.parametrize("mode", ["development", "demo"])
@pytest.mark.parametrize("workdir,module,service", ENTRY_MODULES, ids=IDS)
def test_local_mode_import_succeeds(workdir, module, service, mode):
    result = _import(workdir, module, mode)
    assert result.returncode == 0, result.stderr
    assert "APP FastAPI" in result.stdout
    assert "REFUSED" not in result.stderr


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.production_refusal
@pytest.mark.parametrize("workdir,target,service", [
    ("brandme-core/orchestrator", "main:app", "orchestrator"),
    ("brandme-core/orchestrator", "worker:app", "orchestrator"),
    ("brandme-core/brain", "main:app", "brain"),
])
def test_uvicorn_exits_before_binding_in_production(workdir, target, service):
    """The Dockerfile/compose command shape, minus --reload (see brandme_core/boot.py)."""
    port = _free_port()
    result = subprocess.run(
        [sys.executable, "-m", "uvicorn", target, "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO / workdir, env=_env("production"), capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == EXIT_REFUSED, result.stderr
    assert f"[brandme boot] {service}: REFUSED" in result.stderr
    assert "Uvicorn running" not in result.stderr and "Started server process" not in result.stderr
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0, "nothing may listen after a refusal"


@pytest.mark.production_refusal
def test_in_process_import_cannot_produce_an_app(monkeypatch):
    """TestClient(app) needs `app`; a refused import never creates one."""
    monkeypatch.setenv("BRANDME_MODE", "production")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    name = "bm_boot_guard_orchestrator_main"
    spec = importlib.util.spec_from_file_location(name, REPO / "brandme-core/orchestrator/main.py")
    module = importlib.util.module_from_spec(spec)
    with pytest.raises(BootRefused) as exc:
        spec.loader.exec_module(module)
    assert exc.value.code == EXIT_REFUSED
    assert not hasattr(module, "app")
    assert name not in sys.modules


def test_refusal_is_not_swallowed_by_except_exception():
    with pytest.raises(BootRefused) as exc:
        try:
            guard("orchestrator", env={"BRANDME_MODE": "production"})
        except Exception:  # noqa: BLE001 - the point of the test
            pytest.fail("BootRefused must not be an Exception")
    assert isinstance(exc.value.reason, Exception)
    assert "chain.cardano" in str(exc.value)


@pytest.mark.production_refusal
@pytest.mark.parametrize("module,service,network_var", [
    ("brandme_core.read_api", "read_api", "READ_API_NETWORK"),
    ("brandme_core.privacy_exports", "privacy_exports", "EXPORT_NETWORK"),
])
def test_valid_config_on_a_test_network_is_refused_in_production(module, service, network_var):
    """The config validators accept Preprod; the shared inventory refuses it in production (exit 3)."""
    prefix = "READ_API" if service == "read_api" else "EXPORT"
    env = _env("production") | {
        "ENVIRONMENT": "production",
        "SPANNER_PROJECT_ID": "p", "SPANNER_INSTANCE_ID": "i", "SPANNER_DATABASE_ID": "d",
        network_var: "preprod", f"{prefix}_CONTRACT_ADDRESS": "a" * 64,
        "RIGHTS_SERVICE_TOKEN": "r" * 40, "PRIVACY_SERVICE_TOKEN": "p" * 40,
        "PRIVACY_EXPORT_SERVICE_TOKEN": "e" * 40, "EXPORT_BUCKET": "brandme-production-exports-a1",
    }
    result = subprocess.run([sys.executable, "-W", "ignore", "-m", module, "--check"], cwd=REPO, env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == EXIT_REFUSED, (result.stdout, result.stderr)
    assert f"[brandme boot] {service}: REFUSED" in result.stderr
    assert "is sandbox, not allowed in production" in result.stderr
    assert "ready" not in result.stdout


def test_guard_returns_the_mode_when_allowed():
    assert guard("orchestrator", env={"BRANDME_MODE": "demo"}).value == "demo"
    assert guard("events_worker", env={"BRANDME_MODE": "production", "ENVIRONMENT": "production"}).value == "production"
