"""
Media uploads and photo try-on jobs (W08 server side; ch.02 §6.3, ch.03 §6/§8;
BM-AR-007/008/009/010, BM-DATA-009).

Invariants
* **No provider upload without explicit consent.** A job needs
  ``consent.accepted = true`` for the approved provider's *current* terms;
  dispatch re-checks that the consent is still unrevoked and the member is
  not frozen, immediately before the upload. A revoked consent cancels queued
  jobs and deletes their media without any provider call.
* **Calibrated fit is unavailable** (no validated measurement pipeline); the
  request is refused and no generated image is ever labelled as fit. Live
  overlay is on-device only: the server accepts no camera frames.
* **Retention:** uploaded inputs and unsaved outputs expire 24 h after
  creation (server time). Inputs are deleted as soon as processing ends.
  Saving is an explicit member action; saved outputs stay until deleted.
* **Deletion follows a manifest:** the job and every app-owned object linked
  to it (input, output, derivatives) are tombstoned in one transaction, then
  blobs are purged and provider deletion is requested where the provider
  supports it. Provider-side retention is disclosed, never promised.
* Provider calls and blob I/O never run inside a Spanner transaction
  callback; workers claim work in a transaction, act, then record the
  outcome in another transaction that re-checks the state.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

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
    member_active,
    new_id,
    parse_iso,
    query,
    reject_unknown_keys,
    require_scope,
    require_strict_int,
    require_uuid,
    run_read,
    run_txn,
    server_now,
    service_principal,
)
from brandme_core.domains.persona.privacy_guard import ProcessingFrozen, assert_processing_allowed

from . import events as _events  # noqa: F401
from .providers import GENERATED_LABEL, ProviderRegistry, TryOnProvider
from .store import ALLOWED_TYPES, MAX_BYTES, MediaStore, sniff, storage_ref

RETENTION = timedelta(hours=24)
UPLOAD_URL_TTL = timedelta(minutes=15)
MEDIA_COLS = ("member_id", "media_id", "job_id", "kind", "state", "storage_ref", "content_type", "content_hash", "bytes", "rejection_code",
              "saved", "expires_at", "deleted_at", "purged_at", "version")
JOB_COLS = ("member_id", "job_id", "mode", "consent_id", "item_id", "product_id", "provider_id", "provider_job_ref", "state", "fidelity_label",
            "input_media_ref", "output_media_ref", "saved", "expires_at", "error_code", "provider_deletion", "version")
CONSENT_COLS = ("member_id", "consent_id", "mode", "provider_id", "purposes", "granted_at", "revoked_at", "terms_version")
MODES = ("photo_preview", "live_overlay", "calibrated_fit")
LABEL_TEXT = "Generated visual preview. Not a fit or size guarantee."

CatalogCheck = Callable[[Any, str], bool]
Purge = List[Tuple[str, str, str]]  # (member_id, media_id, storage_ref)


class MediaService:
    def __init__(self, database, store: MediaStore, providers: ProviderRegistry, *, catalog_check: Optional[CatalogCheck] = None,
                 daily_job_limit: int = 10):
        self.db = database
        self.store = store
        self.providers = providers
        self.catalog_check = catalog_check or (lambda _txn, _pid: False)  # no catalog wired: product subjects refused
        self.daily_job_limit = daily_job_limit
        from . import deletion

        deletion.configure_store(store, database)

    # ----------------------------------------------------------------- rows

    def _media(self, txn, member_id: str, media_id: str) -> Optional[Dict[str, Any]]:
        rows = query(txn, f"SELECT {', '.join(MEDIA_COLS)} FROM MediaObjects WHERE member_id=@m AND media_id=@i",
                     {"m": member_id, "i": media_id}, {"m": STR, "i": STR})
        return dict(zip(MEDIA_COLS, rows[0])) if rows else None

    def _job(self, txn, member_id: str, job_id: str) -> Optional[Dict[str, Any]]:
        rows = query(txn, f"SELECT {', '.join(JOB_COLS)} FROM TryOnJobs WHERE member_id=@m AND job_id=@j",
                     {"m": member_id, "j": job_id}, {"m": STR, "j": STR})
        return dict(zip(JOB_COLS, rows[0])) if rows else None

    def _job_any(self, txn, job_id: str) -> Optional[Dict[str, Any]]:
        rows = query(txn, f"SELECT {', '.join(JOB_COLS)} FROM TryOnJobs WHERE job_id=@j", {"j": job_id}, {"j": STR})
        return dict(zip(JOB_COLS, rows[0])) if rows else None

    def _consent(self, txn, member_id: str, consent_id: str) -> Optional[Dict[str, Any]]:
        rows = query(txn, f"SELECT {', '.join(CONSENT_COLS)} FROM TryOnConsents WHERE member_id=@m AND consent_id=@c",
                     {"m": member_id, "c": consent_id}, {"m": STR, "c": STR})
        return dict(zip(CONSENT_COLS, rows[0])) if rows else None

    def _set_job(self, txn, ctx: CommandContext, j: Dict[str, Any], **changes: Any) -> Dict[str, Any]:
        j.update(changes, version=j["version"] + 1)
        cols = ("member_id", "job_id", *changes.keys(), "version", "updated_at")
        txn.update("TryOnJobs", columns=cols, values=[[j["member_id"], j["job_id"], *changes.values(), j["version"], COMMIT_TIMESTAMP]])
        if "state" in changes or "saved" in changes:
            ctx.emit("tryon.job.state_changed", "1", "tryon_job", j["job_id"], j["version"],
                     {"member_id": j["member_id"], "job_id": j["job_id"], "state": j["state"], "saved": bool(j["saved"])}, "member_private")
        return j

    def _tombstone(self, txn, ctx: CommandContext, m: Dict[str, Any], reason: str, now) -> Tuple[str, str, str]:
        txn.update("MediaObjects", columns=("member_id", "media_id", "state", "saved", "deleted_at", "version"),
                   values=[(m["member_id"], m["media_id"], "deleted", False, now, m["version"] + 1)])
        ctx.emit("media.object.deleted", "1", "media_object", m["media_id"], m["version"] + 1,
                 {"member_id": m["member_id"], "media_id": m["media_id"], "reason": reason}, "member_private")
        return (m["member_id"], m["media_id"], m["storage_ref"])

    def _job_media(self, txn, member_id: str, job_id: str) -> List[Dict[str, Any]]:
        return [dict(zip(MEDIA_COLS, r)) for r in query(
            txn, f"SELECT {', '.join(MEDIA_COLS)} FROM MediaObjects WHERE member_id=@m AND job_id=@j AND deleted_at IS NULL",
            {"m": member_id, "j": job_id}, {"m": STR, "j": STR})]

    def _purge(self, refs: Purge) -> int:
        """Delete blobs after the tombstones committed; record purged_at. Re-runnable."""
        n = 0
        for member_id, media_id, ref in refs:
            self.store.delete(ref)

            def tx(txn, member_id=member_id, media_id=media_id):
                txn.execute_update("UPDATE MediaObjects SET purged_at=CURRENT_TIMESTAMP() WHERE member_id=@m AND media_id=@i AND purged_at IS NULL",
                                   params={"m": member_id, "i": media_id}, param_types={"m": STR, "i": STR})

            run_txn(self.db, tx)
            n += 1
        return n

    @staticmethod
    def _media_dto(m: Mapping[str, Any]) -> Dict[str, Any]:
        return {"media_id": m["media_id"], "kind": m["kind"], "state": m["state"], "content_type": m["content_type"], "bytes": m["bytes"],
                "rejection_code": m["rejection_code"], "saved": bool(m["saved"]), "expires_at": iso(m["expires_at"]),
                "deleted_at": iso(m["deleted_at"])}

    def _job_dto(self, j: Mapping[str, Any]) -> Dict[str, Any]:
        provider = self.providers.get(j["provider_id"])
        simulated = bool(provider and provider.simulated)
        return {
            "job_id": j["job_id"], "mode": j["mode"], "state": j["state"], "consent_id": j["consent_id"], "item_id": j["item_id"],
            "product_id": j["product_id"], "provider_id": j["provider_id"], "fidelity_label": j["fidelity_label"],
            "label_text": LABEL_TEXT + (" Simulated provider." if simulated else ""), "saved": bool(j["saved"]),
            "expires_at": iso(j["expires_at"]), "error_code": j["error_code"], "provider_deletion": j["provider_deletion"],
            "result_available": j["state"] == "succeeded" and j["output_media_ref"] is not None,
            "retention": self._retention(provider), "version": str(j["version"]),
        }

    @staticmethod
    def _retention(provider: Optional[TryOnProvider]) -> Dict[str, Any]:
        return {"app_inputs": "deleted when processing ends, at most 24 hours", "app_unsaved_results": "24 hours",
                "app_saved_results": "until you delete them",
                "provider": provider.terms.retention_disclosure if provider else "No provider is configured."}

    # --------------------------------------------------------------- capabilities

    def capabilities(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:read")
        p = self.providers.active()
        return {
            "photo_preview": {"available": p is not None, "provider_id": p.terms.provider_id if p else None,
                              "terms_version": p.terms.terms_version if p else None, "region": p.terms.region if p else None,
                              "simulated": bool(p and p.simulated), "label": LABEL_TEXT, "retention": self._retention(p),
                              "reason": None if p else "No approved photo try-on provider is configured."},
            "live_overlay": {"server": "on_device_only", "reason": "Camera frames and pose landmarks never leave your device."},
            "calibrated_fit": {"available": False, "reason": "No validated measurement and material pipeline exists; generated images are never fit."},
        }

    # ------------------------------------------------------------------ uploads

    def create_upload(self, principal: Principal, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:write")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("kind", "content_type", "bytes"), where="upload")
        if body.get("kind") != "tryon_input":
            raise ValidationFailed("kind must be tryon_input", extra={"field": "kind"})
        ctype = body.get("content_type")
        if ctype not in ALLOWED_TYPES:
            raise ValidationFailed(f"content_type must be one of {sorted(ALLOWED_TYPES)}", extra={"field": "content_type"})
        size = require_strict_int(body.get("bytes"), name="bytes", lo=1, hi=MAX_BYTES)
        m = principal.member_id

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, m):
                raise NotFound("member not found")
            now = server_now(txn)
            try:
                assert_processing_allowed(txn, m, "media.tryon", now)
            except ProcessingFrozen:
                raise DetailedInvalidTransition("uploads are paused while a privacy request is processed", code="processing_frozen")
            media_id = new_id()
            row = {"member_id": m, "media_id": media_id, "job_id": None, "kind": "tryon_input", "state": "awaiting_upload",
                   "storage_ref": storage_ref(m, media_id), "content_type": ctype, "content_hash": None, "bytes": size, "rejection_code": None,
                   "saved": False, "expires_at": now + RETENTION, "deleted_at": None, "purged_at": None, "version": 1}
            txn.insert("MediaObjects", columns=(*MEDIA_COLS, "created_at"), values=[[*(row[c] for c in MEDIA_COLS), COMMIT_TIMESTAMP]])
            return {**self._media_dto(row), "upload_window_until": iso(now + UPLOAD_URL_TTL)}

        out, _ = idempotent_command(self.db, principal, "media.upload.create", idempotency_key, dict(body), tx)
        # The signed target is minted per response (never stored in the idempotency record).
        target = self.store.upload_target(storage_ref(m, out["media_id"]), content_type=ctype, max_bytes=size,
                                          expires_at=parse_iso(out["upload_window_until"], name="upload_window_until"))
        target = {**target, "expires_at": iso(target["expires_at"])}
        return {**out, "upload": target}

    def complete_upload(self, principal: Principal, media_id: Any) -> Dict[str, Any]:
        """Verify the uploaded bytes (size, type by magic bytes, hash) outside any
        transaction, then record verified/rejected."""
        require_scope(principal, "wardrobe:write")
        media_id = require_uuid(media_id, name="media_id")
        m = principal.member_id
        row = run_read(self.db, lambda s: self._media(s, m, media_id))
        if row is None or row["deleted_at"] is not None:
            raise NotFound("upload not found")
        if row["state"] != "awaiting_upload":
            return self._media_dto(row)
        st = self.store.stat(row["storage_ref"])
        code = None
        if st is None:
            raise DetailedInvalidTransition("nothing was uploaded yet", code="upload_missing")
        size, digest = st
        if size > row["bytes"] or size > MAX_BYTES:
            code = "too_large"
        elif not sniff(self.store.read(row["storage_ref"])[:16], row["content_type"]):
            code = "unsupported_content"

        def tx(txn, ctx: CommandContext):
            cur = self._media(txn, m, media_id)
            if cur is None or cur["state"] != "awaiting_upload" or cur["deleted_at"] is not None:
                return cur, None
            now = server_now(txn)
            if code:
                purge = self._tombstone(txn, ctx, cur, "rejected", now)
                txn.update("MediaObjects", columns=("member_id", "media_id", "state", "rejection_code"), values=[(m, media_id, "rejected", code)])
                cur.update(state="rejected", rejection_code=code, deleted_at=now)
                return cur, purge
            txn.update("MediaObjects", columns=("member_id", "media_id", "state", "content_hash", "bytes", "version"),
                       values=[(m, media_id, "verified", digest, size, cur["version"] + 1)])
            cur.update(state="verified", content_hash=digest, bytes=size)
            return cur, None

        cur, purge = command(self.db, principal, tx)
        if purge:
            self._purge([purge])
        return self._media_dto(cur)

    def get_media_job(self, principal: Principal, media_id: Any) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:read")
        media_id = require_uuid(media_id, name="media_id")
        row = run_read(self.db, lambda s: self._media(s, principal.member_id, media_id))
        if row is None:
            raise NotFound("media job not found")
        return self._media_dto(row)

    # ------------------------------------------------------------------ try-on

    def create_job(self, principal: Principal, body: Any, idempotency_key: Optional[str]) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:write")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("mode", "input_media_id", "item_id", "product_id", "consent"), where="try-on job")
        mode = body.get("mode")
        if mode not in MODES:
            raise ValidationFailed(f"mode must be one of {MODES}", extra={"field": "mode"})
        if mode == "calibrated_fit":
            raise DetailedInvalidTransition("calibrated fit is not available: no validated measurement pipeline exists",
                                            code="capability_unavailable", extra={"mode": mode})
        if mode == "live_overlay":
            raise DetailedInvalidTransition("live overlay runs on your device; camera frames are never uploaded", code="on_device_only")
        provider = self.providers.active()
        if provider is None:
            raise DetailedInvalidTransition("photo try-on is not configured: no approved provider", code="photo_preview_not_configured",
                                            extra={"retention": self._retention(None)})
        consent = body.get("consent")
        disclosure = {"provider_id": provider.terms.provider_id, "terms_version": provider.terms.terms_version,
                      "region": provider.terms.region, "retention": provider.terms.retention_disclosure}
        if not isinstance(consent, Mapping) or consent.get("accepted") is not True:
            raise ValidationFailed("explicit consent to send this photo to the provider is required",
                                   extra={"field": "consent", "code": "consent_required", "provider": disclosure})
        reject_unknown_keys(consent, ("accepted", "provider_id", "terms_version"), where="consent")
        if consent.get("provider_id") != provider.terms.provider_id or consent.get("terms_version") != provider.terms.terms_version:
            raise ValidationFailed("the provider terms changed; review them again", extra={"field": "consent", "code": "consent_outdated",
                                                                                         "provider": disclosure})
        input_id = require_uuid(body.get("input_media_id"), name="input_media_id")
        item_id = require_uuid(body["item_id"], name="item_id") if body.get("item_id") is not None else None
        product_id = require_uuid(body["product_id"], name="product_id") if body.get("product_id") is not None else None
        if (item_id is None) == (product_id is None):
            raise ValidationFailed("choose exactly one of item_id or product_id", extra={"field": "item_id"})
        m = principal.member_id

        def tx(txn, ctx: CommandContext):
            if not member_active(txn, m):
                raise NotFound("member not found")
            now = server_now(txn)
            try:
                assert_processing_allowed(txn, m, "media.tryon", now)
            except ProcessingFrozen:
                raise DetailedInvalidTransition("try-on is paused while a privacy request is processed", code="processing_frozen")
            media = self._media(txn, m, input_id)
            if media is None or media["kind"] != "tryon_input" or media["deleted_at"] is not None:
                raise NotFound("photo not found")
            if media["state"] != "verified" or media["job_id"] is not None or media["expires_at"] <= now:
                raise DetailedInvalidTransition("upload a new photo for this try-on", code="input_not_usable")
            if item_id and not query(txn, "SELECT 1 FROM WardrobeItems WHERE member_id=@m AND item_id=@i AND collection != 'archive'",
                                     {"m": m, "i": item_id}, {"m": STR, "i": STR}):
                raise NotFound("item not found")
            if product_id and not self.catalog_check(txn, product_id):
                raise NotFound("product not found")
            day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today = query(txn, "SELECT COUNT(*) FROM TryOnJobs WHERE member_id=@m AND created_at >= @d", {"m": m, "d": day}, {"m": STR, "d": TS})[0][0]
            if today >= self.daily_job_limit:
                raise RateLimited(f"you can create {self.daily_job_limit} photo previews per day", extra={"limit": "daily_tryon_jobs"})
            existing = query(txn, "SELECT consent_id FROM TryOnConsents WHERE member_id=@m AND mode='photo_preview' AND provider_id=@p "
                                  "AND terms_version=@t AND revoked_at IS NULL LIMIT 1",
                             {"m": m, "p": provider.terms.provider_id, "t": provider.terms.terms_version}, {"m": STR, "p": STR, "t": STR})
            if existing:
                consent_id = existing[0][0]
            else:
                consent_id = new_id()
                txn.insert("TryOnConsents", columns=(*CONSENT_COLS, "created_at"),
                           values=[(m, consent_id, "photo_preview", provider.terms.provider_id, ["photo_tryon_generation"], now, None,
                                    provider.terms.terms_version, COMMIT_TIMESTAMP)])
                ctx.emit("tryon.consent.granted", "1", "tryon_consent", consent_id, 1,
                         {"member_id": m, "consent_id": consent_id, "mode": "photo_preview", "provider_id": provider.terms.provider_id,
                          "terms_version": provider.terms.terms_version}, "member_private")
            job_id = new_id()
            label = GENERATED_LABEL + ("_simulated" if provider.simulated else "")
            j = {"member_id": m, "job_id": job_id, "mode": "photo_preview", "consent_id": consent_id, "item_id": item_id, "product_id": product_id,
                 "provider_id": provider.terms.provider_id, "provider_job_ref": None, "state": "queued", "fidelity_label": label,
                 "input_media_ref": input_id, "output_media_ref": None, "saved": False, "expires_at": now + RETENTION, "error_code": None,
                 "provider_deletion": None, "version": 1}
            txn.insert("TryOnJobs", columns=(*JOB_COLS, "created_at", "updated_at"),
                       values=[[*(j[c] for c in JOB_COLS), COMMIT_TIMESTAMP, COMMIT_TIMESTAMP]])
            txn.update("MediaObjects", columns=("member_id", "media_id", "job_id", "version"), values=[(m, input_id, job_id, media["version"] + 1)])
            ctx.emit("tryon.job.created", "1", "tryon_job", job_id, 1,
                     {"member_id": m, "job_id": job_id, "mode": "photo_preview", "consent_id": consent_id}, "member_private")
            return self._job_dto(j)

        out, _ = idempotent_command(self.db, principal, "tryon.job.create", idempotency_key, dict(body), tx)
        return out

    def get_job(self, principal: Principal, job_id: Any) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:read")
        job_id = require_uuid(job_id, name="job_id")
        j = run_read(self.db, lambda s: self._job(s, principal.member_id, job_id))
        if j is None:
            raise NotFound("job not found")
        return self._job_dto(j)

    def result(self, principal: Principal, job_id: Any) -> Tuple[str, bytes]:
        """Protected retrieval of the generated preview (no bucket URL leaves the server)."""
        require_scope(principal, "wardrobe:read")
        job_id = require_uuid(job_id, name="job_id")

        def read(s):
            j = self._job(s, principal.member_id, job_id)
            if j is None or j["state"] != "succeeded" or not j["output_media_ref"]:
                raise NotFound("result not found")
            return self._media(s, principal.member_id, j["output_media_ref"])

        media = run_read(self.db, read)
        if media is None or media["deleted_at"] is not None:
            raise NotFound("result not found")
        return media["content_type"] or "image/png", self.store.read(media["storage_ref"])

    def save_job(self, principal: Principal, job_id: Any) -> Dict[str, Any]:
        """Saving is the member's explicit choice; until then the result expires."""
        require_scope(principal, "wardrobe:write")
        job_id = require_uuid(job_id, name="job_id")
        m = principal.member_id

        def tx(txn, ctx: CommandContext):
            j = self._job(txn, m, job_id)
            if j is None:
                raise NotFound("job not found")
            if j["saved"]:
                return self._job_dto(j)
            if j["state"] != "succeeded" or not j["output_media_ref"] or j["expires_at"] <= server_now(txn):
                raise DetailedInvalidTransition("only a finished, unexpired preview can be saved", code="not_saveable")
            out = self._media(txn, m, j["output_media_ref"])
            txn.update("MediaObjects", columns=("member_id", "media_id", "saved", "expires_at", "version"),
                       values=[(m, out["media_id"], True, None, out["version"] + 1)])
            return self._job_dto(self._set_job(txn, ctx, j, saved=True, expires_at=None))

        return command(self.db, principal, tx)

    def delete_job(self, principal: Principal, job_id: Any) -> Dict[str, Any]:
        """Cancel if possible and delete every app-owned artifact (manifest)."""
        require_scope(principal, "wardrobe:write")
        job_id = require_uuid(job_id, name="job_id")
        m = principal.member_id

        def tx(txn, ctx: CommandContext):
            j = self._job(txn, m, job_id)
            if j is None:
                raise NotFound("job not found")
            if j["state"] == "deleted":
                return j, []
            now = server_now(txn)
            refs = [self._tombstone(txn, ctx, med, "member_deleted", now) for med in self._job_media(txn, m, job_id)]
            provider = self.providers.get(j["provider_id"])
            if not j["provider_job_ref"]:
                pdel = "not_sent"
            elif provider and provider.terms.supports_deletion:
                pdel = "requested"
            else:
                pdel = "unsupported"
            return self._set_job(txn, ctx, j, state="deleted", saved=False, expires_at=None, provider_deletion=pdel), refs

        j, refs = command(self.db, principal, tx)
        purged = self._purge(refs)
        if j["provider_deletion"] == "requested":
            self._provider_delete(j)
            j = run_read(self.db, lambda s: self._job(s, m, job_id))
        return {"job_id": job_id, "state": "deleted", "media_deleted": sorted(r[1] for r in refs), "blobs_purged": purged,
                "provider_deletion": j["provider_deletion"], "provider_retention": self._retention(self.providers.get(j["provider_id"]))["provider"]}

    def _provider_delete(self, j: Mapping[str, Any]) -> None:
        provider = self.providers.get(j["provider_id"])
        try:
            ok = bool(provider and provider.delete(j["provider_job_ref"]))
        except Exception:  # noqa: BLE001
            ok = False

        def tx(txn, ctx: CommandContext):
            cur = self._job(txn, j["member_id"], j["job_id"])
            if cur and cur["provider_deletion"] == "requested":
                self._set_job(txn, ctx, cur, provider_deletion="confirmed" if ok else "failed")

        command(self.db, service_principal("tryon-worker"), tx)

    def revoke_consent(self, principal: Principal, consent_id: Any) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:write")
        consent_id = require_uuid(consent_id, name="consent_id")
        m = principal.member_id

        def tx(txn, ctx: CommandContext):
            c = self._consent(txn, m, consent_id)
            if c is None:
                raise NotFound("consent not found")
            if c["revoked_at"] is not None:
                return {"consent_id": consent_id, "revoked_at": iso(c["revoked_at"]), "jobs_cancelled": 0}, []
            now = server_now(txn)
            txn.update("TryOnConsents", columns=("member_id", "consent_id", "revoked_at"), values=[(m, consent_id, now)])
            ctx.emit("tryon.consent.revoked", "1", "tryon_consent", consent_id, 2, {"member_id": m, "consent_id": consent_id}, "member_private")
            refs: Purge = []
            cancelled = 0
            for row in query(txn, f"SELECT {', '.join(JOB_COLS)} FROM TryOnJobs WHERE member_id=@m AND consent_id=@c AND state='queued'",
                             {"m": m, "c": consent_id}, {"m": STR, "c": STR}):
                j = dict(zip(JOB_COLS, row))
                refs += [self._tombstone(txn, ctx, med, "consent_revoked", now) for med in self._job_media(txn, m, j["job_id"])]
                self._set_job(txn, ctx, j, state="cancelled", error_code="consent_revoked", provider_deletion="not_sent")
                cancelled += 1
            return {"consent_id": consent_id, "revoked_at": iso(now), "jobs_cancelled": cancelled}, refs

        out, refs = command(self.db, principal, tx)
        self._purge(refs)
        return out

    def list_consents(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "wardrobe:read")
        rows = run_read(self.db, lambda s: query(s, f"SELECT {', '.join(CONSENT_COLS)} FROM TryOnConsents WHERE member_id=@m ORDER BY granted_at DESC",
                                                 {"m": principal.member_id}, {"m": STR}))
        return {"items": [{"consent_id": r[1], "mode": r[2], "provider_id": r[3], "purposes": list(r[4]), "granted_at": iso(r[5]),
                           "revoked_at": iso(r[6]), "terms_version": r[7]} for r in rows], "next_cursor": None}

    # ------------------------------------------------------------------ workers

    def dispatch_queued(self, *, limit: int = 20) -> Dict[str, int]:
        """Send queued jobs to the provider. Consent, freeze and provider approval are
        re-checked in the claiming transaction, immediately before any upload."""
        worker = service_principal("tryon-worker")
        queued = run_read(self.db, lambda s: query(
            s, "SELECT member_id, job_id FROM TryOnJobs@{FORCE_INDEX=TryOnJobsByStateExpiry} WHERE state='queued' ORDER BY expires_at LIMIT @l",
            {"l": limit}, {"l": INT}))
        counts = {"submitted": 0, "cancelled": 0, "failed": 0, "skipped": 0}
        for member_id, job_id in queued:
            def claim(txn, ctx: CommandContext, member_id=member_id, job_id=job_id):
                j = self._job(txn, member_id, job_id)
                if j is None or j["state"] != "queued":
                    return "skipped", None, []
                now = server_now(txn)
                c = self._consent(txn, member_id, j["consent_id"])
                reason = None
                if c is None or c["revoked_at"] is not None:
                    reason = "consent_revoked"
                else:
                    try:
                        assert_processing_allowed(txn, member_id, "media.tryon", now)
                    except ProcessingFrozen:
                        reason = "processing_frozen"
                if reason:
                    refs = [self._tombstone(txn, ctx, med, "consent_revoked", now) for med in self._job_media(txn, member_id, job_id)]
                    self._set_job(txn, ctx, j, state="cancelled", error_code=reason, provider_deletion="not_sent")
                    return "cancelled", None, refs
                provider = self.providers.get(j["provider_id"])
                media = self._media(txn, member_id, j["input_media_ref"])
                if provider is None or not provider.approved or c["terms_version"] != provider.terms.terms_version:
                    self._set_job(txn, ctx, j, state="failed", error_code="provider_unavailable")
                    return "failed", None, []
                if media is None or media["deleted_at"] is not None or media["expires_at"] <= now:
                    self._set_job(txn, ctx, j, state="failed", error_code="input_expired")
                    return "failed", None, []
                self._set_job(txn, ctx, j, state="processing")
                return "submit", (j, media["storage_ref"]), []

            outcome, work, refs = command(self.db, worker, claim)
            self._purge(refs)
            if outcome != "submit":
                counts[outcome] += 1
                continue
            j, ref = work
            provider = self.providers.get(j["provider_id"])
            product_ref = f"item:{j['item_id']}" if j["item_id"] else f"product:{j['product_id']}"
            try:
                pref = provider.submit(j["job_id"], self.store.read(ref), product_ref)
                err = None
            except Exception:  # noqa: BLE001 - a provider failure is an outcome
                pref, err = None, "provider_error"

            def record(txn, ctx: CommandContext, j=j, pref=pref, err=err):
                cur = self._job(txn, j["member_id"], j["job_id"])
                if cur is None or cur["state"] != "processing":
                    return "orphan" if pref else "skipped"
                if err:
                    self._set_job(txn, ctx, cur, state="failed", error_code=err)
                    return "failed"
                self._set_job(txn, ctx, cur, provider_job_ref=pref)
                return "submitted"

            result = command(self.db, worker, record)
            if result == "orphan":  # deleted while we were uploading: ask the provider to delete it too
                self._provider_delete({**j, "provider_job_ref": pref, "provider_deletion": "requested"})
                result = "skipped"
            counts[result] += 1
        return counts

    def collect_processing(self, *, limit: int = 20) -> Dict[str, int]:
        worker = service_principal("tryon-worker")
        rows = run_read(self.db, lambda s: query(
            s, "SELECT member_id, job_id, provider_id, provider_job_ref FROM TryOnJobs@{FORCE_INDEX=TryOnJobsByStateExpiry} "
               "WHERE state='processing' AND provider_job_ref IS NOT NULL ORDER BY expires_at LIMIT @l", {"l": limit}, {"l": INT}))
        counts = {"succeeded": 0, "failed": 0, "pending": 0, "skipped": 0}
        for member_id, job_id, provider_id, pref in rows:
            provider = self.providers.get(provider_id)
            try:
                state, data, code = provider.poll(pref) if provider else ("failed", None, "provider_unavailable")
            except Exception:  # noqa: BLE001
                state, data, code = "failed", None, "provider_error"
            if state not in ("succeeded", "failed"):
                counts["pending"] += 1
                continue
            out_id = new_id() if state == "succeeded" else None
            out_ref = storage_ref(member_id, out_id) if out_id else None
            if out_ref:
                self.store.write(out_ref, data, "image/png")

            def record(txn, ctx: CommandContext, member_id=member_id, job_id=job_id, state=state, code=code, out_id=out_id, out_ref=out_ref,
                       size=len(data) if data else None):
                j = self._job(txn, member_id, job_id)
                if j is None or j["state"] != "processing":
                    return "skipped", []
                now = server_now(txn)
                refs = []
                inp = self._media(txn, member_id, j["input_media_ref"])
                if inp and inp["deleted_at"] is None:  # earlier deletion after processing
                    refs.append(self._tombstone(txn, ctx, inp, "processed", now))
                if state == "succeeded":
                    txn.insert("MediaObjects", columns=(*MEDIA_COLS, "created_at"), values=[[
                        member_id, out_id, job_id, "tryon_output", "verified", out_ref, "image/png", None, size, None, False, j["expires_at"],
                        None, None, 1, COMMIT_TIMESTAMP]])
                    self._set_job(txn, ctx, j, state="succeeded", output_media_ref=out_id)
                else:
                    self._set_job(txn, ctx, j, state="failed", error_code=(code or "provider_failed")[:64])
                return state, refs

            result, refs = command(self.db, worker, record)
            self._purge(refs)
            if result == "skipped" and out_ref:
                self.store.delete(out_ref)  # the job was deleted meanwhile: drop the orphan output
            counts[result] += 1
        return counts

    def expire_due(self, *, limit: int = 200) -> Dict[str, int]:
        """Retention sweeper: unsaved media and jobs past their server-time expiry."""
        worker = service_principal("tryon-retention")

        def tx(txn, ctx: CommandContext):
            now = server_now(txn)
            media = [dict(zip(MEDIA_COLS, r)) for r in query(
                txn, f"SELECT {', '.join(MEDIA_COLS)} FROM MediaObjects@{{FORCE_INDEX=MediaObjectsByExpiry}} "
                     "WHERE deleted_at IS NULL AND expires_at <= @n AND saved = FALSE LIMIT @l", {"n": now, "l": limit}, {"n": TS, "l": INT})]
            refs = [self._tombstone(txn, ctx, med, "expired", now) for med in media]
            jobs = [dict(zip(JOB_COLS, r)) for r in query(
                txn, f"SELECT {', '.join(JOB_COLS)} FROM TryOnJobs WHERE saved = FALSE AND expires_at <= @n "
                     "AND state IN ('queued', 'processing', 'succeeded', 'failed', 'awaiting_upload') LIMIT @l", {"n": now, "l": limit}, {"n": TS, "l": INT})]
            for j in jobs:
                pdel = j["provider_deletion"] or ("requested" if j["provider_job_ref"] else "not_sent")
                self._set_job(txn, ctx, j, state="expired", provider_deletion=pdel)
            return refs, [j for j in jobs if j["provider_deletion"] == "requested"]

        refs, provider_jobs = command(self.db, worker, tx)
        for j in provider_jobs:
            self._provider_delete(j)
        return {"media_expired": len(refs), "blobs_purged": self._purge(refs)}

    def purge_pending(self, *, limit: int = 200) -> int:
        """Retry blob deletion for tombstoned objects whose purge did not complete."""
        rows = run_read(self.db, lambda s: query(
            s, "SELECT member_id, media_id, storage_ref FROM MediaObjects@{FORCE_INDEX=MediaObjectsByPurge} "
               "WHERE purged_at IS NULL AND deleted_at IS NOT NULL LIMIT @l", {"l": limit}, {"l": INT}))
        return self._purge([tuple(r) for r in rows])

    def jobs_for(self, member_id: str) -> Sequence[Dict[str, Any]]:
        return run_read(self.db, lambda s: [dict(zip(JOB_COLS, r)) for r in query(
            s, f"SELECT {', '.join(JOB_COLS)} FROM TryOnJobs WHERE member_id=@m", {"m": member_id}, {"m": STR})])
