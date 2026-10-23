"""A scripted Anthropic Messages API behind an httpx ``MockTransport``.

The real ``anthropic`` client sends real requests into this transport, so tests see exactly
what the SDK would put on the wire. Nothing leaves the process; ``KEY`` is fake.

Script items, consumed one per request:

* a message dict (see ``message``), or a callable ``(body) -> message dict``;
* an ``int`` status: an error response whose body carries ``UPSTREAM_DETAIL``;
* ``("redirect", location)``: a 307;
* an exception instance (``httpx.ReadTimeout(...)``, ``httpx.ConnectError(...)``): raised.

An exhausted script answers with a plain finish (``end_turn``, no tool call).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from brandme_core.orchestrator.model_adapter import wire_name

KEY = "sk-ant-api03-" + "x" * 40  # fake: the transport never leaves the process
UPSTREAM_DETAIL = "upstream detail that must never be shown"
THINK = {"type": "thinking", "thinking": "", "signature": "sig-opaque"}


def message(content: List[Dict[str, Any]], stop: str = "tool_use", inp: int = 1200, out: int = 80,
            cache_read: int = 0, cache_write: int = 0, model: str = "claude-opus-5-5",
            stop_details: Optional[Dict[str, Any]] = None, thinking_tokens: Optional[int] = None) -> Dict[str, Any]:
    usage: Dict[str, Any] = {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": cache_read,
                             "cache_creation_input_tokens": cache_write}
    if thinking_tokens is not None:
        usage["output_tokens_details"] = {"thinking_tokens": thinking_tokens}
    return {"id": "msg_0001", "type": "message", "role": "assistant", "model": model, "content": content,
            "stop_reason": stop, "stop_sequence": None, "stop_details": stop_details, "usage": usage}


def tool_use(n: int, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """``name`` is an MCP name (mapped to its wire name) or, without dots, a raw wire name."""
    return {"type": "tool_use", "id": f"toolu_{n:02d}", "name": wire_name(name) if "." in name else name,
            "input": args}


def call(n: int, name: str, args: Dict[str, Any], **kw: Any) -> Dict[str, Any]:
    """One tool call with an empty thinking block in front, as Opus 5.5 answers."""
    return message([THINK, tool_use(n, name, args)], **kw)


def done(**kw: Any) -> Dict[str, Any]:
    return message([THINK, {"type": "text", "text": "Done."}], stop="end_turn", **kw)


class FakeMessagesApi:
    def __init__(self, script: List[Any]):
        self.script = list(script)
        self.requests: List[Dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"url": str(request.url), "headers": dict(request.headers), "body": body,
                              "raw": request.content.decode(), "timeout": request.extensions.get("timeout")})
        item = self.script.pop(0) if self.script else done()
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, int):
            return httpx.Response(item, json={"type": "error", "error": {"type": "api_error",
                                                                          "message": UPSTREAM_DETAIL}})
        if isinstance(item, tuple) and item[0] == "redirect":
            return httpx.Response(307, headers={"location": item[1]})
        if callable(item):
            item = item(body)
        return httpx.Response(200, json=item, headers={"request-id": f"req_{len(self.requests):03d}"})

    def bodies(self) -> List[Dict[str, Any]]:
        return [r["body"] for r in self.requests]


def _block(body: Dict[str, Any], i: int, tag: str) -> Any:
    text = body["messages"][0]["content"][i]["text"]
    assert text.startswith(f"<{tag}>\n") and text.endswith(f"\n</{tag}>")
    return json.loads(text[len(tag) + 3:-(len(tag) + 4)])


def task_data(body: Dict[str, Any]) -> Dict[str, Any]:
    return _block(body, 0, "task_data")


def tool_record(body: Dict[str, Any]) -> Dict[str, Any]:
    return _block(body, 1, "tool_record")


def last_result(body: Dict[str, Any]) -> Dict[str, Any]:
    return tool_record(body)["calls"][-1]["result"]


def make_planner(api: FakeMessagesApi, *, run_log=None, ledger=None, clock=None, environment="development",
                 **budget: Any):
    """The real planner and adapter over the fake transport."""
    import time

    from brandme_core.orchestrator.anthropic_adapter import AnthropicAdapter
    from brandme_core.orchestrator.budget import InMemoryCostLedger
    from brandme_core.orchestrator.model_planner import ModelBudget, ModelPlanner
    from brandme_core.orchestrator.runlog import MemoryRunLog
    adapter = AnthropicAdapter(api_key=KEY, transport=httpx.MockTransport(api))
    return ModelPlanner(adapter, budget=ModelBudget(**budget), ledger=ledger or InMemoryCostLedger(),
                        run_log=run_log if run_log is not None else MemoryRunLog(environment=environment, strict=True),
                        environment=environment, clock=clock or time.monotonic)
