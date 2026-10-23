"""Emulator-only fixture for the gateway → running read API integration test."""
import importlib.util
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
if os.environ.get("BRANDME_MODE") != "development" or not os.environ.get("SPANNER_EMULATOR_HOST"):
    raise RuntimeError("fixture requires development and the Spanner emulator")
spec = importlib.util.spec_from_file_location("seed_migrations", ROOT / "brandme-data/spanner/migrations/runner.py")
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)
db = runner.open_database(create=True, wait=10)
runner.migrate_up(db, log=lambda *_: None)
with db.batch() as b:
    now = datetime.now(timezone.utc)
    b.insert("RightsEntitlements", columns=("network", "contract_address", "entitlement_id", "asset_id", "issuer_id", "epoch",
             "status", "transferable", "reprintable", "controller_subject_ref", "last_tx_id", "last_block_height", "finalized_at", "updated_at", "projection_version"),
             values=[("preprod", "ab" * 32, "cd" * 32, "33333333-3333-4333-8333-333333333333", "ef" * 32,
                      1, "active", True, False, "11111111-1111-4111-8111-111111111111", "fixture-tx", 10, now, now, 1)])
