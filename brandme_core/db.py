# Brand.Me v7 — Stable Integrity Spine
# Database utilities using DATABASE_URL environment variable
# brandme_core/db.py
#
# DEPRECATED in v8: This module uses asyncpg for PostgreSQL connections.
# For new code, use the Spanner client library instead:
#
#   from brandme_core.spanner.pool import create_pool_manager
#   pool = create_pool_manager(project_id, instance_id, database_id)
#   await pool.initialize()
#
# See brandme_core/spanner/ for the v8 database layer.

import os
import asyncio
import warnings
from typing import Optional
import asyncpg
from .logging import get_logger

warnings.warn(
    "brandme_core.db is deprecated. Use brandme_core.spanner.pool for Spanner connections.",
    DeprecationWarning,
    stacklevel=2
)

logger = get_logger("db_utils")


async def create_pool_from_env(
    min_size: int = 5,
    max_size: int = 20,
    max_retries: int = 5,
    retry_delay: float = 2.0
) -> asyncpg.Pool:
    """
    Create a PostgreSQL connection pool from DATABASE_URL environment variable.
    Implements retry logic for connection reliability.
    
    Args:
        min_size: Minimum number of connections in pool
        max_size: Maximum number of connections in pool
        max_retries: Maximum number of connection attempts
        retry_delay: Base delay between retries (doubled each attempt)
    
    Returns:
        asyncpg.Pool: Connection pool
    
    Raises:
        RuntimeError: If connection fails after all retries
    """
    database_url = os.getenv("DATABASE_URL", "postgresql://brandme:brandme@postgres:5432/brandme")
    last_error = None
    
    for attempt in range(max_retries):
        try:
            logger.info({"event": "db_connect_attempt", "attempt": attempt + 1, "max_retries": max_retries})
            
            pool = await asyncpg.create_pool(
                database_url,
                min_size=min_size,
                max_size=max_size,
            )
            
            # Test the connection
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            logger.info({"event": "db_connected", "pool_size": f"{min_size}-{max_size}"})
            return pool
            
        except Exception as e:
            last_error = e
            logger.warning({
                "event": "db_connect_failed",
                "attempt": attempt + 1,
                "error": str(e),
                "will_retry": attempt < max_retries - 1
            })
            
            if attempt < max_retries - 1:
                delay = retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)
            else:
                logger.error({"event": "db_connect_failed_final", "max_retries": max_retries, "error": str(last_error)})
                raise RuntimeError(f"Failed to connect to database after {max_retries} attempts: {str(last_error)}")
    
    raise RuntimeError(f"Database connection failed: {str(last_error)}")


async def safe_close_pool(pool: Optional[asyncpg.Pool]):
    """
    Safely close a database pool, handling errors gracefully.
    
    Args:
        pool: Database pool to close (can be None)
    """
    if pool is None:
        return
    
    try:
        await pool.close()
        logger.info({"event": "db_pool_closed"})
    except Exception as e:
        logger.warning({"event": "db_pool_close_error", "error": str(e)})


async def health_check(pool: asyncpg.Pool) -> bool:
    """
    Check database connection health.
    
    Args:
        pool: Database connection pool
    
    Returns:
        bool: True if database is healthy, False otherwise
    """
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception as e:
        logger.error({"event": "db_health_check_failed", "error": str(e)})
        return False

