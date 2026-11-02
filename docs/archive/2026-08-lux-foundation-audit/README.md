# Lux foundation audit and lift-and-shift plan (August 2026)

Source: branch `claude/brand-me-lux-foundations-audit-8zywr3`, commit `eed6737062da451a38114f8002159c1bed0e5cb5`
(draft PR #29, opened 2026-08-31 against `main` `0f5f58a9`). The two documents are copied here unchanged with
`git show <commit>:docs/audit/<file>`.

| File | What it is |
|---|---|
| `BRANDME_AUDIT.md` | Audit of the repository as of August 2026: no tenancy model, a `test-core` CI job that could not fail, 533 lines of Python tests, no migration runner, broken Makefile targets |
| `LUX_LIFT_AND_SHIFT.md` | Plan to port platform code from the Lux real-estate codebase in tiers (copy / copy-and-rename / pattern only) |

What happened since: the CI gate was made real (`pnpm check`, emulator-backed `tests/`), a checksum-ledger
migration runner exists (`brandme-data/spanner/migrations/runner.py`), and the foundation work landed in
`brandme_core/` through the opus-foundation lane (PRs #33, #53, #58, #62). The `brandme_foundation/` package that
PR #29 added (1,646 lines, 62 tests) was never imported by any service and was not merged; it stays reachable at
the commit above, tagged `archive/lux-foundation-lift-2026-08-31` in the 2026-11 cleanup. PR #29 was closed on
2026-11-02 as preserved-then-retired.
