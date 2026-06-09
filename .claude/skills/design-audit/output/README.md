# Design Audit Output

Generated artifacts from the `design-audit` skill. Files here are checked in so audits remain visible across sessions and reviewable in PRs.

## Structure

```
output/
├── audit-<YYYY-MM-DD>.md          # Phase A scored inventory
├── recommendations-<YYYY-MM-DD>.md # Phase C top-3 recommendations
└── concepts/
    └── <component-stem>/
        ├── <anchor-slug>.tsx       # Phase B generated component
        └── <anchor-slug>.md        # Rationale (breaks / asserts / risk / migration)
```

## Lifecycle

- Audits and recommendations are **timestamped** — never overwrite, always add.
- Concepts are organized by component, then by anchor — overwriting is OK when regenerating the same anchor.
- When a concept is adopted into the actual frontend (Phase D), keep the concept file as historical reference. Mark it adopted by adding a frontmatter note in the rationale `.md`.

## Cleanup

If the audit history gets noisy, prune by date:
- Keep the most recent audit + recommendations
- Keep concepts for components that haven't been redesigned yet
- Move historical audits older than a quarter into `output/archive/<quarter>/`
