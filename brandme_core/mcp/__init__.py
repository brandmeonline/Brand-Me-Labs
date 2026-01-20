"""
Brand.Me v9 — Model Context Protocol (MCP) Integration
======================================================

Implements MCP for external agent access to Brand.Me tools.
Makes the Style Vault searchable by external agents with ethical oversight.

Key features:
- Tool manifest for agent discovery
- Consent verification before tool execution
- ESG verification for transactions
- Human-in-the-loop for sensitive operations
"""

from .tools import (
    MCPToolManifest,
    MCPTool,
    MCPToolExecutor,
    ToolExecutionResult,
)

from .consent import (
    MCPConsentVerifier,
    ConsentResult,
)

__all__ = [
    "MCPToolManifest",
    "MCPTool",
    "MCPToolExecutor",
    "ToolExecutionResult",
    "MCPConsentVerifier",
    "ConsentResult",
]
