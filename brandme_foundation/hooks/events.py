"""Event envelope carried on every hook topic.

Ported from Lux `protocols/v1/entities.HookEvent`. The tenant key is
`owner_id` — the broker refuses to dispatch an event without one, which is
what makes the cross-tenant barrier enforceable at the transport layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HookEvent(_Base):
    """One event published on a Brand.Me lifecycle topic."""

    event_id: str
    topic: str
    owner_id: str
    payload: dict[str, Any]
    occurred_at: datetime
