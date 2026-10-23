"""Run with ``python -m brandme_core.events.worker`` using the core image.

No wallet, chain submission, topic creation, or application side effects. This
process only publishes registered committed events to pre-provisioned topics.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import signal
import threading
from dataclasses import asdict, dataclass
from typing import Mapping

from brandme_core.config import check_legacy_flags, get_mode
from brandme_core.domains import events as domain_events  # noqa: F401 registers supported contracts
from .envelope import PRIVACY_CLASSES, registry, _envelope_validator
from .outbox import OutboxDispatcher
from .pubsub import PubSubPublisher, emulator_endpoint


@dataclass(frozen=True)
class WorkerConfig:
    environment: str
    project: str
    instance: str
    database: str
    topics: dict[str, str]
    emulator_host: str
    event_types: tuple[str, ...]
    poll_seconds: float = 2

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "WorkerConfig":
        mode = get_mode(env)
        if env.get("ENVIRONMENT") != mode.value or check_legacy_flags(mode, env):
            raise ValueError("worker mode and environment must agree without stub flags")
        if mode.is_strict and (env.get("SPANNER_EMULATOR_HOST") or env.get("PUBSUB_EMULATOR_HOST")):
            raise ValueError("emulators forbidden in sandbox and production")
        if not mode.is_strict and not (env.get("SPANNER_EMULATOR_HOST") and env.get("PUBSUB_EMULATOR_HOST")):
            raise ValueError("demo/development requires both emulators")
        emulator = env.get("PUBSUB_EMULATOR_HOST", "")
        if emulator:
            emulator_endpoint(emulator, mode.value)
        required = ["SPANNER_PROJECT_ID", "SPANNER_INSTANCE_ID", "SPANNER_DATABASE_ID"]
        if any(not env.get(k, "").strip() for k in required):
            raise ValueError("explicit Spanner configuration required")
        topics = {c: env.get("OUTBOX_PUBSUB_TOPIC_" + c.upper(), "") for c in PRIVACY_CLASSES}
        known = {t.event_type for t in registry.types()}
        selected = set(env.get("OUTBOX_EVENT_TYPES", ",".join(sorted(known))).split(","))
        if not selected or not selected <= known:
            raise ValueError("event allowlist contains an unsupported contract")
        return cls(mode.value, *(env[k] for k in required), topics, emulator, tuple(sorted(selected)))


def verify_schema(database) -> None:
    with database.snapshot(multi_use=True) as snap:
        rows = list(snap.execute_sql("SELECT version, state FROM SchemaMigrations"))
        if not any(v == 13 and state == "applied" for v, state in rows) or any(state != "applied" for _, state in rows):
            raise RuntimeError("outbox_schema_unavailable")
        # Also verify the actual index and fields, not only a ledger entry.
        list(snap.execute_sql("""SELECT event_id, lease_owner, lease_expires_at, attempts
            FROM OutboxEvents@{FORCE_INDEX=OutboxByEnvironmentStatus} LIMIT 1"""))


def run(config: WorkerConfig, *, once: bool = False, check: bool = False) -> int:
    from google.cloud import spanner
    from google.cloud.spanner_v1.pool import BurstyPool
    stop = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGTERM, signal.SIGINT)}
    publisher = None
    pool = BurstyPool()
    try:
        _envelope_validator()  # missing packaged schema is a startup failure, not a poison event
        client = spanner.Client(project=config.project)
        db = client.instance(config.instance).database(config.database, pool=pool)
        verify_schema(db)
        publisher = PubSubPublisher(config.topics, config.environment, emulator_host=config.emulator_host)
        publisher.check_topics()
        print(json.dumps({"status": "ready", "environment": config.environment,
                          "transport": "pubsub_emulator" if config.emulator_host else "pubsub",
                          "event_contracts": len(config.event_types)}), flush=True)
        if check:
            return 0
        dispatcher = OutboxDispatcher(db, publisher, environment=config.environment, event_types=config.event_types)
        failures = 0
        while not stop.is_set():
            delay = config.poll_seconds
            try:
                result = dispatcher.run_once(should_stop=stop.is_set)
                failures = 0
                if once or any(asdict(result).values()):
                    print(json.dumps({"status": "dispatch", **asdict(result)}), flush=True)
            except Exception:
                # Database/provider errors may contain credentials or private values.
                print('{"status":"dispatch_unavailable"}', flush=True)
                if once:
                    return 1
                failures += 1
                delay = min(60, config.poll_seconds * 2 ** min(failures, 6)) * random.uniform(.75, 1)
            if once:
                return 0 if result.failed == result.dead == result.stale == 0 else 1
            stop.wait(delay)
        return 0
    finally:
        if publisher is not None:
            publisher.close()
        pool.clear()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument("--once", action="store_true", help="process one bounded batch and exit")
    flags.add_argument("--check", action="store_true", help="verify schema, configuration and provisioned topics")
    args = parser.parse_args(argv)
    try:
        return run(WorkerConfig.from_env(os.environ), once=args.once, check=args.check)
    except Exception:
        print('{"status":"startup_refused"}', flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
