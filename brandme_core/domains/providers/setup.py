"""Operator provider setup and connection tests (ch.05 §8; §1 "configured is not verified").

Each provider's setup has six sections: what this enables, access prerequisites,
credential inputs, permitted data use, connection tests and activation.

* Saving setup (any partial subset) never changes a capability state.
* Credential inputs accept only a Secret Manager resource name. Anything that
  looks like a secret value is refused in every field, and responses never echo
  a stored reference: only whether it is set, a fingerprint and the rotation time.
* A connection test runs through the adapter's ``probe`` outside any
  transaction. Its time, environment, exact capability, mode and sanitized
  evidence are then persisted in one transaction. A passing test with a
  verifying evidence kind refreshes a capability that is already enabled
  (through the registry, so a simulation stays ``sandbox``); a failed test
  degrades it; a blocked test changes nothing.
* Activation is the explicit operator step that enables a capability. It needs
  every prerequisite for that capability and a passing, verifying test no older
  than ``ACTIVATION_FRESHNESS``. Nothing else enables a capability here.

Stores write only inside ``transact(env, provider_id, fn)``: ``fn`` receives a
snapshot read in that transaction and returns ``(SetupWrite, result)``. A
retried attempt recomputes both; no provider I/O and no registry mutation
happen inside ``fn``. The in-process registry is updated after commit.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import uuid
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Tuple, TypeVar

from brandme_core.domains.commerce.errors import CommerceError, Forbidden, InvalidRequest, NotFound, VersionConflict
from brandme_core.domains.commerce.principal import Principal

from .contracts import (
    CAPABILITIES, EVIDENCE_KINDS, EXECUTABLE_STATES, PROBE_MODES, PROBE_RESULTS, SETUP_SECTIONS, VERIFYING_EVIDENCE,
    ProbeResult, ProviderError, SetupField, SetupProfile, VerifiableProvider,
)
from .registry import CapabilityStatus, ProviderConnection, ProviderRegistry, RegistryError
from .ingestion import CatalogIngestor, IngestionAudit, ShelfCounts
from .tiers import (
    ASSIGNMENT_ITEM_KEY, ASSIGNMENT_SECTION, CAPABILITY_CUSTOMIZATION, GATED_CAPABILITIES, PricingTable,
    ResolvedTier, TierAuditSink, TierDecision, assignment_value, check_capability, decision_record, emit,
    pricing_table_for, resolve_from_items, shelf_decision,
)

T = TypeVar("T")

PROVIDER_ADMIN_SCOPE = "provider:admin"
ACTIVATION_FRESHNESS = timedelta(hours=24)
STANDARD_DATA_USE_RIGHTS = ("display_images", "cache_images", "transform_images", "retain_prices",
                            "affiliate_tracking", "derive_3d_or_ai")
REFERENCE_FIELDS = ("approval_evidence_ref", "account_ref", "catalog_ref", "endpoint_descriptor_ref")
SETUP_UPDATE_FIELDS = frozenset({"access_level", "program_application_opened", "credential_secret_ref", "data_use",
                                 "activate", *REFERENCE_FIELDS})

CAPABILITY_LABELS: Mapping[str, str] = {
    "catalog.search": "Search the catalog", "catalog.detail": "Show product detail and variants",
    "catalog.feed": "Ingest the catalog feed", "catalog.images": "Display approved product images",
    "catalog.3d": "Use provider 3D assets", "inventory.read": "Read current stock",
    "price.quote": "Get a fresh price quote", "cart.create": "Create a provider cart",
    "cart.update": "Change a provider cart", "checkout.handoff": "Continue at the retailer's checkout",
    "checkout.submit": "Submit an approved checkout", "orders.read": "Read order status",
    "orders.webhook": "Receive signed order events", "returns.request": "Request a return",
    "refunds.read": "Read refund status", "affiliate.attribution": "Attribute affiliate links",
    "receipts.import": "Import receipts", "tryon.photo": "Photo try-on", "tryon.live": "Live try-on",
    "rights.issue": "Issue rights", "rights.transfer": "Transfer rights", "rights.reprint": "Reprint under a license",
    "manufacture.quote": "Quote manufacturing", "manufacture.submit": "Submit a manufacturing job",
}
DATA_USE_LABELS: Mapping[str, str] = {
    "display_images": "Display product images", "cache_images": "Cache product images",
    "transform_images": "Transform images (resize, background removal)", "retain_prices": "Retain observed prices",
    "affiliate_tracking": "Use affiliate tracking", "derive_3d_or_ai": "Create derived 3D or AI representations",
    "cache_prices": "Cache observed prices", "derive_3d": "Create derived 3D representations",
}
SECTION_TITLES: Mapping[str, str] = {
    "enables": "What this enables", "prerequisites": "Access prerequisites", "credentials": "Credential inputs",
    "data_use": "Permitted data use", "tests": "Connection tests", "activation": "Activation",
}


class SetupRefused(CommerceError):
    """A setup change the recorded evidence does not support (approval, activation)."""
    code, status = "setup_refused", 409


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _lines_during(exc: BaseException, lines: Callable[[], Any]) -> None:
    """Writes an operation's decision lines while ``exc`` propagates. ``emit`` swallows operational sink
    failures, so only a strict (test) log refusing a line raises here; it rides on ``exc`` as a note and never
    replaces it."""
    try:
        lines()
    except Exception as refused:
        exc.add_note(f"tier decision log refused a line: {refused}")


def _iso(ts: Optional[datetime]) -> Optional[str]:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


# ------------------------------------------------------------------ secret hygiene
_SECRET_TOKEN = re.compile(
    r"^(sk_|rk_|pk_|whsec_|sk-|ghp_|gho_|ghs_|github_pat_|glpat-|xox[abps]-|ya29\.|AKIA[0-9A-Z]{16}"
    r"|AIza[0-9A-Za-z_-]{30,}|eyJ[A-Za-z0-9_-]{8,})")
_TOKEN_SPLIT = re.compile(r"[\s/:@,;=?&]+")
_HEX = re.compile(r"^[0-9a-fA-F]+$")
_EMAIL = re.compile(r"\S+@\S+\.\S+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/@#+-]*$")
_EVIDENCE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@#+=-]{0,255}$")
_SECRET_RESOURCE = re.compile(
    r"^projects/([a-z0-9][a-z0-9.:-]{0,99})/secrets/([A-Za-z0-9_-]{1,255})/versions/([0-9]{1,10}|latest)$")


def _entropy(token: str) -> float:
    n = len(token)
    return -sum(c / n * math.log2(c / n) for c in Counter(token).values())


def looks_like_secret(value: str) -> bool:
    """Heuristic refusal of pasted secret values: known key prefixes, PEM blocks, long random text."""
    if "PRIVATE KEY" in value.upper() or "-----BEGIN" in value:
        return True
    for token in _TOKEN_SPLIT.split(value):
        if not token:
            continue
        if _SECRET_TOKEN.match(token) or (len(token) >= 32 and _HEX.match(token)):
            return True
        if len(token) >= 24:
            mixed = any(c.isupper() for c in token) and any(c.islower() for c in token) \
                and any(c.isdigit() for c in token)
            h = _entropy(token)
            if (mixed and h >= 4.3) or (len(token) >= 32 and h >= 4.5):
                return True
    return False


def secret_resource_name(value: Any) -> str:
    """A Secret Manager resource name, never a value: ``projects/*/secrets/*/versions/*``."""
    if not isinstance(value, str) or len(value) > 512 or not _SECRET_RESOURCE.match(value.strip()):
        raise InvalidRequest("credential_secret_ref must be a Secret Manager resource name "
                             "(projects/<project>/secrets/<name>/versions/<number|latest>), never a secret value",
                             code="invalid_secret_reference")
    value = value.strip()
    if looks_like_secret(value):
        raise InvalidRequest("credential_secret_ref looks like it contains a secret value; store the value in "
                             "Secret Manager and enter only its resource name", code="secret_value_refused")
    return value


def reference(name: str, value: Any, max_len: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidRequest(f"{name} must be a non-empty reference", code="invalid_reference")
    value = value.strip()
    if looks_like_secret(value):
        raise InvalidRequest(f"{name} looks like a secret value; enter a reference, and keep secrets in "
                             "Secret Manager", code="secret_value_refused")
    if len(value) > max_len or not _REFERENCE.match(value):
        raise InvalidRequest(f"{name} must be a plain reference of at most {max_len} characters "
                             "(letters, digits, space and . _ : / @ # + -)", code="invalid_reference")
    return value


def sanitize_summary(text: Any, limit: int = 1500) -> str:
    """Operator display text: no control characters, no secret-looking tokens, no e-mail addresses."""
    words = _CONTROL.sub(" ", str(text or "")).split()
    clean = " ".join("[redacted]" if looks_like_secret(w) or _EMAIL.search(w) else w for w in words)
    return clean[:limit]


def fingerprint(value: Optional[str]) -> Optional[str]:
    """Masked identifier for a stored reference: confirms a change without revealing the reference."""
    return "ref:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else None


def operator_ref(principal: Principal) -> str:
    """Stable pseudonymous operator reference for ``recorded_by``/``ran_by`` (never a raw member id)."""
    return "operator:" + hashlib.sha256(f"brandme:provider-setup:{principal.actor_ref}".encode()).hexdigest()[:24]


# ------------------------------------------------------------------ records
@dataclass(frozen=True)
class SetupItemRow:
    key: str
    section: str
    done: bool
    evidence_ref: Optional[str] = None  # operator-entered reference or verification run id; server-only
    recorded_by: Optional[str] = None
    recorded_at: Optional[datetime] = None


@dataclass(frozen=True)
class ConnectionRow:
    """The persisted ``ProviderConnections`` row (parent of setup items and capability rows)."""

    display_name: str
    simulation: bool
    access_level: str
    operator_account_ref: Optional[str]
    credential_secret_ref: Optional[str]
    credential_rotated_at: Optional[datetime]
    country_codes: Tuple[str, ...]
    disclosure: str
    data_use: Mapping[str, bool]
    allowed_redirect_hosts: Tuple[str, ...]
    protocols: Mapping[str, str]
    version: int

    @classmethod
    def from_connection(cls, c: ProviderConnection, version: int = 0) -> "ConnectionRow":
        return cls(c.display_name, c.simulation, c.access_level, c.operator_account_ref, c.credential_ref, None,
                   tuple(c.country_codes), c.disclosure, {k: bool(v) for k, v in dict(c.data_use).items()},
                   tuple(c.allowed_redirect_hosts), {k: str(v) for k, v in dict(c.protocols).items()}, version)


@dataclass(frozen=True)
class VerificationRun:
    run_id: str
    environment: str
    provider_id: str
    capability: str
    mode: Optional[str]
    result: str
    evidence_kind: str
    evidence_ref: str
    sanitized_summary: str
    reason_code: Optional[str]
    ran_by: str
    ran_at: datetime

    def to_wire(self) -> Dict[str, Any]:
        return {"run_id": self.run_id, "provider_id": self.provider_id, "environment": self.environment,
                "capability": self.capability, "mode": self.mode, "result": self.result,
                "evidence_kind": self.evidence_kind, "evidence_ref": self.evidence_ref,
                "sanitized_summary": self.sanitized_summary, "reason_code": self.reason_code,
                "ran_at": _iso(self.ran_at)}


@dataclass(frozen=True)
class SetupSnapshot:
    connection: Optional[ConnectionRow]
    items: Mapping[str, SetupItemRow]
    capabilities: Mapping[str, CapabilityStatus]  # persisted rows written by this workflow
    latest_runs: Mapping[str, VerificationRun]  # latest run per capability


@dataclass(frozen=True)
class SetupWrite:
    connection: Optional[ConnectionRow] = None  # required whenever items or capabilities are written
    items: Tuple[SetupItemRow, ...] = ()
    capabilities: Tuple[CapabilityStatus, ...] = ()
    runs: Tuple[VerificationRun, ...] = ()


# V006 has no mode/reason columns on ProviderVerificationRuns; they travel in a versioned summary document.
def _encode_summary(run: VerificationRun) -> str:
    return json.dumps({"v": 1, "mode": run.mode, "reason_code": run.reason_code, "text": run.sanitized_summary},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_summary(raw: Optional[str]) -> Tuple[Optional[str], Optional[str], str]:
    try:
        doc = json.loads(raw or "")
    except ValueError:
        return None, None, raw or ""
    if isinstance(doc, dict) and doc.get("v") == 1:
        return doc.get("mode"), doc.get("reason_code"), str(doc.get("text") or "")
    return None, None, raw or ""


def _check_write(write: SetupWrite, snap: SetupSnapshot) -> None:
    """The V006 column limits and constraints, enforced identically by both stores."""
    if (write.items or write.capabilities) and write.connection is None and snap.connection is None:
        raise ValueError("setup items and capability rows need their ProviderConnections parent row")
    c = write.connection
    if c is not None and (len(c.access_level) > 40 or len(c.operator_account_ref or "") > 256
                          or len(c.credential_secret_ref or "") > 512):
        raise ValueError("connection row exceeds V006 column limits")
    for i in write.items:
        if i.section not in SETUP_SECTIONS or not 0 < len(i.key) <= 40 or len(i.evidence_ref or "") > 256 \
                or len(i.recorded_by or "") > 128:
            raise ValueError(f"setup item {i.key!r} violates V006")
    for s in write.capabilities:
        if len(s.evidence_ref or "") > 256 or len(s.reason_code) > 80:
            raise ValueError(f"capability row {s.name} violates V006")
    for r in write.runs:
        if r.result not in PROBE_RESULTS or r.evidence_kind not in EVIDENCE_KINDS or not 0 < len(r.evidence_ref) <= 256 \
                or len(_encode_summary(r)) > 2000 or not 0 < len(r.ran_by) <= 128:
            raise ValueError(f"verification run {r.run_id} violates V006")


# ------------------------------------------------------------------ stores
class ProviderSetupStore(Protocol):
    def snapshot(self, environment: str, provider_id: str) -> SetupSnapshot: ...

    def recent_runs(self, environment: str, provider_id: str, *, capability: Optional[str] = None,
                    limit: int = 20) -> List[VerificationRun]: ...

    def transact(self, environment: str, provider_id: str,
                 fn: Callable[[SetupSnapshot], Tuple[SetupWrite, T]]) -> T: ...


class InMemoryProviderSetupStore:
    """Deterministic tests: ``transact`` serializes on a lock and applies the write only if ``fn`` returned."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connections: Dict[Tuple[str, str], ConnectionRow] = {}
        self._items: Dict[Tuple[str, str], Dict[str, SetupItemRow]] = {}
        self._caps: Dict[Tuple[str, str], Dict[str, CapabilityStatus]] = {}
        self._runs: List[VerificationRun] = []  # insertion order breaks ran_at ties

    def _ordered_runs(self, key: Tuple[str, str], capability: Optional[str] = None) -> List[VerificationRun]:
        rows = [(r.ran_at, i, r) for i, r in enumerate(self._runs)
                if (r.environment, r.provider_id) == key and capability in (None, r.capability)]
        return [r for _, _, r in sorted(rows, key=lambda t: (t[0], t[1]), reverse=True)]

    def _snapshot(self, key: Tuple[str, str]) -> SetupSnapshot:
        latest: Dict[str, VerificationRun] = {}
        for r in self._ordered_runs(key):
            latest.setdefault(r.capability, r)
        return SetupSnapshot(self._connections.get(key), dict(self._items.get(key, {})),
                             dict(self._caps.get(key, {})), latest)

    def snapshot(self, environment: str, provider_id: str) -> SetupSnapshot:
        with self._lock:
            return self._snapshot((environment, provider_id))

    def recent_runs(self, environment: str, provider_id: str, *, capability: Optional[str] = None,
                    limit: int = 20) -> List[VerificationRun]:
        with self._lock:
            return self._ordered_runs((environment, provider_id), capability)[:limit]

    def transact(self, environment: str, provider_id: str,
                 fn: Callable[[SetupSnapshot], Tuple[SetupWrite, T]]) -> T:
        key = (environment, provider_id)
        with self._lock:
            snap = self._snapshot(key)
            write, result = fn(snap)
            _check_write(write, snap)
            if write.connection is not None:
                self._connections[key] = write.connection
            self._items.setdefault(key, {}).update({i.key: i for i in write.items})
            self._caps.setdefault(key, {}).update({s.name: s for s in write.capabilities})
            self._runs.extend(write.runs)
            return result


_CONN_COLS = ("display_name", "simulation", "access_level", "operator_account_ref", "credential_secret_ref",
              "credential_rotated_at", "country_codes", "disclosure", "data_use", "allowed_redirect_hosts",
              "protocols", "version")
_ITEM_COLS = ("item_key", "section", "done", "evidence_ref", "recorded_by", "recorded_at")
_CAP_COLS = ("capability", "state", "reason_code", "last_checked_at", "evidence_ref", "evidence_kind")
_RUN_COLS = ("run_id", "environment", "provider_id", "capability", "evidence_kind", "evidence_ref", "result",
             "sanitized_summary", "ran_by", "ran_at")
_RUNS_SQL = ("SELECT " + ", ".join(f"r.{c}" for c in _RUN_COLS) + " FROM ProviderVerificationRuns"
             "@{FORCE_INDEX=ProviderVerificationRunsByProvider} AS r WHERE r.environment = @e AND r.provider_id = @p")
_LATEST_RUNS_SQL = _RUNS_SQL + """ AND r.ran_at = (SELECT MAX(x.ran_at) FROM ProviderVerificationRuns AS x
    WHERE x.environment = @e AND x.provider_id = @p AND x.capability = r.capability)"""


def _json_value(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    return json.loads(value.serialize() if hasattr(value, "serialize") else str(value))


def _run_from_row(row: Mapping[str, Any]) -> VerificationRun:
    mode, reason, text = _decode_summary(row["sanitized_summary"])
    return VerificationRun(row["run_id"], row["environment"], row["provider_id"], row["capability"], mode,
                           row["result"], row["evidence_kind"], row["evidence_ref"], text, reason, row["ran_by"],
                           row["ran_at"])


def _query_runs(reader, sql: str, params: Dict[str, Any], limit: Optional[int] = None) -> List[VerificationRun]:
    from google.cloud.spanner_v1 import param_types

    types = {k: param_types.STRING for k in params}
    if limit is not None:
        sql += " ORDER BY r.ran_at DESC, r.run_id DESC LIMIT @n"
        params, types = dict(params, n=limit), dict(types, n=param_types.INT64)
    return [_run_from_row(dict(zip(_RUN_COLS, r))) for r in reader.execute_sql(sql, params=params, param_types=types)]


def _read_snapshot(reader, environment: str, provider_id: str) -> SetupSnapshot:
    from google.cloud.spanner_v1 import KeyRange, KeySet

    rows = list(reader.read("ProviderConnections", columns=_CONN_COLS, keyset=KeySet(keys=[[environment, provider_id]])))
    conn = None
    if rows:
        r = dict(zip(_CONN_COLS, rows[0]))
        conn = ConnectionRow(r["display_name"], r["simulation"], r["access_level"], r["operator_account_ref"],
                             r["credential_secret_ref"], r["credential_rotated_at"], tuple(r["country_codes"] or ()),
                             r["disclosure"], {k: bool(v) for k, v in _json_value(r["data_use"]).items()},
                             tuple(r["allowed_redirect_hosts"] or ()),
                             {k: str(v) for k, v in _json_value(r["protocols"]).items()}, r["version"])
    prefix = KeySet(ranges=[KeyRange(start_closed=[environment, provider_id], end_closed=[environment, provider_id])])
    items = {r[0]: SetupItemRow(*r) for r in reader.read("ProviderSetupItems", columns=_ITEM_COLS, keyset=prefix)}
    caps = {r[0]: CapabilityStatus(*r) for r in reader.read("ProviderCapabilities", columns=_CAP_COLS, keyset=prefix)}
    latest: Dict[str, VerificationRun] = {}
    for run in sorted(_query_runs(reader, _LATEST_RUNS_SQL, {"e": environment, "p": provider_id}),
                      key=lambda r: (r.ran_at, r.run_id), reverse=True):
        latest.setdefault(run.capability, run)  # equal ran_at for one capability: tie broken arbitrarily
    return SetupSnapshot(conn, items, caps, latest)


class SpannerProviderSetupStore:
    """V006 ``ProviderConnections``/``ProviderSetupItems``/``ProviderCapabilities``/``ProviderVerificationRuns``."""

    def __init__(self, database) -> None:
        self.database = database

    def snapshot(self, environment: str, provider_id: str) -> SetupSnapshot:
        with self.database.snapshot(multi_use=True) as snap:
            return _read_snapshot(snap, environment, provider_id)

    def recent_runs(self, environment: str, provider_id: str, *, capability: Optional[str] = None,
                    limit: int = 20) -> List[VerificationRun]:
        sql, params = _RUNS_SQL, {"e": environment, "p": provider_id}
        if capability is not None:
            sql, params = sql + " AND r.capability = @c", dict(params, c=capability)
        with self.database.snapshot() as snap:
            return _query_runs(snap, sql, params, limit)

    def transact(self, environment: str, provider_id: str,
                 fn: Callable[[SetupSnapshot], Tuple[SetupWrite, T]]) -> T:
        def attempt(tx):
            snap = _read_snapshot(tx, environment, provider_id)  # reads take locks; a retry starts over
            write, result = fn(snap)
            _check_write(write, snap)
            self._apply(tx, environment, provider_id, snap, write)
            return result
        return self.database.run_in_transaction(attempt)

    @staticmethod
    def _apply(tx, environment: str, provider_id: str, snap: SetupSnapshot, write: SetupWrite) -> None:
        from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject

        key = [environment, provider_id]
        c = write.connection
        if c is not None:
            row = dict(zip(_CONN_COLS, (c.display_name, c.simulation, c.access_level, c.operator_account_ref,
                                        c.credential_secret_ref, c.credential_rotated_at, list(c.country_codes),
                                        c.disclosure, JsonObject(dict(c.data_use)), list(c.allowed_redirect_hosts),
                                        JsonObject(dict(c.protocols)), c.version)))
            row.update(environment=environment, provider_id=provider_id, updated_at=COMMIT_TIMESTAMP)
            if snap.connection is None:
                row["created_at"] = COMMIT_TIMESTAMP
                tx.insert("ProviderConnections", columns=list(row), values=[list(row.values())])
            else:
                tx.update("ProviderConnections", columns=list(row), values=[list(row.values())])
        if write.items:
            tx.insert_or_update("ProviderSetupItems", columns=("environment", "provider_id") + _ITEM_COLS,
                                values=[key + [i.key, i.section, i.done, i.evidence_ref, i.recorded_by, i.recorded_at]
                                        for i in write.items])
        if write.capabilities:
            tx.insert_or_update("ProviderCapabilities",
                                columns=("environment", "provider_id") + _CAP_COLS + ("updated_at",),
                                values=[key + [s.name, s.state, s.reason_code, s.last_checked_at, s.evidence_ref,
                                               s.evidence_kind, COMMIT_TIMESTAMP] for s in write.capabilities])
        if write.runs:
            tx.insert("ProviderVerificationRuns", columns=_RUN_COLS,
                      values=[[r.run_id, r.environment, r.provider_id, r.capability, r.evidence_kind, r.evidence_ref,
                               r.result, _encode_summary(r), r.ran_by, r.ran_at] for r in write.runs])


# ------------------------------------------------------------------ service
def _default_profile(conn: ProviderConnection) -> SetupProfile:
    if conn.simulation:
        return SetupProfile(summary=conn.disclosure, fixed_rows=(
            ("prerequisites", "simulation_mode", "Runs only in demo or development", "done",
             "The registry refuses simulation adapters in sandbox and production."),
            ("credentials", "credential", "No credential", "not_needed", "A local simulation has no account or secret.")))
    return SetupProfile(
        summary=f"{conn.display_name}: each capability below is enabled only after a passing test and activation.",
        fields=(SetupField("account", "credentials", "Provider account reference stored", "account_ref",
                           "Enter the approved provider account reference"),
                SetupField("secret", "credentials", "Credential stored in Secret Manager", "credential_secret_ref",
                           "Store the credential in Secret Manager, then enter its resource name")),
        data_use_rights=STANDARD_DATA_USE_RIGHTS, data_use_required_for=frozenset(CAPABILITIES))


class ProviderSetupService:
    def __init__(self, registry: ProviderRegistry, store: Optional[ProviderSetupStore] = None, *,
                 clock: Callable[[], datetime] = _utcnow, freshness: timedelta = ACTIVATION_FRESHNESS,
                 pricing_table: Optional[PricingTable] = None, tier_audit: Optional[TierAuditSink] = None):
        self.registry = registry
        self.environment = registry.environment
        self.store = store if store is not None else InMemoryProviderSetupStore()
        self.clock = clock
        self.freshness = freshness
        # Partner tiers (tiers.py): placeholder tiers in demo/development only; elsewhere none until priced.
        self.pricing_table: PricingTable = pricing_table_for(self.environment, pricing_table)
        self.tier_audit = tier_audit
        self._lock = threading.RLock()  # serializes applying persisted state to this process's registry
        self._applied: Dict[str, int] = {}  # provider -> the persisted connection version this process applied
        self._hydrate_refused: Dict[str, frozenset] = {}  # provider -> the hydrate refusals already logged

    # -- helpers -------------------------------------------------------------
    def _require_operator(self, principal: Principal) -> None:
        if principal.environment != self.environment:
            raise Forbidden("principal environment mismatch")
        if PROVIDER_ADMIN_SCOPE not in principal.scopes:  # an operator role; never implied by a member session
            raise Forbidden(f"scope {PROVIDER_ADMIN_SCOPE} required", code="insufficient_scope")

    def _connection(self, provider_id: Any) -> ProviderConnection:
        try:
            conn = self.registry.get(str(provider_id))
        except RegistryError:
            raise NotFound("provider not found") from None
        self._refresh(conn)
        return conn

    @staticmethod
    def profile(conn: ProviderConnection) -> SetupProfile:
        return getattr(conn.adapter, "setup_profile", None) or _default_profile(conn)

    def _refresh(self, conn: ProviderConnection, snap: Optional[SetupSnapshot] = None) -> None:
        """Brings this process's registry to the persisted setup and capability rows whenever the connection's
        persisted version moved: the first use (hydration), every write here, and writes by other processes
        (a downgrade elsewhere reaches this process on its next setup call). Versions apply in order, so a
        stale snapshot never overwrites a newer one. A 3D/AR capability applies as executable only where the
        current tier allows it; the store stays the record. An operator's suspension in this process is never
        lifted by a refresh. A hydrate refusal is logged when it first applies, not again on each version."""
        if snap is None:
            snap = self.store.snapshot(self.environment, conn.provider_id)  # a failed read is retried next time
        version = snap.connection.version if snap.connection is not None else 0
        overridden: List[Tuple[str, TierDecision]] = []
        with self._lock:
            if self._applied.get(conn.provider_id, -1) >= version:
                return
            tier = resolve_from_items(snap.items, self.pricing_table)
            self._sync(conn, snap)
            refused = set()
            for status in snap.capabilities.values():
                if conn.capability(status.name).state == "suspended":
                    continue  # in-process only (registry.suspend): held until the process lifts it
                if status.name in GATED_CAPABILITIES and status.state in EXECUTABLE_STATES:
                    d = check_capability(tier, status.name)
                    if not d.allowed:  # e.g. the pricing table changed since activation: never revive it
                        status = CapabilityStatus(status.name, "unconfigured", "tier_excludes_capability",
                                                  self.clock())
                        key = (status.name, d.code, tier.tier_id, tier.source, tier.table_version)
                        refused.add(key)
                        if key not in self._hydrate_refused.get(conn.provider_id, frozenset()):
                            overridden.append((status.name, d))
                self.registry.set_capability(conn.provider_id, status, tier_checked=True)
            self._hydrate_refused[conn.provider_id] = frozenset(refused)
            self._applied[conn.provider_id] = version
        for name, d in overridden:
            emit(self.tier_audit, decision_record(
                origin="hydrate", dimension="customization", outcome="refuse", code=d.code,
                provider_id=conn.provider_id, tier=tier, capability=name))

    def _after_commit(self, conn: ProviderConnection, lines: Callable[[], Any]) -> None:
        """Applies a committed write to this process's registry, then writes the operation's decision lines.
        The lines are written even when the post-commit read fails, because the write did commit."""
        try:
            self._refresh(conn)
        except BaseException as exc:
            _lines_during(exc, lines)
            raise
        lines()

    def _sync(self, conn: ProviderConnection, snap: SetupSnapshot) -> None:
        """Committed setup → in-process connection and adapter (never capability states)."""
        row = snap.connection
        if row is not None:
            self.registry.configure(conn.provider_id, access_level=row.access_level,
                                    operator_account_ref=row.operator_account_ref,
                                    credential_ref=row.credential_secret_ref, data_use=row.data_use)
        apply = getattr(conn.adapter, "apply_setup", None)
        if not callable(apply) or row is None:
            return
        profile = self.profile(conn)
        values: Dict[str, Any] = {}  # only what an operator saved; an unsaved step stays unset
        for f in profile.fields:
            item = snap.items.get(f.key)
            if item is None:
                continue
            if f.field == "access_level":
                values["access_level"] = row.access_level
            elif f.field == "program_application_opened":
                values[f.field] = item.done
            elif f.field == "credential_secret_ref":
                values.update(credential_secret_ref=row.credential_secret_ref,
                              credential_rotated_at=row.credential_rotated_at)
            elif f.field == "account_ref":
                values["account_ref"] = row.operator_account_ref
            else:
                values[f.field] = item.evidence_ref if item.done else None
                if f.field == "approval_evidence_ref":
                    values["approval_recorded_by"] = item.recorded_by if item.done else None
        marked = {r: row.data_use.get(r, False) for r in profile.data_use_rights
                  if snap.items.get(f"use:{r}") and snap.items[f"use:{r}"].done}
        if marked:
            values["data_use"] = marked
        if values:
            apply(values)

    @staticmethod
    def _base_row(conn: ProviderConnection, snap: SetupSnapshot, if_match: Optional[int]) -> ConnectionRow:
        row = snap.connection or ConnectionRow.from_connection(conn)
        if if_match is not None and row.version != if_match:
            raise VersionConflict(f"setup changed: expected version {if_match}, current is {row.version}",
                                  current_version=row.version)
        return row

    # -- reads ---------------------------------------------------------------
    def get_setup(self, principal: Principal, provider_id: str) -> Dict[str, Any]:
        self._require_operator(principal)
        conn = self._connection(provider_id)
        snap = self.store.snapshot(self.environment, conn.provider_id)
        return self._view(conn, snap, self.store.recent_runs(self.environment, conn.provider_id, limit=20))

    def list_runs(self, principal: Principal, provider_id: str, *, capability: Optional[str] = None,
                  limit: int = 20) -> Dict[str, Any]:
        self._require_operator(principal)
        if capability is not None and capability not in CAPABILITIES:
            raise InvalidRequest("unknown capability", code="unknown_capability")
        if not 1 <= limit <= 100:
            raise InvalidRequest("limit must be 1-100")
        conn = self._connection(provider_id)
        runs = self.store.recent_runs(self.environment, conn.provider_id, capability=capability, limit=limit)
        return {"provider_id": conn.provider_id, "environment": self.environment, "simulation": conn.simulation,
                "items": [r.to_wire() for r in runs], "next_cursor": None}

    # -- setup changes ---------------------------------------------------------
    def update_setup(self, principal: Principal, provider_id: str, fields: Mapping[str, Any], *,
                     if_match: Optional[int] = None) -> Dict[str, Any]:
        self._require_operator(principal)
        conn = self._connection(provider_id)
        profile = self.profile(conn)
        if "activate" in fields:
            if len(fields) != 1:  # a refused activation must never discard a partial save
                raise InvalidRequest("send activate on its own", code="activation_must_be_sent_alone")
            self._activate(principal, conn, profile, fields["activate"], if_match)
        else:
            self._save(principal, conn, profile, self._clean(profile, fields), if_match)
        snap = self.store.snapshot(self.environment, conn.provider_id)
        self._refresh(conn, snap)
        return self._view(conn, snap, self.store.recent_runs(self.environment, conn.provider_id, limit=20))

    def _clean(self, profile: SetupProfile, fields: Mapping[str, Any]) -> Dict[str, Any]:
        unknown = sorted(set(fields) - SETUP_UPDATE_FIELDS)
        if unknown:
            raise InvalidRequest(f"unexpected fields: {unknown}", code="unexpected_field")
        if not fields:
            raise InvalidRequest("send at least one setup field", code="empty_update")
        for name, value in fields.items():  # refuse pasted secrets first, whatever the field
            if isinstance(value, str) and looks_like_secret(value):
                raise InvalidRequest(f"{name} looks like a secret value; enter a reference, and keep secrets in "
                                     "Secret Manager", code="secret_value_refused")
        editable = {f.field for f in profile.fields} | ({"data_use"} if profile.data_use_rights else set())
        not_applicable = sorted(set(fields) - editable)
        if not_applicable:
            raise InvalidRequest(f"not part of this provider's setup: {not_applicable}",
                                 code="setup_field_not_applicable")
        clean: Dict[str, Any] = {}
        for name, value in fields.items():
            if name == "access_level":
                if value not in profile.access_levels:
                    raise InvalidRequest(f"access_level must be one of {list(profile.access_levels)}",
                                         code="invalid_access_level")
            elif name == "program_application_opened":
                if not isinstance(value, bool):
                    raise InvalidRequest("program_application_opened must be true or false")
            elif name == "credential_secret_ref":
                value = secret_resource_name(value)
            elif name == "data_use":
                rights = profile.data_use_rights
                if not isinstance(value, dict) or set(value) != set(rights) \
                        or not all(isinstance(v, bool) for v in value.values()):
                    raise InvalidRequest(f"data_use must mark every right ({', '.join(rights)}) true or false",
                                         code="invalid_data_use")
                value = {k: value[k] for k in rights}
            else:
                value = reference(name, value)
            clean[name] = value
        return clean

    def _save(self, principal: Principal, conn: ProviderConnection, profile: SetupProfile, clean: Dict[str, Any],
              if_match: Optional[int]) -> None:
        now, actor = self.clock(), operator_ref(principal)
        by_field = {f.field: f for f in profile.fields}

        def fn(snap: SetupSnapshot):
            row = self._base_row(conn, snap, if_match)
            approval = snap.items.get("approval")
            approved = bool(approval and approval.done) or "approval_evidence_ref" in clean
            changes: Dict[str, Any] = {}
            items: List[SetupItemRow] = []
            for name, value in clean.items():
                f = by_field.get(name)
                if name == "access_level":
                    if value in profile.approval_levels and not approved:
                        raise SetupRefused(f"{value} access needs recorded approval evidence first",
                                           code="approval_evidence_required")
                    changes["access_level"] = value
                    items.append(SetupItemRow(f.key, f.section, value != "unconfigured", None, actor, now))
                elif name == "data_use":
                    changes["data_use"] = dict(value)
                    items.extend(SetupItemRow(f"use:{k}", "data_use", True, None, actor, now) for k in value)
                elif name == "credential_secret_ref":
                    changes["credential_secret_ref"] = value
                    if value != row.credential_secret_ref:
                        changes["credential_rotated_at"] = now
                    items.append(SetupItemRow(f.key, f.section, True, None, actor, now))  # the ref lives in one place
                elif name == "account_ref":
                    changes["operator_account_ref"] = value
                    items.append(SetupItemRow(f.key, f.section, True, None, actor, now))
                elif name == "program_application_opened":
                    items.append(SetupItemRow(f.key, f.section, value, None, actor, now))
                else:
                    items.append(SetupItemRow(f.key, f.section, True, value, actor, now))
            # Never a capability row: saving setup cannot enable anything.
            return SetupWrite(replace(row, **changes, version=row.version + 1), tuple(items)), None

        self.store.transact(self.environment, conn.provider_id, fn)

    def _activate(self, principal: Principal, conn: ProviderConnection, profile: SetupProfile, capability: Any,
                  if_match: Optional[int]) -> None:
        if not isinstance(capability, str) or capability not in CAPABILITIES:
            raise InvalidRequest("unknown capability", code="unknown_capability")
        now, actor = self.clock(), operator_ref(principal)

        seen: List[ResolvedTier] = []  # the tier the committed (or refusing) attempt read

        def fn(snap: SetupSnapshot):
            del seen[:]
            seen.append(resolve_from_items(snap.items, self.pricing_table))
            row = self._base_row(conn, snap, if_match)
            problems = self._activation_problems(conn, profile, snap, row, capability, now)
            if problems:
                raise SetupRefused("; ".join(m for _, m in problems), code=problems[0][0])
            run = snap.latest_runs[capability]
            status = self.registry.verification_status(conn.provider_id, capability, evidence_ref=run.evidence_ref,
                                                       evidence_kind=run.evidence_kind, checked_at=run.ran_at)
            item = SetupItemRow(f"activate:{capability}", "activation", True, run.run_id, actor, now)
            return SetupWrite(replace(row, version=row.version + 1), (item,), (status,)), status

        gated = capability in GATED_CAPABILITIES

        def record(tier: ResolvedTier) -> None:
            d = check_capability(tier, capability)
            emit(self.tier_audit, decision_record(
                origin="activation", dimension="customization", outcome=d.outcome, code=d.code,
                provider_id=conn.provider_id, tier=tier, actor_ref=principal.actor_ref, capability=capability))

        try:
            self.store.transact(self.environment, conn.provider_id, fn)
        except SetupRefused as e:
            if gated and e.code == "activation_tier_excludes_capability" and seen:
                record(seen[0])
            raise
        # The committed row, in commit order (never the value computed before commit).
        self._after_commit(conn, lambda: record(seen[0]) if gated and seen else None)

    # -- partner tiers -----------------------------------------------------------
    def assign_tier(self, principal: Principal, provider_id: str, tier_id: Optional[str], *,
                    if_match: Optional[int] = None) -> Dict[str, Any]:
        """Records the connection's partner tier (``None`` clears it: no tier, nothing gated). Never enables a
        capability: an upgrade still needs activation backed by a fresh passing test. In the same write it
        resets every persisted-executable presentation capability that the new tier excludes, or that the tier
        in force did not allow (an activation from before a pricing-table change, or from before tiers)."""
        self._require_operator(principal)
        conn = self._connection(provider_id)
        table = self.pricing_table
        if tier_id is not None:
            tier = table.get(tier_id) if isinstance(tier_id, str) else None
            if tier is None:  # placeholder tables never exist outside demo/development (pricing_table_for)
                raise InvalidRequest("unknown partner tier", code="tier_unknown")
        now, actor = self.clock(), operator_ref(principal)

        def fn(snap: SetupSnapshot):
            row = self._base_row(conn, snap, if_match)
            assigned = SetupItemRow(ASSIGNMENT_ITEM_KEY, ASSIGNMENT_SECTION, tier_id is not None,
                                    assignment_value(tier_id, table) if tier_id is not None else None, actor, now)
            before = resolve_from_items(snap.items, table)
            new_tier = resolve_from_items({**snap.items, ASSIGNMENT_ITEM_KEY: assigned}, table)
            items: List[SetupItemRow] = [assigned]
            resets: List[CapabilityStatus] = []
            for cap in sorted(GATED_CAPABILITIES):
                persisted = snap.capabilities.get(cap)  # the store decides, not this process's view
                if cap not in conn.capabilities or persisted is None or persisted.state not in EXECUTABLE_STATES:
                    continue
                if check_capability(new_tier, cap).allowed and check_capability(before, cap).allowed:
                    continue
                resets.append(CapabilityStatus(cap, "unconfigured", "tier_excludes_capability", now))
                items.append(SetupItemRow(f"activate:{cap}", "activation", False, None, actor, now))
            return SetupWrite(replace(row, version=row.version + 1), tuple(items), tuple(resets)), (new_tier, resets)

        new_tier, resets = self.store.transact(self.environment, conn.provider_id, fn)

        def lines() -> None:
            emit(self.tier_audit, decision_record(
                origin="assignment", dimension="assignment", outcome="allow",
                code="tier_assigned" if tier_id is not None else "tier_cleared", provider_id=conn.provider_id,
                tier=new_tier, actor_ref=principal.actor_ref))
            for status in resets:
                emit(self.tier_audit, decision_record(
                    origin="assignment", dimension="customization", outcome="refuse", code="tier_reset_capability",
                    provider_id=conn.provider_id, tier=new_tier, actor_ref=principal.actor_ref,
                    capability=status.name))

        self._after_commit(conn, lines)
        snap = self.store.snapshot(self.environment, conn.provider_id)
        return self._view(conn, snap, self.store.recent_runs(self.environment, conn.provider_id, limit=20))

    def load_shelf_page(self, ingestor: CatalogIngestor, page: Any, *, provider_id: str, now: datetime,
                        audit: IngestionAudit, request_id: Optional[str] = None) -> Tuple[str, str]:
        """Loads one catalog page onto a connection's shelf within its tier's quota (the only production
        entry to ``CatalogIngestor.ingest_page``; no caller yet, the brand-shelf load is not built). The tier
        is read from the setup store for each page; one decision line per page; returns ``(outcome, code)``."""
        conn = self._connection(provider_id)
        tier = resolve_from_items(self.store.snapshot(self.environment, conn.provider_id).items, self.pricing_table)
        counts = ShelfCounts()  # this page's own counts, kept under the ingestor's lock (an audit may be shared)

        def line() -> Tuple[str, str]:
            outcome, code = shelf_decision(tier, requested=counts.added + counts.refused, refused=counts.refused)
            emit(self.tier_audit, decision_record(
                origin="ingestion", dimension="shelf_variants", outcome=outcome, code=code,
                provider_id=conn.provider_id, tier=tier, units_requested=counts.added + counts.refused,
                units_refused=counts.refused, request_id=request_id))
            return outcome, code

        try:
            ingestor.ingest_page(page, provider_id=conn.provider_id, now=now, audit=audit,
                                 max_active_listings=tier.limits.shelf_variants, counts=counts)
        except BaseException as exc:
            _lines_during(exc, line)  # a failed page is recorded too, with what it admitted
            raise
        return line()

    # -- connection tests -------------------------------------------------------
    def run_verification(self, principal: Principal, provider_id: str, capability: Any, mode: Any) -> Dict[str, Any]:
        self._require_operator(principal)
        if not isinstance(capability, str) or capability not in CAPABILITIES:
            raise InvalidRequest("unknown capability", code="unknown_capability")
        if mode not in PROBE_MODES:
            raise InvalidRequest(f"mode must be one of {list(PROBE_MODES)}", code="unknown_mode")
        conn = self._connection(provider_id)
        now = self.clock()
        probe = self._probe(conn, capability, mode, now)  # outside any transaction
        run = VerificationRun(str(uuid.uuid4()), self.environment, conn.provider_id, capability, mode, probe.result,
                              probe.evidence_kind, probe.evidence_ref, probe.sanitized_summary, probe.reason_code,
                              operator_ref(principal), now)

        gate: List[Tuple[ResolvedTier, TierDecision]] = []

        def fn(snap: SetupSnapshot):
            del gate[:]
            status = None
            # Enabled means enabled in the store (or declared by the adapter and never changed), read in this
            # transaction: a process whose view is stale can never refresh or degrade a reset capability.
            # An operator's suspension in this process wins: a test never lifts it.
            persisted = snap.capabilities.get(capability)
            state = persisted.state if persisted is not None else conn.capability(capability).state
            if conn.capability(capability).state == "suspended":
                state = "suspended"
            if state in EXECUTABLE_STATES:  # not yet enabled: only activation enables
                if capability in GATED_CAPABILITIES:
                    tier = resolve_from_items(snap.items, self.pricing_table)
                    d = check_capability(tier, capability)
                    if not d.allowed:  # e.g. a stale process after a downgrade: never refresh or degrade it
                        gate.append((tier, d))
                        return SetupWrite(runs=(run,)), None
                if probe.verifies:
                    status = self.registry.verification_status(
                        conn.provider_id, capability, evidence_ref=probe.evidence_ref,
                        evidence_kind=probe.evidence_kind, checked_at=now)
                elif probe.result == "failed":
                    status = CapabilityStatus(capability, "degraded", probe.reason_code or "connection_test_failed",
                                              now, probe.evidence_ref, probe.evidence_kind)
            if status is None:
                return SetupWrite(runs=(run,)), None
            row = snap.connection or ConnectionRow.from_connection(conn)
            return SetupWrite(replace(row, version=row.version + 1), (), (status,), (run,)), status

        self.store.transact(self.environment, conn.provider_id, fn)

        def lines() -> None:
            if gate:
                tier, d = gate[0]
                emit(self.tier_audit, decision_record(
                    origin="verification", dimension="customization", outcome="refuse", code=d.code,
                    provider_id=conn.provider_id, tier=tier, actor_ref=principal.actor_ref, capability=capability))

        self._after_commit(conn, lines)
        current = conn.capability(capability)
        return dict(run.to_wire(), capability_state=dict(current.to_public(), evidence_kind=current.evidence_kind))

    def _probe(self, conn: ProviderConnection, capability: str, mode: str, now: datetime) -> ProbeResult:
        if conn.capability(capability).state == "unsupported":
            return ProbeResult("blocked", "none", "blocked:capability_not_offered",
                               f"{capability} is not offered by this provider at this access level; there is "
                               "nothing to test.", "capability_not_offered")
        adapter = conn.adapter
        if not isinstance(adapter, VerifiableProvider):
            return ProbeResult("blocked", "none", "blocked:no_connection_test_for_adapter",
                               "This adapter has no connection test. Nothing was sent and no capability changed.",
                               "no_connection_test_for_adapter")
        try:
            result = adapter.probe(capability, mode, now)
        except ProviderError as e:
            return ProbeResult("failed", "none", f"error:{capability}:{e.kind.value}",
                               f"The provider answered {e.kind.value}; the test did not pass.", f"provider_{e.kind.value}")
        except Exception:  # a crashing test is a failed test, never a verified one
            return ProbeResult("failed", "none", f"error:{capability}:probe_error",
                               "The connection test stopped with an internal error; nothing was verified.",
                               "probe_error")
        if not isinstance(result, ProbeResult) or not _EVIDENCE_REF.match(result.evidence_ref or "") \
                or looks_like_secret(result.evidence_ref):
            return ProbeResult("failed", "none", f"error:{capability}:malformed_probe_result",
                               "The adapter returned an unusable test result; nothing was verified.",
                               "malformed_probe_result")
        reason = result.reason_code if result.reason_code and re.fullmatch(r"[a-z0-9_]{1,80}", result.reason_code) \
            else None
        return replace(result, sanitized_summary=sanitize_summary(result.sanitized_summary), reason_code=reason)

    # -- derived view ----------------------------------------------------------
    def _activation_problems(self, conn: ProviderConnection, profile: SetupProfile, snap: SetupSnapshot,
                             row: ConnectionRow, capability: str, now: datetime) -> List[Tuple[str, str]]:
        state = conn.capability(capability).state
        if state == "unsupported":
            return [("activation_capability_not_offered", f"{capability} is not offered by this provider")]
        if state == "suspended":
            return [("activation_capability_suspended", f"{capability} is suspended; lift the suspension first")]
        tier = resolve_from_items(snap.items, self.pricing_table)  # the tier this transaction read
        if not check_capability(tier, capability).allowed:
            needed = CAPABILITY_CUSTOMIZATION[capability].value
            held = f"tier {tier.tier_id} does not include it" if tier.assigned else {
                "unassigned": "no partner tier is assigned",
                "assigned_unknown": "the assigned tier is not in the current pricing table",
                "unconfigured": f"no pricing table is configured in {self.environment}"}[tier.source]
            return [("activation_tier_excludes_capability",
                     f"{capability} needs a partner tier with {needed} customization; {held}")]
        problems: List[Tuple[str, str]] = []
        missing = self._missing(profile, snap, row, capability)
        if missing:
            problems.append(("activation_prerequisites_missing", "complete first: " + ", ".join(missing)))
        run = snap.latest_runs.get(capability)
        if run is None or run.result != "passed":
            problems.append(("activation_test_required",
                             f"run a passing connection test for {capability}" if run is None else
                             f"the latest connection test for {capability} {run.result}; run a passing one"))
        elif run.evidence_kind not in VERIFYING_EVIDENCE:
            problems.append(("activation_evidence_not_verifying",
                             f"{run.evidence_kind} evidence cannot verify {capability}"))
        elif now - run.ran_at > self.freshness:
            hours = int(self.freshness.total_seconds() // 3600)
            problems.append(("activation_test_stale", f"the passing test is older than {hours} h; run it again"))
        return problems

    @staticmethod
    def _missing(profile: SetupProfile, snap: SetupSnapshot, row: ConnectionRow, capability: str) -> List[str]:
        done = lambda key: bool(snap.items.get(key) and snap.items[key].done)  # noqa: E731
        out = []
        if capability in profile.gated_capabilities and row.access_level not in profile.approval_levels:
            out.append("an approved access level (" + ", ".join(sorted(profile.approval_levels)) + ")")
        out += [f.label for f in profile.fields
                if (f.required_for is None or capability in f.required_for) and not done(f.key)]
        if capability in profile.data_use_required_for and not all(done(f"use:{r}") for r in profile.data_use_rights):
            out.append("permitted data use marked for every right")
        return out

    def _view(self, conn: ProviderConnection, snap: SetupSnapshot, runs: List[VerificationRun]) -> Dict[str, Any]:
        now = self.clock()
        profile = self.profile(conn)
        row = snap.connection or ConnectionRow.from_connection(conn)
        caps = {name: conn.capabilities[name] for name in sorted(conn.capabilities)}
        offered = [n for n, s in caps.items() if s.state != "unsupported"]
        unsupported = [n for n, s in caps.items() if s.state == "unsupported"]
        tier_view = None
        if any(n in GATED_CAPABILITIES for n in offered) or ASSIGNMENT_ITEM_KEY in snap.items:
            tier_view = {"tier": resolve_from_items(snap.items, self.pricing_table).to_wire(),
                         "tier_options": [t.to_wire() for t in self.pricing_table.tiers()]}
        done = lambda key: bool(snap.items.get(key) and snap.items[key].done)  # noqa: E731
        level_chosen = done("access_level")

        def not_needed(required_for: Optional[frozenset]) -> bool:
            return bool(level_chosen and profile.approval_levels and row.access_level not in profile.approval_levels
                        and required_for and required_for <= profile.gated_capabilities)

        def item(key: str, label: str, state: str, detail: Optional[str] = None, evidence_ref: Optional[str] = None,
                 recorded_at: Optional[datetime] = None) -> Dict[str, Any]:
            out: Dict[str, Any] = {"key": key, "label": label, "state": state}
            if detail:
                out["detail"] = detail
            if evidence_ref:
                out["evidence_ref"] = evidence_ref
            if recorded_at:
                out["recorded_at"] = _iso(recorded_at)
            return out

        sections: Dict[str, List[Dict[str, Any]]] = {k: [] for k in SECTION_TITLES}
        for name in offered:
            s = caps[name]
            state = {"verified": "done", "sandbox": "done", "unconfigured": "todo"}.get(s.state, "blocked")
            sim = " (simulation)" if conn.simulation and s.state == "sandbox" else ""
            sections["enables"].append(item(f"cap:{name}", f"{CAPABILITY_LABELS[name]} ({name})", state,
                                            f"{s.state}{sim}: {s.reason_code}"))
        if unsupported:
            sections["enables"].append(item("not_offered", "Not offered", "not_needed",
                                            "Not available from this provider: " + ", ".join(unsupported)))

        for section, key, label, state, detail in profile.fixed_rows:
            sections[section].append(item(key, label, state, detail))
        labels = {f.key: f.label for f in profile.fields}
        for f in profile.fields:
            stored = snap.items.get(f.key)
            if stored and stored.done:
                ref, detail = fingerprint(stored.evidence_ref), "Recorded"
                if f.field == "credential_secret_ref":
                    ref = fingerprint(row.credential_secret_ref)
                    detail = "Configured in Secret Manager (write-only)" + (
                        f"; rotated {_iso(row.credential_rotated_at)}" if row.credential_rotated_at else "")
                elif f.field == "account_ref":
                    ref = fingerprint(row.operator_account_ref)
                elif f.field == "access_level":
                    detail = f"Access level: {row.access_level}"
                elif f.field == "program_application_opened":
                    detail = "Application recorded as submitted by an operator"
                sections[f.section].append(item(f.key, f.label, "done", detail, ref, stored.recorded_at))
            elif not_needed(f.required_for):
                sections[f.section].append(item(f.key, f.label, "not_needed",
                                                f"Needed only for approved access. {f.action}"))
            else:
                waiting = [labels.get(a, a) for a in f.after if not done(a)]
                sections[f.section].append(
                    item(f.key, f.label, "blocked", f"Complete first: {', '.join(waiting)}. Then: {f.action}")
                    if waiting else item(f.key, f.label, "todo", f.action))

        if profile.data_use_rights:
            for right in profile.data_use_rights:
                stored = snap.items.get(f"use:{right}")
                label = DATA_USE_LABELS.get(right, right)
                if stored and stored.done:
                    sections["data_use"].append(item(
                        f"use:{right}", label, "done", "Permitted" if row.data_use.get(right) else "Not permitted",
                        recorded_at=stored.recorded_at))
                elif not_needed(profile.data_use_required_for):
                    sections["data_use"].append(item(f"use:{right}", label, "not_needed",
                                                     "Needed only for approved access."))
                else:
                    sections["data_use"].append(item(
                        f"use:{right}", label, "todo",
                        "Mark whether the agreement permits this; feed access does not grant it by itself"))
        else:
            for right, allowed in sorted(dict(conn.data_use).items()):
                sections["data_use"].append(item(f"use:{right}", DATA_USE_LABELS.get(right, right), "done",
                                                 ("Permitted" if allowed else "Not permitted") + " (fixed by the adapter)"))
            if not conn.data_use:
                sections["data_use"].append(item("use:none", "No media or price data", "not_needed",
                                                 "This provider supplies no data that needs usage rights."))

        hours = int(self.freshness.total_seconds() // 3600)
        for name in offered:
            run = snap.latest_runs.get(name)
            label = f"Connection test: {name}"
            if run is None:
                sections["tests"].append(item(f"test:{name}", label, "todo", "Run the read-only connection test"))
                continue
            if run.result == "passed" and run.evidence_kind not in VERIFYING_EVIDENCE:
                state, detail = "blocked", f"Passed {run.evidence_kind} only; that cannot verify {name}."
            elif run.result == "passed" and now - run.ran_at > self.freshness:
                state, detail = "todo", f"Last passed more than {hours} h ago; run it again."
            elif run.result == "passed":
                state, detail = "done", f"Passed ({run.evidence_kind}). {run.sanitized_summary}"
            elif run.result == "failed":
                state, detail = "todo", f"Failed: {run.sanitized_summary} Fix the cause and run it again."
            else:
                state, detail = "blocked", f"Blocked: {run.sanitized_summary}"
            sections["tests"].append(item(f"test:{name}", label, state, detail, run.evidence_ref, run.ran_at))

        for name in offered:
            stored = snap.items.get(f"activate:{name}")
            label = f"Activate {name}"
            if stored and stored.done:
                s = caps[name]
                sections["activation"].append(item(f"activate:{name}", label, "done",
                                                   f"Activated; now {s.state}: {s.reason_code}",
                                                   recorded_at=stored.recorded_at))
                continue
            problems = self._activation_problems(conn, profile, snap, row, name, now)
            hard = {"activation_capability_not_offered", "activation_capability_suspended",
                    "activation_evidence_not_verifying", "activation_tier_excludes_capability"}
            if not problems:
                sections["activation"].append(item(f"activate:{name}", label, "todo",
                                                   f"Ready: prerequisites done and a passing test within {hours} h."))
            else:
                latest = snap.latest_runs.get(name)
                blocked = any(c in hard for c, _ in problems) or not isinstance(conn.adapter, VerifiableProvider) \
                    or (latest is not None and latest.result == "blocked")
                sections["activation"].append(item(f"activate:{name}", label, "blocked" if blocked else "todo",
                                                   "Before activating: " + "; ".join(m for _, m in problems)))

        editable = [f.field for f in profile.fields] + (["data_use"] if profile.data_use_rights else [])
        return {
            "provider_id": conn.provider_id, "display_name": conn.display_name, "environment": self.environment,
            "simulation": conn.simulation, "disclosure": conn.disclosure, "access_level": row.access_level,
            "access_levels": list(profile.access_levels), "editable_fields": editable,
            "data_use_rights": list(profile.data_use_rights),
            "credential_configured": row.credential_secret_ref is not None,
            "credential_fingerprint": fingerprint(row.credential_secret_ref),
            "credential_rotated_at": _iso(row.credential_rotated_at),
            "version": str(row.version),
            "sections": [{"key": k, "title": SECTION_TITLES[k], **({"description": profile.summary} if k == "enables"
                                                                    else {}), "items": v}
                         for k, v in sections.items()],
            "capabilities": [dict(s.to_public(), evidence_kind=s.evidence_kind) for s in caps.values()],
            "testable_capabilities": offered,
            "connection_test_available": isinstance(conn.adapter, VerifiableProvider),
            "freshness_hours": hours,
            "recent_runs": [r.to_wire() for r in runs],
            "editable": True,
            # Partner tier (operator view only), shown where it bounds something: placeholder tiers are labeled
            # and nothing here is a price. A link-out or affiliate connection with no 3D/AR has no tier block.
            **(tier_view or {}),
        }
