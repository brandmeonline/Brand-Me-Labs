"""
Brand.Me Spanner-Firestore Sync
==============================

Synchronizes data between Spanner (source of truth) and
Firestore (real-time cache).
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio
import json

from google.cloud import spanner
from google.cloud.spanner_v1 import param_types

from brandme_core.logging import get_logger

logger = get_logger("firestore.sync")


class SpannerFirestoreSync:
    """
    Bi-directional sync between Spanner and Firestore.

    Spanner is the source of truth for:
    - Asset ownership
    - Consent policies
    - Provenance chain
    - Audit logs

    Firestore is the real-time cache for:
    - Wardrobe state
    - Cube face data (denormalized)
    - Agentic state

    Sync patterns:
    1. Spanner -> Firestore: On asset changes, push to Firestore
    2. Firestore -> Spanner: On agentic modifications, sync back
    """

    def __init__(self, spanner_pool, firestore_client, wardrobe_manager, agentic_manager):
        self.spanner = spanner_pool
        self.firestore = firestore_client
        self.wardrobe = wardrobe_manager
        self.agentic = agentic_manager

    async def sync_cube_to_firestore(
        self,
        asset_id: str,
        owner_id: str
    ):
        """
        Sync a cube's data from Spanner to Firestore.

        Used when:
        - New cube is created
        - Ownership changes
        - Initial load
        """
        # Fetch from Spanner
        async with self.spanner.session() as snapshot:
            # Get asset
            asset_result = snapshot.execute_sql(
                """
                SELECT asset_id, current_owner_id, display_name, created_at, updated_at
                FROM Assets
                WHERE asset_id = @asset_id
                """,
                params={'asset_id': asset_id},
                param_types={'asset_id': param_types.STRING}
            )
            asset_rows = list(asset_result)

            if not asset_rows:
                logger.warning({
                    "event": "sync_asset_not_found",
                    "asset_id": asset_id[:8] + "..."
                })
                return

            # Get faces
            faces_result = snapshot.execute_sql(
                """
                SELECT face_name, data, visibility, blockchain_tx_hash, updated_at
                FROM CubeFaces
                WHERE cube_id = @cube_id
                """,
                params={'cube_id': asset_id},
                param_types={'cube_id': param_types.STRING}
            )

            faces = {}
            visibility_settings = {}

            for row in faces_result:
                face_name = row[0]
                faces[face_name] = {
                    'data': json.loads(row[1]) if row[1] else {},
                    'blockchain_tx_hash': row[3]
                }
                visibility_settings[face_name] = row[2]

        # Default faces if not present
        default_faces = ['product_details', 'provenance', 'ownership', 'social_layer', 'esg_impact', 'lifecycle']
        for face in default_faces:
            if face not in faces:
                faces[face] = {'data': {}}
                visibility_settings[face] = 'public' if face not in ['ownership', 'lifecycle'] else 'private'

        # Add to Firestore wardrobe
        await self.wardrobe.add_cube(
            user_id=owner_id,
            cube_id=asset_id,
            faces={name: data.get('data', {}) for name, data in faces.items()},
            visibility_settings=visibility_settings
        )

        logger.info({
            "event": "cube_synced_to_firestore",
            "asset_id": asset_id[:8] + "...",
            "owner_id": owner_id[:8] + "...",
            "faces": list(faces.keys())
        })

    async def sync_face_to_spanner(
        self,
        user_id: str,
        cube_id: str,
        face_name: str
    ):
        """
        Sync a face's data from Firestore back to Spanner.

        Used after agent modifications.
        """
        # Mark as syncing
        await self.agentic.start_sync(user_id, cube_id, face_name)

        try:
            # Get face data from Firestore
            cube_data = await self.wardrobe.get_cube(user_id, cube_id)
            if not cube_data:
                raise ValueError(f"Cube {cube_id} not found")

            face_data = cube_data.get('faces', {}).get(face_name)
            if not face_data:
                raise ValueError(f"Face {face_name} not found")

            # Write to Spanner
            def _update_face(transaction):
                # Convert data to bytes for storage
                data_bytes = json.dumps(face_data.get('data', {})).encode('utf-8')

                transaction.insert_or_update(
                    table='CubeFaces',
                    columns=['cube_id', 'face_name', 'data', 'visibility', 'updated_at'],
                    values=[(
                        cube_id,
                        face_name,
                        data_bytes,
                        face_data.get('visibility', 'public'),
                        spanner.COMMIT_TIMESTAMP
                    )]
                )

            self.spanner.run_in_transaction(_update_face)

            # Mark sync complete
            await self.agentic.complete_sync(user_id, cube_id, face_name)

            logger.info({
                "event": "face_synced_to_spanner",
                "cube_id": cube_id[:8] + "...",
                "face": face_name
            })

        except Exception as e:
            logger.error({
                "event": "sync_to_spanner_failed",
                "cube_id": cube_id[:8] + "...",
                "face": face_name,
                "error": str(e)
            })
            raise

    async def sync_pending_changes(self, user_id: str) -> int:
        """
        Sync all pending changes for a user to Spanner.

        Returns number of faces synced.
        """
        pending = await self.wardrobe.get_pending_sync_cubes(user_id)
        count = 0

        for item in pending:
            try:
                await self.sync_face_to_spanner(
                    user_id=user_id,
                    cube_id=item['cube_id'],
                    face_name=item['face_name']
                )
                count += 1
            except Exception as e:
                logger.error({
                    "event": "pending_sync_failed",
                    "cube_id": item['cube_id'][:8] + "...",
                    "face": item['face_name'],
                    "error": str(e)
                })

        return count

    async def sync_ownership_transfer(
        self,
        asset_id: str,
        from_user_id: str,
        to_user_id: str
    ):
        """
        Sync ownership transfer to Firestore.

        Moves cube from one user's wardrobe to another.
        """
        # Transfer in Firestore
        await self.wardrobe.transfer_cube(
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            cube_id=asset_id
        )

        logger.info({
            "event": "ownership_transfer_synced",
            "asset_id": asset_id[:8] + "...",
            "from": from_user_id[:8] + "...",
            "to": to_user_id[:8] + "..."
        })

    async def full_sync_user_wardrobe(self, user_id: str) -> int:
        """
        Fully sync a user's wardrobe from Spanner to Firestore.

        Used for initial load or recovery.
        Returns number of cubes synced.
        """
        # Get all assets owned by user from Spanner
        async with self.spanner.session() as snapshot:
            result = snapshot.execute_sql(
                """
                SELECT asset_id
                FROM Assets
                WHERE current_owner_id = @user_id AND is_active = true
                """,
                params={'user_id': user_id},
                param_types={'user_id': param_types.STRING}
            )
            asset_ids = [row[0] for row in result]

        # Sync each asset
        count = 0
        for asset_id in asset_ids:
            try:
                await self.sync_cube_to_firestore(asset_id, user_id)
                count += 1
            except Exception as e:
                logger.error({
                    "event": "full_sync_cube_failed",
                    "asset_id": asset_id[:8] + "...",
                    "error": str(e)
                })

        logger.info({
            "event": "full_wardrobe_synced",
            "user_id": user_id[:8] + "...",
            "cubes_synced": count
        })

        return count


class SyncWorker:
    """
    Background worker for periodic sync tasks.
    """

    def __init__(self, sync_service: SpannerFirestoreSync):
        self.sync = sync_service
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self, sync_interval_seconds: int = 60):
        """Start the sync worker."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop(sync_interval_seconds))
        logger.info({"event": "sync_worker_started", "interval": sync_interval_seconds})

    async def stop(self):
        """Stop the sync worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info({"event": "sync_worker_stopped"})

    async def _run_loop(self, interval: int):
        """Main sync loop."""
        while self._running:
            try:
                # Clean up stale agent sessions
                cleaned = await self.sync.agentic.cleanup_stale_sessions()
                if cleaned > 0:
                    logger.info({"event": "stale_sessions_cleaned", "count": cleaned})

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error({
                    "event": "sync_worker_error",
                    "error": str(e)
                })
                await asyncio.sleep(interval)
