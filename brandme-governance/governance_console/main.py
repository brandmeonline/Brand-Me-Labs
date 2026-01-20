# Brand.Me v8 — Global Integrity Spine
# Implements: Request tracing, human escalation guardrails, safe facet previews.
# brandme-governance/governance_console/main.py
#
# v8: Migrated from PostgreSQL to Spanner

import os
from typing import List
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id
from brandme_core.spanner.pool import create_pool_manager
from brandme_core.metrics import get_metrics_collector, generate_metrics
from google.cloud.spanner_v1 import param_types
from google.cloud import spanner
from fastapi.responses import Response

logger = get_logger("governance_console")
metrics = get_metrics_collector("governance")

REGION_DEFAULT = os.getenv("REGION_DEFAULT", "us-east1")
SPANNER_PROJECT = os.getenv("SPANNER_PROJECT_ID", "test-project")
SPANNER_INSTANCE = os.getenv("SPANNER_INSTANCE_ID", "brandme-instance")
SPANNER_DATABASE = os.getenv("SPANNER_DATABASE_ID", "brandme-db")


class GovernanceDecisionRequest(BaseModel):
    approved: bool
    reviewer_user_id: str
    note: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.spanner_pool = create_pool_manager(
        project_id=SPANNER_PROJECT,
        instance_id=SPANNER_INSTANCE,
        database_id=SPANNER_DATABASE
    )
    await app.state.spanner_pool.initialize()
    logger.info({"event": "governance_console_started", "database": "spanner"})
    yield
    await app.state.spanner_pool.close()
    logger.info({"event": "governance_console_stopped"})


app = FastAPI(lifespan=lifespan)

# v7 fix: enable CORS with secure configuration
from brandme_core.cors_config import get_cors_config
cors_config = get_cors_config()
app.add_middleware(
    CORSMiddleware,
    **cors_config
)


@app.get("/governance/escalations")
async def get_escalations(request: Request):
    """
    List pending escalations requiring human review.
    NEVER expose facet bodies, only high-level escalation metadata.
    NEVER log PII.
    v8: Updated for Spanner AuditLog table.
    """
    def _get_escalations(transaction):
        results = transaction.execute_sql(
            """
            SELECT
                related_asset_id,
                action_summary,
                region_code,
                created_at
            FROM AuditLog
            WHERE escalated_to_human = TRUE
              AND human_approver_id IS NULL
            ORDER BY created_at DESC
            """
        )
        return list(results)

    rows = app.state.spanner_pool.database.run_in_transaction(_get_escalations)

    escalations = [
        {
            "scan_id": row[0],
            "reason": row[1],
            "region_code": row[2],
            "created_at": row[3].isoformat() + "Z" if row[3] else None,
        }
        for row in rows
    ]

    response = JSONResponse(content=escalations)
    request_id = ensure_request_id(request, response)

    logger.info({
        "event": "governance_list_escalations",
        "pending_count": len(escalations),
        "request_id": request_id,
    })

    return response


@app.post("/governance/escalations/{scan_id}/decision")
async def resolve_escalation(scan_id: str, payload: GovernanceDecisionRequest, request: Request):
    """
    Approve or deny an escalated scan.
    TODO: if approved == True, future: trigger orchestrator to finalize anchoring with /scan/commit replay
    NEVER log PII, only redacted reviewer_user_id.
    v8: Updated for Spanner AuditLog table.
    """
    def _resolve_escalation(transaction):
        # Spanner doesn't support UPDATE with complex expressions like PostgreSQL
        # Instead, we'll read, modify, and update
        results = transaction.execute_sql(
            """
            SELECT audit_id, decision_summary
            FROM AuditLog
            WHERE related_asset_id = @scan_id
              AND escalated_to_human = TRUE
              AND human_approver_id IS NULL
            """,
            params={"scan_id": scan_id},
            param_types={"scan_id": param_types.STRING}
        )

        for row in results:
            audit_id = row[0]
            current_summary = row[1] or ""
            new_summary = f"{current_summary} / human_decision"

            transaction.update(
                table="AuditLog",
                columns=["audit_id", "human_approver_id", "escalated_to_human", "decision_summary"],
                values=[(audit_id, payload.reviewer_user_id, False, new_summary)]
            )

    app.state.spanner_pool.database.run_in_transaction(_resolve_escalation)

    response = JSONResponse(content={"status": "resolved"})
    request_id = ensure_request_id(request, response)

    logger.info({
        "event": "governance_resolved_escalation",
        "scan_id": scan_id,
        "approved": payload.approved,
        "reviewer_user": redact_user_id(payload.reviewer_user_id),
        "request_id": request_id,
    })
    # TODO: if approved == True, finalize anchoring in orchestrator

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
                return JSONResponse(content={"status": "ok", "service": "governance", "database": "spanner"})
            else:
                return JSONResponse(content={"status": "degraded", "service": "governance", "database": "unhealthy"}, status_code=503)
    except Exception as e:
        logger.error({"event": "health_check_failed", "error": str(e)})
        metrics.update_health("database", False)
        return JSONResponse(content={"status": "degraded", "service": "governance", "database": "error"}, status_code=503)
    return JSONResponse(content={"status": "error", "service": "governance", "message": "no_spanner_pool"}, status_code=503)


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_metrics(),
        media_type="text/plain; version=0.0.4"
    )
