# Next assignment — consumer-domains lane (PR #52) — from Mia, orchestrator

**Trigger:** PR #53 (foundation round 2) merged to `main` at `1f0d7387`, and PR #54 merged at `0c3d7ea2`. PR #52 is now `mergeable: false / dirty` against current `main` (`0c3d7ea2`). Mia verified by diffing both PRs' file lists that the ONLY overlapping file is `.github/workflows/ci-cd.yml`. No domain code conflicts.

**Do this, in order:**
1. Merge current `main` (`0c3d7ea2878d66a35d68451df4edb60d79f1ed92`) into the PR #52 branch (`claude/opus-consumer-domains-1csp2g`). No rebase.
2. Resolve `.github/workflows/ci-cd.yml` keeping BOTH changes: foundation's current version of the file AND this lane's `test-consumer-domains` job plus the `build-images` dependency on it. Nothing else should need resolution; if anything else conflicts, stop and record it in your status file instead of guessing.
3. Re-verify on the merged tree from a CLEAN checkout (the dirty-tree blind spot from Stage 10 must not recur): the lane suites via the new CI job's exact command, plus `pnpm check`. Report counts in your status file as a Stage 11 entry.
4. Push and confirm the PR shows green check-runs + mergeable clean.

**Then:** Mia auto-merges PR #52 under the founder's aggressive auto-merge authorization (2026-10-23) — no new founder approval needed. Do not merge it yourself.

**After #52 lands:** your next build is the ruled Q19 item — GCS-backed `MediaStore` (signed URLs, lifecycle, purge) against a local GCS emulator; the dev bucket + service account are founder questions (Q15 in `questions-for-founder-20261023.md`, this directory) and are not yet provisioned, so build emulator-first.

Record status only in `docs/build/status/opus-consumer-domains.md`. Never edit `docs/design/brandme/**` or `contracts/**`.
