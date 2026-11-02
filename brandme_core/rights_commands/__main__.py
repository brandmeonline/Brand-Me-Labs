"""Run the rights command service in the core image: python -m brandme_core.rights_commands.

--check validates configuration, migration coverage and the restore barrier
without listening. No schema changes, wallet operations or chain broadcasts.
"""
from __future__ import annotations

import argparse
import os

from .config import CommandConfig


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    pool = None
    try:
        from google.cloud import spanner
        from google.cloud.spanner_v1.pool import BurstyPool
        import uvicorn
        from .app import create_app, verify_schema

        config = CommandConfig.from_env(os.environ)
        # Shared trust-path inventory, in-process. This service has no audited
        # entry yet, so strict modes refuse it (exit 3, not caught here).
        from brandme_core.boot import guard

        guard("rights_commands")
        pool = BurstyPool()
        client = spanner.Client(project=config.project)
        db = client.instance(config.instance).database(config.database, pool=pool)
        verify_schema(db)
        if args.check:
            print('{"status":"ready","commands":true}', flush=True)
            return 0
        uvicorn.run(create_app(db, config), host="0.0.0.0", port=config.port, access_log=False,
                    proxy_headers=False, server_header=False, limit_concurrency=64, timeout_keep_alive=5)
        return 0
    except Exception:
        print('{"status":"startup_refused"}', flush=True)
        return 2
    finally:
        if pool is not None:
            pool.clear()


if __name__ == "__main__":
    raise SystemExit(main())
