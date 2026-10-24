"""
The foundation outbox worker with this lane's contracts loaded (dev form).

``brandme_core.events.worker`` (PR #47) builds its allowlist from the event
registry at startup and imports only the foundation catalog, so this lane's
events stay ``pending``. This entrypoint imports the five consumer domains
first (registering their closed contracts), then runs the same worker with the
same configuration and safety checks. ``OUTBOX_EVENT_TYPES`` still narrows it.

    python -m brandme_core.domains.persona.outbox_worker [--once|--check]

When the foundation worker imports ``brandme_core.domains.persona.lane`` itself,
this module is no longer needed.
"""

from __future__ import annotations

from typing import List, Optional

from .lane import load_domains


def main(argv: Optional[List[str]] = None) -> int:
    load_domains()
    try:
        from brandme_core.events import worker
    except ImportError:
        print('{"status":"startup_refused","reason":"foundation_outbox_worker_unavailable"}', flush=True)
        return 2
    return worker.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
