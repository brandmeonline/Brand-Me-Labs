# Brand.Me v8 — Global Integrity Spine
# Implements: Request tracing, human escalation guardrails, safe facet previews.
# brandme-core/orchestrator/worker.py
#
# v8: Migrated from PostgreSQL to Spanner

import hashlib
import json
import os
import uuid
from typing import List, Dict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
import httpx

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id, truncate_id
from brandme_core.spanner.pool import create_pool_manager
from brandme_core.metrics import get_metrics_collector, generate_metrics
from google.cloud.spanner_v1 import param_types
from google.cloud import spanner
from fastapi.responses import Response

logger = get_logger("orchestrator_service")
metrics = get_metrics_collector("orchestrator")

REGION_DEFAULT = os.getenv("REGION_DEFAULT", "us-east1")
SPANNER_PROJECT = os.getenv("SPANNER_PROJECT_ID", "test-project")
SPANNER_INSTANCE = os.getenv("SPANNER_INSTANCE_ID", "brandme-instance")
SPANNER_DATABASE = os.getenv("SPANNER_DATABASE_ID", "brandme-db")


class OrchestratorScanPacket(BaseModel):
    scan_id: str
    scanner_user_id: str
    garment_id: str
    resolved_scope: str
    policy_version: str
    policy_decision: str  # v7 fix: added to contract
    region_code: str
    occurred_at: str


async def call_knowledge_service(garment_id: str, scope: str, request_id: str, http_client) -> List[Dict[str, object]]:
    """
    GET http://knowledge:8003/garment/{garment_id}/passport?scope={scope} with retry logic
    Headers: {"X-Request-Id": request_id}
    """
    from brandme_core.http_client import http_get_with_retry
    from brandme_core.env import get_service_url
    
    knowledge_url = f"{get_service_url('knowledge')}/garment/{garment_id}/passport"
    
    # v7 fix: use retry logic for service-to-service calls
    try:
        response = await http_get_with_retry(
            http_client,
            knowledge_url,
            params={"scope": scope},
            headers={"X-Request-Id": request_id},
            timeout=15.0,
            max_retries=3,
        )
        data = response.json()
        return data.get("facets", [])
    except Exception as e:
        logger.error({"event": "knowledge_call_failed", "error": str(e), "request_id": request_id})
        return []


async def call_compliance_audit_log(scan_id: str, decision_summary: str, decision_detail: Dict[str, object], risk_flagged: bool, escalated_to_human: bool, request_id: str, http_client) -> None:
    """
    POST http://compliance:8004/audit/log with retry logic
    Headers: {"X-Request-Id": request_id}
    """
    from brandme_core.http_client import http_post_with_retry
    from brandme_core.env import get_service_url
    
    compliance_url = f"{get_service_url('compliance')}/audit/log"
    
    # v7 fix: use retry logic for service-to-service calls
    try:
        await http_post_with_retry(
            http_client,
            compliance_url,
            json={
                "scan_id": scan_id,
                "decision_summary": decision_summary,
                "decision_detail": decision_detail,
                "risk_flagged": risk_flagged,
                "escalated_to_human": escalated_to_human,
            },
            headers={"X-Request-Id": request_id},
            timeout=10.0,
            max_retries=3,
        )
    except Exception as e:
        logger.error({"event": "compliance_audit_log_failed", "error": str(e), "request_id": request_id})


async def call_compliance_anchor_chain(scan_id: str, tx_hashes: Dict[str, str], request_id: str, http_client) -> None:
    """
    POST http://compliance:8004/audit/anchorChain with retry logic
    Headers: {"X-Request-Id": request_id}
    """
    from brandme_core.http_client import http_post_with_retry
    from brandme_core.env import get_service_url
    
    compliance_url = f"{get_service_url('compliance')}/audit/anchorChain"
    
    # v7 fix: use retry logic for service-to-service calls
    try:
        await http_post_with_retry(
            http_client,
            compliance_url,
            json={
                "scan_id": scan_id,
                "cardano_tx_hash": tx_hashes["cardano_tx_hash"],
                "midnight_tx_hash": tx_hashes["midnight_tx_hash"],
                "crosschain_root_hash": tx_hashes["crosschain_root_hash"],
            },
            headers={"X-Request-Id": request_id},
            timeout=10.0,
            max_retries=3,
        )
    except Exception as e:
        logger.error({"event": "compliance_anchor_chain_failed", "error": str(e), "request_id": request_id})


def call_tx_builder(garment_id: str, facets: List[Dict], scope: str) -> Dict[str, str]:
    """
    Build transaction hashes for Cardano (public), Midnight (private), and crosschain root.
    TODO: Replace with real blockchain transaction construction.
    """
    facet_hash = hashlib.sha256(json.dumps(facets, sort_keys=True).encode()).hexdigest()
    cardano_hash = hashlib.sha256((garment_id + scope + facet_hash).encode()).hexdigest()
    midnight_hash = hashlib.sha256((garment_id + "midnight" + facet_hash).encode()).hexdigest()
    crosschain_root = hashlib.sha256((cardano_hash + midnight_hash).encode()).hexdigest()

    return {
        "cardano_tx_hash": "tx_cardano_" + cardano_hash[:16],
        "midnight_tx_hash": "tx_midnight_" + midnight_hash[:16],
        "crosschain_root_hash": "root_" + crosschain_root[:16],
    }


async def process_allowed_scan(decision_packet: Dict[str, str], request_id: str, spanner_pool, http_client) -> Dict[str, object]:
    """
    Process allowed scan: fetch facets, persist, anchor, audit.
    Only allowed scans reach here (escalated scans are blocked upstream).
    v8: Uses Spanner for persistence.
    """
    scan_id = decision_packet["scan_id"]
    scanner_user_id = decision_packet["scanner_user_id"]
    garment_id = decision_packet["garment_id"]
    resolved_scope = decision_packet["resolved_scope"]
    policy_version = decision_packet["policy_version"]
    region_code = decision_packet["region_code"]
    occurred_at = decision_packet["occurred_at"]

    shown_facets = await call_knowledge_service(garment_id, resolved_scope, request_id, http_client)

    # v8: Insert audit log entry for the scan event
    def _insert_scan_audit(transaction):
        audit_id = str(uuid.uuid4())
        transaction.insert(
            table="AuditLog",
            columns=[
                "audit_id", "related_asset_id", "actor_type", "action_type",
                "action_summary", "decision_summary", "risk_flagged",
                "escalated_to_human", "policy_version", "region_code",
                "prev_hash", "entry_hash", "created_at"
            ],
            values=[(
                audit_id, scan_id, "system", "scan",
                f"scan_event_{resolved_scope}", f"scope_{resolved_scope}",
                False, False, policy_version, region_code,
                "", hashlib.sha256(scan_id.encode()).hexdigest(),
                spanner.COMMIT_TIMESTAMP
            )]
        )

    spanner_pool.database.run_in_transaction(_insert_scan_audit)

    tx_hashes = call_tx_builder(garment_id, shown_facets, resolved_scope)

    # v8: Insert chain anchor
    def _insert_chain_anchor(transaction):
        anchor_id = str(uuid.uuid4())
        transaction.insert(
            table="ChainAnchor",
            columns=[
                "anchor_id", "scan_id", "cardano_tx_hash", "midnight_tx_hash",
                "crosschain_root_hash", "anchored_at"
            ],
            values=[(
                anchor_id, scan_id,
                tx_hashes["cardano_tx_hash"],
                tx_hashes["midnight_tx_hash"],
                tx_hashes["crosschain_root_hash"],
                spanner.COMMIT_TIMESTAMP
            )]
        )

    spanner_pool.database.run_in_transaction(_insert_chain_anchor)

    await call_compliance_audit_log(
        scan_id,
        f"policy allowed scope {resolved_scope}",
        {"policy_version": policy_version, "region_code": region_code},
        risk_flagged=False,
        escalated_to_human=False,
        request_id=request_id,
        http_client=http_client,
    )

    await call_compliance_anchor_chain(scan_id, tx_hashes, request_id, http_client)

    logger.info({
        "event": "scan_committed",
        "scan_id": scan_id,
        "scanner_user": redact_user_id(scanner_user_id),
        "garment_partial": truncate_id(garment_id),
        "region_code": region_code,
        "shown_facets_count": len(shown_facets),
        "request_id": request_id,
    })

    return {
        "status": "ok",
        "scan_id": scan_id,
        "shown_facets_count": len(shown_facets),
        "cardano_tx_hash": tx_hashes["cardano_tx_hash"],
        "midnight_tx_hash": tx_hashes["midnight_tx_hash"],
        "crosschain_root_hash": tx_hashes["crosschain_root_hash"],
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.spanner_pool = create_pool_manager(
        project_id=SPANNER_PROJECT,
        instance_id=SPANNER_INSTANCE,
        database_id=SPANNER_DATABASE
    )
    await app.state.spanner_pool.initialize()
    app.state.http_client = httpx.AsyncClient()
    logger.info({"event": "orchestrator_service_started", "database": "spanner"})
    yield
    await app.state.spanner_pool.close()
    await app.state.http_client.aclose()
    logger.info({"event": "orchestrator_service_stopped"})


app = FastAPI(lifespan=lifespan)


@app.post("/scan/commit")
async def scan_commit(body: OrchestratorScanPacket, request: Request):
    """
    Commit allowed scan: persist, anchor, audit.
    """
    response = JSONResponse(content={})
    request_id = ensure_request_id(request, response)

    # v7 fix: escalated scans do not anchor
    if body.policy_decision == "escalate":
        logger.info({
            "event": "scan_escalated_skip_anchor",
            "scan_id": body.scan_id,
            "request_id": request_id
        })
        response = JSONResponse(content={"status": "escalated_pending_human"})
        ensure_request_id(request, response)
        return response

    decision_packet = body.dict()

    result = await process_allowed_scan(
        decision_packet,
        request_id,
        app.state.spanner_pool,
        app.state.http_client,
    )

    response = JSONResponse(content=result)
    request_id = ensure_request_id(request, response)

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
                return JSONResponse(content={"status": "ok", "service": "orchestrator", "database": "spanner"})
            else:
                return JSONResponse(content={"status": "degraded", "service": "orchestrator", "database": "unhealthy"}, status_code=503)
    except Exception as e:
        logger.error({"event": "health_check_failed", "error": str(e)})
        metrics.update_health("database", False)
        return JSONResponse(content={"status": "degraded", "service": "orchestrator", "database": "error"}, status_code=503)
    return JSONResponse(content={"status": "error", "service": "orchestrator", "message": "no_spanner_pool"}, status_code=503)


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_metrics(),
        media_type="text/plain; version=0.0.4"
    )
