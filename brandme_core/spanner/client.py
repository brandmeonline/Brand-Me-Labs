"""
Brand.Me Spanner Client
======================

Core Spanner client with automatic configuration for emulator/production.
"""

import os
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
import asyncio

from google.cloud import spanner
from google.cloud.spanner_v1 import param_types
from google.api_core import exceptions as gcp_exceptions

from brandme_core.logging import get_logger

logger = get_logger("spanner.client")


class SpannerClient:
    """
    Unified Spanner client for Brand.Me services.

    Supports both emulator (dev/test) and production modes.
    """

    def __init__(
        self,
        project_id: str,
        instance_id: str,
        database_id: str,
        pool_size: int = 10,
        max_sessions: int = 100
    ):
        self.project_id = project_id
        self.instance_id = instance_id
        self.database_id = database_id
        self.pool_size = pool_size
        self.max_sessions = max_sessions

        self._client: Optional[spanner.Client] = None
        self._database: Optional[spanner.Database] = None
        self._initialized = False

    async def initialize(self):
        """Initialize the Spanner client and database connection."""
        if self._initialized:
            return

        emulator_host = os.getenv('SPANNER_EMULATOR_HOST')

        if emulator_host:
            logger.info({
                "event": "spanner_init_emulator",
                "host": emulator_host,
                "project": self.project_id,
                "instance": self.instance_id,
                "database": self.database_id
            })
        else:
            logger.info({
                "event": "spanner_init_production",
                "project": self.project_id,
                "instance": self.instance_id,
                "database": self.database_id
            })

        self._client = spanner.Client(project=self.project_id)
        instance = self._client.instance(self.instance_id)

        # Configure session pool
        from google.cloud.spanner_v1.pool import PingingPool
        pool = PingingPool(
            size=self.pool_size,
            default_timeout=30,
            ping_interval=300  # 5 minutes
        )

        self._database = instance.database(self.database_id, pool=pool)
        self._initialized = True

        logger.info({
            "event": "spanner_initialized",
            "pool_size": self.pool_size,
            "max_sessions": self.max_sessions
        })

    async def close(self):
        """Close the Spanner client."""
        if self._client:
            self._client.close()
            self._client = None
            self._database = None
            self._initialized = False
            logger.info({"event": "spanner_closed"})

    @property
    def database(self) -> spanner.Database:
        """Get the database instance."""
        if not self._database:
            raise RuntimeError("SpannerClient not initialized. Call initialize() first.")
        return self._database

    async def execute_sql(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        param_types_map: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a SQL query and return results as list of dicts.
        """
        def _execute(snapshot):
            result = snapshot.execute_sql(
                sql,
                params=params,
                param_types=param_types_map
            )
            rows = []
            for row in result:
                row_dict = {}
                for i, field in enumerate(result.fields):
                    row_dict[field.name] = row[i]
                rows.append(row_dict)
            return rows

        with self.database.snapshot() as snapshot:
            return _execute(snapshot)

    async def execute_partitioned_dml(self, sql: str, params: Optional[Dict] = None):
        """Execute partitioned DML for large updates."""
        row_count = self.database.execute_partitioned_dml(sql, params=params)
        return row_count

    def run_in_transaction(self, func):
        """Run a function within a transaction."""
        return self.database.run_in_transaction(func)

    async def health_check(self) -> bool:
        """Check if Spanner is healthy."""
        try:
            with self.database.snapshot() as snapshot:
                result = list(snapshot.execute_sql("SELECT 1"))
                return len(result) > 0
        except Exception as e:
            logger.error({"event": "spanner_health_check_failed", "error": str(e)})
            return False


def create_spanner_client(
    project_id: Optional[str] = None,
    instance_id: Optional[str] = None,
    database_id: Optional[str] = None
) -> SpannerClient:
    """
    Factory function to create a SpannerClient with env config.
    """
    return SpannerClient(
        project_id=project_id or os.getenv('SPANNER_PROJECT_ID', 'brandme-project'),
        instance_id=instance_id or os.getenv('SPANNER_INSTANCE_ID', 'brandme-instance'),
        database_id=database_id or os.getenv('SPANNER_DATABASE_ID', 'brandme-db'),
        pool_size=int(os.getenv('SPANNER_POOL_SIZE', '10')),
        max_sessions=int(os.getenv('SPANNER_MAX_SESSIONS', '100'))
    )
