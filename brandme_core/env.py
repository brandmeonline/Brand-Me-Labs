# Brand.Me v7 — Stable Integrity Spine
# Environment variable validation utilities
# brandme_core/env.py

import os
from typing import Optional, List
from .logging import get_logger

logger = get_logger("env")


class EnvConfig:
    """Environment variable configuration with validation."""
    
    # Database
    DATABASE_URL: str
    REGION_DEFAULT: str = "us-east1"
    
    # Service URLs (defaults for docker-compose)
    BRAIN_SERVICE_URL: str = "http://brain:8000"
    POLICY_SERVICE_URL: str = "http://policy:8001"
    ORCHESTRATOR_SERVICE_URL: str = "http://orchestrator:8002"
    KNOWLEDGE_SERVICE_URL: str = "http://knowledge:8003"
    COMPLIANCE_SERVICE_URL: str = "http://compliance:8004"
    IDENTITY_SERVICE_URL: str = "http://identity:8005"
    GOVERNANCE_SERVICE_URL: str = "http://governance_console:8006"
    
    # Optional settings
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "*"  # Comma-separated list
    
    @classmethod
    def validate(cls) -> 'EnvConfig':
        """
        Validate and load environment variables.
        
        Returns:
            EnvConfig: Validated configuration
            
        Raises:
            ValueError: If required environment variables are missing
        """
        config = cls()
        
        # Required: DATABASE_URL
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.warning({
                "event": "env_missing_datABASE_url",
                "using_default": True,
            })
            database_url = "postgresql://brandme:brandme@postgres:5432/brandme"
        config.DATABASE_URL = database_url
        
        # Optional with defaults
        config.REGION_DEFAULT = os.getenv("REGION_DEFAULT", "us-east1")
        config.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        config.CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
        
        # Service URLs (can be overridden for K8s/external)
        config.BRAIN_SERVICE_URL = os.getenv("BRAIN_SERVICE_URL", "http://brain:8000")
        config.POLICY_SERVICE_URL = os.getenv("POLICY_SERVICE_URL", "http://policy:8001")
        config.ORCHESTRATOR_SERVICE_URL = os.getenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator:8002")
        config.KNOWLEDGE_SERVICE_URL = os.getenv("KNOWLEDGE_SERVICE_URL", "http://knowledge:8003")
        config.COMPLIANCE_SERVICE_URL = os.getenv("COMPLIANCE_SERVICE_URL", "http://compliance:8004")
        config.IDENTITY_SERVICE_URL = os.getenv("IDENTITY_SERVICE_URL", "http://identity:8005")
        config.GOVERNANCE_SERVICE_URL = os.getenv("GOVERNANCE_SERVICE_URL", "http://governance_console:8006")
        
        # Log configuration
        logger.info({
            "event": "env_config_loaded",
            "region": config.REGION_DEFAULT,
            "log_level": config.LOG_LEVEL,
        })
        
        return config


# Global config instance
env = EnvConfig.validate()


def get_database_url() -> str:
    """Get DATABASE_URL from environment."""
    return env.DATABASE_URL


def get_region_default() -> str:
    """Get default region from environment."""
    return env.REGION_DEFAULT


def get_service_url(service_name: str) -> str:
    """
    Get service URL by name.
    
    Args:
        service_name: One of: brain, policy, orchestrator, knowledge, compliance, identity, governance
    
    Returns:
        str: Service URL
    """
    url_map = {
        "brain": env.BRAIN_SERVICE_URL,
        "policy": env.POLICY_SERVICE_URL,
        "orchestrator": env.ORCHESTRATOR_SERVICE_URL,
        "knowledge": env.KNOWLEDGE_SERVICE_URL,
        "compliance": env.COMPLIANCE_SERVICE_URL,
        "identity": env.IDENTITY_SERVICE_URL,
        "governance": env.GOVERNANCE_SERVICE_URL,
    }
    
    url = url_map.get(service_name.lower())
    if not url:
        raise ValueError(f"Unknown service name: {service_name}")
    
    return url


def parse_cors_origins() -> List[str]:
    """
    Parse CORS origins from environment variable.
    
    Returns:
        List[str]: List of allowed origins
    """
    origins = env.CORS_ORIGINS.split(",")
    # Strip whitespace and filter empty strings
    origins = [origin.strip() for origin in origins if origin.strip()]
    
    # If "*" is present, return ["*"] for global access
    if "*" in origins:
        return ["*"]
    
    return origins

