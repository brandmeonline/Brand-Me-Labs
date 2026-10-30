"""Assistant tasks and My Data deletion (ch.03 §8): queued work cannot recreate deleted data.

Every write a task makes carries its processing basis: the time the task was created,
on the commerce service's clock. A category deletion that completes after that refuses
the task's next write in the category, and the task stops with the fixed code
``processing_restricted``. A task created after the deletion may write again. Inline
and background runs alike, on an in-memory tombstone stand-in and on Spanner through
the real ``MyDataService``.
"""

import pytest

from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.domains.commerce.privacy_handler import CARTS_QUOTES
from brandme_core.domains.commerce.store import InMemoryCommerceStore
from brandme_core.domains.privacy.deletion import ProcessingFrozenError
from brandme_core.mcp.authz import ExecutorAssertionVerifier
from brandme_core.mcp.tools import McpToolExecutor
from brandme_core.orchestrator import AssistantRuntime, BackgroundRunner, DeterministicPlanner
from tests.fixtures.commerce.harness import MEMBER, world
from tests.fixtures.commerce.stores import _spanner_db  # noqa: F401  (fixture)
from tests.test_commerce_privacy import _real_now, my_data  # noqa: F401  (fixture)

RUNS = pytest.mark.parametrize("background", [False, True], ids=["inline", "background"])


class _TombstoneStore(InMemoryCommerceStore):
    """In-memory stand-in for a completed category deletion's tombstone (V009 ``DeletionTombstones``)."""

    def __init__(self):
        super().__init__()
        self.tombstones = {}
        self.bases = []  # the processing basis each guarded write was checked against

    def assert_processing_allowed(self, member_id, category, basis_time):
        self.bases.append(basis_time)
        super().assert_processing_allowed(member_id, category, basis_time)
        deleted_at = self.tombstones.get((member_id, category))
        if deleted_at is not None and deleted_at >= basis_time:
            raise ProcessingFrozenError(f"{category} was deleted after this job's basis time")


class _DeletesAfterSearch(DeterministicPlanner):
    """Once the task has read its inputs (the catalog search), the member's deletion completes."""

    def __init__(self, delete, background=False):
        self.delete, self.done, self.runs_in_background = delete, False, background

    def next_calls(self, task, observations):
        if observations and not self.done:
            self.done = True
            self.delete()
        return super().next_calls(task, observations)


def _runtime(w):
    ex = McpToolExecutor(commerce=w.svc, registry=w.registry,
                         verifier=ExecutorAssertionVerifier(gateway_issuer="gw", keys={}, environment="development"))
    return AssistantRuntime(ex, environment="development")


def _run(rt, ag, planner, background):
    task = rt.create(ag, "overshirt", AssistanceMode.PREPARE)
    if not background:
        return rt.run(ag, task.id, planner)
    runner = BackgroundRunner(rt)
    try:
        runner.submit(ag, task.id, planner)
        assert runner.drain(30)
    finally:
        runner.shutdown()
    return rt.get(ag, task.id)


def _member_carts(w):
    return [c for c in w.store.rows("carts") if c.member_id == MEMBER]


def _assert_stopped(task):
    errors = [e.data["code"] for e in task.events if e.type == "error"]
    assert (task.state, errors) == ("failed", ["processing_restricted"])
    refused = [e.data for e in task.events if e.type == "action_refused"]
    assert refused == [{"tool": "brandme.cart.create", "code": "processing_restricted"}]
    assert not any(e.type in ("approval_requested", "outcome") for e in task.events)


@RUNS
def test_a_deletion_completed_mid_task_stops_the_task_in_memory(background):
    store = _TombstoneStore()
    w = world(store=store)
    _, ag = w.delegate(AssistanceMode.PREPARE)
    rt = _runtime(w)
    store.bases.clear()  # creating the grant was a guarded write too

    def delete():
        w.svc.erase_carts_and_quotes(MEMBER)
        store.tombstones[(MEMBER, CARTS_QUOTES)] = w.clock()
        w.clock.advance(seconds=1)  # the deletion is complete and time moves on

    task = _run(rt, ag, _DeletesAfterSearch(delete, background), background)
    _assert_stopped(task)
    assert store.bases == [task.created_at]  # the task's creation, not "now"
    assert _member_carts(w) == [] and w.store.rows("quotes") == []
    # Work created after the deletion reads fresh inputs and may write again.
    fresh = _run(rt, ag, DeterministicPlanner(), background)
    assert fresh.state == "awaiting_approval" and len(_member_carts(w)) == 1


@RUNS
def test_a_deletion_completed_mid_task_stops_the_task_on_spanner(my_data, background):
    svc, w = my_data
    w.clock.now = _real_now()  # a deployment's service clock: tombstones carry Spanner commit times
    _, ag = w.delegate(AssistanceMode.PREPARE)
    rt = _runtime(w)
    receipts = []

    def delete():
        receipts.append(svc.run_deletion(svc.request_deletion(MEMBER, _real_now(), [CARTS_QUOTES])))
        w.clock.now = _real_now()

    task = _run(rt, ag, _DeletesAfterSearch(delete, background), background)
    assert receipts and receipts[0]["completed_at"] is not None  # the category was deleted, the freeze lifted
    _assert_stopped(task)
    assert _member_carts(w) == [] and w.store.rows("quotes") == []
    w.clock.now = _real_now()
    fresh = _run(rt, ag, DeterministicPlanner(), background)
    assert fresh.state == "awaiting_approval" and len(_member_carts(w)) == 1
