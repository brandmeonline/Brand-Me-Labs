"""
Brand.Me Idempotent Writer
=========================

Ensures idempotent writes using Spanner commit timestamps.
Uses a mutations table to deduplicate operations.
"""

import hashlib
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime

from google.cloud import spanner
from google.cloud.spanner_v1 import param_types

from brandme_core.logging import get_logger

logger = get_logger("spanner.idempotent")


@dataclass
class MutationResult:
    """Result of an idempotent mutation."""
    status: str  # 'executed' | 'duplicate'
    mutation_id: str
    commit_timestamp: Optional[datetime] = None
    rows_affected: int = 0


class IdempotentWriter:
    """
    Ensures idempotent writes using Spanner commit timestamps.

    Uses a MutationLog table to deduplicate operations based on
    a deterministic hash of (operation_name, params).

    Usage:
        writer = IdempotentWriter(pool_manager)

        result = await writer.execute_idempotent(
            operation_name="transfer_ownership",
            params={"cube_id": "abc", "new_owner": "xyz"},
            mutations=[
                {"table": "Assets", "columns": ["asset_id", "current_owner_id"], "values": [["abc", "xyz"]]}
            ]
        )

        if result.status == "duplicate":
            print("Already executed")
    """

    def __init__(self, pool_manager):
        self.pool = pool_manager

    def _compute_mutation_id(self, operation: str, params: Dict[str, Any]) -> str:
        """Generate deterministic mutation ID from operation + params."""
        # Sort params for deterministic ordering
        sorted_items = sorted(
            (k, str(v)) for k, v in params.items()
        )
        payload = f"{operation}:{sorted_items}"
        return hashlib.sha256(payload.encode()).hexdigest()[:32]

    def _compute_params_hash(self, params: Dict[str, Any]) -> str:
        """Compute hash of params for logging."""
        sorted_items = sorted(
            (k, str(v)) for k, v in params.items()
        )
        return hashlib.sha256(str(sorted_items).encode()).hexdigest()[:16]

    async def execute_idempotent(
        self,
        operation_name: str,
        params: Dict[str, Any],
        mutations: List[Dict[str, Any]],
        actor_id: Optional[str] = None
    ) -> MutationResult:
        """
        Execute mutations idempotently using Spanner commit timestamps.

        Args:
            operation_name: Name of the operation (e.g., "transfer_ownership")
            params: Parameters that uniquely identify this operation
            mutations: List of mutation dicts with:
                - table: Table name
                - columns: List of column names
                - values: List of value tuples
            actor_id: Optional actor who initiated the operation

        Returns:
            MutationResult with status, mutation_id, and commit_timestamp
        """
        mutation_id = self._compute_mutation_id(operation_name, params)
        params_hash = self._compute_params_hash(params)

        logger.info({
            "event": "idempotent_execute_start",
            "operation": operation_name,
            "mutation_id": mutation_id,
            "params_hash": params_hash
        })

        def check_and_write(transaction):
            # Check if mutation already executed
            result = transaction.execute_sql(
                """
                SELECT mutation_id, commit_timestamp, result_status
                FROM MutationLog
                WHERE mutation_id = @mutation_id
                """,
                params={'mutation_id': mutation_id},
                param_types={'mutation_id': param_types.STRING}
            )

            existing = list(result)
            if existing:
                logger.info({
                    "event": "idempotent_duplicate",
                    "mutation_id": mutation_id,
                    "original_timestamp": str(existing[0][1])
                })
                return MutationResult(
                    status='duplicate',
                    mutation_id=mutation_id,
                    commit_timestamp=existing[0][1]
                )

            # Execute all mutations
            rows_affected = 0
            for mutation in mutations:
                if mutation.get('type') == 'insert':
                    transaction.insert(
                        table=mutation['table'],
                        columns=mutation['columns'],
                        values=mutation['values']
                    )
                    rows_affected += len(mutation['values'])
                elif mutation.get('type') == 'update':
                    transaction.update(
                        table=mutation['table'],
                        columns=mutation['columns'],
                        values=mutation['values']
                    )
                    rows_affected += len(mutation['values'])
                else:
                    # Default to insert_or_update
                    transaction.insert_or_update(
                        table=mutation['table'],
                        columns=mutation['columns'],
                        values=mutation['values']
                    )
                    rows_affected += len(mutation['values'])

            # Log this mutation for deduplication
            transaction.insert(
                table='MutationLog',
                columns=['mutation_id', 'operation_name', 'params_hash', 'actor_id', 'result_status', 'commit_timestamp'],
                values=[(mutation_id, operation_name, params_hash, actor_id, 'success', spanner.COMMIT_TIMESTAMP)]
            )

            logger.info({
                "event": "idempotent_executed",
                "mutation_id": mutation_id,
                "rows_affected": rows_affected
            })

            return MutationResult(
                status='executed',
                mutation_id=mutation_id,
                rows_affected=rows_affected
            )

        result = self.pool.run_in_transaction(check_and_write)
        return result

    async def check_mutation_status(self, mutation_id: str) -> Optional[MutationResult]:
        """Check if a mutation has been executed."""
        async with self.pool.session() as snapshot:
            result = snapshot.execute_sql(
                """
                SELECT mutation_id, commit_timestamp, result_status
                FROM MutationLog
                WHERE mutation_id = @mutation_id
                """,
                params={'mutation_id': mutation_id},
                param_types={'mutation_id': param_types.STRING}
            )

            rows = list(result)
            if rows:
                return MutationResult(
                    status='duplicate',
                    mutation_id=rows[0][0],
                    commit_timestamp=rows[0][1]
                )
            return None

    async def cleanup_old_mutations(self, days_to_keep: int = 7) -> int:
        """
        Clean up old mutation log entries.

        Note: Spanner doesn't have TTL, so this must be called periodically.
        """
        cutoff_sql = f"""
        DELETE FROM MutationLog
        WHERE commit_timestamp < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days_to_keep} DAY)
        """

        row_count = self.pool._database.execute_partitioned_dml(cutoff_sql)

        logger.info({
            "event": "mutation_cleanup",
            "days_kept": days_to_keep,
            "rows_deleted": row_count
        })

        return row_count
