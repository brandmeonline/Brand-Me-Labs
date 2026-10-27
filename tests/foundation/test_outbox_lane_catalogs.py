"""Every lane catalog reaches the foundation outbox worker (brandme_core/events/catalogs.py).

Unit part: the worker's default allowlist covers each catalog, no contract
declares a forbidden payload key, every contract has a valid minimal event, no
domain module registers a contract outside the catalogs, and a catalog that
fails to load refuses startup with a fixed code. Emulator part: one event per
registered contract, written with write_events, is published by
``python -m brandme_core.events.worker --once`` to the real Pub/Sub emulator
and pulled exactly once from the topic of its privacy class.
"""
import base64
from collections import Counter
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
import requests

from brandme_core.events import EventEnvelope, FORBIDDEN_PAYLOAD_KEYS, registry, write_events
from brandme_core.events.catalogs import CATALOGS
from brandme_core.events.worker import WorkerConfig
from .conftest import requires_spanner
from .test_outbox_delivery import config_env, outbox_db, provision, pubsub_server, read, topics  # noqa: F401

REPO = Path(__file__).resolve().parents[2]
# Contracts each lane adds to the worker, pinned so a new lane contract is a
# reviewed change here too (it starts flowing on the foundation's topics).
EXPECTED_CONTRACTS = {"foundation": 11, "consumer-domains": 36, "commerce-agents": 7}
UUID_TEXT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# The JSON Schema subset the catalogs use. example() refuses anything else, so a
# new construct fails loudly here instead of producing an invalid probe event.
KEYWORDS = frozenset({"type", "properties", "required", "additionalProperties", "const", "enum", "anyOf", "format",
                      "pattern", "minLength", "maxLength", "minimum", "maximum", "items", "minItems", "maxItems",
                      "uniqueItems"})
FORMATS = {"uuid": lambda: str(uuid.uuid4()), "date-time": lambda: "2026-10-25T00:00:00Z"}
PATTERNS = {
    "^[0-9a-f]{64}$": "ab" * 32,
    "^(0|[1-9][0-9]*)$": "7",
    "^(0|[1-9][0-9]{0,17})$": "7",
    "^sha256:[0-9a-f]{64}$": "sha256:" + "cd" * 32,
}


def example(schema, where):
    """Minimal valid instance of a closed contract schema: required fields only."""
    unknown = set(schema) - KEYWORDS
    if unknown:
        pytest.fail(f"{where}: no example rule for {sorted(unknown)}; extend example()")
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if "anyOf" in schema:
        return example(schema["anyOf"][0], where)
    kind = schema.get("type")
    if kind == "object":
        if schema.get("additionalProperties") is not False:
            pytest.fail(f"{where}: open object schema")
        return {k: example(schema["properties"][k], f"{where}.{k}") for k in schema.get("required", [])}
    if kind == "array":
        if schema.get("uniqueItems") and schema.get("minItems", 0) > 1:
            pytest.fail(f"{where}: no example rule for several unique items")
        return [example(schema["items"], f"{where}[]") for _ in range(schema.get("minItems", 0))]
    if kind == "integer":
        return schema.get("minimum", 0)
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    if kind == "string":
        if "format" in schema:
            if schema["format"] not in FORMATS:
                pytest.fail(f"{where}: no example for format {schema['format']}; add one to FORMATS")
            return FORMATS[schema["format"]]()
        if "pattern" in schema:
            if schema["pattern"] not in PATTERNS:
                pytest.fail(f"{where}: no example for pattern {schema['pattern']}; add one to PATTERNS")
            return PATTERNS[schema["pattern"]]
        return "x" * max(1, schema.get("minLength", 1))
    pytest.fail(f"{where}: no example rule for type {kind!r}")


def property_names(schema):
    # properties/items/anyOf are the only subschema keywords example() accepts.
    for name, sub in schema.get("properties", {}).items():
        yield name
        yield from property_names(sub)
    if "items" in schema:
        yield from property_names(schema["items"])
    for sub in schema.get("anyOf", []):
        yield from property_names(sub)


def envelope(contract):
    return EventEnvelope(event_type=contract.event_type, schema_version=contract.schema_version,
                         aggregate_type="catalog_probe", aggregate_id=str(uuid.uuid4()), aggregate_version=1,
                         environment="development", actor_ref="service:catalog-probe",
                         correlation_id=str(uuid.uuid4()), privacy_class=contract.privacy_class,
                         payload=example(contract.payload_schema, contract.event_type))


def python(code, *args, env=None):
    return subprocess.run([sys.executable, "-W", "ignore", "-c", code, *args], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=120)


# Fresh interpreter: load the catalogs one at a time, in order, with the real
# loader, and attribute each contract to the first catalog that registers it.
# Then build the default allowlist exactly as the worker process does.
CATALOG_PROBE = """
import json, sys
from brandme_core.events import catalogs, registry
from brandme_core.events.worker import WorkerConfig
keys = lambda: {(t.event_type, t.schema_version) for t in registry.types()}
everything, lanes = catalogs.CATALOGS, {}
for catalog in everything:
    before = keys()
    catalogs.CATALOGS = (catalog,)
    status = catalogs.load_catalogs()[catalog.lane]
    lanes[catalog.lane] = {"status": status, "contracts": sorted(keys() - before)}
catalogs.CATALOGS = everything
config = WorkerConfig.from_env(json.loads(sys.argv[1]))
print(json.dumps({"lanes": lanes, "event_types": config.event_types, "catalogs": dict(config.catalogs)}))
"""


@pytest.fixture(scope="module")
def probe():
    out = python(CATALOG_PROBE, json.dumps(config_env()))
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    result = json.loads(out.stdout.splitlines()[-1])
    result["lanes"] = {lane: {"status": v["status"], "contracts": [tuple(c) for c in v["contracts"]]}
                       for lane, v in result["lanes"].items()}
    return result


def test_worker_allowlist_covers_every_catalog(probe):
    config = WorkerConfig.from_env(config_env())
    assert dict(config.catalogs) == probe["catalogs"] == {lane: v["status"] for lane, v in probe["lanes"].items()}
    assert set(config.event_types) == set(probe["event_types"])
    for catalog in CATALOGS:
        lane = probe["lanes"][catalog.lane]
        if lane["status"] == "absent":
            # Tolerated only while the lane's PR is unmerged and its module truly does not exist.
            assert catalog.until_merged and importlib.util.find_spec(catalog.module) is None, catalog.lane
            assert not lane["contracts"]
            continue
        assert lane["status"] == "loaded"
        assert len(lane["contracts"]) == EXPECTED_CONTRACTS[catalog.lane], (catalog.lane, lane["contracts"])
        missing = {t for t, _ in lane["contracts"]} - set(probe["event_types"])
        assert not missing, (catalog.lane, sorted(missing))
    # Every lane on main is loaded, commerce-agents included (PR #51 merged).
    statuses = {lane: probe["lanes"][lane]["status"] for lane in EXPECTED_CONTRACTS}
    assert statuses == dict.fromkeys(EXPECTED_CONTRACTS, "loaded"), statuses
    # Nothing in the allowlist comes from outside the catalogs.
    attributed = {t for lane in probe["lanes"].values() for t, _ in lane["contracts"]}
    assert attributed == set(probe["event_types"])


def test_no_contract_declares_a_forbidden_payload_key(probe):
    WorkerConfig.from_env(config_env())
    bad = {}
    for lane in probe["lanes"].values():
        for event_type, version in lane["contracts"]:
            names = {n for n in property_names(registry.get(event_type, version).payload_schema)
                     if n.lower() in FORBIDDEN_PAYLOAD_KEYS}
            if names:
                bad[f"{event_type}@{version}"] = sorted(names)
    assert not bad


def test_every_contract_has_a_valid_minimal_event(probe):
    WorkerConfig.from_env(config_env())
    for lane in probe["lanes"].values():
        for event_type, version in lane["contracts"]:
            envelope(registry.get(event_type, version)).validate()


# Fresh interpreter: after the catalogs, importing every module under
# brandme_core.domains must register nothing more. A contract registered
# anywhere else would never be published.
WALK = """
import importlib, json, pkgutil
import brandme_core.domains
from brandme_core.events import registry
from brandme_core.events.catalogs import load_catalogs
load_catalogs()
keys = lambda: {f"{t.event_type}@{t.schema_version}" for t in registry.types()}
before, failures, modules = keys(), [], 0
for info in pkgutil.walk_packages(brandme_core.domains.__path__, "brandme_core.domains.", onerror=failures.append):
    try:
        importlib.import_module(info.name)
        modules += 1
    except Exception as exc:
        failures.append(f"{info.name}: {type(exc).__name__}")
print(json.dumps({"extra": sorted(keys() - before), "failures": failures, "modules": modules}))
"""


def test_no_domain_module_registers_a_contract_outside_the_catalogs():
    out = python(WALK)
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    walk = json.loads(out.stdout.splitlines()[-1])
    assert walk["modules"] > 50 and not walk["failures"], walk
    assert walk["extra"] == [], "register these contracts through a catalog in brandme_core/events/catalogs.py"


# Fresh interpreter: replace CATALOGS with one probe entry, then run the real
# worker entrypoint. Startup must refuse before any Spanner or Pub/Sub call.
REFUSAL = """
import sys
from brandme_core.events import catalogs, worker
catalogs.CATALOGS = catalogs.CATALOGS + (catalogs.Catalog("probe-lane", sys.argv[1], loader=sys.argv[2] or None,
                                                          until_merged=sys.argv[3] or None),)
raise SystemExit(worker.main(["--check"]))
"""


@pytest.mark.parametrize("module,loader,until_merged", [
    ("brandme_core.domains.no_such_catalog", "", ""),  # a required catalog is missing
    ("q8_probe_broken_catalog", "", "PR #0"),  # present but broken: never "absent"
    ("q8_probe_dependency_catalog", "", "PR #0"),  # present, a dependency is missing (ModuleNotFoundError)
    ("q8_probe_loader_catalog", "load", "PR #0"),  # its loader fails
])
def test_catalog_failure_refuses_startup_with_a_fixed_code(tmp_path, module, loader, until_merged):
    (tmp_path / "q8_probe_broken_catalog.py").write_text('raise ImportError("PROBE_PRIVATE_DETAIL")\n')
    (tmp_path / "q8_probe_dependency_catalog.py").write_text("import q8_no_such_dependency_PROBE_PRIVATE_DETAIL\n")
    (tmp_path / "q8_probe_loader_catalog.py").write_text('def load():\n    raise RuntimeError("PROBE_PRIVATE_DETAIL")\n')
    env = {**os.environ, **config_env(), "PYTHONPATH": os.pathsep.join([str(tmp_path), str(REPO)])}
    out = python(REFUSAL, module, loader, until_merged, env=env)
    assert out.returncode == 2, out.stdout + out.stderr
    assert out.stdout == '{"status":"startup_refused","reason":"event_catalog_unavailable","lane":"probe-lane"}\n'
    assert "PROBE_PRIVATE_DETAIL" not in out.stdout + out.stderr and "Traceback" not in out.stderr


def test_absent_catalog_is_reported_only_while_its_module_does_not_exist(monkeypatch):
    from brandme_core.events import catalogs

    monkeypatch.setattr(catalogs, "CATALOGS", catalogs.CATALOGS + (
        catalogs.Catalog("probe-lane", "brandme_core.domains.no_such_catalog", until_merged="PR #0"),))
    assert catalogs.load_catalogs()["probe-lane"] == "absent"


def pull_all(host, sub, expected, rounds=100):
    got = []
    while rounds and len(got) < expected:
        rounds -= 1
        r = requests.post(f"http://{host}/v1/{sub}:pull", json={"maxMessages": 100, "returnImmediately": True}, timeout=5)
        r.raise_for_status()
        msgs = r.json().get("receivedMessages", [])
        if msgs:
            requests.post(f"http://{host}/v1/{sub}:acknowledge", json={"ackIds": [m["ackId"] for m in msgs]},
                          timeout=5).raise_for_status()
            got.extend(m["message"] for m in msgs)
        else:
            time.sleep(.05)
    return got


@requires_spanner
def test_one_event_per_contract_round_trips_through_the_foundation_worker(outbox_db, pubsub_server, probe):  # noqa: F811
    WorkerConfig.from_env(config_env())
    lane_of = {key: lane for lane, v in probe["lanes"].items() for key in v["contracts"]}
    events = [envelope(registry.get(*key)) for key in sorted(lane_of)]
    outbox_db.run_in_transaction(lambda tx: write_events(tx, events))
    mapping = topics("-" + uuid.uuid4().hex[:8]); subs = provision(pubsub_server, mapping)
    env = {**os.environ, **config_env(), "SPANNER_DATABASE_ID": outbox_db.database_id,
           "SPANNER_EMULATOR_HOST": os.environ["SPANNER_EMULATOR_HOST"], "PUBSUB_EMULATOR_HOST": pubsub_server,
           **{"OUTBOX_PUBSUB_TOPIC_" + c.upper(): t for c, t in mapping.items()}}
    logs, delivered = "", 0
    for _ in range(5):  # --once claims at most 50 events per run
        run = subprocess.run([sys.executable, "-m", "brandme_core.events.worker", "--once"], env=env, cwd=REPO,
                             capture_output=True, text=True, timeout=120)
        logs += run.stdout + run.stderr
        assert run.returncode == 0, logs[-3000:]
        lines = [json.loads(line) for line in run.stdout.splitlines()]
        assert lines[0] == {"status": "ready", "environment": "development", "transport": "pubsub_emulator",
                            "event_contracts": len(events), "catalogs": probe["catalogs"]}
        delivered += sum(line.get("delivered", 0) for line in lines if line["status"] == "dispatch")
        if all(read(outbox_db, e)["status"] == "delivered" for e in events):
            break
    assert all(read(outbox_db, e)["status"] == "delivered" for e in events), logs[-3000:]
    assert delivered == len(events)

    by_id, received = {e.event_id: e for e in events}, []
    for privacy, sub in subs.items():
        want = {e.event_id for e in events if e.privacy_class == privacy}
        got = pull_all(pubsub_server, sub, len(want))
        got += pull_all(pubsub_server, sub, 1, rounds=10)  # and then nothing more arrives
        assert sorted(m["attributes"]["event_id"] for m in got) == sorted(want), privacy  # once, on its own topic
        for m in got:
            ev = by_id[m["attributes"]["event_id"]]
            assert json.loads(base64.b64decode(m["data"])) == ev.to_wire()
            assert m["attributes"] == {"event_id": ev.event_id, "event_type": ev.event_type,
                                       "schema_version": ev.schema_version, "environment": "development",
                                       "privacy_class": privacy}
            received.append(ev)

    per_lane = Counter(lane_of[(e.event_type, e.schema_version)] for e in received)
    assert probe["catalogs"] == dict.fromkeys(EXPECTED_CONTRACTS, "loaded")
    assert dict(per_lane) == EXPECTED_CONTRACTS  # foundation 11, consumer-domains 36, commerce-agents 7
    assert len(received) == len(events) == 54
    ids = {i for e in events for i in (e.event_id, e.aggregate_id, e.correlation_id)}
    ids |= {i for e in events for i in UUID_TEXT.findall(json.dumps(e.payload))}
    assert not [i for i in ids if i in logs]
