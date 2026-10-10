"""Organization-tenancy contracts and trusted context resolution.

These models establish the Brand.Me identity boundary without activating a
database-backed membership lookup.  Authentication proves an external
``(issuer, subject)`` pair; an active persisted membership will authorize an
organization in a later vertical slice.  A request-supplied organization ID is
therefore only a selector and can never create authority.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, NoReturn
from urllib.parse import urlsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


Identifier = str


class OrganizationKind(StrEnum):
    BRAND = "brand"
    RETAILER = "retailer"
    INDIVIDUAL = "individual"


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class PrincipalStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class MembershipRole(StrEnum):
    OWNER = "owner"
    CUSTODIAN = "custodian"
    STAFF = "staff"
    OPS = "ops"
    READONLY = "readonly"


class MembershipStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class AgentProfileStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class OrganizationCapability(StrEnum):
    ORGANIZATION_READ = "organization.read"
    ORGANIZATION_MANAGE = "organization.manage"
    MEMBERSHIPS_READ = "memberships.read"
    MEMBERSHIPS_MANAGE = "memberships.manage"
    ASSETS_READ = "assets.read"
    ASSETS_WRITE = "assets.write"
    PROVENANCE_READ = "provenance.read"
    PROVENANCE_WRITE = "provenance.write"
    CONSENT_READ = "consent.read"
    CONSENT_MANAGE = "consent.manage"
    WORKFLOWS_READ = "workflows.read"
    WORKFLOWS_WRITE = "workflows.write"
    OPERATIONS_READ = "operations.read"


class Organization(_Base):
    organization_id: Identifier = Field(min_length=1, max_length=128)
    kind: OrganizationKind
    name: str = Field(min_length=1, max_length=200)
    status: OrganizationStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def timestamps_are_ordered(self) -> Organization:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot predate created_at")
        return self


class _ExternalIdentity(_Base):
    issuer: str = Field(min_length=1, max_length=512)
    subject: str = Field(min_length=1, max_length=512)

    @field_validator("issuer")
    @classmethod
    def issuer_is_exact_https_origin_or_path(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("issuer must not contain surrounding whitespace")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("issuer must be an exact credential-free HTTPS URL")
        return value

    @field_validator("subject")
    @classmethod
    def subject_is_opaque_and_nonempty(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("subject must be an exact nonempty opaque identifier")
        return value


class AuthenticatedPrincipal(_ExternalIdentity):
    """External identity claims already verified by the authentication layer."""

    authentication_source: Literal["verified_jwt"]


class VerifiedHumanPrincipal(_ExternalIdentity):
    """Provider-neutral human identity proven by an OIDC ID token.

    Email and display name are optional provider metadata.  They never replace
    the immutable ``(issuer, subject)`` identity key and never establish
    organization authority.
    """

    authentication_source: Literal["oidc"]
    subject: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    email_verified: bool | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("email", "display_name")
    @classmethod
    def optional_metadata_is_exact(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("human identity metadata must be exact and printable")
        return value

    def authenticated_principal(self) -> AuthenticatedPrincipal:
        """Narrow to the established persistence-resolver input contract."""

        return AuthenticatedPrincipal(
            issuer=self.issuer,
            subject=self.subject,
            authentication_source="verified_jwt",
        )


class PilotIdentityCaptureReceipt(_Base):
    """Non-disclosing receipt for the one-time pilot identity handoff."""

    status: Literal["captured"]
    correlation_id: str = Field(min_length=16, max_length=128)
    issuer_secret_version: str = Field(min_length=1, max_length=512)
    subject_secret_version: str = Field(min_length=1, max_length=512)


class PilotIdentityCaptureReadiness(_Base):
    """Non-disclosing readiness signal for the temporary pilot action."""

    status: Literal["ready"]


class UserPrincipal(_ExternalIdentity):
    principal_id: Identifier = Field(min_length=1, max_length=128)
    status: PrincipalStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def timestamps_are_ordered(self) -> UserPrincipal:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot predate created_at")
        return self


class OrganizationMembership(_Base):
    membership_id: Identifier = Field(min_length=1, max_length=128)
    organization_id: Identifier = Field(min_length=1, max_length=128)
    principal_id: Identifier = Field(min_length=1, max_length=128)
    role: MembershipRole
    capabilities: tuple[OrganizationCapability, ...]
    status: MembershipStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("capabilities")
    @classmethod
    def capabilities_are_unique(
        cls, value: tuple[OrganizationCapability, ...]
    ) -> tuple[OrganizationCapability, ...]:
        if len(value) != len(set(value)):
            raise ValueError("membership capabilities must be unique")
        return value

    @model_validator(mode="after")
    def timestamps_are_ordered(self) -> OrganizationMembership:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot predate created_at")
        return self


class AgentProfile(_Base):
    agent_profile_id: Identifier = Field(min_length=1, max_length=128)
    organization_id: Identifier = Field(min_length=1, max_length=128)
    principal_id: Identifier | None = Field(default=None, min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)
    status: AgentProfileStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def timestamps_are_ordered(self) -> AgentProfile:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot predate created_at")
        return self


class OrganizationContext(_Base):
    """Immutable organization authority derived from a persisted membership."""

    context_version: Literal["organization_context_v1"]
    authority_source: Literal["persisted_membership"]
    organization_id: Identifier = Field(min_length=1, max_length=128)
    principal_id: Identifier = Field(min_length=1, max_length=128)
    membership_id: Identifier = Field(min_length=1, max_length=128)
    agent_profile_id: Identifier | None = Field(default=None, min_length=1, max_length=128)
    role: MembershipRole
    capabilities: tuple[OrganizationCapability, ...]


class ResolvedOrganizationMembership(_Base):
    """One active organization choice returned by the pre-tenant resolver."""

    organization_id: Identifier = Field(min_length=1, max_length=128)
    membership_id: Identifier = Field(min_length=1, max_length=128)
    role: MembershipRole
    capabilities: tuple[OrganizationCapability, ...]
    agent_profile_id: Identifier | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("capabilities")
    @classmethod
    def resolved_capabilities_are_unique(
        cls, value: tuple[OrganizationCapability, ...]
    ) -> tuple[OrganizationCapability, ...]:
        if len(value) != len(set(value)):
            raise ValueError("resolved membership capabilities must be unique")
        return value


class MembershipResolutionStatus(StrEnum):
    UNAVAILABLE = "unavailable"
    ORGANIZATION_SELECTION_REQUIRED = "organization_selection_required"
    RESOLVED = "resolved"


class MembershipResolution(_Base):
    """Non-enumerating result derived only from a verified external identity."""

    status: MembershipResolutionStatus
    principal_id: Identifier | None = Field(default=None, min_length=1, max_length=128)
    memberships: tuple[ResolvedOrganizationMembership, ...]
    selected_organization_id: Identifier | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def status_matches_memberships(self) -> MembershipResolution:
        organization_ids = [item.organization_id for item in self.memberships]
        if len(organization_ids) != len(set(organization_ids)):
            raise ValueError("resolved organization memberships must be unique")
        if self.status is MembershipResolutionStatus.UNAVAILABLE:
            if self.principal_id is not None or self.memberships or self.selected_organization_id:
                raise ValueError("unavailable resolution cannot expose identity state")
        elif self.principal_id is None or not self.memberships:
            raise ValueError("available resolution requires principal and memberships")
        elif self.status is MembershipResolutionStatus.ORGANIZATION_SELECTION_REQUIRED:
            if len(self.memberships) < 2 or self.selected_organization_id is not None:
                raise ValueError("organization selection state is inconsistent")
        elif self.selected_organization_id not in set(organization_ids):
            raise ValueError("resolved organization selection is not allowed")
        return self


class MembershipResolutionErrorCode(StrEnum):
    UNAVAILABLE = "unavailable"
    ORGANIZATION_SELECTION_REQUIRED = "organization_selection_required"
    REQUESTED_ORGANIZATION_NOT_ALLOWED = "requested_organization_not_allowed"


class MembershipResolutionError(PermissionError):
    """Publicly uniform resolution failure with an internal diagnostic code."""

    def __init__(self, code: MembershipResolutionErrorCode) -> None:
        super().__init__("organization context unavailable")
        self.code = code


def organization_context_from_resolution(
    resolution: MembershipResolution,
) -> OrganizationContext:
    """Create tenant authority only from a successful server-derived selection."""

    if resolution.status is MembershipResolutionStatus.UNAVAILABLE:
        raise MembershipResolutionError(MembershipResolutionErrorCode.UNAVAILABLE)
    if resolution.status is MembershipResolutionStatus.ORGANIZATION_SELECTION_REQUIRED:
        raise MembershipResolutionError(
            MembershipResolutionErrorCode.ORGANIZATION_SELECTION_REQUIRED
        )
    assert resolution.principal_id is not None
    assert resolution.selected_organization_id is not None
    selected = next(
        item
        for item in resolution.memberships
        if item.organization_id == resolution.selected_organization_id
    )
    return OrganizationContext(
        context_version="organization_context_v1",
        authority_source="persisted_membership",
        organization_id=selected.organization_id,
        principal_id=resolution.principal_id,
        membership_id=selected.membership_id,
        agent_profile_id=selected.agent_profile_id,
        role=selected.role,
        capabilities=selected.capabilities,
    )


class OrganizationContextErrorCode(StrEnum):
    PRINCIPAL_IDENTITY_MISMATCH = "principal_identity_mismatch"
    PRINCIPAL_INACTIVE = "principal_inactive"
    ORGANIZATION_INACTIVE = "organization_inactive"
    MEMBERSHIP_PRINCIPAL_MISMATCH = "membership_principal_mismatch"
    MEMBERSHIP_ORGANIZATION_MISMATCH = "membership_organization_mismatch"
    MEMBERSHIP_INACTIVE = "membership_inactive"
    REQUESTED_ORGANIZATION_MISMATCH = "requested_organization_mismatch"
    REQUIRED_CAPABILITY_MISSING = "required_capability_missing"
    AGENT_PROFILE_MISMATCH = "agent_profile_mismatch"
    AGENT_PROFILE_INACTIVE = "agent_profile_inactive"


class OrganizationContextError(PermissionError):
    """Non-enumerating authorization failure with an internal diagnostic code."""

    def __init__(self, code: OrganizationContextErrorCode) -> None:
        super().__init__("organization context unavailable")
        self.code = code


def _deny(code: OrganizationContextErrorCode) -> NoReturn:
    raise OrganizationContextError(code)


def resolve_organization_context(
    *,
    authenticated: AuthenticatedPrincipal,
    principal: UserPrincipal,
    organization: Organization,
    membership: OrganizationMembership,
    requested_organization_id: str | None = None,
    required_capabilities: tuple[OrganizationCapability, ...] = (),
    agent_profile: AgentProfile | None = None,
) -> OrganizationContext:
    """Resolve trusted organization authority without consulting request claims.

    Repository-backed lookup is intentionally outside this pure seam.  Callers
    must load ``principal``, ``organization`` and ``membership`` from the
    authoritative store using the verified external identity.  A body/path
    organization ID can narrow that authority but can never replace it.
    """

    if (authenticated.issuer, authenticated.subject) != (
        principal.issuer,
        principal.subject,
    ):
        _deny(OrganizationContextErrorCode.PRINCIPAL_IDENTITY_MISMATCH)
    if principal.status is not PrincipalStatus.ACTIVE:
        _deny(OrganizationContextErrorCode.PRINCIPAL_INACTIVE)
    if organization.status is not OrganizationStatus.ACTIVE:
        _deny(OrganizationContextErrorCode.ORGANIZATION_INACTIVE)
    if membership.principal_id != principal.principal_id:
        _deny(OrganizationContextErrorCode.MEMBERSHIP_PRINCIPAL_MISMATCH)
    if membership.organization_id != organization.organization_id:
        _deny(OrganizationContextErrorCode.MEMBERSHIP_ORGANIZATION_MISMATCH)
    if membership.status is not MembershipStatus.ACTIVE:
        _deny(OrganizationContextErrorCode.MEMBERSHIP_INACTIVE)
    if (
        requested_organization_id is not None
        and requested_organization_id != organization.organization_id
    ):
        _deny(OrganizationContextErrorCode.REQUESTED_ORGANIZATION_MISMATCH)
    if not set(required_capabilities).issubset(membership.capabilities):
        _deny(OrganizationContextErrorCode.REQUIRED_CAPABILITY_MISSING)

    profile_id: str | None = None
    if agent_profile is not None:
        if (
            agent_profile.organization_id != organization.organization_id
            or (
                agent_profile.principal_id is not None
                and agent_profile.principal_id != principal.principal_id
            )
        ):
            _deny(OrganizationContextErrorCode.AGENT_PROFILE_MISMATCH)
        if agent_profile.status is not AgentProfileStatus.ACTIVE:
            _deny(OrganizationContextErrorCode.AGENT_PROFILE_INACTIVE)
        profile_id = agent_profile.agent_profile_id

    return OrganizationContext(
        context_version="organization_context_v1",
        authority_source="persisted_membership",
        organization_id=organization.organization_id,
        principal_id=principal.principal_id,
        membership_id=membership.membership_id,
        agent_profile_id=profile_id,
        role=membership.role,
        capabilities=membership.capabilities,
    )
