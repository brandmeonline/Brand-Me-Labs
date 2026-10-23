"""Commerce domain errors mapped to problem+json codes (ch.03 §6)."""

from __future__ import annotations


class CommerceError(Exception):
    """Base error. ``code`` is a stable problem code; ``status`` the HTTP mapping."""

    code = "commerce_error"
    status = 422
    retryable = False

    def __init__(self, detail: str, *, code: str | None = None):
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code


class NotFound(CommerceError):
    code, status = "not_found", 404


class Forbidden(CommerceError):
    code, status = "forbidden", 403


class InvalidQuote(CommerceError):
    code, status = "invalid_quote", 422


class QuoteExpired(CommerceError):
    code, status = "quote_expired", 422


class ApprovalInvalid(CommerceError):
    code, status = "approval_invalid", 422


class DelegationInvalid(CommerceError):
    code, status = "delegation_invalid", 403


class BudgetExceeded(CommerceError):
    code, status = "budget_exceeded", 422


class InvalidTransition(CommerceError):
    code, status = "invalid_transition", 422


class VersionConflict(CommerceError):
    code, status = "version_conflict", 409


class IdempotencyConflict(CommerceError):
    code, status = "idempotency_conflict", 409


class CapabilityUnavailable(CommerceError):
    code, status, retryable = "capability_unavailable", 503, False
