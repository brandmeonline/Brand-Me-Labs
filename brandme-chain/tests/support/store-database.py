"""Apply the real migration chain to an isolated emulator database."""
import importlib.util
import os
import sys
from pathlib import Path
from google.cloud import spanner

assert os.environ.get('SPANNER_EMULATOR_HOST'), 'emulator required'
root = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('migrations', root / 'brandme-data/spanner/migrations/runner.py')
runner = importlib.util.module_from_spec(spec)
sys.modules['migrations'] = runner
spec.loader.exec_module(runner)
client = spanner.Client(project='test-project')
instance = client.instance('brandme-instance')
if not instance.exists():
    client.instance('brandme-instance', configuration_name='projects/test-project/instanceConfigs/emulator-config', node_count=1).create().result(60)
db = instance.database(sys.argv[2])
if sys.argv[1] == 'drop':
    db.drop()
elif sys.argv[1] == 'validate-events':
    sys.path.insert(0, str(root))
    import uuid
    from brandme_core.events import EventEnvelope
    from brandme_core.domains import events as domain_events
    with db.snapshot() as snapshot:
        for row in snapshot.execute_sql("SELECT event_id, event_type, schema_version, aggregate_type, aggregate_id, aggregate_version, occurred_at, environment, actor_ref, correlation_id, causation_id, privacy_class, payload FROM OutboxEvents"):
            EventEnvelope(event_id=row[0], event_type=row[1], schema_version=row[2], aggregate_type=row[3], aggregate_id=row[4],
                aggregate_version=row[5], occurred_at=row[6], environment=row[7], actor_ref=row[8], correlation_id=row[9],
                causation_id=row[10], privacy_class=row[11], payload=row[12]).validate()
            if row[1] == 'rights.entitlement.projected':
                payload = row[12]
                assert row[4] == str(uuid.uuid5(uuid.NAMESPACE_URL,
                    f"brandme:rights:{payload['network']}:{payload['contract_address']}:{payload['entitlement_id']}"))
else:
    db.create().result(60)
    runner.migrate_up(db, log=lambda *_: None)
