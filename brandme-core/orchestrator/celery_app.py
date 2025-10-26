# Copyright (c) Brand.Me, Inc. All rights reserved.
"""
Celery Application Configuration
=================================

Celery app for async task orchestration across Brand.Me platform.

Tasks:
- Persist scan events to database
- Fetch filtered facets from knowledge service
- Submit blockchain transactions
- Log audit trail entries
- Send notifications
- Execute scheduled maintenance
"""

import os
from celery import Celery
from kombu import Exchange, Queue

# Initialize Celery app
app = Celery(
    "brandme",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
)

# Celery Configuration
app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes hard limit
    task_soft_time_limit=240,  # 4 minutes soft limit

    # Results
    result_expires=3600,  # 1 hour
    result_extended=True,

    # Worker settings
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=False,

    # Retry policy
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,

    # Routing
    task_default_queue="default",
    task_default_exchange="brandme",
    task_default_routing_key="default",

    # Queue definitions
    task_queues=(
        Queue("default", Exchange("brandme"), routing_key="default"),
        Queue("scans", Exchange("brandme"), routing_key="scan.#"),
        Queue("blockchain", Exchange("brandme"), routing_key="blockchain.#"),
        Queue("audit", Exchange("brandme"), routing_key="audit.#"),
        Queue("notifications", Exchange("brandme"), routing_key="notify.#"),
        Queue("priority", Exchange("brandme"), routing_key="priority.#", priority=10),
    ),

    # Task routes
    task_routes={
        "brandme.orchestrator.tasks.persist_scan_event": {
            "queue": "scans",
            "routing_key": "scan.persist",
        },
        "brandme.orchestrator.tasks.fetch_facets": {
            "queue": "scans",
            "routing_key": "scan.facets",
        },
        "brandme.orchestrator.tasks.submit_blockchain_tx": {
            "queue": "blockchain",
            "routing_key": "blockchain.submit",
        },
        "brandme.orchestrator.tasks.log_audit_entry": {
            "queue": "audit",
            "routing_key": "audit.log",
        },
        "brandme.orchestrator.tasks.send_notification": {
            "queue": "notifications",
            "routing_key": "notify.send",
        },
    },

    # Beat schedule for periodic tasks
    beat_schedule={
        "cleanup-expired-scans": {
            "task": "brandme.orchestrator.tasks.cleanup_expired_scans",
            "schedule": 3600.0,  # Every hour
        },
        "verify-audit-chain": {
            "task": "brandme.orchestrator.tasks.verify_audit_chain_integrity",
            "schedule": 86400.0,  # Every 24 hours
        },
        "sync-blockchain-state": {
            "task": "brandme.orchestrator.tasks.sync_blockchain_state",
            "schedule": 300.0,  # Every 5 minutes
        },
    },

    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Auto-discover tasks from installed apps
app.autodiscover_tasks(["brandme.orchestrator"])

if __name__ == "__main__":
    app.start()
