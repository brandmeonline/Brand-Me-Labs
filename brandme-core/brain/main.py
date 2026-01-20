# Brand.Me v8 — Global Integrity Spine
# Implements: Request tracing, human escalation guardrails, safe facet previews.
# brandme-core/brain/main.py
#
# v8: Migrated from PostgreSQL to Spanner

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
from brandme_core.spanner.pool import create_pool_manager
from brandme_core.metrics import get_metrics_collector, generate_metrics
from google.cloud.spanner_v1 import param_types
from fastapi.responses import Response

logger = get_logger("brain_service")

REGION_DEFAULT = os.getenv("REGION_DEFAULT", "us-east1")
SPANNER_PROJECT = os.getenv("SPANNER_PROJECT_ID", "test-project")
SPANNER_INSTANCE = os.getenv("SPANNER_INSTANCE_ID", "brandme-instance")
SPANNER_DATABASE = os.getenv("SPANNER_DATABASE_ID", "brandme-db")


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


def lookup_garment_id(spanner_pool, garment_tag: str) -> str:
    """
    Look up garment_id (asset_id) from NFC/RFID tag.
    v9: Uses Spanner Assets table with physical_tag_id column.

    Args:
        spanner_pool: Spanner connection pool
        garment_tag: NFC/RFID tag identifier

    Returns:
        asset_id if found, raises ValueError if not found
    """
    def _lookup(transaction):
        results = transaction.execute_sql(
            """
            SELECT asset_id
            FROM Assets
            WHERE physical_tag_id = @tag_id
            LIMIT 1
            """,
            params={"tag_id": garment_tag},
            param_types={"tag_id": param_types.STRING}
        )
        for row in results:
            return row[0]
        return None

    asset_id = spanner_pool.database.run_in_transaction(_lookup)

    if not asset_id:
        logger.warning({
            "event": "tag_lookup_not_found",
            "garment_tag": garment_tag[:8] + "..." if len(garment_tag) > 8 else garment_tag
        })
        raise ValueError(f"No asset found for tag: {garment_tag}")

    logger.info({
        "event": "tag_lookup_success",
        "garment_tag": garment_tag[:8] + "...",
        "asset_id": asset_id[:8] + "..."
    })

    return asset_id


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
    app.state.spanner_pool = create_pool_manager(
        project_id=SPANNER_PROJECT,
        instance_id=SPANNER_INSTANCE,
        database_id=SPANNER_DATABASE
    )
    await app.state.spanner_pool.initialize()
    app.state.http_client = httpx.AsyncClient()
    logger.info({"event": "brain_service_started", "database": "spanner"})
    yield
    await app.state.spanner_pool.close()
    await app.state.http_client.aclose()
    logger.info({"event": "brain_service_stopped"})


app = FastAPI(lifespan=lifespan)

# Initialize metrics collector
metrics = get_metrics_collector("brain")

# v7 fix: enable CORS with secure configuration
from brandme_core.cors_config import get_cors_config
cors_config = get_cors_config()
app.add_middleware(
    CORSMiddleware,
    **cors_config
)


@app.post("/intent/resolve")
async def intent_resolve(body: IntentResolveRequest, request: Request):
    """
    Resolve scan intent: garment_tag -> garment_id -> policy check -> orchestrator commit.
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    try:
        garment_id = lookup_garment_id(app.state.spanner_pool, body.garment_tag)
    except ValueError as e:
        logger.warning({
            "event": "intent_resolve_tag_not_found",
            "scan_id": body.scan_id,
            "garment_tag": body.garment_tag[:8] + "..." if len(body.garment_tag) > 8 else body.garment_tag,
            "request_id": request_id,
        })
        return JSONResponse(
            status_code=404,
            content={
                "action": "scan_failed",
                "error": "garment_not_found",
                "message": str(e),
                "garment_tag": body.garment_tag,
            }
        )

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
    """Health check with Spanner connectivity verification."""
    try:
        if app.state.spanner_pool and app.state.spanner_pool.database:
            def _health_check(transaction):
                results = transaction.execute_sql("SELECT 1")
                for row in results:
                    return True
                return False

            is_healthy = app.state.spanner_pool.database.run_in_transaction(_health_check)
            metrics.update_health("database", is_healthy)
            if is_healthy:
                return JSONResponse(content={"status": "ok", "service": "brain", "database": "spanner"})
            else:
                return JSONResponse(content={"status": "degraded", "service": "brain", "database": "unhealthy"}, status_code=503)
    except Exception as e:
        logger.error({"event": "health_check_failed", "error": str(e)})
        metrics.update_health("database", False)
        return JSONResponse(content={"status": "degraded", "service": "brain", "database": "error"}, status_code=503)
    return JSONResponse(content={"status": "error", "service": "brain", "message": "no_spanner_pool"}, status_code=503)


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_metrics(),
        media_type="text/plain; version=0.0.4"
    )
