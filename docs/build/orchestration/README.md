# Orchestration — Mia ↔ builders protocol

Mia is the standing orchestrator for the Brand.Me bench program (founder direction, 2026-10-05; direct-trigger model confirmed 2026-10-23).

## How work flows

1. **Assignments live here.** Mia writes each lane's next assignment as a file in this directory (`next-<lane>-<topic>.md`) and posts a short trigger comment on the lane's PR naming the file. Builders keep their Claude/Codex sessions open and listening; a trigger comment + file is the start signal — no founder pasting.
2. **Builders respond in their own surfaces**: commits on their branch/PR and their lane status file (`docs/build/status/<lane>.md`). Mia verifies evidence against GitHub (SHAs, check-runs, file contents) — claims are never taken on trust.
3. **Auto-merge (founder posture, 2026-10-23: aggressive).** Mia auto-merges any PR that is **green (all check-runs success, expected skips only) + mergeable clean + ready (not draft)**, including PRs targeting `main`, without re-asking per PR. Drafts are marked ready by Mia only when the lane's own evidence is complete.
4. **Notation rule.** Every merge Mia executes gets a notation comment on the PR stating why the merge is correct: the exact head SHA verified, the check-run tally, mergeable state, scope, and the founder authorization it rests on. Holds are notated the same way, with the reason and the exact next step.
5. **Founder gates stay founder gates**: credentials/secrets, funded wallets, prod-scoped anything, external releases, device sessions. Lanes stop at their check-in and deliver questions; Mia digests them with recommendations (`questions-for-founder-*.md` in this directory).

## Current state

See `merge-log-20261023.md` for the 2026-10-23 merge train and `questions-for-founder-20261023.md` for the open decision set.
