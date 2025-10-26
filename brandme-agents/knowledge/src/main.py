# brandme-agents/knowledge/src/main.py

from typing import Optional
from typing import List, Dict, Optional
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncpg

from brandme_core.logging import get_logger, ensure_request_id, truncate_id

logger = get_logger("knowledge_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.db_pool = await asyncpg.create_pool(
        host="postgres",
        port=5432,
        database="brandme",
        user="postgres",
        password="postgres",
        min_size=5,
        max_size=20,
    )
    logger.info({"event": "knowledge_service_started"})
    yield
    await app.state.db_pool.close()
    logger.info({"event": "knowledge_service_stopped"})

    # Shutdown
    await app.state.db_pool.close()
    logger.info({"event": "knowledge_service_stopped"})


app = FastAPI(lifespan=lifespan)

app = FastAPI(lifespan=lifespan)


@app.get("/garment/{garment_id}/passport")
async def get_garment_passport(garment_id: str, request: Request, scope: Optional[str] = Query("public")):
    """
    Return safe garment facets for display.
    NEVER log facet bodies.
    NEVER return pricing history, ownership lineage, wallet addresses, or anything personal.
    TODO: future - friends_only/private may include richer data with consent, but NEVER pricing lineage, ownership chain, or PII.
    """
@app.get("/garment/{garment_id}/passport")
async def get_garment_passport(
    garment_id: str, request: Request, scope: Optional[str] = Query("public")
):
    """
    Return safe garment facets for display.
    Enforce scope rules: for MLS, REGARDLESS of requested scope, only return is_public_default = TRUE facets.
    NEVER return pricing history, ownership lineage, wallet addresses, or anything personal.

    TODO: friends_only and private may unlock more detail,
    BUT STILL MUST NOT leak pricing lineage or private ownership chain without explicit design.
    """
    # For MLS, return only public-safe facets
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
                "designer": "Stella McCartney",
                "cut_and_sewn": "Italy",
            },
        },
        {
            "facet_type": "MATERIALS",
            "facet_payload_preview": {
                "composition": "95% Organic Cotton, 5% Elastane",
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
    logger.debug(
        {
            "event": "knowledge_passport_lookup",
            "garment_partial": truncate_id(garment_id),
            "effective_scope": scope or "public",
            "facet_count": len(safe_facets_list),
            "request_id": request_id,
        }
    )

    return response


@app.get("/health")
async def health():
    return JSONResponse(content={"status": "ok"})
