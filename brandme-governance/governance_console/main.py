# Brand.Me v6 — Stable Integrity Spine
# Implements: Request tracing, human escalation guardrails, safe facet previews.
# brandme-governance/governance_console/main.py

from typing import List
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
import asyncpg

from brandme_core.logging import get_logger, redact_user_id, ensure_request_id

logger = get_logger("governance_console")




class GovernanceDecisionRequest(BaseModel):
    approved: bool
    reviewer_user_id: str
    note: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.db_pool = await asyncpg.create_pool(
        host="postgres",
        port=5432,
        database="brandme",
        user="postgres",
        password="postgres",
        min_size=5,
        max_size=20,
    )
    logger.info({"event": "governance_console_started"})
    yield
    # Shutdown
    await app.state.db_pool.close()
    logger.info({"event": "governance_console_stopped"})


app = FastAPI(lifespan=lifespan)

# v6 fix: CORS for public-facing governance console
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO tighten in prod
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/governance/escalations")
async def get_escalations(request: Request):
    """
    List pending escalations requiring human review.
    NEVER expose facet bodies, only high-level escalation metadata.
    NEVER log PII.
    """
    async with app.state.db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                al.related_scan_id AS scan_id,
                (al.decision_detail->>'reason') AS reason,
                (al.decision_detail->>'region_code') AS region_code,
                al.created_at
            FROM audit_log al
            WHERE al.escalated_to_human = TRUE
              AND al.human_approver_id IS NULL
            ORDER BY al.created_at DESC
            """
        )

    escalations = [
        {
            "scan_id": row["scan_id"],
            "region_code": row["region_code"],
            "reason": row["reason"],
            "created_at": row["created_at"].isoformat() + "Z" if row["created_at"] else None,
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
    TODO: if approved == True, in future tell orchestrator to finalize anchoring for this scan_id.
    """
    async with app.state.db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE audit_log
            SET human_approver_id = $1,
                escalated_to_human = FALSE,
                decision_summary = decision_summary || ' / human_decision',
                decision_detail = jsonb_set(
                    decision_detail,
                    '{governance_note}',
                    to_jsonb($2::text),
                    true
                )
            WHERE related_scan_id = $3
              AND escalated_to_human = TRUE
              AND human_approver_id IS NULL
            """,
            payload.reviewer_user_id,
            payload.note,
            scan_id,
        )

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
    return JSONResponse(content={"status": "ok"})
