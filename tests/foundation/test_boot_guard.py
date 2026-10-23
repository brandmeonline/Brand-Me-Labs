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


def test_guard_returns_the_mode_when_allowed():
    assert guard("orchestrator", env={"BRANDME_MODE": "demo"}).value == "demo"
    assert guard("events_worker", env={"BRANDME_MODE": "production", "ENVIRONMENT": "production"}).value == "production"
