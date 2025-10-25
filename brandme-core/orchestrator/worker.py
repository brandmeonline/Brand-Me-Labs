"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Orchestrator Worker (Celery)
============================

Coordinates workflows when policy decisions are "allow":
1. Insert scan_event row
2. Fetch allowed facets from Knowledge Service
3. Call Chain Service to anchor to blockchains
4. Log audit trail via Compliance Service
"""

from celery import Celery
import asyncpg
import httpx
import logging
import os
from dotenv import load_dotenv
import json
from datetime import datetime
import nats
from nats.js import JetStreamContext
import asyncio

load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
)
logger = logging.getLogger(__name__)

# Celery app
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery('orchestrator', broker=redis_url, backend=redis_url)

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL")

# Service URLs
KNOWLEDGE_SERVICE_URL = os.getenv("KNOWLEDGE_SERVICE_URL", "http://localhost:8101")
CHAIN_SERVICE_URL = os.getenv("CHAIN_SERVICE_URL", "http://localhost:3001")
COMPLIANCE_SERVICE_URL = os.getenv("COMPLIANCE_SERVICE_URL", "http://localhost:8102")


# ==========================================
# Database Functions
# ==========================================

async def insert_scan_event(
    scan_id: str,
    scanner_user_id: str,
    garment_id: str,
    resolved_scope: str,
    policy_version: str,
    region_code: str,
    shown_facets: list
):
    """Insert scan event into database"""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            """
            INSERT INTO scan_event (
                scan_id, scanner_user_id, garment_id, occurred_at,
                resolved_scope, policy_version, region_code, shown_facets
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            scan_id,
            scanner_user_id,
            garment_id,
            datetime.utcnow(),
            resolved_scope,
            policy_version,
            region_code,
            json.dumps(shown_facets)
        )
        logger.info(f"Inserted scan_event: scan_id={scan_id}")
    finally:
        await conn.close()


async def update_chain_anchor(
    scan_id: str,
    cardano_tx_hash: str,
    midnight_tx_hash: str,
    crosschain_root_hash: str
):
    """Insert chain anchor record"""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            """
            INSERT INTO chain_anchor (
                scan_id, cardano_tx_hash, midnight_tx_hash, crosschain_root_hash
            ) VALUES ($1, $2, $3, $4)
            """,
            scan_id,
            cardano_tx_hash,
            midnight_tx_hash,
            crosschain_root_hash
        )
        logger.info(f"Inserted chain_anchor: scan_id={scan_id}")
    finally:
        await conn.close()


# ==========================================
# Service Calls
# ==========================================

async def fetch_allowed_facets(garment_id: str, scope: str) -> list:
    """
    Fetch allowed facets from Knowledge Service

    GET /garment/{garment_id}/passport?scope={scope}
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{KNOWLEDGE_SERVICE_URL}/garment/{garment_id}/passport",
                params={"scope": scope},
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch facets: {e}")
            return []


async def anchor_to_chains(
    scan_id: str,
    garment_id: str,
    allowed_facets: list,
    resolved_scope: str,
    policy_version: str
) -> dict:
    """
    Call Chain Service to anchor scan to blockchains

    POST /tx/anchor-scan
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{CHAIN_SERVICE_URL}/tx/anchor-scan",
                json={
                    "scan_id": scan_id,
                    "garment_id": garment_id,
                    "allowed_facets": allowed_facets,
                    "resolved_scope": resolved_scope,
                    "policy_version": policy_version
                },
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to anchor to chains: {e}")
            return {
                "cardano_tx_hash": "ERROR",
                "midnight_tx_hash": "ERROR",
                "crosschain_root_hash": "ERROR"
            }


async def log_audit_trail(
    scan_id: str,
    decision_summary: str,
    decision_detail: dict,
    risk_flagged: bool = False
):
    """
    Log audit trail via Compliance Service

    POST /audit/log
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{COMPLIANCE_SERVICE_URL}/audit/log",
                json={
                    "scan_id": scan_id,
                    "decision_summary": decision_summary,
                    "decision_detail": decision_detail,
                    "risk_flagged": risk_flagged,
                    "escalated_to_human": False
                },
                timeout=10.0
            )
            response.raise_for_status()
            logger.info(f"Logged audit trail: scan_id={scan_id}")
        except httpx.HTTPError as e:
            logger.error(f"Failed to log audit: {e}")


async def anchor_chain_reference(
    scan_id: str,
    cardano_tx_hash: str,
    midnight_tx_hash: str,
    crosschain_root_hash: str
):
    """
    Update audit log with chain anchor references

    POST /audit/anchorChain
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{COMPLIANCE_SERVICE_URL}/audit/anchorChain",
                json={
                    "scan_id": scan_id,
                    "cardano_tx_hash": cardano_tx_hash,
                    "midnight_tx_hash": midnight_tx_hash,
                    "crosschain_root_hash": crosschain_root_hash
                },
                timeout=10.0
            )
            response.raise_for_status()
            logger.info(f"Anchored chain reference: scan_id={scan_id}")
        except httpx.HTTPError as e:
            logger.error(f"Failed to anchor chain reference: {e}")


# ==========================================
# Celery Tasks
# ==========================================

@celery_app.task
def process_allowed_scan(event_data: dict):
    """
    Process scan when policy decision is "allow"

    This is the main orchestration task that:
    1. Inserts scan_event
    2. Fetches allowed facets
    3. Anchors to blockchains
    4. Logs audit trail
    """
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_process_allowed_scan_async(event_data))


async def _process_allowed_scan_async(event_data: dict):
    """Async implementation of process_allowed_scan"""
    scan_id = event_data.get('scan_id')
    scanner_user_id = event_data.get('scanner_user_id')
    garment_id = event_data.get('garment_id')
    resolved_scope = event_data.get('resolved_scope')
    policy_version = event_data.get('policy_version')
    region_code = event_data.get('region_code', 'us-east1')

    logger.info(f"Processing allowed scan: scan_id={scan_id}")

    try:
        # 1. Fetch allowed facets from Knowledge Service
        allowed_facets = await fetch_allowed_facets(garment_id, resolved_scope)
        logger.info(f"Fetched {len(allowed_facets)} allowed facets for scan_id={scan_id}")

        # 2. Insert scan_event into database
        await insert_scan_event(
            scan_id=scan_id,
            scanner_user_id=scanner_user_id,
            garment_id=garment_id,
            resolved_scope=resolved_scope,
            policy_version=policy_version,
            region_code=region_code,
            shown_facets=allowed_facets
        )

        # 3. Anchor to blockchains
        chain_result = await anchor_to_chains(
            scan_id=scan_id,
            garment_id=garment_id,
            allowed_facets=allowed_facets,
            resolved_scope=resolved_scope,
            policy_version=policy_version
        )

        cardano_tx_hash = chain_result.get('cardano_tx_hash')
        midnight_tx_hash = chain_result.get('midnight_tx_hash')
        crosschain_root_hash = chain_result.get('crosschain_root_hash')

        # 4. Update chain_anchor in database
        await update_chain_anchor(
            scan_id=scan_id,
            cardano_tx_hash=cardano_tx_hash,
            midnight_tx_hash=midnight_tx_hash,
            crosschain_root_hash=crosschain_root_hash
        )

        # 5. Log audit trail
        await log_audit_trail(
            scan_id=scan_id,
            decision_summary=f"Scan allowed for {resolved_scope} scope",
            decision_detail={
                "scanner_user_id": scanner_user_id,
                "garment_id": garment_id,
                "resolved_scope": resolved_scope,
                "policy_version": policy_version,
                "facet_count": len(allowed_facets)
            },
            risk_flagged=False
        )

        # 6. Anchor chain references to audit log
        await anchor_chain_reference(
            scan_id=scan_id,
            cardano_tx_hash=cardano_tx_hash,
            midnight_tx_hash=midnight_tx_hash,
            crosschain_root_hash=crosschain_root_hash
        )

        logger.info(f"Successfully processed scan: scan_id={scan_id}")

        return {
            "status": "success",
            "scan_id": scan_id,
            "facets_count": len(allowed_facets),
            "cardano_tx_hash": cardano_tx_hash,
            "midnight_tx_hash": midnight_tx_hash
        }

    except Exception as e:
        logger.error(f"Error processing scan: scan_id={scan_id}, error={e}")
        raise


# ==========================================
# NATS Consumer (Event-Driven)
# ==========================================

async def start_nats_consumer():
    """Start NATS consumer to listen for policy.decision events"""
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")

    nc = await nats.connect(nats_url)
    js = nc.jetstream()

    logger.info("Orchestrator NATS consumer started")

    async def message_handler(msg):
        """Handle policy.decision event"""
        try:
            data = json.loads(msg.data.decode())
            logger.info(f"Received policy.decision: scan_id={data.get('scan_id')}, decision={data.get('decision')}")

            # Only process if decision is "allow"
            if data.get('decision') == 'allow':
                # Trigger Celery task
                process_allowed_scan.delay(data)
                logger.info(f"Queued Celery task for scan_id={data.get('scan_id')}")

            await msg.ack()

        except Exception as e:
            logger.error(f"Error handling policy.decision event: {e}")
            await msg.nak()

    await js.subscribe(
        "policy.decision",
        cb=message_handler,
        durable="orchestrator-consumer",
        stream="SCANS"
    )

    # Keep running
    try:
        await asyncio.Future()
    except KeyboardInterrupt:
        logger.info("Shutting down orchestrator")
    finally:
        await nc.close()


if __name__ == "__main__":
    # Start NATS consumer
    asyncio.run(start_nats_consumer())
