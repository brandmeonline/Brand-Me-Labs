"""
Brand.Me v9 — Product Cube Data Models
=======================================

Defines the six faces of a Product Cube:
Brand.Me v9 — Product Cube Data Models

Defines the seven faces of a Product Cube:
1. Product Details (immutable, public)
2. Provenance (append-only, public)
3. Ownership (mutable, private)
4. Social Layer (mutable, public)
5. ESG & Impact (verified claims, public)
6. Lifecycle (mutable, authenticated)
7. Molecular Data (v9: material tracking for circular economy)
"""

from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum
from pydantic import BaseModel, Field
from uuid import UUID

# Enums

class FaceName(str, Enum):
    """Six faces of the Product Cube"""
    """Seven faces of the Product Cube (v9: added molecular_data)"""
    PRODUCT_DETAILS = "product_details"
    PROVENANCE = "provenance"
    OWNERSHIP = "ownership"
    SOCIAL_LAYER = "social_layer"
    ESG_IMPACT = "esg_impact"
    LIFECYCLE = "lifecycle"
    MOLECULAR_DATA = "molecular_data"  # v9: Material tracking for circular economy

class VisibilityLevel(str, Enum):
    """Visibility levels for face data"""
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    FRIENDS = "friends"
    PRIVATE = "private"
    CUSTOM = "custom"

class FaceStatus(str, Enum):
    """Status of face access after policy check"""
    VISIBLE = "visible"
    ESCALATED = "escalated_pending_human"
    DENIED = "denied"

class PolicyDecision(str, Enum):
    """Policy service decision"""
    ALLOW = "allow"
    ESCALATE = "escalate"
    DENY = "deny"

class TransferMethod(str, Enum):
    """Ownership transfer methods"""
    PURCHASE = "purchase"
    GIFT = "gift"
    INHERITANCE = "inheritance"
    TRADE = "trade"


class LifecycleState(str, Enum):
    """v9: DPP Lifecycle states for circular economy"""
    PRODUCED = "PRODUCED"    # Newly manufactured
    ACTIVE = "ACTIVE"        # In use by consumer
    REPAIR = "REPAIR"        # Under repair
    DISSOLVE = "DISSOLVE"    # Being dissolved for materials
    REPRINT = "REPRINT"      # Materials being reprinted into new product

# Face Data Models

class ProductDetailsData(BaseModel):
    """Product Details face data (immutable)"""
    product_id: str
    product_name: str
    brand_name: str
    model_version: str
    manufacturing_date: datetime
    serial_number: str
    specifications: Dict[str, Any]
    certifications: List[Dict[str, Any]]

class ProvenanceData(BaseModel):
    """Provenance face data (append-only)"""
    origin: Dict[str, Any]
    journey: Dict[str, Any]
    compliance: Dict[str, Any]
    environmental_impact: Dict[str, Any]

class OwnershipData(BaseModel):
    """Ownership face data (mutable, private)"""
    current_owner: Dict[str, Any]
    transfer_history: List[Dict[str, Any]]
    rights: Dict[str, Any]
    authentication: Dict[str, Any]

class SocialLayerData(BaseModel):
    """Social Layer face data (mutable, public)"""
    ratings: Dict[str, Any]
    reviews: List[Dict[str, Any]]
    influence: Dict[str, Any]
    moments: List[Dict[str, Any]]
    flex_score: float
    vibe: Dict[str, Any]

class ESGImpactData(BaseModel):
    """ESG & Impact face data (verified claims, public)"""
    environmental: Dict[str, Any]
    social: Dict[str, Any]
    governance: Dict[str, Any]
    sustainability_score: Dict[str, float]

class LifecycleData(BaseModel):
    """Lifecycle face data (mutable, authenticated)"""
    durability: Dict[str, Any]
    repairability: Dict[str, Any]
    repair_history: List[Dict[str, Any]]
    resale: Dict[str, Any]
    end_of_life: Dict[str, Any]


class MaterialComposition(BaseModel):
    """v9: Single material in product composition"""
    material_id: str
    material_type: str                     # e.g., "organic_cotton", "recycled_polyester"
    percentage: float                      # Percentage of total product
    esg_score: Optional[float] = None      # 0.0-1.0
    origin_region: Optional[str] = None
    certifications: List[str] = []
    is_recyclable: bool = True


class MolecularDataFace(BaseModel):
    """
    v9: Molecular Data face for circular economy tracking.

    Tracks material composition, tensile strength, dissolve authorization,
    and reprint lineage for the DPP lifecycle.
    """
    # Material composition
    materials: List[MaterialComposition]
    primary_material_id: str               # Main material for ESG verification

    # Physical properties
    tensile_strength_mpa: Optional[float] = None     # For durability tracking
    weight_grams: Optional[float] = None
    dimensions_cm: Optional[Dict[str, float]] = None  # width, height, depth

    # Circular economy tracking
    lifecycle_state: LifecycleState = LifecycleState.PRODUCED
    dissolve_authorized: bool = False
    dissolve_auth_key_hash: Optional[str] = None     # SHA-256 of auth key
    burn_proof_tx_hash: Optional[str] = None         # Midnight burn proof

    # Reprint lineage (for products made from dissolved materials)
    reprint_generation: int = 0                      # 0 = original, 1+ = reprinted
    parent_asset_id: Optional[str] = None            # If reprinted, link to parent
    dissolved_at: Optional[datetime] = None
    reprinted_at: Optional[datetime] = None

    # Biometric sync for AR glasses
    ar_sync_enabled: bool = True
    last_biometric_sync: Optional[datetime] = None
    sync_latency_ms: Optional[float] = None          # Target: <100ms


# Cube Face Model

class CubeFace(BaseModel):
    """A single face of the Product Cube with policy status"""
    face_name: FaceName
    status: FaceStatus
    visibility: VisibilityLevel
    data: Optional[Dict[str, Any]] = None
    blockchain_tx_hash: Optional[str] = None

    # Escalation fields (when status=escalated_pending_human)
    escalation_id: Optional[str] = None
    message: Optional[str] = None
    estimated_response_time: Optional[str] = None
    governance_console_url: Optional[str] = None

# Product Cube Model

class ProductCube(BaseModel):
    """Complete Product Cube with all faces"""
    cube_id: str
    owner_id: str
    created_at: datetime
    updated_at: datetime
    faces: Dict[FaceName, CubeFace]

# Request Models

class CreateCubeRequest(BaseModel):
    """Request to create a new Product Cube"""
    product_details: ProductDetailsData
    provenance: Optional[ProvenanceData] = None
    molecular_data: Optional[MolecularDataFace] = None  # v9: Material tracking
    owner_id: str
    initial_visibility: Dict[FaceName, VisibilityLevel]

class TransferOwnershipRequest(BaseModel):
    """Request to transfer ownership of a cube"""
    from_owner_id: str
    to_owner_id: str
    transfer_method: TransferMethod
    price: Optional[float] = None
    designer_royalty_amount: Optional[float] = None

# Response Models

class TransferResponse(BaseModel):
    """Response from ownership transfer"""
    status: str
    transfer_id: Optional[str] = None
    blockchain_tx_hash: Optional[str] = None
    new_owner_id: Optional[str] = None
    transfer_date: Optional[datetime] = None

    # Escalation fields
    escalation_id: Optional[str] = None
    message: Optional[str] = None
    estimated_approval_time: Optional[str] = None
    governance_console_url: Optional[str] = None


# v9: Lifecycle & Circular Economy Request Models

class LifecycleTransitionRequest(BaseModel):
    """v9: Request to transition lifecycle state"""
    new_state: LifecycleState
    triggered_by: str  # user_id or agent_id
    notes: Optional[str] = None
    esg_verification_required: bool = True


class DissolveAuthorizationRequest(BaseModel):
    """v9: Request to authorize dissolve for circular economy"""
    owner_id: str
    reason: str
    target_materials: Optional[List[str]] = None  # Specific materials to recover


class ReprintRequest(BaseModel):
    """v9: Request to reprint from dissolved materials"""
    parent_asset_id: str
    new_product_details: ProductDetailsData
    owner_id: str
    material_ids: List[str]
    burn_proof_tx_hash: Optional[str] = None  # Midnight burn proof from dissolve


class BiometricSyncRequest(BaseModel):
    """v9: Request to update biometric sync for AR glasses"""
    device_id: str
    sync_timestamp: datetime
    latency_ms: float


# v9: Lifecycle Response Models

class LifecycleTransitionResponse(BaseModel):
    """v9: Response from lifecycle transition"""
    status: str  # "success", "escalated", "denied"
    cube_id: str
    previous_state: LifecycleState
    new_state: LifecycleState
    transition_timestamp: Optional[datetime] = None
    esg_verified: bool = False

    # Escalation fields
    escalation_id: Optional[str] = None
    message: Optional[str] = None


class DissolveAuthorizationResponse(BaseModel):
    """v9: Response from dissolve authorization"""
    status: str
    cube_id: str
    auth_key_hash: Optional[str] = None  # For owner to authorize actual dissolve
    recoverable_materials: Optional[List[Dict[str, Any]]] = None
    estimated_value_usd: Optional[float] = None

    # Escalation fields
    escalation_id: Optional[str] = None
    message: Optional[str] = None
