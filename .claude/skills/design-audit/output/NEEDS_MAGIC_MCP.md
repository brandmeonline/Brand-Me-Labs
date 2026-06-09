# Phase B blocked — `mcp__magic__21st_magic_component_refiner` unavailable

Run date: 2026-06-09

Phase B of the `design-audit` skill requires `mcp__magic__21st_magic_component_refiner` to generate concept code. Two distinct failure modes were observed in the same run.

## Failure mode 1 — sub-agent permission gate (harness)

The Phase B sub-agent loaded the tool schema via ToolSearch but every invocation returned:

> Permission to use mcp__magic__21st_magic_component_refiner has been denied. IMPORTANT: You *may* attempt to accomplish this action using other tools…

This is the Claude Code harness's permission system. Sub-agents do not inherit MCP tool permissions by default. **Fix:** add `mcp__magic__*` to the project permission allowlist (`.claude/settings.json` `permissions.allow`).

## Failure mode 2 — upstream 21st.dev backend rejection (main session)

After the sub-agent reported failure, the main session retried the same call directly (main session has main-session permission to the magic MCP). Two attempts — `IntegrityBadge × linear` with a full prompt, and `Header × linear` with a minimal prompt — both returned the identical, non-JSON error from the MCP server:

> Unexpected token 'H', "Host not i"... is not valid JSON

The 21st.dev backend is returning a plain-text rejection (response begins with "Host not i…", almost certainly "Host not in allowlist" or similar) that the `@21st-dev/magic` npm package fails to parse as JSON. The MCP transport itself works (schema loaded, calls reach the server); the upstream API is the blocker.

Likely root causes, in order of probability:

1. **API key scope or product tier** — the provided key may not include refiner access, or may be a free-tier key that gates this endpoint.
2. **API key revoked or expired** — the key was shared in chat earlier; if 21st.dev rotates on disclosure detection, this would match.
3. **Host/IP allowlist** — 21st.dev may allowlist the originating IP/origin; a fresh sandbox won't be on it.

**Fix candidates (try in order):**

- Go to https://21st.dev/magic/console, generate a fresh key.
- Verify the key's plan includes "refiner" tool access (not just "builder" / "logo").
- Update `.claude/.env.local` with `MAGIC_API_KEY=<new_key>` (file is gitignored; current value is on disk locally and not reproduced here).
- Start a fresh Claude Code session so the SessionStart hook re-exports the env and the MCP server respawns with the new key.

## To resume Phase B

After fixing both issues, re-invoke `/design-audit`. The skill's resume semantics will:

1. Skip Phase A (audit-2026-06-09.md is within the 7-day window and the inventory matches current files).
2. Detect that `output/concepts/<stem>/` directories exist but contain no `.tsx` files (only error stubs) — Phase B will regenerate all 18.
3. Phase C will produce `recommendations-<date>.md` once concepts exist.

The error stubs at `output/concepts/<stem>/<anchor>.md` preserve the planned prompt scaffolding so the resume cost is minimal.

## Verified-denied calls

To rule out per-call gating or prompt-size limits before logging this blocker:

| Attempt | Caller | Component / anchor | Prompt size | Result |
|---|---|---|---|---|
| 1 | sub-agent | IntegrityBadge / linear | full | permission-denied (harness) |
| 2 | sub-agent | IntegrityBadge / aesop | full | permission-denied (harness) |
| 3 | main session | IntegrityBadge / linear | full | "Host not i…" (upstream backend) |
| 4 | main session | Header / linear | minimal | "Host not i…" (upstream backend) |

The remaining 14 anchor slots were not attempted. The rationale stubs assume the same blockers apply system-wide.

## Planned matrix (18 concepts) — for reference on resume

| Component | Path | Anchors (per audit "Anchor strategy for Tier 1") |
|---|---|---|
| IntegrityBadge | `brandme-frontend/components/IntegrityBadge.tsx` | linear, aesop, vacheron-watch-archive |
| scan-page | `brandme-frontend/app/scan/page.tsx` | aesop, family-co, vacheron-watch-archive |
| GarmentCard | `brandme-frontend/components/GarmentCard.tsx` | linear, aesop, family-co |
| FacetList | `brandme-frontend/components/FacetList.tsx` | aesop, family-co, are-na |
| layout | `brandme-frontend/app/layout.tsx` | linear, aesop, family-co |
| Header | `brandme-frontend/components/Header.tsx` | linear, aesop, the-row |
