"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Claim-level passport read API v1 (ch.04 §6) — the versioned interface other
lanes consume. Each statement is separate (product identified, tag verified,
issuer recognized, entitlement controlled, ownership claim reviewed,
lifecycle attested) with its own source, time, environment, network and
expiry/revocation. There is no single "authentic" flag.

Visibility is filtered on the server per claim: ``public`` claims for anyone,
``owner`` claims only for the current controller, ``private`` only for the
subject who supplied them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from google.cloud.spanner_v1 import param_types as pt
from google.cloud.spanner_v1.database import Database

API_VERSION = "brandme.passport.claims/v1"

Viewer = Literal["public", "owner", "supplier"]

WHAT_THIS_MEANS = {
    "product_identified": "This product was matched to a catalog or issuer record.",
    "tag_verified": "A secure tag authentication succeeded under the issuer's policy. It does not prove the tag was never moved.",
    "issuer_recognized": "The issuer that made these claims is registered and was active at the time.",
    "entitlement_controlled": "Someone proved control of this digital entitlement. It does not prove physical possession.",
    "ownership_claim_reviewed": "An ownership claim was reviewed by the named reviewer.",
    "lifecycle_attested": "A named party attested a lifecycle event (repair, reprint, recycling).",
    "esg_claim": "An environmental or social claim with the stated method, unit and uncertainty.",
}


def read_claims(db: Database, asset_id: str, viewer: Viewer, *, at: Optional[datetime] = None,
                facet: Optional[str] = None) -> dict[str, Any]:
    at = at or datetime.now(timezone.utc)
    allowed = {"public": ["public"], "owner": ["public", "owner"], "supplier": ["public", "owner", "private"]}[viewer]
    sql = ("SELECT claim_id, facet, claim_type, assurance, source, environment, network, evidence_ref, visibility, "
           "value_json, observed_at, expires_at, revoked_at FROM PassportClaims WHERE asset_id = @a AND visibility IN UNNEST(@v)")
    params: dict[str, Any] = {"a": asset_id, "v": allowed}
    types: dict[str, Any] = {"a": pt.STRING, "v": pt.Array(pt.STRING)}
    if facet:
        sql += " AND facet = @f"
        params["f"], types["f"] = facet, pt.STRING
    with db.snapshot() as s:
        rows = list(s.execute_sql(sql + " ORDER BY observed_at", params=params, param_types=types))
    statements = []
    for r in rows:
        expires, revoked = r[11], r[12]
        state = "revoked" if revoked else "expired" if (expires and expires <= at) else "current"
        statements.append({
            "claim_id": r[0], "facet": r[1], "statement": r[2], "assurance": r[3], "source": r[4],
            "environment": r[5], "network": r[6], "test_network": r[6] in ("undeployed", "preview", "preprod"),
            "evidence_ref": r[7] if viewer != "public" or r[8] == "public" else None,
            "value": r[9], "observed_at": r[10].isoformat(), "expires_at": expires.isoformat() if expires else None,
            "state": state, "what_this_means": WHAT_THIS_MEANS.get(r[2], ""),
        })
    return {"api": API_VERSION, "asset_id": asset_id, "viewer": viewer, "statements": statements}
