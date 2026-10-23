-- Persona (opus-consumer-domains): link profiles to members and add the
-- profile constraints, as a forward migration so V002 stays byte-identical to
-- what existing databases already applied (the runner rejects checksum drift).
--
-- Spanner cannot convert an existing table to an interleaved one, so the
-- member link is a foreign key with ON DELETE CASCADE: a persona cannot exist
-- without a V001 member and is removed with it (its interleaved children
-- cascade with it). Adding the key validates existing rows, so a database with
-- persona rows for nonexistent members fails here and must be cleaned first.
-- Tombstones and guest-migration records stay unlinked: they must outlive the
-- member row.

ALTER TABLE PersonaProfiles ADD CONSTRAINT ck_persona_budget CHECK (budget_ceiling_minor IS NULL OR budget_ceiling_minor >= 0);

ALTER TABLE PersonaProfiles ADD CONSTRAINT ck_persona_version CHECK (version >= 1);

ALTER TABLE PersonaProfiles ADD CONSTRAINT FK_PersonaProfiles_Members FOREIGN KEY (member_id) REFERENCES Members (member_id) ON DELETE CASCADE;
