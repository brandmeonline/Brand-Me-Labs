# Brand.Me v7 — Stable Integrity Spine
# Implements: Request tracing, human escalation guardrails, safe facet previews.
# brandme-agents/knowledge/src/main.py
# v6 fix: removed duplicate FastAPI init / duplicate lifespan definitions

import os
from typing import Optional
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from brandme_core.logging import get_logger, ensure_request_id, truncate_id
from brandme_core.db import create_pool_from_env, safe_close_pool, health_check

logger = get_logger("knowledge_service")

REGION_DEFAULT = os.getenv("REGION_DEFAULT", "us-east1")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await create_pool_from_env(min_size=5, max_size=20)
    logger.info({"event": "knowledge_service_started"})
    yield
    await safe_close_pool(app.state.db_pool)
    logger.info({"event": "knowledge_service_stopped"})


app = FastAPI(lifespan=lifespan)

# v7 fix: enable CORS for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO tighten in prod
    allow_methods=["*"],
    allow_headers=["*"],
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
    """Health check with database connectivity verification."""
    if app.state.db_pool:
        is_healthy = await health_check(app.state.db_pool)
        if is_healthy:
            return JSONResponse(content={"status": "ok", "service": "knowledge"})
        else:
            return JSONResponse(content={"status": "degraded", "service": "knowledge", "database": "unhealthy"}, status_code=503)
    return JSONResponse(content={"status": "error", "service": "knowledge", "message": "no_db_pool"}, status_code=503)
