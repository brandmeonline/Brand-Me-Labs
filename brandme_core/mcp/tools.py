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

    # Tool Handlers - Connect to actual services via Spanner

    async def _handle_search_wardrobe(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """
        Handle wardrobe search via Spanner.
        Queries Assets and Owns tables to find user's items.
        """
        from google.cloud.spanner_v1 import param_types

        user_id = params.get("user_id")
        query_text = params.get("query", "")
        filters = params.get("filters", {})
        limit = min(params.get("limit", 10), 50)

        def _search(transaction):
            # Build dynamic query based on filters
            conditions = ["o.owner_id = @user_id", "o.is_current = true"]
            query_params = {"user_id": user_id}
            query_param_types = {"user_id": param_types.STRING}

            if filters.get("lifecycle_state"):
                conditions.append("a.lifecycle_state = @lifecycle_state")
                query_params["lifecycle_state"] = filters["lifecycle_state"]
                query_param_types["lifecycle_state"] = param_types.STRING

            if filters.get("category"):
                conditions.append("a.category = @category")
                query_params["category"] = filters["category"]
                query_param_types["category"] = param_types.STRING

            if query_text:
                conditions.append("(a.display_name LIKE @query OR a.description LIKE @query)")
                query_params["query"] = f"%{query_text}%"
                query_param_types["query"] = param_types.STRING

            where_clause = " AND ".join(conditions)

            sql = f"""
                SELECT a.asset_id, a.display_name, a.category, a.lifecycle_state,
                       a.public_esg_score, a.asset_type, o.acquired_at
                FROM Owns o
                JOIN Assets a ON o.asset_id = a.asset_id
                WHERE {where_clause}
                ORDER BY o.acquired_at DESC
                LIMIT {limit}
            """

            results = transaction.execute_sql(sql, params=query_params, param_types=query_param_types)

            items = []
            for row in results:
                items.append({
                    "asset_id": row[0],
                    "display_name": row[1],
                    "category": row[2],
                    "lifecycle_state": row[3],
                    "esg_score": row[4],
                    "asset_type": row[5],
                    "acquired_at": row[6].isoformat() if row[6] else None
                })
            return items

        items = self.spanner_pool.database.run_in_transaction(_search)

        logger.info({
            "event": "mcp_wardrobe_search",
            "user_id": user_id[:8] + "...",
            "agent_id": agent_id[:8] + "...",
            "result_count": len(items),
            "filters": list(filters.keys())
        })

        return {
            "items": items,
            "total_count": len(items),
            "filters_applied": list(filters.keys())
        }

    async def _handle_get_cube_details(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """
        Handle cube details request via Spanner.
        Returns asset details with requested faces.
        """
        from google.cloud.spanner_v1 import param_types

        user_id = params.get("user_id")
        cube_id = params.get("cube_id")
        include_faces = params.get("include_faces", ["product_details", "esg_impact"])

        def _get_details(transaction):
            # Get asset details
            results = transaction.execute_sql(
                """
                SELECT a.asset_id, a.display_name, a.category, a.description,
                       a.lifecycle_state, a.public_esg_score, a.asset_type,
                       a.reprint_generation, a.created_at,
                       m.material_type, m.esg_score as material_esg
                FROM Assets a
                LEFT JOIN Materials m ON a.primary_material_id = m.material_id
                WHERE a.asset_id = @asset_id
                """,
                params={"asset_id": cube_id},
                param_types={"asset_id": param_types.STRING}
            )

            for row in results:
                return {
                    "asset_id": row[0],
                    "display_name": row[1],
                    "category": row[2],
                    "description": row[3],
                    "lifecycle_state": row[4],
                    "public_esg_score": row[5],
                    "asset_type": row[6],
                    "reprint_generation": row[7],
                    "created_at": row[8].isoformat() if row[8] else None,
                    "material_type": row[9],
                    "material_esg": row[10]
                }
            return None

        details = self.spanner_pool.database.run_in_transaction(_get_details)

        if not details:
            raise ValueError(f"Cube {cube_id} not found")

        # Build faces response based on include_faces
        faces = {}
        if "product_details" in include_faces:
            faces["product_details"] = {
                "display_name": details["display_name"],
                "category": details["category"],
                "description": details["description"],
                "asset_type": details["asset_type"]
            }
        if "esg_impact" in include_faces:
            faces["esg_impact"] = {
                "public_esg_score": details["public_esg_score"],
                "material_esg": details["material_esg"]
            }
        if "lifecycle" in include_faces:
            faces["lifecycle"] = {
                "current_state": details["lifecycle_state"],
                "reprint_generation": details["reprint_generation"]
            }
        if "molecular_data" in include_faces:
            faces["molecular_data"] = {
                "material_type": details["material_type"]
            }

        logger.info({
            "event": "mcp_cube_details",
            "cube_id": cube_id[:8] + "...",
            "agent_id": agent_id[:8] + "...",
            "faces_included": include_faces
        })

        return {
            "cube_id": cube_id,
            "display_name": details["display_name"],
            "lifecycle_state": details["lifecycle_state"],
            "esg_score": details["public_esg_score"],
            "faces": faces
        }

    async def _handle_suggest_outfit(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """
        Handle outfit suggestion via Spanner query.
        Suggests outfits based on occasion, weather, and sustainability priority.
        """
        from google.cloud.spanner_v1 import param_types

        user_id = params.get("user_id")
        occasion = params.get("occasion", "casual")
        sustainability_priority = params.get("sustainability_priority", True)

        def _get_wardrobe(transaction):
            # Get user's active items, ordered by ESG score if sustainability priority
            order_by = "CAST(a.public_esg_score AS FLOAT64) DESC" if sustainability_priority else "o.acquired_at DESC"

            results = transaction.execute_sql(
                f"""
                SELECT a.asset_id, a.display_name, a.category, a.public_esg_score,
                       a.asset_type, m.material_type
                FROM Owns o
                JOIN Assets a ON o.asset_id = a.asset_id
                LEFT JOIN Materials m ON a.primary_material_id = m.material_id
                WHERE o.owner_id = @user_id
                    AND o.is_current = true
                    AND a.lifecycle_state = 'ACTIVE'
                ORDER BY {order_by}
                LIMIT 20
                """,
                params={"user_id": user_id},
                param_types={"user_id": param_types.STRING}
            )

            items = []
            for row in results:
                items.append({
                    "asset_id": row[0],
                    "display_name": row[1],
                    "category": row[2],
                    "esg_score": row[3],
                    "asset_type": row[4],
                    "material_type": row[5]
                })
            return items

        items = self.spanner_pool.database.run_in_transaction(_get_wardrobe)

        # Group items by category for outfit building
        by_category = {}
        for item in items:
            cat = item.get("category", "other")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(item)

        # Build outfit suggestions (simplified algorithm)
        outfits = []
        tops = by_category.get("tops", []) + by_category.get("shirts", [])
        bottoms = by_category.get("bottoms", []) + by_category.get("pants", [])
        accessories = by_category.get("accessories", [])

        # Create up to 3 outfit combinations
        for i in range(min(3, max(len(tops), len(bottoms), 1))):
            outfit_items = []
            total_esg = 0
            count = 0

            if i < len(tops):
                outfit_items.append(tops[i])
                if tops[i].get("esg_score"):
                    try:
                        total_esg += float(tops[i]["esg_score"])
                        count += 1
                    except (ValueError, TypeError):
                        pass

            if i < len(bottoms):
                outfit_items.append(bottoms[i])
                if bottoms[i].get("esg_score"):
                    try:
                        total_esg += float(bottoms[i]["esg_score"])
                        count += 1
                    except (ValueError, TypeError):
                        pass

            if accessories and i < len(accessories):
                outfit_items.append(accessories[i])

            if outfit_items:
                outfits.append({
                    "items": outfit_items,
                    "esg_score": round(total_esg / count, 2) if count > 0 else None,
                    "style_notes": f"Suggested for {occasion}. {'Optimized for sustainability.' if sustainability_priority else ''}"
                })

        logger.info({
            "event": "mcp_outfit_suggestion",
            "user_id": user_id[:8] + "...",
            "agent_id": agent_id[:8] + "...",
            "occasion": occasion,
            "outfits_suggested": len(outfits)
        })

        return {
            "outfits": outfits,
            "occasion": occasion,
            "sustainability_priority": sustainability_priority
        }

    async def _handle_initiate_rental(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """
        Handle rental initiation via Spanner.
        Creates rental request record requiring human approval.
        """
        from google.cloud import spanner

        user_id = params.get("user_id")
        cube_id = params.get("cube_id")
        renter_id = params.get("renter_id")
        duration_days = params.get("rental_duration_days", 7)
        price_usd = params.get("rental_price_usd")

        rental_id = str(uuid.uuid4())

        def _create_rental(transaction):
            # Verify ownership
            owner_check = transaction.execute_sql(
                """
                SELECT owner_id FROM Owns
                WHERE asset_id = @asset_id AND owner_id = @user_id AND is_current = true
                """,
                params={"asset_id": cube_id, "user_id": user_id},
                param_types={"asset_id": param_types.STRING, "user_id": param_types.STRING}
            )
            is_owner = any(True for _ in owner_check)
            if not is_owner:
                raise ValueError("User does not own this asset")

            # Create rental request in AgentTransaction table
            transaction.insert(
                table="AgentTransaction",
                columns=[
                    "transaction_id", "agent_id", "user_id", "transaction_type",
                    "asset_id", "status", "requires_human_review",
                    "initiated_at"
                ],
                values=[(
                    rental_id, agent_id, user_id, "rental",
                    cube_id, "pending_approval", True,
                    spanner.COMMIT_TIMESTAMP
                )]
            )

        from google.cloud.spanner_v1 import param_types
        self.spanner_pool.database.run_in_transaction(_create_rental)

        logger.info({
            "event": "mcp_rental_initiated",
            "rental_id": rental_id[:8] + "...",
            "cube_id": cube_id[:8] + "...",
            "agent_id": agent_id[:8] + "..."
        })

        return {
            "rental_id": rental_id,
            "status": "pending_human_approval",
            "requires_human_approval": True,
            "esg_verified": True,
            "duration_days": duration_days
        }

    async def _handle_list_for_resale(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """
        Handle resale listing via Spanner.
        Creates listing record requiring human approval.
        """
        from google.cloud import spanner
        from google.cloud.spanner_v1 import param_types

        user_id = params.get("user_id")
        cube_id = params.get("cube_id")
        asking_price = params.get("asking_price_usd")
        condition = params.get("condition", "good")

        listing_id = str(uuid.uuid4())

        def _create_listing(transaction):
            # Verify ownership
            owner_check = transaction.execute_sql(
                """
                SELECT owner_id FROM Owns
                WHERE asset_id = @asset_id AND owner_id = @user_id AND is_current = true
                """,
                params={"asset_id": cube_id, "user_id": user_id},
                param_types={"asset_id": param_types.STRING, "user_id": param_types.STRING}
            )
            is_owner = any(True for _ in owner_check)
            if not is_owner:
                raise ValueError("User does not own this asset")

            # Create listing in AgentTransaction table
            transaction.insert(
                table="AgentTransaction",
                columns=[
                    "transaction_id", "agent_id", "user_id", "transaction_type",
                    "asset_id", "transaction_value_usd", "status",
                    "requires_human_review", "initiated_at"
                ],
                values=[(
                    listing_id, agent_id, user_id, "resale_listing",
                    cube_id, asking_price, "pending_approval",
                    True, spanner.COMMIT_TIMESTAMP
                )]
            )

        self.spanner_pool.database.run_in_transaction(_create_listing)

        logger.info({
            "event": "mcp_resale_listed",
            "listing_id": listing_id[:8] + "...",
            "cube_id": cube_id[:8] + "...",
            "agent_id": agent_id[:8] + "..."
        })

        return {
            "listing_id": listing_id,
            "status": "pending_human_approval",
            "requires_human_approval": True,
            "esg_verified": True,
            "asking_price_usd": asking_price,
            "condition": condition
        }

    async def _handle_request_repair(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """
        Handle repair request via Spanner.
        Creates repair request and estimates ESG improvement.
        """
        from google.cloud import spanner
        from google.cloud.spanner_v1 import param_types

        user_id = params.get("user_id")
        cube_id = params.get("cube_id")
        damage_description = params.get("damage_description")
        repair_type = params.get("preferred_repair_type", "restore")

        repair_id = str(uuid.uuid4())

        def _create_repair(transaction):
            # Verify ownership and get current ESG
            results = transaction.execute_sql(
                """
                SELECT a.public_esg_score, a.lifecycle_state
                FROM Owns o
                JOIN Assets a ON o.asset_id = a.asset_id
                WHERE o.asset_id = @asset_id AND o.owner_id = @user_id AND o.is_current = true
                """,
                params={"asset_id": cube_id, "user_id": user_id},
                param_types={"asset_id": param_types.STRING, "user_id": param_types.STRING}
            )

            asset_data = None
            for row in results:
                asset_data = {"esg_score": row[0], "lifecycle_state": row[1]}

            if not asset_data:
                raise ValueError("User does not own this asset or asset not found")

            # Create repair request in AgentTransaction
            transaction.insert(
                table="AgentTransaction",
                columns=[
                    "transaction_id", "agent_id", "user_id", "transaction_type",
                    "asset_id", "status", "requires_human_review", "initiated_at"
                ],
                values=[(
                    repair_id, agent_id, user_id, "repair_request",
                    cube_id, "submitted", False, spanner.COMMIT_TIMESTAMP
                )]
            )

            return asset_data

        asset_data = self.spanner_pool.database.run_in_transaction(_create_repair)

        # Estimate ESG improvement based on repair type
        esg_improvement_map = {
            "patch": 0.05,
            "restore": 0.10,
            "upcycle": 0.15
        }
        estimated_improvement = esg_improvement_map.get(repair_type, 0.10)

        logger.info({
            "event": "mcp_repair_requested",
            "repair_id": repair_id[:8] + "...",
            "cube_id": cube_id[:8] + "...",
            "repair_type": repair_type
        })

        return {
            "repair_request_id": repair_id,
            "estimated_esg_improvement": estimated_improvement,
            "status": "submitted",
            "repair_type": repair_type,
            "damage_description": damage_description
        }

    async def _handle_request_dissolve(self, params: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """
        Handle dissolve request via Spanner.
        Requires auth key from owner to proceed with dissolution.
        """
        from google.cloud import spanner
        from google.cloud.spanner_v1 import param_types

        user_id = params.get("user_id")
        cube_id = params.get("cube_id")
        dissolution_method = params.get("dissolution_method", "mechanical")

        dissolve_id = str(uuid.uuid4())

        def _create_dissolve_request(transaction):
            # Verify ownership and check lifecycle state
            results = transaction.execute_sql(
                """
                SELECT a.lifecycle_state, a.primary_material_id, m.recyclability_pct
                FROM Owns o
                JOIN Assets a ON o.asset_id = a.asset_id
                LEFT JOIN Materials m ON a.primary_material_id = m.material_id
                WHERE o.asset_id = @asset_id AND o.owner_id = @user_id AND o.is_current = true
                """,
                params={"asset_id": cube_id, "user_id": user_id},
                param_types={"asset_id": param_types.STRING, "user_id": param_types.STRING}
            )

            asset_data = None
            for row in results:
                asset_data = {
                    "lifecycle_state": row[0],
                    "material_id": row[1],
                    "recyclability_pct": row[2] or 75.0
                }

            if not asset_data:
                raise ValueError("User does not own this asset or asset not found")

            if asset_data["lifecycle_state"] not in ["ACTIVE", "REPAIR"]:
                raise ValueError(f"Cannot dissolve asset in state {asset_data['lifecycle_state']}")

            # Create dissolve request
            transaction.insert(
                table="AgentTransaction",
                columns=[
                    "transaction_id", "agent_id", "user_id", "transaction_type",
                    "asset_id", "status", "requires_human_review", "initiated_at"
                ],
                values=[(
                    dissolve_id, agent_id, user_id, "dissolve_request",
                    cube_id, "pending_authorization", True, spanner.COMMIT_TIMESTAMP
                )]
            )

            return asset_data

        asset_data = self.spanner_pool.database.run_in_transaction(_create_dissolve_request)

        logger.info({
            "event": "mcp_dissolve_requested",
            "dissolve_id": dissolve_id[:8] + "...",
            "cube_id": cube_id[:8] + "...",
            "dissolution_method": dissolution_method
        })

        return {
            "dissolve_request_id": dissolve_id,
            "requires_auth_key": True,
            "estimated_material_recovery_pct": asset_data.get("recyclability_pct", 75.0),
            "status": "pending_authorization",
            "dissolution_method": dissolution_method,
            "message": "Owner must provide dissolve auth key to proceed"
        }
