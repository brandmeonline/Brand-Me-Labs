"""Catalog search across registered providers, shared by the MCP tool and the HTTP API.

Results are observations: each item carries provider, freshness, simulation
label and disclosure, and provider text is wrapped as untrusted data. A catalog
price is never a purchasable quote.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from .ingestion import price_freshness
from .registry import ProviderRegistry

UNTRUSTED_TEXT_LIMIT = 2000


def untrusted_text(text: str, origin: str) -> Dict[str, str]:
    """Provider/retrieved text is data: normalized, control chars stripped, length-capped, labeled."""
    clean = "".join(ch for ch in unicodedata.normalize("NFKC", text or "")
                    if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    return {"type": "untrusted_text", "origin": origin, "text": clean[:UNTRUSTED_TEXT_LIMIT]}


def _variant_id(conn, source_variant_ref: str) -> Optional[str]:
    fn = getattr(conn.adapter, "variant_id_for", None)
    return fn(source_variant_ref) if fn is not None else None


def search_catalog(registry: ProviderRegistry, now: datetime, query: str, *,
                   provider_ids: Iterable[str] = (), limit: int = 12) -> Dict[str, Any]:
    wanted = set(provider_ids)
    items, unavailable = [], []
    for conn in registry.all():
        if wanted and conn.provider_id not in wanted:
            continue
        if not conn.can_execute("catalog.search"):
            unavailable.append({"provider_id": conn.provider_id,
                                "reason_code": conn.capability("catalog.search").reason_code,
                                "handoff": conn.capability("checkout.handoff").state})
            continue
        page = conn.adapter.search(query, limit=limit)
        for v in page.items:
            fresh = price_freshness(v, now)
            items.append({
                "provider_id": v.provider_id, "merchant_id": v.merchant_id,
                "source_product_id": v.source_product_id, "source_variant_ref": v.source_variant_id,
                "variant_id": _variant_id(conn, v.source_variant_id),
                "title": untrusted_text(v.title, f"provider:{v.provider_id}"),
                "description": untrusted_text(v.description, f"provider:{v.provider_id}"),
                "category": v.category, "size_label": v.size_label, "availability": v.availability,
                "observed_price": v.price.to_wire() if v.price else None,
                "price_is_quote": False, "price_freshness": fresh.state,
                "checked_at": fresh.checked_at.strftime("%Y-%m-%dT%H:%M:%SZ") if fresh.checked_at else None,
                "simulation": conn.simulation, "disclosure": conn.disclosure,
            })
    return {"items": items, "unavailable_providers": unavailable,
            "note": "Prices are observations; request a checkout quote for purchasable terms."}
