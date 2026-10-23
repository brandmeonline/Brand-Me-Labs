"""Processing guard for every writer of personal or derived data in this lane.

Delegates to the privacy lane's published ``assert_processing_allowed``
(``brandme_core.domains.privacy.deletion``, opus-midnight-rights W10). That
module and its V009 tables (``ProcessingFreezes``, ``DeletionTombstones``) are
not on this lane's base branch yet. Until integration supplies them, this guard
is a no-op and the lane falls back to its own deletion tombstones
(e.g. ``PersonaTombstones``). The fallback is reported by
``guard_enforced()`` so status and tests can say which guard actually ran.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


class ProcessingFrozen(Exception):
    """A write was refused because of a freeze or a newer deletion tombstone."""


def guard_enforced() -> bool:
    try:
        import brandme_core.domains.privacy.deletion  # noqa: F401
    except ImportError:
        return False
    return True


def assert_processing_allowed(txn: Any, member_id: str, category: str, basis_time: datetime) -> bool:
    """Raise ``ProcessingFrozen`` if the privacy lane forbids this write.

    Returns True when the privacy lane's guard ran and False when it is absent.
    The subject reference is the internal member UUID.
    """
    try:
        from brandme_core.domains.privacy.deletion import ProcessingFrozenError, assert_processing_allowed as guard
    except ImportError:
        return False
    try:
        guard(txn, member_id, category, basis_time)
    except ProcessingFrozenError as exc:
        raise ProcessingFrozen(str(exc)) from exc
    return True
