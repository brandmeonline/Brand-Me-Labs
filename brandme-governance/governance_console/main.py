import datetime as dt
import uuid
from typing import Optional, List
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id

logger = get_logger("governance_console")

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
    logger.info({"event": "governance_startup", "pool_ready": True})
    yield
    await pool.close()
    logger.info({"event": "governance_shutdown"})


app = FastAPI(lifespan=lifespan)


class GovernanceDecision(BaseModel):
    approved: bool
    reviewer_user_id: str
    note: str


@app.get("/governance/escalations")
async def get_escalations(request: Request):
    """
    Returns a list of pending escalations.
    SELECT from audit_log WHERE escalated_to_human = TRUE AND human_approver_id IS NULL
    """
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

    # Build response
    response = JSONResponse(escalations)

    # Ensure request_id
    request_id = ensure_request_id(request, response)

    # Log
    logger.info({
        "event": "governance_list_escalations",
        "number_of_pending": len(escalations),
        "request_id": request_id
    })

    return response


@app.post("/governance/escalations/{scan_id}/decision")
async def resolve_escalation(scan_id: str, decision: GovernanceDecision, request: Request):
    """
    Approve or deny an escalation.
    UPDATE audit_log SET human_approver_id, decision_summary, decision_detail, escalated_to_human = FALSE
    """
    async with pool.acquire() as conn:
        # Get current decision_detail
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
            response = JSONResponse({"error": "escalation not found or already resolved"}, status_code=404)
            request_id = ensure_request_id(request, response)
            return response

        decision_detail = row["decision_detail"]
        decision_summary = row["decision_summary"]

        # Update decision_detail with governance note
        decision_detail["governance_note"] = decision.note
        decision_detail["governance_approved"] = decision.approved

        # Update decision_summary
        new_decision_summary = decision_summary + " / human_decision"

        # Update audit_log
        await conn.execute(
            """
            UPDATE audit_log
            SET human_approver_id = $1,
                decision_summary = $2,
                decision_detail = $3,
                escalated_to_human = FALSE
            WHERE scan_id = $4 AND escalated_to_human = TRUE AND human_approver_id IS NULL
            """,
            decision.reviewer_user_id,
            new_decision_summary,
            decision_detail,
            scan_id
        )

    # TODO: if approved == True:
    #   In future, tell orchestrator to proceed with anchoring.
    # if approved == False:
    #   do nothing further; scan remains unanchored / denied.

    # Build response
    response = JSONResponse({"status": "resolved"})

    # Ensure request_id
    request_id = ensure_request_id(request, response)

    # Log (NEVER log private facet data, price history, or identity PII)
    logger.info({
        "event": "governance_decision",
        "scan_id": scan_id,
        "reviewer_user_redacted": redact_user_id(decision.reviewer_user_id),
        "approved": decision.approved,
        "request_id": request_id
    })

    return response
