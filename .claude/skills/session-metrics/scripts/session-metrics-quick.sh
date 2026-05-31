#!/usr/bin/env bash
# session-metrics-quick.sh — one-shot session-metrics export for the CURRENT
# Claude Code project. Auto-locates session-metrics.py, detects the project
# slug + newest session, and runs a quick HTML+JSON export. Bundled alongside
# session-metrics.py so quick runs work from any shell without path juggling.
#
# Usage:
#   ./session-metrics-quick.sh                   # newest session of cwd's project -> HTML+JSON
#   ./session-metrics-quick.sh --output md csv    # override formats / pass ANY script flag
#   ./session-metrics-quick.sh --project-cost     # flags pass straight through
#
# Env overrides:
#   SM_PY=/path/to/session-metrics.py    # skip auto-discovery
#   CLAUDE_PROJECTS_DIR=/alt/projects    # non-default projects dir (the script honours it too)
#
# Note: session-metrics.py already auto-detects the project + newest session
# from cwd; this wrapper's real job is locating the (version-pinned) script and
# echoing what it picked. Run it from inside the project you want to analyse.
set -euo pipefail

# --- 1. Locate session-metrics.py (first match wins) ------------------------
find_script() {
  [ -n "${SM_PY:-}" ] && { printf '%s\n' "$SM_PY"; return; }
  # Bundled case (primary): the report script ships next to this wrapper.
  local self_dir
  self_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
  [ -f "$self_dir/session-metrics.py" ] && { printf '%s\n' "$self_dir/session-metrics.py"; return; }
  # Project-local checkout.
  [ -f ".claude/skills/session-metrics/scripts/session-metrics.py" ] \
    && { printf '%s\n' ".claude/skills/session-metrics/scripts/session-metrics.py"; return; }
  # Personal-config copy.
  [ -f "$HOME/.claude/skills/session-metrics/scripts/session-metrics.py" ] \
    && { printf '%s\n' "$HOME/.claude/skills/session-metrics/scripts/session-metrics.py"; return; }
  # Plugin cache is version-pinned (.../session-metrics/<ver>/...) -> pick newest.
  local newest
  newest="$(find "$HOME/.claude/plugins/cache" \
              -path '*/session-metrics/*/skills/session-metrics/scripts/session-metrics.py' \
              2>/dev/null | sort -V | tail -1)"
  [ -n "$newest" ] && { printf '%s\n' "$newest"; return; }
  # Unversioned marketplace copy, last resort (grep . sets the exit status).
  find "$HOME/.claude/plugins/marketplaces" \
    -path '*/session-metrics/skills/session-metrics/scripts/session-metrics.py' \
    2>/dev/null | head -1 | grep .
}
SCRIPT="$(find_script)" || { echo "session-metrics.py not found — set SM_PY=/path/to/it" >&2; exit 1; }

# --- 2. Detect project slug + newest session (mirrors the script's _cwd_to_slug)
PROJECTS_DIR="${CLAUDE_PROJECTS_DIR:-$HOME/.claude/projects}"
SLUG="$(printf '%s' "$PWD" | sed 's/[^A-Za-z0-9-]/-/g')"
SESSION=""
if [ -d "$PROJECTS_DIR/$SLUG" ]; then
  # newest top-level *.jsonl (subagents/ is a subdir, so it's excluded). The
  # `|| true` keeps the no-match case from tripping `set -e` under `pipefail`
  # so we fall through to the script's own auto-detection instead of aborting.
  # SC2012: filenames are session UUIDs ([0-9a-f-], no spaces/newlines), and the
  # `find`-based mtime sort isn't portable (GNU -printf / stat differ on BSD).
  # shellcheck disable=SC2012
  newest="$(ls -t "$PROJECTS_DIR/$SLUG"/*.jsonl 2>/dev/null | head -1)" || true
  [ -n "$newest" ] && SESSION="$(basename "$newest" .jsonl)"
fi

# --- 3. Pick a Python runner (uv preferred; plain python3 works — no deps) ---
if command -v uv >/dev/null 2>&1; then RUN=(uv run python); else RUN=(python3); fi

echo "[quick] script  : $SCRIPT"                              >&2
echo "[quick] slug    : $SLUG"                                >&2
echo "[quick] session : ${SESSION:-<auto-detect by script>}"  >&2

# --- 4. Run: default to a quick HTML+JSON export; pass through any user args -
ARGS=(--quiet --output html json); [ "$#" -gt 0 ] && ARGS=("$@")
if [ -n "$SESSION" ]; then
  exec "${RUN[@]}" "$SCRIPT" --session "$SESSION" "${ARGS[@]}"
else
  exec "${RUN[@]}" "$SCRIPT" "${ARGS[@]}"
fi
