# brandme-core/brain/main.py
import os
import uuid
from typing import Optional

import asyncpg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from brandme_core.logging import ensure_request_id, get_logger, redact_user_id


class IntentResolveRequest(BaseModel):
    scan_id: str
    scanner_user_id: str
    garment_tag: str
    region_code: str


class IntentResolveResponse(BaseModel):
    action: str
    garment_id: str
    scanner_user_id: str
    region_code: str
    policy_decision: str
    resolved_scope: str
    policy_version: str


app = FastAPI()
logger = get_logger("brain")

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    """Initialize asyncpg connection pool on startup."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL not set, using stub connection pool")
        app.state.db_pool = None
    else:
        app.state.db_pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
        logger.info("Database connection pool initialized")


@app.on_event("shutdown")
async def shutdown():
    """Close asyncpg connection pool on shutdown."""
    if app.state.db_pool:
        await app.state.db_pool.close()
        logger.info("Database connection pool closed")


async def lookup_garment_id(pool: Optional[asyncpg.Pool], garment_tag: str) -> str:
    """
    Resolve a physical garment tag (NFC/RFID/QR code) to a garment_id UUID.

    For MLS/stub: returns a generated UUID.

    TODO: Replace stub with real DB query:
        SELECT garment_id FROM garments
        WHERE rfid_tag = $1 OR nfc_tag = $1 OR qr_code = $1
        LIMIT 1
    """
    # Stub implementation
    garment_id = str(uuid.uuid4())
    logger.debug(
        "Resolved garment tag to ID (stub)",
        extra={"garment_tag": garment_tag[:8] + "…", "garment_id": garment_id[:8] + "…"}
    )
    return garment_id


async def call_policy_gate(payload: dict, request_id: str) -> dict:
    """
    Call the Policy service to determine if this scan is allowed.

    POST http://localhost:8001/policy/check

    Request body:
        {
            "scanner_user_id": "...",
            "garment_id": "...",
            "region_code": "...",
            "action": "request_passport_view"
        }

    Response:
        {
            "decision": "allow" | "deny" | "escalate",
            "resolved_scope": "public" | "friends_only" | "private",
            "policy_version": "policy_v1_us-east1"
        }

    For MLS/stub: returns hardcoded allow/public response.

    TODO: Replace stub with real HTTP call using httpx:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8001/policy/check",
                json=payload,
                headers={"X-Request-Id": request_id}
            )
            return response.json()
    """
    # Stub implementation
    logger.debug(
        "Calling policy gate (stub)",
        extra={
            "scanner_user_id": redact_user_id(payload.get("scanner_user_id")),
            "garment_id": payload.get("garment_id", "")[:8] + "…",
            "request_id": request_id
        }
    )

    return {
        "decision": "allow",
        "resolved_scope": "public",
        "policy_version": "policy_v1_us-east1"
    }


@app.post("/intent/resolve")
async def resolve_intent(request: Request, body: IntentResolveRequest) -> JSONResponse:
    """
    AI Brain Hub / Intent Resolver endpoint.

    Accepts a scan context (scan_id, garment_tag, scanner_user_id, region_code).
    Resolves garment_tag -> garment_id.
    Calls policy service to determine what can be shown.
    Returns the resolution including policy decision.

    Flow:
        1. Lookup garment_id from garment_tag
        2. Call policy service with scanner_user_id, garment_id, region_code
        3. Return policy decision + resolved scope
        4. Propagate X-Request-Id for traceability
    """
    pool = app.state.db_pool

    # Step 1: Resolve garment tag to garment ID
    garment_id = await lookup_garment_id(pool, body.garment_tag)

    # Step 2: Call policy gate to check if scan is allowed
    policy_payload = {
        "scanner_user_id": body.scanner_user_id,
        "garment_id": garment_id,
        "region_code": body.region_code,
        "action": "request_passport_view"
    }

    # We'll set request_id later from ensure_request_id, but for the policy call we can peek
    temp_request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    policy_result = await call_policy_gate(policy_payload, temp_request_id)

    decision = policy_result["decision"]
    resolved_scope = policy_result["resolved_scope"]
    policy_version = policy_result["policy_version"]

    # Step 3: Build response
    response_body = {
        "action": "request_passport_view",
        "garment_id": garment_id,
        "scanner_user_id": body.scanner_user_id,
        "region_code": body.region_code,
        "policy_decision": decision,
        "resolved_scope": resolved_scope,
        "policy_version": policy_version
    }

    response = JSONResponse(content=response_body)

    # Step 4: Ensure X-Request-Id is propagated
    request_id = ensure_request_id(request, response)

    # Step 5: Log the resolution with redacted PII
    logger.info(
        "Intent resolved",
        extra={
            "scan_id": body.scan_id,
            "scanner_user_id": redact_user_id(body.scanner_user_id),
            "garment_id": garment_id[:8] + "…",
            "region_code": body.region_code,
            "decision": decision,
            "resolved_scope": resolved_scope,
            "policy_version": policy_version,
            "request_id": request_id
        }
    )

    # TODO: integrate NATS / JetStream consumer that listens for "scan.requested" events from gateway instead of only HTTP
    # TODO: forward allow/deny/escalate packets to orchestrator.worker when we go async
    # TODO: escalate path: if policy_decision == "escalate", this should enqueue human review instead of continuing automatically

    return response
