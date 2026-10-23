"""Persona (Looking Glass) domain: declared/inferred/effective style axes,
evidence suppression, snapshots, context overrides and the deterministic
recommender. See docs/design/brandme/01-product-experience.md §4.

Importing the package registers the persona event types and data categories.
"""

from . import deletion as _deletion  # noqa: F401  (data-category registration)
from . import events as _events  # noqa: F401  (event-type registration)
