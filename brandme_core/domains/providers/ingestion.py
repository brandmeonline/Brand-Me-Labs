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
  slots for its additions (and a variant the page also tombstones takes none), and a lower limit deletes
  nothing. A page applies whole or not at all.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Tuple

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
        tombstones = _tombstone_pairs(page.tombstones)  # read once; a malformed entry refuses the whole page
        removed = set(tombstones)
        with self._lock:
            # The page applies whole: every write is staged, and nothing is stored, counted or audited until
            # the last record has been processed. A page that fails part-way therefore changes nothing, and can
            # never keep an addition admitted on a slot its unapplied tombstones were to free.
            staged: Dict[VariantKey, StoredVariant] = {}
            delta = IngestionAudit(audit.run_id, audit.provider_id)
            added = refused = 0

            def current(key: VariantKey) -> Optional[StoredVariant]:
                return staged[key] if key in staged else self.variants.get(key)

            # The page's own tombstones free their slots for its additions: a page that swaps one listing for
            # another stays within the limit it was already at.
            active = sum(1 for k, sv in self.variants.items()
                         if k[0] == provider_id and not sv.tombstoned and (k[2], k[3]) not in removed)
            for v in page.items:
                problem = _validate(v, provider_id)
                if problem:
                    delta.rejected += 1
                    delta.rejections.append(f"{v.source_variant_id}:{problem}")
                    continue
                key = variant_key(v)
                prev = current(key)
                if prev is not None and prev.tombstoned and v.source_updated_at <= prev.last_ingested_at:
                    delta.unchanged += 1  # a replayed page never resurrects a deleted variant
                    continue
                if prev is not None and prev.variant == v and not prev.tombstoned:
                    delta.unchanged += 1
                    continue
                if prev is not None and v.source_updated_at < prev.variant.source_updated_at:
                    delta.unchanged += 1  # out-of-order older record never overwrites newer data
                    continue
                # An addition to the shelf, unless this page also tombstones it (it never occupies a slot).
                if (prev is None or prev.tombstoned) and (key[2], key[3]) not in removed:
                    if limit is not None and active >= limit:
                        delta.rejected += 1
                        delta.quota_refused += 1
                        refused += 1
                        delta.rejections.append(f"{v.source_variant_id}:shelf_quota_exceeded")
                        continue
                    active += 1
                    delta.new_listings += 1
                    added += 1
                    delta.admitted_refs.append(v.source_variant_id)
                staged[key] = StoredVariant(
                    v, (prev.revision + 1) if prev else 1, prev.first_seen_at if prev else now, now, False)
                delta.accepted += 1
            keys = set()
            if removed:  # most pages tombstone nothing and skip this scan of the store
                keys = {k for k in self.variants if k[0] == provider_id and (k[2], k[3]) in removed}
                keys |= {k for k in staged if (k[2], k[3]) in removed}  # staged keys are all this provider's
                # A tombstone names no merchant (wire shape [product, variant]). If its ids match variants of
                # more than one merchant at this provider, it is ambiguous: the page is refused rather than
                # discontinuing every merchant's listing. Nothing has been written yet.
                merchants: Dict[Tuple[str, str], set] = {}
                for k in keys:
                    merchants.setdefault((k[2], k[3]), set()).add(k[1])
                if any(len(m) > 1 for m in merchants.values()):
                    raise ValueError("a tombstone matches variants of more than one merchant; tombstones need a "
                                     "merchant to remove one merchant's listing")
            for key in keys:
                sv = current(key)
                if not sv.tombstoned:
                    staged[key] = replace(sv, tombstoned=True, revision=sv.revision + 1,
                                          variant=replace(sv.variant, availability="discontinued"),
                                          last_ingested_at=now)
                    delta.tombstoned += 1
            # Commit the page.
            self.variants.update(staged)
            self.cursors[provider_id] = page.next_cursor
            for name in ("accepted", "unchanged", "rejected", "tombstoned", "new_listings", "quota_refused"):
                setattr(audit, name, getattr(audit, name) + getattr(delta, name))
            audit.rejections.extend(delta.rejections)
            audit.admitted_refs.extend(delta.admitted_refs)
            audit.final_cursor = page.next_cursor
            counts.added += added
            counts.refused += refused

    def offers(self, provider_id: str) -> List[SourceVariant]:
        return [sv.variant for k, sv in self.variants.items() if k[0] == provider_id and not sv.tombstoned]


def _tombstone_pairs(raw: Any) -> Tuple[Tuple[str, str], ...]:
    """A page's tombstones as ``(source_product_id, source_variant_id)`` string pairs, read exactly once (an
    adapter may hand over any iterable, and pairs decoded from JSON arrive as lists)."""
    pairs = []
    for entry in raw or ():
        if not isinstance(entry, (tuple, list)) or len(entry) != 2 \
                or not all(isinstance(part, str) and part for part in entry):
            raise ValueError("each tombstone must be a (source_product_id, source_variant_id) pair of strings")
        pairs.append((entry[0], entry[1]))
    return tuple(pairs)


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
