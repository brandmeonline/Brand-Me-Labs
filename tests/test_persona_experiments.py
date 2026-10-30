"""Ultra plan 02 item 8: five experiment definitions, wired to a flag that
always answers the default arm until the founder approves a definition and
foundation's flag primitive exists."""

import pytest

from brandme_core.domains.persona import experiments as ex
from test_persona_harness import MEMBER_SCOPES, insert_member, spanner_db  # noqa: F401


@pytest.fixture(autouse=True)
def clean():
    yield
    ex.APPROVALS.clear()
    ex.install_primitive(None)


def test_five_definitions_with_defaults_built_and_nothing_running():
    defs = ex.definitions()
    assert set(defs) == {"closet_memory", "curator_verbosity", "the_reveal", "visitor_traces", "decision_thread_persistence"}
    for d in defs.values():
        assert d["default"] in d["built"] and set(d["built"]) <= set(d["arms"]) and len(d["arms"]) == 2
        assert d["metrics"] and d["guardrails"] and d["question"].endswith("?")
        assert d["approved"] is False and d["running"] is False
    assert all(ex.arm(e, "m-1") == ex.EXPERIMENTS[e].default for e in ex.EXPERIMENTS)


def test_only_an_approved_version_with_the_primitive_assigns_and_only_built_arms():
    always = lambda exp, version, member, built: built[-1]  # noqa: E731
    ex.install_primitive(always)
    assert ex.arm("decision_thread_persistence", "m-1") == "persist"  # no approval yet
    ex.APPROVALS["decision_thread_persistence"] = 1
    assert ex.arm("decision_thread_persistence", "m-1") == "fade_after_close"
    ex.APPROVALS["decision_thread_persistence"] = 0  # approval of an older definition does not count
    assert ex.arm("decision_thread_persistence", "m-1") == "persist"
    ex.APPROVALS["the_reveal"] = 1
    ex.install_primitive(lambda *_: "anticipation_pause")  # not built: never served
    assert ex.arm("the_reveal", "m-1") == "instant"
    ex.install_primitive(None)
    ex.APPROVALS["decision_thread_persistence"] = 1
    assert ex.arm("decision_thread_persistence", "m-1") == "persist"  # approved but no primitive: off


def test_wired_flags_change_behaviour_only_when_approved_and_assigned(spanner_db):  # noqa: F811
    import uuid

    from brandme_core.domains.persona.kernel import member_principal
    from brandme_core.domains.social.decisions import DecisionService
    from brandme_core.domains.social.relationships import RelationshipService
    from brandme_core.domains.wardrobe.service import WardrobeService

    owner, friend = (member_principal(insert_member(spanner_db), MEMBER_SCOPES) for _ in range(2))
    rel = RelationshipService(spanner_db)
    rel.accept(friend, rel.request(owner, friend.member_id)["relationship_id"])
    item = WardrobeService(spanner_db).create_items(owner, {"source": "manual", "title": "Coat", "category": "outerwear"},
                                                    "k-" + uuid.uuid4().hex)["items"][0]["id"]
    svc = DecisionService(spanner_db)
    d = svc.create(owner, {"subject_type": "wardrobe_item", "subject_id": item, "prompt": "Coat?", "recipient_ids": [friend.member_id],
                           "discussion_mode": "open"}, "k-" + uuid.uuid4().hex)
    svc.add_comment(friend, d["decision_id"], {"body": "Yes, the long one"}, "k-" + uuid.uuid4().hex)
    svc.close(owner, d["decision_id"])
    assert len(svc.comments(owner, d["decision_id"])["items"]) == 1  # default: the thread persists
    ex.install_primitive(lambda exp, version, member, built: "fade_after_close")
    assert len(svc.comments(owner, d["decision_id"])["items"]) == 1  # assigned but not approved: still default
    ex.APPROVALS["decision_thread_persistence"] = 1
    assert svc.comments(owner, d["decision_id"]) == {"decision_id": d["decision_id"], "items": [], "hidden_until_you_answer": False, "faded": True}
