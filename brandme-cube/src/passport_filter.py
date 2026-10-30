"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Field-level passport filtering (ch.04 §6), applied after the per-face policy
decision. Face-level ALLOW is necessary but not sufficient: nested owner
references, valuation and private evidence are stripped unless the viewer
is the owner, and chain references are only passed through when they are
real observed evidence.

Consumers outside the cube read the claim-level API instead
(brandme_core.domains.rights.passport, `brandme.passport.claims/v1`).
"""

from __future__ import annotations

import re
from typing import Any, Optional

#: Keys that identify or describe the current/previous owner, or private value data.
OWNER_ONLY_KEYS = frozenset({
    "owner_id", "current_owner_id", "previous_owner_id", "owner_handle", "owner_email", "ownership_history",
    "acquired_at", "purchase_price", "price_history", "current_valuation", "valuation", "receipt", "receipt_ref",
    "shipping_address", "controller_subject_ref", "wallet_address", "personal_notes",
})

#: Chain references produced by the removed stubs/simulators. Never shown as evidence.
_FABRICATED_TX = re.compile(r"^(cardano_tx_|simulated_|encrypted_|stub_|mock_|fake_)", re.IGNORECASE)


def is_observed_chain_ref(tx: Optional[str]) -> bool:
    return bool(tx) and not _FABRICATED_TX.match(tx) and bool(re.fullmatch(r"(0x)?[0-9a-fA-F]{64}", tx))


def filter_face_data(data: Any, viewer_is_owner: bool) -> Any:
    """Recursively drop owner-only keys for non-owners. Owners see their own data."""
    if viewer_is_owner:
        return data
    if isinstance(data, dict):
        return {k: filter_face_data(v, False) for k, v in data.items() if k not in OWNER_ONLY_KEYS}
    if isinstance(data, list):
        return [filter_face_data(v, False) for v in data]
    return data


def chain_ref_for_display(tx: Optional[str]) -> Optional[str]:
    return tx if is_observed_chain_ref(tx) else None
