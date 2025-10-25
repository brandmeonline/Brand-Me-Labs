# brandme_core/logging.py
import json
import logging
import sys
import uuid
from typing import Optional


class StructuredLogger:
    """Wrapper around Python's logging that outputs structured JSON."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.context = {}

    def bind(self, **kwargs):
        """Chain additional context to this logger."""
        new_logger = StructuredLogger(self.service_name)
        new_logger.context = {**self.context, **kwargs}
        return new_logger

    def _log(self, level: str, message: str, extra: Optional[dict] = None):
        """Internal method to output structured JSON logs."""
        log_entry = {
            "service": self.service_name,
            "level": level,
            "message": message,
            **self.context
        }
        if extra:
            log_entry.update(extra)

        # Filter out any sensitive keys that should never be logged
        sensitive_keys = [
            "wallet_key", "private_key", "ownership_lineage",
            "purchase_history", "midnight_payload", "midnight_facet"
        ]
        for key in sensitive_keys:
            if key in log_entry:
                log_entry[key] = "[REDACTED]"

        self.logger.log(
            getattr(logging, level.upper()),
            json.dumps(log_entry)
        )

    def debug(self, message: str, extra: Optional[dict] = None):
        self._log("debug", message, extra)

    def info(self, message: str, extra: Optional[dict] = None):
        self._log("info", message, extra)

    def warning(self, message: str, extra: Optional[dict] = None):
        self._log("warning", message, extra)

    def error(self, message: str, extra: Optional[dict] = None):
        self._log("error", message, extra)


def get_logger(service_name: str) -> StructuredLogger:
    """
    Returns a structured JSON logger for the given service.

    Usage:
        logger = get_logger("brain")
        logger.info("Processing scan", extra={"scan_id": scan_id})
    """
    return StructuredLogger(service_name)


def redact_user_id(user_id: Optional[str]) -> str:
    """
    Redacts a user ID to prevent PII leakage in logs.

    Returns first 8 characters + "…"
    If user_id is None or empty, returns "unknown".

    Example:
        redact_user_id("a1b2c3d4-e5f6-7890-abcd-ef1234567890") -> "a1b2c3d4…"
    """
    if not user_id:
        return "unknown"
    if len(user_id) <= 8:
        return user_id
    return f"{user_id[:8]}…"


def ensure_request_id(request, response) -> str:
    """
    Ensures X-Request-Id header is present on request and response.

    - If X-Request-Id exists on incoming request, use that value
    - Otherwise generate a new UUID4
    - Set X-Request-Id on outgoing response
    - Return the request_id value

    This enables full traceability across services:
    brain -> policy -> orchestrator -> audit

    Usage in FastAPI route:
        response = JSONResponse(content=result)
        request_id = ensure_request_id(request, response)
        logger.info("Request completed", extra={"request_id": request_id})
        return response
    """
    request_id = request.headers.get("X-Request-Id")

    if not request_id:
        request_id = str(uuid.uuid4())

    response.headers["X-Request-Id"] = request_id

    return request_id


# TODO: forward logs to centralized aggregator / OpenTelemetry pipeline
# TODO: add request_id to log context automatically (thread-local or async context)
