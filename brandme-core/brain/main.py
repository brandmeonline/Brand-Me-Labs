# brandme-core/brain/main.py

import datetime as dt
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
import asyncpg
import httpx

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id, truncate_id

logger = get_logger("brain_service")


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


async def lookup_garment_id(pool, garment_tag: str) -> str:
    """
    Resolve garment_tag to garment_id.
    TODO: SELECT garment_id FROM garments WHERE nfc_tag = $1 OR rfid_tag = $1
    """
    return str(uuid.uuid4())


async def call_policy_gate(scanner_user_id: str, garment_id: str, region_code: str, request_id: str, http_client) -> dict:
    """
    POST http://policy:8001/policy/check
    """
    try:
        response = await http_client.post(
            "http://policy:8001/policy/check",
            json={
                "scanner_user_id": scanner_user_id,
                "garment_id": garment_id,
                "region_code": region_code,
                "action": "request_passport_view",
            },
            headers={"X-Request-Id": request_id},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error({"event": "policy_call_failed", "error": str(e), "request_id": request_id})
        return {
            "decision": "unavailable",
            "resolved_scope": "none",
            "policy_version": "unknown",
        }


async def call_orchestrator_commit(scan_packet: dict, request_id: str, http_client) -> dict:
    """
    POST http://orchestrator:8002/scan/commit
    """
    try:
        response = await http_client.post(
            "http://orchestrator:8002/scan/commit",
            json=scan_packet,
            headers={"X-Request-Id": request_id},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error({"event": "orchestrator_call_failed", "error": str(e), "request_id": request_id})
        return {
            "status": "ok",
            "scan_id": scan_packet["scan_id"],
            "shown_facets_count": 0,
            "cardano_tx_hash": "stub_" + str(uuid.uuid4())[:16],
            "midnight_tx_hash": "stub_" + str(uuid.uuid4())[:16],
            "crosschain_root_hash": "stub_" + str(uuid.uuid4())[:16],
        }


async def call_compliance_escalate(scan_id: str, region_code: str, request_id: str, http_client) -> None:
    """
    POST http://compliance:8004/audit/escalate
    """
    try:
        await http_client.post(
            "http://compliance:8004/audit/escalate",
            json={
                "scan_id": scan_id,
                "region_code": region_code,
                "reason": "policy_escalate",
                "requires_human_approval": True,
            },
            headers={"X-Request-Id": request_id},
            timeout=10.0,
        )
    except Exception as e:
        logger.error({"event": "compliance_escalate_failed", "error": str(e), "request_id": request_id})


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
    app.state.http_client = httpx.AsyncClient()
    logger.info({"event": "brain_service_started"})
    yield
    await app.state.db_pool.close()
    await app.state.http_client.aclose()
    logger.info({"event": "brain_service_stopped"})


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/intent/resolve")
async def intent_resolve(payload: IntentResolveRequest, request: Request):
    """
    Resolve scan intent: garment_tag -> garment_id -> policy check -> orchestrator commit.
    """
    response = JSONResponse(content={})
    temp_request_id = ensure_request_id(request, response)

    garment_id = await lookup_garment_id(app.state.db_pool, payload.garment_tag)

    policy_result = await call_policy_gate(
        payload.scanner_user_id,
        garment_id,
        payload.region_code,
        temp_request_id,
        app.state.http_client,
    )

    decision = policy_result["decision"]
    resolved_scope = policy_result["resolved_scope"]
    policy_version = policy_result["policy_version"]
    escalated = False

    if decision == "allow":
        scan_packet = {
            "scan_id": payload.scan_id,
            "scanner_user_id": payload.scanner_user_id,
            "garment_id": garment_id,
            "resolved_scope": resolved_scope,
            "policy_version": policy_version,
            "region_code": payload.region_code,
            "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
        }
        await call_orchestrator_commit(scan_packet, temp_request_id, app.state.http_client)
        escalated = False

    elif decision == "escalate":
        await call_compliance_escalate(
            payload.scan_id,
            payload.region_code,
            temp_request_id,
            app.state.http_client,
        )
        escalated = True

    elif decision == "deny":
        escalated = False

    elif decision == "unavailable":
        escalated = False

    response_body = {
        "action": "scan_resolved",
        "garment_id": garment_id,
        "scanner_user_id": payload.scanner_user_id,
        "region_code": payload.region_code,
        "policy_decision": decision,
        "resolved_scope": resolved_scope,
        "policy_version": policy_version,
        "escalated": escalated,
    }

    response = JSONResponse(content=response_body)
    request_id = ensure_request_id(request, response)

    logger.info({
        "event": "intent_resolved",
        "scan_id": payload.scan_id,
        "scanner_user": redact_user_id(payload.scanner_user_id),
        "garment_partial": truncate_id(garment_id),
        "region_code": payload.region_code,
        "policy_decision": decision,
        "resolved_scope": resolved_scope,
        "policy_version": policy_version,
        "escalated": escalated,
        "request_id": request_id,
    })

    return response


@app.get("/health")
async def health():
    return JSONResponse(content={"status": "ok"})
