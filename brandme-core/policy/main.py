"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Policy & Safety Service
=======================

Consent policy enforcement, regional compliance, and safety validation.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Literal
import asyncpg
import hashlib
import yaml
import logging
from contextlib import asynccontextmanager
from pathlib import Path
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

# Policy cache
policy_cache = {}


# ==========================================
# Pydantic Models
# ==========================================

class PolicyCheckRequest(BaseModel):
    scanner_user_id: str = Field(..., description="User performing the scan")
    garment_id: str = Field(..., description="Garment being scanned")
    region_code: str = Field(default="us-east1", description="Region code")
    action: str = Field(default="request_passport_view", description="Action to validate")


class PolicyCheckResponse(BaseModel):
    decision: Literal["allow", "deny", "escalate"] = Field(..., description="Policy decision")
    resolved_scope: Optional[str] = Field(None, description="Visibility scope: public, friends_only, private")
    policy_version: str = Field(..., description="SHA256 hash of policy version")
    reason: Optional[str] = Field(None, description="Human-readable reason")


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


async def get_garment_owner(garment_id: str) -> Optional[str]:
    """Get current owner of garment"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT current_owner_id FROM garments WHERE garment_id = $1",
            garment_id
        )
        return str(row['current_owner_id']) if row else None


async def get_consent_policies(garment_id: str, region_code: str = None):
    """
    Fetch consent policies for a garment

    Returns list of policies with visibility_scope and allowed status
    """
    async with db_pool.acquire() as conn:
        query = """
            SELECT policy_id, visibility_scope, facet_type, allowed, region_code
            FROM consent_policies
            WHERE garment_id = $1
            AND (region_code = $2 OR region_code IS NULL)
            ORDER BY created_at DESC
        """
        rows = await conn.fetch(query, garment_id, region_code)
        return [dict(row) for row in rows]


async def check_relationship(scanner_user_id: str, owner_user_id: str) -> str:
    """
    Determine relationship between scanner and owner

    Returns:
        - 'public': No relationship (anyone can scan)
        - 'friends_only': Connected users only
        - 'private': Owner only

    For MVP, we'll use a simple rule:
    - If scanner == owner: 'private'
    - Otherwise: 'public'

    TODO: Implement friend graph lookup
    """
    if scanner_user_id == owner_user_id:
        return "private"

    # TODO: Check friend relationship in future
    # For now, default to public
    return "public"


# ==========================================
# Policy Functions
# ==========================================

def load_regional_policies(region_code: str) -> dict:
    """
    Load regional policy configuration from YAML

    Policies are stored in policies/region/{region_code}.yaml
    """
    if region_code in policy_cache:
        return policy_cache[region_code]

    policy_file = Path(__file__).parent.parent / "policies" / "region" / f"{region_code}.yaml"

    if not policy_file.exists():
        # Fall back to default policy
        policy_file = Path(__file__).parent.parent / "policies" / "region" / "default.yaml"

    if policy_file.exists():
        with open(policy_file, 'r') as f:
            policies = yaml.safe_load(f)
            policy_cache[region_code] = policies
            return policies

    # Return minimal default if no file found
    return {
        "region_code": region_code,
        "policies": [
            {"scope": "public", "facet_types": ["authenticity", "esg"], "allowed": True},
            {"scope": "private", "facet_types": ["*"], "allowed": True},
        ]
    }


def compute_policy_version(policies: dict) -> str:
    """
    Compute SHA256 hash of policy configuration

    This creates a tamper-evident version identifier
    """
    policy_string = json.dumps(policies, sort_keys=True)
    return hashlib.sha256(policy_string.encode()).hexdigest()


async def evaluate_policy(
    scanner_user_id: str,
    garment_id: str,
    region_code: str,
    action: str
) -> PolicyCheckResponse:
    """
    Evaluate policy and return decision

    Logic:
    1. Get garment owner
    2. Determine relationship (scanner -> owner)
    3. Load regional policies
    4. Check consent policies from database
    5. Make decision: allow/deny/escalate
    """
    # Get garment owner
    owner_id = await get_garment_owner(garment_id)
    if not owner_id:
        return PolicyCheckResponse(
            decision="deny",
            policy_version="no_garment",
            reason="Garment not found"
        )

    # Determine relationship
    relationship = await check_relationship(scanner_user_id, owner_id)

    # Load regional policies
    regional_policies = load_regional_policies(region_code)
    policy_version = compute_policy_version(regional_policies)

    # Get consent policies from database
    consent_policies = await get_consent_policies(garment_id, region_code)

    # Evaluate based on relationship and consent
    # Default allow for public scopes
    resolved_scope = relationship

    # Check if any consent policy denies access
    for policy in consent_policies:
        if policy['visibility_scope'] == relationship and not policy['allowed']:
            return PolicyCheckResponse(
                decision="deny",
                resolved_scope=relationship,
                policy_version=policy_version,
                reason=f"Consent policy denies {relationship} access"
            )

    # Check regional restrictions
    for regional_policy in regional_policies.get('policies', []):
        if regional_policy.get('scope') == relationship:
            if not regional_policy.get('allowed', True):
                return PolicyCheckResponse(
                    decision="deny",
                    resolved_scope=relationship,
                    policy_version=policy_version,
                    reason=f"Regional policy denies {relationship} access in {region_code}"
                )

    # Check for risky patterns that require escalation
    # Example: If scanner has low trust score, escalate
    # TODO: Implement trust score check

    # Default: allow
    return PolicyCheckResponse(
        decision="allow",
        resolved_scope=relationship,
        policy_version=policy_version,
        reason=f"Access granted for {relationship} scope"
    )


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

        # Subscribe to intent.resolved events
        await jetstream.subscribe(
            "intent.resolved",
            cb=handle_intent_resolved,
            durable="policy-safety-consumer",
            stream="SCANS"
        )
        logger.info("Subscribed to intent.resolved events")

    except Exception as e:
        logger.error(f"Failed to connect to NATS: {e}")
        raise


async def close_nats():
    """Close NATS connection"""
    global nats_client
    if nats_client:
        await nats_client.close()
        logger.info("NATS connection closed")


async def handle_intent_resolved(msg):
    """
    Handle intent.resolved event from AI Brain Hub

    Event payload:
    {
        "scan_id": "uuid",
        "scanner_user_id": "uuid",
        "garment_id": "uuid",
        "action": "request_passport_view",
        "region_code": "us-east1"
    }
    """
    try:
        data = json.loads(msg.data.decode())
        logger.info(f"Received intent.resolved event: scan_id={data.get('scan_id')}")

        # Evaluate policy
        result = await evaluate_policy(
            scanner_user_id=data.get('scanner_user_id'),
            garment_id=data.get('garment_id'),
            region_code=data.get('region_code', 'us-east1'),
            action=data.get('action', 'request_passport_view')
        )

        # Publish policy decision
        await publish_policy_decision({
            "scan_id": data.get('scan_id'),
            "scanner_user_id": data.get('scanner_user_id'),
            "garment_id": data.get('garment_id'),
            "decision": result.decision,
            "resolved_scope": result.resolved_scope,
            "policy_version": result.policy_version,
            "reason": result.reason,
            "region_code": data.get('region_code', 'us-east1')
        })

        logger.info(f"Policy decision made: scan_id={data.get('scan_id')}, decision={result.decision}")
        await msg.ack()

    except Exception as e:
        logger.error(f"Error handling intent.resolved event: {e}")
        await msg.nak()


async def publish_policy_decision(data: dict):
    """Publish policy.decision event to NATS"""
    try:
        await jetstream.publish(
            "policy.decision",
            json.dumps(data).encode()
        )
        logger.debug(f"Published policy.decision event: {data}")
    except Exception as e:
        logger.error(f"Failed to publish policy.decision event: {e}")
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
    title="Brand.Me Policy & Safety",
    description="Consent policy enforcement and safety validation",
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
        "service": "brandme-core-policy",
        "database": "connected" if db_pool else "disconnected",
        "nats": "connected" if nats_client else "disconnected"
    }


@app.post("/policy/check", response_model=PolicyCheckResponse)
async def check_policy(request: PolicyCheckRequest):
    """
    Check consent policy for a scan request

    Returns decision: allow/deny/escalate
    """
    try:
        result = await evaluate_policy(
            scanner_user_id=request.scanner_user_id,
            garment_id=request.garment_id,
            region_code=request.region_code,
            action=request.action
        )
        return result

    except Exception as e:
        logger.error(f"Error checking policy: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
