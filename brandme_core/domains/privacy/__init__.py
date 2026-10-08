"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Privacy domain (W10): My Data inventory, export, deletion, tombstones and
restore. Other domains register through ``deletion.register_domain``.
"""

from .deletion import (  # noqa: F401
    DataCategory,
    DeletionOutcome,
    DomainPrivacyHandler,
    ExportSection,
    OnDelete,
    PrivacyRegistry,
    ProcessingFrozenError,
    SubjectContext,
    Supplier,
    Tombstone,
    assert_processing_allowed,
    register_domain,
    registry,
)
