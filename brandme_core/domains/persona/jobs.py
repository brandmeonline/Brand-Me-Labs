"""
Scheduled work for the consumer-domains lane (dev form): one process a
scheduler or long-running worker can own.

    python -m brandme_core.domains.persona.jobs [--once]

* ``decisions.close_due``: close decisions whose server deadline passed and
  settle their counts (ch.01 §6.3).
* ``benefits.expire_due``: release pending reservations past their expiry and
  return the points.
* Media retention (unsaved previews, blob purge retries) needs the API's real
  object store. Only a per-process in-memory store exists, so this process
  reports it as ``not_configured`` instead of pretending to sweep.
* Benefit fulfillment needs a partner fulfiller per benefit; none exists, so it
  is ``not_configured`` too.

Every job is bounded and idempotent; output is counts only (no member ids).
Configuration: ``BRANDME_MODE`` equal to ``ENVIRONMENT``, ``SPANNER_PROJECT_ID``,
``SPANNER_INSTANCE_ID``, ``SPANNER_DATABASE_ID``; the Spanner emulator is
required in demo/development and refused in sandbox/production.
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
    from brandme_core.domains.social.decisions import DecisionService

    from .lane import load_domains

    load_domains()
    benefits = BenefitService(database)
    out: Dict[str, Any] = {
        "decisions": DecisionService(database).close_due(environment=environment),
        "reservations": benefits.expire_due(environment=environment),
    }
    if media is None:
        out["media"] = "not_configured"
    else:
        out["media"] = {**media.expire_due(), "purge_retried": media.purge_pending()}
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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Consumer-domains scheduled jobs")
    parser.add_argument("--once", action="store_true", help="run one pass and exit")
    args = parser.parse_args(argv)
    try:
        cfg = _config(os.environ)
        from google.cloud import spanner

        db = spanner.Client(project=cfg["SPANNER_PROJECT_ID"]).instance(cfg["SPANNER_INSTANCE_ID"]).database(cfg["SPANNER_DATABASE_ID"])
    except Exception:
        print('{"status":"startup_refused"}', flush=True)
        return 2
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        try:
            print(json.dumps({"status": "ran", **run_jobs(db, environment=cfg["environment"])}, sort_keys=True), flush=True)
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
