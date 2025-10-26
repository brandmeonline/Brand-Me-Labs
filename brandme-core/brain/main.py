"""
Brand.Me Brain Service
======================
AI Brain Hub and Intent Resolver - coordinates scan flow and policy decisions.

Features:
- Resilient HTTP clients with automatic retries
- Proper error handling and graceful degradation
- Request ID propagation for distributed tracing
- Health check endpoints
- Structured logging with PII redaction
"""
import datetime as dt
import uuid
from typing import Optional
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator

from brandme_core import (
    get_logger,
    redact_user_id,
    ensure_request_id,
    config,
    create_db_pool,
    safe_close_pool,
    get_http_client,
    close_all_clients,
    DatabaseError,
    ServiceUnavailableError,
    ValidationError,
)

logger = get_logger("brain_service")

pool: Optional[asyncpg.Pool] = None


# ============================================================================
# Lifespan Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    global pool

    # Startup
    try:
        pool = await create_db_pool()
        logger.info("Brain service startup complete")
    except DatabaseError as e:
        logger.error("Failed to start brain service", extra={"error": str(e)})
        # Continue without DB in stub mode
        if config.ENABLE_STUB_MODE:
            logger.warning("Running in stub mode without database")
            pool = None
        else:
            raise

    yield

    # Shutdown
    await safe_close_pool(pool)
    await close_all_clients()
    logger.info("Brain service shutdown complete")


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Brand.Me Brain Service",
    description="AI Brain Hub and Intent Resolver",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request/Response Models
# ============================================================================

class IntentResolveRequest(BaseModel):
    scan_id: str
    scanner_user_id: str
    garment_tag: str
    region_code: str

    @validator('scan_id', 'scanner_user_id', 'garment_tag')
    def validate_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    @validator('region_code')
    def validate_region_code(cls, v):
        if not v or len(v) < 2:
            raise ValueError("Invalid region code")
        return v.lower()


class IntentResolveResponse(BaseModel):
    action: str
    garment_id: str
    scanner_user_id: str
    region_code: str
    policy_decision: str
    resolved_scope: str
    policy_version: str
    escalated: bool


# ============================================================================
# Helper Functions
# ============================================================================

async def lookup_garment_id(garment_tag: str) -> str:
    """
    Resolve a garment tag to a garment ID.

    In stub mode: returns a UUID.
    In production: queries database for garment mapping.
    """
    if config.ENABLE_STUB_MODE or pool is None:
        garment_id = str(uuid.uuid4())
        logger.debug("Generated stub garment_id", extra={"garment_tag": garment_tag[:8] + "…"})
        return garment_id

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT garment_id FROM garments WHERE nfc_tag = $1 OR rfid_tag = $1 OR qr_code = $1 LIMIT 1",
                garment_tag
            )
            if row:
                return str(row["garment_id"])
            else:
                # Tag not found - create stub in dev mode
                if config.is_development():
                    garment_id = str(uuid.uuid4())
                    logger.warning("Garment tag not found, using stub", extra={"tag": garment_tag[:8] + "…"})
                    return garment_id
                else:
                    raise ValidationError(f"Garment tag not found", field="garment_tag")

    except DatabaseError:
        # Fallback to stub if database is unavailable
        logger.warning("Database unavailable for garment lookup, using stub")
        return str(uuid.uuid4())


async def call_policy_gate(
    scanner_user_id: str,
    garment_id: str,
    region_code: str,
    request_id: str
) -> dict:
    """
    Call the policy service to check if scan is allowed.

    Returns:
        dict with keys: decision, resolved_scope, policy_version
    """
    if config.ENABLE_STUB_MODE:
        return {
            "decision": "allow",
            "resolved_scope": "public",
            "policy_version": "policy_v1_us-east1"
        }

    try:
        client = get_http_client("policy", config.POLICY_SERVICE_URL)
        response = await client.post(
            "/policy/check",
            request_id=request_id,
            json={
                "scanner_user_id": scanner_user_id,
                "garment_id": garment_id,
                "region_code": region_code,
                "action": "request_passport_view"
            }
        )
        response.raise_for_status()
        return response.json()

    except ServiceUnavailableError as e:
        logger.warning("Policy service unavailable, allowing with public scope", extra={"error": str(e)})
        # Graceful degradation: allow with minimal scope
        return {
            "decision": "allow",
            "resolved_scope": "public",
            "policy_version": "fallback_public"
        }


async def call_orchestrator(scan_packet: dict, request_id: str) -> dict:
    """
    Call the orchestrator service to process an allowed scan.

    Returns:
        dict with orchestrator response
    """
    if config.ENABLE_STUB_MODE:
        return {
            "status": "ok",
            "scan_id": scan_packet["scan_id"],
            "shown_facets_count": 3,
            "cardano_tx_hash": "cardano_stub_" + str(uuid.uuid4()),
            "midnight_tx_hash": "midnight_stub_" + str(uuid.uuid4()),
            "crosschain_root_hash": "root_stub_" + str(uuid.uuid4())
        }

    try:
        client = get_http_client("orchestrator", config.ORCHESTRATOR_SERVICE_URL)
        response = await client.post(
            "/scan/commit",
            request_id=request_id,
            json=scan_packet
        )
        response.raise_for_status()
        return response.json()

    except ServiceUnavailableError as e:
        logger.error("Orchestrator service unavailable", extra={"error": str(e), "scan_id": scan_packet["scan_id"]})
        # Don't fail the user request - log and continue
        # The scan can be reprocessed later from audit logs
        return {
            "status": "deferred",
            "scan_id": scan_packet["scan_id"],
            "message": "Scan logged but anchoring deferred due to service unavailability"
        }


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """
    Health check endpoint for container orchestration.

    Returns:
        200 if service is healthy
        503 if service dependencies are unhealthy
    """
    health_status = {
        "service": "brain",
        "status": "healthy",
        "database": "unknown",
        "timestamp": dt.datetime.utcnow().isoformat() + "Z"
    }

    # Check database connectivity
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            health_status["database"] = "healthy"
        except Exception as e:
            health_status["database"] = "unhealthy"
            health_status["database_error"] = str(e)
            if not config.ENABLE_STUB_MODE:
                health_status["status"] = "degraded"
                return JSONResponse(health_status, status_code=503)
    else:
        health_status["database"] = "not_configured"

    return JSONResponse(health_status, status_code=200)


@app.post("/intent/resolve", response_model=IntentResolveResponse)
async def intent_resolve(payload: IntentResolveRequest, request: Request):
    """
    Resolve scan intent and coordinate policy check + orchestration.

    Flow:
        1. Resolve garment_tag -> garment_id
        2. Call policy service for authorization
        3. If allowed: call orchestrator to anchor scan
        4. If escalated: queue for human review
        5. Return resolution to client
    """
    try:
        # Step 1: Resolve garment ID
        garment_id = await lookup_garment_id(payload.garment_tag)

        # Generate request ID for tracing
        temp_request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

        # Step 2: Call policy gate
        policy_result = await call_policy_gate(
            payload.scanner_user_id,
            garment_id,
            payload.region_code,
            temp_request_id
        )

        decision = policy_result["decision"]
        resolved_scope = policy_result["resolved_scope"]
        policy_version = policy_result["policy_version"]
        escalated = False

        # Step 3: Handle policy decision
        if decision == "allow":
            scan_packet = {
                "scan_id": payload.scan_id,
                "scanner_user_id": payload.scanner_user_id,
                "garment_id": garment_id,
                "resolved_scope": resolved_scope,
                "policy_version": policy_version,
                "region_code": payload.region_code,
                "occurred_at": dt.datetime.utcnow().isoformat() + "Z"
            }

            await call_orchestrator(scan_packet, temp_request_id)
            escalated = False

        elif decision == "escalate":
            escalated = True
            # TODO: Call compliance service to queue escalation
            logger.info("Scan escalated for human review", extra={"scan_id": payload.scan_id})

        # Step 4: Build response
        response_body = {
            "action": "request_passport_view",
            "garment_id": garment_id,
            "scanner_user_id": payload.scanner_user_id,
            "region_code": payload.region_code,
            "policy_decision": decision,
            "resolved_scope": resolved_scope,
            "policy_version": policy_version,
            "escalated": escalated
        }

        response = JSONResponse(response_body)
        request_id = ensure_request_id(request, response)

        # Step 5: Log
        logger.info({
            "event": "intent_resolved",
            "scan_id": payload.scan_id,
            "scanner_user_redacted": redact_user_id(payload.scanner_user_id),
            "garment_partial": garment_id[:8] + "…",
            "region_code": payload.region_code,
            "policy_decision": decision,
            "resolved_scope": resolved_scope,
            "escalated": escalated,
            "request_id": request_id
        })

        return response

    except ValidationError as e:
        logger.warning("Validation error", extra={"error": str(e)})
        raise HTTPException(status_code=400, detail=e.to_dict())

    except Exception as e:
        logger.error("Unexpected error in intent_resolve", extra={"error": str(e)})
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": str(e)}
        )
