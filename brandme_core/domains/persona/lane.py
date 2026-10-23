"""
Integration points of the consumer-domains lane (persona, wardrobe, social,
rewards, media) for the services that compose them: the privacy/My Data
service, the outbox worker and event subscribers. Importing this module has no
side effects beyond importing the five domain packages (which register their
event types and foundation data categories).

* ``register_consumer_domains(registry, database=, media_store=)`` registers the
  five native ``DomainPrivacyHandler`` instances in a privacy-lane
  ``PrivacyRegistry`` (e.g. the read API's ``ReadService.catalog``) and wires
  the media domain's blob purge to the given database and object store. It is
  idempotent for the same registry.
* ``consumer_event_types()`` lists this lane's registered event contracts by
  privacy class: the closed catalog an outbox worker must load (by importing
  this module) before it can publish them. Types not loaded stay pending.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional, Tuple

CONSUMER_DOMAINS: Tuple[str, ...] = ("persona", "wardrobe", "social", "rewards", "media")


def load_domains() -> None:
    """Import the five packages (registers event types and data categories)."""
    for d in CONSUMER_DOMAINS:
        importlib.import_module(f"brandme_core.domains.{d}")


def consumer_privacy_handlers() -> List[Any]:
    """One handler per domain: the instance registered at import when there is
    one, otherwise a fresh one. Raises if the privacy lane is not installed."""
    load_domains()
    handlers = []
    for d in CONSUMER_DOMAINS:
        mod = importlib.import_module(f"brandme_core.domains.{d}.deletion")
        handler = mod.PRIVACY_HANDLER or mod.build_privacy_handler()
        if handler is None:
            raise RuntimeError("brandme_core.domains.privacy is not installed; consumer domains cannot register")
        handlers.append(handler)
    return handlers


def register_consumer_domains(registry: Any, *, database: Any = None, media_store: Any = None) -> List[str]:
    """Register persona/wardrobe/social/rewards/media in ``registry``. Returns the
    domain names covered. ``database``/``media_store`` let deletion purge try-on
    blobs after commit; without them media deletion reports blobs as pending."""
    from brandme_core.domains.media import deletion as media_deletion

    if database is not None or media_store is not None:
        media_deletion.configure_store(media_store, database)
    known = {c.key for c in registry.categories()}
    for handler in consumer_privacy_handlers():
        if all(c.key in known for c in handler.categories()):
            continue  # already registered in this registry
        registry.register(handler)
    return list(CONSUMER_DOMAINS)


def consumer_event_types() -> Dict[str, List[str]]:
    """{privacy_class: [event_type@schema_version, ...]} for this lane's contracts."""
    load_domains()
    from brandme_core.events import registry

    prefixes = ("persona.", "wardrobe.", "closet.", "outfit.", "relationship.", "member.blocked", "decision.", "share.",
                "moderation.", "reward.", "badge.", "benefit.", "tryon.", "media.")
    out: Dict[str, List[str]] = {}
    for t in registry.types():
        if t.event_type.startswith(prefixes):
            out.setdefault(t.privacy_class, []).append(f"{t.event_type}@{t.schema_version}")
    return {k: sorted(v) for k, v in sorted(out.items())}


def coverage(registry: Any) -> Dict[str, Optional[Any]]:
    """Which consumer domains a registry actually covers (for inventory honesty)."""
    domains = sorted({c.domain for c in registry.categories()})
    return {"domains": domains, "consumer_domains_complete": all(d in domains for d in CONSUMER_DOMAINS)}
