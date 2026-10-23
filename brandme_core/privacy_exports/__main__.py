"""Private selected-category export API or leased worker in the core image.

python -m brandme_core.privacy_exports [--check | --worker [--once]]
Schema/resources are provisioned separately; this command never creates them.
"""
import argparse
import json
import os
import signal
import threading

from .config import ExportConfig


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--worker", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.once and not args.worker:
        parser.error("--once requires --worker")
    pool = store = None
    try:
        from google.cloud import spanner
        from google.cloud.spanner_v1.pool import BurstyPool
        import uvicorn
        from .app import create_app
        from .service import ExportService, verify_schema
        from .storage import PrivateStore
        config = ExportConfig.from_env(os.environ)
        pool = BurstyPool()
        db = spanner.Client(project=config.project).instance(config.instance).database(config.database, pool=pool)
        verify_schema(db)
        store = PrivateStore(config)
        store.check()
        if args.check:
            print('{"status":"ready","full_account":false}', flush=True)
        elif args.worker:
            stopped = threading.Event()
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: stopped.set())
            service = ExportService(db, config, store)
            while not stopped.is_set():
                try:
                    outcome = service.run_once()
                except Exception:
                    outcome = "dependency_unavailable"
                print(json.dumps({"export_worker": outcome, "cleanup_failures": service.cleanup_failures}), flush=True)
                if args.once:
                    return 2 if outcome == "dependency_unavailable" or service.cleanup_failures else 0
                stopped.wait(10 if outcome in {"idle", "dependency_unavailable"} else 1)
        else:
            uvicorn.run(create_app(db, config, store), host="0.0.0.0", port=config.port, access_log=False,
                        proxy_headers=False, server_header=False, limit_concurrency=32, timeout_keep_alive=5)
        return 0
    except Exception:
        print('{"status":"startup_refused"}', flush=True)
        return 2
    finally:
        if store is not None:
            store.close()
        if pool is not None:
            pool.clear()


if __name__ == "__main__":
    raise SystemExit(main())
