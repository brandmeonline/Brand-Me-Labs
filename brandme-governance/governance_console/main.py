"""
Brand.Me Governance Console
============================
Human review and approval for escalated scans.

Features:
- Database connection with retries
- Health check endpoints
- PII redaction in logs
- Escalation queue management
"""
import datetime as dt
from typing import Optional
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from brandme_core import (
    get_logger,
    redact_user_id,
    ensure_request_id,
    config,
    create_db_pool,
    safe_close_pool,
    DatabaseError,
)

logger = get_logger("governance_console")
pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    try:
        pool = await create_db_pool()
        logger.info("Governance console startup complete")
    except DatabaseError as e:
        logger.error("Database initialization failed", extra={"error": str(e)})
        if not config.ENABLE_STUB_MODE:
            raise

    yield
    await safe_close_pool(pool)
    logger.info("Governance console shutdown complete")


app = FastAPI(
    title="Brand.Me Governance Console",
    description="Human review and approval for escalated scans",
    version="2.0.0",
    lifespan=lifespan
)


class GovernanceDecision(BaseModel):
    approved: bool
    reviewer_user_id: str
    note: str


@app.get("/health")
async def health_check():
    health_status = {"service": "governance", "status": "healthy", "database": "unknown"}
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            health_status["database"] = "healthy"
        except Exception:
            health_status["database"] = "unhealthy"
            if not config.ENABLE_STUB_MODE:
                return JSONResponse(health_status, status_code=503)
    return JSONResponse(health_status)


@app.get("/governance/escalations")
async def get_escalations(request: Request):
    """
    Returns a list of pending escalations.
    SELECT from audit_log WHERE escalated_to_human = TRUE AND human_approver_id IS NULL
    """
    if not pool:
        raise HTTPException(503, "Database unavailable")

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT scan_id, decision_detail, created_at
                FROM audit_log
                WHERE escalated_to_human = TRUE AND human_approver_id IS NULL
                ORDER BY created_at ASC
                """
            )

            escalations = []
            for row in rows:
                decision_detail = row["decision_detail"]
                region_code = decision_detail.get("region_code", "unknown")
                reason = decision_detail.get("reason", "no reason provided")
                created_at = row["created_at"].isoformat() + "Z"

                escalations.append({
                    "scan_id": row["scan_id"],
                    "region_code": region_code,
                    "reason": reason,
                    "created_at": created_at
                })

        response = JSONResponse(escalations)
        request_id = ensure_request_id(request, response)

        logger.info({
            "event": "governance_list_escalations",
            "number_of_pending": len(escalations),
            "request_id": request_id
        })

        return response

    except Exception as e:
        logger.error("Failed to list escalations", extra={"error": str(e)})
        raise HTTPException(500, f"Failed to list escalations: {str(e)}")


@app.post("/governance/escalations/{scan_id}/decision")
async def resolve_escalation(scan_id: str, decision: GovernanceDecision, request: Request):
    """
    Approve or deny an escalation.
    UPDATE audit_log SET human_approver_id, decision_summary, decision_detail, escalated_to_human = FALSE
    """
    if not pool:
        raise HTTPException(503, "Database unavailable")

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT decision_detail, decision_summary
                FROM audit_log
                WHERE scan_id = $1 AND escalated_to_human = TRUE AND human_approver_id IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                scan_id
            )

            if not row:
                raise HTTPException(404, "Escalation not found or already resolved")

            decision_detail = dict(row["decision_detail"])
            decision_summary = row["decision_summary"]

            # Update decision_detail with governance note
            decision_detail["governance_note"] = decision.note
            decision_detail["governance_approved"] = decision.approved

            # Update decision_summary
            new_decision_summary = decision_summary + " / human_decision"

            # Update audit_log
            import json
            await conn.execute(
                """
                UPDATE audit_log
                SET human_approver_id = $1,
                    decision_summary = $2,
                    decision_detail = $3::jsonb,
                    escalated_to_human = FALSE
                WHERE scan_id = $4 AND escalated_to_human = TRUE AND human_approver_id IS NULL
                """,
                decision.reviewer_user_id,
                new_decision_summary,
                json.dumps(decision_detail),
                scan_id
            )

        # TODO: if approved == True: tell orchestrator to proceed with anchoring
        # TODO: if approved == False: scan remains unanchored / denied

        response = JSONResponse({"status": "resolved"})
        request_id = ensure_request_id(request, response)

        logger.info({
            "event": "governance_decision",
            "scan_id": scan_id,
            "reviewer_user_redacted": redact_user_id(decision.reviewer_user_id),
            "approved": decision.approved,
            "request_id": request_id
        })

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to resolve escalation", extra={"error": str(e)})
        raise HTTPException(500, f"Failed to resolve escalation: {str(e)}")
