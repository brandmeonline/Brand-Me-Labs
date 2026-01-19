# Copyright (c) Brand.Me, Inc. All rights reserved.
"""
Health Check Utilities
======================

Standardized health check endpoints for all Brand.Me services.
v8: Updated to support Spanner instead of PostgreSQL.

Features:
- Liveness probes (is service running?)
- Readiness probes (can service accept traffic?)
- Startup probes (has service fully initialized?)
- Dependency health checks (Spanner, redis, NATS)
"""

import asyncio
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timezone
from enum import Enum

import redis.asyncio as aioredis
from nats.aio.client import Client as NATS
from fastapi import FastAPI, Response, status
from fastapi.responses import JSONResponse


class HealthStatus(str, Enum):
    """Health check status enum."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthCheck:
    """Health check manager for services."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.start_time = datetime.now(timezone.utc)
        self.custom_checks: List[Callable] = []
        self.spanner_pool = None  # v8: Spanner pool instead of asyncpg
        self.redis_client: Optional[aioredis.Redis] = None
        self.nats_client: Optional[NATS] = None

    def register_spanner_pool(self, pool):
        """Register Spanner connection pool (v8)."""
        self.spanner_pool = pool

    def register_redis_client(self, client: aioredis.Redis):
        """Register Redis client."""
        self.redis_client = client

    def register_nats_client(self, client: NATS):
        """Register NATS client."""
        self.nats_client = client

    def add_custom_check(self, check_func: Callable):
        """Add custom health check function."""
        self.custom_checks.append(check_func)

    async def check_database(self) -> Dict[str, Any]:
        """Check Spanner database connectivity (v8)."""
        if not self.spanner_pool:
            return {"status": "not_configured", "healthy": True}

        try:
            def _health_check(transaction):
                results = transaction.execute_sql("SELECT 1")
                for row in results:
                    return True
                return False

            if self.spanner_pool.database:
                is_healthy = self.spanner_pool.database.run_in_transaction(_health_check)
                if is_healthy:
                    return {
                        "status": "healthy",
                        "healthy": True,
                        "database": "spanner",
                    }
        except Exception as e:
            return {
                "status": "unhealthy",
                "healthy": False,
                "error": str(e),
            }

        return {"status": "unhealthy", "healthy": False}

    async def check_redis(self) -> Dict[str, Any]:
        """Check Redis connectivity."""
        if not self.redis_client:
            return {"status": "not_configured", "healthy": True}

        try:
            await self.redis_client.ping()
            info = await self.redis_client.info("stats")
            return {
                "status": "healthy",
                "healthy": True,
                "total_connections": info.get("total_connections_received", 0),
                "connected_clients": info.get("connected_clients", 0),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "healthy": False,
                "error": str(e),
            }

    async def check_nats(self) -> Dict[str, Any]:
        """Check NATS connectivity."""
        if not self.nats_client:
            return {"status": "not_configured", "healthy": True}

        try:
            if self.nats_client.is_connected:
                return {
                    "status": "healthy",
                    "healthy": True,
                    "connected": True,
                }
            else:
                return {
                    "status": "unhealthy",
                    "healthy": False,
                    "connected": False,
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "healthy": False,
                "error": str(e),
            }

    async def liveness(self) -> Dict[str, Any]:
        """
        Liveness probe - Is the service running?

        Returns 200 if the service is alive, 503 if dead.
        Kubernetes will restart the pod if this fails.
        """
        return {
            "status": "alive",
            "service": self.service_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def readiness(self) -> Dict[str, Any]:
        """
        Readiness probe - Can the service accept traffic?

        Returns 200 if ready, 503 if not ready.
        Kubernetes will remove pod from load balancer if this fails.
        """
        checks = {}
        overall_healthy = True

        # Check database
        db_health = await self.check_database()
        checks["database"] = db_health
        if not db_health.get("healthy", False):
            overall_healthy = False

        # Check Redis
        redis_health = await self.check_redis()
        checks["redis"] = redis_health
        if not redis_health.get("healthy", False):
            overall_healthy = False

        # Check NATS
        nats_health = await self.check_nats()
        checks["nats"] = nats_health
        if not nats_health.get("healthy", False):
            overall_healthy = False

        # Run custom checks
        for check_func in self.custom_checks:
            try:
                check_result = await check_func()
                checks[check_func.__name__] = check_result
                if not check_result.get("healthy", False):
                    overall_healthy = False
            except Exception as e:
                checks[check_func.__name__] = {
                    "status": "error",
                    "healthy": False,
                    "error": str(e),
                }
                overall_healthy = False

        return {
            "status": "ready" if overall_healthy else "not_ready",
            "service": self.service_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
            "overall_healthy": overall_healthy,
        }

    async def startup(self) -> Dict[str, Any]:
        """
        Startup probe - Has the service fully initialized?

        Returns 200 if started, 503 if still starting.
        Kubernetes will wait for this before checking liveness/readiness.
        """
        uptime_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()

        # Service is considered started after all dependencies are healthy
        readiness_result = await self.readiness()

        return {
            "status": "started" if readiness_result["overall_healthy"] else "starting",
            "service": self.service_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": uptime_seconds,
            "checks": readiness_result["checks"],
        }

    async def detailed_health(self) -> Dict[str, Any]:
        """
        Detailed health check for monitoring and debugging.

        Includes all dependency statuses, metrics, and custom checks.
        """
        uptime_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        readiness_result = await self.readiness()

        return {
            "service": self.service_name,
            "status": HealthStatus.HEALTHY if readiness_result["overall_healthy"] else HealthStatus.UNHEALTHY,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": uptime_seconds,
            "version": "0.1.0",  # TODO: Get from environment
            "dependencies": readiness_result["checks"],
            "overall_healthy": readiness_result["overall_healthy"],
        }


def setup_health_routes(app: FastAPI, health_check: HealthCheck):
    """
    Add standard health check routes to FastAPI application.

    Routes:
    - GET /health - Detailed health check
    - GET /health/live - Liveness probe
    - GET /health/ready - Readiness probe
    - GET /health/startup - Startup probe
    """

    @app.get("/health", tags=["Health"])
    async def health():
        """Detailed health check endpoint."""
        result = await health_check.detailed_health()
        status_code = (
            status.HTTP_200_OK
            if result["overall_healthy"]
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return JSONResponse(content=result, status_code=status_code)

    @app.get("/health/live", tags=["Health"])
    async def liveness():
        """Kubernetes liveness probe."""
        result = await health_check.liveness()
        return JSONResponse(content=result, status_code=status.HTTP_200_OK)

    @app.get("/health/ready", tags=["Health"])
    async def readiness():
        """Kubernetes readiness probe."""
        result = await health_check.readiness()
        status_code = (
            status.HTTP_200_OK
            if result["overall_healthy"]
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return JSONResponse(content=result, status_code=status_code)

    @app.get("/health/startup", tags=["Health"])
    async def startup():
        """Kubernetes startup probe."""
        result = await health_check.startup()
        status_code = (
            status.HTTP_200_OK
            if result["status"] == "started"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return JSONResponse(content=result, status_code=status_code)

    # Add simple /healthz endpoint for compatibility
    @app.get("/healthz", tags=["Health"])
    async def healthz():
        """Simple health check (returns 200 OK if alive)."""
        return Response(status_code=status.HTTP_200_OK)
