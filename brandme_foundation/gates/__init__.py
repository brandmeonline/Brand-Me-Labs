"""Six permanent quality gates run by `make gate`.

Each gate is a callable module that reads its inputs (metrics or fixtures),
computes a single metric, compares to threshold, writes structured JSON to
metrics/gate_results.jsonl, and exits 0 (pass) or 1 (fail).

Pre-traffic mode: gates exit 0 when there is no production data yet but mark
their result as `status: "no_data"` so dashboards can distinguish "no signal"
from "passed". Once Phase 1 ships real telemetry, gates evaluate against it.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_RESULTS_PATH = Path(__file__).resolve().parent.parent / "metrics" / "gate_results.jsonl"


def emit(gate_name: str, status: str, metric: float | None, threshold: float | None,
         details: dict[str, Any] | None = None) -> int:
    """Write a structured gate result. Returns the process exit code."""
    record = {
        "gate": gate_name,
        "status": status,
        "metric": metric,
        "threshold": threshold,
        "ts": datetime.now(timezone.utc).isoformat(),
        "details": details or {},
    }
    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _RESULTS_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")

    if status == "pass" or status == "no_data":
        return 0
    print(f"GATE FAIL: {gate_name} metric={metric} threshold={threshold}", file=sys.stderr)
    return 1
