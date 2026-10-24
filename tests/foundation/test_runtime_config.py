"""Runtime env-contract tests for the ported fail-closed config.

Lux has no dedicated test module for `services/runtime/config.py` — its
coverage is incidental, via `tests/services/runtime/test_runtime.py`. The
port retargeted the whole env-var inventory to Brand.Me (Spanner/Firestore,
ZK/Midnight, the cube_projector role), so these are new tests written against
the ported behavior rather than carried over.

The invariant under test: misconfiguration raises at boot. A service never
silently degrades.
"""

from __future__ import annotations

import pytest

from brandme_foundation.runtime.config import (
    dependency_state,
    load_runtime_settings,
)


def _clear(monkeypatch) -> None:
    for name in (
        "RUNTIME_ROLE", "APP_ENV", "PORT", "GRACEFUL_SHUTDOWN_SECONDS",
        "RUNTIME_HEALTH_ONLY", "RUNTIME_BOOTSTRAP_MODE", "K_SERVICE",
        "SPANNER_PROJECT_ID", "SPANNER_INSTANCE_ID", "SPANNER_DATABASE_ID",
        "SPANNER_DB_ROLE", "FIRESTORE_PROJECT_ID", "DATABASE_URL",
        "POSTGRES_PASSWORD", "MIDNIGHT_ENABLED", "STORE_BACKEND",
        "BROKER_BACKEND", "AUTH_JWT_MODE", "CUBE_PROJECTION_CONSUMER_ENABLED",
        "WORKER_TRANSFER_CLOSE_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_to_dev_api(monkeypatch) -> None:
    _clear(monkeypatch)
    settings = load_runtime_settings()
    assert settings.role == "api"
    assert settings.app_env == "dev"
    assert settings.deployed is False


def test_unknown_role_raises(monkeypatch) -> None:
    _clear(monkeypatch)
    with pytest.raises(RuntimeError, match="unknown RUNTIME_ROLE"):
        load_runtime_settings("chain_anchor")


def test_cube_projector_is_a_known_role(monkeypatch) -> None:
    """The Brand.Me rename of Lux's graph_projector role took effect."""
    _clear(monkeypatch)
    monkeypatch.setenv("CUBE_PROJECTION_CONSUMER_ENABLED", "1")
    monkeypatch.setenv("SPANNER_DB_ROLE", "brandme_cube_projector")
    monkeypatch.setenv("SPANNER_PROJECT_ID", "brandme")
    monkeypatch.setenv("SPANNER_INSTANCE_ID", "main")
    monkeypatch.setenv("SPANNER_DATABASE_ID", "assets")
    assert load_runtime_settings("cube_projector").role == "cube_projector"


def test_cube_projector_requires_its_consumer_flag(monkeypatch) -> None:
    _clear(monkeypatch)
    with pytest.raises(RuntimeError, match="explicit consumer flag"):
        load_runtime_settings("cube_projector")


def test_cube_projector_requires_its_dedicated_db_role(monkeypatch) -> None:
    """Least privilege: the projector may not run as any other Spanner role."""
    _clear(monkeypatch)
    monkeypatch.setenv("CUBE_PROJECTION_CONSUMER_ENABLED", "1")
    monkeypatch.setenv("SPANNER_DB_ROLE", "brandme_worker")
    with pytest.raises(RuntimeError, match="brandme_cube_projector"):
        load_runtime_settings("cube_projector")


def test_cube_projector_rejects_unrelated_database_authority(monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("CUBE_PROJECTION_CONSUMER_ENABLED", "1")
    monkeypatch.setenv("SPANNER_DB_ROLE", "brandme_cube_projector")
    monkeypatch.setenv("SPANNER_PROJECT_ID", "brandme")
    monkeypatch.setenv("SPANNER_INSTANCE_ID", "main")
    monkeypatch.setenv("SPANNER_DATABASE_ID", "assets")
    monkeypatch.setenv("DATABASE_URL", "postgresql://somewhere")
    with pytest.raises(RuntimeError, match="unrelated database authority"):
        load_runtime_settings("cube_projector")


def test_invalid_app_env_raises(monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(RuntimeError, match="unknown APP_ENV"):
        load_runtime_settings("api")


@pytest.mark.parametrize("port", ["0", "70000", "not-a-port"])
def test_invalid_port_raises(monkeypatch, port: str) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("PORT", port)
    with pytest.raises(RuntimeError, match="PORT"):
        load_runtime_settings("api")


def test_dependency_state_never_infers_health(monkeypatch) -> None:
    """Unset dependencies report unavailable — never assumed healthy."""
    _clear(monkeypatch)
    state = dependency_state()
    assert state["spanner"] == "unavailable"
    assert state["firestore"] == "unavailable"
    assert state["midnight"] == "disabled"
    assert state["pubsub"] == "local_only"


def test_dependency_state_reflects_brandme_configuration(monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("SPANNER_INSTANCE_ID", "main")
    monkeypatch.setenv("FIRESTORE_PROJECT_ID", "brandme")
    monkeypatch.setenv("MIDNIGHT_ENABLED", "true")
    monkeypatch.setenv("BROKER_BACKEND", "pubsub")
    monkeypatch.setenv("STORE_BACKEND", "spanner")
    state = dependency_state()
    assert state["spanner"] == "configured"
    assert state["firestore"] == "configured"
    assert state["midnight"] == "configured"
    assert state["pubsub"] == "configured"
    assert state["persistence"] == "configured"
