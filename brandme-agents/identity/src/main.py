"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Identity Service
================

Provides user persona data, trust scores, and Cardano DID information.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import asyncpg
import logging
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
)
logger = logging.getLogger(__name__)

# Database pool
db_pool: Optional[asyncpg.Pool] = None


# ==========================================
# Pydantic Models
# ==========================================

class UserPersona(BaseModel):
    user_id: str
    handle: str
    display_name: Optional[str] = None
    persona_warm_cold: Optional[float] = Field(None, description="Persona dimension: 0=warm, 1=cold")
    persona_sport_couture: Optional[float] = Field(None, description="Persona dimension: 0=sport, 1=couture")
    trust_score: Optional[float] = Field(None, description="Reputation score (0-999.99)")
    region_code: Optional[str] = Field(None, description="User's primary region")
    did_cardano: Optional[str] = Field(None, description="Cardano Decentralized Identifier")


# ==========================================
# Database Functions
# ==========================================

async def init_db_pool():
    """Initialize database connection pool"""
    global db_pool
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    db_pool = await asyncpg.create_pool(database_url, min_size=5, max_size=20)
    logger.info("Database pool initialized")


async def close_db_pool():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database pool closed")


async def get_user_persona(user_id: str) -> Optional[UserPersona]:
    """
    Fetch user persona data from database

    Returns user's persona scores, trust score, and DID
    """
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                user_id,
                handle,
                display_name,
                persona_warm_cold,
                persona_sport_couture,
                trust_score,
                region_code,
                did_cardano
            FROM users
            WHERE user_id = $1 AND is_active = TRUE
            """,
            user_id
        )

        if not row:
            return None

        return UserPersona(
            user_id=str(row['user_id']),
            handle=row['handle'],
            display_name=row['display_name'],
            persona_warm_cold=float(row['persona_warm_cold']) if row['persona_warm_cold'] else None,
            persona_sport_couture=float(row['persona_sport_couture']) if row['persona_sport_couture'] else None,
            trust_score=float(row['trust_score']) if row['trust_score'] else None,
            region_code=row['region_code'],
            did_cardano=row['did_cardano']
        )


async def update_trust_score(user_id: str, new_score: float):
    """
    Update user's trust score

    Trust scores can be updated based on:
    - Successful scans
    - Reported issues
    - Community feedback
    """
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET trust_score = $1, updated_at = NOW()
            WHERE user_id = $2
            """,
            new_score,
            user_id
        )
        logger.info(f"Updated trust score for user {user_id}: {new_score}")


# ==========================================
# FastAPI App
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    # Startup
    await init_db_pool()
    yield
    # Shutdown
    await close_db_pool()


app = FastAPI(
    title="Brand.Me Identity Service",
    description="User persona, trust scores, and DID management",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# API Endpoints
# ==========================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "brandme-identity",
        "database": "connected" if db_pool else "disconnected"
    }


@app.get("/user/{user_id}/persona", response_model=UserPersona)
async def get_persona(user_id: str):
    """
    Get user persona data

    Returns:
    - Persona dimensions (warm/cold, sport/couture)
    - Trust score
    - Region
    - Cardano DID (if minted)
    """
    try:
        persona = await get_user_persona(user_id)

        if not persona:
            raise HTTPException(status_code=404, detail=f"User not found: {user_id}")

        return persona

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching persona for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.put("/user/{user_id}/trust-score")
async def update_user_trust_score(user_id: str, new_score: float):
    """
    Update user's trust score

    This endpoint is typically called by:
    - Reputation management systems
    - Admin tools
    - ML models

    Args:
        user_id: User UUID
        new_score: New trust score (0-999.99)
    """
    try:
        if new_score < 0 or new_score > 999.99:
            raise HTTPException(
                status_code=400,
                detail="Trust score must be between 0 and 999.99"
            )

        await update_trust_score(user_id, new_score)

        return {
            "status": "success",
            "user_id": user_id,
            "new_trust_score": new_score
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating trust score for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
