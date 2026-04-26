#!/bin/bash
# SessionStart hook: export secrets needed by project MCP servers (e.g. MAGIC_API_KEY
# for the 21st.dev Magic MCP server declared in .mcp.json).
#
# Reads .claude/.env.local (gitignored) and forwards each line as an export
# into $CLAUDE_ENV_FILE so values are present in the session's environment.
set -euo pipefail

ENV_LOCAL="${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/.env.local"

if [ ! -f "$ENV_LOCAL" ]; then
  echo "session-start: $ENV_LOCAL not found; skipping env export" >&2
  exit 0
fi

if [ -z "${CLAUDE_ENV_FILE:-}" ]; then
  echo "session-start: CLAUDE_ENV_FILE not set; skipping env export" >&2
  exit 0
fi

while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    ''|\#*) continue ;;
  esac
  key="${line%%=*}"
  val="${line#*=}"
  if [ -z "$key" ] || [ "$key" = "$line" ]; then
    continue
  fi
  # strip a single matching pair of surrounding quotes if present
  case "$val" in
    \"*\") val="${val#\"}"; val="${val%\"}" ;;
    \'*\') val="${val#\'}"; val="${val%\'}" ;;
  esac
  # single-quote the value, escaping embedded single quotes as '\''
  escaped=$(printf "%s" "$val" | sed "s/'/'\\\\''/g")
  printf "export %s='%s'\n" "$key" "$escaped" >> "$CLAUDE_ENV_FILE"
done < "$ENV_LOCAL"
