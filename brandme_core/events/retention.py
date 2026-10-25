"""Outbox retention and erasure of a deleted subject's event and replay records.

Run with ``python -m brandme_core.events.retention --once`` using the core
image (hourly CronJob ``events-retention`` in brandme-infra/helm/brandme).
Spanner only: no Pub/Sub, wallet, chain submission or application side effects.

Founder ruling Q19 (the "Q9 purge"):

* ``purge_delivered`` deletes delivered ``OutboxEvents`` rows 7 days after
  delivery, and ``subject_erased`` tombstones 7 days after the erasure.
  Pending, leased and every other dead row are never purged by age.
* ``erase_subject_events`` withdraws a subject's undelivered events in place
  (status ``dead``, ``last_error = 'subject_erased'``, empty payload, neutral
  references) and deletes their delivered events. A withdrawn row is never
  claimed again, and a lease in flight can no longer finish (``stale``).
* ``erase_subject_requests`` deletes the subject's ``IdempotencyRecords`` and
  unlinks other principals' replay bodies that name them.
* ``sweep_erased_subjects`` re-applies both for subjects whose platform
  categories were deleted in the last 30 days: the backstop for writers that
  are not freeze-guarded and for events written after the deletion step.

Copies already accepted by Pub/Sub cannot be recalled; they expire with the
topic and subscription retention (at least 24 hours, events/README.md).
The privacy wiring (categories, receipts, restore) is ``events/erasure.py``.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import signal
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping, Sequence

from brandme_core.config import check_legacy_flags, get_mode
from .outbox import SHARDS

DELIVERED_RETENTION = timedelta(days=7)
SWEEP_WINDOW = timedelta(days=30)
SUBJECT_BATCH = 100
UNLINK_BATCH = 25
#: The two foundation categories whose tombstones the sweep re-applies.
CATEGORIES = ("platform.event_outbox", "platform.request_replay")
#: Replaces a subject in another principal's replay body (same nil member as the lanes use).
NIL_SUBJECT = "00000000-0000-0000-0000-000000000000"
ENVIRONMENTS = ("demo", "development", "sandbox", "production")

# Over @s ARRAY<STRING> of subject keys. Payloads are matched on an exact JSON
# string token, never a substring, so a short ref ('m9') cannot match 'm99'.
SUBJECT_MATCH = (
    "(aggregate_id IN UNNEST(@s) OR EXISTS(SELECT 1 FROM UNNEST(@s) AS x WHERE actor_ref = CONCAT('member:', x)"
    " OR STARTS_WITH(actor_ref, CONCAT('member:', x, '/'))"
    " OR STRPOS(TO_JSON_STRING(payload), CONCAT('\"', x, '\"')) > 0))"
)
# 'member:<x>' and its delegations ('member:<x>/delegation:<id>', base.py:84-85).
PRINCIPAL_MATCH = (
    "EXISTS(SELECT 1 FROM UNNEST(@s) AS x WHERE principal_ref = CONCAT('member:', x)"
    " OR STARTS_WITH(principal_ref, CONCAT('member:', x, '/')))"
)

# next_attempt_at records when the row was withdrawn: dead rows are never
# claimed (outbox.py:123-124), and purge_delivered ages tombstones by it.
_WITHDRAW = f"""UPDATE OutboxEvents SET status = 'dead', last_error = 'subject_erased', payload = JSON '{{}}',
    actor_ref = 'service:privacy', aggregate_id = event_id, correlation_id = event_id, causation_id = NULL,
    lease_owner = NULL, lease_expires_at = NULL, next_attempt_at = CURRENT_TIMESTAMP()
    WHERE status != 'delivered' AND {SUBJECT_MATCH}"""
_DELETE_DELIVERED = f"DELETE FROM OutboxEvents WHERE status = 'delivered' AND {SUBJECT_MATCH}"
_DELETE_REQUESTS = f"DELETE FROM IdempotencyRecords WHERE {PRINCIPAL_MATCH}"

_REF = re.compile(r"[A-Za-z0-9._:@/+-]{1,128}")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def subject_keys(subject_ref: str) -> tuple[str, ...]:
    """Every value that names ``subject_ref`` in event and replay records.

    A member UUID is also matched in its ``member:<uuid>`` actor form, and
    ``member:<uuid>`` as the bare UUID. Refs are limited to characters that
    JSON never escapes, so the exact-token match cannot miss an encoded form.
    """
    if not isinstance(subject_ref, str) or not _REF.fullmatch(subject_ref):
        raise ValueError("invalid subject reference")
    bare = subject_ref.removeprefix("member:")
    keys = {subject_ref}
    if _UUID.fullmatch(bare):
        keys.update((bare, f"member:{bare}"))
    return tuple(sorted(keys))


def _batches(subject_refs: Iterable[str]) -> list[list[str]]:
    if isinstance(subject_refs, str):
        raise TypeError("pass a collection of subject references, not one string")  # 'm9' would erase 'm' and '9'
    keys = sorted({k for ref in subject_refs for k in subject_keys(ref)})
    return [keys[i:i + SUBJECT_BATCH] for i in range(0, len(keys), SUBJECT_BATCH)]


def _array(batch: Sequence[str]) -> tuple[dict, dict]:
    from google.cloud.spanner_v1 import param_types

    return {"s": list(batch)}, {"s": param_types.Array(param_types.STRING)}


def erase_subject_events(database, subject_refs: Iterable[str]) -> tuple[int, int]:
    """Withdraw undelivered and delete delivered outbox rows naming the subjects.

    Partitioned DML, idempotent, outside any transaction. Returns
    ``(withdrawn, deleted)``; Spanner reports a lower bound for partitioned DML.
    """
    withdrawn = deleted = 0
    for batch in _batches(subject_refs):
        params, types = _array(batch)
        # Withdraw first: a withdrawn row can never become delivered (_finish
        # requires 'leased'), so the delete then sees every delivered row.
        withdrawn += database.execute_partitioned_dml(_WITHDRAW, params=params, param_types=types)
        deleted += database.execute_partitioned_dml(_DELETE_DELIVERED, params=params, param_types=types)
    return withdrawn, deleted


def erase_subject_requests(database, subject_refs: Iterable[str]) -> tuple[int, int]:
    """Delete the subjects' replay records; unlink them from other principals' bodies.

    Another member's record stays (deleting it would let their retry run the
    command twice); each exact JSON token naming a subject becomes the nil
    member. Returns ``(deleted, unlinked)``; ``unlinked`` counts row updates,
    so a body naming subjects handled by several statements counts more than once.
    """
    from google.cloud.spanner_v1 import param_types

    deleted = unlinked = 0
    for batch in _batches(subject_refs):
        params, types = _array(batch)
        deleted += database.execute_partitioned_dml(_DELETE_REQUESTS, params=params, param_types=types)
        # One nested REPLACE per key; Spanner caps expression nesting (the emulator at 75).
        for i in range(0, len(batch), UNLINK_BATCH):
            tokens = {f"t{j}": json.dumps(k) for j, k in enumerate(batch[i:i + UNLINK_BATCH])}  # _REF needs no escaping
            body = "TO_JSON_STRING(response_body)"
            for name in tokens:
                body = f"REPLACE({body}, @{name}, @nil)"
            unlinked += database.execute_partitioned_dml(
                f"UPDATE IdempotencyRecords SET response_body = PARSE_JSON({body}) WHERE EXISTS("
                "SELECT 1 FROM UNNEST(@tokens) AS t WHERE STRPOS(TO_JSON_STRING(response_body), t) > 0)",
                params={**tokens, "tokens": list(tokens.values()), "nil": json.dumps(NIL_SUBJECT)},
                param_types={**dict.fromkeys(tokens, param_types.STRING), "nil": param_types.STRING,
                             "tokens": param_types.Array(param_types.STRING)})
    return deleted, unlinked


def _aware(now: datetime) -> datetime:
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("timezone-aware time required")
    return now


def purge_delivered(database, environment: str, now: datetime, older_than: timedelta = DELIVERED_RETENTION,
                    batch_size: int = 500) -> int:
    """Delete one environment's delivered rows and ``subject_erased`` tombstones older than the window.

    Per shard through OutboxByEnvironmentStatus (V013). A delivered row always
    has ``next_attempt_at <= delivered_at`` (leasing and delivery never move
    it), so ``next_attempt_at < cutoff`` is a safe index prefilter. Each
    batch commits about ``batch_size`` x 4 mutations (row plus three indexes).
    """
    from google.cloud.spanner_v1 import param_types

    if environment not in ENVIRONMENTS:
        raise ValueError("explicit event environment required")
    if not (timedelta(days=1) <= older_than and 1 <= batch_size <= 1000):
        raise ValueError("invalid retention bounds")
    cutoff = _aware(now) - older_than
    purged = 0
    for shard in range(SHARDS):
        for status, residual in (("delivered", "delivered_at < @cutoff"), ("dead", "last_error = 'subject_erased'")):
            params = {"e": environment, "sh": shard, "st": status, "cutoff": cutoff, "n": batch_size}
            types = {"e": param_types.STRING, "sh": param_types.INT64, "st": param_types.STRING,
                     "cutoff": param_types.TIMESTAMP, "n": param_types.INT64}
            where = f"shard = @sh AND status = @st AND next_attempt_at < @cutoff AND {residual}"
            while True:
                with database.snapshot() as snap:
                    ids = [r[0] for r in snap.execute_sql(
                        "SELECT event_id FROM OutboxEvents@{FORCE_INDEX=OutboxByEnvironmentStatus} "
                        f"WHERE environment = @e AND {where} LIMIT @n", params=params, param_types=types)]
                if not ids:
                    break
                keyed = {**params, "ids": ids}
                keyed_types = {**types, "ids": param_types.Array(param_types.STRING)}
                count = database.run_in_transaction(lambda tx: tx.execute_update(
                    f"DELETE FROM OutboxEvents WHERE event_id IN UNNEST(@ids) AND environment = @e AND {where}",
                    params=keyed, param_types=keyed_types))
                purged += count
                if count == 0 or len(ids) < batch_size:
                    break
    return purged


@dataclass(frozen=True)
class SweepResult:
    subjects: int = 0
    withdrawn: int = 0
    deleted: int = 0
    requests_deleted: int = 0
    requests_unlinked: int = 0


def sweep_erased_subjects(database, now: datetime, window: timedelta = SWEEP_WINDOW) -> SweepResult:
    """Re-erase subjects whose platform categories were deleted within ``window``.

    Reads the privacy lane's DeletionTombstones (V009, read-only here) for the
    two foundation categories, whole-category tombstones only.
    """
    from google.cloud.spanner_v1 import param_types

    since = _aware(now) - window
    with database.snapshot() as snap:
        subjects = sorted({r[0] for r in snap.execute_sql(
            "SELECT DISTINCT subject_ref FROM DeletionTombstones@{FORCE_INDEX=DeletionTombstonesByCreated} "
            "WHERE created_at >= @since AND category IN UNNEST(@c) "
            "AND (record_keys IS NULL OR ARRAY_LENGTH(record_keys) = 0)",
            params={"since": since, "c": list(CATEGORIES)},
            param_types={"since": param_types.TIMESTAMP, "c": param_types.Array(param_types.STRING)})})
    if not subjects:
        return SweepResult()
    withdrawn, deleted = erase_subject_events(database, subjects)
    requests_deleted, requests_unlinked = erase_subject_requests(database, subjects)
    return SweepResult(len(subjects), withdrawn, deleted, requests_deleted, requests_unlinked)


# --- process -----------------------------------------------------------------

@dataclass(frozen=True)
class RetentionConfig:
    environment: str
    project: str
    instance: str
    database: str
    interval_seconds: float = 3600

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "RetentionConfig":
        mode = get_mode(env)
        if env.get("ENVIRONMENT") != mode.value or check_legacy_flags(mode, env):
            raise ValueError("retention mode and environment must agree without stub flags")
        if mode.is_strict and env.get("SPANNER_EMULATOR_HOST"):
            raise ValueError("emulator forbidden in sandbox and production")
        if not mode.is_strict and not env.get("SPANNER_EMULATOR_HOST"):
            raise ValueError("demo/development requires the Spanner emulator")
        required = ["SPANNER_PROJECT_ID", "SPANNER_INSTANCE_ID", "SPANNER_DATABASE_ID"]
        if any(not env.get(k, "").strip() for k in required):
            raise ValueError("explicit Spanner configuration required")
        return cls(mode.value, *(env[k] for k in required))


def verify_schema(database) -> None:
    with database.snapshot(multi_use=True) as snap:
        rows = list(snap.execute_sql("SELECT version, state FROM SchemaMigrations"))
        applied = {v for v, state in rows if state == "applied"}
        if not {9, 13} <= applied or any(state != "applied" for _, state in rows):
            raise RuntimeError("retention_schema_unavailable")
        # The indexes and columns this job reads, not only ledger entries.
        list(snap.execute_sql("""SELECT event_id, delivered_at, last_error
            FROM OutboxEvents@{FORCE_INDEX=OutboxByEnvironmentStatus} LIMIT 1"""))
        list(snap.execute_sql("""SELECT subject_ref, record_keys
            FROM DeletionTombstones@{FORCE_INDEX=DeletionTombstonesByCreated} LIMIT 1"""))
        list(snap.execute_sql("SELECT principal_ref, response_body FROM IdempotencyRecords LIMIT 1"))


def tick(database, environment: str, now: datetime) -> dict:
    """One bounded pass: age purge, then the erased-subject sweep. Counts only."""
    purged = purge_delivered(database, environment, now)
    return {"purged": purged, **asdict(sweep_erased_subjects(database, now))}


def run(config: RetentionConfig, *, once: bool = False, check: bool = False) -> int:
    from google.cloud import spanner
    from google.cloud.spanner_v1.pool import BurstyPool
    stop = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGTERM, signal.SIGINT)}
    pool = BurstyPool()
    try:
        client = spanner.Client(project=config.project)
        db = client.instance(config.instance).database(config.database, pool=pool)
        verify_schema(db)
        print(json.dumps({"status": "ready", "environment": config.environment,
                          "delivered_retention_days": DELIVERED_RETENTION.days,
                          "sweep_window_days": SWEEP_WINDOW.days}), flush=True)
        if check:
            return 0
        failures = 0
        while not stop.is_set():
            delay = config.interval_seconds
            try:
                # Logs carry counts only: never event, member or subject ids.
                print(json.dumps({"status": "retention", **tick(db, config.environment, datetime.now(timezone.utc))}),
                      flush=True)
                failures = 0
            except Exception:
                # Database errors may contain private values or credentials.
                print('{"status":"retention_unavailable"}', flush=True)
                if once:
                    return 1
                failures += 1
                delay = min(config.interval_seconds, 60 * 2 ** min(failures, 6)) * random.uniform(.75, 1)
            if once:
                return 0
            stop.wait(delay)
        return 0
    finally:
        pool.clear()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument("--once", action="store_true", help="run one purge and sweep pass and exit")
    flags.add_argument("--check", action="store_true", help="verify schema and configuration")
    args = parser.parse_args(argv)
    # Shared trust-path inventory, enforced in-process as well as by the preflight CLI.
    from brandme_core.boot import guard

    guard("events_retention")
    try:
        return run(RetentionConfig.from_env(os.environ), once=args.once, check=args.check)
    except Exception:
        print('{"status":"startup_refused"}', flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
