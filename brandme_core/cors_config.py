# Brand.Me — CORS configuration for FastAPI services
# brandme_core/cors_config.py
"""
CORS settings for the legacy FastAPI services.

The environment comes from BRANDME_MODE (``resolve_environment``): it is
required, ENVIRONMENT may only repeat it, and a process is never assumed to be
development. In sandbox and production a wildcard origin is refused instead
of being silently rewritten.
"""

from typing import Mapping, Optional

from .config import Mode, resolve_environment
from .env import parse_cors_origins
from .logging import get_logger

logger = get_logger("cors_config")


def get_cors_config(env: Optional[Mapping[str, str]] = None) -> dict:
    """
    Get secure CORS configuration for FastAPI services.

    Raises ModeConfigurationError if BRANDME_MODE is unset/invalid or
    ENVIRONMENT contradicts it, and ValueError for a wildcard origin in
    sandbox/production.

    Returns:
        dict: CORS middleware configuration
    """
    environment = resolve_environment(env)
    origins = parse_cors_origins()

    if Mode(environment).is_strict and "*" in origins:
        logger.warning({
            "event": "cors_wildcard_refused",
            "environment": environment,
            "message": "CORS_ORIGINS must list explicit origins in sandbox/production",
        })
        raise ValueError(f"CORS_ORIGINS='*' is not allowed when BRANDME_MODE={environment}")

    config = {
        "allow_origins": origins,
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        "allow_headers": [
            "Content-Type",
            "Authorization",
            "X-Request-Id",
            "X-Region",
        ],
        "expose_headers": [
            "X-Request-Id",
        ],
        "max_age": 86400,  # 24 hours
    }

    logger.info({
        "event": "cors_config_loaded",
        "origins_count": len(origins),
        "environment": environment,
    })

    return config
