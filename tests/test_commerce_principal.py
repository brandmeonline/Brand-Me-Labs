"""S8: commerce on the foundation Principal, event registry and data categories.

* first-party = session without delegation; it acts as the member, so profile-only
  session scopes still allow the member's own commerce actions;
* an agent is resolved to its one active delegation for (member, client);
  scopes are the intersection of token scopes and delegation scopes;
* ``simulated`` assurance approves only simulated providers in local environments;
* every outbox row is a foundation ``EventEnvelope`` that validates.
"""

from dataclasses import replace
from datetime import timedelta

import pytest

from brandme_core.domains.base import Principal
from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.domains.commerce.errors import (
    ApprovalInvalid, DelegationConflict, DelegationInvalid, Forbidden, InvalidRequest,
)
from brandme_core.domains.commerce.principal import is_agent, is_first_party, meets_assurance
from brandme_core.domains.providers.local_atelier import MERCHANT_ID, PROVIDER_ID
from brandme_core.events import EventEnvelope, registry
from tests.fixtures.commerce.stores import commerce_store, _spanner_db  # noqa: F401  (fixtures)
from tests.fixtures.commerce.harness import AGENT_CLIENT, MEMBER, agent, limits, line, member_session, world
from tests.fixtures.commerce.harness import OTHER_MEMBER as OTHER_MEMBER_ID


@pytest.fixture
def w(commerce_store):
    return world(store=commerce_store)


def test_first_party_rule():
    assert is_first_party(member_session())
    bearer = replace(member_session(), session_id=None)
    assert is_agent(bearer)
    # A session that carries a delegation is acting for an agent, not as the member.
    assert is_agent(replace(member_session(), delegation_id="d"))


def test_profile_only_session_can_buy_for_itself(w):
    assert w.member.scopes == {"profile:read", "profile:write", "privacy:manage"}
    _, quote, op = w.prepared(w.member)
    approval = w.approve(op)
    done = w.svc.execute_purchase(w.member, operation_id=op.id, approval_id=approval.id,
                                  idempotency_key="member-own-0000001")
    assert done.state == "accepted" and approval.delegation_ref is None


def test_agent_without_delegation_id_is_resolved(w):
    d, _ = w.delegate()
    unbound = agent(None, d.scopes)
    bound = w.svc.bind(unbound)
    assert bound.delegation_id == d.id
    _, _, op = w.prepared(unbound)
    assert op.delegation_id == d.id  # recorded against the resolved grant
    approval = w.approve(op)
    assert approval.delegation_ref == d.id
    done = w.svc.execute_purchase(unbound, operation_id=op.id, approval_id=approval.id,
                                  idempotency_key="resolved-0000000001")
    assert done.state == "accepted"


def test_agent_with_no_grant_is_refused(w):
    with pytest.raises(DelegationInvalid) as e:
        w.svc.create_cart(agent(None, {"commerce:cart"}), provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID,
                          lines=[line()])
    assert e.value.code == "delegation_required"
    nameless = Principal(member_id=MEMBER, subject="s", session_id=None, client_id=None,
                         scopes=frozenset({"commerce:cart"}), assurance_level="aal1", environment="development")
    with pytest.raises(DelegationInvalid):
        w.svc.bind(nameless)


def test_other_clients_grant_is_not_borrowed(w):
    d, _ = w.delegate()
    with pytest.raises(DelegationInvalid):
        w.svc.bind(agent(None, d.scopes, client="client-some-other-agent"))
    with pytest.raises(DelegationInvalid):  # naming someone else's delegation id does not help either
        w.svc.bind(agent(d.id, d.scopes, client="client-some-other-agent"))


def test_one_active_delegation_per_member_and_client(w):
    d, _ = w.delegate(AssistanceMode.PREPARE)
    with pytest.raises(DelegationConflict) as e:
        w.delegate(AssistanceMode.BUY_WITHIN_RULES)
    assert e.value.status == 409
    w.svc.revoke_delegation(w.member, d.id)
    d2, _ = w.delegate(AssistanceMode.BUY_WITHIN_RULES)
    assert w.svc.bind(agent(None, d2.scopes)).delegation_id == d2.id
    # A different client may hold its own grant at the same time.
    other = w.svc.create_delegation(w.member, client_id="client-second-agent", mode=AssistanceMode.RESEARCH,
                                    allowed_providers={PROVIDER_ID}, limits=None,
                                    expires_at=w.clock.now + timedelta(days=1))
    assert other.client_id == "client-second-agent"


def test_concurrent_grants_for_one_client_cannot_both_win(w):
    import threading
    results, errors = [], []

    def grant():
        try:
            results.append(w.svc.create_delegation(
                w.member, client_id=AGENT_CLIENT, mode=AssistanceMode.RESEARCH, allowed_providers={PROVIDER_ID},
                limits=None, expires_at=w.clock.now + timedelta(days=1)))
        except DelegationConflict as exc:
            errors.append(exc)

    threads = [threading.Thread(target=grant) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(results) == 1 and len(errors) == 5
    assert len(w.store.active_delegations(MEMBER, AGENT_CLIENT, w.clock.now)) == 1


def test_expired_grant_frees_the_slot(w):
    d, _ = w.delegate(AssistanceMode.RESEARCH)
    w.clock.advance(days=8)
    with pytest.raises(DelegationInvalid):
        w.svc.bind(agent(None, d.scopes))
    d2, _ = w.delegate(AssistanceMode.RESEARCH)
    assert d2.id != d.id


def test_agents_cannot_grant_or_revoke(w):
    d, ag = w.delegate()
    for fn in (lambda: w.svc.create_delegation(ag, client_id=AGENT_CLIENT, mode=AssistanceMode.RESEARCH,
                                               allowed_providers={PROVIDER_ID}, limits=None,
                                               expires_at=w.clock.now + timedelta(days=1)),
               lambda: w.svc.revoke_delegation(ag, d.id)):
        with pytest.raises(Forbidden) as e:
            fn()
        assert e.value.code == "not_trusted_surface"


def test_agent_scope_is_token_and_grant_intersection(w):
    d, _ = w.delegate(AssistanceMode.PREPARE)
    # Token claims purchase, but the prepare grant does not include it.
    over = agent(None, d.scopes | {"commerce:purchase"})
    _, _, op = w.prepared(over)
    approval = w.approve(op)
    with pytest.raises(Forbidden) as e:
        w.svc.execute_purchase(over, operation_id=op.id, approval_id=approval.id,
                               idempotency_key="intersect-00000001")
    assert e.value.code == "insufficient_scope"
    # Grant includes cart, but the token does not.
    narrow = agent(None, {"commerce:research"})
    with pytest.raises(Forbidden):
        w.svc.create_cart(narrow, provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID, lines=[line()])


def test_simulated_assurance_rules():
    sim = member_session(aal="simulated")
    assert meets_assurance(sim, "aal2", simulation_ok=True)
    assert not meets_assurance(sim, "aal2", simulation_ok=False)
    assert not meets_assurance(member_session(aal="simulated", environment="sandbox"), "aal2", simulation_ok=True)
    assert not meets_assurance(member_session(aal="simulated", environment="production"), "aal2",
                               simulation_ok=True)
    assert meets_assurance(member_session(aal="aal2", environment="production"), "aal2", simulation_ok=False)
    assert not meets_assurance(member_session(aal="aal1"), "aal2", simulation_ok=True)


def test_simulated_member_can_approve_only_simulated_provider(w):
    sim = member_session(aal="simulated")
    _, _, op = w.prepared(sim)
    ch = w.svc.open_approval_challenge(sim, op.id)
    approval = w.svc.approve(sim, operation_id=op.id, challenge_id=ch.id, nonce=ch.nonce,
                             displayed_quote_hash=ch.quote_hash)
    assert approval.assurance_level == "simulated"

    _, _, op2 = w.prepared(sim, line("trousers"))
    ch2 = w.svc.open_approval_challenge(sim, op2.id)
    w.registry.get(PROVIDER_ID).simulation = False  # same flow against a non-simulation provider
    with pytest.raises(ApprovalInvalid) as e:
        w.svc.approve(sim, operation_id=op2.id, challenge_id=ch2.id, nonce=ch2.nonce,
                      displayed_quote_hash=ch2.quote_hash)
    assert e.value.code == "reauthentication_required"


def test_simulated_identity_cannot_register_ap2_device_key(w):
    from jwcrypto.jwk import JWK
    pub = JWK.generate(kty="EC", crv="P-256").export_public(as_dict=True)
    with pytest.raises(Forbidden) as e:
        w.svc.register_surface_key(member_session(aal="simulated"), pub)
    assert e.value.code == "reauthentication_required"
    assert w.svc.register_surface_key(w.member, pub)


def test_environment_mismatch_refused(w):
    with pytest.raises(Forbidden):
        w.svc.create_cart(member_session(environment="sandbox"), provider_id=PROVIDER_ID,
                          merchant_id=MERCHANT_ID, lines=[line()])


def test_idempotency_key_length_follows_foundation_contract(w):
    with pytest.raises(InvalidRequest) as e:
        w.svc.create_cart(w.member, provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID, lines=[line()],
                          idempotency_key="short")
    assert e.value.code == "idempotency_key_invalid" and e.value.status == 400
    with pytest.raises(InvalidRequest):
        w.svc.create_cart(w.member, provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID, lines=[line()],
                          idempotency_key="x" * 129)


def test_idempotency_is_scoped_to_actor_including_delegation(w):
    d, ag = w.delegate(AssistanceMode.PREPARE)
    key = "shared-key-0000000001"
    a = w.svc.create_cart(ag, provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID, lines=[line()],
                          idempotency_key=key)
    b = w.svc.create_cart(w.member, provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID, lines=[line()],
                          idempotency_key=key)
    assert a.id != b.id  # same key, different actor_ref: independent operations
    assert w.svc.create_cart(agent(None, d.scopes), provider_id=PROVIDER_ID, merchant_id=MERCHANT_ID,
                             lines=[line()], idempotency_key=key).id == a.id


def test_outbox_rows_are_validated_foundation_envelopes(w):
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    approval = w.approve(op)
    w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="envelope-0000000001")
    w.svc.revoke_delegation(w.member, d.id)
    events = w.store.outbox()
    types = [e.event_type for e in events]
    assert types == ["commerce.delegation.created", "commerce.quote.ready",
                     "commerce.purchase.approval_requested", "commerce.purchase.authorized",
                     "commerce.order.observed", "commerce.delegation.revoked"]
    registered = {(t.event_type, t.schema_version) for t in registry.types()}
    for e in events:
        assert isinstance(e, EventEnvelope)
        assert (e.event_type, e.schema_version) in registered
        e.validate()
        assert e.privacy_class == "member_private" and e.environment == "development"
    by_type = {e.event_type: e for e in events}
    assert by_type["commerce.delegation.created"].actor_ref == f"member:{MEMBER}"
    assert by_type["commerce.quote.ready"].actor_ref == f"member:{MEMBER}/delegation:{d.id}"
    assert by_type["commerce.order.observed"].payload["wardrobe_effect"] == "incoming"


def test_event_payload_outside_schema_is_refused(w):
    from brandme_core.events.envelope import EventValidationError
    qid = "8a3c0f5e-6d1b-4e0f-9d6c-0b6f3f0c2a11"
    for payload in ({"quote_id": qid, "quote_hash": "sha256:" + "0" * 64, "cart_id": "not-a-uuid"},
                    {"quote_id": qid, "quote_hash": "sha256:" + "0" * 64, "cart_id": qid, "address": "x"}):
        with pytest.raises(EventValidationError):
            w.store.run(lambda tx: w.svc._event(tx, "commerce.quote.ready", "CheckoutQuote", qid, 1,
                                                w.member, payload))
    assert w.store.outbox() == []


def test_revoked_agent_cannot_read(w):
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    w.svc.revoke_delegation(w.member, d.id)
    with pytest.raises(DelegationInvalid):
        w.svc.get_operation(ag, op.id)
    assert w.svc.get_operation(w.member, op.id).state == "cancelled"


def test_buy_mode_limits_unchanged_by_binding(w):
    d, _ = w.delegate(lim=limits(per_order=1_000))
    from brandme_core.domains.commerce.errors import BudgetExceeded
    with pytest.raises(BudgetExceeded):
        w.prepared(agent(None, d.scopes))


def test_operator_queue_needs_operator_role_and_hides_members(w):
    from brandme_core.domains.providers.local_atelier import Behavior
    d, ag = w.delegate()
    _, _, op = w.prepared(ag)
    approval = w.approve(op)
    w.provider.arm(Behavior.TIMEOUT_AFTER_ACCEPT)
    res = w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id, idempotency_key="ops-queue-00000001")
    assert res.state == "outcome_unknown"
    with pytest.raises(Forbidden):
        w.svc.operator_queue(w.member)  # a member session is never an operator
    operator = Principal(member_id=OTHER_MEMBER_ID, subject="ops", session_id=None, client_id="ops-console",
                         scopes=frozenset({"commerce:operator"}), assurance_level="aal2", environment="development")
    q = w.svc.operator_queue(operator)
    assert [i["operation_id"] for i in q["outcome_unknown"]] == [res.id]
    assert MEMBER not in str(q)
    assert q["stale_submitting"] == [] and q["webhooks_pending"] == []
