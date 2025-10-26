# brandme_core/__init__.py
"""
Brand.Me Core Utilities

Shared utilities for all Brand.Me services including:
- Structured logging with PII redaction
- Resilient HTTP clients with retries
- Database connection pooling
- Configuration management
- Custom exceptions
"""

from .logging import get_logger, redact_user_id, ensure_request_id
from .config import config, ServiceConfig
from .database import create_db_pool, execute_with_retry, safe_close_pool
from .http_client import get_http_client, close_all_clients, ResilientHttpClient
from .exceptions import (
    BrandMeException,
    DatabaseError,
    ServiceUnavailableError,
    ValidationError,
    ResourceNotFoundError,
    TimeoutError,
    PolicyViolationError
)

__all__ = [
    # Logging
    "get_logger",
    "redact_user_id",
    "ensure_request_id",
    # Config
    "config",
    "ServiceConfig",
    # Database
    "create_db_pool",
    "execute_with_retry",
    "safe_close_pool",
    # HTTP Client
    "get_http_client",
    "close_all_clients",
    "ResilientHttpClient",
    # Exceptions
    "BrandMeException",
    "DatabaseError",
    "ServiceUnavailableError",
    "ValidationError",
    "ResourceNotFoundError",
    "TimeoutError",
    "PolicyViolationError",
]
