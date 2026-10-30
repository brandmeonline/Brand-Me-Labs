"""
Reward rules and badges (ch.01 §7.2/§7.3; contracts/reward-rules.json).

The rule table mirrors the contract's proposed defaults and is checked
against it by ``test_rules_mirror_the_contract``. Caps use UTC windows on the
qualifying server event time; a member's profile timezone never moves them.

Rules with no wired source in this repository are listed but never settle:
``referral_activated`` (no referral system) and
``optional_research_contribution`` (no campaign with defined compensation).

``EXTENSIONS`` are lane rules for the founder-locked design that the contract
does not list yet. Each names its proposed deviation. The contract mirror test
checks every contract rule exactly and requires every other rule to be listed
here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Rule:
    id: str
    version: int
    points: Optional[int]
    condition: str
    lifetime_max: Optional[int] = None
    cap_points: Optional[int] = None
    cap_window: Optional[str] = None  # calendar_day | iso_week | calendar_month
    wired: bool = True
    member_text: str = ""


RULES: Dict[str, Rule] = {r.id: r for r in (
    Rule("meaningful_style_setup", 1, 100, "first_saved_profile_and_first_saved_look_for_member", lifetime_max=1,
         member_text="Save your style profile and your first look"),
    Rule("first_owned_item", 1, 25, "first_persistent_member_declared_or_evidence_backed_owned_item", lifetime_max=1,
         member_text="Add your first owned item"),
    Rule("friend_decision_response", 1, 10, "eligible_unique_nonowner_response_before_server_deadline",
         cap_points=100, cap_window="calendar_day",
         member_text="Answer a friend's decision before it closes; yes, pass and alternatives earn the same"),
    Rule("styling_proposal_accepted", 1, 25, "different_member_accepts_unique_substantive_outfit_proposal",
         cap_points=100, cap_window="calendar_day", member_text="A friend accepts your outfit proposal"),
    Rule("catalog_correction_accepted", 1, 50, "authorized_reviewer_accepts_evidenced_correction",
         cap_points=250, cap_window="iso_week", member_text="A reviewer accepts your evidenced catalog correction"),
    Rule("referral_activated", 1, 50, "new_verified_account_completes_meaningful_use_with_valid_referral", wired=False,
         member_text="Not available yet"),
    Rule("optional_research_contribution", 1, None, "explicit_campaign_consent_and_valid_contribution", wired=False,
         member_text="Not available yet"),
    Rule("verified_repair", 1, 50, "approved_repair_workflow_supplies_unique_valid_completion_evidence",
         cap_points=200, cap_window="calendar_month", member_text="An approved repair workflow confirms a repair"),
    # Ultra plan 02 item 2 (Now loop): influence credit when a friend's verdict moves a verified purchase.
    Rule("decision_influence", 1, 25, "verified_delivered_order_of_subject_or_chosen_alternative_within_14_days_after_in_window_verdict",
         cap_points=100, cap_window="calendar_day", member_text="A friend bought what you helped them choose"),
    # Ultra plan 02 item 5: daily-capped surveys and quizzes (three a day earn points).
    Rule("survey_completed", 1, 10, "member_completes_an_operator_published_survey_or_quiz_once",
         cap_points=30, cap_window="calendar_day", member_text="Complete a short survey or quiz; three a day earn points"),
)}

EXTENSIONS: Dict[str, str] = {"decision_influence": "PD-20", "survey_completed": "PD-21"}

# Influence: the decision closed at most this long before the purchase was delivered.
INFLUENCE_WINDOW = timedelta(days=14)

# Disclosed anti-collusion policy for proposals: one award per owner→proposer
# pair per UTC day (contracts: collusive_repeated_acceptance; no hidden scores).
PROPOSAL_PAIR_DAILY_LIMIT = 1


def utc(t: datetime) -> datetime:
    if t.tzinfo is None:
        raise ValueError("aware datetime required")
    t = t.astimezone(timezone.utc)
    return datetime(t.year, t.month, t.day, t.hour, t.minute, t.second, t.microsecond, tzinfo=timezone.utc)


def cap_window(kind: str, at: datetime) -> Tuple[datetime, datetime]:
    """[start, end) of the UTC window containing ``at``."""
    t = utc(at)
    day = t.replace(hour=0, minute=0, second=0, microsecond=0)
    if kind == "calendar_day":
        return day, day + timedelta(days=1)
    if kind == "iso_week":
        start = day - timedelta(days=day.isoweekday() - 1)
        return start, start + timedelta(days=7)
    if kind == "calendar_month":
        start = day.replace(day=1)
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        return start, end
    raise ValueError(kind)


@dataclass(frozen=True)
class Badge:
    id: str
    title: str
    criteria: str
    criteria_version: int = 1


BADGES: Dict[str, Badge] = {b.id: b for b in (
    Badge("first_reflection", "First Reflection", "Save your style profile for the first time."),
    Badge("closet_curator", "Closet Curator", "Place 10 owned items in your closet."),
    Badge("trusted_eye", "Trusted Eye",
          "Give 20 valid answers to friends' decisions across at least 5 decisions. Describes participation, not identity verification."),
    Badge("style_collaborator", "Style Collaborator", "Have 5 of your outfit proposals accepted by friends."),
    Badge("care_keeper", "Care Keeper", "Have one repair confirmed by an approved repair workflow."),
    Badge("material_story", "Material Story", "Have one product-history contribution accepted by a reviewer."),
)}

CLOSET_CURATOR_ITEMS = 10
TRUSTED_EYE_RESPONSES = 20
TRUSTED_EYE_DECISIONS = 5
STYLE_COLLABORATOR_ACCEPTED = 5
