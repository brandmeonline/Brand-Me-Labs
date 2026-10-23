"""
Guest → account migration (ch.01 §3.1; BM-ONB-004).

A guest's device-local onboarding state migrates atomically when they sign
up or sign in. Migration is idempotent at the *domain* level, not only per
Idempotency-Key: signing in twice (even from a new session with a new key)
finds the existing ``GuestMigrations`` row for (member, guest namespace) and
writes nothing. A guest namespace can be claimed by one member only.

Account data always wins: guest declared values fill only axes the account
has not answered. Other domains (wardrobe: saved products, outfits, closet
theme) plug in as *sections*; every section applies inside the same Spanner
transaction, so either the whole guest state migrates or none of it does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Mapping, Optional

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

from .events import emit_updated
from .kernel import (
    STR,
    CommandContext,
    DetailedInvalidTransition,
    NotFound,
    Principal,
    ValidationFailed,
    canonical_digest,
    idempotent_command,
    member_active,
    query,
    reject_non_finite,
    reject_unknown_keys,
    require_scope,
    stable_id,
)
from .model import AXIS_KEYS, validate_axis_key, validate_axis_value
from .service import PersonaService

NAMESPACE_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
INTENTS = ("everyday", "work", "going_out", "occasion")
BODY_KEYS = ("guest_namespace_id", "persona", "saved_look", "sections")
PERSONA_KEYS = ("declared", "onboarding_intent", "learning_enabled")


@dataclass(frozen=True)
class GuestSection:
    """A domain's slice of guest state (registered by that domain)."""

    name: str
    validate: Callable[[Any], Any]
    apply: Callable[[Any, CommandContext, str, Any], Dict[str, Any]]  # (txn, ctx, member_id, normalized) -> summary


_SECTIONS: Dict[str, GuestSection] = {}


def register_guest_section(section: GuestSection) -> None:
    existing = _SECTIONS.get(section.name)
    if existing is not None and existing is not section:
        raise RuntimeError(f"guest section {section.name} already registered")
    _SECTIONS[section.name] = section


def registered_sections() -> List[str]:
    return sorted(_SECTIONS)


def _parse(body: Any) -> Dict[str, Any]:
    if not isinstance(body, Mapping):
        raise ValidationFailed("body must be an object")
    reject_non_finite(body)
    reject_unknown_keys(body, BODY_KEYS, where="guest migration")
    ns = body.get("guest_namespace_id")
    if not isinstance(ns, str) or not NAMESPACE_RE.match(ns):
        raise ValidationFailed("guest_namespace_id must be 16-64 characters [A-Za-z0-9_-]", extra={"field": "guest_namespace_id"})
    persona = body.get("persona") or {}
    if not isinstance(persona, Mapping):
        raise ValidationFailed("persona must be an object")
    reject_unknown_keys(persona, PERSONA_KEYS, where="guest persona")
    declared: Dict[str, Dict[str, Any]] = {}
    for k, v in (persona.get("declared") or {}).items():
        k = validate_axis_key(k)
        if not isinstance(v, Mapping):
            raise ValidationFailed(f"declared.{k} must be an object")
        reject_unknown_keys(v, ("value", "locked"), where=f"declared.{k}")
        value = validate_axis_value(v.get("value"), name=f"declared.{k}.value")
        locked = v.get("locked", value is not None)
        if not isinstance(locked, bool) or (value is None and locked):
            raise ValidationFailed(f"declared.{k}.locked must be a boolean and needs a value")
        if value is not None:
            declared[k] = {"value": value, "locked": locked}
    intent = persona.get("onboarding_intent")
    if intent is not None and intent not in INTENTS:
        if not isinstance(intent, str) or not (1 <= len(intent.strip()) <= 60):
            raise ValidationFailed("onboarding_intent must be a known intent or 1-60 characters")
        intent = intent.strip()
    learning = persona.get("learning_enabled")
    if learning is not None and not isinstance(learning, bool):
        raise ValidationFailed("learning_enabled must be a boolean")
    saved_look = body.get("saved_look", False)
    if not isinstance(saved_look, bool):
        raise ValidationFailed("saved_look must be a boolean")
    sections_in = body.get("sections") or {}
    if not isinstance(sections_in, Mapping):
        raise ValidationFailed("sections must be an object")
    unknown = sorted(set(sections_in) - set(_SECTIONS))
    if unknown:
        raise ValidationFailed(f"unsupported guest sections: {', '.join(unknown)}", extra={"rejected_fields": unknown})
    sections = {name: _SECTIONS[name].validate(payload) for name, payload in sorted(sections_in.items())}
    return {
        "guest_namespace_id": ns,
        "declared": declared,
        "onboarding_intent": intent,
        "learning_enabled": learning,
        "saved_look": saved_look,
        "sections": sections,
    }


class GuestMigrationService:
    def __init__(self, database, persona: PersonaService):
        self.db = database
        self.persona = persona

    def migrate(self, principal: Principal, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        require_scope(principal, "profile:write")
        req = _parse(body)
        digest = canonical_digest(
            {k: v for k, v in req.items() if k != "sections"} | {"sections": {k: repr(v) for k, v in req["sections"].items()}}
        )
        member_id = principal.member_id
        migration_id = stable_id("guest-migration", member_id, req["guest_namespace_id"])

        def txn_fn(txn, ctx: CommandContext) -> Dict[str, Any]:
            svc = self.persona
            if svc._tombstoned(txn, member_id) or not member_active(txn, member_id):
                raise NotFound("member not found")
            prior = query(
                txn,
                "SELECT member_id, payload_digest FROM GuestMigrations@{FORCE_INDEX=GuestMigrationsByNamespace} "
                "WHERE guest_namespace_id=@n",
                {"n": req["guest_namespace_id"]},
                {"n": STR},
            )
            if prior:
                owner, _digest = prior[0]
                if owner != member_id:
                    raise DetailedInvalidTransition(
                        "this guest data was already saved to a different account", code="guest_namespace_claimed"
                    )
                p = svc._load(txn, member_id)
                return {
                    "migration_id": migration_id,
                    "status": "already_migrated",
                    "profile_version": str(p.version),
                    "applied_axes": [],
                    "kept_account_axes": [],
                    "sections": {},
                }
            now = svc.clock.now()
            p = svc._load(txn, member_id)
            created = not p.exists
            applied, kept = [], []
            for k in AXIS_KEYS:
                g = req["declared"].get(k)
                if g is None:
                    continue
                if p.axes[k].declared is not None:
                    kept.append(k)  # account data wins
                    continue
                p.axes[k] = replace(p.axes[k], declared=g["value"], locked=g["locked"], declared_revision=p.version + 1)
                applied.append(k)
            if created and req["learning_enabled"] is not None:
                p.learning_enabled = req["learning_enabled"]
            if req["onboarding_intent"] and not p.onboarding_intent:
                p.onboarding_intent = req["onboarding_intent"]
            p.version += 1
            svc._write(txn, p, now)
            emit_updated(ctx, member_id, p.version, "guest_migrated", applied)
            ctx.emit(
                "persona.guest.migrated",
                "1",
                "persona_profile",
                member_id,
                p.version,
                {
                    "member_id": member_id,
                    "migration_id": migration_id,
                    "profile_version": str(p.version),
                    "saved_look": req["saved_look"],
                },
                "member_private",
            )
            summaries = {
                name: _SECTIONS[name].apply(txn, ctx, member_id, payload) for name, payload in req["sections"].items()
            }
            txn.insert(
                "GuestMigrations",
                columns=("member_id", "guest_namespace_id", "payload_digest", "migrated_at"),
                values=[(member_id, req["guest_namespace_id"], digest, COMMIT_TIMESTAMP)],
            )
            return {
                "migration_id": migration_id,
                "status": "migrated",
                "profile_version": str(p.version),
                "applied_axes": applied,
                "kept_account_axes": kept,
                "sections": summaries,
            }

        from google.api_core.exceptions import AlreadyExists

        try:
            response, _replayed = idempotent_command(
                self.db, principal, "guest.migrate", idempotency_key, {"digest": digest}, txn_fn
            )
        except AlreadyExists:
            # Another account committed the same namespace concurrently (unique index).
            raise DetailedInvalidTransition(
                "this guest data was already saved to a different account", code="guest_namespace_claimed"
            ) from None
        return response
