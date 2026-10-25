"""Outbox retention and erasure of a deleted subject's event and replay records.

Run with ``python -m brandme_core.events.retention --once`` using the core
image (hourly CronJob ``events-retention`` in brandme-infra/helm/brandme).
Spanner only: no Pub/Sub, wallet, chain submission or application side effects.

Founder ruling Q19 (the "Q9 purge"):

* ``purge_delivered`` deletes delivered ``OutboxEvents`` rows 7 days after
  delivery, and ``subject_erased`` tombstones 7 days after the erasure.
  Pending, leased and every other dead row are never purged by age.
* ``erase_subject_events`` withdraws the subject's own undelivered events in
  place (status ``dead``, ``last_error = 'subject_erased'``, empty payload,
  neutral references) and deletes their own delivered events. An event is the
  subject's own when its actor (``member:<id>`` or a delegation of it) or its
  aggregate is the subject. A withdrawn row is never claimed again, and a
  lease in flight can no longer finish (``stale``). Every other event that
  names the subject keeps its row and status: each JSON string value naming
  them becomes the nil member, so other members' side effects survive.
* ``erase_subject_requests`` deletes the subject's ``IdempotencyRecords`` and
  unlinks other principals' replay bodies the same way.
* ``sweep_erased_subjects`` re-applies both for subjects whose platform
  categories were deleted by an account deletion in the last 30 days: the
  backstop for writers that are not freeze-guarded and for events written
  after the deletion step.

Copies already accepted by Pub/Sub cannot be recalled; they expire with the
topic and subscription retention (at least 24 hours, events/README.md). A
delivery already in flight when the erasure runs still publishes the payload
it claimed. The privacy wiring (categories, receipts, restore) is
``events/erasure.py``.
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
UNLINK_BATCH = 100  # compare-and-set updates per transaction
#: The two foundation categories whose tombstones the sweep re-applies.
CATEGORIES = ("platform.event_outbox", "platform.request_replay")
#: Replaces a subject in another principal's records (the nil member the lanes use, kernel.py:60).
NIL_SUBJECT = "00000000-0000-0000-0000-000000000000"
ENVIRONMENTS = ("demo", "development", "sandbox", "production")

# Over @s ARRAY<STRING> of subject keys: the subject's own events, by aggregate
# or by actor 'member:<x>' and its delegations ('member:<x>/delegation:<id>',
# base.py:84-85). Exact matches only, so a short ref ('m9') never matches 'm99'.
OWN_MATCH = (
    "(aggregate_id IN UNNEST(@s) OR EXISTS(SELECT 1 FROM UNNEST(@s) AS x WHERE actor_ref = CONCAT('member:', x)"
    " OR STARTS_WITH(actor_ref, CONCAT('member:', x, '/'))))"
)
PRINCIPAL_MATCH = (
    "EXISTS(SELECT 1 FROM UNNEST(@s) AS x WHERE principal_ref = CONCAT('member:', x)"
    " OR STARTS_WITH(principal_ref, CONCAT('member:', x, '/')))"
)

# next_attempt_at records when the row was withdrawn: dead rows are never
# claimed (outbox.py:123-124), and purge_delivered ages tombstones by it.
_WITHDRAW = f"""UPDATE OutboxEvents SET status = 'dead', last_error = 'subject_erased', payload = JSON '{{}}',
    actor_ref = 'service:privacy', aggregate_id = event_id, correlation_id = event_id, causation_id = NULL,
    lease_owner = NULL, lease_expires_at = NULL, next_attempt_at = CURRENT_TIMESTAMP()
    WHERE status != 'delivered' AND {OWN_MATCH}"""
_DELETE_DELIVERED = f"DELETE FROM OutboxEvents WHERE status = 'delivered' AND {OWN_MATCH}"
_DELETE_REQUESTS = f"DELETE FROM IdempotencyRecords WHERE {PRINCIPAL_MATCH}"
# (table, primary key columns and types, JSON column, rows the subject owns).
_EVENT_BODIES = ("OutboxEvents", (("shard", "INT64"), ("event_id", "STRING")), "payload", OWN_MATCH)
_REPLAY_BODIES = ("IdempotencyRecords", (("principal_ref", "STRING"), ("environment", "STRING"),
                                         ("operation", "STRING"), ("idempotency_key", "STRING")),
                  "response_body", PRINCIPAL_MATCH)

_REF = re.compile(r"[A-Za-z0-9._:@/+-]{1,128}")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def matchable(subject_ref: object) -> bool:
    """Whether the platform can match ``subject_ref`` safely (see ``subject_keys``)."""
    return isinstance(subject_ref, str) and _REF.fullmatch(subject_ref) is not None


def subject_keys(subject_ref: str) -> tuple[str, ...]:
    """Every value that names ``subject_ref`` in event and replay records.

    A member UUID is also matched in its ``member:<uuid>`` actor form, and
    ``member:<uuid>`` as the bare UUID. Refs are limited to characters that
    JSON never escapes, so the quoted-token prefilter in ``_unlink`` cannot
    miss an encoded form.
    """
    if not matchable(subject_ref):
        raise ValueError("invalid subject reference")
    bare = subject_ref.removeprefix("member:")
    keys = {subject_ref}
    if _UUID.fullmatch(bare):
        keys.update((bare, f"member:{bare}"))
    return tuple(sorted(keys))


def _nil_for(key: str) -> str:
    # Keeps the form: a 'member:<id>' value stays a member ref.
    return f"member:{NIL_SUBJECT}" if key.startswith("member:") else NIL_SUBJECT


def unlinked(value: object, nil: Mapping[str, str]) -> tuple[object, bool]:
    """``value`` with every JSON string value in ``nil`` replaced, and whether anything changed.

    Values only: object keys are never rewritten (two erased keys would
    collapse into one) and text that merely contains an id is left alone. A
    list keeps at most one nil member, so a list of unique ids stays unique
    when several of its members are erased (decision.closed's
    eligible_respondent_ids is ``uniqueItems``).
    """
    if isinstance(value, str):
        new = nil.get(value, value)
        return new, new != value
    if isinstance(value, dict):
        out, changed = {}, False
        for k, v in value.items():
            out[k], hit = unlinked(v, nil)
            changed = changed or hit
        return out, changed
    if isinstance(value, list):
        items = [unlinked(v, nil) for v in value]
        if not any(hit for _, hit in items):
            return value, False
        nils, out = set(nil.values()), []
        for new, _ in items:
            if not (isinstance(new, str) and new in nils and new in out):
                out.append(new)
        return out, True
    return value, False


def _batches(subject_refs: Iterable[str]) -> list[list[str]]:
    if isinstance(subject_refs, str):
        raise TypeError("pass a collection of subject references, not one string")  # 'm9' would erase 'm' and '9'
    keys = sorted({k for ref in subject_refs for k in subject_keys(ref)})
    return [keys[i:i + SUBJECT_BATCH] for i in range(0, len(keys), SUBJECT_BATCH)]


def _array(batch: Sequence[str]) -> tuple[dict, dict]:
    from google.cloud.spanner_v1 import param_types

    return {"s": list(batch)}, {"s": param_types.Array(param_types.STRING)}


def _unlink(database, bodies: tuple, batch: Sequence[str]) -> int:
    """Replace the subjects in other principals' JSON values; returns the rows changed.

    A snapshot prefilter finds bodies containing a quoted key ('"<x>"': a value
    or an object key); ``unlinked`` rewrites values only. Each write is a
    compare-and-set on the text read, so a row that changed meanwhile is left
    for the next pass instead of being overwritten.
    """
    from google.cloud.spanner_v1 import param_types

    table, key, column, own = bodies
    text = f"TO_JSON_STRING({column})"
    params, types = _array(batch)
    params["q"], types["q"] = [json.dumps(k) for k in batch], param_types.Array(param_types.STRING)  # _REF: no escapes
    with database.snapshot() as snap:
        rows = list(snap.execute_sql(
            f"SELECT {', '.join(c for c, _ in key)}, {text} FROM {table} WHERE NOT {own} "
            f"AND EXISTS(SELECT 1 FROM UNNEST(@q) AS q WHERE STRPOS({text}, q) > 0)", params=params, param_types=types))
    nil = {k: _nil_for(k) for k in batch}
    changes = []
    for *pk, old in rows:
        new, changed = unlinked(json.loads(old), nil)
        if changed:
            changes.append((pk, old, json.dumps(new, separators=(",", ":"))))
    where = " AND ".join(f"{c} = @k{i}" for i, (c, _) in enumerate(key))
    sql = f"UPDATE {table} SET {column} = PARSE_JSON(@new) WHERE {where} AND {text} = @old"
    row_types = {**{f"k{i}": getattr(param_types, t) for i, (_, t) in enumerate(key)},
                 "old": param_types.STRING, "new": param_types.STRING}
    done = 0
    for i in range(0, len(changes), UNLINK_BATCH):
        statements = [(sql, {**{f"k{j}": v for j, v in enumerate(pk)}, "old": old, "new": new}, row_types)
                      for pk, old, new in changes[i:i + UNLINK_BATCH]]

        def tx(t, statements=statements):
            status, counts = t.batch_update(statements)
            if status.code != 0:
                raise RuntimeError("unlink_failed")  # never the status text: it can quote a body
            return sum(counts)

        done += database.run_in_transaction(tx)
    return done


def erase_subject_events(database, subject_refs: Iterable[str]) -> tuple[int, int, int]:
    """Erase the subjects from the outbox; idempotent, outside any caller's transaction.

    The subjects' own events: undelivered ones are withdrawn and delivered ones
    deleted (partitioned DML). Every other event naming them, in any status,
    keeps its row with the subjects unlinked. Returns ``(withdrawn, deleted,
    unlinked)``; Spanner reports a lower bound for partitioned DML, and a row
    naming subjects from several batches is unlinked (and counted) per batch.
    """
    withdrawn = deleted = changed = 0
    for batch in _batches(subject_refs):
        params, types = _array(batch)
        # Withdraw first: a withdrawn row can never become delivered (_finish
        # requires 'leased'), so the delete then sees every delivered row.
        withdrawn += database.execute_partitioned_dml(_WITHDRAW, params=params, param_types=types)
        deleted += database.execute_partitioned_dml(_DELETE_DELIVERED, params=params, param_types=types)
        changed += _unlink(database, _EVENT_BODIES, batch)
    return withdrawn, deleted, changed


def erase_subject_requests(database, subject_refs: Iterable[str]) -> tuple[int, int]:
    """Delete the subjects' replay records; unlink them from other principals' bodies.

    Another member's record stays (deleting it would let their retry run the
    command twice); each JSON string value naming a subject becomes the nil
    member. Returns ``(deleted, unlinked)``; a body naming subjects from
    several batches is unlinked (and counted) once per batch.
    """
    deleted = changed = 0
    for batch in _batches(subject_refs):
        params, types = _array(batch)
        deleted += database.execute_partitioned_dml(_DELETE_REQUESTS, params=params, param_types=types)
        changed += _unlink(database, _REPLAY_BODIES, batch)
    return deleted, changed


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
    unlinked: int = 0
    requests_deleted: int = 0
    requests_unlinked: int = 0


def sweep_erased_subjects(database, now: datetime, window: timedelta = SWEEP_WINDOW) -> SweepResult:
    """Re-erase subjects whose account deletion tombstoned a platform category within ``window``.

    Reads the privacy lane's DeletionTombstones and DeletionJobs (V009,
    read-only here): whole-category tombstones of the two foundation
    categories whose job has ``scope = 'account'``. A category-only job is
    refused by the handler (erasure.py) and never swept: that member is still
    active. Refs the platform cannot match were refused too and are skipped.
    """
    from google.cloud.spanner_v1 import param_types

    since = _aware(now) - window
    with database.snapshot() as snap:
        rows = snap.execute_sql(
            "SELECT DISTINCT t.subject_ref FROM DeletionTombstones@{FORCE_INDEX=DeletionTombstonesByCreated} AS t "
            "JOIN DeletionJobs AS j ON j.job_id = t.deletion_job_id "
            "WHERE t.created_at >= @since AND t.category IN UNNEST(@c) "
            "AND (t.record_keys IS NULL OR ARRAY_LENGTH(t.record_keys) = 0) "
            "AND j.scope = 'account' AND j.subject_ref = t.subject_ref",
            params={"since": since, "c": list(CATEGORIES)},
            param_types={"since": param_types.TIMESTAMP, "c": param_types.Array(param_types.STRING)})
        subjects = sorted({r[0] for r in rows if matchable(r[0])})
    if not subjects:
        return SweepResult()
    withdrawn, deleted, changed = erase_subject_events(database, subjects)
    requests_deleted, requests_unlinked = erase_subject_requests(database, subjects)
    return SweepResult(len(subjects), withdrawn, deleted, changed, requests_deleted, requests_unlinked)


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
        list(snap.execute_sql("""SELECT subject_ref, record_keys, deletion_job_id
            FROM DeletionTombstones@{FORCE_INDEX=DeletionTombstonesByCreated} LIMIT 1"""))
        list(snap.execute_sql("SELECT job_id, subject_ref, scope FROM DeletionJobs LIMIT 1"))
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
