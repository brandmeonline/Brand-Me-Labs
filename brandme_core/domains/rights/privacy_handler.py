"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Rights domain registration with the My Data framework.
"""

from __future__ import annotations

from typing import Any

from google.cloud.spanner_v1 import param_types as pt

from brandme_core.domains.privacy.deletion import (
    DataCategory, DeletionOutcome, ExportSection, OnDelete, SubjectContext, Supplier, Tombstone,
)


class RightsPrivacyHandler:
    domain = "rights"

    def categories(self):
        return [
            DataCategory("rights.control_links", "rights", "Which digital entitlements you control", Supplier.SYSTEM,
                         ("member",), "While you control them", "Changes only through a transfer",
                         OnDelete.ERASE),
            DataCategory("rights.transfers", "rights", "Your transfer requests", Supplier.MEMBER, ("member", "recipient"),
                         "Until you delete them", "Cancel before acceptance", OnDelete.ERASE),
            DataCategory("rights.reprint_jobs", "rights", "Your reprint jobs", Supplier.MEMBER, ("member", "manufacturer"),
                         "7 years after delivery", "Cancel before rights are consumed", OnDelete.RETAIN_LEGAL,
                         retention_basis="Manufacturing and sales records retained for warranty, tax and dispute handling; "
                                         "your member reference is removed."),
            DataCategory("rights.chain_commitments", "rights", "Public ownership commitments on Midnight", Supplier.SYSTEM,
                         ("public",), "Permanent (public ledger)", "Cannot be edited",
                         OnDelete.NOT_ERASABLE_PUBLIC_LEDGER, personal=False),
        ]

    def export(self, snap: Any, ctx: SubjectContext, category: str) -> ExportSection:
        s = ctx.subject_ref
        if category in ("rights.control_links", "rights.chain_commitments"):
            rows = list(snap.execute_sql(
                "SELECT network, contract_address, entitlement_id, asset_id, epoch, status, last_tx_id FROM RightsEntitlements "
                "WHERE controller_subject_ref = @s", params={"s": s}, param_types={"s": pt.STRING}))
            refs = [{"network": r[0], "contract_address": r[1], "entitlement_id": r[2], "epoch": r[4], "last_tx_id": r[6]} for r in rows]
            if category == "rights.chain_commitments":
                return ExportSection(category, [], references=refs,
                                     notes=["Public references only. Ownership secrets are exported separately from Wallet → Ownership backup."])
            return ExportSection(category, [{"asset_id": r[3], "entitlement_id": r[2], "status": r[5], "network": r[0]} for r in rows])
        if category == "rights.transfers":
            rows = snap.execute_sql("SELECT intent_id, entitlement_id, state, created_at FROM TransferIntents WHERE from_subject_ref = @s",
                                    params={"s": s}, param_types={"s": pt.STRING})
            return ExportSection(category, [{"intent_id": r[0], "entitlement_id": r[1], "state": r[2], "created_at": r[3]} for r in rows])
        rows = snap.execute_sql("SELECT job_id, state, quantity, created_at FROM ReprintJobs WHERE member_subject_ref = @s",
                                params={"s": s}, param_types={"s": pt.STRING})
        return ExportSection(category, [{"job_id": r[0], "state": r[1], "quantity": r[2], "created_at": r[3]} for r in rows])

    def delete(self, txn: Any, ctx: SubjectContext, category: str) -> DeletionOutcome:
        p, t = {"s": ctx.subject_ref}, {"s": pt.STRING}
        if category == "rights.control_links":
            n = txn.execute_update("UPDATE RightsEntitlements SET controller_subject_ref = NULL WHERE controller_subject_ref = @s", params=p, param_types=t)
            return DeletionOutcome(category, n)
        if category == "rights.transfers":
            n = txn.execute_update("DELETE FROM TransferIntents WHERE from_subject_ref = @s", params=p, param_types=t)
            return DeletionOutcome(category, n)
        if category == "rights.reprint_jobs":
            n = txn.execute_update("UPDATE ReprintJobs SET member_subject_ref = 'deleted-member' WHERE member_subject_ref = @s", params=p, param_types=t)
            return DeletionOutcome(category, n, detail="member reference removed; job record retained")
        return DeletionOutcome(category, 0, detail="public ledger commitments are not erasable")

    def purge_derived(self, ctx: SubjectContext, category: str) -> DeletionOutcome:
        return DeletionOutcome(category, 0)

    def reapply_tombstone(self, txn: Any, t: Tombstone) -> int:
        return self.delete(txn, SubjectContext(t.subject_ref, t.deletion_job_id, t.created_at), t.category).rows_affected
