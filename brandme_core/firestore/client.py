"""
Brand.Me Firestore Client
========================

Core Firestore client with automatic configuration for emulator/production.
"""

import os
from typing import Optional, Dict, Any, List
import asyncio

from google.cloud import firestore
from google.cloud.firestore_v1 import AsyncClient

from brandme_core.logging import get_logger

logger = get_logger("firestore.client")


class FirestoreClient:
    """
    Unified Firestore client for Brand.Me services.

    Supports both emulator (dev/test) and production modes.
    Provides async operations for wardrobe state management.
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self._client: Optional[AsyncClient] = None
        self._initialized = False

    async def initialize(self):
        """Initialize the Firestore client."""
        if self._initialized:
            return

        emulator_host = os.getenv('FIRESTORE_EMULATOR_HOST')

        if emulator_host:
            logger.info({
                "event": "firestore_init_emulator",
                "host": emulator_host,
                "project": self.project_id
            })
        else:
            logger.info({
                "event": "firestore_init_production",
                "project": self.project_id
            })

        self._client = AsyncClient(project=self.project_id)
        self._initialized = True

        logger.info({"event": "firestore_initialized"})

    async def close(self):
        """Close the Firestore client."""
        if self._client:
            self._client.close()
            self._client = None
            self._initialized = False
            logger.info({"event": "firestore_closed"})

    @property
    def client(self) -> AsyncClient:
        """Get the Firestore client instance."""
        if not self._client:
            raise RuntimeError("FirestoreClient not initialized. Call initialize() first.")
        return self._client

    def collection(self, path: str):
        """Get a collection reference."""
        return self.client.collection(path)

    def document(self, path: str):
        """Get a document reference."""
        return self.client.document(path)

    async def get_document(self, path: str) -> Optional[Dict[str, Any]]:
        """Get a document by path."""
        doc_ref = self.client.document(path)
        doc = await doc_ref.get()

        if doc.exists:
            return doc.to_dict()
        return None

    async def set_document(
        self,
        path: str,
        data: Dict[str, Any],
        merge: bool = False
    ):
        """Set a document."""
        doc_ref = self.client.document(path)
        await doc_ref.set(data, merge=merge)

    async def update_document(self, path: str, data: Dict[str, Any]):
        """Update a document."""
        doc_ref = self.client.document(path)
        await doc_ref.update(data)

    async def delete_document(self, path: str):
        """Delete a document."""
        doc_ref = self.client.document(path)
        await doc_ref.delete()

    async def query_collection(
        self,
        collection_path: str,
        filters: Optional[List[tuple]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Query a collection with optional filters.

        Args:
            collection_path: Path to collection
            filters: List of (field, op, value) tuples
            order_by: Field to order by
            limit: Max documents to return

        Returns:
            List of document dicts
        """
        query = self.client.collection(collection_path)

        if filters:
            for field, op, value in filters:
                query = query.where(field, op, value)

        if order_by:
            query = query.order_by(order_by)

        if limit:
            query = query.limit(limit)

        docs = await query.get()
        return [{'id': doc.id, **doc.to_dict()} for doc in docs]

    async def batch_write(self, operations: List[Dict[str, Any]]):
        """
        Perform batch write operations.

        operations: List of dicts with:
            - type: 'set' | 'update' | 'delete'
            - path: document path
            - data: document data (for set/update)
        """
        batch = self.client.batch()

        for op in operations:
            doc_ref = self.client.document(op['path'])

            if op['type'] == 'set':
                batch.set(doc_ref, op.get('data', {}), merge=op.get('merge', False))
            elif op['type'] == 'update':
                batch.update(doc_ref, op.get('data', {}))
            elif op['type'] == 'delete':
                batch.delete(doc_ref)

        await batch.commit()

    async def health_check(self) -> bool:
        """Check if Firestore is healthy."""
        try:
            # Try to read a test document
            test_ref = self.client.collection('_health').document('check')
            await test_ref.set({'timestamp': firestore.SERVER_TIMESTAMP})
            return True
        except Exception as e:
            logger.error({"event": "firestore_health_check_failed", "error": str(e)})
            return False


def create_firestore_client(project_id: Optional[str] = None) -> FirestoreClient:
    """Factory function to create a FirestoreClient with env config."""
    return FirestoreClient(
        project_id=project_id or os.getenv('FIRESTORE_PROJECT_ID', 'brandme-project')
    )
