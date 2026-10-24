"""The operator page says what actually resolves a stuck purchase.

No commerce worker, scheduler or sweeper exists in this build. ``CommerceService.reconcile`` runs only
when a verified provider event arrives for an order Brand.Me does not know yet (``handle_webhook``),
for that provider's ``outcome_unknown`` operations, or when something calls it directly. A stalled
``submitting`` operation is moved to unknown only by a direct ``reconcile`` call.
"""

import re
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "brandme-console" / "app" / "(ops)" / "commerce" / "operations" / "page.tsx"


def test_operations_page_promises_no_automatic_reconciliation():
    text = PAGE.read_text()
    assert not re.search(r"(?i)automatic|runs in the (commerce )?worker", text)
    assert "No worker or schedule" in text  # the gap is stated, not implied away
