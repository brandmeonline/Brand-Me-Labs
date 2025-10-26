import uuid
from typing import Optional
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id

logger = get_logger("identity_service")

pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(
        host="postgres",
        port=5432,
        database="brandme",
        user="brandme_user",
        password="brandme_pass",
        min_size=2,
        max_size=10,
    )
    logger.info({"event": "identity_startup", "pool_ready": True})

    # Create identity table if not exists
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

    yield
    await pool.close()
    logger.info({"event": "identity_shutdown"})


app = FastAPI(lifespan=lifespan)


@app.get("/identity/{user_id}/profile")
async def get_identity_profile(user_id: str, request: Request):
    """
    Get identity profile for a user.
    Returns: user_id, display_name, region_code, trust_score, did_cardano,
             friends_allowed, consent_version
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id, display_name, region_code, trust_score, did_cardano FROM identity WHERE user_id = $1",
            user_id
        )

        if not row:
            # Stub: create a default identity
            display_name = f"User_{user_id[:8]}"
            region_code = "us-east1"
            trust_score = 0.5
            did_cardano = None

            await conn.execute(
                """
                INSERT INTO identity (user_id, display_name, region_code, trust_score, did_cardano)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id) DO NOTHING
                """,
                user_id, display_name, region_code, trust_score, did_cardano
            )
        else:
            display_name = row["display_name"]
            region_code = row["region_code"]
            trust_score = float(row["trust_score"])
            did_cardano = row["did_cardano"]

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

    # Build response
    response = JSONResponse(payload)

    # Ensure request_id
    request_id = ensure_request_id(request, response)

    # Log
    logger.info({
        "event": "identity_profile_lookup",
        "user_redacted": redact_user_id(user_id),
        "region_code": payload["region_code"],
        "trust_score": payload["trust_score"],
        "request_id": request_id
    })

    # TODO: expose trust_score calculation methodology to compliance for algorithmic accountability

    return response
