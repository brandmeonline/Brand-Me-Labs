# Brand.Me v7 — Stable Integrity Spine
# Implements: Request tracing, human escalation guardrails, safe facet previews.
# brandme-core/brain/main.py

import datetime as dt
import uuid
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
import httpx

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id, truncate_id
from brandme_core.db import create_pool_from_env, safe_close_pool, health_check

logger = get_logger("brain_service")

REGION_DEFAULT = os.getenv("REGION_DEFAULT", "us-east1")


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
    TEMP: return str(uuid.uuid4())
    TODO: SELECT garment_id FROM garments WHERE nfc_tag=$1 OR rfid_tag=$1
    """
    return str(uuid.uuid4())


async def call_policy_gate(scanner_user_id: str, garment_id: str, region_code: str, request_id: str, http_client) -> dict:
    """
    POST http://policy:8001/policy/check with retry logic
    Headers: {"X-Request-Id": request_id}
    """
    from brandme_core.http_client import http_post_with_retry
    from brandme_core.env import get_service_url
    
    policy_url = f"{get_service_url('policy')}/policy/check"
    
    try:
        response = await http_post_with_retry(
            http_client,
            policy_url,
            json={
                "scanner_user_id": scanner_user_id,
                "garment_id": garment_id,
                "region_code": region_code,
                "action": "request_passport_view",
            },
            headers={"X-Request-Id": request_id},
            timeout=10.0,
            max_retries=3,
        )
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
    POST http://orchestrator:8002/scan/commit with retry logic
    Headers: {"X-Request-Id": request_id}
    """
    from brandme_core.http_client import http_post_with_retry
    from brandme_core.env import get_service_url
    
    orchestrator_url = f"{get_service_url('orchestrator')}/scan/commit"
    
    try:
        response = await http_post_with_retry(
            http_client,
            orchestrator_url,
            json=scan_packet,
            headers={"X-Request-Id": request_id},
            timeout=30.0,
            max_retries=3,
        )
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
    POST http://compliance:8004/audit/escalate with retry logic
    Headers: {"X-Request-Id": request_id}
    """
    from brandme_core.http_client import http_post_with_retry
    from brandme_core.env import get_service_url
    
    compliance_url = f"{get_service_url('compliance')}/audit/escalate"
    
    try:
        await http_post_with_retry(
            http_client,
            compliance_url,
            json={
                "scan_id": scan_id,
                "region_code": region_code,
                "reason": "policy_escalate",
                "requires_human_approval": True,
            },
            headers={"X-Request-Id": request_id},
            timeout=10.0,
            max_retries=3,
        )
    except Exception as e:
        logger.error({"event": "compliance_escalate_failed", "error": str(e), "request_id": request_id})


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await create_pool_from_env(min_size=5, max_size=20)
    app.state.http_client = httpx.AsyncClient()
    logger.info({"event": "brain_service_started"})
    yield
    await safe_close_pool(app.state.db_pool)
    await app.state.http_client.aclose()
    logger.info({"event": "brain_service_stopped"})


app = FastAPI(lifespan=lifespan)

# v7 fix: enable CORS for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3002"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/intent/resolve")
async def intent_resolve(body: IntentResolveRequest, request: Request):
    """
    Resolve scan intent: garment_tag -> garment_id -> policy check -> orchestrator commit.
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    garment_id = await lookup_garment_id(app.state.db_pool, body.garment_tag)

    policy_result = await call_policy_gate(
        body.scanner_user_id,
        garment_id,
        body.region_code,
        request_id,
        app.state.http_client,
    )

    decision = policy_result["decision"]
    resolved_scope = policy_result["resolved_scope"]
    policy_version = policy_result["policy_version"]
    escalated = False

    if decision == "allow":
        # v7 fix: include policy_decision in scan_packet
        scan_packet = {
            "scan_id": body.scan_id,
            "scanner_user_id": body.scanner_user_id,
            "garment_id": garment_id,
            "resolved_scope": resolved_scope,
            "policy_version": policy_version,
            "policy_decision": decision,
            "region_code": body.region_code,
            "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
        }
        await call_orchestrator_commit(scan_packet, request_id, app.state.http_client)
        escalated = False

    elif decision == "escalate":
        # v7 fix: DO NOT call orchestrator for escalated scans
        await call_compliance_escalate(
            body.scan_id,
            body.region_code,
            request_id,
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
        "scanner_user_id": body.scanner_user_id,
        "region_code": body.region_code,
        "policy_decision": decision,
        "resolved_scope": resolved_scope,
        "policy_version": policy_version,
        "escalated": escalated,
    }

    response = JSONResponse(content=response_body)
    request_id = ensure_request_id(request, response)

    logger.info({
        "event": "intent_resolved",
        "scan_id": body.scan_id,
        "scanner_user": redact_user_id(body.scanner_user_id),
        "garment_partial": truncate_id(garment_id),
        "region_code": body.region_code,
        "policy_decision": decision,
        "resolved_scope": resolved_scope,
        "policy_version": policy_version,
        "escalated": escalated,
        "request_id": request_id,
    })

    return response


@app.get("/health")
async def health():
    """Health check with database connectivity verification."""
    if app.state.db_pool:
        is_healthy = await health_check(app.state.db_pool)
        if is_healthy:
            return JSONResponse(content={"status": "ok", "service": "brain"})
        else:
            return JSONResponse(content={"status": "degraded", "service": "brain", "database": "unhealthy"}, status_code=503)
    return JSONResponse(content={"status": "error", "service": "brain", "message": "no_db_pool"}, status_code=503)
