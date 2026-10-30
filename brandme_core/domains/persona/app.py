"""
The consumer-domain HTTP service: this lane's routers behind the gateway's
principal assertion (Ultra plan 02, item 1).

    python -m brandme_core.domains.persona.app [--check]

Mounted: persona, wardrobe and outfits, social (relationships, decisions,
shares, notifications, reports), Home = Flow and followed houses, rewards,
benefits, house standings, surveys and in-app credit, closet visibility and
the persona card, small-group rooms, media uploads and try-on. The gateway mounts the matching public routers
(brandme-gateway/src/routes/v1/index.ts) and reaches this service through
its DomainClient (brandme-gateway/src/services/domains.ts).

Not mounted: the ``/ops`` moderation and dispute routers. Operator authority
needs the console's own authentication (ch.03 §3), which does not exist yet.

Configuration (``BRANDME_MODE`` equal to ``ENVIRONMENT``):
- Spanner: ``SPANNER_PROJECT_ID``, ``SPANNER_INSTANCE_ID``, ``SPANNER_DATABASE_ID``.
  The Spanner emulator is required in demo/development and refused in strict modes.
- Assertions: ``CONSUMER_DOMAIN_ASSERTION_ISSUER``, plus ``CONSUMER_DOMAIN_ASSERTION_JWKS``
  (public keys only).
- Media: ``BRANDME_MEDIA_BUCKET`` (``media/gcs_store.from_environment``). Without a
  bucket, the media and try-on routes are not mounted.
- ``PORT`` (default 8010).

No try-on provider is approved. ``BRANDME_TRYON_PROVIDER`` is unset by default, so photo
previews report ``photo_preview_not_configured``. ``simulated`` (demo/development only)
selects the labelled stand-in. The jobs process dispatches and collects jobs; this
service never calls a provider.
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Callable, List, Mapping, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .assertion import DomainAssertionVerifier, bearer_resolver
from .lane import load_domains

DEFAULT_PORT = 8010


def create_app(database: Any, *, resolve_principal: Callable[[Any], Any], media_store: Any = None, providers: Any = None,
               catalog: Any = None) -> FastAPI:
    """``catalog`` is the houses port for Flow and standings; default ``CatalogHouses``."""
    load_domains()
    from brandme_core.domains.media.api import create_media_router
    from brandme_core.domains.media.providers import ProviderRegistry
    from brandme_core.domains.media.service import MediaService
    from brandme_core.domains.rewards.api import create_rewards_router
    from brandme_core.domains.rewards.benefits import BenefitService
    from brandme_core.domains.rewards.credits import CreditService
    from brandme_core.domains.rewards.service import RewardsService
    from brandme_core.domains.rewards.standing import StandingService
    from brandme_core.domains.rewards.surveys import SurveyService
    from brandme_core.domains.social.api import create_flow_router, create_rooms_router, create_social_router
    from brandme_core.domains.social.decisions import DecisionService
    from brandme_core.domains.social.flow import FlowService
    from brandme_core.domains.social.houses import CatalogHouses, HouseService, catalog_piece_exists
    from brandme_core.domains.social.notifications import NotificationService
    from brandme_core.domains.social.relationships import RelationshipService, friendship_proposal_policy
    from brandme_core.domains.social.reports import ReportService
    from brandme_core.domains.social.rooms import RoomService
    from brandme_core.domains.social.shares import ShareService
    from brandme_core.domains.wardrobe.api import create_wardrobe_router
    from brandme_core.domains.wardrobe.outfits import OutfitService
    from brandme_core.domains.wardrobe.service import WardrobeService

    from brandme_core.domains.wardrobe.visibility import ClosetVisibilityService

    from .api import create_card_router, create_persona_router
    from .card import PersonaCardService
    from .onboarding import GuestMigrationService
    from .service import PersonaService

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    persona = PersonaService(database)
    app.include_router(create_persona_router(persona, GuestMigrationService(database, persona), resolve_principal))
    houses = catalog if catalog is not None else CatalogHouses()
    app.include_router(create_wardrobe_router(WardrobeService(database), OutfitService(database, proposal_policy=friendship_proposal_policy),
                                              resolve_principal, ClosetVisibilityService(database, catalog=houses)))
    app.include_router(create_card_router(PersonaCardService(database, persona=persona, catalog=houses), resolve_principal))
    app.include_router(create_social_router(RelationshipService(database), DecisionService(database, catalog_check=catalog_piece_exists),
                                            ShareService(database),
                                            NotificationService(database), resolve_principal, ReportService(database)))
    app.include_router(create_rooms_router(RoomService(database, catalog_check=catalog_piece_exists), resolve_principal))
    app.include_router(create_flow_router(FlowService(database, catalog=houses, persona=persona), HouseService(database, catalog=houses),
                                          resolve_principal))
    app.include_router(create_rewards_router(RewardsService(database), BenefitService(database), resolve_principal,
                                             StandingService(database, catalog=houses), SurveyService(database), CreditService(database)))
    if media_store is not None:
        app.include_router(create_media_router(MediaService(database, media_store, providers or ProviderRegistry()), resolve_principal))

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok", "media": "mounted" if media_store is not None else "not_configured"},
                            headers={"Cache-Control": "no-store"})

    return app


def _config(env: Mapping[str, str]) -> dict:
    environment = env.get("ENVIRONMENT", "")
    if environment not in ("demo", "development", "sandbox", "production") or env.get("BRANDME_MODE") != environment:
        raise ValueError("BRANDME_MODE and ENVIRONMENT must agree")
    if (environment in ("sandbox", "production")) == bool(env.get("SPANNER_EMULATOR_HOST")):
        raise ValueError("the Spanner emulator is required in demo/development and refused in sandbox/production")
    keys = ("SPANNER_PROJECT_ID", "SPANNER_INSTANCE_ID", "SPANNER_DATABASE_ID", "CONSUMER_DOMAIN_ASSERTION_ISSUER",
            "CONSUMER_DOMAIN_ASSERTION_JWKS")
    if any(not env.get(k, "").strip() for k in keys):
        raise ValueError("explicit Spanner and assertion configuration required")
    port = int(env.get("PORT", str(DEFAULT_PORT)))
    return {"environment": environment, "port": port, **{k: env[k] for k in keys}}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Consumer-domain HTTP service")
    parser.add_argument("--check", action="store_true", help="validate configuration and exit")
    args = parser.parse_args(argv)
    try:
        from brandme_core.boot import guard

        cfg = _config(os.environ)
        # Unaudited processes are refused in strict modes by the shared boot guard.
        guard("consumer_domains")
        from google.cloud import spanner

        from brandme_core.domains.media import gcs_store

        db = spanner.Client(project=cfg["SPANNER_PROJECT_ID"]).instance(cfg["SPANNER_INSTANCE_ID"]).database(cfg["SPANNER_DATABASE_ID"])
        verifier = DomainAssertionVerifier.from_jwks(issuer=cfg["CONSUMER_DOMAIN_ASSERTION_ISSUER"], jwks=cfg["CONSUMER_DOMAIN_ASSERTION_JWKS"],
                                                     environment=cfg["environment"])
        from brandme_core.domains.media.providers import registry_from_environment

        store = gcs_store.from_environment(os.environ)
        app = create_app(db, resolve_principal=bearer_resolver(verifier), media_store=store, providers=registry_from_environment(os.environ))
    except Exception:
        print('{"status":"startup_refused"}', flush=True)
        return 2
    if args.check:
        print('{"status":"ready"}', flush=True)
        return 0
    import uvicorn

    uvicorn.run(app, host="127.0.0.1" if cfg["environment"] in ("demo", "development") else "0.0.0.0", port=cfg["port"],
                access_log=False, proxy_headers=False, server_header=False, limit_concurrency=64, timeout_keep_alive=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
