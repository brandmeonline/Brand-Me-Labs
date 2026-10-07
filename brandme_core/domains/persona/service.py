"""
Persona (Looking Glass) application service backed by Spanner.

Every command runs in one Spanner read/write transaction that commits the
domain rows and their outbox events together (ch.03 §5). Transaction callbacks
perform no external I/O, so Spanner's automatic ABORTED retry cannot duplicate
side effects.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from google.cloud import spanner

from .kernel import (
    BOOL,
    INT,
    STR,
    Clock,
    InvalidTransition,
    NotFound,
    OutboxEvent,
    Principal,
    SystemClock,
    ValidationFailed,
    VersionConflict,
    canonical_digest,
    idempotency_lookup,
    idempotency_store,
    iso,
    json_value,
    new_id,
    parse_revision,
    query,
    register_event,
    reject_unknown_keys,
    require_strict_int,
    write_outbox,
    run_read,
    run_txn,
    JsonObject,
)
from .model import (
    AXIS_KEYS,
    EVIDENCE_SOURCE_TYPES,
    INFERENCE_MODEL_VERSION,
    INFERENCE_PURPOSE,
    PERSONA_SCHEMA_VERSION,
    SRC_UNKNOWN,
    AxisState,
    ContextOverride,
    Evidence,
    adaptation_proposals,
    apply_inference,
    axis_labels,
    infer_axes,
    resolve_effective,
    source_fingerprint,
    validate_axis_key,
    validate_axis_value,
    validate_contributions,
)
from .recommender import Candidate, RecommendationRequest, WardrobeRef, recommend

register_event("persona.updated", ["member_id", "profile_version", "change_kind", "changed_axes"])
register_event("persona.evidence.suppressed", ["member_id", "profile_version", "evidence_id"])
register_event("persona.snapshot.saved", ["member_id", "snapshot_id", "profile_version", "first_snapshot"])
register_event("persona.guest.migrated", ["member_id", "guest_namespace_id", "profile_version"])

PATCH_KEYS = ("changes", "learning_enabled", "client_revision", "axis_settings", "constraints")
CHANGE_KEYS = ("axis", "value", "locked")
AXIS_SETTING_KEYS = ("hidden", "inference_allowed", "adapt_enabled")
CONSTRAINT_KEYS = (
    "budget_ceiling_minor",
    "budget_currency",
    "excluded_brands",
    "excluded_materials",
    "excluded_categories",
    "prefer_owned",
    "social_signals_enabled",
    "goals",
)
RESET_SCOPES = ("inference", "declarations", "all")
FEEDBACK_SIGNALS = {"interested": 1, "not_me": -1}
MAX_EVIDENCE_PER_RECOMPUTE = 2000

CandidateSource = Callable[[Principal], Sequence[Candidate]]
WardrobeSource = Callable[[Any, str], Sequence[WardrobeRef]]  # (txn_or_snapshot, member_id)
RevokedConsentSource = Callable[[Any, str], Set[str]]


def _no_wardrobe(_txn, _member_id) -> Sequence[WardrobeRef]:
    return ()


def _no_revocations(_txn, _member_id) -> Set[str]:
    return set()


class _Profile:
    """In-transaction view of a member's persona aggregate."""

    def __init__(self, member_id: str):
        self.member_id = member_id
        self.exists = False
        self.version = 0
        self.learning_enabled = True
        self.social_signals_enabled = True
        self.prefer_owned = False
        self.budget_ceiling_minor: Optional[int] = None
        self.budget_currency: Optional[str] = None
        self.excluded_brands: List[str] = []
        self.excluded_materials: List[str] = []
        self.excluded_categories: List[str] = []
        self.goals: List[str] = []
        self.onboarding_intent: Optional[str] = None
        self.inferred_at: Optional[datetime] = None
        self.updated_at: Optional[datetime] = None
        self.axes: Dict[str, AxisState] = {k: AxisState(key=k) for k in AXIS_KEYS}
        self.overrides: List[ContextOverride] = []


class PersonaService:
    def __init__(
        self,
        database,
        *,
        clock: Clock = None,
        candidate_source: Optional[CandidateSource] = None,
        wardrobe_source: WardrobeSource = _no_wardrobe,
        revoked_consents: RevokedConsentSource = _no_revocations,
    ):
        self.db = database
        self.clock = clock or SystemClock()
        self.candidate_source = candidate_source or (lambda _p: ())
        self.wardrobe_source = wardrobe_source
        self.revoked_consents = revoked_consents

    # ------------------------------------------------------------------ load

    def _tombstoned(self, txn, member_id: str) -> bool:
        return bool(query(txn, "SELECT 1 FROM PersonaTombstones WHERE member_id=@m", {"m": member_id}, {"m": STR}))

    def _load(self, txn, member_id: str) -> _Profile:
        p = _Profile(member_id)
        rows = query(
            txn,
            "SELECT version, learning_enabled, social_signals_enabled, prefer_owned, budget_ceiling_minor, "
            "budget_currency, excluded_brands, excluded_materials, excluded_categories, goals, onboarding_intent, "
            "inferred_at, updated_at FROM PersonaProfiles WHERE member_id=@m",
            {"m": member_id},
            {"m": STR},
        )
        if not rows:
            return p
        r = rows[0]
        p.exists = True
        (
            p.version,
            p.learning_enabled,
            p.social_signals_enabled,
            p.prefer_owned,
            p.budget_ceiling_minor,
            p.budget_currency,
            brands,
            mats,
            cats,
            goals,
            p.onboarding_intent,
            p.inferred_at,
            p.updated_at,
        ) = r
        p.excluded_brands, p.excluded_materials, p.excluded_categories, p.goals = (
            list(brands or []),
            list(mats or []),
            list(cats or []),
            list(goals or []),
        )
        for row in query(
            txn,
            "SELECT axis_key, declared_value, locked, adapt_enabled, adapt_first_accepted, adapt_last_applied_at, "
            "inference_allowed, hidden, declared_revision, inferred_value, inferred_confidence, inferred_evidence_count "
            "FROM PersonaAxes WHERE member_id=@m",
            {"m": member_id},
            {"m": STR},
        ):
            k = row[0]
            if k not in p.axes:
                continue
            p.axes[k] = AxisState(
                key=k,
                declared=row[1],
                locked=row[2],
                adapt_enabled=row[3],
                adapt_first_accepted=row[4],
                adapt_last_applied_at=row[5],
                inference_allowed=row[6],
                hidden=row[7],
                declared_revision=row[8],
                inferred=row[9],
                inferred_confidence=row[10],
                inferred_evidence_count=row[11],
            )
        for row in query(
            txn,
            "SELECT override_id, label, axes, starts_at, ends_at, enabled FROM PersonaContextOverrides WHERE member_id=@m",
            {"m": member_id},
            {"m": STR},
        ):
            p.overrides.append(ContextOverride(row[0], row[1], json_value(row[2]), row[3], row[4], row[5]))
        return p

    def _load_visible(self, snap, member_id: str) -> _Profile:
        if self._tombstoned(snap, member_id):
            raise NotFound("profile not found")
        return self._load(snap, member_id)

    def _load_evidence(self, txn, member_id: str) -> List[Evidence]:
        out = []
        for r in query(
            txn,
            "SELECT evidence_id, source_type, source_ref, purpose, axis_contributions, weight, observed_at, expires_at, "
            "consent_id, suppression_state FROM PersonaEvidence WHERE member_id=@m "
            "ORDER BY observed_at DESC, evidence_id LIMIT @lim",
            {"m": member_id, "lim": MAX_EVIDENCE_PER_RECOMPUTE},
            {"m": STR, "lim": INT},
        ):
            out.append(
                Evidence(
                    evidence_id=r[0],
                    source_type=r[1],
                    source_ref=r[2],
                    purpose=r[3],
                    axis_contributions=json_value(r[4]) or {},
                    weight=r[5],
                    observed_at=r[6],
                    expires_at=r[7],
                    consent_id=r[8],
                    suppression_state=r[9],
                )
            )
        return out

    def _suppressed(self, txn, member_id: str) -> Set[str]:
        return {
            r[0]
            for r in query(
                txn, "SELECT source_fingerprint FROM PersonaSuppressions WHERE member_id=@m", {"m": member_id}, {"m": STR}
            )
        }

    def _recompute_inference(self, txn, p: _Profile, now: datetime, *, also_suppressed: Iterable[str] = ()) -> None:
        # Spanner reads do not observe this transaction's buffered mutations, so
        # callers pass fingerprints they are suppressing in the same transaction.
        inferred = infer_axes(
            self._load_evidence(txn, p.member_id),
            now=now,
            suppressed_fingerprints=self._suppressed(txn, p.member_id) | set(also_suppressed),
            revoked_consents=self.revoked_consents(txn, p.member_id),
        )
        p.axes = apply_inference(p.axes, inferred)
        p.inferred_at = now

    # ----------------------------------------------------------------- write

    def _write(self, txn, p: _Profile, now: datetime, *, axes_changed: Iterable[str] = AXIS_KEYS) -> None:
        cols = (
            "member_id",
            "schema_version",
            "version",
            "learning_enabled",
            "social_signals_enabled",
            "prefer_owned",
            "budget_ceiling_minor",
            "budget_currency",
            "excluded_brands",
            "excluded_materials",
            "excluded_categories",
            "goals",
            "onboarding_intent",
            "inference_model_version",
            "inferred_at",
            "updated_at",
        )
        vals = [
            p.member_id,
            PERSONA_SCHEMA_VERSION,
            p.version,
            p.learning_enabled,
            p.social_signals_enabled,
            p.prefer_owned,
            p.budget_ceiling_minor,
            p.budget_currency,
            p.excluded_brands,
            p.excluded_materials,
            p.excluded_categories,
            p.goals,
            p.onboarding_intent,
            INFERENCE_MODEL_VERSION,
            p.inferred_at,
            spanner.COMMIT_TIMESTAMP,
        ]
        if p.exists:
            txn.update("PersonaProfiles", columns=cols, values=[vals])
        else:
            txn.insert("PersonaProfiles", columns=cols + ("created_at",), values=[vals + [spanner.COMMIT_TIMESTAMP]])
        axis_cols = (
            "member_id",
            "axis_key",
            "declared_value",
            "locked",
            "adapt_enabled",
            "adapt_first_accepted",
            "adapt_last_applied_at",
            "inference_allowed",
            "hidden",
            "declared_revision",
            "inferred_value",
            "inferred_confidence",
            "inferred_evidence_count",
            "updated_at",
        )
        keys = AXIS_KEYS if not p.exists else tuple(k for k in AXIS_KEYS if k in set(axes_changed))
        rows = []
        for k in keys:
            a = p.axes[k]
            rows.append(
                (
                    p.member_id,
                    k,
                    a.declared,
                    a.locked,
                    a.adapt_enabled,
                    a.adapt_first_accepted,
                    a.adapt_last_applied_at,
                    a.inference_allowed,
                    a.hidden,
                    a.declared_revision,
                    a.inferred,
                    a.inferred_confidence,
                    a.inferred_evidence_count,
                    spanner.COMMIT_TIMESTAMP,
                )
            )
        if rows:
            txn.insert_or_update("PersonaAxes", columns=axis_cols, values=rows)

    def _event(self, p: _Profile, principal_ref: str, env: str, now: datetime, change_kind: str, changed: Iterable[str]) -> OutboxEvent:
        return OutboxEvent(
            event_type="persona.updated",
            aggregate_type="persona_profile",
            aggregate_id=p.member_id,
            aggregate_version=p.version,
            payload={
                "member_id": p.member_id,
                "profile_version": str(p.version),
                "change_kind": change_kind,
                "changed_axes": sorted(set(changed)),
            },
            actor_ref=principal_ref,
            environment=env,
            occurred_at=now,
        )

    # ------------------------------------------------------------------- DTO

    def _dto(self, p: _Profile, now: datetime) -> Dict[str, Any]:
        eff = resolve_effective(p.axes, p.overrides, p.learning_enabled, now)
        declared = {k: p.axes[k].declared for k in AXIS_KEYS}
        inferred = {k: (p.axes[k].inferred if p.axes[k].inference_allowed else None) for k in AXIS_KEYS}
        effective = {k: eff[k].value for k in AXIS_KEYS}
        axes_detail = []
        for k in AXIS_KEYS:
            a, e = p.axes[k], eff[k]
            axes_detail.append(
                {
                    "axis": k,
                    "declared": a.declared,
                    "inferred": inferred[k],
                    "inferred_confidence": a.inferred_confidence if inferred[k] is not None else None,
                    "inferred_evidence_count": a.inferred_evidence_count if inferred[k] is not None else 0,
                    "effective": e.value,
                    "effective_source": e.source,
                    "override_id": e.override_id,
                    "state": "unanswered" if e.source == SRC_UNKNOWN else "answered",
                    "display_position": 50 if e.value is None else e.value,
                    "locked": a.locked,
                    "adapt_enabled": a.adapt_enabled,
                    "inference_allowed": a.inference_allowed,
                    "hidden": a.hidden,
                    "summary": axis_labels(k, e.value),
                }
            )
        return {
            "profile": {
                "member_id": p.member_id,
                "version": str(p.version),
                "declared_axes": declared,
                "inferred_axes": inferred,
                "effective_axes": effective,
                "locked_axes": [k for k in AXIS_KEYS if p.axes[k].locked],
                "learning_enabled": p.learning_enabled,
                "updated_at": iso(p.updated_at or now),
            },
            "axes": axes_detail,
            "constraints": {
                "budget_ceiling_minor": None if p.budget_ceiling_minor is None else str(p.budget_ceiling_minor),
                "budget_currency": p.budget_currency,
                "excluded_brands": p.excluded_brands,
                "excluded_materials": p.excluded_materials,
                "excluded_categories": p.excluded_categories,
                "prefer_owned": p.prefer_owned,
                "social_signals_enabled": p.social_signals_enabled,
                "goals": p.goals,
            },
            "context_overrides": [
                {
                    "override_id": o.override_id,
                    "label": o.label,
                    "axes": dict(o.axes),
                    "starts_at": iso(o.starts_at),
                    "ends_at": iso(o.ends_at),
                    "enabled": o.enabled,
                    "active": o.active(now),
                }
                for o in sorted(p.overrides, key=lambda o: (o.starts_at, o.override_id))
            ],
            "adaptation_proposals": [
                {
                    "axis": a.axis,
                    "current": a.current,
                    "proposed": a.proposed,
                    "inferred": a.inferred,
                    "requires_confirmation": a.requires_confirmation,
                }
                for a in adaptation_proposals(p.axes, p.learning_enabled, now)
            ],
            "exists": p.exists,
        }

    # --------------------------------------------------------------- queries

    def get(self, principal: Principal) -> Dict[str, Any]:
        principal.require("profile:read")
        p = run_read(self.db, lambda snap: self._load_visible(snap, principal.member_id))
        return self._dto(p, self.clock.now())

    def list_evidence(self, principal: Principal) -> List[Dict[str, Any]]:
        principal.require("profile:read")

        def read(snap):
            out = []
            for r in query(
                snap,
                "SELECT evidence_id, source_type, source_ref, purpose, axis_contributions, weight, model_version, "
                "observed_at, expires_at, suppression_state, suppressed_at FROM PersonaEvidence "
                "WHERE member_id=@m ORDER BY observed_at DESC, evidence_id",
                {"m": principal.member_id},
                {"m": STR},
            ):
                out.append(
                    {
                        "evidence_id": r[0],
                        "source_type": r[1],
                        "source_ref": r[2],
                        "purpose": r[3],
                        "axis_contributions": json_value(r[4]) or {},
                        "weight": r[5],
                        "model_version": r[6],
                        "observed_at": iso(r[7]),
                        "expires_at": iso(r[8]),
                        "suppression_state": r[9],
                        "suppressed_at": iso(r[10]),
                    }
                )
            return out

        return run_read(self.db, read)

    # -------------------------------------------------------------- commands

    def _begin(self, txn, principal: Principal, if_match: Optional[str]) -> _Profile:
        if self._tombstoned(txn, principal.member_id):
            raise NotFound("profile not found")
        p = self._load(txn, principal.member_id)
        if if_match is not None:
            base = parse_revision(if_match)
            if base != p.version:
                raise VersionConflict(
                    "persona changed on another device",
                    extra={"current_version": str(p.version)},
                )
        return p

    def patch(self, principal: Principal, if_match: Optional[str], body: Mapping[str, Any]) -> Dict[str, Any]:
        principal.require("profile:write")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, PATCH_KEYS, where="persona patch")
        base = parse_revision(if_match)
        changes = body.get("changes")
        if not isinstance(changes, list) or len(changes) > 12:
            raise ValidationFailed("changes must be a list of at most 12 axis changes")
        cr = body.get("client_revision")
        if not isinstance(cr, str) or not (1 <= len(cr) <= 64):
            raise ValidationFailed("client_revision is required")
        seen: Set[str] = set()
        parsed: List[Tuple[str, Optional[int], bool]] = []
        for ch in changes:
            if not isinstance(ch, Mapping):
                raise ValidationFailed("each change must be an object")
            reject_unknown_keys(ch, CHANGE_KEYS, where="axis change")
            if set(ch) != set(CHANGE_KEYS):
                raise ValidationFailed("each change needs axis, value and locked")
            k = validate_axis_key(ch["axis"])
            if k in seen:
                raise ValidationFailed(f"duplicate axis {k} in one patch", extra={"field": "changes"})
            seen.add(k)
            v = validate_axis_value(ch["value"])
            if not isinstance(ch["locked"], bool):
                raise ValidationFailed("locked must be a boolean")
            if v is None and ch["locked"]:
                raise ValidationFailed(f"cannot lock unanswered axis {k}")
            parsed.append((k, v, ch["locked"]))
        settings = body.get("axis_settings") or {}
        if not isinstance(settings, Mapping):
            raise ValidationFailed("axis_settings must be an object")
        parsed_settings: Dict[str, Dict[str, bool]] = {}
        for k, s in settings.items():
            validate_axis_key(k)
            if not isinstance(s, Mapping):
                raise ValidationFailed("axis setting must be an object")
            reject_unknown_keys(s, AXIS_SETTING_KEYS, where="axis setting")
            for sk, sv in s.items():
                if not isinstance(sv, bool):
                    raise ValidationFailed(f"{sk} must be a boolean")
            parsed_settings[k] = dict(s)
        constraints = body.get("constraints") or {}
        if not isinstance(constraints, Mapping):
            raise ValidationFailed("constraints must be an object")
        reject_unknown_keys(constraints, CONSTRAINT_KEYS, where="constraints")
        learning = body.get("learning_enabled")
        if learning is not None and not isinstance(learning, bool):
            raise ValidationFailed("learning_enabled must be a boolean")
        touched = sorted(seen | set(parsed_settings))

        def txn_fn(txn):
            now = self.clock.now()
            if self._tombstoned(txn, principal.member_id):
                raise NotFound("profile not found")
            p = self._load(txn, principal.member_id)
            if base != p.version:
                conflicting = sorted(k for k in touched if p.axes[k].declared_revision > base)
                raise VersionConflict(
                    "persona changed on another device; reload and re-apply your edits",
                    extra={
                        "current_version": str(p.version),
                        "mergeable": not conflicting,
                        "conflicting_axes": conflicting,
                        "guidance": "reload" if conflicting else "reapply_with_current_version",
                    },
                )
            new_version = p.version + 1
            for k, v, locked in parsed:
                a = p.axes[k]
                p.axes[k] = replace(
                    a,
                    declared=v,
                    locked=locked,
                    adapt_enabled=False if locked else a.adapt_enabled,
                    declared_revision=new_version,
                )
            for k, s in parsed_settings.items():
                a = p.axes[k]
                if s.get("adapt_enabled") is True:
                    if a.locked or any(c[0] == k and c[2] for c in parsed):
                        raise ValidationFailed(f"unlock {k} before letting it adapt")
                    if a.declared is None and not any(c[0] == k and c[1] is not None for c in parsed):
                        raise ValidationFailed(f"{k} needs a declared value to adapt from")
                a = replace(a, **{sk: sv for sk, sv in s.items()})
                if "adapt_enabled" in s:
                    a = replace(a, declared_revision=new_version)
                p.axes[k] = a
            if learning is not None:
                p.learning_enabled = learning
            self._apply_constraints(p, constraints)
            # "Do not infer this" or toggling learning takes effect immediately.
            self._recompute_inference(txn, p, now)
            p.version = new_version
            self._write(txn, p, now)
            write_outbox(txn, [self._event(p, principal.actor_ref, principal.environment, now, "declared", touched)])
            p.exists = True
            p.updated_at = now
            return self._dto(p, now)

        out = run_txn(self.db, txn_fn)
        out["client_revision"] = cr
        return out

    @staticmethod
    def _str_list(v: Any, name: str, max_items: int = 50, max_len: int = 120) -> List[str]:
        if not isinstance(v, list) or len(v) > max_items:
            raise ValidationFailed(f"{name} must be a list of at most {max_items}")
        out = []
        for s in v:
            if not isinstance(s, str) or not (1 <= len(s.strip()) <= max_len):
                raise ValidationFailed(f"{name} entries must be non-empty strings")
            if s.strip() not in out:
                out.append(s.strip())
        return out

    def _apply_constraints(self, p: _Profile, c: Mapping[str, Any]) -> None:
        if "budget_ceiling_minor" in c or "budget_currency" in c:
            raw = c.get("budget_ceiling_minor", None if p.budget_ceiling_minor is None else str(p.budget_ceiling_minor))
            cur = c.get("budget_currency", p.budget_currency)
            if raw is None:
                p.budget_ceiling_minor, p.budget_currency = None, None
            else:
                if not isinstance(raw, str) or not raw.isdigit() or len(raw) > 15 or (len(raw) > 1 and raw[0] == "0"):
                    raise ValidationFailed("budget_ceiling_minor must be a decimal string of minor units")
                if not isinstance(cur, str) or len(cur) != 3 or not cur.isupper() or not cur.isalpha():
                    raise ValidationFailed("budget_currency must be an ISO 4217 code")
                p.budget_ceiling_minor, p.budget_currency = int(raw), cur
        for name in ("excluded_brands", "excluded_materials", "excluded_categories", "goals"):
            if name in c:
                setattr(p, name, self._str_list(c[name], name))
        for name in ("prefer_owned", "social_signals_enabled"):
            if name in c:
                if not isinstance(c[name], bool):
                    raise ValidationFailed(f"{name} must be a boolean")
                setattr(p, name, c[name])

    # ------------------------------------------------------------ evidence

    def ingest_evidence(
        self,
        *,
        member_id: str,
        source_type: str,
        source_ref: str,
        axis_contributions: Mapping[str, Any],
        weight: float = 1.0,
        purpose: str = INFERENCE_PURPOSE,
        observed_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        consent_id: Optional[str] = None,
        worker_ref: str = "worker:persona-inference",
        environment: str = "development",
    ) -> str:
        """Inference-worker entrypoint. Returns a disposition string; never writes
        declared values or locks."""
        if source_type not in EVIDENCE_SOURCE_TYPES:
            raise ValidationFailed(f"unsupported evidence source {source_type}")
        if not isinstance(source_ref, str) or not (1 <= len(source_ref) <= 256):
            raise ValidationFailed("source_ref required")
        contributions = validate_contributions(axis_contributions)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not (0 < weight <= 10):
            raise ValidationFailed("weight must be in (0, 10]")
        fp = source_fingerprint(source_type, source_ref)

        def txn_fn(txn):
            now = self.clock.now()
            if self._tombstoned(txn, member_id):
                return "tombstoned"
            p = self._load(txn, member_id)
            if not p.exists:
                return "no_profile"
            if purpose != INFERENCE_PURPOSE:
                return "purpose_not_permitted"
            if not p.learning_enabled:
                return "learning_disabled"
            if fp in self._suppressed(txn, member_id):
                return "suppressed"
            if query(
                txn,
                "SELECT 1 FROM PersonaEvidence@{FORCE_INDEX=PersonaEvidenceByFingerprint} "
                "WHERE member_id=@m AND source_fingerprint=@f",
                {"m": member_id, "f": fp},
                {"m": STR, "f": STR},
            ):
                return "duplicate"
            allowed = {k: v for k, v in contributions.items() if p.axes[k].inference_allowed}
            if not allowed:
                return "no_permitted_axes"
            eid = new_id()
            txn.insert(
                "PersonaEvidence",
                columns=(
                    "member_id",
                    "evidence_id",
                    "source_type",
                    "source_ref",
                    "source_fingerprint",
                    "purpose",
                    "consent_id",
                    "axis_contributions",
                    "weight",
                    "model_version",
                    "observed_at",
                    "expires_at",
                    "suppression_state",
                    "suppressed_at",
                    "created_at",
                ),
                values=[
                    (
                        member_id,
                        eid,
                        source_type,
                        source_ref,
                        fp,
                        purpose,
                        consent_id,
                        JsonObject(allowed),
                        float(weight),
                        INFERENCE_MODEL_VERSION,
                        observed_at or now,
                        expires_at,
                        "active",
                        None,
                        spanner.COMMIT_TIMESTAMP,
                    )
                ],
            )
            evidence = self._load_evidence(txn, member_id) + [
                Evidence(eid, source_type, source_ref, purpose, allowed, float(weight), observed_at or now, expires_at, consent_id)
            ]
            inferred = infer_axes(
                evidence,
                now=now,
                suppressed_fingerprints=self._suppressed(txn, member_id),
                revoked_consents=self.revoked_consents(txn, member_id),
            )
            p.axes = apply_inference(p.axes, inferred)
            p.inferred_at = now
            p.version += 1
            self._write(txn, p, now)
            write_outbox(txn, [self._event(p, worker_ref, environment, now, "inference", allowed.keys())])
            return "accepted"

        return run_txn(self.db, txn_fn)

    def suppress_evidence(self, principal: Principal, evidence_id: str) -> Dict[str, Any]:
        principal.require("profile:write")

        def txn_fn(txn):
            now = self.clock.now()
            p = self._begin(txn, principal, None)
            rows = query(
                txn,
                "SELECT source_fingerprint, suppression_state, axis_contributions FROM PersonaEvidence "
                "WHERE member_id=@m AND evidence_id=@e",
                {"m": principal.member_id, "e": evidence_id},
                {"m": STR, "e": STR},
            )
            if not rows:
                raise NotFound("evidence not found")
            fp, state, contrib = rows[0]
            changed = sorted((json_value(contrib) or {}).keys())
            if state == "active":
                txn.update(
                    "PersonaEvidence",
                    columns=("member_id", "evidence_id", "suppression_state", "suppressed_at", "axis_contributions"),
                    values=[(principal.member_id, evidence_id, "suppressed", now, JsonObject({}))],
                )
            txn.insert_or_update(
                "PersonaSuppressions",
                columns=("member_id", "source_fingerprint", "reason", "created_at"),
                values=[(principal.member_id, fp, "member_suppressed", spanner.COMMIT_TIMESTAMP)],
            )
            # Recompute from the remaining evidence (the suppressed row is now excluded).
            self._recompute_inference(txn, p, now, also_suppressed=[fp])
            p.version += 1
            self._write(txn, p, now)
            write_outbox(
                txn,
                [
                    OutboxEvent(
                        event_type="persona.evidence.suppressed",
                        aggregate_type="persona_profile",
                        aggregate_id=p.member_id,
                        aggregate_version=p.version,
                        payload={"member_id": p.member_id, "profile_version": str(p.version), "evidence_id": evidence_id},
                        actor_ref=principal.actor_ref,
                        environment=principal.environment,
                        occurred_at=now,
                    ),
                    self._event(p, principal.actor_ref, principal.environment, now, "evidence_suppressed", changed),
                ],
            )
            p.updated_at = now
            return self._dto(p, now)

        return run_txn(self.db, txn_fn)

    # --------------------------------------------------------------- reset

    def reset(self, principal: Principal, if_match: Optional[str], scope: str, confirm: bool) -> Dict[str, Any]:
        principal.require("profile:write")
        if scope not in RESET_SCOPES:
            raise ValidationFailed(f"scope must be one of {RESET_SCOPES}")
        if confirm is not True:
            raise ValidationFailed("reset requires explicit confirmation", extra={"field": "confirm"})
        parse_revision(if_match)

        def txn_fn(txn):
            now = self.clock.now()
            p = self._begin(txn, principal, if_match)
            if not p.exists:
                raise InvalidTransition("there is no saved profile to reset")
            if scope in ("inference", "all"):
                for r in query(
                    txn,
                    "SELECT evidence_id, source_fingerprint FROM PersonaEvidence WHERE member_id=@m AND suppression_state='active'",
                    {"m": p.member_id},
                    {"m": STR},
                ):
                    txn.update(
                        "PersonaEvidence",
                        columns=("member_id", "evidence_id", "suppression_state", "suppressed_at", "axis_contributions"),
                        values=[(p.member_id, r[0], "reset", now, JsonObject({}))],
                    )
                    txn.insert_or_update(
                        "PersonaSuppressions",
                        columns=("member_id", "source_fingerprint", "reason", "created_at"),
                        values=[(p.member_id, r[1], "member_reset", spanner.COMMIT_TIMESTAMP)],
                    )
                p.axes = {
                    k: replace(a, inferred=None, inferred_confidence=None, inferred_evidence_count=0) for k, a in p.axes.items()
                }
            new_version = p.version + 1
            if scope in ("declarations", "all"):
                p.axes = {
                    k: replace(
                        a,
                        declared=None,
                        locked=False,
                        adapt_enabled=False,
                        adapt_first_accepted=False,
                        adapt_last_applied_at=None,
                        declared_revision=new_version,
                    )
                    for k, a in p.axes.items()
                }
            if scope == "all":
                p.axes = {k: replace(a, hidden=False, inference_allowed=True) for k, a in p.axes.items()}
                for o in p.overrides:
                    txn.delete("PersonaContextOverrides", spanner.KeySet(keys=[[p.member_id, o.override_id]]))
                p.overrides = []
                p.budget_ceiling_minor = p.budget_currency = None
                p.excluded_brands, p.excluded_materials, p.excluded_categories, p.goals = [], [], [], []
                p.prefer_owned = False
                p.social_signals_enabled = True
            p.version = new_version
            self._write(txn, p, now)
            write_outbox(txn, [self._event(p, principal.actor_ref, principal.environment, now, f"reset_{scope}", AXIS_KEYS)])
            p.updated_at = now
            return self._dto(p, now)

        return run_txn(self.db, txn_fn)

    # ----------------------------------------------------------- snapshots

    def create_snapshot(self, principal: Principal, name: str) -> Dict[str, Any]:
        principal.require("profile:write")
        if not isinstance(name, str) or not (1 <= len(name.strip()) <= 80):
            raise ValidationFailed("snapshot name must be 1-80 characters")

        def txn_fn(txn):
            now = self.clock.now()
            p = self._begin(txn, principal, None)
            if not p.exists:
                raise InvalidTransition("save your style before taking a snapshot")
            eff = resolve_effective(p.axes, p.overrides, p.learning_enabled, now)
            snap = {
                "declared": {k: p.axes[k].declared for k in AXIS_KEYS},
                "locked": [k for k in AXIS_KEYS if p.axes[k].locked],
                "effective": {k: eff[k].value for k in AXIS_KEYS},
            }
            declared_n = sum(1 for v in snap["declared"].values() if v is not None)
            summary = f"{declared_n} of 12 axes chosen, {len(snap['locked'])} locked"
            first = not query(txn, "SELECT 1 FROM PersonaSnapshots WHERE member_id=@m LIMIT 1", {"m": p.member_id}, {"m": STR})
            sid = new_id()
            txn.insert(
                "PersonaSnapshots",
                columns=("member_id", "snapshot_id", "profile_version", "saved_name", "axes_snapshot", "redacted_summary", "created_at"),
                values=[(p.member_id, sid, p.version, name.strip(), JsonObject(snap), summary, spanner.COMMIT_TIMESTAMP)],
            )
            write_outbox(
                txn,
                [
                    OutboxEvent(
                        event_type="persona.snapshot.saved",
                        aggregate_type="persona_profile",
                        aggregate_id=p.member_id,
                        aggregate_version=p.version,
                        payload={
                            "member_id": p.member_id,
                            "snapshot_id": sid,
                            "profile_version": str(p.version),
                            "first_snapshot": first,
                        },
                        actor_ref=principal.actor_ref,
                        environment=principal.environment,
                        occurred_at=now,
                    )
                ],
            )
            return {"snapshot_id": sid, "saved_name": name.strip(), "profile_version": str(p.version), "summary": summary}

        return run_txn(self.db, txn_fn)

    def snapshot_diff(self, principal: Principal, snapshot_id: str) -> Dict[str, Any]:
        principal.require("profile:read")

        def read(snap):
            rows = query(
                snap,
                "SELECT axes_snapshot, saved_name, profile_version FROM PersonaSnapshots WHERE member_id=@m AND snapshot_id=@s",
                {"m": principal.member_id, "s": snapshot_id},
                {"m": STR, "s": STR},
            )
            if not rows:
                raise NotFound("snapshot not found")
            return rows, self._load(snap, principal.member_id)

        rows, p = run_read(self.db, read)
        data = json_value(rows[0][0])
        changes = []
        for k in AXIS_KEYS:
            then_v, now_v = data["declared"].get(k), p.axes[k].declared
            then_l, now_l = k in data["locked"], p.axes[k].locked
            if then_v != now_v or then_l != now_l:
                changes.append({"axis": k, "current": now_v, "snapshot": then_v, "current_locked": now_l, "snapshot_locked": then_l})
        return {"snapshot_id": snapshot_id, "saved_name": rows[0][1], "profile_version": str(rows[0][2]), "changes": changes}

    def restore_snapshot(self, principal: Principal, if_match: Optional[str], snapshot_id: str) -> Dict[str, Any]:
        principal.require("profile:write")
        parse_revision(if_match)

        def txn_fn(txn):
            now = self.clock.now()
            p = self._begin(txn, principal, if_match)
            rows = query(
                txn,
                "SELECT axes_snapshot FROM PersonaSnapshots WHERE member_id=@m AND snapshot_id=@s",
                {"m": p.member_id, "s": snapshot_id},
                {"m": STR, "s": STR},
            )
            if not rows:
                raise NotFound("snapshot not found")
            data = json_value(rows[0][0])
            new_version = p.version + 1
            changed = []
            for k in AXIS_KEYS:
                v, lk = data["declared"].get(k), k in data["locked"]
                a = p.axes[k]
                if a.declared != v or a.locked != lk:
                    changed.append(k)
                    p.axes[k] = replace(a, declared=v, locked=lk, adapt_enabled=False if lk else a.adapt_enabled, declared_revision=new_version)
            p.version = new_version
            self._write(txn, p, now)
            write_outbox(txn, [self._event(p, principal.actor_ref, principal.environment, now, "snapshot_restored", changed)])
            p.updated_at = now
            return self._dto(p, now)

        return run_txn(self.db, txn_fn)

    # ---------------------------------------------------- context overrides

    def add_context_override(
        self, principal: Principal, if_match: Optional[str], label: str, axes: Mapping[str, Any], starts_at: datetime, ends_at: datetime
    ) -> Dict[str, Any]:
        principal.require("profile:write")
        parse_revision(if_match)
        if not isinstance(label, str) or not (1 <= len(label.strip()) <= 120):
            raise ValidationFailed("label must be 1-120 characters")
        parsed = {validate_axis_key(k): require_strict_int(v, name=k, lo=0, hi=100) for k, v in (axes or {}).items()}
        if not parsed:
            raise ValidationFailed("an override needs at least one axis")
        if starts_at.tzinfo is None or ends_at.tzinfo is None or ends_at <= starts_at:
            raise ValidationFailed("override window must be a valid UTC interval")

        def txn_fn(txn):
            now = self.clock.now()
            p = self._begin(txn, principal, if_match)
            if not p.exists:
                raise InvalidTransition("save your style before adding a context")
            oid = new_id()
            txn.insert(
                "PersonaContextOverrides",
                columns=("member_id", "override_id", "label", "axes", "starts_at", "ends_at", "enabled", "created_at"),
                values=[(p.member_id, oid, label.strip(), JsonObject(parsed), starts_at, ends_at, True, spanner.COMMIT_TIMESTAMP)],
            )
            p.overrides.append(ContextOverride(oid, label.strip(), parsed, starts_at, ends_at, True))
            p.version += 1
            self._write(txn, p, now, axes_changed=())
            write_outbox(txn, [self._event(p, principal.actor_ref, principal.environment, now, "context_override", parsed.keys())])
            p.updated_at = now
            return self._dto(p, now)

        return run_txn(self.db, txn_fn)

    def set_context_override_enabled(self, principal: Principal, if_match: Optional[str], override_id: str, enabled: bool) -> Dict[str, Any]:
        principal.require("profile:write")
        parse_revision(if_match)

        def txn_fn(txn):
            now = self.clock.now()
            p = self._begin(txn, principal, if_match)
            o = next((o for o in p.overrides if o.override_id == override_id), None)
            if o is None:
                raise NotFound("context not found")
            txn.update(
                "PersonaContextOverrides",
                columns=("member_id", "override_id", "enabled"),
                values=[(p.member_id, override_id, bool(enabled))],
            )
            p.overrides = [replace(x, enabled=bool(enabled)) if x.override_id == override_id else x for x in p.overrides]
            p.version += 1
            self._write(txn, p, now, axes_changed=())
            write_outbox(txn, [self._event(p, principal.actor_ref, principal.environment, now, "context_override", o.axes.keys())])
            p.updated_at = now
            return self._dto(p, now)

        return run_txn(self.db, txn_fn)

    # ---------------------------------------------------------- adaptation

    def accept_adaptation(self, principal: Principal, if_match: Optional[str], axis: str) -> Dict[str, Any]:
        principal.require("profile:write")
        validate_axis_key(axis)
        parse_revision(if_match)

        def txn_fn(txn):
            now = self.clock.now()
            p = self._begin(txn, principal, if_match)
            prop = next((a for a in adaptation_proposals(p.axes, p.learning_enabled, now) if a.axis == axis), None)
            if prop is None:
                raise InvalidTransition("no adaptation is currently proposed for this axis")
            p.version += 1
            p.axes[axis] = replace(
                p.axes[axis],
                declared=prop.proposed,
                adapt_first_accepted=True,
                adapt_last_applied_at=now,
                declared_revision=p.version,
            )
            self._write(txn, p, now, axes_changed=[axis])
            write_outbox(txn, [self._event(p, principal.actor_ref, principal.environment, now, "adaptation_accepted", [axis])])
            p.updated_at = now
            return self._dto(p, now)

        return run_txn(self.db, txn_fn)

    def run_weekly_adaptation(self, member_id: str, environment: str = "development") -> List[str]:
        """Scheduled worker: apply only already-confirmed, bounded adaptation steps."""

        def txn_fn(txn):
            now = self.clock.now()
            if self._tombstoned(txn, member_id):
                return []
            p = self._load(txn, member_id)
            props = [a for a in adaptation_proposals(p.axes, p.learning_enabled, now) if not a.requires_confirmation]
            if not props:
                return []
            p.version += 1
            for a in props:
                p.axes[a.axis] = replace(p.axes[a.axis], declared=a.proposed, adapt_last_applied_at=now, declared_revision=p.version)
            self._write(txn, p, now, axes_changed=[a.axis for a in props])
            write_outbox(txn, [self._event(p, "worker:persona-adaptation", environment, now, "adaptation_applied", [a.axis for a in props])])
            return [a.axis for a in props]

        return run_txn(self.db, txn_fn)

    # ------------------------------------------------------ recommendations

    def _request_for(self, txn, p: _Profile, now: datetime, occasion: Optional[str], limit: int) -> RecommendationRequest:
        eff = resolve_effective(p.axes, p.overrides, p.learning_enabled, now)
        feedback: Dict[str, List[int]] = {}
        dismissed: Set[str] = set()
        if p.exists:
            for prod, cat, sig in query(
                txn,
                "SELECT product_id, category, signal FROM RecommendationFeedback WHERE member_id=@m",
                {"m": p.member_id},
                {"m": STR},
            ):
                if sig == "not_me":
                    dismissed.add(prod)
                if p.learning_enabled:
                    feedback.setdefault(cat, []).append(FEEDBACK_SIGNALS[sig])
        wardrobe = list(self.wardrobe_source(txn, p.member_id))
        return RecommendationRequest(
            effective={k: eff[k].value for k in AXIS_KEYS},
            effective_sources={k: eff[k].source for k in AXIS_KEYS},
            occasion=occasion,
            budget_ceiling_minor=p.budget_ceiling_minor,
            budget_currency=p.budget_currency,
            excluded_brands=frozenset(p.excluded_brands),
            excluded_materials=frozenset(p.excluded_materials),
            excluded_categories=frozenset(p.excluded_categories),
            dismissed_products=frozenset(dismissed),
            wardrobe=wardrobe,
            feedback_by_category=feedback,
            limit=limit,
        )

    def recommendations(self, principal: Principal, *, occasion: Optional[str] = None, limit: int = 6) -> Dict[str, Any]:
        principal.require("profile:read")
        limit = require_strict_int(limit, name="limit", lo=1, hi=24)
        now = self.clock.now()

        def read(snap):
            p = self._load_visible(snap, principal.member_id)
            return p, self._request_for(snap, p, now, occasion, limit)

        p, req = run_read(self.db, read)
        result = recommend(self.candidate_source(principal), req).to_dict()
        result["profile_version"] = str(p.version)
        return result

    def preview(self, principal: Principal, body: Mapping[str, Any], *, occasion: Optional[str] = None) -> Dict[str, Any]:
        """Read-only: applies a draft in memory, never writes the profile."""
        principal.require("profile:read")
        if not isinstance(body, Mapping):
            raise ValidationFailed("body must be an object")
        reject_unknown_keys(body, ("changes", "client_revision", "constraints"), where="persona preview")
        cr = body.get("client_revision")
        if not isinstance(cr, str) or not (1 <= len(cr) <= 64):
            raise ValidationFailed("client_revision is required")
        changes = body.get("changes") or []
        if not isinstance(changes, list) or len(changes) > 12:
            raise ValidationFailed("changes must be a list of at most 12")
        now = self.clock.now()

        def read(snap):
            p = self._load_visible(snap, principal.member_id)
            seen = set()
            for ch in changes:
                if not isinstance(ch, Mapping):
                    raise ValidationFailed("each change must be an object")
                reject_unknown_keys(ch, CHANGE_KEYS, where="axis change")
                k = validate_axis_key(ch.get("axis"))
                if k in seen:
                    raise ValidationFailed(f"duplicate axis {k}")
                seen.add(k)
                p.axes[k] = replace(p.axes[k], declared=validate_axis_value(ch.get("value")), locked=bool(ch.get("locked", False)))
            self._apply_constraints(p, body.get("constraints") or {})
            return p, self._request_for(snap, p, now, occasion, 6)

        p, req = run_read(self.db, read)
        result = recommend(self.candidate_source(principal), req).to_dict()
        eff = resolve_effective(p.axes, p.overrides, p.learning_enabled, now)
        return {
            "client_revision": cr,
            "profile_version": str(p.version),
            "effective_axes": {k: eff[k].value for k in AXIS_KEYS},
            "recommendations": result,
            "persisted": False,
        }

    def record_feedback(self, principal: Principal, product_id: str, category: str, signal: str, idempotency_key: str) -> Dict[str, Any]:
        principal.require("profile:write")
        if signal not in FEEDBACK_SIGNALS:
            raise ValidationFailed("signal must be interested or not_me")
        if not isinstance(category, str) or not (1 <= len(category) <= 60):
            raise ValidationFailed("category required")
        digest = canonical_digest({"product_id": product_id, "category": category, "signal": signal})

        def txn_fn(txn):
            hit = idempotency_lookup(txn, principal, "recommendation.feedback", idempotency_key, digest)
            if hit:
                return hit.response
            p = self._begin(txn, principal, None)
            if not p.exists:
                raise InvalidTransition("save your style before giving feedback")
            fid = new_id()
            txn.insert(
                "RecommendationFeedback",
                columns=("member_id", "feedback_id", "product_id", "category", "signal", "created_at"),
                values=[(p.member_id, fid, product_id, category, signal, spanner.COMMIT_TIMESTAMP)],
            )
            resp = {"feedback_id": fid, "signal": signal, "learning_applied": p.learning_enabled}
            idempotency_store(txn, principal, "recommendation.feedback", idempotency_key, digest, resp, self.clock.now())
            return resp

        return run_txn(self.db, txn_fn)
