"""Commerce domain errors, mapped onto the foundation ``DomainError`` family (ch.03 §6).

Subclassing the foundation classes keeps one problem+json vocabulary across
domains: an HTTP adapter that maps ``DomainError`` maps these too.
"""

from __future__ import annotations

from brandme_core.domains import base


class CommerceError(base.DomainError):
    code = "commerce_error"
    status = 422
    retryable = False


class InvalidRequest(CommerceError):
    code, status = "invalid_request", 400


class NotFound(CommerceError, base.NotFound):
    code, status = "not_found", 404


class Forbidden(CommerceError, base.Forbidden):
    code, status = "forbidden", 403


class InvalidQuote(CommerceError):
    code, status = "invalid_quote", 422


class QuoteExpired(CommerceError):
    code, status = "quote_expired", 422


class ApprovalInvalid(CommerceError):
    code, status = "approval_invalid", 422


class DelegationInvalid(CommerceError):
    code, status = "delegation_invalid", 403


class DelegationConflict(CommerceError):
    code, status = "active_delegation_exists", 409


class BudgetExceeded(CommerceError):
    code, status = "budget_exceeded", 422


class InvalidTransition(CommerceError, base.InvalidTransition):
    code, status = "invalid_transition", 422


class VersionConflict(CommerceError, base.VersionConflict):
    code, status = "revision_conflict", 409

    def __init__(self, detail: str, *, code: str | None = None, current_version: int | None = None):
        CommerceError.__init__(self, detail, code=code)
        self.current_version = current_version


class IdempotencyConflict(CommerceError, base.IdempotencyConflict):
    code, status = "idempotency_key_reused", 409


class ProcessingRestricted(CommerceError):
    """A member or agent write refused by the My Data processing guard (deletion pending or restricted)."""
    code, status = "processing_restricted", 409


class CapabilityUnavailable(CommerceError):
    code, status, retryable = "capability_unavailable", 503, False
