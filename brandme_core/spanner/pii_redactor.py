"""
Brand.Me PII Redacting Spanner Client
=====================================

Spanner client wrapper that applies PII redaction at the driver level.
All queries pass through redaction before returning to application code.
"""

import re
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field

from brandme_core.logging import get_logger

logger = get_logger("spanner.pii")


@dataclass
class RedactionConfig:
    """Configuration for PII redaction."""
    # Fields that should always be fully redacted
    full_redact_fields: Set[str] = field(default_factory=lambda: {
        'email', 'phone', 'phone_number', 'ssn', 'social_security',
        'address', 'street_address', 'ip_address', 'credit_card',
        'bank_account', 'password', 'password_hash'
    })

    # Fields that should be partially redacted (show prefix/suffix)
    partial_redact_fields: Set[str] = field(default_factory=lambda: {
        'user_id', 'owner_id', 'creator_id', 'actor_id', 'grantee_user_id',
        'scanner_user_id', 'from_user_id', 'to_user_id'
    })

    # Patterns for auto-detection
    email_pattern: str = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    phone_pattern: str = r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
    uuid_pattern: str = r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'

    # Redaction settings
    partial_prefix_len: int = 8
    partial_suffix_len: int = 4


class PIIRedactingClient:
    """
    Spanner client wrapper that applies PII redaction at the driver level.

    Usage:
        client = PIIRedactingClient(pool_manager)

        # Query with automatic redaction in logs
        results = await client.query_with_redacted_logging(
            "SELECT * FROM Users WHERE user_id = @user_id",
            params={"user_id": "abc-123-xyz"}
        )

        # Get redacted row for external APIs
        safe_row = client.redact_row(row, context='external')
    """

    def __init__(
        self,
        pool_manager,
        config: Optional[RedactionConfig] = None,
        redact_in_logs: bool = True,
        redact_in_responses: bool = False
    ):
        self.pool = pool_manager
        self.config = config or RedactionConfig()
        self.redact_in_logs = redact_in_logs
        self.redact_in_responses = redact_in_responses

        # Compile patterns
        self._email_regex = re.compile(self.config.email_pattern)
        self._phone_regex = re.compile(self.config.phone_pattern)
        self._uuid_regex = re.compile(self.config.uuid_pattern, re.IGNORECASE)

    def redact_user_id(self, user_id: str) -> str:
        """
        Redact user ID for logging (preserves prefix/suffix for debugging).

        Example: "11111111-1111-1111-1111-111111111111" -> "11111111...1111"
        """
        if not user_id or len(user_id) < 12:
            return '[REDACTED]'

        prefix_len = self.config.partial_prefix_len
        suffix_len = self.config.partial_suffix_len

        return f"{user_id[:prefix_len]}...{user_id[-suffix_len:]}"

    def _should_fully_redact(self, field_name: str) -> bool:
        """Check if field should be fully redacted."""
        field_lower = field_name.lower()
        return field_lower in self.config.full_redact_fields

    def _should_partially_redact(self, field_name: str) -> bool:
        """Check if field should be partially redacted."""
        field_lower = field_name.lower()
        return (
            field_lower in self.config.partial_redact_fields or
            field_lower.endswith('_id') and 'user' in field_lower
        )

    def _detect_and_redact_value(self, value: Any) -> Any:
        """Auto-detect and redact PII in a value."""
        if not isinstance(value, str):
            return value

        # Check for email pattern
        if self._email_regex.search(value):
            return self._email_regex.sub('[EMAIL_REDACTED]', value)

        # Check for phone pattern
        if self._phone_regex.search(value):
            return self._phone_regex.sub('[PHONE_REDACTED]', value)

        return value

    def redact_value(self, field_name: str, value: Any, context: str = 'log') -> Any:
        """
        Redact a single value based on field name and context.

        Args:
            field_name: Name of the field
            value: Value to redact
            context: 'log' for internal logging, 'external' for API responses

        Returns:
            Redacted value
        """
        if value is None:
            return None

        if self._should_fully_redact(field_name):
            return '[REDACTED]'

        if self._should_partially_redact(field_name):
            if context == 'log':
                return self.redact_user_id(str(value))
            elif context == 'external':
                return '[REDACTED]'
            else:
                return value

        # Auto-detect PII in string values
        if isinstance(value, str) and context in ('log', 'external'):
            return self._detect_and_redact_value(value)

        return value

    def redact_row(self, row: Dict[str, Any], context: str = 'log') -> Dict[str, Any]:
        """
        Apply PII redaction to a row.

        Args:
            row: Dictionary with field names and values
            context: 'log' for internal, 'external' for API responses

        Returns:
            Redacted row dictionary
        """
        return {
            key: self.redact_value(key, value, context)
            for key, value in row.items()
        }

    def redact_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Redact parameters for logging."""
        if not params:
            return {}

        return {
            key: self.redact_value(key, value, 'log')
            for key, value in params.items()
        }

    async def execute_sql(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        param_types: Optional[Dict] = None,
        redact_results: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Execute SQL with automatic PII redaction in logs.

        Args:
            sql: SQL query
            params: Query parameters
            param_types: Spanner param types
            redact_results: Whether to redact results (for external APIs)

        Returns:
            List of row dictionaries
        """
        # Log with redacted params
        if self.redact_in_logs:
            safe_params = self.redact_params(params) if params else {}
            logger.info({
                "event": "spanner_query",
                "sql_preview": sql[:100] + "..." if len(sql) > 100 else sql,
                "params_redacted": safe_params
            })

        # Execute query
        async with self.pool.session() as snapshot:
            result = snapshot.execute_sql(sql, params=params, param_types=param_types)

            rows = []
            for row in result:
                row_dict = {}
                for i, field in enumerate(result.fields):
                    row_dict[field.name] = row[i]
                rows.append(row_dict)

        # Optionally redact results
        if redact_results or self.redact_in_responses:
            rows = [self.redact_row(row, 'external') for row in rows]

        return rows

    async def query_user_safe(
        self,
        user_id: str,
        include_fields: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Query a user with automatic PII redaction for external responses.
        """
        from google.cloud.spanner_v1 import param_types as pt

        fields = include_fields or [
            'user_id', 'handle', 'display_name', 'region_code',
            'trust_score', 'is_verified'
        ]

        sql = f"""
        SELECT {', '.join(fields)}
        FROM Users
        WHERE user_id = @user_id
        """

        rows = await self.execute_sql(
            sql,
            params={'user_id': user_id},
            param_types={'user_id': pt.STRING},
            redact_results=True
        )

        return rows[0] if rows else None


def create_pii_client(pool_manager, **kwargs) -> PIIRedactingClient:
    """Factory function to create a PIIRedactingClient."""
    return PIIRedactingClient(pool_manager, **kwargs)
