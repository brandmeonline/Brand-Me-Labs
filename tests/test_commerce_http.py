"""S11: the commerce domain's internal HTTP API (gateway → domain hop), unmounted.

Real ES256 gateway assertions, FastAPI TestClient, deterministic simulated provider.
"""

import base64
import json
import time
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.domains.commerce.http_api import ASSISTANT_CLIENT_ID, PREFIX, CommerceHttpApi, create_commerce_app
from brandme_core.domains.providers.local_atelier import MERCHANT_ID, PROVIDER_ID
from brandme_core.mcp.authz import DOMAIN_AUDIENCE, EXECUTOR_AUDIENCE, ExecutorAssertionVerifier, sign_executor_assertion
from brandme_core.mcp.tools import McpToolExecutor
from brandme_core.orchestrator import AssistantRuntime, DeterministicPlanner
from tests.fixtures.commerce.harness import AGENT_CLIENT, MEMBER, line, world

GW = "https://gateway.example.invalid"


class Http:
    def __init__(self):
        self.w = world()
        self.key = ec.generate_private_key(ec.SECP256R1())
        verifier = ExecutorAssertionVerifier(gateway_issuer=GW, keys={"gw-1": self.key.public_key()},
                                             environment="development", audience=DOMAIN_AUDIENCE, allow_session=True)
        mcp = McpToolExecutor(commerce=self.w.svc, registry=self.w.registry, verifier=ExecutorAssertionVerifier(
            gateway_issuer=GW, keys={"gw-1": self.key.public_key()}, environment="development"))
        self.runtime = AssistantRuntime(mcp, environment="development")
        self.api = CommerceHttpApi(service=self.w.svc, verifier=verifier, runtime=self.runtime,
                                   planner_factory=DeterministicPlanner)
        self.client = TestClient(create_commerce_app(self.api))

    def assertion(self, principal, audience=DOMAIN_AUDIENCE):
        return sign_executor_assertion(private_key=self.key, kid="gw-1", gateway_issuer=GW, principal=principal,
                                       jti=uuid.uuid4().hex, audience=audience)

    @staticmethod
    def session(**over):
        return {"member_id": MEMBER, "subject": MEMBER, "session_id": "a1b2c3d4e5f60718", "client_id": None,
                "scopes": ["profile:read", "profile:write", "privacy:manage"], "assurance_level": "aal2",
                "environment": "development", "delegation_id": None, "identity_provider": "dev", **over}

    @staticmethod
    def bearer(scopes, **over):
        return {"member_id": MEMBER, "subject": "sub-agent", "session_id": None, "client_id": AGENT_CLIENT,
                "scopes": list(scopes), "assurance_level": "aal1", "environment": "development",
                "delegation_id": None, "identity_provider": "oidc", **over}

    def call(self, op, body=None, principal=None, headers=None, audience=DOMAIN_AUDIENCE):
        h = {"Authorization": "Bearer " + self.assertion(principal or self.session(), audience), **(headers or {})}
        return self.client.post(f"{PREFIX}/{op}", content=json.dumps(body or {}), headers=h)


@pytest.fixture
def h():
    return Http()


def _line():
    l = line()
    return {"variant_id": l.variant_id, "source_variant_ref": l.source_variant_ref, "quantity": l.quantity}


def _quote(h, principal=None):
    r = h.call("cart.create", {"provider_id": PROVIDER_ID, "merchant_id": MERCHANT_ID, "lines": [_line()]},
               principal, {"Idempotency-Key": "http-cart-0000000001"})
    assert r.status_code == 201, r.text
    cart = r.json()
    assert r.headers["etag"] == '"1"'
    q = h.call("cart.quote", {"cart_id": cart["id"]}, principal)
    assert q.status_code == 200, q.text
    return cart, q.json()


def _approve(h, op_id):
    ch = h.call("approval.challenge", {"operation_id": op_id})
    assert ch.status_code == 201, ch.text
    c = ch.json()
    a = h.call("approval.create", {"operation_id": op_id, "challenge_id": c["id"], "nonce": c["nonce"],
                                   "displayed_quote_hash": c["quote_hash"]})
    assert a.status_code == 201, a.text
    return a.json()


def test_member_session_buys_for_itself_end_to_end(h):
    cart, quote = _quote(h)
    op = h.call("purchase.request", {"quote_id": quote["id"]}).json()
    assert op["state"] == "awaiting_approval"
    approval = _approve(h, op["id"])
    assert approval["quote_hash"] == quote["quote_hash"] and "nonce" not in approval
    r = h.call("purchase.execute", {"quote_id": quote["id"], "approval_id": approval["id"], "delegation_id": None},
               headers={"Idempotency-Key": "http-exec-0000000001"})
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["state"] == "accepted" and r.headers["cache-control"] == "private, no-store"
    order = h.call("order.get", {"order_id": done["order_id"]}).json()
    assert order["order_status"] == "accepted" and order["total"] == quote["total"]


def test_agent_bearer_resolves_grant_and_member_approves(h):
    d, _ = h.w.delegate()
    agent = h.bearer(d.scopes)  # no delegation_id: the domain resolves (member, client)
    _, quote = _quote(h, agent)
    op = h.call("purchase.request", {"quote_id": quote["id"]}, agent).json()
    assert op["delegation_id"] == d.id
    refused = h.call("approval.challenge", {"operation_id": op["id"]}, agent)
    assert refused.status_code == 403 and refused.json()["code"] == "not_trusted_surface"
    approval = _approve(h, op["id"])
    mismatch = h.call("purchase.execute", {"quote_id": quote["id"], "approval_id": approval["id"], "delegation_id": None},
                      agent, {"Idempotency-Key": "http-exec-0000000002"})
    assert mismatch.status_code == 403 and mismatch.json()["code"] == "delegation_mismatch"
    ok = h.call("purchase.execute", {"quote_id": quote["id"], "approval_id": approval["id"], "delegation_id": d.id},
                agent, {"Idempotency-Key": "http-exec-0000000003"})
    assert ok.status_code == 200 and ok.json()["state"] == "accepted"


def test_audiences_are_not_interchangeable(h):
    r = h.call("operation.get", {"operation_id": str(uuid.uuid4())}, audience=EXECUTOR_AUDIENCE)
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json")
    with pytest.raises(ValueError):
        ExecutorAssertionVerifier(gateway_issuer=GW, keys={}, environment="development", allow_session=True)
    no_auth = h.client.post(f"{PREFIX}/delegation.list", content="{}")
    assert no_auth.status_code == 401


def test_identity_fields_and_unknown_operations_rejected(h):
    r = h.call("cart.quote", {"cart_id": str(uuid.uuid4()), "member_id": MEMBER})
    assert r.status_code == 400 and r.json()["code"] == "unexpected_field"
    assert h.call("purchase.approve_for_me", {}).status_code == 404


def test_cart_update_requires_if_match(h):
    cart, _ = _quote(h)
    r = h.call("cart.update", {"cart_id": cart["id"], "lines": [_line()]})
    assert r.status_code == 428 and r.json()["code"] == "if_match_required"
    stale = h.call("cart.update", {"cart_id": cart["id"], "lines": [_line()]}, headers={"If-Match": '"7"'})
    assert stale.status_code == 409 and stale.json()["code"] == "revision_conflict"
    ok = h.call("cart.update", {"cart_id": cart["id"], "lines": [_line()]}, headers={"If-Match": '"1"'})
    assert ok.status_code == 200 and ok.headers["etag"] == '"2"'


def test_short_idempotency_key_rejected(h):
    r = h.call("cart.create", {"provider_id": PROVIDER_ID, "merchant_id": MERCHANT_ID, "lines": [_line()]},
               headers={"Idempotency-Key": "short"})
    assert r.status_code == 400 and r.json()["code"] == "idempotency_key_invalid"


def test_delegations_are_first_party_only(h):
    expires = "2026-10-12T12:00:00Z"
    created = h.call("delegation.create", {"client_id": AGENT_CLIENT, "mode": "research",
                                           "allowed_providers": [PROVIDER_ID], "expires_at": expires})
    assert created.status_code == 201, created.text
    again = h.call("delegation.create", {"client_id": AGENT_CLIENT, "mode": "research",
                                         "allowed_providers": [PROVIDER_ID], "expires_at": expires})
    assert again.status_code == 409 and again.json()["code"] == "active_delegation_exists"
    listed = h.call("delegation.list").json()["items"]
    assert [d["id"] for d in listed] == [created.json()["id"]]
    agent = h.bearer(["commerce:research"])
    assert h.call("delegation.list", principal=agent).status_code == 403
    assert h.call("delegation.revoke", {"delegation_id": created.json()["id"]}, agent).status_code == 403
    revoked = h.call("delegation.revoke", {"delegation_id": created.json()["id"]}).json()
    assert revoked["revoked_at"] is not None


def test_buy_grant_limits_round_trip(h):
    body = {"client_id": AGENT_CLIENT, "mode": "buy_within_rules", "allowed_providers": [PROVIDER_ID],
            "expires_at": "2026-10-12T12:00:00Z",
            "limits": {"currency": "USD", "max_per_order": {"amount_minor": "20000", "currency": "USD"},
                       "max_cumulative": {"amount_minor": "30000", "currency": "USD"}, "window_seconds": 86400,
                       "allowed_merchants": [MERCHANT_ID]}}
    r = h.call("delegation.create", body)
    assert r.status_code == 201, r.text
    assert r.json()["limits"]["max_per_order"] == {"amount_minor": "20000", "currency": "USD"}
    autonomous = dict(body, client_id="client-other", limits=dict(body["limits"], require_final_human_approval=False))
    refused = h.call("delegation.create", autonomous)
    assert refused.status_code == 403 and refused.json()["code"] == "autonomous_not_supported"


def test_provider_console_requires_operator_role_and_never_shows_secrets(h):
    assert h.call("provider.list").status_code == 403  # a member session is not an operator
    admin = h.bearer(["provider:admin"], client_id="ops-console")
    listed = h.call("provider.list", principal=admin)
    assert listed.status_code == 200
    text = listed.text
    assert "credential_ref" not in text and "operator_account_ref" not in text
    detail = h.call("provider.get", {"provider_id": PROVIDER_ID}, admin).json()
    assert detail["simulation"] is True and detail["credential_configured"] is False
    health = h.call("provider.health", {"provider_id": PROVIDER_ID}, admin).json()
    assert "checkout.submit" in health["executable"]
    setup = h.call("provider.setup.get", {"provider_id": PROVIDER_ID}, admin).json()
    assert setup["editable"] is True and setup["simulation"] is True
    assert [s["key"] for s in setup["sections"]] == ["enables", "prerequisites", "credentials", "data_use", "tests",
                                                    "activation"]
    r = h.call("provider.setup.update", {"provider_id": PROVIDER_ID, "access_level": "approved_publisher"}, admin)
    assert r.status_code == 400 and r.json()["code"] == "setup_field_not_applicable"  # a simulation has no access levels
    assert h.call("provider.get", {"provider_id": "nordstrom_api"}, admin).status_code == 404
    assert h.call("provider.setup.get", {"provider_id": "nordstrom_api"}, admin).status_code == 404


SECRET_REF = "projects/brandme-dev-fictional/secrets/impact-publisher/versions/3"


def test_provider_setup_and_connection_tests_over_http(h):
    from brandme_core.domains.providers import nordstrom
    h.w.registry.register(nordstrom.connection("development"))
    admin = h.bearer(["provider:admin"], client_id="ops-console")
    for op, body in (("provider.verify", {"provider_id": PROVIDER_ID, "capability": "catalog.search",
                                          "mode": "read_only_test"}),
                     ("provider.setup.update", {"provider_id": "nordstrom_impact", "program_application_opened": True}),
                     ("provider.runs", {"provider_id": PROVIDER_ID})):
        assert h.call(op, body).status_code == 403  # the member session is not an operator
    run = h.call("provider.verify", {"provider_id": PROVIDER_ID, "capability": "catalog.search",
                                     "mode": "read_only_test"}, admin)
    assert run.status_code == 201 and run.headers["cache-control"] == "private, no-store"
    body = run.json()
    assert body["result"] == "passed" and body["capability_state"]["state"] == "sandbox"
    assert {"ran_at", "environment", "capability", "sanitized_summary", "evidence_ref"} <= set(body)
    runs = h.call("provider.runs", {"provider_id": PROVIDER_ID, "capability": "catalog.search"}, admin).json()
    assert [r["run_id"] for r in runs["items"]] == [body["run_id"]]
    bad = h.call("provider.verify", {"provider_id": PROVIDER_ID, "capability": "checkout.buy_now",
                                     "mode": "read_only_test"}, admin)
    assert bad.status_code == 400 and bad.json()["code"] == "unknown_capability"
    refused = h.call("provider.setup.update", {"provider_id": PROVIDER_ID, "activate": "price.quote"}, admin)
    assert refused.status_code == 409 and refused.json()["code"] == "activation_test_required"
    assert refused.headers["content-type"].startswith("application/problem+json")
    activated = h.call("provider.setup.update", {"provider_id": PROVIDER_ID, "activate": "catalog.search"}, admin)
    assert activated.status_code == 200
    items = {i["key"]: i for s in activated.json()["sections"] for i in s["items"]}
    assert items["activate:catalog.search"]["state"] == "done"

    secret = h.call("provider.setup.update", {"provider_id": "nordstrom_impact",
                                              "credential_secret_ref": "sk_live_51Hfictionalfictional"}, admin)
    assert secret.status_code == 400 and secret.json()["code"] == "secret_value_refused"
    assert "sk_live" not in secret.text
    ok = h.call("provider.setup.update", {"provider_id": "nordstrom_impact", "credential_secret_ref": SECRET_REF},
                admin, {"If-Match": '"0"'})
    assert ok.status_code == 200 and ok.json()["credential_configured"] is True
    assert SECRET_REF not in ok.text and "impact-publisher" not in ok.text
    stale = h.call("provider.setup.update", {"provider_id": "nordstrom_impact", "account_ref": "fictional-account"},
                   admin, {"If-Match": '"0"'})
    assert stale.status_code == 409 and stale.json()["code"] == "revision_conflict"
    injected = h.call("provider.setup.update", {"provider_id": "nordstrom_impact",
                                                "capabilities": {"catalog.feed": "verified"}}, admin)
    assert injected.status_code == 400 and injected.json()["code"] == "unexpected_field"
    gated = h.call("provider.verify", {"provider_id": "nordstrom_impact", "capability": "catalog.feed",
                                       "mode": "read_only_test"}, admin).json()
    assert gated["result"] == "blocked" and gated["reason_code"] == "publisher_approval_required"
    health = h.call("provider.health", {"provider_id": "nordstrom_impact"}, admin).json()
    assert health["executable"] == []  # configured is not verified


def test_capabilities_summary_is_honest_about_simulation(h):
    items = h.call("capabilities.effective").json()["items"]
    checkout = items[0]
    assert checkout["name"] == "commerce.checkout" and checkout["state"] == "simulated"
    assert checkout["simulation_label"]
    assert all(i["state"] in ("available", "simulated", "unconfigured", "unsupported", "degraded") for i in items)


def test_catalog_search_and_product_detail(h):
    res = h.call("catalog.search", {"q": "overshirt", "limit": 5}).json()
    item = res["items"][0]
    assert item["price_is_quote"] is False and item["title"]["type"] == "untrusted_text"
    product = h.call("catalog.product", {"product_id": f"{item['provider_id']}:{item['source_product_id']}"})
    assert product.status_code == 200 and product.json()["variants"]
    assert h.call("catalog.product", {"product_id": "nope"}).status_code == 404


def test_assistant_needs_a_grant_to_the_brandme_assistant(h):
    r = h.call("assistant.task.create", {"goal": "linen overshirt", "assistance_mode": "research"})
    assert r.status_code == 403 and r.json()["code"] == "delegation_required"
    h.w.svc.create_delegation(h.w.member, client_id=ASSISTANT_CLIENT_ID, mode=AssistanceMode.RESEARCH,
                              allowed_providers={PROVIDER_ID}, limits=None,
                              expires_at=h.w.clock.now.replace(day=12))
    task = h.call("assistant.task.create", {"goal": "linen overshirt", "assistance_mode": "research"})
    assert task.status_code == 201, task.text
    assert task.json()["state"] == "completed"
    events = h.call("assistant.task.events", {"task_id": task.json()["id"]}).json()["events"]
    assert any(e["type"] == "finding" for e in events)
    wrong_mode = h.call("assistant.task.create", {"goal": "buy it", "assistance_mode": "buy_within_rules"})
    assert wrong_mode.status_code == 403


def _service_headers(h):
    return {"Authorization": "Bearer " + h.assertion(None)}


def test_webhook_needs_service_assertion_and_provider_signature(h):
    d, ag = h.w.delegate()
    _, _, op = h.w.prepared(ag)
    approval = h.w.approve(op)
    res = h.w.svc.execute_purchase(ag, operation_id=op.id, approval_id=approval.id,
                                   idempotency_key="http-hook-0000000001")
    order = h.w.store.get("orders", res.order_id)
    headers, body = h.w.provider.capture(order.provider_order_ref)[0]
    envelope = json.dumps({"headers": headers, "body_b64": base64.b64encode(body).decode()})
    url = f"{PREFIX}/webhooks/{PROVIDER_ID}"
    as_member = h.client.post(url, content=envelope, headers={"Authorization": "Bearer " + h.assertion(h.session())})
    assert as_member.status_code == 401
    ok = h.client.post(url, content=envelope, headers=_service_headers(h))
    assert ok.status_code == 200 and ok.json()["received"] is True
    assert h.w.store.get("orders", order.id).payment_status == "captured"
    forged = json.dumps({"headers": headers, "body_b64": base64.b64encode(body.replace(b"payment", b"pAyment")).decode()})
    bad = h.client.post(url, content=forged, headers=_service_headers(h))
    assert bad.status_code == 400 and bad.json()["code"] == "webhook_rejected"


def test_expired_or_replayed_assertion_rejected(h):
    token = sign_executor_assertion(private_key=h.key, kid="gw-1", gateway_issuer=GW, principal=h.session(),
                                    jti="replay-0000000000000001", audience=DOMAIN_AUDIENCE)
    url = f"{PREFIX}/delegation.list"
    assert h.client.post(url, content="{}", headers={"Authorization": "Bearer " + token}).status_code == 200
    assert h.client.post(url, content="{}", headers={"Authorization": "Bearer " + token}).status_code == 401
    old = sign_executor_assertion(private_key=h.key, kid="gw-1", gateway_issuer=GW, principal=h.session(),
                                  jti=uuid.uuid4().hex, audience=DOMAIN_AUDIENCE, now=int(time.time()) - 3600)
    assert h.client.post(url, content="{}", headers={"Authorization": "Bearer " + old}).status_code == 401


def test_assertion_shape_matches_the_published_schema(h):
    import jsonschema
    import jwt
    from pathlib import Path
    schema = json.loads((Path(__file__).resolve().parents[1] / "brandme_core/mcp/schemas/domain_assertion.schema.json")
                        .read_text())
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    for principal in (h.session(), h.bearer(["commerce:cart"]), None):
        claims = jwt.decode(h.assertion(principal), options={"verify_signature": False})
        assert not list(v.iter_errors(claims)), principal


def test_return_idempotency_key_reaches_the_domain(h):
    _, quote = _quote(h)
    op = h.call("purchase.request", {"quote_id": quote["id"]}).json()
    approval = _approve(h, op["id"])
    done = h.call("purchase.execute", {"quote_id": quote["id"], "approval_id": approval["id"], "delegation_id": None},
                  headers={"Idempotency-Key": "http-exec-0000000009"}).json()
    order = h.w.store.get("orders", done["order_id"])
    h.w.svc.handle_webhook(PROVIDER_ID, *h.w.provider.ship(order.provider_order_ref)[0])
    body = {"order_id": done["order_id"], "source_variant_ref": "demo-overshirt-m", "quantity": 1}
    first = h.call("order.return", body, headers={"Idempotency-Key": "http-return-000000001"})
    again = h.call("order.return", body, headers={"Idempotency-Key": "http-return-000000001"})
    assert first.status_code == again.status_code == 202
    assert first.json()["return_id"] == again.json()["return_id"] and len(h.w.provider.return_calls) == 1


def test_gateway_request_id_correlates_domain_events(h):
    rid = "0b7c3f2e-9d41-4e6a-8f15-2c9a4d7e1b33"
    r = h.call("cart.create", {"provider_id": PROVIDER_ID, "merchant_id": MERCHANT_ID, "lines": [_line()]},
               headers={"Idempotency-Key": "http-corr-0000000001", "X-Request-Id": rid})
    q = h.call("cart.quote", {"cart_id": r.json()["id"]}, headers={"X-Request-Id": rid})
    assert q.status_code == 200, q.text
    ready = [e for e in h.w.store.outbox() if e.event_type == "commerce.quote.ready"]
    assert [e.correlation_id for e in ready] == [rid]
    # A request id that is not a UUID is ignored (a fresh correlation id, never the raw header).
    h.call("cart.quote", {"cart_id": r.json()["id"]}, headers={"X-Request-Id": "not-a-uuid; drop table"})
    latest = [e for e in h.w.store.outbox() if e.event_type == "commerce.quote.ready"][-1]
    uuid.UUID(latest.correlation_id)


def test_assistant_task_create_is_idempotent(h):
    h.w.svc.create_delegation(h.w.member, client_id=ASSISTANT_CLIENT_ID, mode=AssistanceMode.RESEARCH,
                              allowed_providers={PROVIDER_ID}, limits=None,
                              expires_at=h.w.clock.now.replace(year=2027))
    body = {"goal": "linen overshirt", "assistance_mode": "research"}
    key = {"Idempotency-Key": "task-create-00000001"}
    first = h.call("assistant.task.create", body, headers=key)
    again = h.call("assistant.task.create", body, headers=key)  # e.g. the gateway timed out and the client retried
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    events = h.call("assistant.task.events", {"task_id": first.json()["id"]}).json()["events"]
    assert [e["type"] for e in events].count("goal") == 1
    clash = h.call("assistant.task.create", {"goal": "something else", "assistance_mode": "research"}, headers=key)
    assert clash.status_code == 409 and clash.json()["code"] == "idempotency_key_reused"


def test_cancellation_reaches_the_domain_once_per_key(h):
    _, quote = _quote(h)
    op = h.call("purchase.request", {"quote_id": quote["id"]}).json()
    approval = _approve(h, op["id"])
    done = h.call("purchase.execute", {"quote_id": quote["id"], "approval_id": approval["id"], "delegation_id": None},
                  headers={"Idempotency-Key": "http-exec-0000000010"}).json()
    body = {"order_id": done["order_id"]}
    first = h.call("order.cancel", body, headers={"Idempotency-Key": "http-cancel-000000001"})
    again = h.call("order.cancel", body, headers={"Idempotency-Key": "http-cancel-000000001"})
    assert first.status_code == again.status_code == 202
    assert first.json() == again.json() and first.json()["status"] == "cancelled"
    assert len(h.w.provider._cancellations) == 1
