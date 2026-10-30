"""Closed list of the event catalogs the outbox worker publishes.

Each lane registers its closed contracts with ``brandme_core.events.registry``
when its catalog module is imported (then calls ``loader``, if one is named).
Adding a lane is a reviewed foundation change to ``CATALOGS``: nothing is read
from the environment and no module is named by configuration. A failure inside
any catalog refuses worker startup; see README.md "Event catalogs".
"""
from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Catalog:
    lane: str
    module: str
    loader: Optional[str] = None
    # Set only while a new lane's PR is unmerged; delete it when the PR merges.
    # Then, and only then, a module that does not exist is reported "absent"
    # instead of refusing startup. Its parent package must already exist on main:
    # find_spec imports the parent, and a missing parent refuses (fails closed).
    until_merged: Optional[str] = None


CATALOGS = (
    Catalog("foundation", "brandme_core.domains.events"),
    # Importing the lane module registers only persona; load_domains() adds the rest.
    Catalog("consumer-domains", "brandme_core.domains.persona.lane", loader="load_domains"),
    Catalog("commerce-agents", "brandme_core.domains.commerce.events"),
)


class CatalogUnavailable(RuntimeError):
    """A catalog failed to load. Carries the lane only, never the cause's text."""

    def __init__(self, lane: str) -> None:
        super().__init__("event_catalog_unavailable")
        self.lane = lane


def load_catalogs() -> dict[str, str]:
    """Register every catalog's contracts; returns {lane: "loaded" | "absent"}."""
    status = {}
    for catalog in CATALOGS:
        try:
            if catalog.until_merged and importlib.util.find_spec(catalog.module) is None:
                status[catalog.lane] = "absent"
                continue
            module = importlib.import_module(catalog.module)
            if catalog.loader:
                getattr(module, catalog.loader)()
        except Exception as exc:
            raise CatalogUnavailable(catalog.lane) from exc
        status[catalog.lane] = "loaded"
    return status
