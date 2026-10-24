"""Rewards domain (W05): append-only points ledger settled from committed
domain events, UTC caps, linked reversals with recovery-due, six badges,
benefit reservations with durable fulfillment, member disputes and operator
corrections. See ch.01 §7, ch.03 §4 and contracts/reward-rules.json.

Importing the package registers reward event types and data categories.
"""

from . import deletion as _deletion  # noqa: F401
from . import events as _events  # noqa: F401
