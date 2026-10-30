"""
Scheduled work for the consumer-domains lane (dev form): one process a
scheduler or long-running worker can own.

    python -m brandme_core.domains.persona.jobs [--once]

* ``decisions.close_due``: close decisions whose server deadline passed and
  settle their counts (ch.01 §6.3).
* ``benefits.expire_due``: release pending reservations past their expiry and
  return the points.
* ``media.dispatch_queued`` / ``collect_processing`` / ``expire_due`` /
  ``purge_pending``: send queued try-on jobs, collect results, expire unsaved
  media and retry blob purges, on the GCS store selected by
  ``BRANDME_MEDIA_BUCKET`` (``media/gcs_store.from_environment``;
  ``STORAGE_EMULATOR_HOST`` for the local emulator in demo/development) and the
  provider chosen by ``BRANDME_TRYON_PROVIDER``. Without a bucket this reports
  ``not_configured``. Without a provider, queued jobs stay queued. A provider
  deletion that could not be requested is recorded as ``failed``, never as
  confirmed.
* ``standings.recompute_if_due``: rebuild per-house loyalty tiers from
  verified purchases at most once a day (``rewards/standing.py``).
* ``credits.expire_due``: return the points of in-app credit unused after a
  year (``rewards/credits.py``).
* ``cards.recompose_due``: recompose persona cards marked stale by trigger
  events, and backfill every card daily (``persona/card.py``).
* Benefit fulfillment needs a partner fulfiller per benefit; none exists, so it
  is ``not_configured`` too.

Every job is bounded and idempotent; output is counts only (no member ids).
Configuration: ``BRANDME_MODE`` equal to ``ENVIRONMENT``, ``SPANNER_PROJECT_ID``,
``SPANNER_INSTANCE_ID``, ``SPANNER_DATABASE_ID``; the Spanner emulator is
required in demo/development and refused in sandbox/production, and so is
the storage emulator.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import threading
from typing import Any, Dict, List, Mapping, Optional

INTERVAL_SECONDS = 30


def run_jobs(database: Any, *, environment: str, media: Any = None, fulfillers: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """One bounded pass of every lane job. ``media`` is a MediaService wired to
    the real object store; ``fulfillers`` maps benefit_id → fulfiller."""
    from brandme_core.domains.rewards.benefits import BenefitService
    from brandme_core.domains.rewards.credits import CreditService
    from brandme_core.domains.rewards.standing import StandingService
    from brandme_core.domains.social.decisions import DecisionService
    from brandme_core.domains.social.houses import CatalogHouses

    from .card import PersonaCardService
    from .lane import load_domains
    from .service import PersonaService

    load_domains()
    benefits = BenefitService(database)
    cards = PersonaCardService(database, persona=PersonaService(database), catalog=CatalogHouses())
    standings = StandingService(database, catalog=CatalogHouses()).recompute_if_due()
    if standings != "not_due":
        cards.mark_all_with_standings()
    out: Dict[str, Any] = {
        "decisions": DecisionService(database).close_due(environment=environment),
        "reservations": benefits.expire_due(environment=environment),
        "standings": standings,
        "credits_expired": CreditService(database).expire_due(),
        "cards": cards.recompose_due(),
    }
    if media is None:
        out["media"] = "not_configured"
    else:
        out["media"] = {"dispatched": media.dispatch_queued(), "collected": media.collect_processing(), **media.expire_due(),
                        "purge_retried": media.purge_pending()}
    if not fulfillers:
        out["fulfillment"] = "not_configured"
    else:
        out["fulfillment"] = {b: benefits.run_fulfillment(f, benefit_id=b, environment=environment) for b, f in fulfillers.items()}
    return out


def _config(env: Mapping[str, str]) -> Dict[str, str]:
    environment = env.get("ENVIRONMENT", "")
    if environment not in ("demo", "development", "sandbox", "production") or env.get("BRANDME_MODE") != environment:
        raise ValueError("BRANDME_MODE and ENVIRONMENT must agree")
    strict = environment in ("sandbox", "production")
    if strict == bool(env.get("SPANNER_EMULATOR_HOST")):
        raise ValueError("the Spanner emulator is required in demo/development and refused in sandbox/production")
    keys = ("SPANNER_PROJECT_ID", "SPANNER_INSTANCE_ID", "SPANNER_DATABASE_ID")
    if any(not env.get(k, "").strip() for k in keys):
        raise ValueError("explicit Spanner configuration required")
    return {"environment": environment, **{k: env[k] for k in keys}}


def _media(database: Any, env: Mapping[str, str]) -> Any:
    from brandme_core.domains.media import gcs_store
    from brandme_core.domains.media.providers import registry_from_environment
    from brandme_core.domains.media.service import MediaService

    store = gcs_store.from_environment(env)
    return None if store is None else MediaService(database, store, registry_from_environment(env))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Consumer-domains scheduled jobs")
    parser.add_argument("--once", action="store_true", help="run one pass and exit")
    args = parser.parse_args(argv)
    try:
        cfg = _config(os.environ)
        from google.cloud import spanner

        db = spanner.Client(project=cfg["SPANNER_PROJECT_ID"]).instance(cfg["SPANNER_INSTANCE_ID"]).database(cfg["SPANNER_DATABASE_ID"])
        media = _media(db, os.environ)
    except Exception:
        print('{"status":"startup_refused"}', flush=True)
        return 2
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        try:
            print(json.dumps({"status": "ran", **run_jobs(db, environment=cfg["environment"], media=media)}, sort_keys=True), flush=True)
        except Exception:
            print('{"status":"jobs_unavailable"}', flush=True)
            if args.once:
                return 1
        if args.once:
            return 0
        stop.wait(INTERVAL_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
