"""
Product Cube Data Models

Defines the six faces of a Product Cube:
1. Product Details (immutable, public)
2. Provenance (append-only, public)
3. Ownership (mutable, private)
4. Social Layer (mutable, public)
5. ESG & Impact (verified claims, public)
6. Lifecycle (mutable, authenticated)
"""

from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum
from pydantic import BaseModel, Field
from uuid import UUID

# Enums

class FaceName(str, Enum):
    """Six faces of the Product Cube"""
    PRODUCT_DETAILS = "product_details"
    PROVENANCE = "provenance"
    OWNERSHIP = "ownership"
    SOCIAL_LAYER = "social_layer"
    ESG_IMPACT = "esg_impact"
    LIFECYCLE = "lifecycle"

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
