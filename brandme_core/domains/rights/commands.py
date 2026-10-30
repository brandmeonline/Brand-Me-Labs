"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Authenticated rights commands (round 03 build step 2): transfer intents,
recipient binding, reprint quotes and ownership-proof challenges.

The member's wallet proves and submits. Nothing here holds a witness, a wallet
seed or a prover. A command authorizes the member against finalized
projections, fixes the terms the wallet must prove, and commits the workflow
row, its event and the idempotency record in one transaction
(``run_idempotent_command``). A projection is evidence of past chain state, not
of current control: the contract re-checks control, epoch and recipient when
the proof lands (brandme-chain/contracts/src/brandme_rights.compact:300-367).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP, JsonObject, param_types as pt

from brandme_core.domains import CommandContext, DomainError, NotFound, Principal, canonical_digest, run_idempotent_command
from brandme_core.domains.events import OWNERSHIP_TRANSFER_REQUESTED
from brandme_core.domains.privacy.deletion import ProcessingFrozenError, assert_processing_allowed

RIGHTS = ("display", "transfer", "personal_manufacture", "repair_parts", "commercial_reproduction")
TERMS_SCHEMA = "brandme.transfer-terms/v1"
AUDIENCE_DOMAIN = b"brandme.ownership.audience/v1\x00"
#: States in which an intent still holds the entitlement (spec 04 §5 state machine).
OPEN = ("Draft", "AwaitingRecipient", "ReadyToProve", "Proving", "Submitted", "Reconciling", "Observed")
#: States from which a recipient may still be bound.
UNBOUND = ("AwaitingRecipient",)
NETWORKS = ("undeployed", "preview", "preprod")

_HEX32 = re.compile(r"[0-9a-f]{64}")
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
# 43+ base64url characters carry at least 256 bits; the invite is a bearer secret.
_INVITE = re.compile(r"[A-Za-z0-9_-]{43,128}")
_TERRITORY = re.compile(r"[A-Z]{2}")


class RightsCommandError(DomainError):
    """A refused command with its HTTP status; ``code`` is the public reason."""

    def __init__(self, status: int, code: str, detail: Optional[str] = None):
        super().__init__(detail or code, code=code)
        self.status = status


@dataclass(frozen=True)
class ChainScope:
    """The one network and contract this deployment serves (never Mainnet)."""

    network: str
    contract_address: str

    def __post_init__(self) -> None:
        if self.network not in NETWORKS or not _HEX32.fullmatch(self.contract_address):
            raise ValueError("explicit test network and contract scope required")


def member_context(subject: str, scopes: frozenset[str], environment: str) -> CommandContext:
    """A first-party member principal resolved by the gateway (never a delegated agent)."""
    principal = Principal(member_id=subject, subject=subject, session_id=None, client_id=None, scopes=scopes,
                          assurance_level="gateway_verified", environment=environment)
    return CommandContext(principal=principal, environment=environment)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _invalid(field: str) -> RightsCommandError:
    return RightsCommandError(400, "invalid_request", f"invalid {field}")


def _strict_keys(body: Any, required: set[str], optional: set[str] = frozenset()) -> Mapping[str, Any]:
    if not isinstance(body, Mapping) or not required <= set(body) or set(body) - required - optional:
        raise _invalid("fields")
    return body


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _rows(reader: Any, sql: str, params: Mapping[str, Any], types: Mapping[str, Any]) -> list[list[Any]]:
    return [list(r) for r in reader.execute_sql(sql, params=dict(params), param_types=dict(types))]


def assert_serving(reader: Any) -> None:
    # Same barrier as MyDataService.assert_serving, read in the command's own transaction.
    if _rows(reader, "SELECT restore_id FROM RestoreRuns WHERE state NOT IN ('tombstones_reapplied', 'serving') LIMIT 1", {}, {}):
        raise RightsCommandError(503, "restore_in_progress")


def _controlled(reader: Any, scope: ChainScope, subject: str, *, asset_id: Optional[str] = None,
                entitlement_id: Optional[str] = None) -> list[Any]:
    """The one active entitlement the member controls, or NotFound (existence never leaks)."""
    where, params, types = ("asset_id = @key", {"key": asset_id}, {"key": pt.STRING}) if asset_id else \
        ("entitlement_id = @key", {"key": entitlement_id}, {"key": pt.STRING})
    rows = _rows(reader, "SELECT entitlement_id, epoch, transferable, reprintable FROM RightsEntitlements "
                         f"WHERE network = @n AND contract_address = @c AND {where} AND status = 'active' "
                         "AND controller_subject_ref = @s LIMIT 2",
                 {"n": scope.network, "c": scope.contract_address, "s": subject, **params},
                 {"n": pt.STRING, "c": pt.STRING, "s": pt.STRING, **types})
    if not rows:
        raise NotFound("resource not found")
    if len(rows) > 1:
        # Owner access already requires exactly one active link (read_api/README.md, "Read boundaries").
        raise RightsCommandError(409, "ambiguous_entitlement")
    return rows[0]


# ------------------------------------------------------------------ transfers

def terms_digest(rights_scope: list[str], documents: list[str]) -> str:
    """The offer's termsDigest: the agreed rights and documents, canonically encoded."""
    return canonical_digest({"schema": TERMS_SCHEMA, "rights_scope": rights_scope, "include_documents": documents})


def _transfer_request(body: Any) -> dict[str, Any]:
    b = _strict_keys(body, {"rights_scope", "recipient_invite", "expires_in_seconds"}, {"include_documents"})
    scope, docs, ttl = b["rights_scope"], b.get("include_documents", []), b["expires_in_seconds"]
    if not isinstance(scope, list) or not scope or any(r not in RIGHTS for r in scope) or len(set(scope)) != len(scope):
        raise _invalid("rights_scope")
    if not isinstance(b["recipient_invite"], str) or not _INVITE.fullmatch(b["recipient_invite"]):
        raise _invalid("recipient_invite")
    if type(ttl) is not int or not 300 <= ttl <= 7 * 24 * 3600:
        raise _invalid("expires_in_seconds")
    if (not isinstance(docs, list) or len(docs) > 20 or len(set(docs)) != len(docs)
            or any(not isinstance(d, str) or not _UUID.fullmatch(d) for d in docs)):
        raise _invalid("include_documents")
    return {"rights_scope": sorted(scope), "include_documents": sorted(docs), "expires_in_seconds": ttl,
            "invite_digest": _digest(b["recipient_invite"])}


def create_transfer(database: Any, ctx: CommandContext, scope: ChainScope, asset_id: str, body: Any,
                    idempotency_key: str, *, now: Optional[datetime] = None) -> tuple[dict, bool]:
    """Offer a controlled, transferable entitlement to whoever holds the invite.

    The intent waits for the recipient (``AwaitingRecipient``). It holds the
    entitlement: a second open intent for it is refused until this one ends.
    """
    if not _UUID.fullmatch(asset_id):
        raise _invalid("asset_id")
    request = _transfer_request(body)  # the raw invite never enters a stored value
    subject = ctx.principal.member_id

    def fn(txn: Any, ctx: CommandContext) -> dict:
        at = now or _now()
        assert_serving(txn)
        assert_processing_allowed(txn, subject, "rights.transfers", at)
        entitlement_id, epoch, transferable, _ = _controlled(txn, scope, subject, asset_id=asset_id)
        if not transferable:
            raise RightsCommandError(422, "not_transferable")
        if _rows(txn, "SELECT intent_id FROM TransferIntents WHERE network = @n AND entitlement_id = @e "
                      "AND state IN UNNEST(@open) AND expires_at > @t LIMIT 1",
                 {"n": scope.network, "e": entitlement_id, "open": list(OPEN), "t": at},
                 {"n": pt.STRING, "e": pt.STRING, "open": pt.Array(pt.STRING), "t": pt.TIMESTAMP}):
            raise RightsCommandError(409, "transfer_in_progress")
        intent_id, nonce = str(uuid.uuid4()), secrets.token_hex(32)
        expires = at + timedelta(seconds=request["expires_in_seconds"])
        digest = terms_digest(request["rights_scope"], request["include_documents"])
        txn.insert("TransferIntents",
                   ["intent_id", "network", "contract_address", "entitlement_id", "from_subject_ref", "rights_scope_json",
                    "expected_epoch", "invite_digest", "offer_nonce", "terms_digest", "state", "expires_at", "created_at",
                    "updated_at"],
                   [[intent_id, scope.network, scope.contract_address, entitlement_id, subject,
                     JsonObject({"rights_scope": request["rights_scope"], "include_documents": request["include_documents"]}),
                     epoch, request["invite_digest"], nonce, digest, "AwaitingRecipient", expires, at, COMMIT_TIMESTAMP]])
        ctx.emit(OWNERSHIP_TRANSFER_REQUESTED.event_type, "1", "transfer_intent", intent_id, 1,
                 {"intent_id": intent_id, "network": scope.network, "entitlement_id": entitlement_id}, "member_private")
        return _intent_view({"intent_id": intent_id, "network": scope.network, "contract_address": scope.contract_address,
                             "entitlement_id": entitlement_id, "expected_epoch": epoch, "state": "AwaitingRecipient",
                             "expires_at": expires, "terms_digest": digest, "offer_nonce": nonce,
                             "rights_scope": request["rights_scope"], "include_documents": request["include_documents"],
                             "recipient_commitment": None}, role="sender", now=at)

    return run_idempotent_command(database, ctx, "rights.transfer.create", idempotency_key,
                                  {"asset_id": asset_id, **request, "network": scope.network,
                                   "contract_address": scope.contract_address}, fn)


def accept_transfer(database: Any, ctx: CommandContext, scope: ChainScope, intent_id: str, body: Any,
                    idempotency_key: str, *, now: Optional[datetime] = None) -> tuple[dict, bool]:
    """Bind the recipient's commitment (computed by their wallet for the next epoch).

    This is the first half of acceptance: the sender can now prove the offer.
    The transfer becomes final only when the recipient's ``acceptTransfer``
    proof is observed and finalized on chain.
    """
    if not _UUID.fullmatch(intent_id):
        raise _invalid("intent_id")
    b = _strict_keys(body, {"recipient_invite", "recipient_commitment"})
    commitment = b["recipient_commitment"]
    if not isinstance(b["recipient_invite"], str) or not _INVITE.fullmatch(b["recipient_invite"]):
        raise _invalid("recipient_invite")
    if not isinstance(commitment, str) or not _HEX32.fullmatch(commitment) or commitment == "0" * 64:
        raise _invalid("recipient_commitment")  # the contract also rejects the default commitment
    invite = _digest(b["recipient_invite"])
    subject = ctx.principal.member_id

    def fn(txn: Any, ctx: CommandContext) -> dict:
        at = now or _now()
        assert_serving(txn)
        rows = _rows(txn, "SELECT from_subject_ref, entitlement_id, expected_epoch, state, expires_at, invite_digest, "
                          "offer_nonce, terms_digest, rights_scope_json FROM TransferIntents "
                          "WHERE intent_id = @i AND network = @n AND contract_address = @c",
                     {"i": intent_id, "n": scope.network, "c": scope.contract_address},
                     {"i": pt.STRING, "n": pt.STRING, "c": pt.STRING})
        # A wrong invite and a missing intent are indistinguishable.
        if not rows or not rows[0][5] or not hmac.compare_digest(rows[0][5], invite):
            raise NotFound("resource not found")
        sender, entitlement_id, epoch, state, expires, _, nonce, digest, terms = rows[0]
        if sender == subject:
            raise RightsCommandError(409, "recipient_is_sender")
        if state not in UNBOUND:
            raise RightsCommandError(409, "invalid_transition")
        if expires <= at:
            raise RightsCommandError(410, "transfer_expired")
        # Both members' data is processed here. The sender's restriction is not the
        # recipient's to learn, so it reads as an intent that can no longer be accepted.
        assert_processing_allowed(txn, subject, "rights.transfers", at)
        try:
            assert_processing_allowed(txn, sender, "rights.transfers", at)
        except ProcessingFrozenError:
            raise RightsCommandError(409, "invalid_transition") from None
        current = _rows(txn, "SELECT epoch FROM RightsEntitlements WHERE network = @n AND contract_address = @c "
                             "AND entitlement_id = @e AND status = 'active' AND controller_subject_ref = @s",
                        {"n": scope.network, "c": scope.contract_address, "e": entitlement_id, "s": sender},
                        {"n": pt.STRING, "c": pt.STRING, "e": pt.STRING, "s": pt.STRING})
        if not current or current[0][0] != epoch:
            raise RightsCommandError(409, "stale_intent")
        txn.update("TransferIntents", ["intent_id", "recipient_commitment", "recipient_subject_ref", "state", "updated_at"],
                   [[intent_id, commitment, subject, "ReadyToProve", COMMIT_TIMESTAMP]])
        return _intent_view({"intent_id": intent_id, "network": scope.network, "contract_address": scope.contract_address,
                             "entitlement_id": entitlement_id, "expected_epoch": epoch, "state": "ReadyToProve",
                             "expires_at": expires, "terms_digest": digest, "offer_nonce": nonce,
                             **_terms(terms), "recipient_commitment": commitment}, role="recipient", now=at)

    return run_idempotent_command(database, ctx, "rights.transfer.accept", idempotency_key,
                                  {"intent_id": intent_id, "invite_digest": invite, "recipient_commitment": commitment,
                                   "network": scope.network, "contract_address": scope.contract_address}, fn)


def transfer_status(database: Any, scope: ChainScope, subject: str, intent_id: str, *,
                    now: Optional[datetime] = None) -> dict:
    """The sender's or recipient's view of an intent; anyone else gets NotFound."""
    if not _UUID.fullmatch(intent_id):
        raise _invalid("intent_id")
    with database.snapshot(multi_use=True) as snap:
        assert_serving(snap)
        rows = _rows(snap, "SELECT from_subject_ref, recipient_subject_ref, entitlement_id, expected_epoch, state, expires_at, "
                           "offer_nonce, terms_digest, rights_scope_json, recipient_commitment FROM TransferIntents "
                           "WHERE intent_id = @i AND network = @n AND contract_address = @c "
                           "AND (from_subject_ref = @s OR recipient_subject_ref = @s)",
                     {"i": intent_id, "n": scope.network, "c": scope.contract_address, "s": subject},
                     {"i": pt.STRING, "n": pt.STRING, "c": pt.STRING, "s": pt.STRING})
    if not rows:
        raise NotFound("resource not found")
    sender, _, entitlement_id, epoch, state, expires, nonce, digest, terms, commitment = rows[0]
    return _intent_view({"intent_id": intent_id, "network": scope.network, "contract_address": scope.contract_address,
                         "entitlement_id": entitlement_id, "expected_epoch": epoch, "state": state, "expires_at": expires,
                         "terms_digest": digest, "offer_nonce": nonce, **_terms(terms), "recipient_commitment": commitment},
                        role="sender" if sender == subject else "recipient", now=now or _now())


def _terms(raw: Any) -> dict[str, list[str]]:
    terms = raw if isinstance(raw, dict) else json.loads(raw.serialize() if hasattr(raw, "serialize") else str(raw))
    return {"rights_scope": list(terms["rights_scope"]), "include_documents": list(terms.get("include_documents", []))}


def _intent_view(i: Mapping[str, Any], *, role: str, now: datetime) -> dict:
    """JSON-safe view: no subject references, no invite. Int64 values are decimal strings."""
    state = i["state"]
    if state in ("Draft", "AwaitingRecipient", "ReadyToProve") and i["expires_at"] <= now:
        state = "Expired"  # nothing has been proven yet, so expiry needs no write
    view = {k: i[k] for k in ("intent_id", "network", "contract_address", "entitlement_id", "terms_digest",
                              "rights_scope", "include_documents")}
    view.update(state=state, role=role, expected_epoch=str(i["expected_epoch"]), expires_at=i["expires_at"].isoformat(),
                proving=None)
    if state == "ReadyToProve" and role == "sender":
        # Exactly the arguments the sender's wallet proves locally; the wallet adds the witnesses.
        view["proving"] = {"circuit": "offerTransfer", "entitlement_id": i["entitlement_id"], "nonce": i["offer_nonce"],
                           "recipient_commitment": i["recipient_commitment"],
                           "expiry": str(int(i["expires_at"].timestamp())), "terms_digest": i["terms_digest"]}
    return view


# --------------------------------------------------------------- reprints

def reprint_quote(database: Any, scope: ChainScope, subject: str, asset_id: str, body: Any, *,
                  now: Optional[datetime] = None) -> dict:
    """Eligibility for a personal reprint, or the conditions still missing.

    Read-only: browsing never reserves or consumes quota. The quota shown is a
    projection; the contract's allowance is the authority when rights are consumed.
    """
    if not _UUID.fullmatch(asset_id):
        raise _invalid("asset_id")
    b = _strict_keys(body, {"quantity", "manufacturer_id", "territory"}, {"modifications"})
    quantity, manufacturer, territory = b["quantity"], b["manufacturer_id"], b["territory"]
    if type(quantity) is not int or not 1 <= quantity <= 100:
        raise _invalid("quantity")
    if not isinstance(manufacturer, str) or not _HEX32.fullmatch(manufacturer):
        raise _invalid("manufacturer_id")
    if not isinstance(territory, str) or not _TERRITORY.fullmatch(territory):
        raise _invalid("territory")
    mods = b.get("modifications", {})
    if (not isinstance(mods, Mapping) or len(mods) > 20
            or any(not isinstance(k, str) or not isinstance(v, str) or len(k) > 64 or len(v) > 256 for k, v in mods.items())):
        raise _invalid("modifications")
    at = now or _now()
    missing: list[str] = []
    with database.snapshot(multi_use=True) as snap:
        assert_serving(snap)
        entitlement_id, _, _, reprintable = _controlled(snap, scope, subject, asset_id=asset_id)
        if not reprintable:
            missing.append("entitlement_not_reprintable")
        licenses = _rows(snap, "SELECT issuer_id, territory, allowance_id, quota_granted, valid_until FROM LicenseGrants "
                               "WHERE network = @n AND entitlement_id = @e AND 'personal_manufacture' IN UNNEST(permissions) "
                               "AND allowance_id IS NOT NULL AND (valid_until IS NULL OR valid_until > @t) "
                               "ORDER BY created_at DESC, license_id LIMIT 1",
                         {"n": scope.network, "e": entitlement_id, "t": at}, {"n": pt.STRING, "e": pt.STRING, "t": pt.TIMESTAMP})
        allowance = remaining = valid_until = None
        if not licenses:
            missing.append("license_missing")
        else:
            issuer, territories, allowance, granted, valid_until = licenses[0]
            if territories and territory not in territories:
                missing.append("territory_not_licensed")
            used = _rows(snap, "SELECT COALESCE(SUM(quantity), 0) FROM ReprintJobs WHERE network = @n AND allowance_id = @a "
                               "AND state NOT IN ('cancelled', 'failed')",
                         {"n": scope.network, "a": allowance}, {"n": pt.STRING, "a": pt.STRING})[0][0]
            remaining = max((granted or 0) - used, 0)
            if quantity > remaining:
                missing.append("quota_exceeded")
            capable = _rows(snap, "SELECT 1 FROM ManufacturerCapabilities WHERE manufacturer_id = @m AND issuer_id = @i "
                                  "AND active AND @t IN UNNEST(territories)",
                            {"m": manufacturer, "i": issuer, "t": territory}, {"m": pt.STRING, "i": pt.STRING, "t": pt.STRING})
            if not capable:
                missing.append("manufacturer_not_capable")
    return {
        "eligible": not missing,
        "missing": missing,
        "entitlement_id": entitlement_id,
        "network": scope.network,
        "quantity": str(quantity),
        "territory": territory,
        "manufacturer_id": manufacturer,
        "allowance_id": allowance,
        "quota_remaining": None if remaining is None else str(remaining),
        "license_valid_until": valid_until.isoformat() if valid_until else None,
        # No price source exists yet; a quote never invents one.
        "price": None,
        "price_status": "unavailable",
    }


# ------------------------------------------------------------- challenges

def audience_digest(audience: str) -> str:
    """The ``audience`` argument of proveControl, shared by the wallet and the verifier."""
    return hashlib.sha256(AUDIENCE_DOMAIN + audience.encode()).hexdigest()


def authorize_challenge(database: Any, scope: ChainScope, subject: str, body: Any, *,
                        now: Optional[datetime] = None) -> dict:
    """Confirm the member may prove control for this challenge; nothing is stored.

    Single use is enforced by the contract, which records the challenge key
    for (entitlement, epoch, challenge, audience) when the proof lands.
    """
    b = _strict_keys(body, {"entitlement_id", "audience", "challenge", "ttl_seconds"})
    if not isinstance(b["entitlement_id"], str) or not _HEX32.fullmatch(b["entitlement_id"]):
        raise _invalid("entitlement_id")
    if not isinstance(b["audience"], str) or not 1 <= len(b["audience"]) <= 128:
        raise _invalid("audience")
    if not isinstance(b["challenge"], str) or not _HEX32.fullmatch(b["challenge"]):
        raise _invalid("challenge")
    if type(b["ttl_seconds"]) is not int or not 60 <= b["ttl_seconds"] <= 600:
        raise _invalid("ttl_seconds")
    with database.snapshot(multi_use=True) as snap:
        assert_serving(snap)
        entitlement_id, epoch, _, _ = _controlled(snap, scope, subject, entitlement_id=b["entitlement_id"])
    return {"entitlement_id": entitlement_id, "expected_epoch": str(epoch), "audience_digest": audience_digest(b["audience"]),
            "expires_at": ((now or _now()) + timedelta(seconds=b["ttl_seconds"])).isoformat()}
