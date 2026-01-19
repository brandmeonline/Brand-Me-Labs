"""
Brand.Me Spanner Pool Manager
============================

Optimized session pool for high-concurrency NATS JetStream environment.
"""

import os
import asyncio
from typing import Optional, Dict, Any, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

from google.cloud import spanner
from google.cloud.spanner_v1.pool import PingingPool
from google.api_core import exceptions as gcp_exceptions

from brandme_core.logging import get_logger

logger = get_logger("spanner.pool")


@dataclass
class PoolStats:
    """Pool statistics for monitoring."""
    active_sessions: int
    max_sessions: int
    pool_size: int
    utilization: float
    queued_requests: int
    last_health_check: Optional[datetime]
    is_healthy: bool


class ResourceExhaustedError(Exception):
    """Raised when session pool is exhausted."""
    pass


class SpannerPoolManager:
    """
    Optimized Spanner session pool for high-concurrency NATS JetStream environment.

    Key optimizations:
    - PingingPool keeps sessions warm
    - Configurable pool size based on NATS consumer count
    - Graceful degradation under load
    - Backpressure handling
    """

    def __init__(
        self,
        project_id: str,
        instance_id: str,
        database_id: str,
        min_sessions: int = 10,
        max_sessions: int = 100,
        ping_interval: int = 300,
        acquire_timeout: float = 30.0,
        enable_backpressure: bool = True
    ):
        self.project_id = project_id
        self.instance_id = instance_id
        self.database_id = database_id
        self.min_sessions = min_sessions
        self.max_sessions = max_sessions
        self.ping_interval = ping_interval
        self.acquire_timeout = acquire_timeout
        self.enable_backpressure = enable_backpressure

        self._client: Optional[spanner.Client] = None
        self._database: Optional[spanner.Database] = None
        self._pool: Optional[PingingPool] = None

        self._active_sessions = 0
        self._queued_requests = 0
        self._lock = asyncio.Lock()
        self._semaphore: Optional[asyncio.Semaphore] = None

        self._last_health_check: Optional[datetime] = None
        self._is_healthy = False
        self._initialized = False

    async def initialize(self):
        """Initialize the pool manager."""
        if self._initialized:
            return

        emulator_host = os.getenv('SPANNER_EMULATOR_HOST')

        logger.info({
            "event": "pool_manager_init",
            "min_sessions": self.min_sessions,
            "max_sessions": self.max_sessions,
            "ping_interval": self.ping_interval,
            "emulator": emulator_host is not None
        })

        self._client = spanner.Client(project=self.project_id)
        instance = self._client.instance(self.instance_id)

        # Create PingingPool for session keepalive
        self._pool = PingingPool(
            size=self.min_sessions,
            default_timeout=self.acquire_timeout,
            ping_interval=self.ping_interval
        )

        self._database = instance.database(self.database_id, pool=self._pool)

        # Semaphore for backpressure
        self._semaphore = asyncio.Semaphore(self.max_sessions)

        # Initial health check
        self._is_healthy = await self._health_check()
        self._last_health_check = datetime.utcnow()
        self._initialized = True

        logger.info({
            "event": "pool_manager_initialized",
            "is_healthy": self._is_healthy
        })

    async def close(self):
        """Close the pool manager."""
        if self._client:
            self._client.close()
            self._client = None
            self._database = None
            self._pool = None
            self._initialized = False
            logger.info({"event": "pool_manager_closed"})

    async def _health_check(self) -> bool:
        """Perform health check."""
        try:
            with self._database.snapshot() as snapshot:
                list(snapshot.execute_sql("SELECT 1"))
            return True
        except Exception as e:
            logger.error({"event": "health_check_failed", "error": str(e)})
            return False

    @asynccontextmanager
    async def session(self):
        """
        Get a read-only session from the pool with backpressure handling.
        """
        if not self._initialized:
            raise RuntimeError("Pool not initialized")

        if self.enable_backpressure:
            async with self._lock:
                self._queued_requests += 1

            try:
                # Wait for available slot
                await asyncio.wait_for(
                    self._semaphore.acquire(),
                    timeout=self.acquire_timeout
                )
            except asyncio.TimeoutError:
                async with self._lock:
                    self._queued_requests -= 1
                raise ResourceExhaustedError(
                    f"Session pool exhausted. Active: {self._active_sessions}, "
                    f"Max: {self.max_sessions}, Queued: {self._queued_requests}"
                )
            finally:
                async with self._lock:
                    self._queued_requests -= 1

        async with self._lock:
            self._active_sessions += 1

        try:
            with self._database.snapshot() as snapshot:
                yield snapshot
        finally:
            async with self._lock:
                self._active_sessions -= 1
            if self.enable_backpressure:
                self._semaphore.release()

    @asynccontextmanager
    async def transaction(self):
        """
        Get a read-write transaction with automatic retry.
        """
        if not self._initialized:
            raise RuntimeError("Pool not initialized")

        if self.enable_backpressure:
            async with self._lock:
                self._queued_requests += 1

            try:
                await asyncio.wait_for(
                    self._semaphore.acquire(),
                    timeout=self.acquire_timeout
                )
            except asyncio.TimeoutError:
                async with self._lock:
                    self._queued_requests -= 1
                raise ResourceExhaustedError("Session pool exhausted for transaction")
            finally:
                async with self._lock:
                    self._queued_requests -= 1

        async with self._lock:
            self._active_sessions += 1

        try:
            # Spanner's run_in_transaction handles retries
            yield self._database
        finally:
            async with self._lock:
                self._active_sessions -= 1
            if self.enable_backpressure:
                self._semaphore.release()

    def run_in_transaction(self, func: Callable) -> Any:
        """
        Run a function within a Spanner transaction.
        Handles automatic retries for aborted transactions.
        """
        return self._database.run_in_transaction(func)

    async def get_stats(self) -> PoolStats:
        """Return current pool statistics for monitoring."""
        async with self._lock:
            return PoolStats(
                active_sessions=self._active_sessions,
                max_sessions=self.max_sessions,
                pool_size=self.min_sessions,
                utilization=self._active_sessions / self.max_sessions if self.max_sessions > 0 else 0,
                queued_requests=self._queued_requests,
                last_health_check=self._last_health_check,
                is_healthy=self._is_healthy
            )

    async def refresh_health(self):
        """Refresh health check status."""
        self._is_healthy = await self._health_check()
        self._last_health_check = datetime.utcnow()
        return self._is_healthy


def create_pool_manager(
    project_id: Optional[str] = None,
    instance_id: Optional[str] = None,
    database_id: Optional[str] = None
) -> SpannerPoolManager:
    """Factory function to create a SpannerPoolManager with env config."""
    return SpannerPoolManager(
        project_id=project_id or os.getenv('SPANNER_PROJECT_ID', 'brandme-project'),
        instance_id=instance_id or os.getenv('SPANNER_INSTANCE_ID', 'brandme-instance'),
        database_id=database_id or os.getenv('SPANNER_DATABASE_ID', 'brandme-db'),
        min_sessions=int(os.getenv('SPANNER_MIN_SESSIONS', '10')),
        max_sessions=int(os.getenv('SPANNER_MAX_SESSIONS', '100')),
        ping_interval=int(os.getenv('SPANNER_PING_INTERVAL', '300')),
        acquire_timeout=float(os.getenv('SPANNER_ACQUIRE_TIMEOUT', '30.0')),
        enable_backpressure=os.getenv('SPANNER_ENABLE_BACKPRESSURE', 'true').lower() == 'true'
    )
