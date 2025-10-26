# brandme_core/database.py
"""
Database utilities for Brand.Me services.
Provides connection pooling, error handling, and retry logic.
"""
import asyncio
from typing import Optional
import asyncpg
from .config import config
from .logging import get_logger
from .exceptions import DatabaseError

logger = get_logger("database")


async def create_db_pool(
    max_retries: int = 5,
    retry_delay: float = 2.0
) -> asyncpg.Pool:
    """
    Create a PostgreSQL connection pool with retry logic.

    Args:
        max_retries: Maximum number of connection attempts
        retry_delay: Base delay between retries (doubled each attempt)

    Returns:
        asyncpg.Pool: Connection pool

    Raises:
        DatabaseError: If connection fails after all retries
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            logger.info(
                "Connecting to database",
                extra={
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "host": config.DB_HOST,
                    "database": config.DB_NAME
                }
            )

            pool = await asyncpg.create_pool(
                host=config.DB_HOST,
                port=config.DB_PORT,
                database=config.DB_NAME,
                user=config.DB_USER,
                password=config.DB_PASSWORD,
                min_size=config.DB_MIN_POOL_SIZE,
                max_size=config.DB_MAX_POOL_SIZE,
                command_timeout=config.DB_COMMAND_TIMEOUT,
                timeout=config.DB_CONNECT_TIMEOUT,
            )

            # Test the connection
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")

            logger.info(
                "Database connection established",
                extra={
                    "host": config.DB_HOST,
                    "database": config.DB_NAME,
                    "pool_size": f"{config.DB_MIN_POOL_SIZE}-{config.DB_MAX_POOL_SIZE}"
                }
            )

            return pool

        except Exception as e:
            last_error = e
            logger.warning(
                "Database connection failed",
                extra={
                    "attempt": attempt + 1,
                    "error": str(e),
                    "will_retry": attempt < max_retries - 1
                }
            )

            if attempt < max_retries - 1:
                delay = retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "Database connection failed after all retries",
                    extra={"max_retries": max_retries, "error": str(e)}
                )
                raise DatabaseError(
                    f"Failed to connect to database after {max_retries} attempts",
                    {"last_error": str(last_error)}
                )

    # Should never reach here, but for type safety
    raise DatabaseError(
        "Unexpected error in database connection logic",
        {"last_error": str(last_error)}
    )


async def execute_with_retry(
    pool: asyncpg.Pool,
    query: str,
    *args,
    max_retries: int = 3
):
    """
    Execute a database query with retry logic for transient failures.

    Args:
        pool: Database connection pool
        query: SQL query to execute
        *args: Query parameters
        max_retries: Maximum number of retry attempts

    Raises:
        DatabaseError: If query fails after all retries
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            async with pool.acquire() as conn:
                return await conn.execute(query, *args)

        except asyncpg.exceptions.PostgresError as e:
            last_error = e

            # Check if error is transient (retryable)
            is_transient = any([
                "connection" in str(e).lower(),
                "timeout" in str(e).lower(),
                "busy" in str(e).lower(),
            ])

            if is_transient and attempt < max_retries - 1:
                logger.warning(
                    "Transient database error, retrying",
                    extra={"attempt": attempt + 1, "error": str(e)}
                )
                await asyncio.sleep(0.1 * (2 ** attempt))
                continue
            else:
                # Non-transient error or max retries exceeded
                logger.error(
                    "Database query failed",
                    extra={"query": query[:100], "error": str(e)}
                )
                raise DatabaseError(
                    f"Database query failed: {str(e)}",
                    {"query": query[:100]}
                )

        except Exception as e:
            # Unexpected error - don't retry
            logger.error(
                "Unexpected database error",
                extra={"query": query[:100], "error": str(e)}
            )
            raise DatabaseError(
                f"Unexpected database error: {str(e)}",
                {"query": query[:100]}
            )

    # Should never reach here
    raise DatabaseError(
        "Database query failed after all retries",
        {"last_error": str(last_error)}
    )


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
        logger.info("Database connection pool closed")
    except Exception as e:
        logger.warning(
            "Error closing database pool",
            extra={"error": str(e)}
        )
