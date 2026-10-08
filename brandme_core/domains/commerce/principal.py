"""Authenticated principal (ch.03 §3).

A ``Principal`` is produced by the identity boundary (gateway session or MCP
assertion verification). Domain code never builds one from request fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Optional

ENVIRONMENTS = ("demo", "development", "sandbox", "production")


@dataclass(frozen=True)
class Principal:
    member_id: str
    subject: str
    issuer: str
    client_id: str
    scopes: FrozenSet[str]
    assurance_level: str  # e.g. "aal1", "aal2"
    environment: str
    session_id: Optional[str] = None
    delegation_id: Optional[str] = None
    # True only for a first-party consumer session rendered by Brand.Me's own
    # deterministic UI. Agents/MCP clients are never trusted surfaces.
    first_party_session: bool = False

    def __post_init__(self) -> None:
        if self.environment not in ENVIRONMENTS:
            raise ValueError(f"unknown environment {self.environment!r}")
        if not self.member_id or not self.subject or not self.issuer or not self.client_id:
            raise ValueError("principal identity fields are required")
        object.__setattr__(self, "scopes", frozenset(self.scopes))

    @property
    def is_agent(self) -> bool:
        return self.delegation_id is not None or not self.first_party_session

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes
