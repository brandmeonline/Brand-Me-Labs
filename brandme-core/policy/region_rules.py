"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Region Rules Module
===================

Enforces region-specific data access policies and legal compliance.

Handles:
- GDPR compliance (EU regions)
- CCPA compliance (California, US)
- Data localization requirements
- Regional content restrictions
- Legal hold / embargo enforcement
"""

import os
from typing import Literal, Optional, Union
import yaml
from pathlib import Path

ScopeLevel = Literal["public", "friends_only", "private"]


class RegionRulesEngine:
    """
    Manages region-specific rules and policies.

    Loads rules from YAML files in brandme-core/policies/region/
    """

    def __init__(self, policies_dir: Optional[str] = None):
        """
        Initialize the region rules engine.

        Args:
            policies_dir: Path to policies directory. Defaults to ../policies/region/
        """
        if policies_dir is None:
            # Default to policies/region/ relative to this file
            current_dir = Path(__file__).parent
            policies_dir = str(current_dir.parent / "policies" / "region")

        self.policies_dir = Path(policies_dir)
        self.region_policies: dict[str, dict] = {}
        self._load_policies()

    def _load_policies(self):
        """
        Load all region policy YAML files.

        Expected file structure:
        policies/region/us-east1.yaml
        policies/region/eu-west1.yaml
        etc.
        """
        if not self.policies_dir.exists():
            # No policies loaded - will use defaults
            return

        for yaml_file in self.policies_dir.glob("*.yaml"):
            try:
                with open(yaml_file, 'r') as f:
                    policy = yaml.safe_load(f)
                    region_code = yaml_file.stem  # filename without .yaml
                    self.region_policies[region_code] = policy
            except Exception:
                # Skip invalid policy files
                continue

    def is_allowed(
        self,
        region_code: str,
        scope: ScopeLevel
    ) -> Union[bool, Literal["escalate"]]:
        """
        Determine if data access is allowed based on region and scope.

        Args:
            region_code: Geographic region code (e.g., "us-east1", "eu-west1")
            scope: Resolved consent scope ("public", "friends_only", "private")

        Returns:
            True: Access allowed
            False: Access denied
            "escalate": Requires human review

        Region-specific logic:
        - EU regions: Check GDPR compliance, may require explicit consent
        - California: Check CCPA opt-out status
        - Embargoed regions: Always deny or escalate
        - Default: Allow public data, escalate private data
        """
        # Get region policy or use default
        policy = self.region_policies.get(region_code, {})

        # Check if region is under embargo or legal hold
        if policy.get("embargo", False):
            return False

        if policy.get("requires_human_review", False):
            return "escalate"

        # GDPR-specific logic for EU regions
        if policy.get("gdpr_applies", False):
            # For GDPR regions, private data requires explicit consent
            # which we check via consent_rules
            # Here we just enforce the minimum: public is OK, private escalates
            if scope == "private":
                return "escalate"
            # friends_only and public are allowed
            return True

        # CCPA-specific logic for California (us-west*)
        if region_code.startswith("us-west") and policy.get("ccpa_applies", False):
            # Similar to GDPR - escalate private data
            if scope == "private":
                return "escalate"
            return True

        # Default logic: Allow public, escalate private
        if scope == "public":
            return True
        elif scope == "friends_only":
            return True
        elif scope == "private":
            # Private data requires additional checks in production
            # For MVP, we escalate to be safe
            return "escalate"

        # Unknown scope - deny by default
        return False


# Global instance
_engine: Optional[RegionRulesEngine] = None


def get_engine() -> RegionRulesEngine:
    """Get or create the global RegionRulesEngine instance."""
    global _engine
    if _engine is None:
        _engine = RegionRulesEngine()
    return _engine


def is_allowed(
    region_code: str,
    scope: ScopeLevel
) -> Union[bool, Literal["escalate"]]:
    """
    Check if data access is allowed based on region and scope.

    This is a convenience function that delegates to the global RegionRulesEngine.

    Args:
        region_code: Geographic region code (e.g., "us-east1", "eu-west1")
        scope: Resolved consent scope ("public", "friends_only", "private")

    Returns:
        True: Access allowed
        False: Access denied
        "escalate": Requires human review

    Examples:
        >>> is_allowed("us-east1", "public")
        True
        >>> is_allowed("eu-west1", "private")
        "escalate"  # GDPR requires additional checks
        >>> is_allowed("sanctioned-region", "public")
        False  # Embargoed
    """
    engine = get_engine()
    return engine.is_allowed(region_code, scope)


def reload_policies():
    """
    Reload region policies from disk.

    Useful for hot-reloading configuration changes without restart.
    """
    global _engine
    _engine = None  # Force recreation on next get_engine() call
