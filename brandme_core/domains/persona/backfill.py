"""
Resumable backfill of the two legacy persona columns (ch.03 §4, ch.06 W02).

The legacy ``Users`` table (``brandme-data/spanner/schema.sql``) stores
``persona_warm_cold`` and ``persona_sport_couture`` as FLOAT64 on a 0–1 scale
(0 = warm / sport, 1 = cold / couture; ``brandme-data/schemas/001_users.sql``).
They map onto the ``temperature`` (Warm/Cool) and ``sport_couture`` axes.

We cannot tell whether a legacy value was deliberately chosen, seeded or
written by an old model, so it is NOT copied in as a declared, locked
preference. It becomes inspectable, suppressible ``legacy_profile`` evidence
(purpose ``personalization``, weight 1.0). The member sees "carried over from
your earlier profile" and can exclude it; the ten other axes stay unknown.
(Proposed deviation PD-06.)

The backfill runs in checkpointed batches keyed by ``user_id``; re-running a
batch is idempotent because evidence is unique per source fingerprint. Rows
whose legacy ``user_id`` has no active V001 member, and out-of-range or
non-finite values, are counted and skipped rather than guessed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Optional

from .kernel import INT, STR, query, run_read
from .service import PersonaService

LEGACY_COLUMNS = {"persona_warm_cold": "temperature", "persona_sport_couture": "sport_couture"}


@dataclass
class BackfillReport:
    legacy_table: bool
    scanned: int = 0
    evidence_written: int = 0
    already_present: int = 0
    profiles_created: int = 0
    skipped_no_member: int = 0
    skipped_invalid: int = 0
    skipped_null: int = 0
    skipped_other: Dict[str, int] = field(default_factory=dict)
    next_cursor: Optional[str] = None
    done: bool = False


def legacy_value(raw) -> Optional[int]:
    """0–1 float → 0–100 integer, or None if missing; raises ValueError if invalid."""
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw) or not (0.0 <= raw <= 1.0):
        raise ValueError(f"legacy persona value out of range: {raw!r}")
    return int((Decimal(repr(float(raw))) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _legacy_table_exists(snap) -> bool:
    return bool(
        query(
            snap,
            "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '' AND TABLE_NAME = 'Users' "
            "AND COLUMN_NAME = 'persona_warm_cold'",
        )
    )


def backfill_batch(
    db,
    svc: PersonaService,
    *,
    after_user_id: str = "",
    batch_size: int = 200,
    environment: str = "development",
) -> BackfillReport:
    if not run_read(db, _legacy_table_exists):
        return BackfillReport(legacy_table=False, done=True)
    rows = run_read(
        db,
        lambda s: query(
            s,
            "SELECT user_id, persona_warm_cold, persona_sport_couture FROM Users "
            "WHERE user_id > @after ORDER BY user_id LIMIT @n",
            {"after": after_user_id, "n": batch_size},
            {"after": STR, "n": INT},
        ),
    )
    report = BackfillReport(legacy_table=True, next_cursor=after_user_id or None, done=len(rows) < batch_size)
    for user_id, warm_cold, sport_couture in rows:
        report.scanned += 1
        report.next_cursor = user_id
        values = {}
        invalid = False
        for column, raw in (("persona_warm_cold", warm_cold), ("persona_sport_couture", sport_couture)):
            try:
                v = legacy_value(raw)
            except ValueError:
                invalid = True
                continue
            if v is None:
                report.skipped_null += 1
            else:
                values[column] = v
        if invalid:
            report.skipped_invalid += 1
        if not values:
            continue
        created = svc.ensure_profile(user_id, service="persona-legacy-backfill", environment=environment)
        if created == "tombstoned":
            report.skipped_no_member += 1
            continue
        if created == "created":
            report.profiles_created += 1
        for column, v in sorted(values.items()):
            disposition = svc.ingest_evidence(
                member_id=user_id,
                source_type="legacy_profile",
                source_ref=f"Users/{user_id}/{column}",
                axis_contributions={LEGACY_COLUMNS[column]: v},
                weight=1.0,
                service="persona-legacy-backfill",
                environment=environment,
            )
            if disposition == "accepted":
                report.evidence_written += 1
            elif disposition == "duplicate":
                report.already_present += 1
            else:
                report.skipped_other[disposition] = report.skipped_other.get(disposition, 0) + 1
    return report


def backfill_all(db, svc: PersonaService, *, batch_size: int = 200, environment: str = "development", cursor: str = ""):
    """Run batches until done; yields each batch report (checkpoint = ``next_cursor``)."""
    while True:
        rep = backfill_batch(db, svc, after_user_id=cursor, batch_size=batch_size, environment=environment)
        yield rep
        if rep.done or rep.next_cursor is None:
            return
        cursor = rep.next_cursor
