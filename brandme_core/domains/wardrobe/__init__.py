"""Wardrobe domain (W04): closet items, intake, duplicates, care and wear,
closet layout/placement, outfits with immutable versions and friend proposals,
packing lists, and provider-order reduction. See ch.01 §5, ch.02 §4.5, ch.03 §4.

Importing the package registers wardrobe event types and data categories.
"""

from . import deletion as _deletion  # noqa: F401
from . import events as _events  # noqa: F401
from . import guest_sections as _guest_sections  # noqa: F401  (guest-migration sections)
