"""Principal handling for commerce (ch.03 §3), on top of the foundation principal.

The authenticated principal is ``brandme_core.domains.base.Principal``, produced
by the identity boundary (gateway session/bearer resolution or the MCP executor
assertion). Domain code never builds one from request fields.

Foundation's principal has no first-party flag, so commerce uses one rule:
**first-party = an interactive session (``session_id``) with no delegation.**
Everything else (bearer API clients, MCP agents) is an agent and must act
through an active delegation the member granted on the trusted surface.
"""

from __future__ import annotations

from brandme_core.domains.base import Principal

ENVIRONMENTS = ("demo", "development", "sandbox", "production")
LOCAL_ENVIRONMENTS = frozenset({"demo", "development"})
_AAL = {"aal1": 1, "aal2": 2, "aal3": 3}


def is_first_party(principal: Principal) -> bool:
    return principal.session_id is not None and principal.delegation_id is None


def is_agent(principal: Principal) -> bool:
    return not is_first_party(principal)


def validate_principal(principal: Principal) -> None:
    if not isinstance(principal, Principal):
        raise TypeError("commerce requires brandme_core.domains.base.Principal")
    if principal.environment not in ENVIRONMENTS:
        raise ValueError(f"unknown environment {principal.environment!r}")
    if not principal.member_id or not principal.subject:
        raise ValueError("principal identity fields are required")


def meets_assurance(principal: Principal, required: str, *, simulation_ok: bool) -> bool:
    """``simulated`` (foundation dev identity) counts only for local simulation flows."""
    if principal.assurance_level == "simulated":
        return simulation_ok and principal.environment in LOCAL_ENVIRONMENTS
    return _AAL.get(principal.assurance_level, 0) >= _AAL[required]


__all__ = ["Principal", "is_first_party", "is_agent", "validate_principal", "meets_assurance",
           "ENVIRONMENTS", "LOCAL_ENVIRONMENTS"]
