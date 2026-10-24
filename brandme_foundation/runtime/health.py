"""Capability-free health application for first-environment rollback baselines."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, Request

from brandme_foundation.runtime.config import load_runtime_settings
from brandme_foundation.runtime.http import RuntimeRequestMiddleware


def create_health_app(role: Literal["api", "worker", "webhooks"]) -> FastAPI:
    settings = load_runtime_settings(role)
    if not settings.health_only:
        raise RuntimeError("capability-free health app requires RUNTIME_HEALTH_ONLY=1")

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(RuntimeRequestMiddleware, role=role)

    @app.get("/health")
    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "role": role, "revision": settings.revision}

    @app.get("/ready")
    @app.get("/readyz")
    def readyz(request: Request) -> dict[str, Any]:
        ready = bool(getattr(request.app.state, "ready", False))
        return {
            "status": "ready" if ready else "draining",
            "role": role,
            "capability": "health_only",
            "revision": settings.revision,
        }

    return app
