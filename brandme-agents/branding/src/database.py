"""
Neo4j Async Database Module with Circuit Breaker and Connection Pooling.

Architecture Notes:
-------------------
This module implements a resilient Neo4j connection layer for the Personal Branding Agent.
It coexists with the main Spanner-based system (v9 architecture) for specialized GraphRAG
workloads that benefit from Neo4j's native graph traversal and vector search capabilities.

Key Features:
- Async Neo4j driver with connection pooling
- Circuit breaker pattern for fault tolerance (2000ms latency threshold)
- RBAC enforcement: READ_ONLY for :ClosedBookProduct, WRITE for :DynamicUserEntity
- Fallback to cached JSON product list when graph is unavailable

Copyright (c) Brand.Me, Inc. All rights reserved.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, TypeVar

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession
from neo4j.exceptions import (
    AuthError,
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from pycircuitbreaker import CircuitBreaker, CircuitBreakerError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Type variable for generic async functions
T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for the circuit breaker."""
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    latency_threshold_ms: float = 2000.0  # 2 second latency threshold
    half_open_max_calls: int = 3


@dataclass
class Neo4jConfig:
    """Neo4j connection configuration."""
    uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "neo4j://localhost:7687"))
    username: str = field(default_factory=lambda: os.getenv("NEO4J_USERNAME", "neo4j"))
    password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", "password"))
    database: str = field(default_factory=lambda: os.getenv("NEO4J_DATABASE", "neo4j"))
    max_connection_pool_size: int = 50
    connection_acquisition_timeout: float = 60.0
    max_transaction_retry_time: float = 30.0

    # RBAC database users (separate credentials for different access levels)
    readonly_username: str = field(
        default_factory=lambda: os.getenv("NEO4J_READONLY_USER", "branding_reader")
    )
    readonly_password: str = field(
        default_factory=lambda: os.getenv("NEO4J_READONLY_PASSWORD", "")
    )
    writer_username: str = field(
        default_factory=lambda: os.getenv("NEO4J_WRITER_USER", "branding_writer")
    )
    writer_password: str = field(
        default_factory=lambda: os.getenv("NEO4J_WRITER_PASSWORD", "")
    )


@dataclass
class CachedProductList:
    """
    Cached JSON product list for circuit breaker fallback.

    When Neo4j latency exceeds threshold or circuit opens,
    we fall back to this pre-loaded product catalog.
    """
    products: list[dict[str, Any]] = field(default_factory=list)
    loaded_at: float = 0.0
    cache_ttl: float = 300.0  # 5 minute cache TTL

    @classmethod
    def load_from_file(cls, path: Path | str) -> "CachedProductList":
        """Load product catalog from JSON file."""
        cache_path = Path(path)
        if not cache_path.exists():
            logger.warning(f"Product cache file not found: {cache_path}")
            return cls()

        try:
            with open(cache_path) as f:
                data = json.load(f)
            return cls(
                products=data.get("products", []),
                loaded_at=time.time()
            )
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load product cache: {e}")
            return cls()

    def is_valid(self) -> bool:
        """Check if cache is still valid."""
        return (
            len(self.products) > 0 and
            (time.time() - self.loaded_at) < self.cache_ttl
        )

    def get_products_by_category(self, category: str | None = None) -> list[dict[str, Any]]:
        """Get products, optionally filtered by category."""
        if category is None:
            return self.products
        return [p for p in self.products if p.get("category") == category]


class LatencyAwareCircuitBreaker:
    """
    Circuit breaker that triggers on both failures and high latency.

    Opens circuit when:
    - failure_threshold consecutive failures occur
    - Average latency exceeds latency_threshold_ms
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._latency_samples: list[float] = []
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def _check_state_transition(self) -> None:
        """Check if state should transition."""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if (
                    self._last_failure_time and
                    (time.time() - self._last_failure_time) >= self.config.recovery_timeout
                ):
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0

    async def record_success(self, latency_ms: float) -> None:
        """Record a successful call with its latency."""
        async with self._lock:
            self._latency_samples.append(latency_ms)
            # Keep only last 10 samples
            self._latency_samples = self._latency_samples[-10:]

            # Check average latency
            avg_latency = sum(self._latency_samples) / len(self._latency_samples)
            if avg_latency > self.config.latency_threshold_ms:
                logger.warning(
                    f"Average latency {avg_latency:.0f}ms exceeds threshold "
                    f"{self.config.latency_threshold_ms:.0f}ms"
                )
                self._failure_count += 1
            else:
                self._failure_count = 0
                self._success_count += 1

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1
                if self._half_open_calls >= self.config.half_open_max_calls:
                    logger.info("Circuit breaker transitioning to CLOSED")
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0

    async def record_failure(self, error: Exception) -> None:
        """Record a failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._failure_count >= self.config.failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.error(
                        f"Circuit breaker OPEN after {self._failure_count} failures. "
                        f"Last error: {error}"
                    )
                self._state = CircuitState.OPEN

            if self._state == CircuitState.HALF_OPEN:
                logger.warning("Failure in HALF_OPEN state, returning to OPEN")
                self._state = CircuitState.OPEN

    async def can_execute(self) -> bool:
        """Check if a call can be executed."""
        await self._check_state_transition()
        return self._state != CircuitState.OPEN


class Neo4jConnectionPool:
    """
    Async Neo4j connection pool with circuit breaker and RBAC support.

    Provides separate drivers for read-only and write operations,
    enforcing RBAC at the connection level.
    """

    def __init__(
        self,
        config: Neo4jConfig,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        product_cache_path: Path | str | None = None,
    ):
        self.config = config
        self.cb_config = circuit_breaker_config or CircuitBreakerConfig()
        self.circuit_breaker = LatencyAwareCircuitBreaker(self.cb_config)

        # Separate drivers for RBAC
        self._read_driver: AsyncDriver | None = None
        self._write_driver: AsyncDriver | None = None

        # Fallback cache
        self._product_cache: CachedProductList | None = None
        if product_cache_path:
            self._product_cache = CachedProductList.load_from_file(product_cache_path)

        self._initialized = False

    async def initialize(self) -> None:
        """Initialize connection pools."""
        if self._initialized:
            return

        with tracer.start_as_current_span("neo4j.pool.initialize", kind=SpanKind.CLIENT) as span:
            try:
                # Read-only driver (for :ClosedBookProduct queries)
                # Uses RBAC user with READ privileges only
                read_auth = (
                    self.config.readonly_username or self.config.username,
                    self.config.readonly_password or self.config.password,
                )
                self._read_driver = AsyncGraphDatabase.driver(
                    self.config.uri,
                    auth=read_auth,
                    max_connection_pool_size=self.config.max_connection_pool_size,
                    connection_acquisition_timeout=self.config.connection_acquisition_timeout,
                    max_transaction_retry_time=self.config.max_transaction_retry_time,
                )

                # Write driver (for :DynamicUserEntity mutations)
                # Uses RBAC user with WRITE privileges to specific labels
                write_auth = (
                    self.config.writer_username or self.config.username,
                    self.config.writer_password or self.config.password,
                )
                self._write_driver = AsyncGraphDatabase.driver(
                    self.config.uri,
                    auth=write_auth,
                    max_connection_pool_size=self.config.max_connection_pool_size // 2,
                    connection_acquisition_timeout=self.config.connection_acquisition_timeout,
                    max_transaction_retry_time=self.config.max_transaction_retry_time,
                )

                # Verify connectivity
                await self._verify_connectivity()

                self._initialized = True
                span.set_status(Status(StatusCode.OK))
                logger.info("Neo4j connection pool initialized successfully")

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error(f"Failed to initialize Neo4j pool: {e}")
                raise

    async def _verify_connectivity(self) -> None:
        """Verify database connectivity."""
        if self._read_driver:
            await self._read_driver.verify_connectivity()
        if self._write_driver:
            await self._write_driver.verify_connectivity()

    async def close(self) -> None:
        """Close all connections."""
        if self._read_driver:
            await self._read_driver.close()
            self._read_driver = None
        if self._write_driver:
            await self._write_driver.close()
            self._write_driver = None
        self._initialized = False
        logger.info("Neo4j connection pool closed")

    @asynccontextmanager
    async def read_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a read-only session for :ClosedBookProduct queries.

        RBAC: This session uses credentials with READ_ONLY access to
        nodes labeled :ClosedBookProduct.
        """
        if not self._read_driver:
            raise RuntimeError("Connection pool not initialized")

        async with self._read_driver.session(database=self.config.database) as session:
            yield session

    @asynccontextmanager
    async def write_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a write session for :DynamicUserEntity mutations.

        RBAC: This session uses credentials with WRITE access only to
        nodes labeled :DynamicUserEntity. Any attempt to write to
        :ClosedBookProduct will fail with authorization error.
        """
        if not self._write_driver:
            raise RuntimeError("Connection pool not initialized")

        async with self._write_driver.session(database=self.config.database) as session:
            yield session

    async def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        *,
        use_fallback: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Execute a read query with circuit breaker protection.

        If circuit is open or latency exceeds threshold, falls back to
        cached product list when use_fallback=True.

        Args:
            query: Cypher query string
            parameters: Query parameters
            use_fallback: Whether to use cached fallback on failure

        Returns:
            List of result records as dictionaries
        """
        with tracer.start_as_current_span(
            "neo4j.execute_read",
            kind=SpanKind.CLIENT,
        ) as span:
            span.set_attribute("db.system", "neo4j")
            span.set_attribute("db.operation", "read")
            span.set_attribute("db.statement", query[:200])  # Truncate for safety

            # Check circuit breaker
            if not await self.circuit_breaker.can_execute():
                span.set_attribute("circuit_breaker.state", "open")
                if use_fallback and self._product_cache and self._product_cache.is_valid():
                    logger.warning("Circuit open, using cached product fallback")
                    span.set_attribute("fallback.used", True)
                    return self._product_cache.products
                raise CircuitBreakerError("Circuit breaker is open")

            start_time = time.perf_counter()
            try:
                async with self.read_session() as session:
                    result = await session.run(query, parameters or {})
                    records = [dict(record) async for record in result]

                latency_ms = (time.perf_counter() - start_time) * 1000
                span.set_attribute("db.latency_ms", latency_ms)

                await self.circuit_breaker.record_success(latency_ms)

                # If latency is high, log warning
                if latency_ms > self.cb_config.latency_threshold_ms:
                    logger.warning(f"Query latency {latency_ms:.0f}ms exceeds threshold")
                    span.set_attribute("latency.exceeded", True)

                return records

            except (ServiceUnavailable, SessionExpired, TransientError) as e:
                latency_ms = (time.perf_counter() - start_time) * 1000
                span.set_attribute("db.latency_ms", latency_ms)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)

                await self.circuit_breaker.record_failure(e)

                # Fallback to cache
                if use_fallback and self._product_cache and self._product_cache.is_valid():
                    logger.warning(f"Query failed, using cached fallback: {e}")
                    span.set_attribute("fallback.used", True)
                    return self._product_cache.products

                raise

    async def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a write query for :DynamicUserEntity nodes.

        RBAC enforced: This method uses the write driver which has
        permissions only for :DynamicUserEntity labels.

        Args:
            query: Cypher query string (must target :DynamicUserEntity)
            parameters: Query parameters

        Returns:
            List of result records as dictionaries
        """
        with tracer.start_as_current_span(
            "neo4j.execute_write",
            kind=SpanKind.CLIENT,
        ) as span:
            span.set_attribute("db.system", "neo4j")
            span.set_attribute("db.operation", "write")
            span.set_attribute("db.statement", query[:200])

            # Validate query targets only allowed labels
            if not self._validate_write_query(query):
                raise ValueError(
                    "Write queries must only target :DynamicUserEntity nodes. "
                    ":ClosedBookProduct is READ_ONLY."
                )

            start_time = time.perf_counter()
            try:
                async with self.write_session() as session:
                    result = await session.run(query, parameters or {})
                    records = [dict(record) async for record in result]
                    # Commit transaction
                    await result.consume()

                latency_ms = (time.perf_counter() - start_time) * 1000
                span.set_attribute("db.latency_ms", latency_ms)

                return records

            except AuthError as e:
                # RBAC violation - user tried to write to unauthorized label
                span.set_status(Status(StatusCode.ERROR, f"RBAC violation: {e}"))
                span.record_exception(e)
                logger.error(f"RBAC violation in write query: {e}")
                raise PermissionError(
                    "Write access denied. The agent service has WRITE access only to "
                    ":DynamicUserEntity nodes."
                ) from e

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    def _validate_write_query(self, query: str) -> bool:
        """
        Validate that write query only targets allowed labels.

        This is a client-side check. Server-side RBAC provides the
        actual enforcement.
        """
        query_upper = query.upper()

        # Check for write operations on ClosedBookProduct
        forbidden_patterns = [
            "CREATE (:CLOSEDBOOKPRODUCT",
            "CREATE (N:CLOSEDBOOKPRODUCT",
            "MERGE (:CLOSEDBOOKPRODUCT",
            "MERGE (N:CLOSEDBOOKPRODUCT",
            "SET N:CLOSEDBOOKPRODUCT",
            "DELETE" in query_upper and "CLOSEDBOOKPRODUCT" in query_upper,
        ]

        # Normalize and check
        normalized = query_upper.replace(" ", "").replace("\n", "")
        for pattern in forbidden_patterns:
            if isinstance(pattern, bool):
                if pattern:
                    return False
            elif pattern.replace(" ", "") in normalized:
                return False

        return True

    def get_fallback_products(
        self,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get products from fallback cache."""
        if not self._product_cache:
            return []
        return self._product_cache.get_products_by_category(category)


# -----------------------------------------------------------------------------
# Neo4j RBAC Setup Queries (Run once by admin)
# -----------------------------------------------------------------------------

NEO4J_RBAC_SETUP = """
// Run these commands as Neo4j admin to set up RBAC for the branding agent

// 1. Create roles
CREATE ROLE branding_reader IF NOT EXISTS;
CREATE ROLE branding_writer IF NOT EXISTS;

// 2. Grant read-only access to ClosedBookProduct
GRANT MATCH {*} ON GRAPH neo4j NODE ClosedBookProduct TO branding_reader;
GRANT TRAVERSE ON GRAPH neo4j TO branding_reader;

// 3. Grant read + write access to DynamicUserEntity
GRANT MATCH {*} ON GRAPH neo4j NODE DynamicUserEntity TO branding_writer;
GRANT WRITE ON GRAPH neo4j NODE DynamicUserEntity TO branding_writer;
GRANT CREATE ON GRAPH neo4j NODE DynamicUserEntity TO branding_writer;
GRANT DELETE ON GRAPH neo4j NODE DynamicUserEntity TO branding_writer;
GRANT SET LABEL DynamicUserEntity ON GRAPH neo4j TO branding_writer;

// 4. Grant relationship access for traversals
GRANT MATCH {*} ON GRAPH neo4j RELATIONSHIP * TO branding_reader;
GRANT MATCH {*} ON GRAPH neo4j RELATIONSHIP * TO branding_writer;
GRANT WRITE ON GRAPH neo4j RELATIONSHIP * TO branding_writer;

// 5. Create users and assign roles
CREATE USER branding_reader IF NOT EXISTS SET PASSWORD 'secure_reader_password' CHANGE NOT REQUIRED;
CREATE USER branding_writer IF NOT EXISTS SET PASSWORD 'secure_writer_password' CHANGE NOT REQUIRED;

GRANT ROLE branding_reader TO branding_reader;
GRANT ROLE branding_writer TO branding_writer;

// 6. Verify setup
SHOW USERS;
SHOW ROLES;
"""


# -----------------------------------------------------------------------------
# Connection Pool Singleton
# -----------------------------------------------------------------------------

_pool: Neo4jConnectionPool | None = None


async def get_neo4j_pool() -> Neo4jConnectionPool:
    """Get or create the Neo4j connection pool singleton."""
    global _pool
    if _pool is None:
        config = Neo4jConfig()
        cb_config = CircuitBreakerConfig()
        cache_path = Path(__file__).parent.parent / "data" / "product_catalog.json"

        _pool = Neo4jConnectionPool(
            config=config,
            circuit_breaker_config=cb_config,
            product_cache_path=cache_path if cache_path.exists() else None,
        )
        await _pool.initialize()

    return _pool


async def close_neo4j_pool() -> None:
    """Close the Neo4j connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
