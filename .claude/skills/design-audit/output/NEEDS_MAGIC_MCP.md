# Phase B blocked — `mcp__magic__21st_magic_component_refiner` unavailable

Run date: 2026-06-09

Phase B of the `design-audit` skill requires `mcp__magic__21st_magic_component_refiner` to generate concept code. Two distinct failure modes were observed in the same run.

## Failure mode 1 — sub-agent permission gate (harness)

The Phase B sub-agent loaded the tool schema via ToolSearch but every invocation returned:

> Permission to use mcp__magic__21st_magic_component_refiner has been denied. IMPORTANT: You *may* attempt to accomplish this action using other tools…

This is the Claude Code harness's permission system. Sub-agents do not inherit MCP tool permissions by default. **Fix:** add `mcp__magic__*` to the project permission allowlist (`.claude/settings.json` `permissions.allow`).

## Failure mode 2 — upstream 21st.dev backend rejects this sandbox at the network layer (main session)

After the sub-agent reported failure, the main session retried the same call directly. Two attempts — `IntegrityBadge × linear` with a full prompt, and `Header × linear` with a minimal prompt — both returned the identical, non-JSON error from the MCP server:

> Unexpected token 'H', "Host not i"... is not valid JSON

A bypass-the-MCP-layer probe of `https://magic.21st.dev/` confirmed the actual cause: the upstream backend responds with **HTTP 403** and body `Host not in allowlist` for every request from this sandbox, regardless of authentication, path, or method:

```
$ curl -sS -o - -w "\nHTTP %{http_code}\n" https://magic.21st.dev/
Host not in allowlist
HTTP 403

$ curl -sS -o - -w "\nHTTP %{http_code}\n" -X POST https://magic.21st.dev/api/refiner \
    -H "Authorization: Bearer <new_key>" -H "Content-Type: application/json" -d '{}'
Host not in allowlist
HTTP 403
```

We rotated the API key (per the leaked-in-chat hygiene fix) and the new key returned the identical 403 — confirming the block is keyed to the sandbox's outbound IP, not to authentication state. The `@21st-dev/magic` npm package's MCP server doesn't surface this clearly because it tries to `JSON.parse` the plaintext 403 body and reports the parse error instead of the HTTP status.

**Implication:** Phase B cannot run from this Claude-Code-on-the-web sandbox. The fix is environmental, not configurational.

**Resolution paths:**

1. **Run `/design-audit` from a local Claude Code session** (CLI on your laptop or a workstation that 21st.dev's allowlist accepts). The skill, `.mcp.json`, `.claude/.env.local`, and audit output all sync via this branch; only the MCP server needs to originate from a non-blocked IP.
2. **Ask 21st.dev support** to allowlist the IP range used by Claude Code on the web, if they're willing.
3. **Accept the audit-only output** from web sessions and defer concept generation to local runs. The audit alone is the most leveraged artifact — it tells you *what* to redesign and *with which anchors* — and a human designer or local Claude Code session can carry it the rest of the way.

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
