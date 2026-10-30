"""Nordstrom: link-only now; approved Impact publisher path gated (ch.05 §2, BM-PROV-001/002/003).

What is verified (2026-10-05): Nordstrom's official affiliate page routes
publishers through Impact [S14]. No public Nordstrom checkout/order API was
verified, so ``checkout.submit``/``orders.*``/``cart.*`` are ``unsupported``.

What is *not* in this file, on purpose: any Nordstrom or Impact endpoint URL,
request path or field name. Those come from the approved account's current
Impact documentation and are entered by an operator during setup [S15].
Until then every publisher capability is ``unconfigured`` with reason
``partner_approval_required`` — the explicit integration gate.

Connection tests (``probe``) make no network call. ``checkout.handoff`` checks
the link-only URL rules locally (``link_validation``, which can never verify a
capability); every publisher capability is ``blocked`` until approval evidence
and a credential reference are recorded, and then still ``blocked`` because the
Impact API client is not built.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

from .contracts import HandoffLink, ProbeResult, ProviderError, ProviderErrorKind, SetupField, SetupProfile
from .registry import CapabilityStatus, ProviderConnection
from .url_guard import UnsafeUrl, validate_redirect

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
_GATED = frozenset(GATED_CAPABILITIES)
_CATALOG = frozenset(c for c in GATED_CAPABILITIES if c.startswith("catalog."))

# The operator setup console's checklist for this provider (brandme_core.domains.providers.setup).
SETUP_PROFILE = SetupProfile(
    summary=("Link-only now: a member saves a nordstrom.com product link and continues at Nordstrom; Brand.Me "
             "does not confirm the purchase. After Nordstrom approves the publisher account through Impact: "
             "authorized catalog data, approved imagery and affiliate links, within the agreement's data-use "
             "rights. No in-app cart, checkout, order, inventory or return operation is offered."),
    access_levels=ACCESS_LEVELS,
    approval_levels=frozenset({"approved_publisher", "contracted_commerce"}),
    gated_capabilities=_GATED,
    fields=(
        SetupField("access_level", "prerequisites", "Authorized access level chosen", "access_level",
                   "Choose link-only until Nordstrom approves the publisher account"),
        SetupField("apply", "prerequisites", "Applied to the Nordstrom program through Impact",
                   "program_application_opened",
                   f"Open {OFFICIAL_PROGRAM_URL} in a new tab and apply manually; Brand.Me never applies for the company",
                   _GATED),
        SetupField("approval", "prerequisites", "Nordstrom approval recorded with evidence", "approval_evidence_ref",
                   "Record the approval reference after Nordstrom accepts the publisher account", _GATED, ("apply",)),
        SetupField("catalog", "prerequisites", "Catalog enabled for this publisher account", "catalog_ref",
                   "Enter the enabled catalog reference from Impact (NORDSTROM_IMPACT_CATALOG_REF)", _CATALOG,
                   ("approval",)),
        SetupField("endpoint", "prerequisites", "Endpoints and field schema confirmed for the approved account",
                   "endpoint_descriptor_ref",
                   f"Confirm them in {IMPACT_PARTNER_DOCS} for the approved account, then enter the descriptor reference",
                   _GATED, ("approval",)),
        SetupField("account", "credentials", "Impact account reference stored", "account_ref",
                   "Enter NORDSTROM_IMPACT_ACCOUNT_REF for the approved publisher account", _GATED, ("approval",)),
        SetupField("secret", "credentials", "Credential stored in Secret Manager (write-only)",
                   "credential_secret_ref",
                   "Store the Impact credential in Secret Manager, then enter its resource name "
                   "(NORDSTROM_IMPACT_CREDENTIAL_SECRET)", _GATED, ("approval",)),
    ),
    data_use_rights=DATA_USE_RIGHTS,
    data_use_required_for=_GATED,
)


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
    setup_profile = SETUP_PROFILE

    def __init__(self, setup: NordstromSetup):
        self.setup = setup

    def apply_setup(self, values: Mapping[str, Any]) -> None:
        """Saved operator setup (server-only values) from the setup service."""
        s = self.setup
        for name in ("access_level", "program_application_opened", "approval_evidence_ref", "account_ref",
                     "credential_secret_ref", "credential_rotated_at", "catalog_ref", "endpoint_descriptor_ref"):
            if name in values:
                setattr(s, name, values[name])
        if "approval_recorded_by" in values:
            s.impact_approval_recorded_by = values["approval_recorded_by"]
        for right, allowed in dict(values.get("data_use") or {}).items():
            if right in s.data_use:
                s.data_use[right] = bool(allowed)

    def probe(self, capability: str, mode: str, now: datetime) -> ProbeResult:
        """Connection test. No network call is made by any branch."""
        if capability == "checkout.handoff" and mode == "read_only_test":
            return self._probe_handoff(now)
        if capability in GATED_CAPABILITIES:
            if not (self.setup.approval_evidence_ref and self.setup.credential_secret_ref):
                return ProbeResult("blocked", "none", "blocked:publisher_approval_required",
                                   "Record Nordstrom/Impact approval evidence and store the Impact credential "
                                   "reference first. No request was sent.", "publisher_approval_required")
            return ProbeResult("blocked", "none", "blocked:impact_api_client_not_built",
                               "The Impact publisher API client is not built yet; it is built from the approved "
                               "account's current Impact documentation. No request was sent.",
                               "impact_api_client_not_built")
        return ProbeResult("blocked", "none", "blocked:no_read_only_probe",
                           f"There is no {mode.replace('_', ' ')} for {capability}. No request was sent.",
                           "no_read_only_probe")

    @staticmethod
    def _probe_handoff(now: datetime) -> ProbeResult:
        ref = f"linkcheck:{PROVIDER_ID}:checkout.handoff:{now.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}"
        sample = "https://www.nordstrom.com/s/link-check"
        refused = 0
        for bad in ("http://www.nordstrom.com/s/link-check", "https://nordstrom.com.example.invalid/s/link-check",
                    "https://www.nordstrom.com:8443/s/link-check", "https://user:pw@www.nordstrom.com/s/link-check"):
            try:
                save_link_only(bad)
            except UnsafeUrl:
                refused += 1
        try:
            ok = validate_redirect(save_link_only(sample).url, ALLOWED_PRODUCT_HOSTS) == sample and refused == 4
        except UnsafeUrl:
            ok = False
        note = ("Nothing was sent to Nordstrom. Link validation proves URL safety only; it cannot verify checkout, "
                "orders or feed access.")
        if not ok:
            return ProbeResult("failed", "link_validation", ref, f"The link-only URL rules did not hold. {note}",
                               "link_rules_failed")
        return ProbeResult("passed", "link_validation", ref,
                           "Link-only handoff rules checked locally: an https://www.nordstrom.com product link is "
                           f"accepted; plain http, other hosts, credentials and non-standard ports are refused. {note}")

    def feed_page(self, cursor: Optional[str]):
        raise ProviderError(ProviderErrorKind.NOT_CONFIGURED,
                            "Nordstrom/Impact publisher access not approved for this deployment")

    def search(self, query: str, *, cursor: Optional[str] = None, limit: int = 24):
        raise ProviderError(ProviderErrorKind.NOT_CONFIGURED, "no approved Nordstrom catalog")

    def detail(self, source_product_id: str):
        raise ProviderError(ProviderErrorKind.NOT_CONFIGURED, "no approved Nordstrom catalog")
