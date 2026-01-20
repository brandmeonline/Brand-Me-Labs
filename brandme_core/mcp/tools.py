"""
Brand.Me v9 — MCP Tool Definitions
==================================

Defines tools exposed via Model Context Protocol for external agents.
Style Vault is searchable as an MCP tool with ethical oversight.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List, Callable

from brandme_core.logging import get_logger

logger = get_logger("mcp.tools")


class ToolCategory(str, Enum):
    """Categories of MCP tools."""
    SEARCH = "search"
    VIEW = "view"
    TRANSACTION = "transaction"
    STYLE = "style"
    LIFECYCLE = "lifecycle"


@dataclass
class MCPTool:
    """
    Definition of an MCP tool.

    Tools with requires_esg_check=True trigger Cardano ESG verification
    before execution. Tools with requires_consent=True verify user consent.
    """
    name: str
    description: str
    category: ToolCategory
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    requires_consent: bool = True
    requires_esg_check: bool = False
    min_trust_score: float = 0.5
    is_transactional: bool = False


@dataclass
class ToolExecutionResult:
    """Result of tool execution."""
    success: bool
    tool_name: str
    invocation_id: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    consent_verified: bool = False
    esg_check_passed: Optional[bool] = None
    human_approval_required: bool = False
    human_approved_by: Optional[str] = None
    execution_time_ms: float = 0.0


# =============================================================================
# MCP Tool Manifest
# =============================================================================

class MCPToolManifest:
    """
    MCP Tool Manifest for Brand.Me Style Vault.

    Exposes wardrobe and fashion tools to external agents.
    """

    VERSION = "1.0.0"
    NAME = "brandme_style_vault"
    DESCRIPTION = "Search and interact with Brand.Me digital fashion wardrobe"

    TOOLS: List[MCPTool] = [
        # Search Tools
        MCPTool(
            name="search_wardrobe",
            description="Search user's wardrobe by criteria (material, color, category, ESG score)",
            category=ToolCategory.SEARCH,
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User's ID"},
                    "query": {"type": "string", "description": "Search query"},
                    "filters": {
                        "type": "object",
                        "properties": {
                            "material_type": {"type": "string"},
                            "category": {"type": "string"},
                            "esg_min_score": {"type": "number", "minimum": 0, "maximum": 1},
                            "lifecycle_state": {"type": "string", "enum": ["PRODUCED", "ACTIVE", "REPAIR", "DISSOLVE", "REPRINT"]},
                            "color": {"type": "string"},
                            "size": {"type": "string"}
                        }
                    },
                    "limit": {"type": "integer", "default": 10, "maximum": 50}
                },
                "required": ["user_id"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"type": "object"}},
                    "total_count": {"type": "integer"}
                }
            },
            requires_consent=True,
            requires_esg_check=False,
            min_trust_score=0.3
        ),

        MCPTool(
            name="get_cube_details",
            description="Get detailed information about a specific Product Cube",
            category=ToolCategory.VIEW,
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "cube_id": {"type": "string"},
                    "include_faces": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of faces to include (product_details, esg_impact, etc.)"
                    }
                },
                "required": ["user_id", "cube_id"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "cube_id": {"type": "string"},
                    "display_name": {"type": "string"},
                    "faces": {"type": "object"},
                    "lifecycle_state": {"type": "string"},
                    "esg_score": {"type": "number"}
                }
            },
            requires_consent=True,
            requires_esg_check=False,
            min_trust_score=0.3
        ),

        # Style Suggestion Tools
        MCPTool(
            name="suggest_outfit",
            description="Get AI-powered outfit suggestions based on wardrobe and occasion",
            category=ToolCategory.STYLE,
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "occasion": {"type": "string", "description": "e.g., casual, formal, sport"},
                    "weather": {"type": "string", "description": "e.g., warm, cold, rainy"},
                    "color_preference": {"type": "string"},
                    "sustainability_priority": {"type": "boolean", "default": True}
                },
                "required": ["user_id", "occasion"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "outfits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "items": {"type": "array"},
                                "esg_score": {"type": "number"},
                                "style_notes": {"type": "string"}
                            }
                        }
                    }
                }
            },
            requires_consent=True,
            requires_esg_check=False,
            min_trust_score=0.4
        ),

        # Transaction Tools (require ESG check)
        MCPTool(
            name="initiate_rental",
            description="Start rental process for a garment",
            category=ToolCategory.TRANSACTION,
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "cube_id": {"type": "string"},
                    "rental_duration_days": {"type": "integer", "minimum": 1, "maximum": 30},
                    "rental_price_usd": {"type": "number"},
                    "renter_id": {"type": "string"}
                },
                "required": ["user_id", "cube_id", "rental_duration_days", "renter_id"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "rental_id": {"type": "string"},
                    "status": {"type": "string"},
                    "requires_human_approval": {"type": "boolean"},
                    "esg_verified": {"type": "boolean"}
                }
            },
            requires_consent=True,
            requires_esg_check=True,
            min_trust_score=0.6,
            is_transactional=True
        ),

        MCPTool(
            name="list_for_resale",
            description="List item on marketplace for resale",
            category=ToolCategory.TRANSACTION,
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "cube_id": {"type": "string"},
                    "asking_price_usd": {"type": "number"},
                    "description": {"type": "string"},
                    "condition": {"type": "string", "enum": ["new", "like_new", "good", "fair"]}
                },
                "required": ["user_id", "cube_id", "asking_price_usd"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "listing_id": {"type": "string"},
                    "status": {"type": "string"},
                    "requires_human_approval": {"type": "boolean"},
                    "esg_verified": {"type": "boolean"}
                }
            },
            requires_consent=True,
            requires_esg_check=True,
            min_trust_score=0.6,
            is_transactional=True
        ),

        # Lifecycle Tools
        MCPTool(
            name="request_repair",
            description="Request repair for a damaged garment",
            category=ToolCategory.LIFECYCLE,
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "cube_id": {"type": "string"},
                    "damage_description": {"type": "string"},
                    "preferred_repair_type": {"type": "string", "enum": ["patch", "restore", "upcycle"]}
                },
                "required": ["user_id", "cube_id", "damage_description"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "repair_request_id": {"type": "string"},
                    "estimated_esg_improvement": {"type": "number"},
                    "status": {"type": "string"}
                }
            },
            requires_consent=True,
            requires_esg_check=False,
            min_trust_score=0.5
        ),

        MCPTool(
            name="request_dissolve",
            description="Request dissolution for circular economy (requires owner consent)",
            category=ToolCategory.LIFECYCLE,
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "cube_id": {"type": "string"},
                    "dissolution_method": {"type": "string", "enum": ["chemical", "mechanical", "enzymatic"]},
                    "facility_id": {"type": "string"}
                },
                "required": ["user_id", "cube_id"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "dissolve_request_id": {"type": "string"},
                    "requires_auth_key": {"type": "boolean"},
                    "estimated_material_recovery_pct": {"type": "number"},
                    "status": {"type": "string"}
                }
            },
            requires_consent=True,
            requires_esg_check=True,
            min_trust_score=0.7,
            is_transactional=True
        )
    ]

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        """Get the full MCP tool manifest."""
        return {
            "name": cls.NAME,
            "description": cls.DESCRIPTION,
            "version": cls.VERSION,
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "category": tool.category.value,
                    "inputSchema": tool.input_schema,
                    "outputSchema": tool.output_schema,
                    "requires_consent": tool.requires_consent,
                    "requires_esg_check": tool.requires_esg_check,
                    "min_trust_score": tool.min_trust_score,
                    "is_transactional": tool.is_transactional
                }
                for tool in cls.TOOLS
            ]
        }

    @classmethod
    def get_tool(cls, name: str) -> Optional[MCPTool]:
        """Get a tool by name."""
        for tool in cls.TOOLS:
            if tool.name == name:
                return tool
        return None


# =============================================================================
# MCP Tool Executor
# =============================================================================

class MCPToolExecutor:
    """
    Executes MCP tools with consent and ESG verification.
    """

    def __init__(
        self,
        spanner_pool,
        consent_verifier,
        esg_verifier,
        cube_service_client=None,
        brain_service_client=None
    ):
        """
        Initialize the tool executor.

        Args:
            spanner_pool: Spanner connection pool
            consent_verifier: MCPConsentVerifier instance
            esg_verifier: ESGVerifier instance
            cube_service_client: Client for cube service
            brain_service_client: Client for brain service
        """
        self.spanner_pool = spanner_pool
        self.consent_verifier = consent_verifier
        self.esg_verifier = esg_verifier
        self.cube_client = cube_service_client
        self.brain_client = brain_service_client

        # Tool handlers
        self._handlers: Dict[str, Callable] = {
            "search_wardrobe": self._handle_search_wardrobe,
            "get_cube_details": self._handle_get_cube_details,
            "suggest_outfit": self._handle_suggest_outfit,
            "initiate_rental": self._handle_initiate_rental,
            "list_for_resale": self._handle_list_for_resale,
            "request_repair": self._handle_request_repair,
            "request_dissolve": self._handle_request_dissolve,
        }

    async def execute(
        self,
        tool_name: str,
        agent_id: str,
        params: Dict[str, Any]
    ) -> ToolExecutionResult:
        """
        Execute an MCP tool.

        Args:
            tool_name: Name of the tool to execute
            agent_id: ID of the calling agent
            params: Tool parameters

        Returns:
            ToolExecutionResult with execution details
        """
        from google.cloud import spanner
        import time

        invocation_id = str(uuid.uuid4())
        start_time = time.time()

        # Get tool definition
        tool = MCPToolManifest.get_tool(tool_name)
        if not tool:
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                invocation_id=invocation_id,
                error=f"Unknown tool: {tool_name}"
            )

        user_id = params.get("user_id")
        if not user_id:
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                invocation_id=invocation_id,
                error="user_id is required"
            )

        # Verify consent
        consent_verified = False
        if tool.requires_consent:
            consent_result = await self.consent_verifier.verify(
                user_id=user_id,
                agent_id=agent_id,
                permission_scope=self._get_permission_scope(tool),
                tool_name=tool_name
            )
            if not consent_result.is_granted:
                return ToolExecutionResult(
                    success=False,
                    tool_name=tool_name,
                    invocation_id=invocation_id,
                    error=consent_result.reason or "Consent not granted",
                    consent_verified=False
                )
            consent_verified = True

        # ESG verification for transactional tools
        esg_check_passed = None
        human_approval_required = False

        if tool.requires_esg_check:
            # Get asset's material for ESG check
            cube_id = params.get("cube_id")
            if cube_id:
                material_id = await self._get_asset_material(cube_id)
                if material_id:
                    esg_result = await self.esg_verifier.verify_agent_transaction(
                        asset_id=cube_id,
                        material_id=material_id,
                        agent_id=agent_id,
                        transaction_type=tool.name,
                        transaction_value_usd=params.get("asking_price_usd", 0) or params.get("rental_price_usd", 0),
                        user_consent={"min_esg_score": tool.min_trust_score}
                    )
                    esg_check_passed = esg_result.is_approved
                    human_approval_required = esg_result.requires_human_review

                    if not esg_check_passed and not human_approval_required:
                        return ToolExecutionResult(
                            success=False,
                            tool_name=tool_name,
                            invocation_id=invocation_id,
                            error=esg_result.reason or "ESG check failed",
                            consent_verified=consent_verified,
                            esg_check_passed=False
                        )

        # Execute tool handler
        handler = self._handlers.get(tool_name)
        if not handler:
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                invocation_id=invocation_id,
                error=f"No handler for tool: {tool_name}",
                consent_verified=consent_verified,
                esg_check_passed=esg_check_passed
            )

        try:
            result = await handler(params, agent_id)

            execution_time = (time.time() - start_time) * 1000

            # Log invocation to Spanner
            await self._log_invocation(
                invocation_id=invocation_id,
                tool_name=tool_name,
                agent_id=agent_id,
                user_id=user_id,
                params=params,
                success=True,
                esg_check_passed=esg_check_passed,
                consent_verified=consent_verified,
                human_approval_required=human_approval_required
            )

            logger.info({
                "event": "mcp_tool_executed",
                "invocation_id": invocation_id,
                "tool_name": tool_name,
                "agent_id": agent_id[:8] + "...",
                "user_id": user_id[:8] + "...",
                "success": True,
                "execution_time_ms": execution_time
            })

            return ToolExecutionResult(
                success=True,
                tool_name=tool_name,
                invocation_id=invocation_id,
                result=result,
                consent_verified=consent_verified,
                esg_check_passed=esg_check_passed,
                human_approval_required=human_approval_required,
                execution_time_ms=execution_time
            )

        except Exception as e:
            logger.error({
                "event": "mcp_tool_error",
                "invocation_id": invocation_id,
                "tool_name": tool_name,
                "error": str(e)
            })

            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                invocation_id=invocation_id,
                error=str(e),
                consent_verified=consent_verified,
                esg_check_passed=esg_check_passed,
                execution_time_ms=(time.time() - start_time) * 1000
            )

    def _get_permission_scope(self, tool: MCPTool) -> str:
        """Map tool to permission scope."""
        scope_map = {
            ToolCategory.SEARCH: "view_wardrobe",
            ToolCategory.VIEW: "view_wardrobe",
            ToolCategory.STYLE: "style_suggest",
            ToolCategory.TRANSACTION: "transact",
            ToolCategory.LIFECYCLE: "transact",
        }
        return scope_map.get(tool.category, "view_wardrobe")

    async def _get_asset_material(self, asset_id: str) -> Optional[str]:
        """Get primary material ID for an asset."""
        from google.cloud.spanner_v1 import param_types

        def _get_material(transaction):
            results = transaction.execute_sql(
                """
                SELECT primary_material_id FROM Assets
                WHERE asset_id = @asset_id
                """,
                params={"asset_id": asset_id},
                param_types={"asset_id": param_types.STRING}
            )
            for row in results:
                return row[0]
            return None

        return self.spanner_pool.database.run_in_transaction(_get_material)

    async def _log_invocation(
        self,
        invocation_id: str,
        tool_name: str,
        agent_id: str,
        user_id: str,
        params: Dict[str, Any],
        success: bool,
        esg_check_passed: Optional[bool],
        consent_verified: bool,
        human_approval_required: bool
    ):
        """Log tool invocation to Spanner."""
        from google.cloud import spanner
        from google.cloud.spanner_v1 import param_types
        import hashlib

        params_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()

        # Get tool_id from MCPTools table
        def _get_tool_id(transaction):
            results = transaction.execute_sql(
                """
                SELECT tool_id FROM MCPTools
                WHERE tool_name = @tool_name AND is_active = true
                LIMIT 1
                """,
                params={"tool_name": tool_name},
                param_types={"tool_name": param_types.STRING}
            )
            for row in results:
                return row[0]
            return None

        tool_id = self.spanner_pool.database.run_in_transaction(_get_tool_id)

        if tool_id:
            def _log(transaction):
                transaction.insert(
                    table="MCPInvocations",
                    columns=[
                        "invocation_id", "tool_id", "agent_id", "user_id",
                        "input_params_hash", "result_status", "esg_check_passed",
                        "consent_verified", "human_approval_required", "invoked_at"
                    ],
                    values=[(
                        invocation_id, tool_id, agent_id, user_id,
                        params_hash, "success" if success else "error",
                        esg_check_passed, consent_verified, human_approval_required,
                        spanner.COMMIT_TIMESTAMP
                    )]
                )

            self.spanner_pool.database.run_in_transaction(_log)

    # Tool Handlers (stubs - would connect to actual services)

    async def _handle_search_wardrobe(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Handle wardrobe search."""
        # Stub implementation - would query Firestore wardrobe
        return {
            "items": [],
            "total_count": 0,
            "message": "Search functionality via MCP"
        }

    async def _handle_get_cube_details(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Handle cube details request."""
        return {
            "cube_id": params.get("cube_id"),
            "display_name": "Sample Garment",
            "lifecycle_state": "ACTIVE",
            "faces": {}
        }

    async def _handle_suggest_outfit(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Handle outfit suggestion."""
        return {
            "outfits": [],
            "message": "Outfit suggestion via MCP"
        }

    async def _handle_initiate_rental(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Handle rental initiation."""
        return {
            "rental_id": str(uuid.uuid4()),
            "status": "pending_human_approval",
            "requires_human_approval": True,
            "esg_verified": True
        }

    async def _handle_list_for_resale(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Handle resale listing."""
        return {
            "listing_id": str(uuid.uuid4()),
            "status": "pending_human_approval",
            "requires_human_approval": True,
            "esg_verified": True
        }

    async def _handle_request_repair(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Handle repair request."""
        return {
            "repair_request_id": str(uuid.uuid4()),
            "estimated_esg_improvement": 0.1,
            "status": "submitted"
        }

    async def _handle_request_dissolve(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Handle dissolve request."""
        return {
            "dissolve_request_id": str(uuid.uuid4()),
            "requires_auth_key": True,
            "estimated_material_recovery_pct": 85.0,
            "status": "pending_authorization"
        }
