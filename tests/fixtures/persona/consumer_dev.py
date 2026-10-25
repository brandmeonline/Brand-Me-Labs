"""Emulator-only dev seed for the gateway → consumer-domain end-to-end test
(Ultra plan 02 items 2-4). Fictional data only.

    python tests/fixtures/persona/consumer_dev.py pieces <brand> <count>
        Ingest <count> catalog pieces for a fictional house, as the providers
        lane would, newest last. Prints [{"variant_id", "house_ref"}].
    python tests/fixtures/persona/consumer_dev.py delivered <member_id> <variant_id> <units>
        Observe a delivered order the way commerce reports it, then hand the
        wardrobe events it produced to the rewards consumer, as the outbox
        subscriber would. Prints counts.
"""

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
if os.environ.get("BRANDME_MODE") != "development" or not os.environ.get("SPANNER_EMULATOR_HOST"):
    raise RuntimeError("fixture requires development and the Spanner emulator")

from google.cloud import spanner  # noqa: E402
from google.cloud.spanner_v1 import param_types  # noqa: E402

from brandme_core.domains.persona.lane import load_domains  # noqa: E402
from brandme_core.domains.rewards.consumer import RewardsConsumer  # noqa: E402
from brandme_core.domains.social.houses import catalog_variant_lookup, house_ref_of  # noqa: E402
from brandme_core.domains.wardrobe.service import WardrobeService  # noqa: E402
from brandme_core.events import EventEnvelope  # noqa: E402

OUTBOX_COLS = ("event_id", "event_type", "schema_version", "aggregate_type", "aggregate_id", "aggregate_version", "environment",
               "actor_ref", "correlation_id", "causation_id", "privacy_class", "payload", "occurred_at")


def database():
    client = spanner.Client(project=os.environ["SPANNER_PROJECT_ID"])
    return client.instance(os.environ["SPANNER_INSTANCE_ID"]).database(os.environ["SPANNER_DATABASE_ID"])


def pieces(db, brand: str, n: int):
    now = datetime.now(timezone.utc)
    out, rows = [], []
    for i in range(n):
        vid = str(uuid.uuid4())
        seen = now - timedelta(minutes=10 * (n - i))
        rows.append(("dev-provider", "dev-merchant", vid, vid, vid, brand, f"{brand} piece {i + 1}", "top", f"https://shop.example/{vid}",
                     9000 + 1000 * i, "USD", "in_stock", seen, "policy:dev", 1, False, seen, seen))
        out.append({"variant_id": vid, "house_ref": house_ref_of(brand)})
    with db.batch() as b:
        b.insert("CatalogSourceVariants", columns=(
            "provider_id", "merchant_id", "source_product_id", "source_variant_id", "variant_id", "brand", "title", "category", "product_url",
            "observed_price_minor", "observed_price_currency", "availability", "source_updated_at", "rights_policy_ref", "revision",
            "tombstoned", "first_seen_at", "last_ingested_at"), values=rows)
    return out


def delivered(db, member_id: str, variant_id: str, units: int):
    order_id = str(uuid.uuid4())
    event = EventEnvelope(event_type="commerce.order.observed", schema_version="1", aggregate_type="Order", aggregate_id=order_id,
                          aggregate_version=1, environment="development", actor_ref="service:commerce", correlation_id=str(uuid.uuid4()),
                          privacy_class="member_private",
                          payload={"order_id": order_id, "member_id": member_id, "order_status": "accepted",
                                   "lines": [{"variant_id": variant_id, "source_variant_ref": "DEV-SKU", "ordered": units, "delivered": units,
                                              "returned": 0}]})
    reduced = WardrobeService(db, catalog_lookup=catalog_variant_lookup(db)).apply_order_observation(event)
    with db.snapshot() as s:
        rows = list(s.execute_sql(f"SELECT {', '.join(OUTBOX_COLS)} FROM OutboxEvents WHERE event_type='wardrobe.item.created' "
                                  "AND causation_id=@c ORDER BY occurred_at", params={"c": event.event_id}, param_types={"c": param_types.STRING}))
    consumer = RewardsConsumer(db)
    for r in rows:
        consumer.handle(EventEnvelope.from_row(dict(zip(OUTBOX_COLS, r))))
    return {"items_created": reduced.get("created", 0), "events_delivered": len(rows)}


if __name__ == "__main__":
    load_domains()
    db = database()
    cmd, *args = sys.argv[1:]
    if cmd == "pieces":
        print(json.dumps(pieces(db, args[0], int(args[1]))))
    elif cmd == "delivered":
        print(json.dumps(delivered(db, args[0], args[1], int(args[2]))))
    else:
        raise SystemExit(f"unknown command {cmd}")
