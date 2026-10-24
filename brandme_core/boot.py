# brandme_core/boot.py
"""
In-process boot guard for service entry modules (W00 BM-BASE-002).

The compose ``preflight`` command only protects processes that compose starts.
An image CMD, ``uvicorn main:app`` or ``TestClient(app)`` imports the entry
module directly, so each legacy FastAPI entry module calls :func:`guard` at
import time, before it constructs its app::

    from brandme_core.boot import guard
    BRANDME_MODE = guard("orchestrator")

When the service may not boot (BRANDME_MODE missing or invalid, ENVIRONMENT
contradicting it, or a trust-path fake in sandbox/production) the guard writes
one ``[brandme boot] <service>: REFUSED — <reason>`` line to stderr and raises
:class:`BootRefused`, a ``SystemExit`` with code 3 (the preflight CLI's code).
The import therefore fails: no ``app`` object exists, uvicorn exits non-zero
before it binds a socket, and an uncaught refusal ends the interpreter with
status 3. ``SystemExit`` is used so a broad ``except Exception`` cannot swallow
the refusal.

Caveat: with ``uvicorn --reload`` the supervisor process binds the socket and
only its child imports the app, so the child exits while the supervisor keeps
the port open. Do not use ``--reload`` outside local development.
"""

from __future__ import annotations

import sys
from typing import Iterable, Mapping, Optional

from .config import (
    AdapterRegistration,
    Mode,
    ModeConfigurationError,
    TrustPathViolation,
    enforce_boot_guard,
)

EXIT_REFUSED = 3


class BootRefused(SystemExit):
    """The service refused to boot; ``reason`` is the underlying guard error."""

    def __init__(self, service: str, reason: Exception):
        super().__init__(EXIT_REFUSED)
        self.service = service
        self.reason = reason
        self.message = f"[brandme boot] {service}: REFUSED — {reason}"

    def __str__(self) -> str:
        return self.message


def guard(
    service: str,
    registrations: Optional[Iterable[AdapterRegistration]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Mode:
    """Return the mode ``service`` may run in, or refuse the boot (see module docs)."""
    try:
        return enforce_boot_guard(service, registrations, env)
    except (ModeConfigurationError, TrustPathViolation) as exc:
        refused = BootRefused(service, exc)
        print(refused.message, file=sys.stderr, flush=True)
        raise refused from exc
