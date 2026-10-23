"""Outbox/inbox/idempotency against the emulator (W02 exit: retries never duplicate events or effects)."""
import threading
import uuid

import pytest
from google.api_core.exceptions import Aborted

from brandme_core.domains import (
    CommandContext, IdempotencyConflict, Principal, run_command, run_idempotent_command,
)
from brandme_core.events import OutboxDispatcher, first_delivery

from .conftest import requires_spanner

pytestmark = requires_spanner


class _AbortCause:
    """Minimal grpc.Call stand-in: the client reads retry delay from trailing metadata."""

    def trailing_metadata(self):
        return []


def _principal():
    mid = str(uuid.uuid4())
    return Principal(member_id=mid, subject="dev|t", session_id=None, client_id=None,
                     scopes=frozenset({"profile:write"}), assurance_level="simulated", environment="development")


def _insert_member(tx, member_id):
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP
    tx.insert("Members", columns=("member_id", "locale", "timezone", "age_eligibility_status", "account_state",
                                   "environment", "onboarding_state", "version", "created_at", "updated_at"),
              values=[(member_id, "en-US", "UTC", "unknown", "active", "development", "not_started", 1,
                       COMMIT_TIMESTAMP, COMMIT_TIMESTAMP)])


def _count(db, sql, **params):
    from google.cloud.spanner_v1 import param_types
    with db.snapshot() as s:
        return list(s.execute_sql(sql, params=params, param_types={k: param_types.STRING for k in params}))[0][0]


def test_transaction_retry_commits_exactly_one_outbox_event(migrated_database):
    p = _principal()
    ctx = CommandContext(principal=p, environment="development")
    attempts = {"n": 0}

    def cmd(tx, c):
        attempts["n"] += 1
        _insert_member(tx, p.member_id)
        c.emit("member.created", "1", "member", p.member_id, 1,
               {"member_id": p.member_id, "identity_provider": "dev"}, "member_private")
        if attempts["n"] == 1:
            raise Aborted("simulated contention", errors=[_AbortCause()])  # Spanner retries the whole callback
        return "ok"

    assert run_command(migrated_database, ctx, cmd) == "ok"
    assert attempts["n"] == 2
    assert _count(migrated_database, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id = @a", a=p.member_id) == 1
    assert _count(migrated_database, "SELECT COUNT(*) FROM Members WHERE member_id = @a", a=p.member_id) == 1


def test_failed_command_writes_neither_rows_nor_events(migrated_database):
    p = _principal()
    ctx = CommandContext(principal=p, environment="development")

    def cmd(tx, c):
        _insert_member(tx, p.member_id)
        c.emit("member.created", "1", "member", p.member_id, 1, {"member_id": p.member_id, "identity_provider": "dev"}, "member_private")
        raise ValueError("invariant violated")

    with pytest.raises(ValueError):
        run_command(migrated_database, ctx, cmd)
    assert _count(migrated_database, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id = @a", a=p.member_id) == 0
    assert _count(migrated_database, "SELECT COUNT(*) FROM Members WHERE member_id = @a", a=p.member_id) == 0


def test_dispatch_is_at_least_once_and_inbox_applies_once(migrated_database):
    p = _principal()
    ctx = CommandContext(principal=p, environment="development")
    run_command(migrated_database, ctx, lambda tx, c: (_insert_member(tx, p.member_id), c.emit(
        "member.created", "1", "member", p.member_id, 1, {"member_id": p.member_id, "identity_provider": "dev"}, "member_private")))
    effects = []

    def consumer(ev):
        def tx_fn(tx):
            if first_delivery(tx, "test-projection", ev):
                effects.append(ev.event_id)
        migrated_database.run_in_transaction(tx_fn)

    failing = {"left": 1}

    def deliver(ev):
        consumer(ev)  # consumer commits its receipt...
        if failing["left"]:
            failing["left"] -= 1
            raise ConnectionError("ack lost after remote success")  # ...but the ack is lost

    d = OutboxDispatcher(migrated_database, deliver, base_backoff_seconds=0, max_backoff_seconds=0)
    r1 = d.run_once()
    assert r1.failed >= 1
    r2 = d.run_once()
    assert r2.delivered >= 1
    mine = [e for e in effects]
    assert len(mine) == len(set(mine)), "redelivery must not reapply the effect"
    assert _count(migrated_database, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id = @a AND status = 'delivered'", a=p.member_id) == 1


def test_idempotent_command_replays_and_rejects_key_reuse(migrated_database):
    p = _principal()
    calls = []

    def cmd(tx, c):
        calls.append(1)
        _insert_member(tx, p.member_id)
        return {"member_id": p.member_id}

    key = "k-" + uuid.uuid4().hex
    r1, replay1 = run_idempotent_command(migrated_database, CommandContext(p, "development"), "member.create", key, {"x": 1}, cmd)
    r2, replay2 = run_idempotent_command(migrated_database, CommandContext(p, "development"), "member.create", key, {"x": 1}, cmd)
    assert (replay1, replay2) == (False, True) and r1 == r2 and len(calls) == 1
    with pytest.raises(IdempotencyConflict):
        run_idempotent_command(migrated_database, CommandContext(p, "development"), "member.create", key, {"x": 2}, cmd)


def test_concurrent_duplicate_requests_apply_once(migrated_database):
    p = _principal()
    key = "c-" + uuid.uuid4().hex
    results, errors = [], []

    def cmd(tx, c):
        _insert_member(tx, p.member_id)
        c.emit("member.created", "1", "member", p.member_id, 1, {"member_id": p.member_id, "identity_provider": "dev"}, "member_private")
        return {"member_id": p.member_id}

    def worker():
        try:
            results.append(run_idempotent_command(migrated_database, CommandContext(p, "development"), "member.create", key, {"x": 1}, cmd))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors
    assert sum(1 for _, replay in results if not replay) == 1
    assert _count(migrated_database, "SELECT COUNT(*) FROM OutboxEvents WHERE aggregate_id = @a", a=p.member_id) == 1
