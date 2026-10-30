"""My Data end to end for the five consumer domains (persona, wardrobe, social,
rewards, media) through the privacy lane's ``MyDataService`` (W10) on a fresh,
fully migrated Spanner emulator database.

Real domain data is written through the domain services, the lane registers
its handlers with ``register_consumer_domains``, and the privacy service then
inventories, exports, freezes, deletes and re-applies tombstones after a
simulated restore. The privacy lane is not on this lane's base branch, so the
module skips there and runs on ``main``/integration.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import ANY

import pytest

pd = pytest.importorskip("brandme_core.domains.privacy.deletion", reason="privacy lane (W10) not on this branch; My Data e2e NOT RUN")

from brandme_core.domains import data_categories  # noqa: E402
from brandme_core.domains.media.providers import ProviderRegistry, SimulatedTryOnProvider  # noqa: E402
from brandme_core.domains.media.service import MediaService  # noqa: E402
from brandme_core.domains.media.store import MemoryMediaStore  # noqa: E402
from brandme_core.domains.persona.kernel import (  # noqa: E402
    NIL_MEMBER,
    DetailedInvalidTransition,
    command,
    member_principal,
    run_txn,
    service_principal,
)
from brandme_core.domains.persona.lane import (  # noqa: E402
    CONSUMER_DOMAINS,
    consumer_privacy_handlers,
    coverage,
    register_consumer_domains,
)
from brandme_core.domains.persona.privacy_guard import WHOLE_CATEGORY_ONLY  # noqa: E402
from brandme_core.domains.persona.card import PersonaCardService  # noqa: E402
from brandme_core.domains.persona.service import PersonaService  # noqa: E402
from brandme_core.domains.privacy.privacy import MyDataService  # noqa: E402
from brandme_core.domains.rewards import ledger  # noqa: E402
from brandme_core.domains.rewards.benefits import BenefitService  # noqa: E402
from brandme_core.domains.rewards.credits import CreditService, apply_credit  # noqa: E402
from brandme_core.domains.rewards.rules import RULES  # noqa: E402
from brandme_core.domains.rewards.service import RewardsService  # noqa: E402
from brandme_core.domains.rewards.surveys import SurveyService  # noqa: E402
from brandme_core.domains.social.decisions import DecisionService  # noqa: E402
from brandme_core.domains.social.houses import HouseService  # noqa: E402
from brandme_core.domains.social.relationships import RelationshipService  # noqa: E402
from brandme_core.domains.social.reports import ReportService  # noqa: E402
from brandme_core.domains.social.rooms import RoomService  # noqa: E402
from brandme_core.domains.social.shares import ShareService  # noqa: E402
from brandme_core.domains.wardrobe.outfits import OutfitService  # noqa: E402
from brandme_core.domains.wardrobe.service import WardrobeService  # noqa: E402
from brandme_core.domains.wardrobe.visibility import ClosetVisibilityService  # noqa: E402
from test_persona_harness import MEMBER_SCOPES, count, insert_member, new_migrated_database  # noqa: E402

WRITER = MEMBER_SCOPES | {"rewards:write"}
OPS = frozenset({"moderation:admin"})
ISSUER = "repairer:atelier-north"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


def key():
    return "k-" + uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc)


class OneHouse:
    """Catalog stand-in: the house exists without seeding the providers lane's tables."""

    def house_name(self, snap, house_ref):
        return "Atelier North" if house_ref == "atelier-north" else None


class MemoryObjectStore:
    def __init__(self):
        self.objects = {}

    def put(self, key, data, content_type):
        self.objects[key] = data
        return f"mem://{key}"

    def delete(self, key):
        self.objects.pop(key, None)


@pytest.fixture(scope="module")
def db():
    # Restore re-applies every tombstone in the database, so this module owns one.
    database = new_migrated_database()
    yield database
    try:
        database.drop()
    except Exception:
        pass


def rows(db, sql, **params):
    from google.cloud.spanner_v1 import param_types

    with db.snapshot() as s:
        it = s.execute_sql(sql, params=params, param_types={k: param_types.STRING for k in params})
        data = list(it)
        return [f.name for f in it.fields], data


def frozen(fn):
    with pytest.raises(DetailedInvalidTransition) as e:
        fn()
    assert e.value.code == "processing_frozen"


def seed(db, store, provider):
    gone = member_principal(insert_member(db), WRITER)
    friend = member_principal(insert_member(db), WRITER)
    persona = PersonaService(db)
    persona.patch(gone, '"0"', {"changes": [{"axis": "expression", "value": 72, "locked": True}], "client_revision": "s"})
    persona.create_snapshot(gone, "Before")

    w = WardrobeService(db)
    item = w.create_items(gone, {"source": "manual", "title": "Linen shirt", "category": "top"}, key())["items"][0]["id"]
    f_item = w.create_items(friend, {"source": "manual", "title": "Scarf", "category": "accessory"}, key())["items"][0]["id"]
    OutfitService(db).create_outfit(gone, {"title": "Look", "item_refs": [item]}, key())
    ClosetVisibilityService(db).set_visibility(gone, item, {"visibility": "friends", "detail": "story", "showcase_note": "My favourite"})
    PersonaCardService(db, persona=persona).settings(gone, {"highlight_item_ids": [item], "show_standings": True})

    rel = RelationshipService(db)
    rel.accept(friend, rel.request(gone, friend.member_id)["relationship_id"])
    rel.mute(friend, gone.member_id)  # someone else's mute of the member
    rel.mute(gone, insert_member(db))  # the member's own mute
    decisions = DecisionService(db)
    theirs = decisions.create(friend, {"subject_type": "wardrobe_item", "subject_id": f_item, "prompt": "Scarf?",
                                       "recipient_ids": [gone.member_id], "duration_seconds": 300, "discussion_mode": "open"}, key())
    decisions.respond(gone, theirs["decision_id"], {"choice": "yes", "note": "Nice"})
    decisions.add_comment(gone, theirs["decision_id"], {"body": "With the navy coat"}, key())
    decisions.create(gone, {"subject_type": "wardrobe_item", "subject_id": item, "prompt": "Shirt?", "recipient_ids": [friend.member_id],
                            "duration_seconds": 300, "discussion_mode": "open"}, key())
    rooms = RoomService(db)
    own_room = rooms.create(gone, {"title": "Gowns", "member_ids": [friend.member_id]}, key())["room_id"]
    rooms.post(gone, own_room, {"kind": "note", "body": "Sage or blue?"}, key())
    their_room = rooms.create(friend, {"title": "Trip", "member_ids": [gone.member_id]}, key())["room_id"]
    rooms.react(gone, their_room, rooms.post(friend, their_room, {"kind": "note", "body": "Pack light"}, key())["post_id"], {"reaction": "yes"})
    ShareService(db).create(gone, {"subject_type": "wardrobe_item", "subject_id": item, "audience": "unlisted", "allowed_fields": ["title"],
                                   "recipient_ids": [], "expires_at": "2027-01-01T00:00:00+00:00"}, key())
    ReportService(db).report(gone, {"target_type": "member", "target": {"member_id": friend.member_id}, "reason": "spam"})
    ReportService(db).report(friend, {"target_type": "member", "target": {"member_id": gone.member_id}, "reason": "spam"})
    ReportService(db).report(friend, {"target_type": "decision_response", "target": {"decision_id": theirs["decision_id"],
                                                                                     "respondent_id": gone.member_id}, "reason": "harassment"})

    rewards = RewardsService(db, approved_repair_issuers=frozenset({ISSUER}))
    for _ in range(2):
        rewards.record_verified_repair(service_principal("repair-workflow"), gone.member_id, repair_ref=str(uuid.uuid4()), issuer_ref=ISSUER)
    benefits = BenefitService(db)
    benefit = benefits.create_benefit(member_principal(insert_member(db), OPS),
                                      {"kind": "room_finish", "title": "Finish", "description": "Cosmetic room finish", "cost_points": 50,
                                       "inventory_total": 5})
    benefits.reserve(gone, benefit["benefit_id"], key())
    rewards.open_dispute(gone, {"category": "other", "message": "question"})
    survey = SurveyService(db).create_survey(member_principal(insert_member(db), OPS), {"kind": "survey", "purpose": "style", "title": "Fit", "questions": [
        {"id": "fit", "prompt": "Which fit?", "type": "single", "options": ["Relaxed", "Tailored"]}]})
    SurveyService(db).respond(gone, survey["survey_id"], {"answers": {"fit": "Relaxed"}}, key())
    for month in (1, 2, 3):  # 600 more points from past months' verified repairs (200 a month is the cap)
        for _ in range(4):
            command(db, service_principal("repair-workflow"), lambda t, ctx, month=month: ledger.credit(
                t, ctx, gone.member_id, RULES["verified_repair"], str(uuid.uuid4()), datetime(2025, month, 15, tzinfo=timezone.utc), [f"repair:{ISSUER}"]))
    CreditService(db).convert(gone, {"points": 500}, key())
    HouseService(db, catalog=OneHouse()).follow(gone, "atelier-north", {"share_standing": True})
    run_txn(db, lambda t: t.insert("HouseStandings", columns=("member_id", "house_ref", "tier", "computed_at", "run_id"),
                                   values=[(gone.member_id, "atelier-north", "top_10", now(), str(uuid.uuid4()))]))

    media = MediaService(db, store, ProviderRegistry([provider]))
    u = media.create_upload(gone, {"kind": "tryon_input", "content_type": "image/png", "bytes": len(PNG)}, key())
    store.client_put(u["upload"]["url"], PNG, "image/png", now=now())
    photo = media.complete_upload(gone, u["media_id"])
    consent = {"accepted": True, "provider_id": provider.terms.provider_id, "terms_version": provider.terms.terms_version}
    job = media.create_job(gone, {"mode": "photo_preview", "input_media_id": photo["media_id"], "item_id": item, "consent": consent}, key())
    media.dispatch_queued()
    media.collect_processing()
    media.save_job(gone, job["job_id"])
    return gone, friend, f_item, theirs, benefit, media


# Tables that hold a member's rows, by the column that names the member.
MEMBER_COLUMNS = {
    "PersonaProfiles": "member_id", "WardrobeItems": "member_id", "Outfits": "member_id",
    "Relationships": "member_id", "Decisions": "member_id", "DecisionResponses": "respondent_id",
    "DecisionAudience": "recipient_id", "ShareGrants": "member_id", "Notifications": "member_id",
    "MemberReports": "reporter_id", "MemberMutes": "muted_member_id", "RewardAccounts": "member_id", "RewardEntries": "member_id",
    "BenefitReservations": "member_id", "RewardDisputes": "member_id", "TryOnConsents": "member_id",
    "TryOnJobs": "member_id", "MediaObjects": "member_id", "DecisionComments": "author_id", "MemberHouses": "member_id",
    "HouseStandings": "member_id", "SurveyResponses": "member_id", "PurchaseCredits": "member_id", "PersonaCards": "member_id",
    "Rooms": "owner_id", "RoomMembers": "member_id", "RoomPosts": "author_id", "RoomReactions": "member_id",
}


def remaining(db, member_id):
    return {t: n for t, c in MEMBER_COLUMNS.items() if (n := count(db, f"SELECT COUNT(*) FROM {t} WHERE {c}=@m", m=member_id))}


MIGRATIONS = Path(__file__).resolve().parents[1] / "brandme-data" / "spanner" / "migrations"
LANE_FILES = [*MIGRATIONS.glob("V00[2-5]_*.sql"), *MIGRATIONS.glob("V016_*.sql")]
LANE_TABLES = frozenset(t for f in LANE_FILES for t in re.findall(r"CREATE TABLE (\w+)", f.read_text()))
# Kept on purpose: member id + time only, so a racing job cannot recreate the profile.
RETAINED = frozenset({"PersonaTombstones"})


def traces(db, member_id):
    """Every lane-table column that still contains the member id anywhere in a value."""
    from google.cloud.spanner_v1 import param_types

    found = {}
    with db.snapshot(multi_use=True) as s:
        cols = list(s.execute_sql("SELECT table_name, column_name, spanner_type FROM INFORMATION_SCHEMA.COLUMNS WHERE table_schema = ''"))
        for table, col, typ in cols:
            if table not in LANE_TABLES or table in RETAINED:
                continue
            if typ.startswith("STRING"):
                cond = f"STRPOS({col}, @m) > 0"
            elif typ.startswith("ARRAY<STRING"):
                cond = f"EXISTS(SELECT 1 FROM UNNEST({col}) AS x WHERE STRPOS(x, @m) > 0)"
            elif typ == "JSON":
                cond = f"STRPOS(TO_JSON_STRING({col}), @m) > 0"
            else:
                continue
            n = list(s.execute_sql(f"SELECT COUNT(*) FROM {table} WHERE {cond}", params={"m": member_id}, param_types={"m": param_types.STRING}))[0][0]
            if n:
                found[f"{table}.{col}"] = n
    return found


def test_consumer_domains_through_my_data(db):
    store, provider = MemoryMediaStore(), SimulatedTryOnProvider()
    gone, friend, f_item, theirs, benefit, media = seed(db, store, provider)
    m = gone.member_id
    assert set(remaining(db, m)) == set(MEMBER_COLUMNS), "seed must touch every table this test checks"

    reg = pd.PrivacyRegistry()
    assert register_consumer_domains(reg, database=db, media_store=store) == list(CONSUMER_DOMAINS)
    register_consumer_domains(reg)  # idempotent for the same registry
    assert coverage(reg) == {"domains": sorted(CONSUMER_DOMAINS), "consumer_domains_complete": True}
    svc = MyDataService(db, MemoryObjectStore(), reg, environment="development")

    # Inventory: the privacy lane's catalog and the foundation catalog agree.
    inventory = {c["key"]: c for c in svc.inventory()}
    assert set(inventory) == {c.name for c in data_categories() if c.domain in CONSUMER_DOMAINS}
    assert all(c["retention"] and c["on_edit"] and c["visible_to"] for c in inventory.values())

    # Export: one package across all five domains, past the forbidden-content scan.
    out = svc.export(m, now())
    cats = out["package"]["categories"]
    assert len(out["sha256"]) == 64 and set(cats) == set(inventory)
    for k in ("persona.declared", "persona.snapshots", "wardrobe.items", "wardrobe.outfits", "social.relationships", "social.decisions",
              "social.shares", "social.reports", "social.houses", "rewards.ledger", "rewards.redemptions", "rewards.disputes",
              "rewards.standings", "rewards.surveys", "rewards.credits", "persona.card", "social.rooms", "media.tryon_consents",
              "media.tryon_media"):
        assert cats[k]["records"], k
    assert cats["social.decisions"]["records"][0]["answered"][0]["note"] == "Nice"
    assert cats["social.decisions"]["records"][0]["commented"][0]["body"] == "With the navy coat"
    assert cats["social.houses"]["records"] == [{"house_ref": "atelier-north", "share_standing": True, "followed_at": ANY}]
    assert cats["rewards.standings"]["records"][0]["tier"] == "top_10"
    assert cats["rewards.ledger"]["records"][0]["account"]["available"] == 160  # 100 + 600 repairs + 10 survey; 50 + 500 held (benefit, credit)
    assert cats["rewards.surveys"]["records"][0]["answers"] == {"fit": "Relaxed"}
    assert cats["rewards.credits"]["records"][0]["amount"] == {"minor": 500, "currency": "USD"}
    assert cats["social.rooms"]["records"][0]["posts"][0]["body"] == "Sage or blue?"
    assert cats["persona.card"]["records"][0]["highlight_item_ids"] == [cats["wardrobe.items"]["records"][0]["item_id"]]
    assert cats["wardrobe.items"]["records"][0]["showcase_note"] == "My favourite"
    assert cats["media.tryon_media"]["records"][0]["jobs"][0]["saved"] is True

    # A backup taken before the deletion (restored below).
    backup_at = now()
    backup = {t: rows(db, f"SELECT * FROM {t} WHERE member_id=@m", m=m) for t in ("PersonaProfiles", "WardrobeItems", "MediaObjects")}
    blobs = {r: v for r, v in store.objects.items() if r.startswith(f"members/{m}/")}
    assert blobs and backup["WardrobeItems"][1] and backup["MediaObjects"][1]

    # Deletion request: every guarded writer for the member is refused from this commit on.
    job = svc.request_deletion(m, now())
    frozen(lambda: WardrobeService(db).create_items(gone, {"source": "manual", "title": "Hat", "category": "accessory"}, key()))
    frozen(lambda: PersonaService(db).create_snapshot(gone, "After"))
    frozen(lambda: BenefitService(db).reserve(gone, benefit["benefit_id"], key()))
    frozen(lambda: RewardsService(db).open_dispute(gone, {"category": "other", "message": "again"}))
    frozen(lambda: media.create_upload(gone, {"kind": "tryon_input", "content_type": "image/png", "bytes": 10}, key()))
    credit_id = rows(db, "SELECT credit_id FROM PurchaseCredits WHERE member_id=@m", m=m)[1][0][0]
    frozen(lambda: run_txn(db, lambda t: apply_credit(t, member_id=m, credit_id=credit_id, order_ref="order-dev-1", currency="USD")))
    # Other members cannot newly reach the frozen member: a share naming them is refused, as a decision
    # is, so nothing new is written for them (a grant created now would outlive the share purge).
    notes = count(db, "SELECT COUNT(*) FROM Notifications WHERE member_id=@m", m=m)
    grants = count(db, "SELECT COUNT(*) FROM ShareGrants WHERE @m IN UNNEST(recipient_ids)", m=m)
    with pytest.raises(DetailedInvalidTransition) as e:
        ShareService(db).create(friend, {"subject_type": "wardrobe_item", "subject_id": f_item, "audience": "selected_members",
                                         "allowed_fields": ["title"], "recipient_ids": [m], "expires_at": "2027-01-01T00:00:00+00:00"}, key())
    assert e.value.code == "ineligible_recipients"
    assert count(db, "SELECT COUNT(*) FROM Notifications WHERE member_id=@m", m=m) == notes
    assert count(db, "SELECT COUNT(*) FROM ShareGrants WHERE @m IN UNNEST(recipient_ids)", m=m) == grants

    receipt = svc.run_deletion(job)
    assert {k: r["status"] for k, r in receipt["categories"].items()} == {k: "deleted" for k in inventory}
    assert svc.run_deletion(job) == receipt
    assert remaining(db, m) == {}
    assert traces(db, m) == {}  # no lane column anywhere still holds the member id
    # Reports about the member stay for moderation history, unlinked from them.
    assert count(db, "SELECT COUNT(*) FROM MemberReports WHERE reporter_id=@f AND target_owner_id=@nil", f=friend.member_id, nil=NIL_MEMBER) == 2
    assert [r for r in store.objects if r.startswith(f"members/{m}/")] == []
    # The benefit unit is back, and the friend's decision keeps its count-only result.
    assert count(db, "SELECT inventory_reserved FROM Benefits WHERE benefit_id=@b", b=benefit["benefit_id"]) == 0
    got = DecisionService(db).get(friend, theirs["decision_id"])
    assert got["responses"] == [] and got["decision_id"] == theirs["decision_id"]
    # Account scope: the member stays frozen after completion.
    frozen(lambda: WardrobeService(db).create_items(gone, {"source": "manual", "title": "Hat", "category": "accessory"}, key()))

    # Restore from the older backup brings rows and blobs back; the tombstones remove them again.
    for table, (cols, data) in backup.items():
        run_txn(db, lambda t, table=table, cols=cols, data=data: t.insert(table, columns=cols, values=data))
    store.objects.update(blobs)
    assert set(remaining(db, m)) == {"PersonaProfiles", "WardrobeItems", "MediaObjects"}
    restored = svc.reapply_tombstones_after_restore("dev-backup-before-deletion", backup_at)
    assert restored["tombstones_applied"] == len(inventory)
    assert restored["rows_redeleted"] > 0  # media rows are tombstoned here and purged with their blobs
    assert remaining(db, m) == {} and traces(db, m) == {}
    assert [r for r in store.objects if r.startswith(f"members/{m}/")] == []
    svc.assert_serving()


def test_record_scoped_requests_are_refused_not_widened(db):
    m = member_principal(insert_member(db), WRITER)
    WardrobeService(db).create_items(m, {"source": "manual", "title": "Coat", "category": "top"}, key())
    ctx = pd.SubjectContext(subject_ref=m.member_id, job_id=str(uuid.uuid4()), requested_at=now(), record_keys=("one-record",))

    class Untouched:  # a refused request must not read or write anything
        def __getattr__(self, name):
            raise AssertionError(f"transaction used: {name}")

    for handler in consumer_privacy_handlers():
        for cat in handler.categories():
            out = handler.delete(Untouched(), ctx, cat.key)
            assert (out.rows_affected, out.done, out.exception) == (0, True, WHOLE_CATEGORY_ONLY), cat.key
            tomb = pd.Tombstone(m.member_id, cat.key, "t", "j", ("one-record",), now())
            assert handler.reapply_tombstone(Untouched(), tomb) == 0
    assert count(db, "SELECT COUNT(*) FROM WardrobeItems WHERE member_id=@m", m=m.member_id) == 1
