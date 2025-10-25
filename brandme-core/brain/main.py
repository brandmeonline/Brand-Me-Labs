"""
Copyright (c) Brand.Me, Inc. All rights reserved.

AI Brain Hub Service
====================

Intent resolution and garment lookup service.
Consumes NATS events and resolves garment_tag -> garment_id.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import asyncpg
import asyncio
import logging
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv
import nats
from nats.js import JetStreamContext
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

# NATS connection
nats_client: Optional[nats.NATS] = None
jetstream: Optional[JetStreamContext] = None


# ==========================================
# Pydantic Models
# ==========================================

class IntentResolveRequest(BaseModel):
    scan_id: str = Field(..., description="Scan ID")
    scanner_user_id: str = Field(..., description="Scanner user ID")
    garment_tag: str = Field(..., description="Physical garment tag ID")
    region_code: str = Field(default="us-east1", description="Region code")


class IntentResolveResponse(BaseModel):
    action: str = Field(default="request_passport_view", description="Resolved action")
    garment_id: Optional[str] = Field(None, description="Resolved garment ID")
    scanner_user_id: str = Field(..., description="Scanner user ID")
    error: Optional[str] = Field(None, description="Error message if any")


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


async def lookup_garment_by_tag(garment_tag: str) -> Optional[str]:
    """
    Lookup garment_id by physical_tag_id

    Args:
        garment_tag: Physical tag ID (NFC/QR code)

    Returns:
        garment_id if found, None otherwise
    """
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT garment_id FROM garments WHERE physical_tag_id = $1 AND is_active = TRUE",
            garment_tag
        )
        return str(row['garment_id']) if row else None


# ==========================================
# NATS Functions
# ==========================================

async def init_nats():
    """Initialize NATS connection and subscribe to events"""
    global nats_client, jetstream

    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")

    try:
        nats_client = await nats.connect(nats_url)
        jetstream = nats_client.jetstream()
        logger.info(f"Connected to NATS: {nats_url}")

        # Subscribe to scan.requested events
        await jetstream.subscribe(
            "scan.requested",
            cb=handle_scan_requested,
            durable="brain-hub-consumer",
            stream="SCANS"
        )
        logger.info("Subscribed to scan.requested events")

    except Exception as e:
        logger.error(f"Failed to connect to NATS: {e}")
        raise


async def close_nats():
    """Close NATS connection"""
    global nats_client
    if nats_client:
        await nats_client.close()
        logger.info("NATS connection closed")


async def handle_scan_requested(msg):
    """
    Handle scan.requested event from NATS

    Event payload:
    {
        "scan_id": "uuid",
        "scanner_user_id": "uuid",
        "garment_tag": "NFC_TAG_001",
        "timestamp": "ISO8601",
        "region_code": "us-east1"
    }
    """
    try:
        data = json.loads(msg.data.decode())
        logger.info(f"Received scan.requested event: scan_id={data.get('scan_id')}")

        # Resolve garment_id from garment_tag
        garment_id = await lookup_garment_by_tag(data.get('garment_tag'))

        if not garment_id:
            logger.warning(f"Garment not found for tag: {data.get('garment_tag')}")
            # Publish failure event
            await publish_intent_resolved({
                "scan_id": data.get('scan_id'),
                "scanner_user_id": data.get('scanner_user_id'),
                "error": "Garment not found",
                "action": "garment_not_found"
            })
            await msg.ack()
            return

        # Publish intent resolved event
        await publish_intent_resolved({
            "scan_id": data.get('scan_id'),
            "scanner_user_id": data.get('scanner_user_id'),
            "garment_id": garment_id,
            "action": "request_passport_view",
            "region_code": data.get('region_code', 'us-east1')
        })

        logger.info(f"Intent resolved: scan_id={data.get('scan_id')}, garment_id={garment_id}")
        await msg.ack()

    except Exception as e:
        logger.error(f"Error handling scan.requested event: {e}")
        await msg.nak()


async def publish_intent_resolved(data: dict):
    """Publish intent.resolved event to NATS"""
    try:
        await jetstream.publish(
            "intent.resolved",
            json.dumps(data).encode()
        )
        logger.debug(f"Published intent.resolved event: {data}")
    except Exception as e:
        logger.error(f"Failed to publish intent.resolved event: {e}")
        raise


# ==========================================
# FastAPI App
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    # Startup
    await init_db_pool()
    await init_nats()
    yield
    # Shutdown
    await close_nats()
    await close_db_pool()


app = FastAPI(
    title="Brand.Me AI Brain Hub",
    description="Intent resolution and garment lookup service",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
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
        "service": "brandme-core-brain",
        "database": "connected" if db_pool else "disconnected",
        "nats": "connected" if nats_client else "disconnected"
    }


@app.post("/intent/resolve", response_model=IntentResolveResponse)
async def resolve_intent(request: IntentResolveRequest):
    """
    Resolve intent from scan request

    Maps garment_tag -> garment_id
    """
    try:
        # Lookup garment by tag
        garment_id = await lookup_garment_by_tag(request.garment_tag)

        if not garment_id:
            raise HTTPException(
                status_code=404,
                detail=f"Garment not found for tag: {request.garment_tag}"
            )

        return IntentResolveResponse(
            action="request_passport_view",
            garment_id=garment_id,
            scanner_user_id=request.scanner_user_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving intent: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
