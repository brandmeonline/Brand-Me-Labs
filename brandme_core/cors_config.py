# Brand.Me v7 — Stable Integrity Spine
# CORS configuration for FastAPI services
# brandme_core/cors_config.py

import os
from typing import List
from .logging import get_logger
from .env import parse_cors_origins

logger = get_logger("cors_config")


def get_cors_config() -> dict:
    """
    Get secure CORS configuration for FastAPI services.
    
    Returns:
        dict: CORS middleware configuration
    """
    origins = parse_cors_origins()
    
    # In production, tighten these
    if os.getenv("ENVIRONMENT") == "production":
        # Remove wildcard in production
        if "*" in origins:
            logger.warning({
                "event": "cors_wildcard_in_production",
                "message": "Wildcard CORS should not be used in production",
            })
            # Use known origins only
            origins = [
                "https://brand.me",
                "https://www.brand.me",
                "https://console.brand.me",
            ]
    
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
        "environment": os.getenv("ENVIRONMENT", "development"),
    })
    
    return config

