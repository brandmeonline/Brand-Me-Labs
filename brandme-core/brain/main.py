import datetime as dt
import uuid
from typing import Optional
from contextlib import asynccontextmanager

import asyncpg
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id

logger = get_logger("brain_service")

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
    logger.info({"event": "brain_startup", "pool_ready": True})
    yield
    await pool.close()
    logger.info({"event": "brain_shutdown"})


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:*", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    escalated: bool


async def lookup_garment_id(pool: asyncpg.Pool, garment_tag: str) -> str:
    """
    For MLS: return str(uuid.uuid4()).
    TODO: SELECT garment_id FROM garments WHERE nfc_tag=$1 OR rfid_tag=$1.
    """
    # MLS stub:
    garment_id = str(uuid.uuid4())

    # Production:
    # async with pool.acquire() as conn:
    #     row = await conn.fetchrow(
    #         "SELECT garment_id FROM garments WHERE nfc_tag = $1 OR rfid_tag = $1",
    #         garment_tag
    #     )
    #     if row:
    #         garment_id = row["garment_id"]
    #     else:
    #         raise ValueError("garment_tag not found")

    return garment_id


async def call_policy_gate(
    scanner_user_id: str, garment_id: str, region_code: str, request_id: str
) -> dict:
    """
    Use httpx.AsyncClient to POST to http://policy:8001/policy/check

    Body: {
        "scanner_user_id": scanner_user_id,
        "garment_id": garment_id,
        "region_code": region_code,
        "action": "request_passport_view"
    }
    Headers: X-Request-Id: request_id

    Expect response JSON: {
        "decision": "allow"|"deny"|"escalate",
        "resolved_scope": "public"|"friends_only"|"private",
        "policy_version": "policy_v1_us-east1"
    }

    Return that dict.
    """
    # MLS stub:
    return {
        "decision": "allow",
        "resolved_scope": "public",
        "policy_version": "policy_v1_us-east1"
    }

    # Production:
    # async with httpx.AsyncClient() as client:
    #     resp = await client.post(
    #         "http://policy:8001/policy/check",
    #         json={
    #             "scanner_user_id": scanner_user_id,
    #             "garment_id": garment_id,
    #             "region_code": region_code,
    #             "action": "request_passport_view"
    #         },
    #         headers={"X-Request-Id": request_id}
    #     )
    #     resp.raise_for_status()
    #     return resp.json()


async def call_orchestrator(scan_packet: dict, request_id: str) -> dict:
    """
    Use httpx.AsyncClient to POST to http://orchestrator:8002/scan/commit

    scan_packet looks like: {
        "scan_id": ...,
        "scanner_user_id": ...,
        "garment_id": ...,
        "resolved_scope": ...,
        "policy_version": ...,
        "region_code": ...,
        "occurred_at": "<iso8601Z>"
    }

    Headers: X-Request-Id: request_id

    Expect orchestrator response JSON: {
        "status": "ok",
        "scan_id": "...",
        "shown_facets_count": <int>,
        "cardano_tx_hash": "...",
        "midnight_tx_hash": "...",
        "crosschain_root_hash": "..."
    }
    """
    # MLS stub:
    return {
        "status": "ok",
        "scan_id": scan_packet["scan_id"],
        "shown_facets_count": 3,
        "cardano_tx_hash": "cardano_stub_" + str(uuid.uuid4()),
        "midnight_tx_hash": "midnight_stub_" + str(uuid.uuid4()),
        "crosschain_root_hash": "root_stub_" + str(uuid.uuid4())
    }

    # Production:
    # async with httpx.AsyncClient() as client:
    #     resp = await client.post(
    #         "http://orchestrator:8002/scan/commit",
    #         json=scan_packet,
    #         headers={"X-Request-Id": request_id}
    #     )
    #     resp.raise_for_status()
    #     return resp.json()


@app.post("/intent/resolve")
async def intent_resolve(payload: IntentResolveRequest, request: Request):
    """
    Scan entrypoint and flow coordinator.
    """
    # Resolve garment_id
    garment_id = await lookup_garment_id(pool, payload.garment_tag)

    # Generate temporary request_id for internal calls
    temp_request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

    # Call policy gate
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

    if decision == "allow":
        # Build scan packet
        scan_packet = {
            "scan_id": payload.scan_id,
            "scanner_user_id": payload.scanner_user_id,
            "garment_id": garment_id,
            "resolved_scope": resolved_scope,
            "policy_version": policy_version,
            "region_code": payload.region_code,
            "occurred_at": dt.datetime.utcnow().isoformat() + "Z"
        }

        # Call orchestrator
        await call_orchestrator(scan_packet, temp_request_id)
        escalated = False

    elif decision == "deny":
        escalated = False
        # Do NOT call orchestrator

    elif decision == "escalate":
        escalated = True
        # Do NOT call orchestrator
        # TODO: push escalation to compliance/governance queue

    # Build final response body
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

    # Wrap in JSONResponse
    response = JSONResponse(response_body)

    # Ensure request_id and propagate
    request_id = ensure_request_id(request, response)

    # Log
    logger.info({
        "event": "intent_resolve",
        "scan_id": payload.scan_id,
        "scanner_user_redacted": redact_user_id(payload.scanner_user_id),
        "garment_partial": garment_id[:8] + "…",
        "region_code": payload.region_code,
        "policy_decision": decision,
        "resolved_scope": resolved_scope,
        "policy_version": policy_version,
        "escalated": escalated,
        "request_id": request_id
    })

    return response
