"""
Brand.Me Test Configuration
==========================

Pytest fixtures for Spanner and Firestore emulators, plus the honest-CI rules
for the whole ``tests/`` tree:

* ``QUARANTINE``: every known-broken test, with an owner lane and a blocker.
  Nothing is skipped silently; the terminal summary prints a QUARANTINED block.
* ``BRANDME_REQUIRE_EMULATORS=1`` (CI): a skipped test fails the run unless its
  reason matches ``SKIP_ALLOWLIST``.
"""

import ast
import builtins
import importlib
import os
import socket
import pytest
import asyncio
from collections import Counter
from typing import Generator, AsyncGenerator
import sys
from pathlib import Path

# Ensure repository root is importable for `brandme_core` package imports
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Configure emulator hosts before importing clients
os.environ.setdefault('SPANNER_EMULATOR_HOST', 'localhost:9010')
os.environ.setdefault('SPANNER_PROJECT_ID', 'test-project')
os.environ.setdefault('SPANNER_INSTANCE_ID', 'brandme-instance')
os.environ.setdefault('SPANNER_DATABASE_ID', 'brandme-db')
os.environ.setdefault('FIRESTORE_EMULATOR_HOST', 'localhost:8080')
os.environ.setdefault('FIRESTORE_PROJECT_ID', 'brandme-dev')


# ---------------------------------------------------------------------------
# Quarantine registry
# ---------------------------------------------------------------------------
# One entry per (owner, blocker). Targets are pytest node ids relative to the
# repo root: "tests/x.py::test_name" (all parametrizations) or "tests/x.py"
# (every test in the module).
#
# kind "xfail": the tests still run, under pytest.mark.xfail(strict=True,
#   raises=<raises>). They must fail with exactly that exception. Any other
#   failure fails the run, and a pass is XPASS(strict), which also fails the
#   run: a fixed test forces its entry to be deleted here.
# kind "collect_ignore": only for modules that fail at import time (xfail
#   cannot catch those). Applied only while the file named by "while_missing"
#   is absent, so the quarantine lifts itself when the blocker lands.
#
# Re-verified 2026-10-23 at 744d593 with CI's env (Spanner 1.5.45 + REST,
# Firestore 1.22.0, Pub/Sub, BRANDME_REQUIRE_EMULATORS=1). The lane PRs that
# fix a blocker must delete the matching entry in the same PR.
QUARANTINE = [
    {
        "kind": "xfail",
        "owner": "consumer-domains",
        "raises": "FileNotFoundError",
        "blocker": "tests/fixtures/persona/catalog_candidates.json was never committed (it was hidden by the old "
                   "blanket *.json .gitignore rule, now allowlisted); the lane must commit the fixture",
        "targets": [
            "tests/test_persona_recommender.py::test_deterministic_and_input_order_invariant",
            "tests/test_persona_recommender.py::test_hard_budget_and_exclusions_are_never_violated",
            "tests/test_persona_recommender.py::test_reasons_reference_actual_scoring_evidence",
            "tests/test_persona_recommender.py::test_no_wardrobe_means_no_wardrobe_reason",
            "tests/test_persona_recommender.py::test_neutral_start_is_honest",
            "tests/test_persona_recommender.py::test_sponsorship_is_labelled_and_never_boosts_score",
            "tests/test_persona_recommender.py::test_diversity_caps",
            "tests/test_persona_recommender.py::test_declared_preference_changes_ranking",
            "tests/test_persona_service.py::test_suppression_changes_recommendations_and_blocks_reuse",
            "tests/test_persona_service.py::test_budget_and_exclusions_flow_through_to_recommendations",
            "tests/test_persona_service.py::test_not_me_feedback_hides_product_and_is_idempotent",
            "tests/test_persona_service.py::test_preview_is_read_only",
        ],
    },
    {
        "kind": "xfail",
        "owner": "consumer-domains",
        "raises": "AttributeError",
        "blocker": "AbortOnceDB injects Aborted(errors=['injected']); the locked google-cloud-spanner 3.40.1 retry path "
                   "(session._get_retry_delay) calls .trailing_metadata() on that str, so the retry never happens",
        "targets": [
            "tests/test_persona_service.py::test_transaction_retry_does_not_duplicate_outbox",
        ],
    },
    {
        "kind": "xfail",
        "owner": "commerce-agents",
        "raises": "FileNotFoundError",
        "blocker": "vendored AP2 schemas brandme_core/domains/commerce/ap2_schemas/**/*.json are not on main "
                   "(gitignored when written); they arrive with PR #51",
        "targets": [
            "tests/test_commerce_ap2.py::test_vendored_schemas_are_the_pinned_official_ones",
            "tests/test_commerce_ap2.py::test_valid_mandates_produce_bound_approval_and_purchase",
            "tests/test_commerce_ap2.py::test_replayed_mandate_rejected",
            "tests/test_commerce_ap2.py::test_merchant_checkout_not_matching_quote_rejected",
            "tests/test_commerce_ap2.py::test_merchant_jwt_must_be_es256_and_merchant_signed",
            "tests/test_commerce_ap2.py::test_payment_mandate_terms",
            "tests/test_commerce_ap2.py::test_payment_bound_to_other_checkout_rejected",
            "tests/test_commerce_ap2.py::test_expired_or_overlong_mandate",
            "tests/test_commerce_ap2.py::test_wrong_vct_and_schema_violation",
            "tests/test_commerce_ap2.py::test_key_binding_requires_matching_aud_and_nonce",
        ],
    },
    {
        "kind": "xfail",
        "owner": "commerce-agents",
        "raises": "FileNotFoundError",
        "blocker": "tests/fixtures/providers/impact_feed_fictional.json is not on main (gitignored when written); "
                   "it arrives with PR #51",
        "targets": [
            "tests/test_providers.py::test_feed_replay_and_tombstone",
            "tests/test_providers.py::test_stale_feed_price_is_labeled_not_a_quote",
        ],
    },
    {
        "kind": "collect_ignore",
        "owner": "commerce-agents",
        "while_missing": "brandme_core/mcp/schemas/tool_invocation.schema.json",
        "blocker": "brandme_core/mcp/tools.py reads brandme_core/mcp/schemas/tool_invocation.schema.json at import; "
                   "the MCP schemas arrive with PR #51",
        "targets": [
            "tests/test_mcp.py",
            "tests/test_commerce_assistant.py",
            "tests/test_commerce_protocols.py",
        ],
    },
    {
        "kind": "xfail",
        "owner": "unowned-legacy",
        "raises": "google.api_core.exceptions.NotFound",
        "blocker": "no fixture creates the legacy Users/Assets/Owns/ConsentPolicies/ProvenanceChain schema "
                   "(brandme-data/spanner/schema.sql) in brandme-db; founder decision: delete or fix",
        "targets": [
            "tests/test_consent_graph.py",
            "tests/test_provenance.py",
        ],
    },
    {
        "kind": "xfail",
        "owner": "unowned-legacy",
        "raises": "TypeError",
        "blocker": "WardrobeManager.add_cube puts firestore.SERVER_TIMESTAMP inside the state_history array "
                   "(brandme_core/firestore/wardrobe.py:279), which Firestore rejects; founder decision: delete or fix",
        "targets": [
            "tests/test_wardrobe.py::test_add_cube_to_wardrobe",
            "tests/test_wardrobe.py::test_update_face",
            "tests/test_wardrobe.py::test_transfer_cube",
            "tests/test_wardrobe.py::test_get_all_cubes",
            "tests/test_wardrobe.py::test_visibility_update",
        ],
    },
]

# Legacy modules with no emulator guard of their own: without the emulator they
# hang until --timeout or fail with a connection error (which would also break
# their strict-xfail `raises`). They are skipped with a reason instead, like
# every newer emulator suite; with BRANDME_REQUIRE_EMULATORS=1 that skip fails.
EMULATOR_MODULES = {
    "tests/test_consent_graph.py": "SPANNER_EMULATOR_HOST",
    "tests/test_provenance.py": "SPANNER_EMULATOR_HOST",
    "tests/test_wardrobe.py": "FIRESTORE_EMULATOR_HOST",
}

# With BRANDME_REQUIRE_EMULATORS=1 a skip fails the run unless its reason
# contains one of these strings. Each needs an owner and a reason.
SKIP_ALLOWLIST = {
    # commerce-agents: the official AP2 SDK oracle needs its own pinned
    # interpreter (AP2_SDK_PYTHON); CI does not provide one yet.
    "AP2_SDK_PYTHON": "commerce-agents",
}

_TESTS_DIR = Path(__file__).resolve().parent


def _collect_ignored_entries():
    """collect_ignore entries whose blocking file is still absent."""
    return [e for e in QUARANTINE if e["kind"] == "collect_ignore"
            and not (REPO_ROOT / e["while_missing"]).exists()]


# pytest reads this module-level name; paths are relative to this directory.
collect_ignore = [str((REPO_ROOT / t).relative_to(_TESTS_DIR))
                  for e in _collect_ignored_entries() for t in e["targets"]]


def _require_emulators() -> bool:
    return os.environ.get("BRANDME_REQUIRE_EMULATORS") == "1"


def _resolve_exception(dotted: str):
    if "." not in dotted:
        return getattr(builtins, dotted)
    module, _, name = dotted.rpartition(".")
    return getattr(importlib.import_module(module), name)


def _count_test_functions(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    count = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            count += 1
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            count += sum(1 for n in node.body
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"))
    return count


_reachable_cache = {}


def _emulator_reachable(variable: str) -> bool:
    if variable not in _reachable_cache:
        host, _, port = os.environ.get(variable, "").partition(":")
        try:
            with socket.create_connection((host, int(port)), timeout=1):
                _reachable_cache[variable] = True
        except (OSError, ValueError):
            _reachable_cache[variable] = False
    return _reachable_cache[variable]


def _matches(nodeid: str, target: str) -> bool:
    if "::" not in target:
        return nodeid.startswith(target + "::")
    return nodeid == target or nodeid.startswith(target + "[")


_QUARANTINED = pytest.StashKey[dict]()


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(session, config, items):
    """Mark quarantined tests strict-xfail and reject stale registry entries."""
    quarantined = {}
    matched = set()
    modules = {}
    for item in items:
        module_path = item.nodeid.split("::", 1)[0]
        if getattr(item, "module", None) is not None:
            modules.setdefault(module_path, item.module)
        variable = EMULATOR_MODULES.get(module_path)
        if variable and not _emulator_reachable(variable):
            item.add_marker(pytest.mark.skip(
                reason=f"emulator not reachable ({variable}={os.environ.get(variable, '')}); legacy suite not run"))
            continue
        for entry in QUARANTINE:
            if entry["kind"] != "xfail":
                continue
            target = next((t for t in entry["targets"] if _matches(item.nodeid, t)), None)
            if target is None:
                continue
            matched.add(target)
            reason = f"QUARANTINED [{entry['owner']}] {entry['blocker']}"
            item.add_marker(pytest.mark.xfail(strict=True, raises=_resolve_exception(entry["raises"]), reason=reason))
            quarantined[item.nodeid] = entry
            break
    stale = []
    for entry in QUARANTINE:
        for target in entry["targets"]:
            module_path, _, name = target.partition("::")
            if not (REPO_ROOT / module_path).exists():
                stale.append(f"{target} ({module_path} does not exist)")
            elif entry["kind"] == "xfail" and name and target not in matched and module_path in modules \
                    and not hasattr(modules[module_path], name):
                stale.append(f"{target} (no such test in {module_path})")
    if stale:
        raise pytest.UsageError("stale QUARANTINE entries in tests/conftest.py; delete or fix them:\n  "
                                + "\n  ".join(stale))
    config.stash[_QUARANTINED] = quarantined


def _skip_reason(report) -> str:
    longrepr = report.longrepr
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2])
    return str(longrepr)


def _forbidden_skip(report) -> bool:
    if not (report.skipped and _require_emulators()) or hasattr(report, "wasxfail"):
        return False
    reason = _skip_reason(report)
    return not any(key in reason for key in SKIP_ALLOWLIST)


def _skip_failure_message(report) -> str:
    return (f"BRANDME_REQUIRE_EMULATORS=1 forbids this skip: {_skip_reason(report)}\n"
            "Provide the missing dependency, or add an owned entry to SKIP_ALLOWLIST in tests/conftest.py.")


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """Outermost wrapper: sees the report after xfail handling, so XFAIL is never turned into a failure."""
    outcome = yield
    report = outcome.get_result()
    if _forbidden_skip(report):
        report.longrepr = _skip_failure_message(report)
        report.outcome = "failed"


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_make_collect_report(collector):
    """Module-level skips (pytest.skip(allow_module_level=True), importorskip) count too."""
    outcome = yield
    report = outcome.get_result()
    if _forbidden_skip(report):
        report.longrepr = _skip_failure_message(report)
        report.outcome = "failed"


def pytest_report_header(config):
    ignored = sum(len(e["targets"]) for e in _collect_ignored_entries())
    xfail = sum(len(e["targets"]) for e in QUARANTINE if e["kind"] == "xfail")
    return (f"brandme quarantine: {xfail} strict-xfail targets, {ignored} modules not collected "
            f"(tests/conftest.py QUARANTINE); BRANDME_REQUIRE_EMULATORS={os.environ.get('BRANDME_REQUIRE_EMULATORS', '')}")


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    quarantined = config.stash.get(_QUARANTINED, {})
    xfailed = [r for r in terminalreporter.stats.get("xfailed", []) if r.nodeid in quarantined]
    ignored = _collect_ignored_entries()
    per_owner = Counter(quarantined[r.nodeid]["owner"] for r in xfailed)
    ignored_modules = Counter()
    ignored_functions = Counter()
    for entry in ignored:
        for target in entry["targets"]:
            ignored_modules[entry["owner"]] += 1
            ignored_functions[entry["owner"]] += _count_test_functions(REPO_ROOT / target)
    allowed_skips = Counter()
    for report in terminalreporter.stats.get("skipped", []):
        if hasattr(report, "wasxfail"):
            continue
        reason = _skip_reason(report)
        for key, owner in SKIP_ALLOWLIST.items():
            if key in reason:
                allowed_skips[f"{key} ({owner})"] += 1
    if not (xfailed or ignored or allowed_skips):
        return
    owners = ", ".join(f"{owner}: {n}" for owner, n in sorted(per_owner.items())) or "none"
    tr = terminalreporter
    tr.write_sep("=", "quarantine (not run as passing; see tests/conftest.py QUARANTINE)", yellow=True)
    tr.write_line(f"QUARANTINED: {len(xfailed)} tests (owner: count {owners})")
    for entry in QUARANTINE:
        if entry["kind"] != "xfail":
            continue
        n = sum(1 for r in xfailed if quarantined[r.nodeid] is entry)
        if n:
            tr.write_line(f"  xfail[{entry['raises']}] {entry['owner']}: {n} - {entry['blocker']}")
    if ignored:
        summary = ", ".join(f"{owner}: {ignored_modules[owner]} modules / {ignored_functions[owner]} test functions"
                            for owner in sorted(ignored_modules))
        tr.write_line(f"QUARANTINED (not collected): {sum(ignored_modules.values())} modules ({summary})")
        for entry in ignored:
            tr.write_line(f"  collect_ignore {entry['owner']}: {', '.join(entry['targets'])} - {entry['blocker']}")
    if allowed_skips:
        tr.write_line("ALLOWLISTED SKIPS: " + ", ".join(f"{k}: {n}" for k, n in sorted(allowed_skips.items())))


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def spanner_pool():
    """
    Spanner pool manager configured for emulator.

    Session-scoped to reuse across tests.
    """
    from brandme_core.spanner.pool import create_pool_manager

    pool = create_pool_manager(
        project_id='test-project',
        instance_id='brandme-instance',
        database_id='brandme-db'
    )

    await pool.initialize()
    yield pool
    await pool.close()


@pytest.fixture(scope="session")
async def firestore_client():
    """
    Firestore client configured for emulator.

    Session-scoped to reuse across tests.
    """
    from brandme_core.firestore.client import create_firestore_client

    client = create_firestore_client(project_id='brandme-dev')
    await client.initialize()
    yield client
    await client.close()


@pytest.fixture
async def consent_graph(spanner_pool):
    """Consent graph client for testing."""
    from brandme_core.spanner.consent_graph import ConsentGraphClient
    return ConsentGraphClient(spanner_pool)


@pytest.fixture
async def provenance_client(spanner_pool):
    """Provenance client for testing."""
    from brandme_core.spanner.provenance import ProvenanceClient
    return ProvenanceClient(spanner_pool)


@pytest.fixture
async def wardrobe_manager(firestore_client):
    """Wardrobe manager for testing."""
    from brandme_core.firestore.wardrobe import WardrobeManager
    return WardrobeManager(firestore_client)


@pytest.fixture
async def idempotent_writer(spanner_pool):
    """Idempotent writer for testing."""
    from brandme_core.spanner.idempotent import IdempotentWriter
    return IdempotentWriter(spanner_pool)


@pytest.fixture
async def test_user_id():
    """Generate a test user ID."""
    import uuid
    return str(uuid.uuid4())


@pytest.fixture
async def test_asset_id():
    """Generate a test asset ID."""
    import uuid
    return str(uuid.uuid4())


@pytest.fixture
async def cleanup_spanner(spanner_pool):
    """
    Fixture to cleanup Spanner data after tests.

    Usage:
        async def test_something(cleanup_spanner):
            # test code
            cleanup_spanner.add_user(user_id)
            cleanup_spanner.add_asset(asset_id)
    """
    class SpannerCleanup:
        def __init__(self, pool):
            self.pool = pool
            self.users = []
            self.assets = []
            self.consents = []

        def add_user(self, user_id: str):
            self.users.append(user_id)

        def add_asset(self, asset_id: str):
            self.assets.append(asset_id)

        def add_consent(self, consent_id: str):
            self.consents.append(consent_id)

        async def cleanup(self):
            from google.cloud.spanner_v1 import param_types

            def _cleanup(transaction):
                for user_id in self.users:
                    transaction.execute_update(
                        "DELETE FROM Users WHERE user_id = @user_id",
                        params={'user_id': user_id},
                        param_types={'user_id': param_types.STRING}
                    )

                for asset_id in self.assets:
                    transaction.execute_update(
                        "DELETE FROM Assets WHERE asset_id = @asset_id",
                        params={'asset_id': asset_id},
                        param_types={'asset_id': param_types.STRING}
                    )

                for consent_id in self.consents:
                    transaction.execute_update(
                        "DELETE FROM ConsentPolicies WHERE consent_id = @consent_id",
                        params={'consent_id': consent_id},
                        param_types={'consent_id': param_types.STRING}
                    )

            try:
                self.pool.run_in_transaction(_cleanup)
            except Exception:
                pass  # Ignore cleanup errors

    cleanup = SpannerCleanup(spanner_pool)
    yield cleanup
    await cleanup.cleanup()


@pytest.fixture
async def cleanup_firestore(firestore_client):
    """
    Fixture to cleanup Firestore data after tests.
    """
    class FirestoreCleanup:
        def __init__(self, client):
            self.client = client
            self.paths = []

        def add_path(self, path: str):
            self.paths.append(path)

        async def cleanup(self):
            for path in self.paths:
                try:
                    await self.client.delete_document(path)
                except Exception:
                    pass

    cleanup = FirestoreCleanup(firestore_client)
    yield cleanup
    await cleanup.cleanup()


@pytest.fixture
async def seed_test_user(spanner_pool, test_user_id, cleanup_spanner):
    """
    Create a test user in Spanner.
    """
    from google.cloud import spanner

    def _create(transaction):
        transaction.insert(
            table='Users',
            columns=[
                'user_id', 'handle', 'display_name', 'region_code',
                'trust_score', 'consent_version', 'is_active', 'created_at'
            ],
            values=[(
                test_user_id,
                f'test_user_{test_user_id[:8]}',
                'Test User',
                'us-east1',
                0.8,
                'consent_v1',
                True,
                spanner.COMMIT_TIMESTAMP
            )]
        )

    spanner_pool.run_in_transaction(_create)
    cleanup_spanner.add_user(test_user_id)

    return test_user_id


@pytest.fixture
async def seed_test_asset(spanner_pool, seed_test_user, test_asset_id, cleanup_spanner):
    """
    Create a test asset in Spanner.
    """
    from google.cloud import spanner
    import hashlib

    user_id = seed_test_user
    auth_hash = hashlib.sha256(test_asset_id.encode()).hexdigest()

    def _create(transaction):
        transaction.insert(
            table='Assets',
            columns=[
                'asset_id', 'asset_type', 'display_name',
                'creator_user_id', 'current_owner_id',
                'authenticity_hash', 'is_active', 'created_at'
            ],
            values=[(
                test_asset_id,
                'cube',
                'Test Cube',
                user_id,
                user_id,
                auth_hash,
                True,
                spanner.COMMIT_TIMESTAMP
            )]
        )

        # Create ownership
        transaction.insert(
            table='Owns',
            columns=['owner_id', 'asset_id', 'acquired_at', 'transfer_method', 'is_current'],
            values=[(user_id, test_asset_id, spanner.COMMIT_TIMESTAMP, 'mint', True)]
        )

        # Create provenance entry
        transaction.insert(
            table='ProvenanceChain',
            columns=[
                'provenance_id', 'asset_id', 'sequence_num',
                'from_user_id', 'to_user_id', 'transfer_type', 'transfer_at'
            ],
            values=[(
                f'prov_{test_asset_id[:16]}',
                test_asset_id,
                1,
                None,
                user_id,
                'mint',
                spanner.COMMIT_TIMESTAMP
            )]
        )

    spanner_pool.run_in_transaction(_create)
    cleanup_spanner.add_asset(test_asset_id)

    return test_asset_id
