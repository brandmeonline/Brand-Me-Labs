"""Hardened platform foundation, lifted from the Lux Real Estate codebase.

Every module here was ported from a Lux counterpart that ships behind that
repo's merge gates (tenant isolation, Postgres persistence, browser E2E). The
port retargets the domain — Lux's `realtor_id` tenant key becomes Brand.Me's
`owner_id`, and real-estate vocabulary becomes garment/provenance vocabulary —
while carrying the control flow across unchanged.

Provenance for each module is recorded in docs/audit/LUX_LIFT_AND_SHIFT.md.
"""
