"""
Least-disclosure, revocable shares (ch.01 §8; ch.03 ShareGrant, POST/DELETE
/shares; contracts README rule 11; BM-SOC-009..011).

* ``allowed_fields`` is a typed request checked against a per-subject
  allowlist, not a column selector. Anything else is refused with the list of
  refused fields. Prices, sizes, body data, receipts, tag serials, addresses,
  owner ids, ownership/chain identity and closet totals are never shareable.
* Defaults are least disclosure: the preview contains only the requested
  allowed fields of the one subject. An outfit share lists the items of the
  pinned version only, never the rest of the closet.
* The opaque link token is returned once (create response only). Only its
  SHA-256 is stored; an idempotent replay never returns it again.
* The filtered copy is rendered at share time into ``SharePreviews`` (the
  controlled preview cache). Every access re-checks revocation, expiry,
  audience, blocks and that the subject still exists, under current
  permissions. Revocation sets ``revoked_at`` and deletes the cached preview
  in the same transaction and emits ``share.revoked`` for projection purges.
  An image someone already downloaded cannot be recalled; the UI says so.
* ``closet_capsule`` and ``badge`` subjects belong to contracts but have no
  backing entity in this lane yet (capsules: spatial lane; badges: rewards);
  they are refused with ``unsupported_subject_type`` rather than faked.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Tuple

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject, KeySet

from brandme_core.domains import DomainError
from brandme_core.domains.persona.kernel import (
    INT,
    STR,
    STR_ARRAY,
    TS,
    CommandContext,
    DetailedInvalidTransition,
    NotFound,
    Principal,
    ValidationFailed,
    command,
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
    require_uuid,
    run_read,
    server_now,
)

from . import events as _events  # noqa: F401
from . import policy
from .notifications import blocked_between, notify
from .relationships import are_friends

SUBJECT_TYPES = ("outfit_version", "wardrobe_item", "closet_capsule", "persona_snapshot", "badge")
SUPPORTED_SUBJECTS = ("outfit_version", "wardrobe_item", "persona_snapshot")
AUDIENCES = ("selected_members", "unlisted", "public")
CREATE_KEYS = ("subject_type", "subject_id", "audience", "allowed_fields", "recipient_ids", "expires_at")

# Per-subject allowlists. Everything not listed is refused.
SHAREABLE_FIELDS: Dict[str, Tuple[str, ...]] = {
    "wardrobe_item": ("title", "category", "color_family", "colors", "materials"),
    "outfit_version": ("title", "occasion", "notes", "items"),
    "persona_snapshot": ("saved_name", "summary", "declared_axes"),
}
# What an outfit share discloses about each item of the pinned version.
OUTFIT_ITEM_FIELDS = ("title", "category", "color_family", "colors")

# PD-10 / PD-11 defaults, pending ratification: see ``policy``.
MIN_LIFETIME = policy.SHARE_MIN_LIFETIME
MAX_LIFETIME = policy.SHARE_MAX_LIFETIME
MAX_ACTIVE_SHARES = policy.SHARE_MAX_ACTIVE

GRANT_COLS = ("member_id", "share_id", "subject_type", "subject_id", "subject_version", "audience", "allowed_fields",
              "recipient_ids", "expires_at", "revoked_at", "version", "created_at")


class ShareUnavailable(DomainError):
    """The token was valid once; the share is revoked, expired or its subject is gone."""

    status, code = 410, "share_unavailable"

    def __init__(self, reason: str):
        super().__init__("this share is no longer available")
        self.extra = {"reason": reason}


def gone(reason: str) -> DomainError:
    """PD-11: 410 with a reason by default; 404 if the founder overrides it."""
    return ShareUnavailable(reason) if policy.SHARE_GONE_STATUS == 410 else NotFound("share not found")


def _span(d: timedelta) -> str:
    return f"{d.days} days" if d.days else f"{int(d.total_seconds() // 60)} minutes"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def parse_share(body: Any) -> Dict[str, Any]:
    if not isinstance(body, Mapping):
        raise ValidationFailed("body must be an object")
    reject_non_finite(body)
    reject_unknown_keys(body, CREATE_KEYS, where="share")
    missing = [k for k in CREATE_KEYS if k not in body]
    if missing:
        raise ValidationFailed(f"missing fields: {', '.join(missing)}", extra={"missing_fields": missing})
    subject_type = body["subject_type"]
    if subject_type not in SUBJECT_TYPES:
        raise ValidationFailed("unknown subject_type", extra={"field": "subject_type"})
    if subject_type not in SUPPORTED_SUBJECTS:
        raise ValidationFailed(f"{subject_type} shares are not available yet", extra={"field": "subject_type", "code": "unsupported_subject_type"})
    audience = body["audience"]
    if audience not in AUDIENCES:
        raise ValidationFailed("audience must be selected_members, unlisted or public", extra={"field": "audience"})
    fields = body["allowed_fields"]
    if not isinstance(fields, list) or not (1 <= len(fields) <= 30) or not all(isinstance(f, str) and 1 <= len(f) <= 64 for f in fields):
        raise ValidationFailed("allowed_fields must list 1-30 field names", extra={"field": "allowed_fields"})
    if len(set(fields)) != len(fields):
        raise ValidationFailed("allowed_fields must be unique", extra={"field": "allowed_fields"})
    refused = sorted(f for f in fields if f not in SHAREABLE_FIELDS[subject_type])
    if refused:
        raise ValidationFailed("some fields cannot be shared", extra={"field": "allowed_fields", "refused_fields": refused,
                                                                      "shareable_fields": list(SHAREABLE_FIELDS[subject_type])})
    recips = body["recipient_ids"]
    if not isinstance(recips, list) or len(recips) > 100:
        raise ValidationFailed("recipient_ids must list at most 100 members", extra={"field": "recipient_ids"})
    recips = [require_uuid(r, name="recipient_ids") for r in recips]
    if len(set(recips)) != len(recips):
        raise ValidationFailed("recipient_ids must be unique", extra={"field": "recipient_ids"})
    if audience == "selected_members" and not recips:
        raise ValidationFailed("choose at least one member", extra={"field": "recipient_ids"})
    if audience != "selected_members" and recips:
        raise ValidationFailed("recipient_ids apply only to selected_members", extra={"field": "recipient_ids"})
    return {
        "subject_type": subject_type,
        "subject_id": require_uuid(body["subject_id"], name="subject_id"),
        "audience": audience,
        "allowed_fields": sorted(fields),
        "recipient_ids": recips,
        "expires_at": parse_iso(body["expires_at"], name="expires_at"),
    }


def revoke_grant(txn, ctx: CommandContext, g: Dict[str, Any]) -> Dict[str, Any]:
    """Revoke inside the caller's transaction (owner revoke or moderation)."""
    if g["revoked_at"] is not None:
        return g
    now = server_now(txn)
    g.update(revoked_at=now, version=g["version"] + 1)
    txn.update("ShareGrants", columns=("member_id", "share_id", "revoked_at", "version"), values=[(g["member_id"], g["share_id"], now, g["version"])])
    txn.delete("SharePreviews", KeySet(keys=[[g["member_id"], g["share_id"]]]))
    # Recipients' unread "shared with you" notices disappear with the share.
    txn.execute_update("DELETE FROM Notifications WHERE member_id IN UNNEST(@r) AND subject_ref=@s AND type='share_received' AND read_at IS NULL",
                       params={"r": list(g["recipient_ids"] or []), "s": f"share:{g['share_id']}"}, param_types={"r": STR_ARRAY, "s": STR})
    ctx.emit("share.revoked", "1", "share", g["share_id"], g["version"], {"share_id": g["share_id"], "owner_id": g["member_id"]}, "member_private")
    return g


class ShareService:
    def __init__(self, database):
        self.db = database

    # ------------------------------------------------------------ helpers

    def _grant_by_id(self, txn, share_id: str) -> Optional[Dict[str, Any]]:
        rows = query(txn, f"SELECT {', '.join(GRANT_COLS)} FROM ShareGrants@{{FORCE_INDEX=ShareGrantsById}} WHERE share_id=@s",
                     {"s": share_id}, {"s": STR})
        return dict(zip(GRANT_COLS, rows[0])) if rows else None

    def _grant_by_token(self, txn, token: str) -> Optional[Dict[str, Any]]:
        rows = query(txn, f"SELECT {', '.join(GRANT_COLS)} FROM ShareGrants@{{FORCE_INDEX=ShareGrantsByToken}} WHERE token_hash=@h",
                     {"h": token_hash(token)}, {"h": STR})
        return dict(zip(GRANT_COLS, rows[0])) if rows else None

    def _render(self, txn, owner: str, subject_type: str, subject_id: str, fields: List[str]) -> Tuple[Optional[int], Dict[str, Any]]:
        """Return (pinned subject version, filtered copy). Raises if the subject is not the owner's."""
        m = {"m": owner, "s": subject_id}
        mt = {"m": STR, "s": STR}
        if subject_type == "wardrobe_item":
            rows = query(txn, "SELECT title, category, color_family, colors, materials FROM WardrobeItems "
                              "WHERE member_id=@m AND item_id=@s AND collection != 'archive'", m, mt)
            if not rows:
                raise ValidationFailed("you can share your own closet items", extra={"field": "subject_id"})
            full = dict(zip(("title", "category", "color_family", "colors", "materials"), rows[0]))
            full["colors"] = list(full["colors"] or [])
            full["materials"] = list(full["materials"] or [])
            return None, {k: full[k] for k in fields}
        if subject_type == "outfit_version":
            o = query(txn, "SELECT title, head_version FROM Outfits WHERE member_id=@m AND outfit_id=@s AND NOT archived", m, mt)
            if not o:
                raise ValidationFailed("you can share your own outfits", extra={"field": "subject_id"})
            title, head = o[0]
            v = query(txn, "SELECT layer_order, occasion, notes FROM OutfitVersions WHERE member_id=@m AND outfit_id=@s AND version_no=@v",
                      {**m, "v": head}, {**mt, "v": INT})
            layer_order, occasion, notes = v[0]
            full: Dict[str, Any] = {"title": title, "occasion": occasion, "notes": notes}
            if "items" in fields:
                items = {r[0]: r[1:] for r in query(
                    txn, "SELECT item_id, title, category, color_family, colors FROM WardrobeItems WHERE member_id=@m AND item_id IN UNNEST(@ids)",
                    {"m": owner, "ids": list(layer_order)}, {"m": STR, "ids": STR_ARRAY})}
                # Position, not item id: the link reveals the composition, not closet identifiers.
                full["items"] = [
                    {"position": i, **dict(zip(OUTFIT_ITEM_FIELDS, (t, c, cf, list(cs or []))))}
                    for i, (t, c, cf, cs) in enumerate(items[x] for x in layer_order if x in items)
                ]
            return head, {k: full[k] for k in fields}
        rows = query(txn, "SELECT saved_name, redacted_summary, axes_snapshot, profile_version FROM PersonaSnapshots "
                          "WHERE member_id=@m AND snapshot_id=@s", m, mt)
        if not rows:
            raise ValidationFailed("you can share your own style snapshots", extra={"field": "subject_id"})
        saved_name, summary, axes, version = rows[0]
        declared = {k: v for k, v in (json_value(axes).get("declared") or {}).items() if v is not None}
        full = {"saved_name": saved_name, "summary": summary, "declared_axes": declared}
        return version, {k: full[k] for k in fields}

    def _subject_exists(self, txn, g: Mapping[str, Any]) -> bool:
        m = {"m": g["member_id"], "s": g["subject_id"]}
        mt = {"m": STR, "s": STR}
        if g["subject_type"] == "wardrobe_item":
            return bool(query(txn, "SELECT 1 FROM WardrobeItems WHERE member_id=@m AND item_id=@s AND collection != 'archive'", m, mt))
        if g["subject_type"] == "outfit_version":
            return bool(query(txn, "SELECT 1 FROM OutfitVersions WHERE member_id=@m AND outfit_id=@s AND version_no=@v",
                              {**m, "v": g["subject_version"]}, {**mt, "v": INT})) and bool(
                query(txn, "SELECT 1 FROM Outfits WHERE member_id=@m AND outfit_id=@s AND NOT archived", m, mt))
        return bool(query(txn, "SELECT 1 FROM PersonaSnapshots WHERE member_id=@m AND snapshot_id=@s", m, mt))

    @staticmethod
    def _owner_dto(g: Mapping[str, Any], now: datetime) -> Dict[str, Any]:
        state = "revoked" if g["revoked_at"] else ("expired" if g["expires_at"] <= now else "active")
        return {
            "share_id": g["share_id"],
            "subject_type": g["subject_type"],
            "subject_id": g["subject_id"],
            "subject_version": None if g["subject_version"] is None else str(g["subject_version"]),
            "audience": g["audience"],
            "allowed_fields": list(g["allowed_fields"]),
            "recipient_ids": list(g["recipient_ids"] or []),
            "expires_at": iso(g["expires_at"]),
            "revoked_at": iso(g["revoked_at"]),
            "state": state,
            "version": str(g["version"]),
        }

    # ------------------------------------------------------------- create

    def create(self, principal: Principal, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        """Returns the grant plus ``token`` (first response only)."""
        require_scope(principal, "social:write")
        req = parse_share(body)
        owner = principal.member_id
        token = secrets.token_urlsafe(32)  # generated once, outside the retried callback

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, owner):
                raise NotFound("member not found")
            now = server_now(txn)
            from brandme_core.domains.persona.privacy_guard import ProcessingFrozen, assert_processing_allowed

            try:
                assert_processing_allowed(txn, owner, "social.shares", now)
            except ProcessingFrozen:
                raise DetailedInvalidTransition("sharing is paused while a privacy request is processed", code="processing_frozen")
            if not (now + MIN_LIFETIME <= req["expires_at"] <= now + MAX_LIFETIME):
                raise ValidationFailed(f"expires_at must be between {_span(MIN_LIFETIME)} and {_span(MAX_LIFETIME)} from now",
                                       extra={"field": "expires_at", "server_time": iso(now)})
            unreachable = sorted(r for r in req["recipient_ids"] if r == owner or not are_friends(txn, owner, r))
            if unreachable:
                raise DetailedInvalidTransition("recipients must be friends you can reach", code="ineligible_recipients",
                                                extra={"ineligible_recipient_ids": unreachable})
            active = query(txn, "SELECT COUNT(*) FROM ShareGrants WHERE member_id=@m AND revoked_at IS NULL AND expires_at > @n",
                           {"m": owner, "n": now}, {"m": STR, "n": TS})[0][0]
            if active >= MAX_ACTIVE_SHARES:
                raise DetailedInvalidTransition("revoke an old share before creating another", code="too_many_shares")
            version, preview = self._render(txn, owner, req["subject_type"], req["subject_id"], req["allowed_fields"])
            share_id = new_id()
            g = {
                "member_id": owner, "share_id": share_id, "subject_type": req["subject_type"], "subject_id": req["subject_id"],
                "subject_version": version, "audience": req["audience"], "allowed_fields": req["allowed_fields"],
                "recipient_ids": req["recipient_ids"] or None, "expires_at": req["expires_at"], "revoked_at": None, "version": 1,
            }
            txn.insert("ShareGrants", columns=(*GRANT_COLS[:-1], "token_hash", "created_at"),
                       values=[[*(g[c] for c in GRANT_COLS[:-1]), token_hash(token), COMMIT_TIMESTAMP]])
            txn.insert("SharePreviews", columns=("member_id", "share_id", "preview", "rendered_at"),
                       values=[(owner, share_id, JsonObject(preview), COMMIT_TIMESTAMP)])
            ev = ctx.emit("share.created", "1", "share", share_id, 1,
                          {"share_id": share_id, "owner_id": owner, "subject_type": req["subject_type"]}, "member_private")
            for r in req["recipient_ids"]:
                notify(txn, recipient_id=r, event_id=ev.event_id, type_="share_received", actor_member_id=owner,
                       subject_ref=f"share:{share_id}", payload={"share_id": share_id})
            out = self._owner_dto({**g, "created_at": now}, now)
            out["preview"] = preview
            return out

        response, replayed = idempotent_command(self.db, principal, "shares.create", idempotency_key, dict(body), tx)
        if replayed:
            return {**response, "token": None, "token_already_issued": True}
        return {**response, "token": token}

    # ------------------------------------------------------------- revoke

    def revoke(self, principal: Principal, share_id: Any) -> Dict[str, Any]:
        require_scope(principal, "social:write")
        share_id = require_uuid(share_id, name="share_id")

        def tx(txn, ctx: CommandContext):
            g = self._grant_by_id(txn, share_id)
            if g is None or g["member_id"] != principal.member_id:
                raise NotFound("share not found")
            return self._owner_dto(revoke_grant(txn, ctx, g), server_now(txn))

        return command(self.db, principal, tx)

    # -------------------------------------------------------------- access

    def _open(self, s, g: Optional[Dict[str, Any]], viewer: Optional[str]) -> Dict[str, Any]:
        if g is None:
            raise NotFound("share not found")
        now = server_now(s)
        owner = g["member_id"]
        if viewer is not None and viewer != owner and blocked_between(s, viewer, owner):
            raise NotFound("share not found")
        if g["audience"] == "selected_members" and viewer != owner:
            if viewer is None or viewer not in (g["recipient_ids"] or []) or not are_friends(s, owner, viewer):
                raise NotFound("share not found")
        if g["revoked_at"] is not None:
            raise gone("revoked")
        if g["expires_at"] <= now:
            raise gone("expired")
        if not member_active(s, owner) or not self._subject_exists(s, g):
            raise gone("removed")
        rows = query(s, "SELECT preview FROM SharePreviews WHERE member_id=@m AND share_id=@s",
                     {"m": owner, "s": g["share_id"]}, {"m": STR, "s": STR})
        if not rows:
            raise gone("removed")
        return {
            "share_id": g["share_id"],
            "subject_type": g["subject_type"],
            "fields": json_value(rows[0][0]),
            "expires_at": iso(g["expires_at"]),
            "notice": "Revoking a share stops access here; copies someone already saved cannot be recalled.",
        }

    def open_by_token(self, token: Any, viewer: Optional[Principal] = None) -> Dict[str, Any]:
        """Link access. Anonymous viewers may open unlisted/public shares only."""
        if not isinstance(token, str) or not (16 <= len(token) <= 128) or not token.isascii():
            raise NotFound("share not found")
        if viewer is not None:
            require_scope(viewer, "social:read")
        vid = viewer.member_id if viewer is not None else None
        return run_read(self.db, lambda s: self._open(s, self._grant_by_token(s, token), vid))

    def open_for_member(self, principal: Principal, share_id: Any) -> Dict[str, Any]:
        """Selected-member access from a notification; no token needed."""
        require_scope(principal, "social:read")
        share_id = require_uuid(share_id, name="share_id")

        def read(s):
            g = self._grant_by_id(s, share_id)
            if g is not None and g["audience"] != "selected_members" and g["member_id"] != principal.member_id:
                g = None  # link shares are reachable by token only
            return self._open(s, g, principal.member_id)

        return run_read(self.db, read)

    def list(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "social:read")

        def read(s):
            now = server_now(s)
            rows = query(s, f"SELECT {', '.join(GRANT_COLS)} FROM ShareGrants WHERE member_id=@m ORDER BY created_at DESC LIMIT 100",
                         {"m": principal.member_id}, {"m": STR})
            return [self._owner_dto(dict(zip(GRANT_COLS, r)), now) for r in rows]

        return {"items": run_read(self.db, read), "next_cursor": None}
