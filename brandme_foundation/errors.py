"""MCP error taxonomy."""

from __future__ import annotations


class MCPError(RuntimeError):
    """Base for every MCP server error. Always carries a stable error code."""

    code: str = "mcp/internal"


class TenantRequired(MCPError):
    code = "mcp/tenant-required"


class CrossTenantAccess(MCPError):
    """Raised when a tool call would surface another owner's data."""

    code = "mcp/cross-tenant-access"


class PIIBoundaryViolation(MCPError):
    code = "mcp/pii-boundary-violation"


class ToolNotFound(MCPError):
    code = "mcp/tool-not-found"


class CapabilityMismatch(MCPError):
    """Raised when a call does not match the server's declared capability."""

    code = "mcp/capability-mismatch"


class BudgetExceeded(MCPError):
    code = "mcp/budget-exceeded"


class RateLimited(MCPError):
    code = "mcp/rate-limited"


class ConsentRequired(MCPError):
    """Raised when an action needs a signed consent record that is missing
    or revoked (P7: voice cloning requires the tenant owner's consent)."""

    code = "mcp/consent-required"


class ScanRequired(MCPError):
    """Raised when text reaches a synthesis boundary without a valid
    fair-housing scan token for exactly that text and tenant (P7)."""

    code = "mcp/scan-required"


class FeatureDisabled(MCPError):
    """Raised when a tool is called while its feature flag is off
    (VOICE_DELIVERY_ENABLED pattern — new behavior ships default-off)."""

    code = "mcp/feature-disabled"
