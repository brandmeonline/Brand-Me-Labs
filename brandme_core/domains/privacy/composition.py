"""
Copyright (c) Brand.Me, Inc. All rights reserved.

My Data composition in dev form (round 03 build step 4): one registry holding
every real domain handler, and a ``MyDataService`` over it.

Registered: the five consumer domains (persona, wardrobe, social, rewards,
media), commerce, rights and foundation's platform records. This is not a
deployable composition. Deletion still needs one serialized executor per
subject (``MyDataService.run_deletion``), and the identity step (founder flag
F-identity, contract item 9 in ``deletion.py``) is foundation's to register.
Demo and development only.
"""

from __future__ import annotations

from typing import Any

from .deletion import PrivacyRegistry
from .privacy import MyDataService, ObjectStore

DEV_ENVIRONMENTS = ("demo", "development")


def compose_registry(*, database: Any = None, media_store: Any = None, media_providers: Any = None) -> PrivacyRegistry:
    """A fresh registry with every real handler; registration checks apply to each."""
    from brandme_core.domains.commerce import privacy_handler as commerce
    from brandme_core.domains.persona.lane import register_consumer_domains
    from brandme_core.domains.rights.privacy_handler import RightsPrivacyHandler
    from brandme_core.events.erasure import register_platform_privacy

    reg = PrivacyRegistry()
    register_consumer_domains(reg, database=database, media_store=media_store, media_providers=media_providers)
    commerce.register(reg)
    reg.register(RightsPrivacyHandler())
    if register_platform_privacy(reg) is None:
        raise RuntimeError("foundation's platform privacy handler did not register")
    return reg


def compose_my_data(database: Any, store: ObjectStore, *, environment: str, media_store: Any = None,
                    media_providers: Any = None) -> MyDataService:
    if environment not in DEV_ENVIRONMENTS:
        raise ValueError("the dev-form My Data composition runs in demo or development only")
    reg = compose_registry(database=database, media_store=media_store, media_providers=media_providers)
    return MyDataService(database, store, reg, environment=environment)
