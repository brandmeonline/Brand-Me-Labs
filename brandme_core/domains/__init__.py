"""Consumer domain modules (spec ch.03 §1.6: modules inside brain + shared lib first).

Framework (opus-foundation lane): ``base`` (principal, policy, commands,
idempotency, data categories) and ``events`` (event type registration).
Each subpackage README reserves a domain for its owning lane.
"""
from . import events  # noqa: F401  registers identity/platform event types
from .base import (
    CommandContext,
    DataCategory,
    DomainError,
    Forbidden,
    Grant,
    IdempotencyConflict,
    InvalidTransition,
    NotFound,
    PreconditionRequired,
    Principal,
    VersionConflict,
    authorize,
    canonical_digest,
    data_categories,
    expect_version,
    parse_if_match,
    register_data_category,
    run_command,
    run_idempotent_command,
)

__all__ = [
    "CommandContext", "DataCategory", "DomainError", "Forbidden", "Grant", "IdempotencyConflict",
    "InvalidTransition", "NotFound", "PreconditionRequired", "Principal", "VersionConflict", "authorize",
    "canonical_digest", "data_categories", "expect_version", "parse_if_match", "register_data_category",
    "run_command", "run_idempotent_command",
]
