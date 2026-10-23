"""
Social lane defaults that the contracts do not fix. They ship now so the lane
does not stall, and wait for founder ratification at the lane check-in. Each
can be changed here alone; services and tests read these names.

* PD-10: a share lives between ``SHARE_MIN_LIFETIME`` and ``SHARE_MAX_LIFETIME``;
  a member holds at most ``SHARE_MAX_ACTIVE`` unrevoked, unexpired shares.
* PD-11: a share reached through a valid token, or by an authorized member, that
  is revoked, expired or whose subject is gone answers ``SHARE_GONE_STATUS``
  (410 ``share_unavailable`` with ``reason``). Anything else is 404. Setting the
  status to 404 makes a gone share indistinguishable from an unknown one.
* PD-09 (endpoints and ``target_member_id``) is a contract-surface proposal, not
  a tunable; it is listed here so the ratification record is in one place.
"""

from __future__ import annotations

from datetime import timedelta

SHARE_MIN_LIFETIME = timedelta(minutes=5)
SHARE_MAX_LIFETIME = timedelta(days=365)
SHARE_MAX_ACTIVE = 200
SHARE_GONE_STATUS = 410  # 404 is the alternative under PD-11

RATIFICATION = {"PD-09": "pending", "PD-10": "pending", "PD-11": "pending"}
