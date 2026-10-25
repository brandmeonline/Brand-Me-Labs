"""
Five-minute social decisions (ch.01 §6; contracts invariant 5;
BM-SOC-002..008, BM-SOC-012).

* The server fixes ``opened_at``/``closes_at`` (opened_at + the window) from
  Spanner server time inside the opening transaction. The asker picks the
  window from ``policy.NOW_WINDOWS`` (default 300 s) and may state a ``why``.
* A response is accepted only if the server time read inside its own
  transaction is strictly before ``closes_at`` and the decision is open
  (see ``clock.py``). Late calls get ``decision_closed``. One response record
  per respondent and decision (primary key); it can be changed until the
  deadline, and only one participation can ever be rewarded.
* Closing happens once (state check in a serializable transaction).
  Eligibility is reconciled at close: in the audience, not the creator, not
  blocked, answered before the deadline. The event lists eligible respondents
  for the rewards domain.
* Blind mode hides other respondents' choices from a respondent until they
  have answered (or the decision closed). The creator sees results.
* An agent without communication authority (``social:send``) can only
  create a *draft*. Nothing is sent until the member opens it from their own
  session (BM-SOC-012).
* Rate limits (configurable defaults): 5 new decisions per UTC day, 3 open at
  once, 1 invitation per recipient per request. Repeating an identical request
  is allowed but flagged ``repeat_request`` so it cannot farm rewards.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

from brandme_core.domains.persona.kernel import (
    INT,
    STR,
    TS,
    CommandContext,
    DetailedInvalidTransition,
    NotFound,
    Principal,
    RateLimited,
    ValidationFailed,
    command,
    idempotent_command,
    iso,
    guard_write,
    processing_allowed,
    member_active,
    query,
    reject_non_finite,
    reject_unknown_keys,
    require_scope,
    require_text,
    require_uuid,
    run_read,
    stable_id,
)

from . import events as _events  # noqa: F401
from .clock import SpannerTxnClock, TxnClock, utc_day_start
from .notifications import blocked_between, notify
from .policy import COMMENTS_PER_AUTHOR, NOW_DEFAULT_WINDOW, NOW_WINDOWS
from .relationships import are_friends

DURATION_SECONDS = NOW_DEFAULT_WINDOW
SUBJECT_TYPES = ("wardrobe_item", "catalog_product", "outfit_version")
MODES = ("blind_until_response", "open")
CHOICES = ("yes", "pass", "alternative")
OUTCOMES = ("bought", "saved", "passed", "still_deciding")
CREATE_KEYS = ("subject_type", "subject_id", "prompt", "recipient_ids", "duration_seconds", "discussion_mode", "why")
REQUIRED_CREATE_KEYS = ("subject_type", "subject_id", "prompt", "recipient_ids", "discussion_mode")


@dataclass(frozen=True)
class DecisionLimits:
    per_day: int = 5
    concurrent_open: int = 3
    max_recipients: int = 12
    repeat_window: timedelta = timedelta(hours=24)


# (txn, creator_id, product_id) -> bool : catalog subjects are owned by the providers lane.
CatalogCheck = Callable[[Any, str], bool]

DEC_COLS = ("member_id", "decision_id", "subject_type", "subject_id", "prompt", "why", "discussion_mode", "duration_seconds", "state",
            "created_by_actor", "request_fingerprint", "repeat_of", "opened_at", "closes_at", "closed_at", "close_reason",
            "yes_count", "pass_count", "alternative_count", "requester_outcome", "version")
RESP_COLS = ("respondent_id", "choice", "alternative_ref", "note", "revision", "first_submitted_at", "submitted_at", "eligible")
COMMENT_COLS = ("comment_id", "author_id", "body", "created_at", "removed_at", "removed_reason")


def fingerprint(subject_type: str, subject_id: str, prompt: str, recipients: Sequence[str]) -> str:
    norm = " ".join(unicodedata.normalize("NFKC", prompt).casefold().split())
    return hashlib.sha256("\x1f".join([subject_type, subject_id, norm, *sorted(recipients)]).encode()).hexdigest()


def result_label(yes: int, pas: int, alt: int) -> str:
    if yes + pas + alt == 0:
        return "No replies this time"
    parts = [f"{yes} yes", f"{pas} pass"] + ([f"{alt} alternative" + ("s" if alt != 1 else "")] if alt else [])
    return ", ".join(parts)


def parse_create(body: Any) -> Dict[str, Any]:
    if not isinstance(body, Mapping):
        raise ValidationFailed("body must be an object")
    reject_non_finite(body)
    reject_unknown_keys(body, CREATE_KEYS, where="decision")
    missing = [k for k in REQUIRED_CREATE_KEYS if k not in body]
    if missing:
        raise ValidationFailed(f"missing fields: {', '.join(missing)}", extra={"missing_fields": missing})
    if body["subject_type"] not in SUBJECT_TYPES:
        raise ValidationFailed("unsupported subject_type", extra={"field": "subject_type"})
    window = body.get("duration_seconds", NOW_DEFAULT_WINDOW)
    if type(window) is not int or window not in NOW_WINDOWS:  # 300.0 and True are not windows
        raise ValidationFailed(f"duration_seconds must be one of {list(NOW_WINDOWS)}", extra={"field": "duration_seconds"})
    why = body.get("why")
    if why is not None:
        why = require_text(why, name="why", max_len=280)
    if body["discussion_mode"] not in MODES:
        raise ValidationFailed("discussion_mode must be blind_until_response or open", extra={"field": "discussion_mode"})
    recips = body["recipient_ids"]
    if not isinstance(recips, list) or not (1 <= len(recips) <= 12):
        raise ValidationFailed("choose 1-12 recipients", extra={"field": "recipient_ids"})
    recips = [require_uuid(r, name="recipient_ids") for r in recips]
    if len(set(recips)) != len(recips):
        raise ValidationFailed("each recipient can be invited once", extra={"field": "recipient_ids"})
    return {
        "subject_type": body["subject_type"],
        "subject_id": require_uuid(body["subject_id"], name="subject_id"),
        "prompt": require_text(body["prompt"], name="prompt", max_len=280),
        "why": why,
        "duration_seconds": window,
        "recipient_ids": recips,
        "discussion_mode": body["discussion_mode"],
    }


def parse_response(body: Any) -> Dict[str, Any]:
    if not isinstance(body, Mapping):
        raise ValidationFailed("body must be an object")
    reject_unknown_keys(body, ("choice", "alternative_ref", "note"), where="response")
    choice = body.get("choice")
    if choice not in CHOICES:
        raise ValidationFailed("choice must be yes, pass or alternative", extra={"field": "choice"})
    alt = body.get("alternative_ref")
    if choice == "alternative":
        alt = require_uuid(alt, name="alternative_ref")
    elif alt is not None:
        raise ValidationFailed("alternative_ref is only for 'Try this instead'", extra={"field": "alternative_ref"})
    note = body.get("note")
    if note is not None:
        if not isinstance(note, str) or len(note) > 500:
            raise ValidationFailed("note must be at most 500 characters", extra={"field": "note"})
        note = note.strip() or None
    return {"choice": choice, "alternative_ref": alt, "note": note}


class DecisionService:
    def __init__(self, database, *, clock: TxnClock = None, limits: DecisionLimits = DecisionLimits(),
                 catalog_check: Optional[CatalogCheck] = None):
        self.db = database
        self.clock = clock or SpannerTxnClock()
        self.limits = limits
        self.catalog_check = catalog_check or (lambda _txn, _pid: True)

    # ------------------------------------------------------------ loading

    def _locate(self, txn, decision_id: str) -> Optional[Dict[str, Any]]:
        rows = query(txn, f"SELECT {', '.join(DEC_COLS)} FROM Decisions@{{FORCE_INDEX=DecisionsById}} WHERE decision_id=@d",
                     {"d": decision_id}, {"d": STR})
        return dict(zip(DEC_COLS, rows[0])) if rows else None

    def _audience(self, txn, d: Mapping[str, Any]) -> List[Dict[str, Any]]:
        return [{"recipient_id": r[0], "removed": r[1]} for r in query(
            txn, "SELECT recipient_id, removed FROM DecisionAudience WHERE member_id=@m AND decision_id=@d ORDER BY recipient_id",
            {"m": d["member_id"], "d": d["decision_id"]}, {"m": STR, "d": STR})]

    def _responses(self, txn, d: Mapping[str, Any]) -> List[Dict[str, Any]]:
        return [dict(zip(RESP_COLS, r)) for r in query(
            txn, f"SELECT {', '.join(RESP_COLS)} FROM DecisionResponses WHERE member_id=@m AND decision_id=@d ORDER BY respondent_id",
            {"m": d["member_id"], "d": d["decision_id"]}, {"m": STR, "d": STR})]

    def _visible(self, txn, d: Mapping[str, Any], viewer: str) -> str:
        """'creator' | 'audience' ; raises NotFound otherwise (no existence leak)."""
        if d["member_id"] == viewer:
            return "creator"
        if d["state"] == "draft" or blocked_between(txn, viewer, d["member_id"]):
            raise NotFound("decision not found")
        if not any(a["recipient_id"] == viewer and not a["removed"] for a in self._audience(txn, d)):
            raise NotFound("decision not found")
        return "audience"

    def _dto(self, txn, d: Mapping[str, Any], viewer: str, role: str, now: datetime) -> Dict[str, Any]:
        responses = [r for r in self._responses(txn, d) if r["respondent_id"] == viewer or not blocked_between(txn, viewer, r["respondent_id"])]
        mine = next((r for r in responses if r["respondent_id"] == viewer), None)
        show_all = role == "creator" or d["state"] == "closed" or d["discussion_mode"] == "open" or mine is not None
        out = {
            "decision_id": d["decision_id"],
            "creator_id": d["member_id"],
            "subject_type": d["subject_type"],
            "subject_id": d["subject_id"],
            "prompt": d["prompt"],
            "why": d["why"],
            "discussion_mode": d["discussion_mode"],
            "duration_seconds": d["duration_seconds"],
            "state": d["state"],
            "opened_at": iso(d["opened_at"]),
            "closes_at": iso(d["closes_at"]),
            "server_time": iso(now),
            "remaining_seconds": max(0, int((d["closes_at"] - now).total_seconds())) if d["state"] == "open" and d["closes_at"] else 0,
            "my_response": None if mine is None else {"choice": mine["choice"], "alternative_ref": mine["alternative_ref"], "note": mine["note"],
                                                      "revision": mine["revision"], "submitted_at": iso(mine["submitted_at"])},
            "responses": [
                {"respondent_id": r["respondent_id"], "choice": r["choice"], "alternative_ref": r["alternative_ref"], "note": r["note"],
                 "eligible": d.get("_eligible", {}).get(r["respondent_id"], r["eligible"])}
                for r in responses
            ] if show_all else [],
            "responses_hidden_until_you_answer": not show_all,
            "response_count": len(responses),
            "repeat_request": d["repeat_of"] is not None,
        }
        if role == "creator":
            out["audience"] = [a["recipient_id"] for a in self._audience(txn, d) if not a["removed"]]
            out["requester_outcome"] = d["requester_outcome"]
            out["requester_outcome_label"] = "self-reported" if d["requester_outcome"] else None
        if d["state"] == "closed":
            out["result"] = {"yes": d["yes_count"], "pass": d["pass_count"], "alternative": d["alternative_count"],
                             "label": result_label(d["yes_count"], d["pass_count"], d["alternative_count"]),
                             "zero_replies": d["yes_count"] + d["pass_count"] + d["alternative_count"] == 0}
            if out["result"]["zero_replies"] and role == "creator":
                out["next_actions"] = ["save", "ask_again_as_new_request"]
        return out

    # ------------------------------------------------------------- create

    def _check_subject(self, txn, creator: str, subject_type: str, subject_id: str) -> None:
        if subject_type == "wardrobe_item":
            ok = query(txn, "SELECT 1 FROM WardrobeItems WHERE member_id=@m AND item_id=@i AND collection != 'archive'",
                       {"m": creator, "i": subject_id}, {"m": STR, "i": STR})
        elif subject_type == "outfit_version":
            ok = query(txn, "SELECT 1 FROM Outfits WHERE member_id=@m AND outfit_id=@o AND NOT archived",
                       {"m": creator, "o": subject_id}, {"m": STR, "o": STR})
        else:
            ok = self.catalog_check(txn, subject_id)
        if not ok:
            raise ValidationFailed("the subject must be your own item/outfit or an available catalog product", extra={"field": "subject_id"})

    def _check_limits(self, txn, creator: str, now: datetime) -> None:
        """Per-UTC-day and concurrent limits, counted on server-timed opened_at."""
        day = utc_day_start(now)
        today = query(txn, "SELECT COUNT(*) FROM Decisions WHERE member_id=@m AND opened_at >= @t AND opened_at < @e",
                      {"m": creator, "t": day, "e": day + timedelta(days=1)}, {"m": STR, "t": TS, "e": TS})[0][0]
        if today >= self.limits.per_day:
            raise RateLimited(f"you can start {self.limits.per_day} decisions per day", extra={"limit": "per_day"})
        open_now = query(txn, "SELECT COUNT(*) FROM Decisions WHERE member_id=@m AND state='open' AND closes_at > @n",
                         {"m": creator, "n": now}, {"m": STR, "n": TS})[0][0]
        if open_now >= self.limits.concurrent_open:
            raise RateLimited(f"at most {self.limits.concurrent_open} decisions can be open at once", extra={"limit": "concurrent_open"})

    def create(self, principal: Principal, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        req = parse_create(body)
        creator = principal.member_id
        as_draft = principal.delegation_id is not None and "social:send" not in principal.scopes
        fp = fingerprint(req["subject_type"], req["subject_id"], req["prompt"], req["recipient_ids"])

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, creator):
                raise NotFound("member not found")
            guard_write(txn, creator, "social.decisions")
            now = self.clock.now(txn)
            if creator in req["recipient_ids"]:
                raise ValidationFailed("you cannot ask yourself; use a private comparison instead", extra={"field": "recipient_ids"})
            ineligible = sorted(r for r in req["recipient_ids"]
                                if not are_friends(txn, creator, r) or not processing_allowed(txn, r, "social.decisions"))
            if ineligible:
                raise DetailedInvalidTransition("recipients must be friends you can reach", code="ineligible_recipients",
                                                extra={"ineligible_recipient_ids": ineligible})
            self._check_subject(txn, creator, req["subject_type"], req["subject_id"])
            if not as_draft:
                self._check_limits(txn, creator, now)
            # A draft's repetition is decided when it is sent (open_draft), not now.
            prior = None if as_draft else self._repeat_of(txn, creator, fp, now, None)
            decision_id = stable_id("decision", creator, ctx.correlation_id)
            opened = None if as_draft else now
            closes = None if as_draft else now + timedelta(seconds=req["duration_seconds"])
            row = {
                "member_id": creator, "decision_id": decision_id, "subject_type": req["subject_type"], "subject_id": req["subject_id"],
                "prompt": req["prompt"], "why": req["why"], "discussion_mode": req["discussion_mode"],
                "duration_seconds": req["duration_seconds"],
                "state": "draft" if as_draft else "open", "created_by_actor": principal.actor_ref, "request_fingerprint": fp,
                "repeat_of": prior, "opened_at": opened, "closes_at": closes, "closed_at": None,
                "close_reason": None, "yes_count": 0, "pass_count": 0, "alternative_count": 0, "requester_outcome": None, "version": 1,
            }
            txn.insert("Decisions", columns=(*DEC_COLS, "created_at", "updated_at"),
                       values=[[*(row[c] for c in DEC_COLS), COMMIT_TIMESTAMP, COMMIT_TIMESTAMP]])
            txn.insert("DecisionAudience", columns=("member_id", "decision_id", "recipient_id", "closes_at", "removed"),
                       values=[(creator, decision_id, r, closes, False) for r in req["recipient_ids"]])
            if not as_draft:
                self._announce(txn, ctx, row, req["recipient_ids"])
            out = self._dto(txn, {**row}, creator, "creator", now)
            out["audience"] = req["recipient_ids"]
            if as_draft:
                out["requires_member_approval"] = True
            return out

        response, _ = idempotent_command(self.db, principal, "decisions.create", idempotency_key, dict(body), tx)
        return response

    def _announce(self, txn, ctx: CommandContext, d: Mapping[str, Any], recipients: Sequence[str]) -> None:
        ev = ctx.emit("decision.opened", "1", "decision", d["decision_id"], d["version"],
                      {"decision_id": d["decision_id"], "creator_id": d["member_id"], "audience_count": len(recipients),
                       "closes_at": iso(d["closes_at"])}, "member_private")
        for r in recipients:
            notify(txn, recipient_id=r, event_id=ev.event_id, type_="decision_request", actor_member_id=d["member_id"],
                   subject_ref=f"decision:{d['decision_id']}", payload={"decision_id": d["decision_id"], "closes_at": iso(d["closes_at"])})

    def _repeat_of(self, txn, creator: str, fp: str, now: datetime, exclude: Optional[str]) -> Optional[str]:
        """The most recent identical request this member actually sent inside the
        repeat window. Unsent drafts never count."""
        rows = query(txn, "SELECT decision_id FROM Decisions WHERE member_id=@m AND request_fingerprint=@f AND opened_at IS NOT NULL "
                          "AND opened_at >= @since AND decision_id != @x ORDER BY opened_at DESC LIMIT 1",
                     {"m": creator, "f": fp, "since": now - self.limits.repeat_window, "x": exclude or ""},
                     {"m": STR, "f": STR, "since": TS, "x": STR})
        return rows[0][0] if rows else None

    def open_draft(self, principal: Principal, decision_id: Any) -> Dict[str, Any]:
        """The member, in their own session, sends a draft an agent prepared."""
        require_scope(principal, "social:write")
        decision_id = require_uuid(decision_id, name="decision_id")
        if principal.delegation_id is not None:
            raise DetailedInvalidTransition("only the member can send a prepared request", code="member_approval_required")

        def tx(txn, ctx: CommandContext):
            d = self._locate(txn, decision_id)
            if d is None or d["member_id"] != principal.member_id:
                raise NotFound("decision not found")
            if d["state"] != "draft":
                raise DetailedInvalidTransition(f"decision is {d['state']}", code="not_a_draft")
            guard_write(txn, principal.member_id, "social.decisions")
            now = self.clock.now(txn)
            self._check_limits(txn, principal.member_id, now)
            active = [a["recipient_id"] for a in self._audience(txn, d) if not a["removed"]]
            recipients = [r for r in active if are_friends(txn, d["member_id"], r) and processing_allowed(txn, r, "social.decisions")]
            if not recipients:
                raise DetailedInvalidTransition("no eligible recipients remain", code="ineligible_recipients")
            closes = now + timedelta(seconds=d["duration_seconds"])
            repeat_of = self._repeat_of(txn, d["member_id"], d["request_fingerprint"], now, decision_id)
            d.update(state="open", opened_at=now, closes_at=closes, repeat_of=repeat_of, version=d["version"] + 1)
            txn.update("Decisions", columns=("member_id", "decision_id", "state", "opened_at", "closes_at", "repeat_of", "version", "updated_at"),
                       values=[(d["member_id"], decision_id, "open", now, closes, repeat_of, d["version"], COMMIT_TIMESTAMP)])
            # Recipients who stopped being reachable leave the audience, so they cannot read or answer it.
            txn.update("DecisionAudience", columns=("member_id", "decision_id", "recipient_id", "closes_at", "removed"),
                       values=[(d["member_id"], decision_id, r, closes, r not in recipients) for r in active])
            self._announce(txn, ctx, d, recipients)
            return self._dto(txn, d, principal.member_id, "creator", now)

        return command(self.db, principal, tx)

    # ------------------------------------------------------------- respond

    def respond(self, principal: Principal, decision_id: Any, body: Any) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        decision_id = require_uuid(decision_id, name="decision_id")
        resp = parse_response(body)
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            d = self._locate(txn, decision_id)
            if d is None:
                raise NotFound("decision not found")
            if d["member_id"] == me:
                raise DetailedInvalidTransition("you cannot answer your own request", code="self_response")
            self._visible(txn, d, me)
            guard_write(txn, me, "social.decisions")
            now = self.clock.now(txn)
            if d["state"] != "open" or now >= d["closes_at"]:
                raise DetailedInvalidTransition("this decision has closed", code="decision_closed",
                                                extra={"closes_at": iso(d["closes_at"]), "server_time": iso(now)})
            if resp["choice"] == "alternative":
                own = query(txn, "SELECT 1 FROM WardrobeItems WHERE member_id=@m AND item_id=@i AND collection != 'archive'",
                            {"m": me, "i": resp["alternative_ref"]}, {"m": STR, "i": STR})
                if not own and not self.catalog_check(txn, resp["alternative_ref"]):
                    raise ValidationFailed("the alternative must be an item you can see", extra={"field": "alternative_ref"})
            existing = query(txn, "SELECT revision, first_submitted_at, choice, alternative_ref, note, submitted_at FROM DecisionResponses "
                                  "WHERE member_id=@m AND decision_id=@d AND respondent_id=@r",
                             {"m": d["member_id"], "d": decision_id, "r": me}, {"m": STR, "d": STR, "r": STR})
            if existing and tuple(existing[0][2:5]) == (resp["choice"], resp["alternative_ref"], resp["note"]):
                # A replay of the same answer changes nothing and emits nothing.
                return {"decision_id": decision_id, "choice": resp["choice"], "alternative_ref": resp["alternative_ref"],
                        "revision": existing[0][0], "submitted_at": iso(existing[0][5]), "closes_at": iso(d["closes_at"]), "unchanged": True}
            revision = existing[0][0] + 1 if existing else 1
            first = existing[0][1] if existing else now
            txn.insert_or_update(
                "DecisionResponses",
                columns=("member_id", "decision_id", "respondent_id", "choice", "alternative_ref", "note", "revision",
                         "first_submitted_at", "submitted_at", "committed_at", "eligible"),
                values=[(d["member_id"], decision_id, me, resp["choice"], resp["alternative_ref"], resp["note"], revision, first, now,
                         COMMIT_TIMESTAMP, None)],
            )
            ev = ctx.emit("decision.responded", "1", "decision", decision_id, d["version"],
                          {"decision_id": decision_id, "creator_id": d["member_id"], "respondent_id": me, "revision": revision}, "member_private")
            if revision == 1:
                notify(txn, recipient_id=d["member_id"], event_id=ev.event_id, type_="decision_response", actor_member_id=me,
                       subject_ref=f"decision:{decision_id}", payload={"decision_id": decision_id})
            return {"decision_id": decision_id, "choice": resp["choice"], "alternative_ref": resp["alternative_ref"],
                    "revision": revision, "submitted_at": iso(now), "closes_at": iso(d["closes_at"]), "unchanged": False}

        return command(self.db, principal, tx)

    # --------------------------------------------------------------- close

    def _close(self, txn, ctx: CommandContext, d: Dict[str, Any], reason: str, now: datetime) -> Dict[str, Any]:
        audience = {a["recipient_id"] for a in self._audience(txn, d) if not a["removed"]}
        responses = self._responses(txn, d)
        cutoff = min(d["closes_at"], now) if reason == "owner_closed" else d["closes_at"]
        counts = {"yes": 0, "pass": 0, "alternative": 0}
        eligible_ids = []
        updates = []
        for r in responses:
            ok = (
                r["respondent_id"] in audience
                and r["respondent_id"] != d["member_id"]
                and r["submitted_at"] < cutoff
                and not blocked_between(txn, d["member_id"], r["respondent_id"])
            )
            updates.append((d["member_id"], d["decision_id"], r["respondent_id"], ok))
            if ok:
                counts[r["choice"]] += 1
                eligible_ids.append(r["respondent_id"])
        if updates:
            txn.update("DecisionResponses", columns=("member_id", "decision_id", "respondent_id", "eligible"), values=updates)
        d["_eligible"] = {u[2]: u[3] for u in updates}  # buffered writes are not readable in this transaction
        d.update(state="closed", closed_at=now, close_reason=reason, yes_count=counts["yes"], pass_count=counts["pass"],
                 alternative_count=counts["alternative"], version=d["version"] + 1)
        txn.update("Decisions", columns=("member_id", "decision_id", "state", "closed_at", "close_reason", "yes_count", "pass_count",
                                         "alternative_count", "version", "updated_at"),
                   values=[(d["member_id"], d["decision_id"], "closed", now, reason, counts["yes"], counts["pass"], counts["alternative"],
                            d["version"], COMMIT_TIMESTAMP)])
        zero = not eligible_ids
        ev = ctx.emit("decision.closed", "1", "decision", d["decision_id"], d["version"],
                      {"decision_id": d["decision_id"], "creator_id": d["member_id"], "close_reason": reason,
                       "eligible_respondent_ids": sorted(eligible_ids), "repeat_request": d["repeat_of"] is not None,
                       "zero_replies": zero}, "member_private")
        notify(txn, recipient_id=d["member_id"], event_id=ev.event_id, type_="decision_closed", actor_member_id=None,
               subject_ref=f"decision:{d['decision_id']}",
               payload={"decision_id": d["decision_id"], "result": result_label(counts["yes"], counts["pass"], counts["alternative"])})
        return d

    def close(self, principal: Principal, decision_id: Any) -> Dict[str, Any]:
        """Owner's early close; historical responses are never altered."""
        require_scope(principal, "social:write")
        decision_id = require_uuid(decision_id, name="decision_id")

        def tx(txn, ctx: CommandContext):
            d = self._locate(txn, decision_id)
            if d is None or d["member_id"] != principal.member_id:
                raise NotFound("decision not found")
            now = self.clock.now(txn)
            if d["state"] == "closed":
                return self._dto(txn, d, principal.member_id, "creator", now)
            if d["state"] != "open":
                raise DetailedInvalidTransition(f"decision is {d['state']}", code="not_open")
            reason = "expired" if now >= d["closes_at"] else "owner_closed"
            d = self._close(txn, ctx, d, reason, now)
            return self._dto(txn, d, principal.member_id, "creator", now)

        return command(self.db, principal, tx)

    def close_due(self, *, limit: int = 100, environment: str = "development") -> Dict[str, int]:
        """Scheduler: close every open decision whose server deadline passed.
        Each decision closes in its own transaction; repeats are no-ops."""
        from brandme_core.domains.persona.kernel import service_principal

        principal = service_principal("decision-closer", environment=environment)
        due = run_read(self.db, lambda s: query(
            s, "SELECT decision_id FROM Decisions@{FORCE_INDEX=DecisionsByStateClose} WHERE state='open' AND closes_at <= @n "
               "ORDER BY closes_at LIMIT @l", {"n": self.clock.now(s), "l": limit}, {"n": TS, "l": INT}))
        closed = skipped = 0
        for (decision_id,) in due:
            def tx(txn, ctx: CommandContext, decision_id=decision_id):
                d = self._locate(txn, decision_id)
                now = self.clock.now(txn)
                if d is None or d["state"] != "open" or now < d["closes_at"]:
                    return False
                self._close(txn, ctx, d, "expired", now)
                return True

            if command(self.db, principal, tx):
                closed += 1
            else:
                skipped += 1
        return {"closed": closed, "skipped": skipped}

    def cancel(self, principal: Principal, decision_id: Any) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        decision_id = require_uuid(decision_id, name="decision_id")

        def tx(txn, ctx: CommandContext):
            d = self._locate(txn, decision_id)
            if d is None or d["member_id"] != principal.member_id:
                raise NotFound("decision not found")
            if d["state"] not in ("draft", "open"):
                raise DetailedInvalidTransition(f"decision is {d['state']}", code="not_cancellable")
            d.update(state="cancelled", version=d["version"] + 1)
            txn.update("Decisions", columns=("member_id", "decision_id", "state", "version", "updated_at"),
                       values=[(d["member_id"], decision_id, "cancelled", d["version"], COMMIT_TIMESTAMP)])
            ctx.emit("decision.cancelled", "1", "decision", decision_id, d["version"],
                     {"decision_id": decision_id, "creator_id": d["member_id"]}, "member_private")
            return {"decision_id": decision_id, "state": "cancelled"}

        return command(self.db, principal, tx)

    def record_outcome(self, principal: Principal, decision_id: Any, outcome: Any) -> Dict[str, Any]:
        """Self-reported (labelled); never a proven causal conversion."""
        require_scope(principal, "social:write")
        decision_id = require_uuid(decision_id, name="decision_id")
        if outcome not in OUTCOMES:
            raise ValidationFailed(f"outcome must be one of {OUTCOMES}", extra={"field": "outcome"})

        def tx(txn, ctx: CommandContext):
            d = self._locate(txn, decision_id)
            if d is None or d["member_id"] != principal.member_id:
                raise NotFound("decision not found")
            if d["state"] != "closed":
                raise DetailedInvalidTransition("record the outcome after the decision closes", code="not_closed")
            guard_write(txn, principal.member_id, "social.decisions")
            txn.update("Decisions", columns=("member_id", "decision_id", "requester_outcome", "updated_at"),
                       values=[(d["member_id"], decision_id, outcome, COMMIT_TIMESTAMP)])
            return {"decision_id": decision_id, "requester_outcome": outcome, "label": "self-reported"}

        return command(self.db, principal, tx)

    # ------------------------------------------------------------ comments

    def _comments_visible(self, txn, d: Mapping[str, Any], viewer: str, role: str) -> bool:
        """Blind mode keeps the thread hidden from a recipient until they answer, so
        comments never anchor anyone's verdict; it opens to all once closed."""
        if role == "creator" or d["state"] == "closed" or d["discussion_mode"] == "open":
            return True
        return bool(query(txn, "SELECT 1 FROM DecisionResponses WHERE member_id=@m AND decision_id=@d AND respondent_id=@r",
                          {"m": d["member_id"], "d": d["decision_id"], "r": viewer}, {"m": STR, "d": STR, "r": STR}))

    def add_comment(self, principal: Principal, decision_id: Any, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        """A short comment in the decision's thread, inside the window only."""
        require_scope(principal, "social:write")
        decision_id = require_uuid(decision_id, name="decision_id")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("body",), where="comment")
        text = require_text(body.get("body"), name="body", max_len=500)
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            d = self._locate(txn, decision_id)
            if d is None:
                raise NotFound("decision not found")
            role = self._visible(txn, d, me)
            guard_write(txn, me, "social.decisions")
            now = self.clock.now(txn)
            if d["state"] != "open" or now >= d["closes_at"]:
                raise DetailedInvalidTransition("this decision has closed", code="decision_closed",
                                                extra={"closes_at": iso(d["closes_at"]), "server_time": iso(now)})
            if not self._comments_visible(txn, d, me, role):
                raise DetailedInvalidTransition("answer first; the thread opens after your answer", code="answer_first")
            mine = query(txn, "SELECT COUNT(*) FROM DecisionComments WHERE member_id=@m AND decision_id=@d AND author_id=@a",
                         {"m": d["member_id"], "d": decision_id, "a": me}, {"m": STR, "d": STR, "a": STR})[0][0]
            if mine >= COMMENTS_PER_AUTHOR:
                raise RateLimited(f"at most {COMMENTS_PER_AUTHOR} comments per decision", extra={"limit": "comments_per_decision"})
            comment_id = stable_id("decision-comment", decision_id, me, ctx.correlation_id)
            txn.insert("DecisionComments", columns=("member_id", "decision_id", "comment_id", "author_id", "body", "created_at"),
                       values=[(d["member_id"], decision_id, comment_id, me, text, COMMIT_TIMESTAMP)])
            return {"decision_id": decision_id, "comment_id": comment_id, "author_id": me, "body": text, "created_at": iso(now)}

        response, _ = idempotent_command(self.db, principal, "decisions.comment", idempotency_key, dict(body), tx)
        return response

    def comments(self, principal: Principal, decision_id: Any) -> Dict[str, Any]:
        require_scope(principal, "social:read")
        decision_id = require_uuid(decision_id, name="decision_id")
        me = principal.member_id

        def read(s):
            d = self._locate(s, decision_id)
            if d is None:
                raise NotFound("decision not found")
            role = self._visible(s, d, me)
            if not self._comments_visible(s, d, me, role):
                return {"decision_id": decision_id, "items": [], "hidden_until_you_answer": True}
            from brandme_core.domains.persona.experiments import arm

            if d["state"] == "closed" and arm("decision_thread_persistence", me) == "fade_after_close":  # "persist" until approved
                return {"decision_id": decision_id, "items": [], "hidden_until_you_answer": False, "faded": True}
            rows = [dict(zip(COMMENT_COLS, r)) for r in query(
                s, f"SELECT {', '.join(COMMENT_COLS)} FROM DecisionComments WHERE member_id=@m AND decision_id=@d ORDER BY created_at, comment_id",
                {"m": d["member_id"], "d": decision_id}, {"m": STR, "d": STR})]
            items = []
            for c in rows:
                if c["author_id"] != me and blocked_between(s, me, c["author_id"]):
                    continue
                if c["removed_at"] is not None:
                    items.append({"comment_id": c["comment_id"], "removed": True, "created_at": iso(c["created_at"])})
                else:
                    items.append({"comment_id": c["comment_id"], "author_id": c["author_id"], "body": c["body"], "removed": False,
                                  "created_at": iso(c["created_at"]), "mine": c["author_id"] == me})
            return {"decision_id": decision_id, "items": items, "hidden_until_you_answer": False}

        return run_read(self.db, read)

    def remove_comment(self, principal: Principal, decision_id: Any, comment_id: Any) -> Dict[str, Any]:
        """The author withdraws a comment; its text is erased, a placeholder stays."""
        require_scope(principal, "social:write")
        decision_id = require_uuid(decision_id, name="decision_id")
        comment_id = require_uuid(comment_id, name="comment_id")
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            d = self._locate(txn, decision_id)
            if d is None:
                raise NotFound("comment not found")
            c = query(txn, "SELECT author_id, removed_at FROM DecisionComments WHERE member_id=@m AND decision_id=@d AND comment_id=@c",
                      {"m": d["member_id"], "d": decision_id, "c": comment_id}, {"m": STR, "d": STR, "c": STR})
            if not c or c[0][0] != me:
                raise NotFound("comment not found")
            if c[0][1] is None:
                txn.update("DecisionComments", columns=("member_id", "decision_id", "comment_id", "body", "removed_at", "removed_reason"),
                           values=[(d["member_id"], decision_id, comment_id, "", self.clock.now(txn), "author")])
            return {"decision_id": decision_id, "comment_id": comment_id, "removed": True}

        return command(self.db, principal, tx)

    # --------------------------------------------------------------- reads

    def get(self, principal: Principal, decision_id: Any) -> Dict[str, Any]:
        require_scope(principal, "social:read")
        decision_id = require_uuid(decision_id, name="decision_id")

        def read(s):
            d = self._locate(s, decision_id)
            if d is None:
                raise NotFound("decision not found")
            role = self._visible(s, d, principal.member_id)
            return self._dto(s, d, principal.member_id, role, self.clock.now(s))

        return run_read(self.db, read)

    def list(self, principal: Principal, *, role: str = "invited") -> Dict[str, Any]:
        """Pending decisions first (ch.01 §2 /circle)."""
        require_scope(principal, "social:read")
        if role not in ("invited", "mine"):
            raise ValidationFailed("role must be invited or mine", extra={"field": "role"})

        def read(s):
            now = self.clock.now(s)
            if role == "mine":
                ids = [r[0] for r in query(s, "SELECT decision_id FROM Decisions WHERE member_id=@m ORDER BY created_at DESC LIMIT 50",
                                           {"m": principal.member_id}, {"m": STR})]
            else:
                ids = [r[0] for r in query(s, "SELECT decision_id FROM DecisionAudience@{FORCE_INDEX=DecisionAudienceByRecipient} "
                                              "WHERE recipient_id=@m AND NOT removed ORDER BY closes_at DESC LIMIT 50",
                                           {"m": principal.member_id}, {"m": STR})]
            muted = set() if role == "mine" else {r[0] for r in query(s, "SELECT muted_member_id FROM MemberMutes WHERE member_id=@m",
                                                                      {"m": principal.member_id}, {"m": STR})}
            out, hidden = [], 0
            for i in ids:
                d = self._locate(s, i)
                if d is None:
                    continue
                if d["member_id"] in muted:
                    hidden += 1  # still readable and answerable by id; only the list hides it
                    continue
                try:
                    out.append(self._dto(s, d, principal.member_id, self._visible(s, d, principal.member_id), now))
                except NotFound:
                    continue
            out.sort(key=lambda x: (x["state"] != "open", -(x["remaining_seconds"] or 0)))
            return out, hidden

        items, hidden = run_read(self.db, read)
        return {"items": items, "hidden_muted": hidden, "next_cursor": None}
