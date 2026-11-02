"""The kernel's transaction retry wrapper: which discarded-transaction errors it re-runs, and only against the emulator."""

from __future__ import annotations

import pytest
from google.api_core.exceptions import Aborted, FailedPrecondition, NotFound

from brandme_core.domains.persona.kernel import _retrying

EMULATOR_ABORT = Aborted("Transaction 1 aborted due to active transaction 2. The emulator only supports one transaction at a time.")


def _failing(times: int, exc: Exception):
    calls = {"n": 0}

    def call():
        calls["n"] += 1
        if calls["n"] <= times:
            raise exc
        return calls["n"]

    return call, calls


def test_emulator_single_transaction_abort_is_rerun_until_it_commits(monkeypatch):
    monkeypatch.setenv("SPANNER_EMULATOR_HOST", "127.0.0.1:9010")
    call, calls = _failing(3, EMULATOR_ABORT)
    assert _retrying(call, max_attempts=10, budget_seconds=5) == 4
    assert calls["n"] == 4


def test_emulator_single_transaction_abort_gives_up_after_the_budget(monkeypatch):
    monkeypatch.setenv("SPANNER_EMULATOR_HOST", "127.0.0.1:9010")
    call, calls = _failing(50, EMULATOR_ABORT)
    with pytest.raises(Aborted):
        _retrying(call, max_attempts=3, budget_seconds=5)
    assert calls["n"] == 3


def test_aborted_is_not_rerun_outside_the_emulator(monkeypatch):
    monkeypatch.delenv("SPANNER_EMULATOR_HOST", raising=False)
    call, calls = _failing(1, EMULATOR_ABORT)
    with pytest.raises(Aborted):
        _retrying(call, max_attempts=10, budget_seconds=5)
    assert calls["n"] == 1


def test_other_aborts_are_left_to_the_client_even_on_the_emulator(monkeypatch):
    monkeypatch.setenv("SPANNER_EMULATOR_HOST", "127.0.0.1:9010")
    call, calls = _failing(1, Aborted("Transaction was aborted by the server"))
    with pytest.raises(Aborted):
        _retrying(call, max_attempts=10, budget_seconds=5)
    assert calls["n"] == 1


def test_discarded_transaction_messages_still_rerun(monkeypatch):
    monkeypatch.setenv("SPANNER_EMULATOR_HOST", "127.0.0.1:9010")
    for exc in (FailedPrecondition("Transaction has already been committed or rolledback"), NotFound("Transaction not found")):
        call, calls = _failing(2, exc)
        assert _retrying(call, max_attempts=10, budget_seconds=5) == 3
