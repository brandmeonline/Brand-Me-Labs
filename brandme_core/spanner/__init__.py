"""
Brand.Me Spanner Client Library
==============================

Provides optimized Spanner client with:
- Connection pooling for high-concurrency NATS JetStream
- Idempotent writes using commit timestamps
- PII redaction at driver level
- Graph query support for consent and provenance
"""

from .client import SpannerClient, create_spanner_client
from .pool import SpannerPoolManager
from .idempotent import IdempotentWriter
from .pii_redactor import PIIRedactingClient
from .consent_graph import ConsentGraphClient
from .provenance import ProvenanceClient

__all__ = [
    'SpannerClient',
    'create_spanner_client',
    'SpannerPoolManager',
    'IdempotentWriter',
    'PIIRedactingClient',
    'ConsentGraphClient',
    'ProvenanceClient',
]
