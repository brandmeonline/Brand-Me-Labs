"""Media and photo try-on (W08 server side): constrained uploads, consent-gated
provider jobs, explicit save, manifest deletion and 24-hour retention for
unsaved media. Live overlay stays on-device; calibrated fit is unavailable.
See ch.02 §6, ch.03 §6/§8.

Importing the package registers media event types and data categories.
"""

from . import deletion as _deletion  # noqa: F401
from . import events as _events  # noqa: F401
