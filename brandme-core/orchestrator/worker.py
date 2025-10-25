import json
import os
import uuid
from datetime import datetime as dt
from typing import Dict, List

import psycopg2
import psycopg2.extras

from brandme_core.logging import get_logger, redact_user_id


logger = get_logger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required for orchestrator worker")


def _partial_identifier(value: str) -> str:
    if not value:
        return ""
    return f"{value[:8]}\u2026"


def call_knowledge_service(garment_id: str, scope: str) -> List[Dict[str, object]]:
    redacted_garment = _partial_identifier(garment_id)
    logger.debug(
        "Fetching knowledge facets", extra={"garment_id": redacted_garment, "scope": scope}
    )
    return [
        {
            "facet_type": "ESG",
            "facet_payload_preview": {
                "summary": "Sustainability certified",
                "scope": scope,
            },
        }
    ]


def call_tx_builder(
    scan_id: str, garment_id: str, scope: str, policy_version: str
) -> Dict[str, str]:
    logger.debug(
        "Building transaction hashes",
        extra={
            "scan_id": scan_id,
            "garment_id": _partial_identifier(garment_id),
            "scope": scope,
            "policy_version": policy_version,
        },
    )
    return {
        "cardano_tx_hash": uuid.uuid4().hex[:16],
        "midnight_tx_hash": uuid.uuid4().hex[:16],
        "crosschain_root_hash": uuid.uuid4().hex[:16],
    }


def call_compliance_audit_log(
    scan_id: str,
    decision_summary: str,
    decision_detail: Dict[str, object],
    risk_flagged: bool,
    escalated_to_human: bool,
) -> None:
    logger.debug(
        "Logging compliance audit event",
        extra={
            "scan_id": scan_id,
            "decision_summary": decision_summary,
            "risk_flagged": risk_flagged,
            "escalated_to_human": escalated_to_human,
        },
    )


def call_compliance_anchor_chain(scan_id: str, tx_hashes: Dict[str, str]) -> None:
    logger.debug(
        "Notifying compliance of anchor hashes",
        extra={
            "scan_id": scan_id,
            "cardano_tx_hash": tx_hashes.get("cardano_tx_hash"),
            "midnight_tx_hash": tx_hashes.get("midnight_tx_hash"),
        },
    )


def insert_chain_anchor(conn, scan_id: str, tx_hashes: Dict[str, str]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chain_anchor (
                anchor_id,
                scan_id,
                cardano_tx_hash,
                cardano_payload_ref,
                midnight_tx_hash,
                midnight_payload_ref,
                crosschain_root_hash,
                anchored_at
            ) VALUES (
                uuid_generate_v4(),
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                NOW()
            )
            """,
            (
                scan_id,
                tx_hashes["cardano_tx_hash"],
                "PUBLIC_PROOF_STUB",
                tx_hashes["midnight_tx_hash"],
                "PRIVATE_PROOF_STUB",
                tx_hashes["crosschain_root_hash"],
            ),
        )


def process_allowed_scan(decision_packet: Dict[str, str]) -> Dict[str, object]:
    required_keys = {
        "scan_id",
        "scanner_user_id",
        "garment_id",
        "resolved_scope",
        "policy_version",
        "region_code",
    }
    missing = required_keys - decision_packet.keys()
    if missing:
        raise ValueError(f"decision_packet missing required keys: {', '.join(sorted(missing))}")

    scan_id = decision_packet["scan_id"]
    scanner_user_id = decision_packet["scanner_user_id"]
    garment_id = decision_packet["garment_id"]
    resolved_scope = decision_packet["resolved_scope"]
    policy_version = decision_packet["policy_version"]
    region_code = decision_packet["region_code"]
    occurred_at = decision_packet.get("occurred_at")

    if not occurred_at:
        occurred_at = dt.utcnow().isoformat() + "Z"

    shown_facets = call_knowledge_service(garment_id, resolved_scope)
    tx_hashes = call_tx_builder(scan_id, garment_id, resolved_scope, policy_version)

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scan_event (
                    scan_id,
                    scanner_user_id,
                    garment_id,
                    occurred_at,
                    resolved_scope,
                    policy_version,
                    region_code,
                    shown_facets
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (scan_id) DO NOTHING
                """,
                (
                    scan_id,
                    scanner_user_id,
                    garment_id,
                    occurred_at,
                    resolved_scope,
                    policy_version,
                    region_code,
                    psycopg2.extras.Json(shown_facets),
                ),
            )
        insert_chain_anchor(conn, scan_id, tx_hashes)
        conn.commit()

    decision_summary = f"policy allowed scope {resolved_scope}"
    decision_detail = {
        "policy_version": policy_version,
        "region_code": region_code,
        "resolved_scope": resolved_scope,
        "shown_facets_count": len(shown_facets),
    }
    call_compliance_audit_log(
        scan_id=scan_id,
        decision_summary=decision_summary,
        decision_detail=decision_detail,
        risk_flagged=False,
        escalated_to_human=False,
    )
    call_compliance_anchor_chain(scan_id, tx_hashes)

    logger.info(
        "Processed allowed scan",
        extra={
            "scan_id": scan_id,
            "scanner_user_id": redact_user_id(scanner_user_id),
            "garment_id": _partial_identifier(garment_id),
            "region_code": region_code,
            "shown_facets_count": len(shown_facets),
        },
    )

    return {
        "status": "ok",
        "scan_id": scan_id,
        "shown_facets_count": len(shown_facets),
        "cardano_tx_hash": tx_hashes["cardano_tx_hash"],
        "midnight_tx_hash": tx_hashes["midnight_tx_hash"],
        "crosschain_root_hash": tx_hashes["crosschain_root_hash"],
    }


if __name__ == "__main__":
    demo_packet = {
        "scan_id": str(uuid.uuid4()),
        "scanner_user_id": str(uuid.uuid4()),
        "garment_id": str(uuid.uuid4()),
        "resolved_scope": "public",
        "policy_version": "policy_v1_us-east1",
        "region_code": os.getenv("REGION_DEFAULT", "us-east1"),
        "occurred_at": dt.utcnow().isoformat() + "Z",
    }
    result = process_allowed_scan(demo_packet)
    print(json.dumps(result, indent=2))
