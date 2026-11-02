## Summary

<!-- One change. What it does, in two or three sentences. Reference the finding, plan stage or issue it answers. -->

## Why

<!-- The problem or the evidence that motivated it. Link the audit finding, status log stage or deviation. -->

## Verification

<!-- Exactly what was run and the result. Counts, not adjectives. For example:
- `pnpm check`: 12/12 (pytest 2146 passed, 20 skipped, 17 xfailed)
- `pnpm smoke`: 7/7
- gateway vitest: 169/169
- not run locally: image builds (CI) -->

## Documentation and records

- [ ] `CLAUDE.md` row(s) updated if what runs, mounts or depends on something changed
- [ ] `docs/build/implementation-status.md` refreshed if a lane, blocker or baseline moved
- [ ] `docs/build/deviations.md` entry if this departs from the design package
- [ ] Migration number claimed in `tests/foundation/test_migrations.py` and the migrations README (if a migration is added)
- [ ] No new secret-shaped environment variable without a row in `docs/build/security/credential-manifest.yaml`

## Needs another lane

<!-- Files owned by another lane that this change needs edited (mount lines, registries, foundation tests), listed
instead of self-applied. "None" if none. -->

## Out of scope

<!-- What this PR deliberately does not do, and where that work is tracked. -->
