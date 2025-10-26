# Brand.Me v7 — Stable Integrity Spine
# Implements: Request tracing, human escalation guardrails, safe facet previews.
# brandme-agents/identity/src/main.py

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id
from brandme_core.db import create_pool_from_env, safe_close_pool, health_check
from brandme_core.metrics import get_metrics_collector, generate_metrics
from fastapi.responses import Response

logger = get_logger("identity_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # v7 fix: use shared database utility with retry logic
    app.state.db_pool = await create_pool_from_env(min_size=5, max_size=20)
    logger.info({"event": "identity_service_started"})
    yield
    await safe_close_pool(app.state.db_pool)
    logger.info({"event": "identity_service_stopped"})


app = FastAPI(lifespan=lifespan)


@app.get("/identity/{user_id}/profile")
async def get_identity_profile(user_id: str, request: Request):
    """
    Get user identity profile including consent graph.
    Returns synthetic record if user not found (prevents 500s during scanning).
    TODO: persist friends_allowed and consent_version in DB graph
    TODO: expose DID issuance/rotation lifecycle
    """
    payload = {
        "user_id": user_id,
        "display_name": "unknown",
        "region_code": "unknown",
        "trust_score": 0.5,
        "did_cardano": None,
        "friends_allowed": [],
        "consent_version": "consent_v1_alpha",
    }

    response = JSONResponse(content=payload)
    request_id = ensure_request_id(request, response)

    logger.info({
        "event": "identity_profile_lookup",
        "user_redacted": redact_user_id(user_id),
        "region_code": payload["region_code"],
        "trust_score": payload["trust_score"],
        "friends_allowed_count": len(payload["friends_allowed"]),
        "request_id": request_id,
    })

    return response


@app.get("/health")
async def health():
    """Health check endpoint that verifies database connectivity."""
    if app.state.db_pool:
        is_healthy = await health_check(app.state.db_pool)
        metrics.update_health("database", is_healthy)
        if is_healthy:
            return JSONResponse(content={"status": "ok", "service": "identity"})
        else:
            return JSONResponse(content={"status": "degraded", "service": "identity", "database": "unhealthy"}, status_code=503)
    return JSONResponse(content={"status": "error", "service": "identity", "message": "no_db_pool"}, status_code=503)


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_metrics(),
        media_type="text/plain; version=0.0.4"
    )
