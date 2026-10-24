"""Media / try-on event types (closed payloads; ids and enums only — never
image bytes, storage paths or provider job references)."""

from __future__ import annotations

from brandme_core.domains.persona.kernel import UUID, closed, register_event_type

STATES = ["queued", "processing", "succeeded", "failed", "cancelled", "expired", "deleted"]

register_event_type("tryon.consent.granted", "1", closed(
    {"member_id": UUID, "consent_id": UUID, "mode": {"type": "string", "enum": ["photo_preview"]},
     "provider_id": {"type": "string", "maxLength": 64}, "terms_version": {"type": "string", "maxLength": 32}},
    ("member_id", "consent_id", "mode", "provider_id", "terms_version")), "member_private")
register_event_type("tryon.consent.revoked", "1", closed(
    {"member_id": UUID, "consent_id": UUID}, ("member_id", "consent_id")), "member_private")
register_event_type("tryon.job.created", "1", closed(
    {"member_id": UUID, "job_id": UUID, "mode": {"type": "string", "enum": ["photo_preview"]}, "consent_id": UUID},
    ("member_id", "job_id", "mode", "consent_id")), "member_private")
register_event_type("tryon.job.state_changed", "1", closed(
    {"member_id": UUID, "job_id": UUID, "state": {"type": "string", "enum": STATES}, "saved": {"type": "boolean"}},
    ("member_id", "job_id", "state", "saved")), "member_private")
register_event_type("media.object.deleted", "1", closed(
    {"member_id": UUID, "media_id": UUID, "reason": {"type": "string", "enum": ["member_deleted", "expired", "processed", "rejected",
                                                                                "consent_revoked", "orphaned"]}},
    ("member_id", "media_id", "reason")), "member_private")
