# Provenance of this pack

Source: the first audit's upload `brand-me-labs-audit-2026-11-01-codex-01.zip` (115 files), produced by Codex on 2026-11-01 against remote `main`
`ed19dc151d103b108cf972e6d37971c55d5dcf60`. The second audit (`../claude-opus-02/`) reviewed it unchanged; it was committed here on 2026-11-02 on the
owner's instruction so that the reconciliation's references to its files resolve.

The only edit made before committing: the first auditor's local account name was replaced by `auditor` inside recorded local paths in
7 evidence files (evidence/baseline.json, evidence/history-clone-worktrees.txt, evidence/history-reproduce-excerpts.ps1, evidence/history-reproduce-git.ps1, evidence/history-reproduce-semantics.ps1, evidence/local-baseline-before-fetch.txt, evidence/static-checks.json). `evidence/security-secret-candidates.json` carries `"value": "REDACTED"` for
every candidate; no credential material is in this pack.

Its internal links were written for the zip layout and are not validated by the repository's link checker (`docs/audits/` is outside its scope).
