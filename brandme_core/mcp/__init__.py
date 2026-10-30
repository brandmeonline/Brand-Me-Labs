"""
Brand.Me — Model Context Protocol (MCP) tool surface
====================================================

* ``tools``  — ch.05 tool table and the principal-bound ``McpToolExecutor``.
* ``authz``  — MCP 2026-07-28 authorization: audience-bound access token
  validation (reference), protected-resource metadata, executor assertions.
* ``consent`` — legacy Spanner consent-graph verifier (unchanged).

Fake v9 tools (AP2 "intent mandates", ACP "checkout complete", rentals,
resale, ESG-verified results) are retired; see ``tools.RETIRED_TOOLS``.
"""

from .authz import (
    MCP_PROTOCOL_VERSION,
    AuthError,
    ExecutorAssertionVerifier,
    McpAccessTokenValidator,
    protected_resource_metadata,
)
from .consent import ConsentResult, MCPConsentVerifier
from .tools import RETIRED_TOOLS, TOOLS, UNAVAILABLE_TOOLS, McpToolExecutor, ToolOutcome

__all__ = [
    "MCP_PROTOCOL_VERSION", "AuthError", "ExecutorAssertionVerifier", "McpAccessTokenValidator",
    "protected_resource_metadata", "ConsentResult", "MCPConsentVerifier", "RETIRED_TOOLS", "TOOLS",
    "UNAVAILABLE_TOOLS", "McpToolExecutor", "ToolOutcome",
]
