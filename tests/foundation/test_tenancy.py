"""Organization tenancy protocol and context-resolution tests.

Ported from Lux tests/test_tenancy.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from brandme_foundation.tenancy.models import (
    AgentProfile,
    AgentProfileStatus,
    AuthenticatedPrincipal,
    MembershipResolution,
    MembershipResolutionError,
    MembershipResolutionStatus,
    MembershipRole,
    MembershipStatus,
    Organization,
    OrganizationCapability,
    OrganizationContextError,
    OrganizationContextErrorCode,
    OrganizationKind,
    OrganizationMembership,
    OrganizationStatus,
    PrincipalStatus,
    ResolvedOrganizationMembership,
    UserPrincipal,
    VerifiedHumanPrincipal,
    organization_context_from_resolution,
    resolve_organization_context,
)

NOW = datetime(2026, 8, 21, 12, tzinfo=UTC)


def _organization(**updates: Any) -> Organization:
    values: dict[str, Any] = {
        "organization_id": "org-brandme",
        "kind": OrganizationKind.BRAND,
        "name": "Lux Realty Team",
        "status": OrganizationStatus.ACTIVE,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(updates)
    return Organization.model_validate(values)


def _principal(**updates: Any) -> UserPrincipal:
    values: dict[str, Any] = {
        "principal_id": "principal-andrew",
        "issuer": "https://auth.brand.me/",
        "subject": "auth0|andrew",
        "status": PrincipalStatus.ACTIVE,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(updates)
    return UserPrincipal.model_validate(values)


def _membership(**updates: Any) -> OrganizationMembership:
    values: dict[str, Any] = {
        "membership_id": "membership-andrew-lux",
        "organization_id": "org-brandme",
        "principal_id": "principal-andrew",
        "role": MembershipRole.OWNER,
        "capabilities": (
            OrganizationCapability.ORGANIZATION_READ,
            OrganizationCapability.ASSETS_READ,
            OrganizationCapability.ASSETS_WRITE,
        ),
        "status": MembershipStatus.ACTIVE,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(updates)
    return OrganizationMembership.model_validate(values)


def _authenticated(**updates: Any) -> AuthenticatedPrincipal:
    values: dict[str, Any] = {
        "issuer": "https://auth.brand.me/",
        "subject": "auth0|andrew",
        "authentication_source": "verified_jwt",
    }
    values.update(updates)
    return AuthenticatedPrincipal.model_validate(values)


def test_tenancy_models_are_frozen_extra_forbid_and_deeply_immutable() -> None:
    membership = _membership()

    with pytest.raises(ValidationError):
        Organization.model_validate({**_organization().model_dump(), "unknown": True})

    mutable_membership: Any = membership
    with pytest.raises(ValidationError):
        mutable_membership.organization_id = "org-attacker"

    assert isinstance(membership.capabilities, tuple)
    with pytest.raises(AttributeError):
        mutable_membership.capabilities.append(OrganizationCapability.PROVENANCE_READ)

    with pytest.raises(ValidationError, match="unique"):
        _membership(
            capabilities=(
                OrganizationCapability.ASSETS_READ,
                OrganizationCapability.ASSETS_READ,
            )
        )


@pytest.mark.parametrize(
    ("issuer", "subject"),
    [
        ("http://auth.example.com", "subject"),
        ("https://user:password@auth.example.com", "subject"),
        ("https://auth.example.com?tenant=one", "subject"),
        (" https://auth.example.com", "subject"),
        ("https://auth.example.com", " subject"),
        ("https://auth.example.com", "subject\nother"),
    ],
)
def test_external_identity_requires_exact_https_issuer_and_opaque_subject(
    issuer: str,
    subject: str,
) -> None:
    with pytest.raises(ValidationError):
        AuthenticatedPrincipal(
            issuer=issuer,
            subject=subject,
            authentication_source="verified_jwt",
        )


def test_verified_human_identity_keeps_metadata_separate_from_authority() -> None:
    human = VerifiedHumanPrincipal(
        issuer="https://identity.example.test",
        subject="opaque-human-subject",
        authentication_source="oidc",
        email="mutable@example.test",
        email_verified=True,
        display_name="Pilot Owner",
    )
    assert human.authenticated_principal() == AuthenticatedPrincipal(
        issuer=human.issuer,
        subject=human.subject,
        authentication_source="verified_jwt",
    )
    assert "email" not in human.authenticated_principal().model_dump()

    with pytest.raises(ValidationError):
        VerifiedHumanPrincipal(
            issuer="https://identity.example.test",
            subject="opaque-human-subject",
            authentication_source="oidc",
            email=" attacker@example.test",
        )


# NOTE: Lux's `test_verified_identity_claims_do_not_promote_legacy_realtor_scope`
# is omitted here — it exercises services/api_gateway/auth.py, which is a
# later port wave (see docs/audit/LUX_LIFT_AND_SHIFT.md, Wave 2).


def test_active_persisted_membership_resolves_immutable_organization_context() -> None:
    profile = AgentProfile(
        agent_profile_id="agent-andrew",
        organization_id="org-brandme",
        principal_id="principal-andrew",
        display_name="Andrew",
        status=AgentProfileStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )

    context = resolve_organization_context(
        authenticated=_authenticated(),
        principal=_principal(),
        organization=_organization(),
        membership=_membership(),
        requested_organization_id="org-brandme",
        required_capabilities=(OrganizationCapability.ASSETS_WRITE,),
        agent_profile=profile,
    )

    assert context.organization_id == "org-brandme"
    assert context.principal_id == "principal-andrew"
    assert context.agent_profile_id == "agent-andrew"
    assert context.authority_source == "persisted_membership"
    assert context.capabilities == _membership().capabilities


def test_request_supplied_organization_can_never_create_authority() -> None:
    with pytest.raises(OrganizationContextError) as captured:
        resolve_organization_context(
            authenticated=_authenticated(),
            principal=_principal(),
            organization=_organization(),
            membership=_membership(),
            requested_organization_id="org-attacker",
        )

    assert str(captured.value) == "organization context unavailable"
    assert captured.value.code is OrganizationContextErrorCode.REQUESTED_ORGANIZATION_MISMATCH


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        (
            {"authenticated": _authenticated(subject="auth0|different")},
            OrganizationContextErrorCode.PRINCIPAL_IDENTITY_MISMATCH,
        ),
        (
            {"principal": _principal(status=PrincipalStatus.DISABLED)},
            OrganizationContextErrorCode.PRINCIPAL_INACTIVE,
        ),
        (
            {"organization": _organization(status=OrganizationStatus.SUSPENDED)},
            OrganizationContextErrorCode.ORGANIZATION_INACTIVE,
        ),
        (
            {"membership": _membership(status=MembershipStatus.REVOKED)},
            OrganizationContextErrorCode.MEMBERSHIP_INACTIVE,
        ),
    ],
)
def test_untrusted_or_inactive_authority_fails_with_non_enumerating_error(
    overrides: dict[str, Any],
    error_code: OrganizationContextErrorCode,
) -> None:
    arguments: dict[str, Any] = {
        "authenticated": _authenticated(),
        "principal": _principal(),
        "organization": _organization(),
        "membership": _membership(),
    }
    arguments.update(overrides)

    with pytest.raises(OrganizationContextError) as captured:
        resolve_organization_context(**arguments)

    assert str(captured.value) == "organization context unavailable"
    assert captured.value.code is error_code


def test_missing_capability_is_denied_without_changing_membership_authority() -> None:
    with pytest.raises(OrganizationContextError) as captured:
        resolve_organization_context(
            authenticated=_authenticated(),
            principal=_principal(),
            organization=_organization(),
            membership=_membership(),
            required_capabilities=(OrganizationCapability.PROVENANCE_WRITE,),
        )

    assert captured.value.code is OrganizationContextErrorCode.REQUIRED_CAPABILITY_MISSING


def test_membership_resolution_requires_server_derived_valid_selection() -> None:
    membership = ResolvedOrganizationMembership(
        organization_id="org-brandme",
        membership_id="membership-lux",
        role=MembershipRole.OWNER,
        capabilities=(OrganizationCapability.ASSETS_READ,),
        agent_profile_id="profile-lux",
    )
    resolution = MembershipResolution(
        status=MembershipResolutionStatus.RESOLVED,
        principal_id="opaque-random-principal",
        memberships=(membership,),
        selected_organization_id="org-brandme",
    )
    context = organization_context_from_resolution(resolution)
    assert context.organization_id == "org-brandme"
    assert context.principal_id == "opaque-random-principal"
    assert context.capabilities == (OrganizationCapability.ASSETS_READ,)


def test_unavailable_and_multiple_membership_results_fail_uniformly() -> None:
    unavailable = MembershipResolution(
        status=MembershipResolutionStatus.UNAVAILABLE,
        principal_id=None,
        memberships=(),
        selected_organization_id=None,
    )
    with pytest.raises(MembershipResolutionError, match="organization context unavailable"):
        organization_context_from_resolution(unavailable)

    memberships = tuple(
        ResolvedOrganizationMembership(
            organization_id=f"org-{suffix}",
            membership_id=f"membership-{suffix}",
            role=MembershipRole.STAFF,
            capabilities=(),
            agent_profile_id=None,
        )
        for suffix in ("a", "b")
    )
    selection = MembershipResolution(
        status=MembershipResolutionStatus.ORGANIZATION_SELECTION_REQUIRED,
        principal_id="opaque-random-principal",
        memberships=memberships,
        selected_organization_id=None,
    )
    with pytest.raises(MembershipResolutionError, match="organization context unavailable"):
        organization_context_from_resolution(selection)
