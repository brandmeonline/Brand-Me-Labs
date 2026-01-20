"""
Brand.Me Firestore Client Library
================================

Provides real-time wardrobe state management with:
- Real-time listeners for frontend updates
- Agentic state management
- Spanner synchronization
"""

from .client import FirestoreClient, create_firestore_client
from .wardrobe import WardrobeManager
from .realtime import WardrobeRealtimeListener
from .agentic import AgenticStateManager
from .sync import SpannerFirestoreSync

__all__ = [
    'FirestoreClient',
    'create_firestore_client',
    'WardrobeManager',
    'WardrobeRealtimeListener',
    'AgenticStateManager',
    'SpannerFirestoreSync',
]
