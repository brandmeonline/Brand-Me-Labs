"""Operator authority for rewards: see ``persona.kernel.require_operator``
(``moderation:admin``, aal2 outside development, never delegated, never self)."""

from brandme_core.domains.persona.kernel import OPERATOR_SCOPE, require_not_self, require_operator

__all__ = ["OPERATOR_SCOPE", "require_not_self", "require_operator"]
