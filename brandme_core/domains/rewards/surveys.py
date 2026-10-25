"""
Daily-capped surveys and quizzes feeding points (Ultra plan 02, item 5).

* **Operator-authored** (``moderation:admin``). A survey has 1-10 questions and
  a declared ``purpose`` (style, product feedback, house knowledge). Questions
  about health, religion, politics, sexuality, ethnicity, finances or other
  sensitive categories are out of policy; the purpose list exists so
  nothing else can be declared.
* **A quiz** has a correct option for every question. Its score and the correct
  options are returned only after the member answers; the answer key is never
  sent before.
* **One response per member per survey**, with every question answered. A
  completion credits ``survey_completed`` once (10 points). The rule's daily
  cap (30 points, UTC day) makes the fourth completion of a day a recorded
  ``capped`` entry worth 0, so the member can still take part.
* **Answers stay in the member's own data** (export and deletion via the
  ``rewards.surveys`` category). Nothing here shares them with houses.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject

from brandme_core.domains.persona.kernel import (
    STR,
    TS,
    CommandContext,
    DetailedInvalidTransition,
    NotFound,
    Principal,
    ValidationFailed,
    command,
    guard_write,
    idempotent_command,
    iso,
    json_value,
    member_active,
    new_id,
    parse_iso,
    query,
    reject_non_finite,
    reject_unknown_keys,
    require_scope,
    require_text,
    require_uuid,
    run_read,
    server_now,
    stable_id,
)

from . import ledger
from .operators import require_operator
from .rules import RULES, cap_window

KINDS = ("survey", "quiz")
PURPOSES = ("style", "product_feedback", "house_knowledge")
QUESTION_TYPES = ("single", "multi", "scale")
SCALE = (1, 5)
MAX_QUESTIONS = 10
SURVEY_COLS = ("survey_id", "kind", "purpose", "title", "questions", "active", "available_until", "version")


def _question(q: Any, kind: str, i: int) -> Dict[str, Any]:
    if not isinstance(q, Mapping):
        raise ValidationFailed(f"question {i} must be an object")
    reject_unknown_keys(q, ("id", "prompt", "type", "options", "answer"), where=f"question {i}")
    qid = q.get("id")
    if not isinstance(qid, str) or not qid.isidentifier() or len(qid) > 32:
        raise ValidationFailed(f"question {i} needs a short identifier id", extra={"field": f"questions[{i}].id"})
    kind_q = q.get("type")
    if kind_q not in QUESTION_TYPES or (kind == "quiz" and kind_q != "single"):
        raise ValidationFailed(f"question {i} type must be one of {QUESTION_TYPES} (quiz questions are single choice)")
    out: Dict[str, Any] = {"id": qid, "prompt": require_text(q.get("prompt"), name=f"questions[{i}].prompt", max_len=200), "type": kind_q}
    if kind_q == "scale":
        if q.get("options") is not None or q.get("answer") is not None:
            raise ValidationFailed(f"question {i} is a 1-5 scale and takes no options")
        return out
    opts = q.get("options")
    if not isinstance(opts, list) or not 2 <= len(opts) <= 6:
        raise ValidationFailed(f"question {i} needs 2-6 options", extra={"field": f"questions[{i}].options"})
    out["options"] = [require_text(o, name=f"questions[{i}].options", max_len=80) for o in opts]
    if len(set(out["options"])) != len(out["options"]):
        raise ValidationFailed(f"question {i} options must be distinct")
    if kind == "quiz":
        if q.get("answer") not in out["options"]:
            raise ValidationFailed(f"quiz question {i} needs its correct option as answer", extra={"field": f"questions[{i}].answer"})
        out["answer"] = q["answer"]
    elif q.get("answer") is not None:
        raise ValidationFailed("only quiz questions have an answer")
    return out


def _public(q: Mapping[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in q.items() if k != "answer"}


def _answers(questions: List[Dict[str, Any]], body: Any) -> Dict[str, Any]:
    if not isinstance(body, Mapping):
        raise ValidationFailed("body must be an object")
    reject_non_finite(body)
    reject_unknown_keys(body, ("answers",), where="survey response")
    given = body.get("answers")
    if not isinstance(given, Mapping):
        raise ValidationFailed("answers must map each question id to an answer", extra={"field": "answers"})
    ids = [q["id"] for q in questions]
    if set(given) != set(ids):
        raise ValidationFailed("answer every question, and only these", extra={"field": "answers", "question_ids": ids})
    out: Dict[str, Any] = {}
    for q in questions:
        a = given[q["id"]]
        if q["type"] == "single":
            ok = isinstance(a, str) and a in q["options"]
        elif q["type"] == "multi":
            ok = isinstance(a, list) and 1 <= len(a) <= len(q["options"]) and len(set(a)) == len(a) and all(x in q["options"] for x in a)
        else:
            ok = type(a) is int and SCALE[0] <= a <= SCALE[1]
        if not ok:
            raise ValidationFailed(f"answer to {q['id']} is not one of its choices", extra={"field": f"answers.{q['id']}"})
        out[q["id"]] = a
    return out


class SurveyService:
    def __init__(self, database):
        self.db = database

    # ------------------------------------------------------------- operator

    def create_survey(self, operator: Principal, body: Any) -> Dict[str, Any]:
        require_operator(operator)
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_non_finite(body)
        reject_unknown_keys(body, ("kind", "purpose", "title", "questions", "available_until"), where="survey")
        kind, purpose = body.get("kind"), body.get("purpose")
        if kind not in KINDS:
            raise ValidationFailed(f"kind must be one of {KINDS}", extra={"field": "kind"})
        if purpose not in PURPOSES:
            raise ValidationFailed(f"purpose must be one of {PURPOSES}", extra={"field": "purpose"})
        qs = body.get("questions")
        if not isinstance(qs, list) or not 1 <= len(qs) <= MAX_QUESTIONS:
            raise ValidationFailed(f"a survey has 1-{MAX_QUESTIONS} questions", extra={"field": "questions"})
        questions = [_question(q, kind, i) for i, q in enumerate(qs)]
        if len({q["id"] for q in questions}) != len(questions):
            raise ValidationFailed("question ids must be unique")
        row = {"survey_id": new_id(), "kind": kind, "purpose": purpose, "title": require_text(body.get("title"), name="title", max_len=120),
               "questions": questions, "active": True,
               "available_until": parse_iso(body["available_until"], name="available_until") if body.get("available_until") else None,
               "version": 1}

        def tx(txn, ctx: CommandContext):
            txn.insert("Surveys", columns=(*SURVEY_COLS, "created_by", "created_at"),
                       values=[[*(JsonObject(row[c]) if c == "questions" else row[c] for c in SURVEY_COLS), operator.actor_ref, COMMIT_TIMESTAMP]])
            return {**{k: v for k, v in row.items() if k != "available_until"}, "available_until": iso(row["available_until"])}

        return command(self.db, operator, tx)

    def deactivate(self, operator: Principal, survey_id: Any) -> Dict[str, Any]:
        require_operator(operator)
        survey_id = require_uuid(survey_id, name="survey_id")

        def tx(txn, ctx: CommandContext):
            cur = query(txn, "SELECT version FROM Surveys WHERE survey_id=@s", {"s": survey_id}, {"s": STR})
            if not cur:
                raise NotFound("survey not found")
            txn.update("Surveys", columns=("survey_id", "active", "version"), values=[(survey_id, False, cur[0][0] + 1)])
            return {"survey_id": survey_id, "active": False}

        return command(self.db, operator, tx)

    # --------------------------------------------------------------- member

    def _survey(self, snap, survey_id: str) -> Optional[Dict[str, Any]]:
        rows = query(snap, f"SELECT {', '.join(SURVEY_COLS)} FROM Surveys WHERE survey_id=@s", {"s": survey_id}, {"s": STR})
        if not rows:
            return None
        d = dict(zip(SURVEY_COLS, rows[0]))
        d["questions"] = json_value(d["questions"])
        return d

    def _rewarded_today(self, snap, member_id: str, now) -> int:
        rule = RULES["survey_completed"]
        start, end = cap_window(rule.cap_window, now)
        return query(snap, "SELECT COUNT(*) FROM RewardEntries WHERE member_id=@m AND rule_id=@r AND state='posted' "
                           "AND qualifying_at >= @s AND qualifying_at < @e",
                     {"m": member_id, "r": rule.id, "s": start, "e": end}, {"m": STR, "r": STR, "s": TS, "e": TS})[0][0]

    def available(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "rewards:read")
        me = principal.member_id

        def read(s):
            now = server_now(s)
            rows = query(s, f"SELECT {', '.join('v.' + c for c in SURVEY_COLS)} FROM Surveys v WHERE v.active "
                            "AND (v.available_until IS NULL OR v.available_until > @n) "
                            "AND NOT EXISTS (SELECT 1 FROM SurveyResponses r WHERE r.member_id=@m AND r.survey_id=v.survey_id) "
                            "ORDER BY v.created_at DESC LIMIT 50", {"m": me, "n": now}, {"m": STR, "n": TS})
            rule = RULES["survey_completed"]
            left = max(0, rule.cap_points // rule.points - self._rewarded_today(s, me, now))
            items = []
            for r in rows:
                d = dict(zip(SURVEY_COLS, r))
                items.append({"survey_id": d["survey_id"], "kind": d["kind"], "purpose": d["purpose"], "title": d["title"],
                              "questions": [_public(q) for q in json_value(d["questions"])], "available_until": iso(d["available_until"]),
                              "points": rule.points if left else 0})
            return {"items": items, "today": {"rewarded_remaining": left, "points_each": rule.points, "resets": "00:00 UTC"},
                    "answers_are": "Kept in your own data; never shared with houses"}

        return run_read(self.db, read)

    def respond(self, principal: Principal, survey_id: Any, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        require_scope(principal, "rewards:write")
        if principal.delegation_id:
            raise DetailedInvalidTransition("surveys are answered by the member", code="member_only")
        survey_id = require_uuid(survey_id, name="survey_id")
        me = principal.member_id

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, me):
                raise NotFound("member not found")
            sv = self._survey(txn, survey_id)
            now = server_now(txn)
            if sv is None or not sv["active"] or (sv["available_until"] is not None and sv["available_until"] <= now):
                raise NotFound("survey not found")
            answers = _answers(sv["questions"], body)
            guard_write(txn, me, "rewards.surveys")
            if query(txn, "SELECT 1 FROM SurveyResponses WHERE member_id=@m AND survey_id=@s", {"m": me, "s": survey_id}, {"m": STR, "s": STR}):
                raise DetailedInvalidTransition("you already answered this survey", code="already_answered")
            score = None
            result: Dict[str, Any] = {"survey_id": survey_id, "kind": sv["kind"]}
            if sv["kind"] == "quiz":
                correct = {q["id"]: q["answer"] for q in sv["questions"]}
                score = sum(1 for k, v in answers.items() if correct[k] == v)
                result.update(score=score, out_of=len(correct), correct=correct)
            txn.insert("SurveyResponses", columns=("member_id", "survey_id", "answers", "score", "submitted_at"),
                       values=[(me, survey_id, JsonObject(answers), score, COMMIT_TIMESTAMP)])
            reward = ledger.credit(txn, ctx, me, RULES["survey_completed"], stable_id("survey-completed", survey_id, me), now, [f"survey:{survey_id}"])
            result["reward"] = {"status": reward["status"], "points": reward.get("points", 0)}
            return result

        response, _ = idempotent_command(self.db, principal, "surveys.respond", idempotency_key, {"survey_id": survey_id, "body": body}, tx)
        return response


def export_responses(snap, member_id: str) -> List[Dict[str, Any]]:
    return [{"survey_id": r[0], "title": r[1], "answers": json_value(r[2]), "score": r[3], "submitted_at": iso(r[4])}
            for r in query(snap, "SELECT r.survey_id, v.title, r.answers, r.score, r.submitted_at FROM SurveyResponses r "
                                 "LEFT JOIN Surveys v ON v.survey_id = r.survey_id WHERE r.member_id=@m ORDER BY r.submitted_at",
                           {"m": member_id}, {"m": STR})]
