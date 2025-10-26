# brandme-agents/identity/src/main.py

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncpg

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id

logger = get_logger("identity_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await asyncpg.create_pool(
        host="postgres",
        port=5432,
        database="brandme",
        user="postgres",
        password="postgres",
        min_size=5,
        max_size=20,
    )
    logger.info({"event": "identity_service_started"})
    yield
    await app.state.db_pool.close()
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
    return JSONResponse(content={"status": "ok"})
