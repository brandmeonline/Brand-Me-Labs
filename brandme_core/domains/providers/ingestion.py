"""Catalog ingestion, normalization, freshness and media rights (ch.05 §2; BM-PROV-004/005/006).

* Dedupe key is ``(provider, merchant, source_product_id, source_variant_id)``;
  replaying a page or a whole cursor range never duplicates variants.
* Tombstones mark variants discontinued and invalidate their offers.
* Prices from feeds are *observations*: they carry ``checked_at`` and a
  freshness label, and checkout always requires a fresh provider quote.
* Media transformations are allowed only when the source rights grant them.
* A shelf limit (``max_active_listings``, a partner tier's quota applied by
  ``ProviderSetupService.load_shelf_page``) refuses each addition beyond it under the same lock as the
  write. Updates to loaded variants and tombstones are never refused, a page's own tombstones free their
  slots for its additions, and a lower limit deletes nothing.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Dict, List, Mapping, Optional, Tuple

from .contracts import CatalogPage, SourceVariant

DESCRIPTIVE_FRESHNESS = timedelta(hours=24)
AVAILABILITY_FRESHNESS = timedelta(minutes=15)

VariantKey = Tuple[str, str, str, str]


def variant_key(v: SourceVariant) -> VariantKey:
    return (v.provider_id, v.merchant_id, v.source_product_id, v.source_variant_id)


@dataclass(frozen=True)
class StoredVariant:
    variant: SourceVariant
    revision: int
    first_seen_at: datetime
    last_ingested_at: datetime
    tombstoned: bool = False


@dataclass
class IngestionAudit:
    run_id: str
    provider_id: str
    accepted: int = 0
    unchanged: int = 0
    rejected: int = 0
    tombstoned: int = 0
    rejections: List[str] = field(default_factory=list)
    final_cursor: Optional[str] = None
    new_listings: int = 0  # additions to the shelf (a revived tombstone counts)
    quota_refused: int = 0  # additions refused by the shelf limit (also counted in ``rejected``)
    admitted_refs: List[str] = field(default_factory=list)  # source variant ids added to the shelf


@dataclass
class ShelfCounts:
    """One ``ingest_page`` call's own additions and quota refusals (an audit may span pages and threads)."""
    added: int = 0
    refused: int = 0


class CatalogIngestor:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.variants: Dict[VariantKey, StoredVariant] = {}
        self.cursors: Dict[str, Optional[str]] = {}

    def shelf_usage(self, provider_id: str) -> int:
        """Active (non-tombstoned) variants on this connection's shelf."""
        with self._lock:
            return sum(1 for k, sv in self.variants.items() if k[0] == provider_id and not sv.tombstoned)

    def ingest_page(self, page: CatalogPage, *, provider_id: str, now: datetime,
                    audit: IngestionAudit, max_active_listings: Optional[int] = None,
                    counts: Optional[ShelfCounts] = None) -> None:
        limit = max_active_listings
        if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 0):
            raise ValueError("max_active_listings must be a non-negative int or None")
        counts = counts if counts is not None else ShelfCounts()
        with self._lock:
            # The page's own tombstones free their slots for the page's additions: a page that swaps one
            # listing for another stays within the limit it was already at.
            removed = set(page.tombstones)
            active = sum(1 for k, sv in self.variants.items()
                         if k[0] == provider_id and not sv.tombstoned and (k[2], k[3]) not in removed)
            for v in page.items:
                problem = _validate(v, provider_id)
                if problem:
                    audit.rejected += 1
                    audit.rejections.append(f"{v.source_variant_id}:{problem}")
                    continue
                key = variant_key(v)
                prev = self.variants.get(key)
                if prev is not None and prev.tombstoned and v.source_updated_at <= prev.last_ingested_at:
                    audit.unchanged += 1  # a replayed page never resurrects a deleted variant
                    continue
                if prev is not None and prev.variant == v and not prev.tombstoned:
                    audit.unchanged += 1
                    continue
                if prev is not None and v.source_updated_at < prev.variant.source_updated_at:
                    audit.unchanged += 1  # out-of-order older record never overwrites newer data
                    continue
                if prev is None or prev.tombstoned:  # an addition to the shelf
                    if limit is not None and active >= limit:
                        audit.rejected += 1
                        audit.quota_refused += 1
                        counts.refused += 1
                        audit.rejections.append(f"{v.source_variant_id}:shelf_quota_exceeded")
                        continue
                    active += 1
                    audit.new_listings += 1
                    counts.added += 1
                    audit.admitted_refs.append(v.source_variant_id)
                self.variants[key] = StoredVariant(
                    v, (prev.revision + 1) if prev else 1, prev.first_seen_at if prev else now, now, False)
                audit.accepted += 1
            for (pid, vid) in page.tombstones:
                for key, sv in list(self.variants.items()):
                    if key[0] == provider_id and key[2] == pid and key[3] == vid and not sv.tombstoned:
                        self.variants[key] = replace(sv, tombstoned=True, revision=sv.revision + 1,
                                                     variant=replace(sv.variant, availability="discontinued"),
                                                     last_ingested_at=now)
                        audit.tombstoned += 1
            self.cursors[provider_id] = page.next_cursor
            audit.final_cursor = page.next_cursor

    def offers(self, provider_id: str) -> List[SourceVariant]:
        return [sv.variant for k, sv in self.variants.items() if k[0] == provider_id and not sv.tombstoned]


def _validate(v: SourceVariant, provider_id: str) -> Optional[str]:
    if v.provider_id != provider_id:
        return "provider_mismatch"
    if not v.source_product_id or not v.source_variant_id:
        return "missing_source_ids"
    if not v.product_url.startswith("https://"):
        return "non_https_product_url"
    if v.price is not None and v.price.amount_minor <= 0:
        return "non_positive_price"
    return None


@dataclass(frozen=True)
class FreshnessLabel:
    state: str  # fresh | stale | unknown
    checked_at: Optional[datetime]
    message: str
    price_is_quote: bool = False  # a feed price is never a purchasable quote


def price_freshness(v: SourceVariant, now: datetime) -> FreshnessLabel:
    if v.price is None:
        return FreshnessLabel("unknown", None, "Price available at the retailer")
    age = now - v.source_updated_at
    if age > DESCRIPTIVE_FRESHNESS:
        return FreshnessLabel("stale", v.source_updated_at,
                              "Price last checked earlier — final price is confirmed at checkout")
    return FreshnessLabel("fresh", v.source_updated_at, "Price last checked recently; confirmed at checkout")


MEDIA_TRANSFORMS = {
    "display": "display_images",
    "cache": "cache_images",
    "resize": "transform_images",
    "background_removal": "transform_images",
    "derive_3d": "derive_3d_or_ai",
    "ai_tryon_input": "derive_3d_or_ai",
}


class MediaRightsDenied(PermissionError):
    pass


def authorize_media_transform(transform: str, data_use: Mapping[str, bool]) -> str:
    """Returns the right used, or raises. Unknown transforms are denied."""
    right = MEDIA_TRANSFORMS.get(transform)
    if right is None or not data_use.get(right, False):
        raise MediaRightsDenied(f"{transform} not permitted by source rights; show the original or a placeholder")
    return right
