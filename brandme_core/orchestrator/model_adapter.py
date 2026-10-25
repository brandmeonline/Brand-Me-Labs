"""Provider-neutral types for the model planner (no SDK import here).

A planner request is one fresh, self-contained message (``PlanRequest``); a response is at most
one proposed tool call plus counts (``PlanResponse``). Neither carries model text: an adapter
drops text and thinking blocks before anything leaves it, so nothing a model writes can be
stored, logged or shown. ``AnthropicAdapter`` (``anthropic_adapter.py``) is the first
implementation; another provider implements the same ``ModelAdapter`` protocol.

Tool names: MCP names contain dots, provider tool names allow ``[A-Za-z0-9_-]`` only, so
``brandme.catalog.search`` is sent as ``brandme__catalog__search``. A name that does not map back
to a known tool becomes ``UNKNOWN_TOOL``; the model's string is never kept.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import AbstractSet, Any, Mapping, Optional, Protocol, Tuple

from brandme_core.mcp import tools

WIRE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")  # 64 also fits OpenAI function names
UNKNOWN_TOOL = tools.UNKNOWN_TOOL


def wire_name(mcp: str) -> str:
    """``brandme.catalog.search`` -> ``brandme__catalog__search`` (reversible)."""
    if "__" in mcp:
        raise ValueError("an MCP tool name may not contain '__'")
    wire = mcp.replace(".", "__")
    if not WIRE_NAME_RE.match(wire):
        raise ValueError("tool name does not fit provider naming rules")
    return wire


def mcp_name(wire: Any, known: AbstractSet[str]) -> str:
    """The MCP name a provider tool name stands for, or ``UNKNOWN_TOOL``."""
    if not isinstance(wire, str) or not WIRE_NAME_RE.match(wire):
        return UNKNOWN_TOOL
    name = wire.replace("__", ".")
    return name if name in known else UNKNOWN_TOOL


class PlannerConfigError(ValueError):
    """Startup refused. The message is the fixed ``code`` only, never a key, URL or path."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# ----------------------------------------------------------------------- requests
@dataclass(frozen=True)
class ToolDef:
    name: str  # MCP name
    description: str
    input_schema: Mapping[str, Any]

    @property
    def wire(self) -> str:
        return wire_name(self.name)


@dataclass(frozen=True)
class PlanRequest:
    prompt_version: str
    system: str
    tools: Tuple[ToolDef, ...]  # sorted by name
    task_block: str
    record_block: str
    max_output_tokens: int


@dataclass(frozen=True)
class EncodedRequest:
    body: Mapping[str, Any]
    canonical: str  # sorted-key JSON of ``body``: no credentials, no URL
    size_bytes: int


# ---------------------------------------------------------------------- responses
class StopKind(str, Enum):
    TOOL_CALL = "tool_call"
    DONE = "done"
    REFUSAL = "refusal"
    TRUNCATED = "truncated"
    PAUSED = "paused"
    CONTEXT_EXCEEDED = "context_exceeded"
    INCONSISTENT = "inconsistent"  # a tool_use stop without exactly one usable tool call
    UNEXPECTED = "unexpected"  # a stop the planner cannot use: stop_sequence, end_turn with a call, unknown


@dataclass(frozen=True)
class ProposedToolUse:
    tool: str  # MCP name or UNKNOWN_TOOL
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int = 0  # uncached
    output_tokens: int = 0  # includes thinking
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    thinking_tokens: Optional[int] = None

    @property
    def total_input(self) -> int:
        return self.input_tokens + self.cache_read_input_tokens + self.cache_creation_input_tokens


@dataclass(frozen=True)
class PlanResponse:
    """Deliberately no text, thinking or explanation field."""
    stop: StopKind
    raw_stop_reason: Optional[str]  # the provider's value when it is a known one, else "other"
    calls: Tuple[ProposedToolUse, ...]  # length 0 or 1
    usage: ModelUsage
    model_served: str
    provider_request_id: Optional[str]
    refusal_category: Optional[str]
    tool_use_blocks: int
    text_blocks: int
    unknown_tools: int


# ------------------------------------------------------------- errors and billing
class Billing(str, Enum):
    NONE = "none"  # the provider did not bill (rejected before inference)
    UNKNOWN = "unknown"  # it may have (timeout, 5xx, dropped connection): charge the reservation


class ModelCallError(Exception):
    """A failed model call; ``code`` is fixed and member-safe, provider text is never kept."""

    def __init__(self, code: str, billing: Billing):
        super().__init__(code)
        self.code = code
        self.billing = billing


# ------------------------------------------------------------ pricing and profiles
@dataclass(frozen=True)
class ModelPrice:
    """Integer nano-USD per token, so cost arithmetic never uses floats."""
    input: int
    output: int
    cache_write: int
    cache_read: int

    def cost_micro_usd(self, u: ModelUsage) -> int:
        nano = (u.input_tokens * self.input + u.output_tokens * self.output
                + u.cache_creation_input_tokens * self.cache_write + u.cache_read_input_tokens * self.cache_read)
        return math.ceil(nano / 1000)

    def upper_bound_micro_usd(self, input_tokens: int, output_tokens: int) -> int:
        nano = input_tokens * max(self.input, self.cache_write) + output_tokens * self.output
        return math.ceil(nano / 1000)


@dataclass(frozen=True)
class ModelProfile:
    model: str
    price: ModelPrice
    input_overhead_tokens: int  # tool/system framing the provider adds beyond the request bytes
    max_output_tokens_cap: int


# ------------------------------------------------------------------------ adapter
class ModelAdapter(Protocol):
    provider: str
    model: str
    effort: str
    sdk_version: str
    api_version: str
    profile: ModelProfile

    def encode(self, request: PlanRequest) -> EncodedRequest: ...

    def send(self, encoded: EncodedRequest, *, timeout_s: float) -> PlanResponse: ...  # raises ModelCallError only

    def close(self) -> None: ...
