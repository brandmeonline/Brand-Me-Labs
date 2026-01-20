# Copyright (c) Brand.Me, Inc. All rights reserved.
"""
Celery Tasks for Brand.Me Orchestrator
=======================================

Async tasks for scan processing, blockchain integration, and audit logging.
v8: Updated to use Spanner instead of PostgreSQL.
"""

import os
import json
import asyncio
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from uuid import UUID

import httpx
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded, Retry

from brandme.orchestrator.celery_app import app
from brandme_core.logging import get_logger, redact_user_id
from brandme_core.spanner.pool import create_pool_manager
from google.cloud import spanner

logger = get_logger("orchestrator")


# Spanner connection pool (lazy initialization, v8)
_spanner_pool = None

SPANNER_PROJECT = os.getenv("SPANNER_PROJECT_ID", "test-project")
SPANNER_INSTANCE = os.getenv("SPANNER_INSTANCE_ID", "brandme-instance")
SPANNER_DATABASE = os.getenv("SPANNER_DATABASE_ID", "brandme-db")


def get_spanner_pool():
    """Get or create Spanner connection pool (v8)."""
    global _spanner_pool
    if _spanner_pool is None:
        _spanner_pool = create_pool_manager(
            project_id=SPANNER_PROJECT,
            instance_id=SPANNER_INSTANCE,
            database_id=SPANNER_DATABASE
        )
        # Note: For sync Celery tasks, we use the synchronous Spanner client
    return _spanner_pool


class AsyncTask(Task):
    """
    Base task that supports async/await.

    Uses the decorated function as the async implementation.
    The `run` method is the actual task function, and we wrap it
    to run in an event loop.
    """
    _is_async = True

    def __call__(self, *args, **kwargs):
        """Execute the async task in an event loop."""
        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # The decorated function becomes self.run
        if asyncio.iscoroutinefunction(self.run):
            return loop.run_until_complete(self.run(*args, **kwargs))
        else:
            # Fallback for synchronous tasks
            return self.run(*args, **kwargs)


@app.task(
    bind=True,
    base=AsyncTask,
    name="brandme.orchestrator.tasks.persist_scan_event",
    max_retries=3,
    default_retry_delay=60,
)
async def persist_scan_event(
    self,
    scan_id: str,
    scanner_user_id: str,
    garment_id: str,
    resolved_scope: str,
    policy_version: str,
    decision_summary: str,
    shown_facets: List[Dict[str, Any]],
    region_code: str,
    risk_flagged: bool = False,
    escalated_to_human: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Persist scan event to database.

    Args:
        scan_id: UUID of the scan event
        scanner_user_id: UUID of user who scanned
        garment_id: UUID of garment scanned
        resolved_scope: Visibility scope (public/friends_only/private)
        policy_version: SHA256 hash of policy used
        decision_summary: Human-readable decision
        shown_facets: Array of facet objects shown
        region_code: Region where scan occurred
        risk_flagged: Whether scan was flagged for review
        escalated_to_human: Whether human review required

    Returns:
        Status dictionary
    """
    try:
        # v8: Use Spanner instead of PostgreSQL
        spanner_pool = get_spanner_pool()

        def _insert_scan_event(transaction):
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
                    audit_id, scan_id, "user", "scan",
                    f"scan_by_{scanner_user_id[:8]}", decision_summary,
                    risk_flagged, escalated_to_human, policy_version, region_code,
                    "", "",  # Hash chaining done by compliance service
                    spanner.COMMIT_TIMESTAMP
                )]
            )

        spanner_pool.database.run_in_transaction(_insert_scan_event)

        logger.info(
            "Scan event persisted",
            extra={
                "scan_id": scan_id,
                "scanner_user_id": redact_user_id(scanner_user_id),
                "garment_id": garment_id[:8] + "…",
                "resolved_scope": resolved_scope,
                "task_id": self.request.id,
            },
        )

        return {
            "status": "persisted",
            "scan_id": scan_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.error(
            f"Failed to persist scan event: {exc}",
            extra={
                "scan_id": scan_id,
                "error": str(exc),
                "task_id": self.request.id,
            },
        )
        raise self.retry(exc=exc, countdown=60)


@app.task(
    bind=True,
    base=AsyncTask,
    name="brandme.orchestrator.tasks.fetch_facets",
    max_retries=3,
)
async def fetch_facets(
    self,
    garment_id: str,
    scope: str,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch filtered facets from knowledge service.

    Args:
        garment_id: UUID of garment
        scope: Visibility scope (public/friends_only/private)
        request_id: Optional request ID for tracing

    Returns:
        Facets dictionary
    """
    try:
        knowledge_service_url = os.getenv(
            "KNOWLEDGE_SERVICE_URL",
            "http://knowledge:8101"
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{knowledge_service_url}/garment/{garment_id}/passport",
                params={"scope": scope},
                headers={"X-Request-Id": request_id} if request_id else {},
            )
            response.raise_for_status()
            facets = response.json()

        logger.info(
            "Facets fetched from knowledge service",
            extra={
                "garment_id": garment_id[:8] + "…",
                "scope": scope,
                "facet_count": len(facets.get("facets", [])),
                "request_id": request_id,
                "task_id": self.request.id,
            },
        )

        return facets

    except httpx.HTTPStatusError as exc:
        logger.error(
            f"Knowledge service HTTP error: {exc}",
            extra={
                "garment_id": garment_id[:8] + "…",
                "status_code": exc.response.status_code,
                "task_id": self.request.id,
            },
        )
        raise self.retry(exc=exc, countdown=30)

    except Exception as exc:
        logger.error(
            f"Failed to fetch facets: {exc}",
            extra={
                "garment_id": garment_id[:8] + "…",
                "error": str(exc),
                "task_id": self.request.id,
            },
        )
        raise self.retry(exc=exc, countdown=60)


@app.task(
    bind=True,
    base=AsyncTask,
    name="brandme.orchestrator.tasks.submit_blockchain_tx",
    max_retries=5,
    default_retry_delay=120,
)
async def submit_blockchain_tx(
    self,
    scan_id: str,
    garment_id: str,
    authenticity_hash: str,
    metadata: Dict[str, Any],
    network: str = "cardano",
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Submit blockchain transaction for provenance anchoring.

    Args:
        scan_id: UUID of scan event
        garment_id: UUID of garment
        authenticity_hash: Immutable provenance hash
        metadata: Additional metadata to anchor
        network: Blockchain network (cardano/midnight)
        request_id: Optional request ID for tracing

    Returns:
        Transaction details
    """
    try:
        chain_service_url = os.getenv("CHAIN_SERVICE_URL", "http://chain:3001")

        payload = {
            "garment_id": garment_id,
            "authenticity_hash": authenticity_hash,
            "metadata": metadata,
            "network": network,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{chain_service_url}/tx/submit",
                json=payload,
                headers={"X-Request-Id": request_id} if request_id else {},
            )
            response.raise_for_status()
            tx_result = response.json()

        # Log blockchain anchor (v8: now synchronous with Spanner)
        log_blockchain_anchor(
            scan_id=scan_id,
            cardano_tx_hash=tx_result.get("tx_hash") if network == "cardano" else None,
            midnight_tx_hash=tx_result.get("tx_hash") if network == "midnight" else None,
        )

        logger.info(
            "Blockchain transaction submitted",
            extra={
                "scan_id": scan_id,
                "garment_id": garment_id[:8] + "…",
                "network": network,
                "tx_hash": tx_result.get("tx_hash", "")[:16] + "…",
                "request_id": request_id,
                "task_id": self.request.id,
            },
        )

        return tx_result

    except httpx.HTTPStatusError as exc:
        if exc.response.status_code >= 500:
            # Retry on server errors
            raise self.retry(exc=exc, countdown=120)
        else:
            # Don't retry on client errors
            logger.error(
                f"Blockchain submission failed: {exc}",
                extra={
                    "scan_id": scan_id,
                    "status_code": exc.response.status_code,
                    "task_id": self.request.id,
                },
            )
            raise

    except Exception as exc:
        logger.error(
            f"Failed to submit blockchain tx: {exc}",
            extra={
                "scan_id": scan_id,
                "error": str(exc),
                "task_id": self.request.id,
            },
        )
        raise self.retry(exc=exc, countdown=120)


@app.task(
    bind=True,
    base=AsyncTask,
    name="brandme.orchestrator.tasks.log_audit_entry",
    max_retries=3,
)
async def log_audit_entry(
    self,
    scan_id: str,
    decision_summary: str,
    decision_detail: Dict[str, Any],
    risk_flagged: bool = False,
    escalated_to_human: bool = False,
    human_approver_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Log hash-chained audit entry to compliance service.

    Args:
        scan_id: UUID of scan event
        decision_summary: Human-readable decision
        decision_detail: Full decision context
        risk_flagged: Whether scan was flagged
        escalated_to_human: Whether human review occurred
        human_approver_id: UUID of approver if escalated
        request_id: Optional request ID for tracing

    Returns:
        Audit entry details
    """
    try:
        compliance_service_url = os.getenv(
            "COMPLIANCE_SERVICE_URL",
            "http://compliance:8102"
        )

        payload = {
            "scan_id": scan_id,
            "decision_summary": decision_summary,
            "decision_detail": decision_detail,
            "risk_flagged": risk_flagged,
            "escalated_to_human": escalated_to_human,
            "human_approver_id": human_approver_id,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{compliance_service_url}/audit/log",
                json=payload,
                headers={"X-Request-Id": request_id} if request_id else {},
            )
            response.raise_for_status()
            audit_result = response.json()

        logger.info(
            "Audit entry logged",
            extra={
                "scan_id": scan_id,
                "entry_hash": audit_result.get("entry_hash", "")[:16] + "…",
                "risk_flagged": risk_flagged,
                "escalated": escalated_to_human,
                "request_id": request_id,
                "task_id": self.request.id,
            },
        )

        return audit_result

    except Exception as exc:
        logger.error(
            f"Failed to log audit entry: {exc}",
            extra={
                "scan_id": scan_id,
                "error": str(exc),
                "task_id": self.request.id,
            },
        )
        raise self.retry(exc=exc, countdown=60)


def log_blockchain_anchor(
    scan_id: str,
    cardano_tx_hash: Optional[str] = None,
    midnight_tx_hash: Optional[str] = None,
) -> None:
    """Helper to log blockchain anchor to Spanner (v8)."""
    spanner_pool = get_spanner_pool()

    def _insert_anchor(transaction):
        anchor_id = str(uuid.uuid4())
        transaction.insert(
            table="ChainAnchor",
            columns=[
                "anchor_id", "scan_id", "cardano_tx_hash",
                "midnight_tx_hash", "anchored_at"
            ],
            values=[(
                anchor_id, scan_id, cardano_tx_hash,
                midnight_tx_hash, spanner.COMMIT_TIMESTAMP
            )]
        )

    spanner_pool.database.run_in_transaction(_insert_anchor)


@app.task(
    bind=True,
    base=AsyncTask,
    name="brandme.orchestrator.tasks.send_notification",
)
async def send_notification(
    self,
    user_id: str,
    notification_type: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send notification to user.

    Args:
        user_id: UUID of user
        notification_type: Type of notification (scan_complete, escalation, etc.)
        message: Notification message
        metadata: Additional context

    Returns:
        Status dictionary
    """
    # TODO: Implement notification service integration
    # For now, just log
    logger.info(
        "Notification queued",
        extra={
            "user_id": redact_user_id(user_id),
            "type": notification_type,
            "task_id": self.request.id,
        },
    )

    return {
        "status": "queued",
        "user_id": user_id,
        "type": notification_type,
    }


# Periodic Tasks


@app.task(
    bind=True,
    base=AsyncTask,
    name="brandme.orchestrator.tasks.cleanup_expired_scans",
)
async def cleanup_expired_scans(self) -> Dict[str, int]:
    """Clean up expired scan results from cache."""
    # TODO: Implement Redis cleanup
    logger.info("Scan cleanup task executed", extra={"task_id": self.request.id})
    return {"cleaned": 0}


@app.task(
    bind=True,
    base=AsyncTask,
    name="brandme.orchestrator.tasks.verify_audit_chain_integrity",
)
async def verify_audit_chain_integrity(self) -> Dict[str, Any]:
    """Verify integrity of hash-chained audit log."""
    try:
        compliance_service_url = os.getenv(
            "COMPLIANCE_SERVICE_URL",
            "http://compliance:8102"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{compliance_service_url}/audit/verify-integrity"
            )
            response.raise_for_status()
            result = response.json()

        if not result.get("valid", False):
            logger.error(
                "Audit chain integrity violation detected!",
                extra={
                    "task_id": self.request.id,
                    "details": result,
                },
            )
        else:
            logger.info(
                "Audit chain integrity verified",
                extra={"task_id": self.request.id},
            )

        return result

    except Exception as exc:
        logger.error(
            f"Failed to verify audit chain: {exc}",
            extra={
                "error": str(exc),
                "task_id": self.request.id,
            },
        )
        return {"valid": False, "error": str(exc)}


@app.task(
    bind=True,
    base=AsyncTask,
    name="brandme.orchestrator.tasks.sync_blockchain_state",
)
async def sync_blockchain_state(self) -> Dict[str, Any]:
    """Sync blockchain state and verify anchored transactions."""
    # TODO: Implement blockchain state synchronization
    logger.info(
        "Blockchain sync task executed",
        extra={"task_id": self.request.id}
    )
    return {"synced": 0}


# Workflow Tasks


@app.task(
    bind=True,
    name="brandme.orchestrator.tasks.process_scan_workflow",
)
def process_scan_workflow(
    self,
    scan_id: str,
    scanner_user_id: str,
    garment_id: str,
    resolved_scope: str,
    policy_version: str,
    decision_summary: str,
    region_code: str,
    authenticity_hash: str,
    risk_flagged: bool = False,
    escalated_to_human: bool = False,
    request_id: Optional[str] = None,
):
    """
    Execute full scan processing workflow.

    Orchestrates:
    1. Fetch facets from knowledge service
    2. Persist scan event to database
    3. Submit blockchain transaction
    4. Log audit entry
    5. Send notification to user
    """
    from celery import chain, group

    # Build workflow chain
    workflow = chain(
        # Step 1: Fetch facets in parallel with persistence
        group(
            fetch_facets.s(garment_id, resolved_scope, request_id),
            persist_scan_event.s(
                scan_id=scan_id,
                scanner_user_id=scanner_user_id,
                garment_id=garment_id,
                resolved_scope=resolved_scope,
                policy_version=policy_version,
                decision_summary=decision_summary,
                shown_facets=[],  # Will be updated after facets fetched
                region_code=region_code,
                risk_flagged=risk_flagged,
                escalated_to_human=escalated_to_human,
                request_id=request_id,
            ),
        ),

        # Step 2: Submit blockchain TX
        submit_blockchain_tx.s(
            scan_id=scan_id,
            garment_id=garment_id,
            authenticity_hash=authenticity_hash,
            metadata={"region": region_code, "scope": resolved_scope},
            request_id=request_id,
        ),

        # Step 3: Log audit entry
        log_audit_entry.s(
            scan_id=scan_id,
            decision_summary=decision_summary,
            decision_detail={"scope": resolved_scope, "region": region_code},
            risk_flagged=risk_flagged,
            escalated_to_human=escalated_to_human,
            request_id=request_id,
        ),

        # Step 4: Send notification
        send_notification.s(
            user_id=scanner_user_id,
            notification_type="scan_complete",
            message=f"Scan {scan_id} processed successfully",
        ),
    )

    # Execute workflow
    result = workflow.apply_async()

    logger.info(
        "Scan workflow initiated",
        extra={
            "scan_id": scan_id,
            "workflow_id": result.id,
            "request_id": request_id,
            "task_id": self.request.id,
        },
    )

    return {"workflow_id": result.id, "scan_id": scan_id}
