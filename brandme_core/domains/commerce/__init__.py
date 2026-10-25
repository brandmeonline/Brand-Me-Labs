"""Bounded commerce domain (W07): quotes, approvals, budgets, purchases, reconciliation."""

from .privacy_handler import register as _register_privacy

_register_privacy()  # My Data: commerce.agent_grants, commerce.carts_quotes, commerce.orders
