# brandme_core/exceptions.py
"""
Custom exceptions for Brand.Me services.
Provides structured error handling and proper HTTP status codes.
"""
from typing import Optional, Dict, Any


class BrandMeException(Exception):
    """Base exception for all Brand.Me errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON response."""
        return {
            "error": self.error_code,
            "message": self.message,
            "status_code": self.status_code,
            **self.details
        }


class DatabaseError(BrandMeException):
    """Raised when database operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=503,
            error_code="DATABASE_ERROR",
            details=details
        )


class ServiceUnavailableError(BrandMeException):
    """Raised when a downstream service is unavailable."""

    def __init__(self, service_name: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Service {service_name} is currently unavailable",
            status_code=503,
            error_code="SERVICE_UNAVAILABLE",
            details={"service": service_name, **(details or {})}
        )


class ValidationError(BrandMeException):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: Optional[str] = None):
        details = {"field": field} if field else {}
        super().__init__(
            message=message,
            status_code=400,
            error_code="VALIDATION_ERROR",
            details=details
        )


class ResourceNotFoundError(BrandMeException):
    """Raised when a requested resource is not found."""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"{resource_type} not found: {resource_id}",
            status_code=404,
            error_code="RESOURCE_NOT_FOUND",
            details={"resource_type": resource_type, "resource_id": resource_id}
        )


class TimeoutError(BrandMeException):
    """Raised when an operation times out."""

    def __init__(self, operation: str, timeout_seconds: int):
        super().__init__(
            message=f"Operation '{operation}' timed out after {timeout_seconds}s",
            status_code=504,
            error_code="TIMEOUT_ERROR",
            details={"operation": operation, "timeout_seconds": timeout_seconds}
        )


class PolicyViolationError(BrandMeException):
    """Raised when a policy check fails."""

    def __init__(self, message: str, policy_version: str):
        super().__init__(
            message=message,
            status_code=403,
            error_code="POLICY_VIOLATION",
            details={"policy_version": policy_version}
        )
