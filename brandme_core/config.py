# brandme_core/config.py
"""
Centralized configuration management for Brand.Me services.
Uses environment variables with sensible defaults.
"""
import os
from typing import Optional


class ServiceConfig:
    """Base configuration for all Brand.Me services."""

    # Database Configuration
    DB_HOST: str = os.getenv("DB_HOST", "postgres")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "brandme")
    DB_USER: str = os.getenv("DB_USER", "brandme_user")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "brandme_pass")
    DB_MIN_POOL_SIZE: int = int(os.getenv("DB_MIN_POOL_SIZE", "2"))
    DB_MAX_POOL_SIZE: int = int(os.getenv("DB_MAX_POOL_SIZE", "10"))
    DB_CONNECT_TIMEOUT: int = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))
    DB_COMMAND_TIMEOUT: int = int(os.getenv("DB_COMMAND_TIMEOUT", "30"))

    # HTTP Client Configuration
    HTTP_TIMEOUT: int = int(os.getenv("HTTP_TIMEOUT", "30"))
    HTTP_MAX_RETRIES: int = int(os.getenv("HTTP_MAX_RETRIES", "3"))
    HTTP_RETRY_BACKOFF: float = float(os.getenv("HTTP_RETRY_BACKOFF", "0.5"))
    HTTP_POOL_CONNECTIONS: int = int(os.getenv("HTTP_POOL_CONNECTIONS", "10"))
    HTTP_POOL_MAXSIZE: int = int(os.getenv("HTTP_POOL_MAXSIZE", "20"))

    # Service URLs
    POLICY_SERVICE_URL: str = os.getenv("POLICY_SERVICE_URL", "http://policy:8001")
    ORCHESTRATOR_SERVICE_URL: str = os.getenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator:8002")
    KNOWLEDGE_SERVICE_URL: str = os.getenv("KNOWLEDGE_SERVICE_URL", "http://knowledge:8003")
    COMPLIANCE_SERVICE_URL: str = os.getenv("COMPLIANCE_SERVICE_URL", "http://compliance:8004")
    IDENTITY_SERVICE_URL: str = os.getenv("IDENTITY_SERVICE_URL", "http://identity:8005")
    GOVERNANCE_SERVICE_URL: str = os.getenv("GOVERNANCE_SERVICE_URL", "http://governance:8006")

    # Service Behavior
    ENABLE_STUB_MODE: bool = os.getenv("ENABLE_STUB_MODE", "true").lower() == "true"
    ENABLE_STRICT_VALIDATION: bool = os.getenv("ENABLE_STRICT_VALIDATION", "false").lower() == "true"

    # CORS Configuration
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "http://localhost:*,http://localhost:3000").split(",")

    @classmethod
    def get_database_url(cls) -> str:
        """Returns the full PostgreSQL connection URL."""
        return f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"

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
