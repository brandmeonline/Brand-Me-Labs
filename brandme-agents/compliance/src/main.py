# Brand.Me v8 — Global Integrity Spine
# Implements: Request tracing, human escalation guardrails, safe facet previews.
# brandme-agents/compliance/src/main.py
#
# v8: Migrated from PostgreSQL to Spanner

import hashlib
import json
import uuid
import os
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

from brandme_core.logging import get_logger, ensure_request_id
from brandme_core.cors_config import get_cors_config
from brandme_core.spanner.pool import create_pool_manager
from brandme_core.metrics import get_metrics_collector, generate_metrics
from google.cloud.spanner_v1 import param_types

logger = get_logger("compliance_service")
metrics = get_metrics_collector("compliance")

REGION_DEFAULT = os.getenv("REGION_DEFAULT", "us-east1")
SPANNER_PROJECT = os.getenv("SPANNER_PROJECT_ID", "test-project")
SPANNER_INSTANCE = os.getenv("SPANNER_INSTANCE_ID", "brandme-instance")
SPANNER_DATABASE = os.getenv("SPANNER_DATABASE_ID", "brandme-db")


class AuditLogRequest(BaseModel):
    scan_id: str
    decision_summary: str
    decision_detail: dict
    risk_flagged: bool
    escalated_to_human: bool
    human_approver_id: Optional[str] = None


class AnchorChainRequest(BaseModel):
    scan_id: str
    cardano_tx_hash: str
    midnight_tx_hash: str
    crosschain_root_hash: str


class EscalateRequest(BaseModel):
    scan_id: str
    region_code: str
    reason: str
    requires_human_approval: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    # v8: Use Spanner instead of PostgreSQL
    app.state.spanner_pool = create_pool_manager(
        project_id=SPANNER_PROJECT,
        instance_id=SPANNER_INSTANCE,
        database_id=SPANNER_DATABASE
    )
    await app.state.spanner_pool.initialize()
    logger.info({"event": "compliance_service_started", "database": "spanner"})
    yield
    await app.state.spanner_pool.close()
    logger.info({"event": "compliance_service_stopped"})


app = FastAPI(lifespan=lifespan)

# CORS configuration - centralized
cors_config = get_cors_config()
app.add_middleware(
    CORSMiddleware,
    **cors_config
)


@app.post("/audit/log")
async def audit_log(payload: AuditLogRequest, request: Request):
    """
    Log audit entry with hash-chaining for integrity.
    NEVER store or return wallet seeds / private Midnight payloads / facet bodies.
    v8: Updated for Spanner AuditLog table.
    """
    from google.cloud import spanner

    # Get previous hash for chain
    def _get_prev_hash(transaction):
        results = transaction.execute_sql(
            """
            SELECT entry_hash FROM AuditLog
            WHERE related_asset_id = @scan_id
            ORDER BY created_at DESC
            LIMIT 1
            """,
            params={"scan_id": payload.scan_id},
            param_types={"scan_id": param_types.STRING}
        )
        for row in results:
            return row[0]
        return ""

    prev_hash = app.state.spanner_pool.database.run_in_transaction(_get_prev_hash)

    hash_input = prev_hash + payload.decision_summary + json.dumps(payload.decision_detail)
    entry_hash = hashlib.sha256(hash_input.encode()).hexdigest()
    audit_id = str(uuid.uuid4())

    def _insert_audit(transaction):
        transaction.insert(
            table="AuditLog",
            columns=[
                "audit_id", "related_asset_id", "actor_type", "action_type",
                "action_summary", "decision_summary", "risk_flagged",
                "escalated_to_human", "human_approver_id", "policy_version",
                "prev_hash", "entry_hash", "created_at"
            ],
            values=[(
                audit_id, payload.scan_id, "system", "scan",
                payload.decision_summary, payload.decision_summary,
                payload.risk_flagged, payload.escalated_to_human,
                payload.human_approver_id, "v8",
                prev_hash, entry_hash, spanner.COMMIT_TIMESTAMP
            )]
        )

    app.state.spanner_pool.database.run_in_transaction(_insert_audit)

    response = JSONResponse(content={"status": "logged"})
    request_id = ensure_request_id(request, response)

    logger.info({
        "event": "audit_logged",
        "scan_id": payload.scan_id,
        "risk_flagged": payload.risk_flagged,
        "escalated_to_human": payload.escalated_to_human,
        "request_id": request_id,
    })

    return response


@app.post("/audit/anchorChain")
async def anchor_chain(payload: AnchorChainRequest, request: Request):
    """
    Record blockchain anchor hashes for a scan.
    NEVER log private Midnight payloads, only tx hashes.
    """
    response = JSONResponse(content={"status": "ok"})
    request_id = ensure_request_id(request, response)

    logger.info({
        "event": "anchor_chain_recorded",
        "scan_id": payload.scan_id,
        "cardano_tx_hash": payload.cardano_tx_hash,
        "midnight_tx_hash": payload.midnight_tx_hash,
        "request_id": request_id,
    })

    return response


@app.post("/audit/escalate")
async def escalate(payload: EscalateRequest, request: Request):
    """
    Queue escalation for human review.
    v8: Updated for Spanner AuditLog table.
    """
    from google.cloud import spanner

    def _get_prev_hash(transaction):
        results = transaction.execute_sql(
            """
            SELECT entry_hash FROM AuditLog
            WHERE related_asset_id = @scan_id
            ORDER BY created_at DESC
            LIMIT 1
            """,
            params={"scan_id": payload.scan_id},
            param_types={"scan_id": param_types.STRING}
        )
        for row in results:
            return row[0]
        return ""

    prev_hash = app.state.spanner_pool.database.run_in_transaction(_get_prev_hash)

    decision_detail = {"reason": payload.reason, "region_code": payload.region_code}
    hash_input = prev_hash + "escalation_request" + json.dumps(decision_detail)
    entry_hash = hashlib.sha256(hash_input.encode()).hexdigest()
    audit_id = str(uuid.uuid4())

    def _insert_escalation(transaction):
        transaction.insert(
            table="AuditLog",
            columns=[
                "audit_id", "related_asset_id", "actor_type", "action_type",
                "action_summary", "decision_summary", "risk_flagged",
                "escalated_to_human", "policy_version", "prev_hash",
                "entry_hash", "region_code", "created_at"
            ],
            values=[(
                audit_id, payload.scan_id, "system", "escalation",
                "escalation_request", "escalation_request", True, True,
                "v8", prev_hash, entry_hash, payload.region_code,
                spanner.COMMIT_TIMESTAMP
            )]
        )

    app.state.spanner_pool.database.run_in_transaction(_insert_escalation)

    response = JSONResponse(content={"status": "queued"})
    request_id = ensure_request_id(request, response)

    logger.info({
        "event": "audit_escalated",
        "scan_id": payload.scan_id,
        "region_code": payload.region_code,
        "request_id": request_id,
    })

    return response


@app.get("/audit/{scan_id}/explain")
async def audit_explain(scan_id: str, request: Request):
    """
    Explain audit trail for a scan.
    NEVER return facet bodies or user PII here.
    NEVER include purchase history or ownership lineage.
    v8: Updated for Spanner with AuditLog and ChainAnchor tables.
    """
    def _get_audit_info(transaction):
        # Get audit log entries
        audit_results = transaction.execute_sql(
            """
            SELECT
                related_asset_id,
                created_at,
                region_code,
                policy_version,
                action_type
            FROM AuditLog
            WHERE related_asset_id = @scan_id
            ORDER BY created_at DESC
            LIMIT 1
            """,
            params={"scan_id": scan_id},
            param_types={"scan_id": param_types.STRING}
        )
        audit_row = None
        for row in audit_results:
            audit_row = row
            break

        # Get chain anchor
        anchor_results = transaction.execute_sql(
            """
            SELECT
                cardano_tx_hash,
                midnight_tx_hash,
                crosschain_root_hash
            FROM ChainAnchor
            WHERE scan_id = @scan_id
            LIMIT 1
            """,
            params={"scan_id": scan_id},
            param_types={"scan_id": param_types.STRING}
        )
        anchor_row = None
        for row in anchor_results:
            anchor_row = row
            break

        return audit_row, anchor_row

    audit_row, anchor_row = app.state.spanner_pool.database.run_in_transaction(_get_audit_info)

    if not audit_row:
        response = JSONResponse(content={"error": "not_found"}, status_code=404)
        ensure_request_id(request, response)
        return response

    body = {
        "scan_id": audit_row[0],
        "occurred_at": audit_row[1].isoformat() + "Z" if audit_row[1] else None,
        "region_code": audit_row[2],
        "policy_version": audit_row[3],
        "action_type": audit_row[4],
        "cardano_tx_hash": anchor_row[0] if anchor_row else None,
        "midnight_tx_hash": anchor_row[1] if anchor_row else None,
        "crosschain_root_hash": anchor_row[2] if anchor_row else None,
    }

    response = JSONResponse(content=body)
    request_id = ensure_request_id(request, response)

    logger.info({
        "event": "audit_explain",
        "scan_id": scan_id,
        "region_code": body["region_code"],
        "request_id": request_id,
    })

    return response


@app.get("/health")
async def health():
    """Health check with Spanner connectivity verification."""
    try:
        if app.state.spanner_pool and app.state.spanner_pool.database:
            # Simple health check query
            def _health_check(transaction):
                results = transaction.execute_sql("SELECT 1")
                for row in results:
                    return True
                return False

            is_healthy = app.state.spanner_pool.database.run_in_transaction(_health_check)
            metrics.update_health("database", is_healthy)
            if is_healthy:
                return JSONResponse(content={"status": "ok", "service": "compliance", "database": "spanner"})
            else:
                return JSONResponse(content={"status": "degraded", "service": "compliance", "database": "unhealthy"}, status_code=503)
    except Exception as e:
        logger.error({"event": "health_check_failed", "error": str(e)})
        metrics.update_health("database", False)
        return JSONResponse(content={"status": "degraded", "service": "compliance", "database": "error"}, status_code=503)
    return JSONResponse(content={"status": "error", "service": "compliance", "message": "no_spanner_pool"}, status_code=503)


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_metrics(),
        media_type="text/plain; version=0.0.4"
    )
