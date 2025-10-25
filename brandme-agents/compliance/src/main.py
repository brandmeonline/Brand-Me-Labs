"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Compliance & Audit Service
===========================

Hash-chained audit logging and regulator view service.

Key Features:
- Tamper-evident hash-chained audit log
- Dual approval for private data reveals
- Regulator read-only access
- Explainable audit trails
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import asyncpg
import hashlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime
import os
from dotenv import load_dotenv
import json

load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
)
logger = logging.getLogger(__name__)

# Database pool
db_pool: Optional[asyncpg.Pool] = None


# ==========================================
# Pydantic Models
# ==========================================

class AuditLogRequest(BaseModel):
    scan_id: str
    decision_summary: str
    decision_detail: Dict[str, Any]
    risk_flagged: bool = False
    escalated_to_human: bool = False
    human_approver_id: Optional[str] = None


class ChainAnchorRequest(BaseModel):
    scan_id: str
    cardano_tx_hash: str
    midnight_tx_hash: str
    crosschain_root_hash: str


class AuditExplanation(BaseModel):
    scan_id: str
    human_readable_explanation: str
    cardano_tx_hash: Optional[str] = None
    midnight_tx_hash: Optional[str] = None
    crosschain_root_hash: Optional[str] = None
    policy_version: Optional[str] = None
    resolved_scope: Optional[str] = None
    decision_summary: Optional[str] = None
    occurred_at: Optional[datetime] = None


# ==========================================
# Database Functions
# ==========================================

async def init_db_pool():
    """Initialize database connection pool"""
    global db_pool
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    db_pool = await asyncpg.create_pool(database_url, min_size=5, max_size=20)
    logger.info("Database pool initialized")


async def close_db_pool():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database pool closed")


async def get_latest_audit_hash() -> Optional[str]:
    """Get the entry_hash of the most recent audit log entry"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT entry_hash FROM audit_log ORDER BY created_at DESC LIMIT 1"
        )
        return row['entry_hash'] if row else None


async def compute_entry_hash(
    audit_id: str,
    created_at: datetime,
    actor_type: str,
    action_type: str,
    decision_summary: str,
    decision_detail: dict,
    policy_version: str,
    prev_hash: Optional[str]
) -> str:
    """
    Compute SHA256 hash of audit entry

    This creates a tamper-evident hash chain where each entry
    references the hash of the previous entry.
    """
    hash_input = (
        str(audit_id) +
        str(created_at) +
        actor_type +
        action_type +
        decision_summary +
        json.dumps(decision_detail, sort_keys=True) +
        policy_version +
        (prev_hash or "")
    )

    return hashlib.sha256(hash_input.encode()).hexdigest()


async def insert_audit_log(
    scan_id: str,
    decision_summary: str,
    decision_detail: dict,
    risk_flagged: bool = False,
    escalated_to_human: bool = False,
    human_approver_id: Optional[str] = None
) -> str:
    """
    Insert audit log entry with hash chaining

    Returns the audit_id of the new entry
    """
    async with db_pool.acquire() as conn:
        # Get the latest audit hash for chaining
        prev_hash = await get_latest_audit_hash()

        # Get policy version from scan_event
        scan_row = await conn.fetchrow(
            "SELECT policy_version FROM scan_event WHERE scan_id = $1",
            scan_id
        )

        policy_version = scan_row['policy_version'] if scan_row else "unknown"

        # Generate audit_id
        import uuid
        audit_id = str(uuid.uuid4())
        created_at = datetime.utcnow()

        # Compute entry hash
        entry_hash = await compute_entry_hash(
            audit_id=audit_id,
            created_at=created_at,
            actor_type="system",
            action_type="scan",
            decision_summary=decision_summary,
            decision_detail=decision_detail,
            policy_version=policy_version,
            prev_hash=prev_hash
        )

        # Insert audit log
        await conn.execute(
            """
            INSERT INTO audit_log (
                audit_id,
                related_scan_id,
                created_at,
                actor_type,
                action_type,
                decision_summary,
                decision_detail,
                risk_flagged,
                escalated_to_human,
                human_approver_id,
                policy_version,
                prev_hash,
                entry_hash,
                region_code
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            """,
            audit_id,
            scan_id,
            created_at,
            "system",
            "scan",
            decision_summary,
            json.dumps(decision_detail),
            risk_flagged,
            escalated_to_human,
            human_approver_id,
            policy_version,
            prev_hash,
            entry_hash,
            "us-east1"  # TODO: Get from request
        )

        logger.info(f"Inserted audit log: audit_id={audit_id}, prev_hash={prev_hash[:8] if prev_hash else 'NULL'}")

        return audit_id


async def update_audit_with_chain_anchor(
    scan_id: str,
    cardano_tx_hash: str,
    midnight_tx_hash: str,
    crosschain_root_hash: str
):
    """
    Update audit log with blockchain anchor references

    This links the audit trail to on-chain proof
    """
    async with db_pool.acquire() as conn:
        # Create chain_anchor entry (if not already exists)
        try:
            await conn.execute(
                """
                INSERT INTO chain_anchor (
                    scan_id,
                    cardano_tx_hash,
                    midnight_tx_hash,
                    crosschain_root_hash
                ) VALUES ($1, $2, $3, $4)
                ON CONFLICT (scan_id, anchor_type) DO UPDATE
                SET
                    cardano_tx_hash = EXCLUDED.cardano_tx_hash,
                    midnight_tx_hash = EXCLUDED.midnight_tx_hash,
                    crosschain_root_hash = EXCLUDED.crosschain_root_hash,
                    anchored_at = NOW()
                """,
                scan_id,
                cardano_tx_hash,
                midnight_tx_hash,
                crosschain_root_hash
            )

            logger.info(f"Updated chain anchor for scan_id={scan_id}")

        except Exception as e:
            logger.error(f"Error updating chain anchor: {e}")
            raise


async def get_audit_explanation(scan_id: str) -> Optional[AuditExplanation]:
    """
    Get human-readable audit explanation for a scan

    Includes:
    - Policy decision
    - Blockchain references
    - Human-readable summary
    """
    async with db_pool.acquire() as conn:
        # Get scan event
        scan_row = await conn.fetchrow(
            """
            SELECT
                scan_id,
                resolved_scope,
                policy_version,
                occurred_at
            FROM scan_event
            WHERE scan_id = $1
            """,
            scan_id
        )

        if not scan_row:
            return None

        # Get chain anchor
        chain_row = await conn.fetchrow(
            """
            SELECT
                cardano_tx_hash,
                midnight_tx_hash,
                crosschain_root_hash
            FROM chain_anchor
            WHERE scan_id = $1
            """,
            scan_id
        )

        # Get audit log
        audit_row = await conn.fetchrow(
            """
            SELECT decision_summary
            FROM audit_log
            WHERE related_scan_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            scan_id
        )

        # Build human-readable explanation
        explanation = f"Scan {scan_id} was processed with {scan_row['resolved_scope']} visibility scope. "

        if chain_row:
            explanation += f"The scan result was anchored to Cardano (tx: {chain_row['cardano_tx_hash'][:16]}...) "
            explanation += f"and Midnight (tx: {chain_row['midnight_tx_hash'][:16]}...). "

        if audit_row:
            explanation += f"Decision: {audit_row['decision_summary']}"

        return AuditExplanation(
            scan_id=scan_id,
            human_readable_explanation=explanation,
            cardano_tx_hash=chain_row['cardano_tx_hash'] if chain_row else None,
            midnight_tx_hash=chain_row['midnight_tx_hash'] if chain_row else None,
            crosschain_root_hash=chain_row['crosschain_root_hash'] if chain_row else None,
            policy_version=scan_row['policy_version'],
            resolved_scope=scan_row['resolved_scope'],
            decision_summary=audit_row['decision_summary'] if audit_row else None,
            occurred_at=scan_row['occurred_at']
        )


async def verify_audit_chain_integrity() -> dict:
    """
    Verify the integrity of the hash-chained audit log

    Returns:
    - total_entries: Total number of audit log entries
    - valid_links: Number of valid hash chain links
    - broken_links: Number of broken links (indicates tampering)
    - chain_is_intact: Boolean indicating if chain is intact
    """
    async with db_pool.acquire() as conn:
        result = await conn.fetchrow("SELECT * FROM v_audit_chain_integrity")

        return {
            "total_entries": result['total_entries'],
            "valid_links": result['valid_links'],
            "broken_links": result['broken_links'],
            "chain_is_intact": result['chain_is_intact']
        }


# ==========================================
# FastAPI App
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    # Startup
    await init_db_pool()
    yield
    # Shutdown
    await close_db_pool()


app = FastAPI(
    title="Brand.Me Compliance & Audit Service",
    description="Hash-chained audit logging and regulator view",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# API Endpoints
# ==========================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "brandme-compliance",
        "database": "connected" if db_pool else "disconnected"
    }


@app.post("/audit/log")
async def log_audit(request: AuditLogRequest):
    """
    Log audit entry with hash chaining

    This creates a tamper-evident record of every decision.
    Each entry is linked to the previous entry via SHA256 hash.
    """
    try:
        audit_id = await insert_audit_log(
            scan_id=request.scan_id,
            decision_summary=request.decision_summary,
            decision_detail=request.decision_detail,
            risk_flagged=request.risk_flagged,
            escalated_to_human=request.escalated_to_human,
            human_approver_id=request.human_approver_id
        )

        return {
            "status": "success",
            "audit_id": audit_id,
            "message": "Audit log entry created"
        }

    except Exception as e:
        logger.error(f"Error logging audit: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/audit/anchorChain")
async def anchor_chain(request: ChainAnchorRequest):
    """
    Update audit log with blockchain anchor references

    Links the audit trail to on-chain proof.
    """
    try:
        await update_audit_with_chain_anchor(
            scan_id=request.scan_id,
            cardano_tx_hash=request.cardano_tx_hash,
            midnight_tx_hash=request.midnight_tx_hash,
            crosschain_root_hash=request.crosschain_root_hash
        )

        return {
            "status": "success",
            "scan_id": request.scan_id,
            "message": "Chain anchor updated"
        }

    except Exception as e:
        logger.error(f"Error anchoring chain: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/audit/{scan_id}/explain", response_model=AuditExplanation)
async def explain_audit(scan_id: str):
    """
    Get human-readable audit explanation

    Returns:
    - Policy decision summary
    - Blockchain transaction hashes
    - Human-readable explanation
    - Timestamp

    This endpoint is used by:
    - Governance Console (full access)
    - Transparency Portal (sanitized public view)
    - Regulator Portal (read-only audit trail)
    """
    try:
        explanation = await get_audit_explanation(scan_id)

        if not explanation:
            raise HTTPException(status_code=404, detail=f"Audit trail not found for scan: {scan_id}")

        return explanation

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting audit explanation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/audit/verify-integrity")
async def verify_integrity():
    """
    Verify hash chain integrity

    Returns statistics about the audit log hash chain:
    - Total entries
    - Valid links
    - Broken links
    - Overall integrity status

    This is used by:
    - Governance Console (integrity monitoring)
    - Automated integrity checks
    - Security audits
    """
    try:
        integrity = await verify_audit_chain_integrity()
        return integrity

    except Exception as e:
        logger.error(f"Error verifying integrity: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8102)
