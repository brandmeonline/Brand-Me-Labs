"""
Home = Flow (Ultra plan 02, item 3).

* **Position is freshness.** Nothing reorders it. Friends' open Now requests
  addressed to the member cut in first, soonest-closing first, while their
  window is open. After them come the newest pieces from the member's houses
  (followed, or the houses of pieces they own), newest first.
* **Size and depth come from excitement.** Excitement is recent platform
  engagement with the piece (Now decisions about it and want-list adds in the
  last ``ENGAGEMENT_WINDOW``) blended with the member's persona affinity.
  Engagement under ``ENGAGEMENT_FLOOR`` counts as none, so one person's activity
  can never visibly size a piece.
* **The persona lens** drops what the member's hard constraints exclude
  (budget, brands, materials, categories, dismissed pieces). It does not rank.

Each item says why it has its size. Counts are never returned.
"""

from __future__ import annotations

import base64
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from brandme_core.domains.persona.kernel import (
    STR,
    STR_ARRAY,
    TS,
    NotFound,
    Principal,
    ValidationFailed,
    iso,
    parse_iso,
    query,
    require_scope,
    run_read,
    server_now,
)
from brandme_core.domains.persona.recommender import Candidate, lens

from .houses import HouseCatalog, HouseItem, member_houses
from .notifications import blocked_between

ENGAGEMENT_WINDOW = timedelta(days=7)
ENGAGEMENT_FLOOR = 3
ENGAGEMENT_SATURATION = 25
NEUTRAL_AFFINITY = 0.5
SIZES = ((0.75, "hero", 3), (0.4, "standard", 2), (0.0, "compact", 1))
MAX_LIMIT = 48


def excitement(engagement: int, affinity: Optional[float]) -> float:
    eng = 0.0 if engagement < ENGAGEMENT_FLOOR else min(1.0, math.log1p(engagement) / math.log1p(ENGAGEMENT_SATURATION))
    return round(0.6 * eng + 0.4 * (NEUTRAL_AFFINITY if affinity is None else affinity), 4)


def size_for(score: float) -> Tuple[str, int]:
    return next((name, depth) for floor, name, depth in SIZES if score >= floor)


def _cursor(t: datetime, pid: str) -> str:
    return base64.urlsafe_b64encode(f"{iso(t)}|{pid}".encode()).decode().rstrip("=")


def _parse_cursor(raw: Optional[str]) -> Optional[Tuple[datetime, str]]:
    if raw is None:
        return None
    try:
        t, _, pid = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode().partition("|")
        return parse_iso(t, name="cursor"), pid
    except (ValueError, UnicodeDecodeError, ValidationFailed):
        raise ValidationFailed("cursor is not valid", extra={"field": "cursor"}) from None


class FlowService:
    def __init__(self, database, *, catalog: HouseCatalog, persona: Any):
        self.db = database
        self.catalog = catalog
        self.persona = persona

    def _engagement(self, s, product_ids: List[str], now: datetime) -> Dict[str, int]:
        if not product_ids:
            return {}
        since = now - ENGAGEMENT_WINDOW
        out: Dict[str, int] = {}
        for pid, n in query(s, "SELECT subject_id, COUNT(*) FROM Decisions@{FORCE_INDEX=DecisionsBySubject} WHERE subject_type='catalog_product' "
                               "AND subject_id IN UNNEST(@p) AND opened_at >= @t GROUP BY subject_id", {"p": product_ids, "t": since},
                            {"p": STR_ARRAY, "t": TS}):
            out[pid] = out.get(pid, 0) + n
        for pid, n in query(s, "SELECT product_id, COUNT(*) FROM WardrobeItems@{FORCE_INDEX=WardrobeItemsByProduct} WHERE product_id IN UNNEST(@p) "
                               "AND collection='want' AND created_at >= @t GROUP BY product_id", {"p": product_ids, "t": since},
                            {"p": STR_ARRAY, "t": TS}):
            out[pid] = out.get(pid, 0) + n
        return out

    def _requests(self, s, me: str, now: datetime) -> List[Dict[str, Any]]:
        muted = {r[0] for r in query(s, "SELECT muted_member_id FROM MemberMutes WHERE member_id=@m", {"m": me}, {"m": STR})}
        rows = query(s, "SELECT a.member_id, a.decision_id, d.prompt, d.why, d.subject_type, d.subject_id, d.closes_at, d.duration_seconds "
                        "FROM DecisionAudience@{FORCE_INDEX=DecisionAudienceByRecipient} a JOIN Decisions d "
                        "ON d.member_id = a.member_id AND d.decision_id = a.decision_id "
                        "WHERE a.recipient_id=@m AND NOT a.removed AND a.closes_at > @n AND d.state='open' ORDER BY a.closes_at LIMIT 12",
                     {"m": me, "n": now}, {"m": STR, "n": TS})
        out = []
        for creator, did, prompt, why, stype, sid, closes, window in rows:
            if creator in muted or blocked_between(s, me, creator):
                continue
            answered = bool(query(s, "SELECT 1 FROM DecisionResponses WHERE member_id=@c AND decision_id=@d AND respondent_id=@m",
                                  {"c": creator, "d": did, "m": me}, {"c": STR, "d": STR, "m": STR}))
            out.append({"kind": "decision_request", "size": "hero", "depth": 2,
                        "size_reason": "A friend asked you; it closes soon",
                        "decision": {"decision_id": did, "creator_id": creator, "prompt": prompt, "why": why, "subject_type": stype,
                                     "subject_id": sid, "closes_at": iso(closes), "duration_seconds": window,
                                     "remaining_seconds": max(0, int((closes - now).total_seconds())), "answered": answered}})
        return out

    def flow(self, principal: Principal, *, limit: int = 24, cursor: Optional[str] = None) -> Dict[str, Any]:
        """The member's Home: friend requests cutting in, then their houses' newest pieces."""
        require_scope(principal, "social:read")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
            raise ValidationFailed(f"limit must be 1-{MAX_LIMIT}", extra={"field": "limit"})
        before = _parse_cursor(cursor)
        me = principal.member_id

        def read(s):
            now = server_now(s)
            houses = member_houses(s, me, self.catalog)
            requests = self._requests(s, me, now) if before is None else []
            pieces: List[HouseItem] = self.catalog.newest(s, sorted(houses), before=before, limit=limit)
            try:
                req = self.persona.lens_request(s, me)
            except NotFound:
                req = None
            kept = {c.product_id: aff for c, aff in lens([_candidate(p) for p in pieces], req)} if req is not None else \
                {p.product_id: None for p in pieces}
            engagement = self._engagement(s, [p.product_id for p in pieces if p.product_id in kept], now)
            items: List[Dict[str, Any]] = list(requests)
            for p in pieces:
                if p.product_id not in kept:
                    continue
                score = excitement(engagement.get(p.product_id, 0), kept[p.product_id])
                size, depth = size_for(score)
                items.append({"kind": "house_piece", "size": size, "depth": depth, "size_reason": _reason(engagement.get(p.product_id, 0), kept[p.product_id]),
                              "piece": {"product_id": p.product_id, "house_ref": p.house_ref, "house_name": p.house_name, "title": p.title,
                                        "category": p.category, "published_at": iso(p.published_at), "available": p.available,
                                        "observed_price": None if p.price_minor is None else {"minor": p.price_minor, "currency": p.currency,
                                                                                               "label": "Observed price, not a quote"},
                                        "via": houses.get(p.house_ref)}})
            for i, it in enumerate(items, start=1):
                it["position"] = i
            last = pieces[-1] if len(pieces) == limit else None
            return {"items": items, "next_cursor": _cursor(last.published_at, last.product_id) if last else None,
                    "houses": len(houses), "lens_applied": req is not None, "server_time": iso(now)}

        return run_read(self.db, read)


def _candidate(p: HouseItem) -> Candidate:
    # Stock is shown on the piece, not filtered: the lens applies only the member's own constraints.
    return Candidate(product_id=p.product_id, title=p.title, brand=p.house_name, category=p.category or "", color_family="neutral",
                     price_minor=p.price_minor, currency=p.currency, available=True)


def _reason(engagement: int, affinity: Optional[float]) -> str:
    parts = []
    if engagement >= ENGAGEMENT_FLOOR:
        parts.append("members are talking about it")
    if affinity is not None and affinity >= 0.7:
        parts.append("close to your style")
    return ("Larger because " + " and ".join(parts)) if parts else "Newest from your houses"
