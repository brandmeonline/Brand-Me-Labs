"""
Brand.Me Identity Service
==========================
User persona, trust scores, and consent graph management.

Features:
- Database connection with retries
- Health check endpoints
- PII redaction in logs
- Consent graph integration (stub)
"""
import uuid
from typing import Optional
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from brandme_core import (
    get_logger,
    redact_user_id,
    ensure_request_id,
    config,
    create_db_pool,
    safe_close_pool,
    DatabaseError,
)

logger = get_logger("identity_service")
pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    try:
        pool = await create_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS identity (
                    user_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    region_code TEXT NOT NULL,
                    trust_score NUMERIC DEFAULT 0.5,
                    did_cardano TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
        logger.info("Identity service startup complete")
    except DatabaseError as e:
        logger.error("Database initialization failed", extra={"error": str(e)})
        if not config.ENABLE_STUB_MODE:
            raise

    yield
    await safe_close_pool(pool)
    logger.info("Identity service shutdown complete")


app = FastAPI(
    title="Brand.Me Identity Service",
    description="User persona, trust scores, and DID management",
    version="2.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    health_status = {"service": "identity", "status": "healthy", "database": "unknown"}
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            health_status["database"] = "healthy"
        except Exception:
            health_status["database"] = "unhealthy"
            if not config.ENABLE_STUB_MODE:
                return JSONResponse(health_status, status_code=503)
    return JSONResponse(health_status)


@app.get("/identity/{user_id}/profile")
async def get_identity_profile(user_id: str, request: Request):
    """
    Get identity profile for a user.
    Returns: user_id, display_name, region_code, trust_score, did_cardano,
             friends_allowed, consent_version
    """
    try:
        if pool:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT user_id, display_name, region_code, trust_score, did_cardano FROM identity WHERE user_id = $1",
                    user_id
                )

                if row:
                    display_name = row["display_name"]
                    region_code = row["region_code"]
                    trust_score = float(row["trust_score"])
                    did_cardano = row["did_cardano"]
                else:
                    # Create stub identity in development
                    display_name = f"User_{user_id[:8]}"
                    region_code = "us-east1"
                    trust_score = 0.5
                    did_cardano = None

                    if config.is_development():
                        await conn.execute(
                            """
                            INSERT INTO identity (user_id, display_name, region_code, trust_score, did_cardano)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (user_id) DO NOTHING
                            """,
                            user_id, display_name, region_code, trust_score, did_cardano
                        )
        else:
            # Stub mode
            display_name = f"User_{user_id[:8]}"
            region_code = "us-east1"
            trust_score = 0.5
            did_cardano = None

        # TODO: hydrate friends_allowed from consent graph table
        friends_allowed = []

        payload = {
            "user_id": user_id,
            "display_name": display_name,
            "region_code": region_code,
            "trust_score": trust_score,
            "did_cardano": did_cardano,
            "friends_allowed": friends_allowed,
            "consent_version": "consent_v1_alpha"
        }

        response = JSONResponse(payload)
        request_id = ensure_request_id(request, response)

        logger.info({
            "event": "identity_profile_lookup",
            "user_redacted": redact_user_id(user_id),
            "region_code": payload["region_code"],
            "trust_score": payload["trust_score"],
            "request_id": request_id
        })

        # TODO: expose trust_score calculation methodology to compliance for algorithmic accountability

        return response

    except Exception as e:
        logger.error("Profile lookup failed", extra={"error": str(e)})
        raise HTTPException(500, f"Profile lookup failed: {str(e)}")
