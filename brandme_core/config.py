# brandme_core/config.py
"""
Centralized configuration management for Brand.Me services.
Uses environment variables with sensible defaults.

v8: Updated for Spanner + Firestore (PostgreSQL removed)
"""
import os
from typing import Optional


class ServiceConfig:
    """Base configuration for all Brand.Me services."""

    # Spanner Configuration (v8)
    SPANNER_PROJECT_ID: str = os.getenv("SPANNER_PROJECT_ID", "test-project")
    SPANNER_INSTANCE_ID: str = os.getenv("SPANNER_INSTANCE_ID", "brandme-instance")
    SPANNER_DATABASE_ID: str = os.getenv("SPANNER_DATABASE_ID", "brandme-db")
    SPANNER_POOL_SIZE: int = int(os.getenv("SPANNER_POOL_SIZE", "10"))
    SPANNER_MAX_SESSIONS: int = int(os.getenv("SPANNER_MAX_SESSIONS", "100"))

    # Firestore Configuration (v8)
    FIRESTORE_PROJECT_ID: str = os.getenv("FIRESTORE_PROJECT_ID", "test-project")

    # HTTP Client Configuration
    HTTP_TIMEOUT: int = int(os.getenv("HTTP_TIMEOUT", "30"))
    HTTP_MAX_RETRIES: int = int(os.getenv("HTTP_MAX_RETRIES", "3"))
    HTTP_RETRY_BACKOFF: float = float(os.getenv("HTTP_RETRY_BACKOFF", "0.5"))
    HTTP_POOL_CONNECTIONS: int = int(os.getenv("HTTP_POOL_CONNECTIONS", "10"))
    HTTP_POOL_MAXSIZE: int = int(os.getenv("HTTP_POOL_MAXSIZE", "20"))

    # Service URLs
    BRAIN_SERVICE_URL: str = os.getenv("BRAIN_SERVICE_URL", "http://brain:8000")
    POLICY_SERVICE_URL: str = os.getenv("POLICY_SERVICE_URL", "http://policy:8001")
    ORCHESTRATOR_SERVICE_URL: str = os.getenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator:8002")
    KNOWLEDGE_SERVICE_URL: str = os.getenv("KNOWLEDGE_SERVICE_URL", "http://knowledge:8003")
    COMPLIANCE_SERVICE_URL: str = os.getenv("COMPLIANCE_SERVICE_URL", "http://compliance:8004")
    IDENTITY_SERVICE_URL: str = os.getenv("IDENTITY_SERVICE_URL", "http://identity:8005")
    GOVERNANCE_SERVICE_URL: str = os.getenv("GOVERNANCE_SERVICE_URL", "http://governance:8006")
    CUBE_SERVICE_URL: str = os.getenv("CUBE_SERVICE_URL", "http://cube:8007")

    # Service Behavior
    ENABLE_STUB_MODE: bool = os.getenv("ENABLE_STUB_MODE", "true").lower() == "true"
    ENABLE_STRICT_VALIDATION: bool = os.getenv("ENABLE_STRICT_VALIDATION", "false").lower() == "true"

    # CORS Configuration
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "http://localhost:*,http://localhost:3000").split(",")

    @classmethod
    def get_spanner_config(cls) -> dict:
        """Returns Spanner connection configuration."""
        return {
            "project_id": cls.SPANNER_PROJECT_ID,
            "instance_id": cls.SPANNER_INSTANCE_ID,
            "database_id": cls.SPANNER_DATABASE_ID,
        }

    @classmethod
    def is_development(cls) -> bool:
        """Returns True if running in development mode."""
        return os.getenv("ENVIRONMENT", "development").lower() == "development"

    @classmethod
    def is_production(cls) -> bool:
        """Returns True if running in production mode."""
        return os.getenv("ENVIRONMENT", "development").lower() == "production"


# Singleton instance
config = ServiceConfig()
