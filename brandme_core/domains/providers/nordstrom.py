"""Nordstrom: link-only now; approved Impact publisher path gated (ch.05 §2, BM-PROV-001/002/003).

What is verified (2026-10-05): Nordstrom's official affiliate page routes
publishers through Impact [S14]. No public Nordstrom checkout/order API was
verified, so ``checkout.submit``/``orders.*``/``cart.*`` are ``unsupported``.

What is *not* in this file, on purpose: any Nordstrom or Impact endpoint URL,
request path or field name. Those come from the approved account's current
Impact documentation and are entered by an operator during setup [S15].
Until then every publisher capability is ``unconfigured`` with reason
``partner_approval_required`` — the explicit integration gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

from .contracts import HandoffLink, ProviderError, ProviderErrorKind
from .registry import CapabilityStatus, ProviderConnection
from .url_guard import UnsafeUrl

PROVIDER_ID = "nordstrom_impact"
DISPLAY_NAME = "Nordstrom via approved Impact publisher access"
OFFICIAL_PROGRAM_URL = "https://www.nordstrom.com/browse/affiliate-program"
IMPACT_PARTNER_DOCS = "https://integrations.impact.com/partner-api-reference"
ALLOWED_PRODUCT_HOSTS = ("www.nordstrom.com", "nordstrom.com")
CTA_LABEL = "Continue at Nordstrom"
LINK_DISCLOSURE = ("Checkout happens at Nordstrom. Brand.Me has not confirmed a purchase; "
                   "import your receipt after checkout to add it to your closet.")
AFFILIATE_DISCLOSURE = "Brand.Me may earn a commission from this link. It does not affect your style matches."

ACCESS_LEVELS = ("unconfigured", "link_only", "approved_publisher", "contracted_commerce")

# Configuration *names* only. Values live in Secret Manager / operator config.
CONFIG_NAMES = (
    "NORDSTROM_IMPACT_ACCOUNT_REF",        # approved Impact publisher account reference
    "NORDSTROM_IMPACT_CREDENTIAL_SECRET",  # Secret Manager resource name (write-only in console)
    "NORDSTROM_IMPACT_CAMPAIGN_REF",       # Nordstrom program/campaign reference in Impact
    "NORDSTROM_IMPACT_CATALOG_REF",        # enabled catalog reference, if granted
)

DATA_USE_RIGHTS = (
    "display_images", "cache_images", "transform_images", "retain_prices",
    "affiliate_tracking", "derive_3d_or_ai",
)

GATED_CAPABILITIES = ("catalog.feed", "catalog.search", "catalog.detail", "catalog.images",
                      "affiliate.attribution")
UNSUPPORTED_CAPABILITIES = ("cart.create", "cart.update", "checkout.submit", "orders.read",
                            "orders.webhook", "returns.request", "refunds.read", "inventory.read",
                            "price.quote")


@dataclass(frozen=True)
class ChecklistItem:
    key: str
    section: str  # enables | prerequisites | credentials | data_use | tests | activation
    label: str
    done: bool
    action: str


@dataclass
class NordstromSetup:
    """Operator setup state. Saving partial setup never enables a capability."""

    access_level: str = "unconfigured"
    program_application_opened: bool = False
    impact_approval_recorded_by: Optional[str] = None  # operator id that recorded approval evidence
    approval_evidence_ref: Optional[str] = None
    account_ref: Optional[str] = None
    credential_secret_ref: Optional[str] = None  # Secret Manager name, never a value
    credential_rotated_at: Optional[datetime] = None
    catalog_ref: Optional[str] = None
    endpoint_descriptor_ref: Optional[str] = None  # operator-entered from approved-account docs
    data_use: Dict[str, Optional[bool]] = field(default_factory=lambda: {k: None for k in DATA_USE_RIGHTS})
    read_only_test_evidence: Optional[str] = None
    staging_review_by: Optional[str] = None
    countries: Tuple[str, ...] = ("US",)

    def checklist(self) -> List[ChecklistItem]:
        rights_done = all(v is not None for v in self.data_use.values())
        return [
            ChecklistItem("enables", "enables",
                          "Link-only saves now; approved catalog, imagery and affiliate links after approval", True,
                          "No action — informational"),
            ChecklistItem("apply", "prerequisites", "Apply to the Nordstrom program through Impact",
                          self.program_application_opened, f"Open {OFFICIAL_PROGRAM_URL} in a new tab; apply manually"),
            ChecklistItem("approval", "prerequisites", "Nordstrom approval recorded with evidence",
                          bool(self.impact_approval_recorded_by and self.approval_evidence_ref),
                          "Record the approval reference after Nordstrom accepts the publisher account"),
            ChecklistItem("catalog", "prerequisites", "Catalog enabled for this publisher account",
                          bool(self.catalog_ref), "Enter the enabled catalog reference from Impact"),
            ChecklistItem("endpoint", "prerequisites", "Endpoint/field schema confirmed from current Impact docs",
                          bool(self.endpoint_descriptor_ref), f"Use {IMPACT_PARTNER_DOCS} for the approved account"),
            ChecklistItem("account", "credentials", "Impact account reference stored",
                          bool(self.account_ref), "Enter NORDSTROM_IMPACT_ACCOUNT_REF"),
            ChecklistItem("secret", "credentials", "Credential stored in Secret Manager (write-only)",
                          bool(self.credential_secret_ref), "Enter NORDSTROM_IMPACT_CREDENTIAL_SECRET"),
            ChecklistItem("rights", "data_use", "Permitted data use marked for every right", rights_done,
                          "Mark display/cache/transform images, retain prices, affiliate tracking, derived 3D/AI"),
            ChecklistItem("test", "tests", "Read-only bounded catalog test passed",
                          bool(self.read_only_test_evidence), "Run the read-only test after credentials"),
            ChecklistItem("staging", "activation", "Staging ingestion reviewed by an operator",
                          bool(self.staging_review_by), "Inspect example records, then activate"),
        ]

    def missing(self) -> List[ChecklistItem]:
        return [i for i in self.checklist() if not i.done]


def connection(environment: str, setup: Optional[NordstromSetup] = None) -> ProviderConnection:
    setup = setup or NordstromSetup()
    ready = not setup.missing()
    caps: Dict[str, CapabilityStatus] = {}
    for name in GATED_CAPABILITIES:
        caps[name] = CapabilityStatus(
            name, "unconfigured",
            "partner_approval_required" if not ready else "activation_pending_verification")
    for name in UNSUPPORTED_CAPABILITIES:
        caps[name] = CapabilityStatus(name, "unsupported", "no_verified_public_checkout_access"
                                      if name.startswith(("checkout", "cart", "orders")) else "not_offered_by_access_level")
    caps["checkout.handoff"] = CapabilityStatus("checkout.handoff", "unconfigured", "link_only_member_supplied_url")
    return ProviderConnection(
        provider_id=PROVIDER_ID, display_name=DISPLAY_NAME, environment=environment, simulation=False,
        country_codes=setup.countries,
        disclosure="Retailer checkout occurs outside Brand.Me until richer authorized access is verified.",
        capabilities=caps, access_level="link_only" if setup.access_level == "unconfigured" else setup.access_level,
        operator_account_ref=setup.account_ref, credential_ref=setup.credential_secret_ref,
        data_use={k: bool(v) for k, v in setup.data_use.items()},
        allowed_redirect_hosts=ALLOWED_PRODUCT_HOSTS, adapter=ImpactPublisherCatalogAdapter(setup))


@dataclass(frozen=True)
class SavedRetailerLink:
    url: str
    cta: HandoffLink
    purchase_state: str  # always "not_confirmed" until receipt/order evidence
    metadata_source: str  # "member_entered"


def save_link_only(url: str, *, member_title: Optional[str] = None) -> SavedRetailerLink:
    """Link-only level: validate a member-supplied Nordstrom URL. No fetch, no scraping."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or host not in ALLOWED_PRODUCT_HOSTS or parts.username or parts.password \
            or parts.port not in (None, 443):
        raise UnsafeUrl("only https://www.nordstrom.com product links are accepted")
    clean = urlunsplit(("https", host, parts.path or "/", parts.query, ""))
    return SavedRetailerLink(
        url=clean,
        cta=HandoffLink(clean, CTA_LABEL, LINK_DISCLOSURE, affiliate=False),
        purchase_state="not_confirmed", metadata_source="member_entered")


class ImpactPublisherCatalogAdapter:
    """Approved-publisher catalog adapter shell.

    Normalization is implemented and tested with fictional records; the network
    call is deliberately absent until an approved account supplies a verified
    endpoint descriptor. Calling it before then is ``not_configured``.
    """

    provider_id = PROVIDER_ID

    def __init__(self, setup: NordstromSetup):
        self.setup = setup

    def feed_page(self, cursor: Optional[str]):
        raise ProviderError(ProviderErrorKind.NOT_CONFIGURED,
                            "Nordstrom/Impact publisher access not approved for this deployment")

    def search(self, query: str, *, cursor: Optional[str] = None, limit: int = 24):
        raise ProviderError(ProviderErrorKind.NOT_CONFIGURED, "no approved Nordstrom catalog")

    def detail(self, source_product_id: str):
        raise ProviderError(ProviderErrorKind.NOT_CONFIGURED, "no approved Nordstrom catalog")
