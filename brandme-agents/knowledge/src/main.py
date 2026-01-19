# Brand.Me v8 — Global Integrity Spine
# Implements: Request tracing, human escalation guardrails, safe facet previews.
# brandme-agents/knowledge/src/main.py
#
# v8: Migrated from PostgreSQL to Spanner

import os
from typing import Optional
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from brandme_core.logging import get_logger, ensure_request_id, truncate_id
from brandme_core.spanner.pool import create_pool_manager
from brandme_core.metrics import get_metrics_collector, generate_metrics
from fastapi.responses import Response

logger = get_logger("knowledge_service")
metrics = get_metrics_collector("knowledge")

REGION_DEFAULT = os.getenv("REGION_DEFAULT", "us-east1")
SPANNER_PROJECT = os.getenv("SPANNER_PROJECT_ID", "test-project")
SPANNER_INSTANCE = os.getenv("SPANNER_INSTANCE_ID", "brandme-instance")
SPANNER_DATABASE = os.getenv("SPANNER_DATABASE_ID", "brandme-db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.spanner_pool = create_pool_manager(
        project_id=SPANNER_PROJECT,
        instance_id=SPANNER_INSTANCE,
        database_id=SPANNER_DATABASE
    )
    await app.state.spanner_pool.initialize()
    logger.info({"event": "knowledge_service_started", "database": "spanner"})
    yield
    await app.state.spanner_pool.close()
    logger.info({"event": "knowledge_service_stopped"})


app = FastAPI(lifespan=lifespan)

# v7 fix: enable CORS with secure configuration
from brandme_core.cors_config import get_cors_config
cors_config = get_cors_config()
app.add_middleware(
    CORSMiddleware,
    **cors_config
)


@app.get("/garment/{garment_id}/passport")
async def get_garment_passport(garment_id: str, request: Request, scope: Optional[str] = Query("public")):
    """
    Return safe garment facets for display.
    # v6 fix: Always returns public-safe previews only, ignores requested scope parameter for safety.
    NEVER log facet bodies.
    NEVER return pricing history, ownership lineage, wallet addresses, or anything personal.
    TODO: pull real facets with is_public_default = TRUE from DB.
    TODO: future - friends_only/private may include richer data with consent, but NEVER pricing lineage, ownership chain, or PII.
    """
    safe_facets_list = [
        {
            "facet_type": "ESG",
            "facet_payload_preview": {
                "summary": "Sustainability certified",
                "rating": "A",
            },
        },
        {
            "facet_type": "ORIGIN",
            "facet_payload_preview": {
                "cut_and_sewn": "Brooklyn, NY",
                "designer": "KAI / Atelier 7",
            },
        },
    ]

    payload = {"garment_id": garment_id, "facets": safe_facets_list}

    response = JSONResponse(content=payload)
    request_id = ensure_request_id(request, response)

    logger.debug({
        "event": "knowledge_passport_lookup",
        "garment_partial": truncate_id(garment_id),
        "effective_scope": scope,
        "facet_count": len(payload["facets"]),
        "request_id": request_id,
    })

    return response


@app.get("/health")
async def health():
    """Health check with Spanner connectivity verification."""
    try:
        if app.state.spanner_pool and app.state.spanner_pool.database:
            def _health_check(transaction):
                results = transaction.execute_sql("SELECT 1")
                for row in results:
                    return True
                return False

            is_healthy = app.state.spanner_pool.database.run_in_transaction(_health_check)
            metrics.update_health("database", is_healthy)
            if is_healthy:
                return JSONResponse(content={"status": "ok", "service": "knowledge", "database": "spanner"})
            else:
                return JSONResponse(content={"status": "degraded", "service": "knowledge", "database": "unhealthy"}, status_code=503)
    except Exception as e:
        logger.error({"event": "health_check_failed", "error": str(e)})
        metrics.update_health("database", False)
        return JSONResponse(content={"status": "degraded", "service": "knowledge", "database": "error"}, status_code=503)
    return JSONResponse(content={"status": "error", "service": "knowledge", "message": "no_spanner_pool"}, status_code=503)


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_metrics(),
        media_type="text/plain; version=0.0.4"
    )
