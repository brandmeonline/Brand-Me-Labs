"""Legacy persona backfill: two 0–1 legacy columns → suppressible evidence,
checkpointed and idempotent; nothing is declared, locked or invented."""

import math
from datetime import datetime, timezone

import pytest

from brandme_core.domains.persona.backfill import backfill_all, backfill_batch, legacy_value
from brandme_core.domains.persona.kernel import FixedClock, member_principal, run_txn
from brandme_core.domains.persona.service import PersonaService
from test_persona_harness import MEMBER_SCOPES, insert_member, new_migrated_database

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

# Minimal subset of the legacy Users table (the full legacy schema.sql is not
# GoogleSQL-valid and is never applied by the runner).
LEGACY_USERS_DDL = """CREATE TABLE Users (
  user_id STRING(36) NOT NULL,
  handle STRING(255) NOT NULL,
  persona_warm_cold FLOAT64,
  persona_sport_couture FLOAT64,
) PRIMARY KEY (user_id)"""


@pytest.fixture(scope="module")
def db():
    database = new_migrated_database()
    yield database
    database.drop()


def test_legacy_value_scaling():
    assert legacy_value(0.35) == 35 and legacy_value(0.725) == 73 and legacy_value(0.0) == 0 and legacy_value(1.0) == 100
    assert legacy_value(None) is None
    for bad in (1.2, -0.1, math.nan, math.inf, True):
        with pytest.raises(ValueError):
            legacy_value(bad)


def test_no_legacy_table_is_a_clean_noop(db):
    rep = backfill_batch(db, PersonaService(db, clock=FixedClock(NOW)))
    assert rep.legacy_table is False and rep.done


def test_backfill_is_checkpointed_idempotent_and_honest(db):
    db.update_ddl([LEGACY_USERS_DDL]).result(120)
    svc = PersonaService(db, clock=FixedClock(NOW))
    alex = insert_member(db, "00000000-0000-4000-8000-00000000000a")
    maya = insert_member(db, "00000000-0000-4000-8000-00000000000b")
    rows = [
        (alex, "alex", 0.35, 0.65),
        (maya, "maya", 1.7, 0.2),                              # invalid warm/cold, valid sport/couture
        ("00000000-0000-4000-8000-00000000000c", "ghost", 0.5, 0.5),  # no V001 member
        ("00000000-0000-4000-8000-00000000000d", "nulls", None, None),
    ]
    run_txn(db, lambda t: t.insert("Users", columns=("user_id", "handle", "persona_warm_cold", "persona_sport_couture"), values=rows))

    reports = list(backfill_all(db, svc, batch_size=2))
    assert [r.scanned for r in reports] == [2, 2, 0]
    total = lambda k: sum(getattr(r, k) for r in reports)
    assert total("evidence_written") == 3 and total("profiles_created") == 2
    assert total("skipped_invalid") == 1 and total("skipped_no_member") == 1 and total("skipped_null") == 2

    # Re-running from the start writes nothing new.
    again = list(backfill_all(db, svc, batch_size=2))
    assert sum(r.evidence_written for r in again) == 0 and sum(r.already_present for r in again) == 3

    a = svc.get(member_principal(alex, MEMBER_SCOPES))
    assert a["profile"]["declared_axes"] == {k: None for k in a["profile"]["declared_axes"]}  # nothing declared
    assert a["profile"]["locked_axes"] == []
    assert a["profile"]["inferred_axes"]["temperature"] == 35 and a["profile"]["inferred_axes"]["sport_couture"] == 65
    assert sum(v is not None for v in a["profile"]["inferred_axes"].values()) == 2  # other ten stay unknown
    ev = svc.list_evidence(member_principal(alex, MEMBER_SCOPES))
    assert {e["source_type"] for e in ev} == {"legacy_profile"}
    # The member can exclude the carried-over value like any other example.
    temp = next(e for e in ev if e["axis_contributions"] == {"temperature": 35})
    out = svc.suppress_evidence(member_principal(alex, MEMBER_SCOPES), temp["evidence_id"])
    assert out["profile"]["inferred_axes"]["temperature"] is None
    rerun = list(backfill_all(db, svc, batch_size=10))
    assert sum(r.evidence_written for r in rerun) == 0
    assert sum(r.already_present for r in rerun) == 2  # alex sport_couture, maya sport_couture
    assert rerun[0].skipped_other == {"suppressed": 1}  # the excluded value is refused, not re-added
    m = svc.get(member_principal(maya, MEMBER_SCOPES))["profile"]["inferred_axes"]
    assert m["temperature"] is None and m["sport_couture"] == 20
