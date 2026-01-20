"""
Brand.Me Test Configuration
==========================

Pytest fixtures for Spanner and Firestore emulators.
"""

import os
import pytest
import asyncio
from typing import Generator, AsyncGenerator

# Configure emulator hosts before importing clients
os.environ.setdefault('SPANNER_EMULATOR_HOST', 'localhost:9010')
os.environ.setdefault('SPANNER_PROJECT_ID', 'test-project')
os.environ.setdefault('SPANNER_INSTANCE_ID', 'brandme-instance')
os.environ.setdefault('SPANNER_DATABASE_ID', 'brandme-db')
os.environ.setdefault('FIRESTORE_EMULATOR_HOST', 'localhost:8080')
os.environ.setdefault('FIRESTORE_PROJECT_ID', 'brandme-dev')


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
