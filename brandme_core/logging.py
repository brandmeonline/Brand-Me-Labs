# brandme_core/logging.py

import logging
import json
import uuid
from typing import Any, Dict

SENSITIVE_KEYS = {
    "wallet_key",
    "purchase_history",
    "ownership_lineage",
    "private_payload",
    "did_secret",
    "wallet_keys",
    "midnight_private_payload",
}


class StructuredLogger:
    """Logger that emits structured JSON logs with automatic service tagging."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(logging.DEBUG)

        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(logging.DEBUG)
            formatter = StructuredFormatter()
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _scrub(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive keys from log data."""
        scrubbed = {}
        for key, value in data.items():
            if key in SENSITIVE_KEYS:
                scrubbed[key] = "[REDACTED]"
            elif isinstance(value, dict):
                scrubbed[key] = self._scrub(value)
            else:
                scrubbed[key] = value
        return scrubbed

    def info(self, data: Dict[str, Any]):
        data_with_service = {"service": self.service_name, **data}
        scrubbed = self._scrub(data_with_service)
        self.logger.info(json.dumps(scrubbed))

    def debug(self, data: Dict[str, Any]):
        data_with_service = {"service": self.service_name, **data}
        scrubbed = self._scrub(data_with_service)
        self.logger.debug(json.dumps(scrubbed))

    def error(self, data: Dict[str, Any]):
        data_with_service = {"service": self.service_name, **data}
        scrubbed = self._scrub(data_with_service)
        self.logger.error(json.dumps(scrubbed))


class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs JSON-like structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        # TODO: forward to centralized logging / OTel
        return record.getMessage()


def get_logger(service_name: str) -> StructuredLogger:
    """Returns a structured logger for the given service."""
    return StructuredLogger(service_name)


def redact_user_id(user_id: str) -> str:
    """Redact user ID to first 8 chars + ellipsis."""
    if not user_id:
        return "unknown"
    if len(user_id) <= 8:
        return user_id + "…"
    return user_id[:8] + "…"


def truncate_id(value: str) -> str:
    """Truncate any ID to first 8 chars + ellipsis."""
    if not value:
        return "unknown"
    if len(value) <= 8:
        return value + "…"
    return value[:8] + "…"


def ensure_request_id(request, response) -> str:
    """
    Extract or generate request ID and set it on the response header.
    Returns the request ID.
    """
    request_id = request.headers.get("X-Request-Id")
    if not request_id:
        request_id = str(uuid.uuid4())
    response.headers["X-Request-Id"] = request_id
    return request_id
