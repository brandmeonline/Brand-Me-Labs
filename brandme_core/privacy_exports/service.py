"""Durable export queue, fenced builders and recurring private-object cleanup.

External I/O is outside retryable Spanner transactions. Every upload has a
pre-existing cleanup row and a unique attempt name; a stale builder can never
replace the winning object or make its own artifact downloadable.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from uuid import uuid4

from google.cloud.spanner_v1 import param_types as pt

from brandme_core.domains.privacy.deletion import ProcessingFrozenError, assert_processing_allowed
from brandme_core.domains.privacy.privacy import _scan_forbidden
from brandme_core.domains.rights.privacy_handler import RightsPrivacyHandler
from brandme_core.read_api.reads import BoundedSnapshot, ReadError, assert_serving, verify_schema as verify_reads
from .storage import MAX_PACKAGE

CATEGORIES = ("rights.control_links", "rights.operations", "rights.transfers", "rights.reprint_jobs", "rights.chain_commitments")
MAX_ROWS = 1000
LEASE_SECONDS = 120
FIELDS = ("environment", "job_id", "subject_ref", "network", "contract_address", "categories", "state",
          "requested_at", "expires_at", "completed_at", "attempt_id", "attempts", "lease_until",
          "next_attempt_at", "object_generation", "package_sha256", "package_bytes", "failure_code")


def verify_schema(database):
    if not set(CATEGORIES) <= {c.key for c in RightsPrivacyHandler().categories()}:
        raise ReadError(503, "export_catalog_unavailable")
    verify_reads(database)
    with database.snapshot(multi_use=True) as raw:
        s = BoundedSnapshot(raw)
        if s.query("SELECT state FROM SchemaMigrations WHERE version = 14") != [["applied"]]:
            raise ReadError(503, "schema_unavailable")
        s.query(f"SELECT {', '.join(FIELDS)} FROM PrivacyExportJobs LIMIT 0")
        s.query("SELECT cleanup_at FROM PrivacyExportObjects LIMIT 0")
        s.query("SELECT request_hash FROM PrivacyExportRequests LIMIT 0")


def recent_auth(value, now):
    try:
        if not isinstance(value, str) or len(value) > 40:
            raise ValueError()
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        age = (now - dt).total_seconds()
        if dt.tzinfo is None or not -5 <= age <= 600:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise ReadError(401, "reauth_required") from None


def _privacy(s, row):
    try:
        categories = set(row["categories"])
        if "rights.chain_commitments" in categories:
            categories.add("rights.control_links")  # public references still reveal a private member link
        for category in sorted(categories):
            assert_processing_allowed(s, row["subject_ref"], category, row["requested_at"])
    except ProcessingFrozenError:
        raise ReadError(409, "export_restricted") from None


def _now(s):
    return s.query("SELECT CURRENT_TIMESTAMP()")[0][0]


def _wire(row):
    return {"job_id": row["job_id"], "state": row["state"], "categories": row["categories"],
            "coverage": {"domains": ["rights"], "full_account": False, "selected_categories_only": True},
            "environment": row["environment"], "network": row["network"],
            "requested_at": row["requested_at"].isoformat(), "expires_at": row["expires_at"].isoformat(),
            "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
            "package_sha256": row["package_sha256"] if row["state"] == "ready" else None,
            "package_bytes": row["package_bytes"] if row["state"] == "ready" else None,
            "failure_code": row["failure_code"], "download_available": row["state"] == "ready"}


class ExportService:
    def __init__(self, database, config, store):
        self.db, self.config, self.store = database, config, store
        self.cleanup_failures = 0

    def transaction(self, fn):
        return self.db.run_in_transaction(fn, timeout_secs=8)

    def _row(self, s, job_id, subject=None, *, scoped=True):
        params = {"e": self.config.environment, "j": job_id}
        sql = f"SELECT {', '.join(FIELDS)} FROM PrivacyExportJobs WHERE environment = @e AND job_id = @j"
        if scoped:
            sql += " AND network = @n AND contract_address = @c"
            params.update(n=self.config.network, c=self.config.contract)
        if subject is not None:
            sql += " AND subject_ref = @s"
            params["s"] = subject
        rows = s.query(sql, params)
        if not rows:
            raise ReadError(404, "not_found")
        return dict(zip(FIELDS, rows[0]))

    def _update(self, tx, row, **values):
        # Column names are exclusively internal constants, never request data.
        types = {k: pt.TIMESTAMP if k.endswith("_at") or k == "lease_until" else
                 pt.INT64 if k in {"attempts", "package_bytes"} else pt.STRING for k in values}
        params = {**values, "e": row["environment"], "j": row["job_id"]}
        tx.execute_update("UPDATE PrivacyExportJobs SET " + ", ".join(f"{k} = @{k}" for k in values) +
                          " WHERE environment = @e AND job_id = @j", params=params,
                          param_types={**types, "e": pt.STRING, "j": pt.STRING}, retry=None, timeout=2)
        row.update(values)

    def capability(self):
        with self.db.snapshot(multi_use=True) as raw:
            assert_serving(BoundedSnapshot(raw))
        self.store.check()
        return {"status": "available", "environment": self.config.environment, "network": self.config.network,
                "contract_address": self.config.contract, "categories": list(CATEGORIES), "full_account": False,
                "selected_categories_only": True}

    def request(self, subject, categories, key, reauth):
        if (not isinstance(categories, list) or not 1 <= len(categories) <= len(CATEGORIES)
                or any(not isinstance(c, str) or c not in CATEGORIES for c in categories)
                or len(set(categories)) != len(categories)):
            raise ReadError(400, "explicit_supported_categories_required")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
            raise ReadError(400, "idempotency_key_required")
        categories = sorted(categories)
        request_hash = hashlib.sha256(json.dumps([self.config.network, self.config.contract, categories]).encode()).hexdigest()
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        job_id = str(uuid4())

        def create(tx):
            s = BoundedSnapshot(tx)
            assert_serving(s)
            now = _now(s)
            recent_auth(reauth, now)
            params = {"e": self.config.environment, "s": subject, "k": key_hash}
            existing = s.query("SELECT job_id, request_hash FROM PrivacyExportRequests "
                               "WHERE environment = @e AND subject_ref = @s AND key_hash = @k", params)
            if existing:
                if existing[0][1] != request_hash:
                    raise ReadError(409, "idempotency_conflict")
                row = self._row(s, existing[0][0], subject)
                _privacy(s, row)
                if now >= row["expires_at"]:
                    row["state"] = "expired"
                return _wire(row)
            row = {"environment": self.config.environment, "job_id": job_id, "subject_ref": subject,
                   "network": self.config.network, "contract_address": self.config.contract, "categories": categories,
                   "state": "requested", "requested_at": now, "expires_at": now + timedelta(hours=24),
                   "completed_at": None, "attempt_id": None, "attempts": 0, "lease_until": None,
                   "next_attempt_at": now, "object_generation": None, "package_sha256": None,
                   "package_bytes": None, "failure_code": None}
            _privacy(s, row)
            # Serializable predicate protects concurrent requests for one member.
            # A security abuse bound, independent of commercial/AI budgets.
            recent = s.query("SELECT state, expires_at FROM PrivacyExportJobs "
                             "WHERE environment = @e AND subject_ref = @s AND requested_at >= @since LIMIT 11",
                             {"e": row["environment"], "s": subject, "since": now - timedelta(days=1)},
                             {"e": pt.STRING, "s": pt.STRING, "since": pt.TIMESTAMP})
            if len(recent) >= 10 or sum(st in {"requested", "building", "ready"} and exp > now for st, exp in recent) >= 2:
                raise ReadError(429, "export_limit_reached")
            tx.insert("PrivacyExportJobs", columns=FIELDS, values=[[row[k] for k in FIELDS]])
            tx.insert("PrivacyExportRequests", columns=("environment", "subject_ref", "key_hash", "request_hash", "job_id"),
                      values=[(row["environment"], subject, key_hash, request_hash, job_id)])
            return _wire(row)

        return self.transaction(create)

    def status(self, subject, job_id):
        with self.db.snapshot(multi_use=True) as raw:
            s = BoundedSnapshot(raw)
            assert_serving(s)
            row = self._row(s, job_id, subject)
            _privacy(s, row)
            if _now(s) >= row["expires_at"]:
                row["state"] = "expired"
            return _wire(row)

    def _download_row(self, subject, job_id, reauth):
        with self.db.snapshot(multi_use=True) as raw:
            s = BoundedSnapshot(raw)
            assert_serving(s)
            row = self._row(s, job_id, subject)
            now = _now(s)
            recent_auth(reauth, now)
            _privacy(s, row)
            if now >= row["expires_at"]:
                raise ReadError(410, "export_expired")
            if row["state"] != "ready":
                raise ReadError(409, "export_not_ready")
            return row

    def download(self, subject, job_id, reauth):
        row = self._download_row(subject, job_id, reauth)
        self.store.check()
        data = self.store.get(self.store.key(job_id, row["attempt_id"]), row["object_generation"])
        if len(data) != row["package_bytes"] or hashlib.sha256(data).hexdigest() != row["package_sha256"]:
            raise ReadError(503, "export_integrity_unconfirmed")
        # Do not release bytes using only a pre-I/O authorization snapshot.
        latest = self._download_row(subject, job_id, reauth)
        if any(latest[k] != row[k] for k in ("attempt_id", "object_generation", "package_sha256")):
            raise ReadError(409, "export_changed")
        return data, row["package_sha256"]

    def claim(self):
        attempt = str(uuid4())

        def claim_tx(tx):
            s = BoundedSnapshot(tx)
            assert_serving(s)
            now = _now(s)
            ids = s.query("SELECT job_id FROM PrivacyExportJobs WHERE environment = @e AND network = @n "
                          "AND contract_address = @c AND state IN ('requested','building') "
                          "AND next_attempt_at <= CURRENT_TIMESTAMP() AND expires_at > CURRENT_TIMESTAMP() "
                          "ORDER BY next_attempt_at, job_id LIMIT 1",
                          {"e": self.config.environment, "n": self.config.network, "c": self.config.contract})
            if not ids:
                return None
            row = self._row(s, ids[0][0])
            if row["attempts"] >= 3:
                self._update(tx, row, state="failed", failure_code="attempts_exhausted", completed_at=now)
                return None
            try:
                _privacy(s, row)
            except ReadError:
                self._update(tx, row, state="failed", failure_code="export_restricted", completed_at=now)
                return None
            until = now + timedelta(seconds=LEASE_SECONDS)
            self._update(tx, row, state="building", attempt_id=attempt, attempts=row["attempts"] + 1,
                         lease_until=until, next_attempt_at=until, failure_code=None)
            tx.insert("PrivacyExportObjects", columns=("environment", "job_id", "attempt_id", "cleanup_at"),
                      values=[(row["environment"], row["job_id"], attempt, until + timedelta(seconds=10))])
            return row

        return self.transaction(claim_tx)

    def _live(self, s, claimed):
        assert_serving(s)
        row = self._row(s, claimed["job_id"])
        now = _now(s)
        if (row["state"] != "building" or row["attempt_id"] != claimed["attempt_id"]
                or row["lease_until"] <= now or row["expires_at"] <= now):
            raise ReadError(409, "export_lease_lost")
        _privacy(s, row)
        return row

    def build(self, claimed):
        sections = []
        with self.db.snapshot(multi_use=True) as raw:
            s = BoundedSnapshot(raw)
            row = self._live(s, claimed)
            params = {"s": row["subject_ref"], "n": row["network"], "c": row["contract_address"], "e": row["environment"]}
            for category in row["categories"]:
                # Bounded projections of the registered handler's fields. Never
                # fetch opaque operation arguments, witness data or provider JSON.
                if category in {"rights.control_links", "rights.chain_commitments"}:
                    fields = ("network", "contract_address", "entitlement_id", "asset_id", "epoch", "status", "last_tx_id")
                    table, where, use = "RightsEntitlements", "controller_subject_ref = @s AND network = @n AND contract_address = @c", ("s", "n", "c")
                elif category == "rights.operations":
                    fields = ("operation_id", "network", "contract_address", "circuit", "state", "tx_id", "created_at")
                    table, where, use = "ChainOperations", "owner_ref = @s AND network = @n AND contract_address = @c AND environment = @e", ("s", "n", "c", "e")
                elif category == "rights.transfers":
                    fields = ("intent_id", "network", "entitlement_id", "state", "created_at")
                    table, where, use = "TransferIntents", "from_subject_ref = @s AND network = @n", ("s", "n")
                elif category == "rights.reprint_jobs":
                    fields = ("job_id", "network", "entitlement_id", "state", "quantity", "created_at")
                    table, where, use = "ReprintJobs", "member_subject_ref = @s AND network = @n", ("s", "n")
                else:
                    raise ReadError(422, "unsupported_category")
                rows = s.query(f"SELECT {', '.join(fields)} FROM {table} WHERE {where} LIMIT {MAX_ROWS + 1}",
                               {k: params[k] for k in use})
                if len(rows) > MAX_ROWS:
                    raise ReadError(422, "export_too_large")
                records = [{k: v.isoformat() if isinstance(v, datetime) else str(v) if type(v) is int else v
                            for k, v in zip(fields, values)} for values in rows]
                if category == "rights.chain_commitments":
                    records = [{k: v for k, v in r.items() if k not in {"asset_id", "status"}} for r in records]
                sections.append({"category": category, "records": records,
                                 "scope": {"network": row["network"], "contract_address": row["contract_address"] if "c" in use else None},
                                 "public_references_only": category == "rights.chain_commitments"})
            captured = _now(s)
        package = {"schema": "brandme.selected-rights-export/v1", "job_id": row["job_id"],
                   "subject_ref": row["subject_ref"], "environment": row["environment"], "captured_at": captured.isoformat(),
                   "coverage": {"domains": ["rights"], "full_account": False, "selected_categories_only": True},
                   "sections": sections, "ownership_backup": "Midnight ownership secrets are excluded. A separate wallet "
                   "ownership backup is required; a wallet seed phrase alone does not restore contract private state. "
                   "This export does not provide that backup."}
        _scan_forbidden(package)
        content = json.dumps(package, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(content) > MAX_PACKAGE:
            raise ReadError(422, "export_too_large")
        return content

    def finish(self, claimed, generation, content):
        def finish_tx(tx):
            row = self._live(BoundedSnapshot(tx), claimed)
            self._update(tx, row, state="ready", completed_at=_now(BoundedSnapshot(tx)), lease_until=None,
                         object_generation=generation, package_sha256=hashlib.sha256(content).hexdigest(),
                         package_bytes=len(content), failure_code=None)
        self.transaction(finish_tx)

    def fail(self, claimed, code="export_failed"):
        def fail_tx(tx):
            s = BoundedSnapshot(tx)
            assert_serving(s)
            row = self._row(s, claimed["job_id"])
            now = _now(s)
            if row["state"] != "building" or row["attempt_id"] != claimed["attempt_id"] or row["lease_until"] <= now:
                return
            permanent = code in {"export_too_large", "export_restricted"} or row["attempts"] >= 3
            self._update(tx, row, state="failed" if permanent else "requested", lease_until=None,
                         next_attempt_at=now + timedelta(seconds=30), completed_at=now if permanent else None,
                         failure_code=code if code in {"export_too_large", "export_restricted"} else "export_failed")
        self.transaction(fail_tx)

    def sweep(self, limit=5):
        """Invalidate before delete; keep sweeping late/unknown-ack uploads."""
        self.cleanup_failures = 0
        with self.db.snapshot(multi_use=True) as raw:
            s = BoundedSnapshot(raw)
            assert_serving(s)
            rows = s.query("SELECT job_id, attempt_id FROM PrivacyExportObjects WHERE environment = @e "
                           "AND cleanup_at <= CURRENT_TIMESTAMP() ORDER BY cleanup_at LIMIT @limit",
                           {"e": self.config.environment, "limit": limit}, {"e": pt.STRING, "limit": pt.INT64})
        for job_id, attempt in rows:
            def invalidate(tx):
                s = BoundedSnapshot(tx)
                assert_serving(s)
                row = self._row(s, job_id, scoped=False)
                now = _now(s)
                if now >= row["expires_at"]:
                    self._update(tx, row, state="expired", lease_until=None)
                elif row["state"] in {"requested", "building", "ready"}:
                    try:
                        _privacy(s, row)
                    except ReadError:
                        self._update(tx, row, state="failed", failure_code="export_restricted", lease_until=None, completed_at=now)
                live = (row["attempt_id"] == attempt and (row["state"] == "ready" or
                        row["state"] == "building" and row["lease_until"] > now))
                # Recheck ready objects for restrictions every minute, even
                # before expiry. No public access depends on this poll interval.
                delay = 60 if live else 3600
                tx.execute_update("UPDATE PrivacyExportObjects SET cleanup_at = @next WHERE environment = @e "
                                  "AND job_id = @j AND attempt_id = @a",
                                  params={"next": now + timedelta(seconds=delay), "e": self.config.environment, "j": job_id, "a": attempt},
                                  param_types={"next": pt.TIMESTAMP, "e": pt.STRING, "j": pt.STRING, "a": pt.STRING}, retry=None, timeout=2)
                return not live
            try:
                remove = self.transaction(invalidate)
                if remove:
                    self.store.check()
                    self.store.delete(self.store.key(job_id, attempt))
            except Exception:
                # No provider details or personal identifiers in worker logs.
                # The durable row remains; a failed delete is retried next sweep.
                self.cleanup_failures += 1

    def run_once(self):
        self.sweep()
        claimed = self.claim()
        if claimed is None:
            return "idle"
        try:
            content = self.build(claimed)
            self.store.check()
            with self.db.snapshot(multi_use=True) as raw:
                self._live(BoundedSnapshot(raw), claimed)
            generation = self.store.put(self.store.key(claimed["job_id"], claimed["attempt_id"]), content)
            self.finish(claimed, generation, content)
            return "ready"
        except Exception as error:
            # If finalization committed but its ACK was lost, fail() sees ready
            # and leaves that winning object intact. Cleanup uses durable state.
            self.fail(claimed, error.code if isinstance(error, ReadError) else "export_failed")
            return "retry_or_failed"
