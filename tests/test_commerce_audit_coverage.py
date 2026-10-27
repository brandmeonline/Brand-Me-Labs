"""Audit coverage: no tool call, from any origin and with any outcome, skips its audit record.

Ultra plan 02 item 2. Three layers:
- every invocation at the external MCP hop, including ones refused before a principal is verified;
- every proposal the assistant runtime receives, executed or refused;
- no module outside the executor reaches a tool handler except through ``call`` / ``audit_refusal``.
Each record also passes the closed run-log schema, since a rejected line is a lost record.
"""

import ast
import json
import pathlib
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from brandme_core.domains.commerce.delegation import AssistanceMode
from brandme_core.mcp import ExecutorAssertionVerifier, McpToolExecutor
from brandme_core.mcp.tools import KNOWN_TOOL_NAMES
from brandme_core.orchestrator import AssistantRuntime, ProposedCall
from brandme_core.orchestrator.runlog import MemoryRunLog, RunLogViolation
from tests.fixtures.commerce.harness import world
from tests.test_mcp import Harness

ROOT = pathlib.Path(__file__).resolve().parents[1]
ODD_NAMES = ["not.a.tool", "evil.tool; DROP TABLE", ""]
ALL_NAMES = sorted(KNOWN_TOOL_NAMES) + ODD_NAMES


@pytest.fixture(scope="module")
def keys():
    return {"gw": ec.generate_private_key(ec.SECP256R1()), "attacker": ec.generate_private_key(ec.SECP256R1())}


def _logged(h):
    """The harness with a strict run log beside the raw sink: a rejected line raises."""
    log = MemoryRunLog(strict=True)
    raw = h.audit
    h.ex.audit = lambda r: (raw.append(r), log.tool_call(r))
    return log


# ----------------------------------------------------------- external MCP hop
@pytest.mark.parametrize("name", ALL_NAMES)
def test_every_tool_name_at_the_mcp_hop_writes_exactly_one_record(keys, name):
    h = Harness(keys)
    log = _logged(h)
    h.call(name, {})
    assert len(h.audit) == 1 and h.audit[0]["tool"] == name and h.audit[0]["origin"] == "mcp"
    (line,) = log.events("mcp.tool_call")
    assert line["tool"] == (name if name in KNOWN_TOOL_NAMES else "unrecognized")


def test_a_full_agent_flow_at_the_mcp_hop_writes_one_record_per_call(keys):
    h = Harness(keys, mode=AssistanceMode.PREPARE)
    log = _logged(h)
    status, body = h.call("brandme.catalog.search", {"query": "linen"})
    item = body["structured_content"]["items"][0]
    lines = [{"variant_id": item["variant_id"], "source_variant_ref": item["source_variant_ref"], "quantity": 1}]
    status, body = h.call("brandme.cart.create", {"provider_id": item["provider_id"], "merchant_id": item["merchant_id"],
                                                  "lines": lines}, key="audit-cart-000000001")
    cart_id = body["structured_content"]["cart_id"]
    status, body = h.call("brandme.checkout.quote", {"cart_id": cart_id})
    h.call("brandme.purchase.request", {"quote_id": body["structured_content"]["quote"]["id"]})
    h.call("brandme.purchase.execute", {"operation_id": str(uuid.uuid4()), "approval_id": str(uuid.uuid4())},
           key="audit-exec-000000001")  # outside a prepare grant's scopes
    assert [(r["tool"], r["status"]) for r in h.audit] == [
        ("brandme.catalog.search", "ok"), ("brandme.cart.create", "ok"), ("brandme.checkout.quote", "ok"),
        ("brandme.purchase.request", "ok"), ("brandme.purchase.execute", "error")]
    assert len(log.events("mcp.tool_call")) == 5


def test_invocations_refused_before_verification_are_still_audited(keys):
    h = Harness(keys)
    log = _logged(h)
    replayed = h.assertion(jti="audit-replay-0000001")
    h.call("brandme.catalog.search", {"query": "linen"}, assertion=replayed)
    attempts = [
        dict(assertion=replayed),                         # replay
        dict(assertion=h.assertion(key=keys["attacker"])),  # forged
        dict(assertion="not-a-jwt"),                      # malformed
        dict(ttl=600),                                    # lifetime too long
        dict(aud_override="https://mcp.brandme.example.invalid/mcp"),  # an access token's audience
    ]
    for kw in attempts:
        assert h.call("brandme.cart.create", {"provider_id": "demo_atelier"}, **kw)[0] == 401
    refused = h.audit[1:]
    assert len(refused) == len(attempts)
    assert all(r["status"] == "refused" and r["code"] == "invalid_token" and r["member_ref"] is None
               and r["client_id"] is None and r["delegation_id"] is None and r["tool"] == "brandme.cart.create"
               for r in refused)
    assert [ln["status"] for ln in log.events("mcp.tool_call")] == ["ok"] + ["refused"] * len(attempts)
    assert h.w.store.rows("carts") == []


def test_a_non_object_invocation_is_audited(keys):
    h = Harness(keys)
    log = _logged(h)
    status, _ = h.ex.invoke(h.assertion(), ["not", "an", "invocation"])
    assert status == 400 and [(r["status"], r["code"]) for r in h.audit] == [("error", "malformed_invocation")]
    assert log.events("mcp.tool_call")[0]["tool"] == "unrecognized"


@pytest.mark.parametrize("record", [
    {"status": "ok", "origin": "mcp"},          # a successful call must name its member
    {"status": "refused", "origin": "assistant"},  # the runtime always has a verified principal
    {"status": "refused", "origin": "mcp", "client_id": "agent-client"},  # a client implies a principal
])
def test_the_run_log_accepts_a_memberless_record_only_for_an_unauthenticated_refusal(record):
    base = {"request_id": str(uuid.uuid4()), "tool": "brandme.catalog.search", "client_id": None, "member_ref": None,
            "delegation_id": None, "task_ref": None, "step": None, "code": "invalid_token", "duration_ms": 0,
            "arguments_digest": "0123456789abcdef"}
    log = MemoryRunLog(strict=True)
    log.tool_call({**base, "status": "refused", "origin": "mcp"})
    with pytest.raises(RunLogViolation):
        log.tool_call({**base, **record})


# ----------------------------------------------------------- assistant runtime
def _runtime(mode):
    w = world()
    d, ag = w.delegate(mode)
    audit, log = [], MemoryRunLog(strict=True)
    ex = McpToolExecutor(commerce=w.svc, registry=w.registry, audit=lambda r: (audit.append(r), log.tool_call(r)),
                         verifier=ExecutorAssertionVerifier(gateway_issuer="gw", keys={}, environment="development"))
    return w, ag, AssistantRuntime(ex, environment="development", run_log=log), audit, log


class Once:
    def __init__(self, *calls):
        self.calls = list(calls)

    def next_calls(self, task, observations):
        out, self.calls = self.calls, []
        return out


@pytest.mark.parametrize("name", ALL_NAMES)
def test_every_assistant_proposal_writes_exactly_one_record(name):
    w, ag, rt, audit, log = _runtime(AssistanceMode.BUY_WITHIN_RULES)
    task = rt.run(ag, rt.create(ag, "overshirt", AssistanceMode.BUY_WITHIN_RULES).id,
                  Once(ProposedCall(name, {}, idempotency_key="audit-proposal-00001")))
    proposed = [e for e in task.events if e.type == "proposed_action"]
    assert len(proposed) == len(audit) == len(log.events("mcp.tool_call")) == 1
    assert audit[0]["origin"] == "assistant" and audit[0]["task_ref"]
    assert audit[0]["tool"] == (name if name in KNOWN_TOOL_NAMES else "unknown_tool")


def test_a_mixed_assistant_run_writes_one_record_per_proposal():
    from tests.test_commerce_assistant import Script, _cart, _last
    w, ag, rt, audit, log = _runtime(AssistanceMode.PREPARE)
    junk = [ProposedCall("acp.checkout.complete", {}), ProposedCall("made.up", {})]
    p = Script(junk + [ProposedCall("brandme.catalog.search", {"query": "overshirt"})],
               lambda obs: junk + _cart(obs),
               lambda obs: [ProposedCall("brandme.checkout.quote", {"cart_id": _last(obs, "brandme.cart.create")["cart_id"]})],
               lambda obs: [ProposedCall("brandme.purchase.request",
                                         {"quote_id": _last(obs, "brandme.checkout.quote")["quote"]["id"]})])
    task = rt.run(ag, rt.create(ag, "an overshirt in M", AssistanceMode.PREPARE).id, p)
    proposed = [e.data["tool"] for e in task.events if e.type == "proposed_action"]
    assert task.state == "awaiting_approval" and len(proposed) == 8
    assert [r["tool"] for r in audit] == proposed and len(log.events("mcp.tool_call")) == len(proposed)
    assert [r["status"] for r in audit].count("ok") == 4 and [r["status"] for r in audit].count("refused") == 4


# ----------------------------------------------------------- structure
def _py_files():
    for top in ("brandme_core", "brandme-core", "brandme-agents"):
        yield from (ROOT / top).rglob("*.py")


def test_no_module_reaches_tool_handlers_except_through_the_audited_entry_points():
    """Only the executor touches its dispatcher and handler table; anything holding an executor uses only
    ``call``, ``audit_refusal``, ``invoke`` and read-only discovery."""
    executor_file = ROOT / "brandme_core" / "mcp" / "tools.py"
    public = {"call", "audit_refusal", "invoke", "list_tools", "server_discover", "commerce", "registry"}
    offenders = []
    for path in _py_files():
        if path == executor_file:
            continue
        text = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(text, filename=str(path))):
            where = f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, ast.Attribute):
                base = node.value
                holder = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
                if node.attr == "_dispatch" or ("executor" in holder.lower() and node.attr not in public):
                    offenders.append(f"{where} {holder}.{node.attr}")
            elif isinstance(node, ast.Constant) and node.value in ("_dispatch", "_handlers"):
                offenders.append(f"{where} {node.value!r}")  # getattr(executor, "_dispatch")
    assert offenders == []


def test_the_runtime_uses_its_executors_commerce_service_only_to_read():
    """The runtime may read the grant, bind the principal and read the clock; every action is a tool call."""
    path = ROOT / "brandme_core" / "orchestrator" / "runtime.py"
    uses = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) and node.value.attr == "commerce":
            uses.add(node.attr)
    assert uses == {"store", "bind", "clock"}
    text = path.read_text(encoding="utf-8")
    assert ".commerce.store.get(" in text and ".commerce.store.put" not in text
    assert ".commerce.store.transaction" not in text


# ----------------------------------------------------------- the domain's HTTP API (agents on REST routes)
def _http():
    from tests.test_commerce_http import Http
    h = Http()
    log, raw = MemoryRunLog(strict=True), h.audit
    h.api.audit = lambda r: (raw.append(r), log.agent_request(r))
    return h, log


def test_the_domain_http_api_requires_an_audit_sink():
    from brandme_core.domains.commerce.http_api import CommerceHttpApi
    from brandme_core.mcp.authz import DOMAIN_AUDIENCE
    w = world()
    verifier = ExecutorAssertionVerifier(gateway_issuer="gw", keys={}, environment="development",
                                         audience=DOMAIN_AUDIENCE, allow_session=True)
    with pytest.raises(TypeError):
        CommerceHttpApi(service=w.svc, verifier=verifier)  # no default: mounting cannot forget it
    with pytest.raises(ValueError):
        CommerceHttpApi(service=w.svc, verifier=verifier, audit=None, tier_audit=lambda r: None)
    with pytest.raises(ValueError):  # partner-tier decisions are audited too
        CommerceHttpApi(service=w.svc, verifier=verifier, audit=lambda r: None, tier_audit=None)


def test_every_agent_request_on_the_domain_http_api_writes_one_record():
    from tests.test_commerce_http import _line
    from brandme_core.domains.providers.local_atelier import MERCHANT_ID, PROVIDER_ID
    h, log = _http()
    d, _ = h.w.delegate(AssistanceMode.BUY_WITHIN_RULES)
    agent = h.bearer(d.scopes)
    rid = str(uuid.uuid4())
    cart = h.call("cart.create", {"provider_id": PROVIDER_ID, "merchant_id": MERCHANT_ID, "lines": [_line()]},
                  agent, {"Idempotency-Key": "audit-http-cart-0001", "X-Request-Id": rid}).json()
    quote = h.call("cart.quote", {"cart_id": cart["id"]}, agent).json()
    h.call("purchase.request", {"quote_id": quote["id"]}, agent)
    h.call("purchase.execute", {"quote_id": quote["id"], "approval_id": str(uuid.uuid4()), "delegation_id": None},
           agent, {"Idempotency-Key": "audit-http-exec-0001"})  # no member approval: refused by the domain
    h.call("order.cancel", {"order_id": str(uuid.uuid4())}, agent, {"Idempotency-Key": "audit-http-cncl-0001"})
    h.call("no.such_op", {}, agent)
    h.call("cart.create", {"member_id": "someone-else"}, agent, {"Idempotency-Key": "audit-http-cart-0002"})
    h.call("cart.quote", {"cart_id": cart["id"]})  # the member's own request: not an agent record
    got = [(r["operation"], r["status"]) for r in h.audit]
    assert got == [("cart.create", "ok"), ("cart.quote", "ok"), ("purchase.request", "ok"),
                   ("purchase.execute", "error"), ("order.cancel", "error"), ("no.such_op", "error"),
                   ("cart.create", "error")]
    assert all(r["origin"] == "api" and r["client_id"] == agent["client_id"] and r["member_ref"]
               and r["delegation_id"] == d.id for r in h.audit)
    assert h.audit[0]["request_id"] == rid and h.audit[-1]["code"] == "unexpected_field"
    lines = log.events("commerce.agent_request")
    assert len(lines) == len(h.audit) and {ln["retention"] for ln in lines} == {"security_audit_180d"}
    assert all(ln["delegation_ref"] for ln in lines) and d.id not in str(lines) and "someone-else" not in str(lines)


def test_a_crashing_agent_request_on_the_domain_http_api_is_still_audited():
    from tests.test_commerce_http import _line
    from brandme_core.domains.providers.local_atelier import MERCHANT_ID, PROVIDER_ID
    h, log = _http()
    d, _ = h.w.delegate(AssistanceMode.PREPARE)
    real = h.w.svc.create_cart

    def create_then_time_out(*a, **kw):
        real(*a, **kw)
        raise TimeoutError("deadline exceeded after commit: secret-detail")

    h.w.svc.create_cart = create_then_time_out
    with pytest.raises(TimeoutError):
        h.api.dispatch("cart.create", "Bearer " + h.assertion(h.bearer(d.scopes)),
                       json.dumps({"provider_id": PROVIDER_ID, "merchant_id": MERCHANT_ID,
                                   "lines": [_line()]}).encode(), {"idempotency-key": "audit-http-cart-0003"})
    assert [(r["operation"], r["status"], r["code"]) for r in h.audit] == [("cart.create", "error", "internal_error")]
    assert "secret-detail" not in json.dumps(log.lines)


def test_requests_refused_before_verification_on_the_domain_http_api_are_audited():
    h, log = _http()
    d, _ = h.w.delegate(AssistanceMode.PREPARE)
    forged = h.client.post("/internal/commerce/v1/cart.create", content=b"{}",
                           headers={"Authorization": "Bearer not-a-jwt"})
    missing = h.client.post("/internal/commerce/v1/cart.create", content=b"{}")
    wrong_hop = h.call("cart.create", {}, h.bearer(d.scopes), audience="brandme:mcp-executor")
    assert {forged.status_code, missing.status_code, wrong_hop.status_code} == {401}
    assert [(r["status"], r["code"], r["member_ref"], r["client_id"]) for r in h.audit] == [
        ("refused", "invalid_token", None, None)] * 3
    assert len(log.events("commerce.agent_request")) == 3
