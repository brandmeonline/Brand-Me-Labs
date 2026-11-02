"""
Per-house loyalty standing (Ultra plan 02, item 4).

* **Computed from platform stats.** Within each house, members are ranked by
  verified, delivered units: order-acquired items the member still owns, with a
  receipt-backed or stronger claim. A member's percentile is the share of that
  house's buyers with strictly more units, so ties share a tier. Tiers are
  ``top_1`` / ``top_5`` / ``top_10`` / ``top_25`` / ``member``.
* **Small cohorts get no ranking.** With fewer than ``MIN_COHORT`` buyers,
  everyone is ``member``, so a tier can never single someone out.
* **Only the tier is stored** (``HouseStandings``); counts are never persisted
  or returned. A member sees their own tiers.
* **Houses see standing only, never raw history.** A house may see a member's
  tier only if the member opted in for that house
  (``MemberHouses.share_standing``). Everyone else is in suppressed per-tier
  counts.
* **Standing gates house rewards.** A benefit with ``house_ref`` and
  ``min_standing`` can be reserved only by a member at or above that tier
  (``benefits.py``).

``recompute`` runs in the jobs process. ``recompute_if_due`` runs it at most
once per ``RECOMPUTE_EVERY``.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional

from google.cloud.spanner_v1 import KeySet

from brandme_core.domains.persona.kernel import (
    INT,
    STR,
    STR_ARRAY,
    Principal,
    processing_allowed,
    query,
    require_scope,
    run_read,
    run_txn,
    server_now,
)
from brandme_core.domains.social.houses import HouseCatalog, require_house_ref

TIERS = (("top_1", 0.01), ("top_5", 0.05), ("top_10", 0.10), ("top_25", 0.25))
TIER_ORDER = ("top_1", "top_5", "top_10", "top_25", "member")
MIN_COHORT = 20
SUPPRESS_BELOW = 5
RECOMPUTE_EVERY = timedelta(hours=24)
VERIFIED_CLAIMS = ("receipt_backed", "tag_verified", "issuer_attested")
_EMPTY_RUNS: Dict[Any, datetime] = {}  # database → server time of this process's last run that stored no tier


def tier_for(rank_above: int, cohort: int, min_cohort: int = MIN_COHORT) -> str:
    """``rank_above`` = buyers with strictly more units than this member."""
    if cohort < min_cohort:
        return "member"
    share = rank_above / cohort
    return next((name for name, cut in TIERS if share < cut), "member")


def tiers_by_rank(by_member: Mapping[str, int], min_cohort: int = MIN_COHORT) -> Dict[str, str]:
    """Every member's tier from one sort. A count's first position in descending order is the
    number of buyers with strictly more units, so equal counts share a rank and a tier."""
    counts = sorted(by_member.values(), reverse=True)
    above: Dict[int, int] = {}
    for i, c in enumerate(counts):
        above.setdefault(c, i)
    return {m: tier_for(above[n], len(counts), min_cohort) for m, n in by_member.items()}


def meets(tier: Optional[str], required: str) -> bool:
    return tier is not None and TIER_ORDER.index(tier) <= TIER_ORDER.index(required)


class StandingService:
    def __init__(self, database, *, catalog: HouseCatalog, min_cohort: int = MIN_COHORT):
        self.db = database
        self.catalog = catalog
        self.min_cohort = min_cohort

    # ---------------------------------------------------------------- compute

    def recompute(self, *, page: int = 5000) -> Dict[str, Any]:
        """Rebuild every house's standings from verified purchases (bounded pages)."""
        units: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        last: Optional[tuple] = None
        while True:
            def read(s, last=last):
                cond = "AND (member_id > @lm OR (member_id = @lm AND item_id > @li)) " if last else ""
                params: Dict[str, Any] = {"c": list(VERIFIED_CLAIMS), "l": page}
                types: Dict[str, Any] = {"c": STR_ARRAY, "l": INT}
                if last:
                    params.update(lm=last[0], li=last[1])
                    types.update(lm=STR, li=STR)
                rows = query(s, "SELECT member_id, item_id, product_id FROM WardrobeItems WHERE acquisition_source='order' AND collection='owned' "
                                f"AND product_id IS NOT NULL AND claim_level IN UNNEST(@c) {cond}ORDER BY member_id, item_id LIMIT @l", params, types)
                return rows, self.catalog.houses_of(s, sorted({r[2] for r in rows}))

            rows, houses = run_read(self.db, read)
            for member_id, _item, product_id in rows:
                house = houses.get(product_id)
                if house:
                    units[house][member_id] += 1
            if len(rows) < page:
                break
            last = (rows[-1][0], rows[-1][1])
        run_id = str(uuid.uuid4())
        written = 0
        for house, by_member in units.items():
            written += self._write_house(house, tiers_by_rank(by_member, self.min_cohort), run_id)
        stale = self._drop_stale(run_id)
        return {"houses": len(units), "standings": written, "removed": stale, "run_id": run_id}

    def _write_house(self, house: str, tiers: Mapping[str, str], run_id: str) -> int:
        n = 0
        items = sorted(tiers.items())
        for start in range(0, len(items), 500):
            chunk = items[start:start + 500]

            def tx(t, chunk=chunk):
                now = server_now(t)
                rows = [(m, house, tier, now, run_id) for m, tier in chunk if processing_allowed(t, m, "rewards.standings", basis_time=now)]
                if rows:
                    t.insert_or_update("HouseStandings", columns=("member_id", "house_ref", "tier", "computed_at", "run_id"), values=rows)
                return len(rows)

            n += run_txn(self.db, tx)
        return n

    def _drop_stale(self, run_id: str) -> int:
        """Standings this run did not produce (no longer a qualifying buyer)."""
        rows = run_read(self.db, lambda s: query(s, "SELECT member_id, house_ref FROM HouseStandings WHERE run_id != @r", {"r": run_id}, {"r": STR}))
        for start in range(0, len(rows), 500):
            keys = [list(r) for r in rows[start:start + 500]]
            run_txn(self.db, lambda t, keys=keys: t.delete("HouseStandings", keyset=KeySet(keys=keys)))
        return len(rows)

    def recompute_if_due(self, *, now: Optional[datetime] = None) -> Any:
        """The newest stored tier dates the last run. A run that stored nothing
        leaves no date, so this process remembers it instead."""
        last, server = run_read(self.db, lambda s: (query(s, "SELECT MAX(computed_at) FROM HouseStandings", {}, {})[0][0], server_now(s)))
        at = now or server
        key = getattr(self.db, "name", id(self.db))
        last = last or _EMPTY_RUNS.get(key)
        if last is not None and at - last < RECOMPUTE_EVERY:
            return "not_due"
        out = self.recompute()
        if out["standings"] == 0:
            _EMPTY_RUNS[key] = at
        return out

    # ------------------------------------------------------------------ reads

    def mine(self, principal: Principal) -> Dict[str, Any]:
        require_scope(principal, "rewards:read")

        def read(s):
            rows = query(s, "SELECT h.house_ref, h.tier, h.computed_at, m.share_standing FROM HouseStandings h "
                            "LEFT JOIN MemberHouses m ON m.member_id = h.member_id AND m.house_ref = h.house_ref "
                            "WHERE h.member_id=@m ORDER BY h.house_ref", {"m": principal.member_id}, {"m": STR})
            return {"items": [{"house_ref": r[0], "house_name": self.catalog.house_name(s, r[0]), "tier": r[1], "computed_at": r[2].isoformat(),
                               "shared_with_house": bool(r[3])} for r in rows],
                    "basis": "Verified, delivered purchases compared with other members who bought from the same house"}

        return run_read(self.db, read)

    def house_view(self, operator: Principal, house_ref: Any) -> Dict[str, Any]:
        """What a house may see: per-tier counts (small counts suppressed) and, for
        members who opted in, their tier. Never units, items, orders or dates."""
        require_scope(operator, "provider:admin")
        ref = require_house_ref(house_ref)

        def read(s):
            counts = {r[0]: r[1] for r in query(s, "SELECT tier, COUNT(*) FROM HouseStandings@{FORCE_INDEX=HouseStandingsByHouse} "
                                                   "WHERE house_ref=@h GROUP BY tier", {"h": ref}, {"h": STR})}
            shared = query(s, "SELECT h.member_id, h.tier FROM HouseStandings h JOIN MemberHouses m "
                              "ON m.member_id = h.member_id AND m.house_ref = h.house_ref "
                              "WHERE h.house_ref=@h AND m.share_standing ORDER BY h.member_id", {"h": ref}, {"h": STR})
            return {"house_ref": ref,
                    "tiers": {t: (counts.get(t, 0) if counts.get(t, 0) >= SUPPRESS_BELOW else None) for t in TIER_ORDER},
                    "suppressed_below": SUPPRESS_BELOW,
                    "members_sharing": [{"member_id": m, "tier": t} for m, t in shared]}

        return run_read(self.db, read)


def standing_for(txn: Any, member_id: str, house_ref: str) -> Optional[str]:
    rows = query(txn, "SELECT tier FROM HouseStandings WHERE member_id=@m AND house_ref=@h", {"m": member_id, "h": house_ref}, {"m": STR, "h": STR})
    return rows[0][0] if rows else None
