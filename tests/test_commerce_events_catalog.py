"""Commerce events and main's Pub/Sub outbox worker (brandme_core.events.worker).

The worker publishes only event types registered in its process. Its closed
catalog list (``brandme_core/events/catalogs.py``) imports
``brandme_core.domains.commerce.events``, so committed commerce events are published.
These tests pin what that import needs to be safe: the commerce catalog loads on
its own, without the commerce service or provider adapters, and with it loaded the
worker accepts commerce types in its allowlist.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMMERCE_TYPES = {"commerce.delegation.created", "commerce.delegation.revoked", "commerce.quote.ready",
                  "commerce.purchase.approval_requested", "commerce.purchase.authorized", "commerce.order.observed"}
WORKER_ENV = {"BRANDME_MODE": "development", "ENVIRONMENT": "development", "SPANNER_EMULATOR_HOST": "localhost:9010",
              "PUBSUB_EMULATOR_HOST": "localhost:8085", "SPANNER_PROJECT_ID": "p", "SPANNER_INSTANCE_ID": "i",
              "SPANNER_DATABASE_ID": "d", "OUTBOX_EVENT_TYPES": "commerce.order.observed"}


def _run(code: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BRANDME_", "OUTBOX_"))}
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_commerce_catalog_loads_without_the_service_or_providers():
    got = _run("""
import json, sys
import brandme_core.domains.commerce.events
from brandme_core.events import registry
print(json.dumps({"types": sorted(t.event_type for t in registry.types() if t.event_type.startswith("commerce.")),
                  "heavy": sorted(m for m in sys.modules if m.startswith(("brandme_core.domains.commerce.service",
                                  "brandme_core.domains.providers", "rfc8785")))}))
""")
    assert set(got["types"]) == COMMERCE_TYPES
    assert got["heavy"] == []


def test_worker_allowlist_accepts_commerce_types_once_the_catalog_is_imported():
    got = _run(f"""
import json, sys
from brandme_core.events.worker import WorkerConfig
env = {WORKER_ENV!r}
imported = "brandme_core.domains.commerce.events" in sys.modules
default = WorkerConfig.from_env({{k: v for k, v in env.items() if k != "OUTBOX_EVENT_TYPES"}})
after = WorkerConfig.from_env(env).event_types
print(json.dumps({{"imported": imported, "default": list(default.event_types), "catalogs": dict(default.catalogs),
                  "after": list(after)}}))
""")
    # Nothing here imports commerce: the worker's own catalog list loads it.
    assert got["imported"] is False and got["catalogs"]["commerce-agents"] == "loaded"
    assert COMMERCE_TYPES <= set(got["default"])
    assert got["after"] == ["commerce.order.observed"]
