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
else:
    db.create().result(60)
    runner.migrate_up(db, log=lambda *_: None)
