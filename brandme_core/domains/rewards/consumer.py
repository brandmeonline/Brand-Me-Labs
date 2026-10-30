"""
Reward settlement from committed domain events (inbox consumer
``rewards.ledger``). Each delivery runs in one transaction:
``first_delivery`` (foundation inbox) → rule settlement → badge evaluation →
reward events. A redelivered or concurrently duplicated event changes nothing
(BM-LOY-002); a duplicate *cause* arriving through a different event is
stopped by the deterministic credit entry id.

Event → rule mapping (contracts/reward-rules.json):
* ``persona.updated`` (member-declared save) / ``persona.guest.migrated``
  → fact ``profile_saved``; with ``outfit.version.created`` v1 by the owner
  or a migrated saved look → fact ``look_saved``. Both facts → 100
  ``meaningful_style_setup`` once. Badge First Reflection.
* ``wardrobe.item.created`` / ``wardrobe.item.updated`` into ``owned``
  → 25 ``first_owned_item`` once. Want/on-the-way items never qualify.
* ``closet.placement.changed`` / owned item changes → badge Closet Curator.
* ``outfit.proposal.accepted`` → 25 ``styling_proposal_accepted`` to the
  proposer (never self; one per owner→proposer pair per UTC day; 100/day).
  Badge Style Collaborator.
* ``decision.closed`` → 10 ``friend_decision_response`` per eligible
  respondent, identical for yes/pass/alternative (the event carries no
  choices); 100/day; a repeated identical request records an excluded entry.
  Badge Trusted Eye.
* An order-acquired item becoming ``owned`` (delivered) → 25
  ``decision_influence`` (lane extension, PD-20) to each friend whose
  in-window verdict it followed. That is a ``yes`` on the same catalog product,
  or their own ``alternative`` naming it, in a decision that closed within
  ``INFLUENCE_WINDOW`` before delivery. One credit per decision and friend,
  ever; 100/day. Self-reported outcomes never qualify, and blocked pairs are
  skipped.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from brandme_core.domains.persona.kernel import STR, TS, NIL_MEMBER, CommandContext, command, member_active, query, service_principal, stable_id
from brandme_core.domains.persona.privacy_guard import ProcessingFrozen, assert_processing_allowed
from brandme_core.events import EventEnvelope, first_delivery

from . import badges, ledger
from .rules import INFLUENCE_WINDOW, PROPOSAL_PAIR_DAILY_LIMIT, RULES

CONSUMER = "rewards.ledger"
HANDLED = ("persona.updated", "persona.guest.migrated", "outfit.version.created", "wardrobe.item.created", "wardrobe.item.updated",
           "closet.placement.changed", "outfit.proposal.accepted", "decision.closed")


class RewardsConsumer:
    def __init__(self, database):
        self.db = database
        self._handlers: Dict[str, Callable[[Any, CommandContext, EventEnvelope], List[Dict[str, Any]]]] = {
            "persona.updated": self._persona_updated,
            "persona.guest.migrated": self._guest_migrated,
            "outfit.version.created": self._outfit_version,
            "wardrobe.item.created": self._item,
            "wardrobe.item.updated": self._item,
            "closet.placement.changed": self._placement,
            "outfit.proposal.accepted": self._proposal_accepted,
            "decision.closed": self._decision_closed,
        }

    def handle(self, event: EventEnvelope) -> Dict[str, Any]:
        handler = self._handlers.get(event.event_type)
        if handler is None:
            return {"status": "ignored"}
        principal = service_principal("rewards-ledger", environment=event.environment)

        def tx(txn, ctx: CommandContext):
            ctx.causation_id = event.event_id
            if not first_delivery(txn, CONSUMER, event):
                return {"status": "duplicate_delivery", "outcomes": []}
            return {"status": "processed", "outcomes": handler(txn, ctx, event)}

        return command(self.db, principal, tx)

    # ------------------------------------------------------------ guards

    @staticmethod
    def _eligible_member(txn, member_id: str, event: EventEnvelope) -> bool:
        if not member_id or member_id == NIL_MEMBER or not member_active(txn, member_id):
            return False
        try:
            assert_processing_allowed(txn, member_id, "rewards.ledger", event.occurred_at)
        except ProcessingFrozen:
            return False
        return True

    # ------------------------------------------------------------ setup

    def _settle_setup(self, txn, ctx, member_id: str, event: EventEnvelope) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        f = ledger.facts(txn, member_id)
        if "profile_saved" in f and "look_saved" in f:
            out.append(ledger.credit(txn, ctx, member_id, RULES["meaningful_style_setup"], event.event_id, event.occurred_at,
                                     [f"event:{f['profile_saved']['event_id']}", f"event:{f['look_saved']['event_id']}"]))
        out.append({"badges": badges.evaluate(txn, ctx, member_id, ("first_reflection",))})
        return out

    def _persona_updated(self, txn, ctx, event):
        p = event.payload
        member_id = p["member_id"]
        # A member's own saved choices; provisioning/inference/empty profiles do not count.
        if p["change_kind"] not in ("declared", "guest_migrated") or not event.actor_ref.startswith("member:"):
            return []
        if not self._eligible_member(txn, member_id, event):
            return [{"status": "member_not_eligible"}]
        ledger.set_fact(txn, member_id, "profile_saved", event.event_id, event.occurred_at)
        return self._settle_setup(txn, ctx, member_id, event)

    def _guest_migrated(self, txn, ctx, event):
        p = event.payload
        member_id = p["member_id"]
        if not self._eligible_member(txn, member_id, event):
            return [{"status": "member_not_eligible"}]
        if int(p["profile_version"]) > 0:
            ledger.set_fact(txn, member_id, "profile_saved", event.event_id, event.occurred_at)
        if p["saved_look"]:
            ledger.set_fact(txn, member_id, "look_saved", event.event_id, event.occurred_at)
        return self._settle_setup(txn, ctx, member_id, event)

    def _outfit_version(self, txn, ctx, event):
        p = event.payload
        if p["version_no"] != "1" or p["author_member_id"] != p["owner_member_id"]:
            return []
        member_id = p["owner_member_id"]
        if not self._eligible_member(txn, member_id, event):
            return [{"status": "member_not_eligible"}]
        ledger.set_fact(txn, member_id, "look_saved", event.event_id, event.occurred_at)
        return self._settle_setup(txn, ctx, member_id, event)

    # ------------------------------------------------------------ closet

    def _item(self, txn, ctx, event):
        p = event.payload
        member_id = p["member_id"]
        if p["collection"] != "owned":
            return []  # wishlist_only / not yet delivered
        if event.event_type == "wardrobe.item.updated" and "collection" not in p["changed_fields"]:
            return []
        if not self._eligible_member(txn, member_id, event):
            return [{"status": "member_not_eligible"}]
        # Influence settles only on a provider-observed delivery (a new order unit, or an order update that moved its
        # acquisition status), never on a member's own archive/restore of a piece delivered earlier.
        delivery = event.event_type == "wardrobe.item.created" or "acquisition_status" in p["changed_fields"]
        return [ledger.credit(txn, ctx, member_id, RULES["first_owned_item"], event.event_id, event.occurred_at, [f"item:{p['item_id']}"]),
                {"badges": badges.evaluate(txn, ctx, member_id, ("closet_curator",))},
                *(self._influence(txn, ctx, event, member_id, p["item_id"]) if delivery else [])]

    def _influence(self, txn, ctx, event, buyer: str, item_id: str) -> List[Dict[str, Any]]:
        from brandme_core.domains.social.notifications import blocked_between

        row = query(txn, "SELECT product_id, acquisition_source, acquisition_status FROM WardrobeItems WHERE member_id=@m AND item_id=@i",
                    {"m": buyer, "i": item_id}, {"m": STR, "i": STR})
        if not row or row[0][1] != "order" or row[0][2] != "delivered" or not row[0][0]:
            return []
        product = row[0][0]
        verdicts = query(
            txn, "SELECT d.decision_id, r.respondent_id FROM Decisions d JOIN DecisionResponses r "
                 "ON r.member_id = d.member_id AND r.decision_id = d.decision_id "
                 "WHERE d.member_id=@b AND d.state='closed' AND d.closed_at >= @since AND d.closed_at <= @at AND r.eligible = TRUE "
                 "AND ((r.choice='yes' AND d.subject_type='catalog_product' AND d.subject_id=@p) OR (r.choice='alternative' AND r.alternative_ref=@p))",
            {"b": buyer, "since": event.occurred_at - INFLUENCE_WINDOW, "at": event.occurred_at, "p": product},
            {"b": STR, "since": TS, "at": TS, "p": STR})
        out: List[Dict[str, Any]] = []
        for decision_id, friend in verdicts:
            if friend == buyer or blocked_between(txn, buyer, friend) or not self._eligible_member(txn, friend, event):
                out.append({"status": "member_not_eligible", "member_id": friend})
                continue
            # The cause is the decision, so several delivered units credit one verdict once.
            out.append(ledger.credit(txn, ctx, friend, RULES["decision_influence"], stable_id("decision-influence", decision_id),
                                     event.occurred_at, [f"decision:{decision_id}"]))
        return out

    def _placement(self, txn, ctx, event):
        member_id = event.payload["member_id"]
        if not self._eligible_member(txn, member_id, event):
            return [{"status": "member_not_eligible"}]
        return [{"badges": badges.evaluate(txn, ctx, member_id, ("closet_curator",))}]

    # ------------------------------------------------------------ social

    def _proposal_accepted(self, txn, ctx, event):
        p = event.payload
        proposer, owner = p["proposer_member_id"], p["owner_member_id"]
        if proposer == owner:
            return [{"status": "excluded", "reason": "self_acceptance"}]
        if not self._eligible_member(txn, proposer, event):
            return [{"status": "member_not_eligible"}]
        out = ledger.credit(txn, ctx, proposer, RULES["styling_proposal_accepted"], event.event_id, event.occurred_at,
                            [f"proposal:{p['proposal_id']}", f"outfit:{p['outfit_id']}"],
                            pair_ref=f"counterparty:{owner}", pair_limit=PROPOSAL_PAIR_DAILY_LIMIT)
        return [out, {"badges": badges.evaluate(txn, ctx, proposer, ("style_collaborator",))}]

    def _decision_closed(self, txn, ctx, event):
        p = event.payload
        rule = RULES["friend_decision_response"]
        out: List[Dict[str, Any]] = []
        for respondent in p["eligible_respondent_ids"]:
            if respondent == p["creator_id"] or not self._eligible_member(txn, respondent, event):
                out.append({"status": "member_not_eligible", "member_id": respondent})
                continue
            out.append(ledger.credit(txn, ctx, respondent, rule, event.event_id, event.occurred_at, [f"decision:{p['decision_id']}"],
                                     exclusion="repeated_identical_request" if p["repeat_request"] else None))
            out.append({"badges": badges.evaluate(txn, ctx, respondent, ("trusted_eye",))})
        return out
