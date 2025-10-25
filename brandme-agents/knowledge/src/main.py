"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Knowledge Service
=================

RAG-based garment metadata retrieval service.
Fetches garment passport facets based on visibility scope.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
import asyncpg
import logging
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv
import json

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

class FacetPreview(BaseModel):
    facet_id: str
    facet_type: str = Field(..., description="Type: authenticity, esg, ownership, pricing, etc.")
    facet_payload_preview: dict = Field(..., description="Preview of facet data (sanitized)")
    is_public_default: bool = Field(..., description="Whether this facet is public by default")


class GarmentInfo(BaseModel):
    garment_id: str
    display_name: str
    category: Optional[str] = None
    creator_id: str
    current_owner_id: str
    public_esg_score: Optional[str] = None
    public_story_snippet: Optional[str] = None
    is_authentic: bool


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


async def get_garment_info(garment_id: str) -> Optional[GarmentInfo]:
    """Fetch basic garment information"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                garment_id,
                display_name,
                category,
                creator_id,
                current_owner_id,
                public_esg_score,
                public_story_snippet,
                is_authentic
            FROM garments
            WHERE garment_id = $1 AND is_active = TRUE
            """,
            garment_id
        )

        if not row:
            return None

        return GarmentInfo(
            garment_id=str(row['garment_id']),
            display_name=row['display_name'],
            category=row['category'],
            creator_id=str(row['creator_id']),
            current_owner_id=str(row['current_owner_id']),
            public_esg_score=row['public_esg_score'],
            public_story_snippet=row['public_story_snippet'],
            is_authentic=row['is_authentic']
        )


async def get_allowed_facets(
    garment_id: str,
    scope: Literal["public", "friends_only", "private"]
) -> List[FacetPreview]:
    """
    Fetch allowed facets for a garment based on visibility scope

    Logic:
    1. Join garment_passport_facets with consent_policies
    2. Filter by scope
    3. Sanitize payload for public/friends_only scopes
    4. Return full payload for private scope (owner)
    """
    async with db_pool.acquire() as conn:
        # Get all facets for the garment
        facets_query = """
            SELECT
                f.facet_id,
                f.facet_type,
                f.facet_payload,
                f.is_public_default,
                f.midnight_ref,
                f.cardano_ref
            FROM garment_passport_facets f
            WHERE f.garment_id = $1
        """

        facet_rows = await conn.fetch(facets_query, garment_id)

        # Get consent policies for this garment
        consent_query = """
            SELECT
                facet_type,
                visibility_scope,
                allowed
            FROM consent_policies
            WHERE garment_id = $1
        """

        consent_rows = await conn.fetch(consent_query, garment_id)

        # Build consent map
        consent_map = {}
        for policy in consent_rows:
            key = (policy['facet_type'], policy['visibility_scope'])
            consent_map[key] = policy['allowed']

        # Filter facets based on scope and consent
        allowed_facets = []

        for facet in facet_rows:
            facet_type = facet['facet_type']

            # Check if this facet is allowed for the requested scope
            is_allowed = False

            # Check specific consent policy
            if (facet_type, scope) in consent_map:
                is_allowed = consent_map[(facet_type, scope)]
            # Check wildcard consent policy
            elif ('*', scope) in consent_map:
                is_allowed = consent_map[('*', scope)]
            # Fall back to default visibility
            elif scope == "public":
                is_allowed = facet['is_public_default']
            elif scope == "friends_only":
                # Friends can see public + some additional facets
                is_allowed = facet_type in ['authenticity', 'esg', 'story', 'materials']
            elif scope == "private":
                # Owner can see everything
                is_allowed = True

            if is_allowed:
                payload = json.loads(facet['facet_payload']) if isinstance(facet['facet_payload'], str) else facet['facet_payload']

                # Sanitize payload for non-private scopes
                if scope != "private":
                    # Remove sensitive fields
                    payload = sanitize_facet_payload(payload, facet_type)

                allowed_facets.append(
                    FacetPreview(
                        facet_id=str(facet['facet_id']),
                        facet_type=facet_type,
                        facet_payload_preview=payload,
                        is_public_default=facet['is_public_default']
                    )
                )

        logger.info(f"Fetched {len(allowed_facets)} facets for garment {garment_id} with scope {scope}")
        return allowed_facets


def sanitize_facet_payload(payload: dict, facet_type: str) -> dict:
    """
    Sanitize facet payload for public/friends_only visibility

    Remove sensitive information like:
    - Exact pricing
    - Detailed ownership lineage
    - Full repair history
    """
    if facet_type == "pricing":
        # Only show price ranges, not exact values
        if "exact_price" in payload:
            del payload["exact_price"]
        if "purchase_history" in payload:
            del payload["purchase_history"]

    if facet_type == "ownership":
        # Only show current owner, not full lineage
        if "ownership_history" in payload:
            payload["ownership_history"] = "REDACTED"

    return payload


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
    title="Brand.Me Knowledge Service",
    description="Garment metadata and passport retrieval",
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
        "service": "brandme-knowledge",
        "database": "connected" if db_pool else "disconnected"
    }


@app.get("/garment/{garment_id}", response_model=GarmentInfo)
async def get_garment(garment_id: str):
    """
    Get basic garment information (always public)
    """
    try:
        garment = await get_garment_info(garment_id)

        if not garment:
            raise HTTPException(status_code=404, detail=f"Garment not found: {garment_id}")

        return garment

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching garment {garment_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/garment/{garment_id}/passport", response_model=List[FacetPreview])
async def get_garment_passport(
    garment_id: str,
    scope: Literal["public", "friends_only", "private"] = Query(
        default="public",
        description="Visibility scope: public, friends_only, private"
    )
):
    """
    Get garment passport facets filtered by visibility scope

    CRITICAL SECURITY:
    - 'public': Anyone can view (authenticity, ESG only)
    - 'friends_only': Connected users (+ story, materials)
    - 'private': Owner only (all facets including pricing, ownership)

    **NEVER** return Midnight-private facet contents for non-private scopes!
    """
    try:
        facets = await get_allowed_facets(garment_id, scope)
        return facets

    except Exception as e:
        logger.error(f"Error fetching passport for garment {garment_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8101)
