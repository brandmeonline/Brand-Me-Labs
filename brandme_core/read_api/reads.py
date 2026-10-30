"""Bounded, parameterized reads. Authorization and data share a strong snapshot.

This module never opens a write transaction or drives a privacy handler. The
catalog describes the existing rights handler, not whole-account coverage.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone

from google.cloud.spanner_v1 import param_types as pt

from brandme_core.domains.privacy.deletion import PrivacyRegistry, ProcessingFrozenError, assert_processing_allowed
from brandme_core.domains.rights.passport import API_VERSION, WHAT_THIS_MEANS
from brandme_core.domains.rights.privacy_handler import RightsPrivacyHandler
from .config import ReadConfig

JSON_LIMIT = 64 * 1024


class ReadError(Exception):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code
        super().__init__(code)


class BoundedSnapshot:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.deadline = time.monotonic() + 4

    def execute_sql(self, sql, **kwargs):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ReadError(503, "dependency_unavailable")
        return self.snapshot.execute_sql(sql, retry=None, timeout=min(2, remaining), **kwargs)

    def query(self, sql, params=None, types=None):
        params = params or {}
        return list(self.execute_sql(sql, params=params, param_types=types or {k: pt.STRING for k in params}))


def assert_serving(snap):
    if snap.query("SELECT restore_id FROM RestoreRuns WHERE state NOT IN ('tombstones_reapplied', 'serving') LIMIT 1"):
        raise ReadError(503, "restore_incomplete")


def verify_schema(database):
    with database.snapshot(multi_use=True) as raw:
        snap = BoundedSnapshot(raw)
        migrations = snap.query("SELECT version, state FROM SchemaMigrations ORDER BY version LIMIT 1000")
        # Versions 3–5 are reserved; the migration runner deliberately permits gaps.
        required = {1, 2, 6, 7, 8, 9, 10, 11, 12, 13}
        if not required <= {v for v, state in migrations if state == "applied"} or any(s != "applied" for _, s in migrations):
            raise ReadError(503, "schema_unavailable")
        # Check actual fields as well as the migration ledger. Request queries
        # still fail closed if a future schema becomes incompatible.
        for sql in (
            "SELECT projection_version, controller_subject_ref FROM RightsEntitlements LIMIT 0",
            "SELECT environment, visibility, value_json FROM PassportClaims LIMIT 0",
            "SELECT member_subject_ref, network, payment_state FROM ReprintJobs LIMIT 0",
            "SELECT subject_ref, state, receipt_json FROM DeletionJobs LIMIT 0",
            "SELECT subject_ref, category FROM ProcessingFreezes LIMIT 0",
            "SELECT subject_ref, created_at FROM DeletionTombstones LIMIT 0",
        ):
            snap.query(sql)
        assert_serving(snap)


def _iso(value):
    return value.isoformat() if value is not None else None


def _json(value):
    # Google Spanner can return a JsonObject or a JSON-encoded string.
    return json.loads(value) if isinstance(value, str) else value


class ReadService:
    def __init__(self, database, config: ReadConfig):
        self.db, self.config = database, config
        self.catalog = PrivacyRegistry()
        self.catalog.register(RightsPrivacyHandler())

    @contextmanager
    def snapshot(self):
        with self.db.snapshot(multi_use=True) as raw:
            snap = BoundedSnapshot(raw)
            assert_serving(snap)
            yield snap

    def ready(self):
        with self.snapshot():
            return {"status": "ready", "environment": self.config.environment, "read_only": True}

    def entitlements(self, subject, cursor, limit):
        fields = ("entitlement_id", "asset_id", "issuer_id", "epoch", "status", "transferable", "reprintable",
                  "last_tx_id", "last_block_height", "finalized_at", "updated_at")
        with self.snapshot() as snap:
            rows = snap.query(
                f"SELECT {', '.join(fields)} FROM RightsEntitlements WHERE network = @n AND contract_address = @c "
                "AND controller_subject_ref = @s AND entitlement_id > @after ORDER BY entitlement_id LIMIT @limit",
                {"n": self.config.network, "c": self.config.contract, "s": subject, "after": cursor, "limit": limit + 1},
                {"n": pt.STRING, "c": pt.STRING, "s": pt.STRING, "after": pt.STRING, "limit": pt.INT64})
        items = []
        for row in rows[:limit]:
            item = dict(zip(fields, row))
            for field in ("epoch", "last_block_height"):
                item[field] = str(item[field])  # lossless int64 on JavaScript clients
            for field in ("finalized_at", "updated_at"):
                item[field] = _iso(item[field])
            items.append(item)
        return {"environment": self.config.environment, "network": self.config.network,
                "contract_address": self.config.contract, "items": items,
                "next_cursor": rows[limit - 1][0] if len(rows) > limit else None}

    def reprint(self, subject, job_id):
        fields = ("job_id", "network", "entitlement_id", "manufacturer_id", "quantity", "state", "payment_state",
                  "units_attested", "created_at", "updated_at")
        with self.snapshot() as snap:
            rows = snap.query(f"SELECT {', '.join(fields)} FROM ReprintJobs "
                              "WHERE job_id = @j AND member_subject_ref = @s AND network = @n",
                              {"j": job_id, "s": subject, "n": self.config.network})
        if not rows:
            raise ReadError(404, "not_found")
        item = dict(zip(fields, rows[0]))
        for field in ("quantity", "units_attested"):
            item[field] = str(item[field])
        for field in ("created_at", "updated_at"):
            item[field] = _iso(item[field])
        return {**item, "environment": self.config.environment}

    def passport(self, subject, asset_id, cursor, limit):
        now = datetime.now(timezone.utc)
        viewer = "public"
        with self.snapshot() as snap:
            if subject:
                # PassportClaims has no contract or supplier binding. Grant owner
                # access only for one unambiguous active entitlement on this
                # network. A second contract/controller cannot confer access.
                links = snap.query("SELECT contract_address, controller_subject_ref, updated_at FROM RightsEntitlements "
                                   "WHERE asset_id = @a AND network = @n AND status = 'active' LIMIT 2",
                                   {"a": asset_id, "n": self.config.network})
                if len(links) == 1 and links[0][0:2] == [self.config.contract, subject]:
                    try:
                        assert_processing_allowed(snap, subject, "rights.control_links", links[0][2])
                        viewer = "owner"
                    except ProcessingFrozenError:
                        pass  # public statements remain public; never expose restricted claims
            # Opaque JSON has a SQL-side byte bound before it leaves Spanner.
            rows = snap.query(
                "SELECT claim_id, facet, claim_type, assurance, source, environment, network, evidence_ref, "
                f"CASE WHEN BYTE_LENGTH(TO_JSON_STRING(value_json)) <= {JSON_LIMIT} THEN TO_JSON_STRING(value_json) ELSE NULL END, "
                "observed_at, expires_at, revoked_at, BYTE_LENGTH(TO_JSON_STRING(value_json)) FROM PassportClaims "
                "WHERE asset_id = @a AND environment = @e AND (network IS NULL OR network = @n) "
                "AND (visibility = 'public' OR (visibility = 'owner' AND @owner AND network = @n)) "
                "AND claim_id > @after ORDER BY claim_id LIMIT @limit",
                {"a": asset_id, "e": self.config.environment, "n": self.config.network, "owner": viewer == "owner",
                 "after": cursor, "limit": limit + 1},
                {"a": pt.STRING, "e": pt.STRING, "n": pt.STRING, "owner": pt.BOOL, "after": pt.STRING, "limit": pt.INT64})
        statements = []
        for row in rows[:limit]:
            if row[12] and row[12] > JSON_LIMIT:
                raise ReadError(503, "stored_data_unavailable")
            expires, revoked = row[10], row[11]
            statements.append({"claim_id": row[0], "facet": row[1], "statement": row[2], "assurance": row[3],
                               "source": row[4], "environment": row[5], "network": row[6],
                               "test_network": row[6] in ("undeployed", "preview", "preprod"),
                               "evidence_ref": row[7], "value": _json(row[8]), "observed_at": _iso(row[9]),
                               "expires_at": _iso(expires),
                               "state": "revoked" if revoked else "expired" if expires and expires <= now else "current",
                               "what_this_means": WHAT_THIS_MEANS.get(row[2], "")})
        return {"api": API_VERSION, "asset_id": asset_id, "viewer": viewer, "environment": self.config.environment,
                "network": self.config.network, "statements": statements,
                "next_cursor": rows[limit - 1][0] if len(rows) > limit else None}

    def inventory(self):
        with self.snapshot():
            return {"environment": self.config.environment,
                    "categories": [{**asdict(c), "supplied_by": c.supplied_by.value, "on_delete": c.on_delete.value}
                                   for c in self.catalog.categories()],
                    "coverage": {"domains": ["rights"], "full_account": False},
                    "capabilities": {"export": "unavailable", "deletion": "unavailable"}}

    def deletion(self, subject, job_id):
        with self.snapshot() as snap:
            rows = snap.query(
                "SELECT scope, CASE WHEN ARRAY_LENGTH(categories) <= 100 THEN categories ELSE ARRAY<STRING>[] END, "
                "state, requested_at, completed_at, "
                f"CASE WHEN BYTE_LENGTH(TO_JSON_STRING(receipt_json)) <= {JSON_LIMIT} THEN TO_JSON_STRING(receipt_json) ELSE NULL END, "
                "BYTE_LENGTH(TO_JSON_STRING(receipt_json)), ARRAY_LENGTH(categories) FROM DeletionJobs WHERE job_id = @j AND subject_ref = @s",
                {"j": job_id, "s": subject})
        if not rows:
            raise ReadError(404, "not_found")
        scope, categories, state, requested, completed, raw, size, count = rows[0]
        if count > 100 or size and size > JSON_LIMIT:
            raise ReadError(503, "stored_data_unavailable")
        # Do not relay arbitrary handler/provider error text, internal URLs,
        # subject references or unrecognized keys from historical receipts.
        receipt = _json(raw)
        outcomes = {}
        if receipt is not None:
            if not isinstance(receipt, dict) or not isinstance(receipt.get("categories"), dict):
                raise ReadError(503, "stored_data_unavailable")
            for category in categories:
                outcome = receipt["categories"].get(category)
                if not isinstance(outcome, dict) or outcome.get("status") not in (
                    "pending_records", "pending_derived", "exception", "not_erasable", "retained", "deleted",
                ):
                    raise ReadError(503, "stored_data_unavailable")
                counts = {k: outcome.get(k) for k in ("rows_affected", "derived_purged")}
                if any(v is not None and (type(v) is not int or v < 0) for v in counts.values()):
                    raise ReadError(503, "stored_data_unavailable")
                outcomes[category] = {"status": outcome["status"],
                                      **{k: str(v) if v is not None else None for k, v in counts.items()}}
        return {"job_id": job_id, "environment": self.config.environment, "scope": scope, "state": state,
                "categories": list(categories), "requested_at": _iso(requested), "completed_at": _iso(completed),
                "outcomes": outcomes if receipt is not None else None}
