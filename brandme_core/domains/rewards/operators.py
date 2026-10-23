"""Operator authority for rewards (ch.03 §3: console-only ``moderation:admin``).

Operator roles need stronger authentication: outside ``development`` the
session must be ``aal2``. Delegated (agent) principals are never operators.
An operator can never act on their own reward account (self-review)."""

from __future__ import annotations

from brandme_core.domains.persona.kernel import Forbidden, Principal, ServicePrincipal

OPERATOR_SCOPE = "moderation:admin"


def require_operator(principal: Principal) -> None:
    if isinstance(principal, ServicePrincipal) or principal.delegation_id is not None:
        raise Forbidden("operator session required")
    if OPERATOR_SCOPE not in principal.scopes:
        raise Forbidden(f"scope {OPERATOR_SCOPE} required")
    if principal.environment != "development" and principal.assurance_level != "aal2":
        raise Forbidden("operator actions require a recently strengthened (aal2) session")


def require_not_self(principal: Principal, member_id: str) -> None:
    if principal.member_id == member_id:
        raise Forbidden("operators cannot review or correct their own rewards")
