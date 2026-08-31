"""Fail-closed environment contract shared by every Python runtime role.

Ported from Lux `services/runtime/config.py`. The control flow — role
validation, health-only and bootstrap baselines that refuse application
capability, deployed-mode requirements — is carried over unchanged. Only the
env-var inventory is retargeted to Brand.Me's services (Spanner/Firestore
rather than Cloud SQL, ZK/Midnight rather than Lux's typed-persistence
flags).

Misconfiguration raises at boot. A service never silently degrades.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast

RuntimeRole = Literal["api", "worker", "webhooks", "migrate", "cube_projector"]
_ROLES = {"api", "worker", "webhooks", "migrate", "cube_projector"}


@dataclass(frozen=True)
class RuntimeSettings:
    role: RuntimeRole
    app_env: str
    port: int
    region: str
    revision: str
    graceful_shutdown_seconds: int
    health_only: bool = False
    bootstrap_mode: bool = False
    sigterm_probe_enabled: bool = False
    pubsub_push_audience: str = ""
    pubsub_push_service_account_email: str = ""
    worker_transfer_close_enabled: bool = False
    cube_projection_consumer_enabled: bool = False

    @property
    def deployed(self) -> bool:
        return self.app_env in {"preview", "prod"} or bool(os.getenv("K_SERVICE"))


def load_runtime_settings(role: str | None = None) -> RuntimeSettings:
    selected = (role if role is not None else os.getenv("RUNTIME_ROLE", "api")).strip().lower()
    if selected not in _ROLES:
        raise RuntimeError(f"unknown RUNTIME_ROLE: {selected!r}")
    app_env = os.getenv("APP_ENV", "dev").strip().lower()
    if app_env not in {"dev", "test", "preview", "prod"}:
        raise RuntimeError(f"unknown APP_ENV: {app_env!r}")
    try:
        port = int(os.getenv("PORT", "8080"))
    except ValueError as exc:
        raise RuntimeError("PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("PORT must be between 1 and 65535")
    try:
        graceful_shutdown_seconds = int(os.getenv("GRACEFUL_SHUTDOWN_SECONDS", "30"))
    except ValueError as exc:
        raise RuntimeError("GRACEFUL_SHUTDOWN_SECONDS must be an integer") from exc
    if not 1 <= graceful_shutdown_seconds <= 300:
        raise RuntimeError("GRACEFUL_SHUTDOWN_SECONDS must be between 1 and 300")
    region = os.getenv("GCP_REGION", "us-east4").strip()
    if not region:
        raise RuntimeError("GCP_REGION cannot be empty")
    deployed = app_env in {"preview", "prod"} or bool(os.getenv("K_SERVICE"))
    health_only = os.getenv("RUNTIME_HEALTH_ONLY", "").strip() == "1"
    bootstrap_mode = os.getenv("RUNTIME_BOOTSTRAP_MODE", "").strip() == "1"
    if health_only and bootstrap_mode:
        raise RuntimeError("runtime health-only and bootstrap modes are mutually exclusive")
    if health_only:
        if app_env != "preview" or selected not in {"api", "webhooks"}:
            raise RuntimeError(
                "RUNTIME_HEALTH_ONLY is limited to preview API and webhook baselines"
            )
        forbidden_health_configuration = {
            name
            for name in (
                "WORKER_TRANSFER_CLOSE_ENABLED",
                "DATABASE_URL",
                "SPANNER_PROJECT_ID",
                "SPANNER_INSTANCE_ID",
                "SPANNER_DATABASE_ID",
                "SPANNER_EMULATOR_HOST",
                "FIRESTORE_PROJECT_ID",
                "FIRESTORE_EMULATOR_HOST",
                "POSTGRES_DB",
                "POSTGRES_USER",
                "POSTGRES_PASSWORD",
                "ZK_PROOF_ENABLED",
                "MIDNIGHT_ENABLED",
                "MIDNIGHT_API_URL",
                "MCP_ENABLED",
                "BROKER_BACKEND",
                "PUBSUB_PROJECT",
                "PUBSUB_PUSH_AUDIENCE",
                "PUBSUB_PUSH_SERVICE_ACCOUNT_EMAIL",
                "AUTH_JWT_SECRET",
                "WEBHOOK_STANDIN_SECRETS_JSON",
                "WEBHOOK_INSTALLATIONS_JSON",
                "RUNTIME_SIGTERM_PROBE_ENABLED",
            )
            if os.getenv(name, "").strip()
        }
        if forbidden_health_configuration:
            raise RuntimeError("health-only baseline cannot receive application capability")
    if bootstrap_mode:
        if app_env != "preview" or selected != "worker":
            raise RuntimeError(
                "RUNTIME_BOOTSTRAP_MODE is limited to the preview worker baseline"
            )
        forbidden_bootstrap_configuration = {
            name
            for name in (
                "WORKER_TRANSFER_CLOSE_ENABLED",
                "DATABASE_URL",
                "SPANNER_PROJECT_ID",
                "SPANNER_INSTANCE_ID",
                "SPANNER_DATABASE_ID",
                "SPANNER_EMULATOR_HOST",
                "FIRESTORE_PROJECT_ID",
                "FIRESTORE_EMULATOR_HOST",
                "POSTGRES_DB",
                "POSTGRES_USER",
                "POSTGRES_PASSWORD",
                "ZK_PROOF_ENABLED",
                "MIDNIGHT_ENABLED",
                "MIDNIGHT_API_URL",
                "MCP_ENABLED",
                "BROKER_BACKEND",
                "PUBSUB_PROJECT",
                "AUTH_JWT_SECRET",
                "WEBHOOK_STANDIN_SECRETS_JSON",
                "WEBHOOK_INSTALLATIONS_JSON",
                "RUNTIME_SIGTERM_PROBE_ENABLED",
            )
            if os.getenv(name, "").strip()
        }
        if forbidden_bootstrap_configuration:
            raise RuntimeError(
                "bootstrap worker can receive only authenticated transport configuration"
            )
    sigterm_probe_enabled = os.getenv("RUNTIME_SIGTERM_PROBE_ENABLED", "").strip() == "1"
    if sigterm_probe_enabled and (
        app_env != "preview" or selected != "worker" or health_only or bootstrap_mode
    ):
        raise RuntimeError(
            "RUNTIME_SIGTERM_PROBE_ENABLED is limited to the preview application worker"
        )
    worker_transfer_close_enabled = (
        os.getenv("WORKER_TRANSFER_CLOSE_ENABLED", "").strip() == "1"
    )
    cube_projection_consumer_enabled = (
        os.getenv("CUBE_PROJECTION_CONSUMER_ENABLED", "").strip() == "1"
    )
    if worker_transfer_close_enabled and (
        selected != "worker" or health_only or bootstrap_mode
    ):
        raise RuntimeError(
            "transfer-close worker is limited to the application worker"
        )
    if selected in {"worker", "webhooks"}:
        legacy_store = os.getenv("STORE_BACKEND", "").strip().lower()
        database_environment = {
            name
            for name in (
            )
            if os.getenv(name, "").strip()
        }
        worker_database_configuration_allowed = (
            selected == "worker" and worker_transfer_close_enabled
        )
        if legacy_store in {"file", "postgres"} or (
            database_environment and not worker_database_configuration_allowed
        ):
            runtime_label = "distributed worker" if selected == "worker" else "webhook runtime"
            raise RuntimeError(
                f"{runtime_label} cannot hold legacy or Cloud SQL persistence authority"
            )
        if worker_database_configuration_allowed:
            if os.getenv("DB_USER", "").strip() != "brandme_worker":
                raise RuntimeError("transfer-close worker requires DB_USER=brandme_worker")
            required_worker_database = {
                name
                for name in (
                )
                if not os.getenv(name, "").strip()
            }
            if required_worker_database:
                raise RuntimeError(
                    "transfer-close worker database configuration is incomplete"
                )
            forbidden_worker_authority = {
                name
                for name in (
                )
                if os.getenv(name, "").strip()
            }
            if forbidden_worker_authority:
                raise RuntimeError(
                    "transfer-close worker received unrelated database authority"
                )
    if selected == "cube_projector":
        if not cube_projection_consumer_enabled:
            raise RuntimeError("cube projector requires its explicit consumer flag")
        if os.getenv("SPANNER_DB_ROLE", "").strip() != "brandme_cube_projector":
            raise RuntimeError(
                "cube projector requires SPANNER_DB_ROLE=brandme_cube_projector"
            )
        required_cube_database = {
            name
            for name in ("SPANNER_PROJECT_ID", "SPANNER_INSTANCE_ID", "SPANNER_DATABASE_ID")
            if not os.getenv(name, "").strip()
        }
        if required_cube_database:
            raise RuntimeError("cube projector database configuration is incomplete")
        forbidden_cube_authority = {
            name
            for name in (
                "DATABASE_URL",
                "POSTGRES_PASSWORD",
                "WORKER_TRANSFER_CLOSE_ENABLED",
            )
            if os.getenv(name, "").strip()
        }
        if forbidden_cube_authority:
            raise RuntimeError("cube projector received unrelated database authority")
    if (
        selected in {"worker", "webhooks", "cube_projector"}
        and deployed
        and not health_only
        and not bootstrap_mode
    ):
        if os.getenv("BROKER_BACKEND", "").strip().lower() != "pubsub":
            raise RuntimeError(
                f"deployed {selected} requires BROKER_BACKEND=pubsub"
            )
        if not os.getenv("PUBSUB_PROJECT", "").strip():
            raise RuntimeError(f"deployed {selected} requires PUBSUB_PROJECT")
    pubsub_push_audience = os.getenv("PUBSUB_PUSH_AUDIENCE", "").strip()
    pubsub_push_service_account_email = os.getenv(
        "PUBSUB_PUSH_SERVICE_ACCOUNT_EMAIL", ""
    ).strip().lower()
    if selected in {"worker", "cube_projector"} and deployed and not health_only:
        if not pubsub_push_audience:
            raise RuntimeError("deployed worker requires PUBSUB_PUSH_AUDIENCE")
        if not pubsub_push_service_account_email.endswith(".gserviceaccount.com"):
            raise RuntimeError(
                "deployed worker requires PUBSUB_PUSH_SERVICE_ACCOUNT_EMAIL"
            )
    return RuntimeSettings(
        role=cast(RuntimeRole, selected),
        app_env=app_env,
        port=port,
        region=region,
        revision=os.getenv("K_REVISION", os.getenv("GIT_SHA", "local")),
        graceful_shutdown_seconds=graceful_shutdown_seconds,
        health_only=health_only,
        bootstrap_mode=bootstrap_mode,
        sigterm_probe_enabled=sigterm_probe_enabled,
        pubsub_push_audience=pubsub_push_audience,
        pubsub_push_service_account_email=pubsub_push_service_account_email,
        worker_transfer_close_enabled=(
            worker_transfer_close_enabled
        ),
        cube_projection_consumer_enabled=cube_projection_consumer_enabled,
    )


def dependency_state() -> dict[str, str]:
    """Truthful configuration state; no dependency is inferred healthy."""
    store = os.getenv("STORE_BACKEND", "").strip().lower()
    broker = os.getenv("BROKER_BACKEND", "").strip().lower()
    return {
        "persistence": "configured" if store in {"file", "postgres", "spanner"} else "transient",
        "pubsub": "configured" if broker == "pubsub" else "local_only",
        "identity": "configured" if os.getenv("AUTH_JWT_MODE", "").strip() else "unavailable",
        "spanner": "configured" if os.getenv("SPANNER_INSTANCE_ID", "").strip() else "unavailable",
        "firestore": "configured" if os.getenv("FIRESTORE_PROJECT_ID", "").strip() else "unavailable",
        "midnight": "configured" if os.getenv("MIDNIGHT_ENABLED", "").strip().lower() == "true" else "disabled",
    }
