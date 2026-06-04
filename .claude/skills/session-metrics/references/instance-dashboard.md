# Instance dashboard (all-projects) — reference

> Loaded on demand from `SKILL.md` when `$ARGUMENTS[0]` is `all-projects`
> (or the user asks for total spend across every project). Also the home of
> the `--projects-dir` / `--cache-dir` / `--export-dir` overrides, which
> apply at every scope.

## Instance dashboard (all projects)

Reached when `$ARGUMENTS[0]` is `all-projects`, or when the user asks
for the **total cost across every project** ("how much have I spent on
Claude Code overall?", "what's my total spend across all projects?",
"which project is costing me the most?").

Aggregates every project under `~/.claude/projects/` (or
`CLAUDE_PROJECTS_DIR`, or the `--projects-dir` override) into a single
dashboard with instance-wide totals, a daily cost timeline, and a
per-project breakdown table sorted by cost descending. Each project row
hyperlinks to a pre-rendered per-project HTML drilldown that carries
the full session/turn detail (same report as `--project-cost <slug>`).

```bash
# Instance-wide dashboard — HTML + MD + CSV + JSON
uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --all-projects --output html md csv json

# Fast path — no per-project drilldown HTMLs (rows render as plain text)
uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --all-projects --no-project-drilldown --output html

# Multi-instance: point at a non-default Claude Code install
uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --all-projects --projects-dir /opt/claude-work/projects
```

### Output layout

Exports write to a dated subfolder so successive runs don't overwrite
each other and the whole bundle stays portable (zip it, move it, serve
it as static files — relative drilldown links keep working):

```
exports/session-metrics/instance/YYYY-MM-DD-HHMMSS/
  index.html    # entry point — instance dashboard
  index.md
  index.csv     # one row per session, with a project_slug column
  index.json    # full instance report (no per-turn records — only per-session summaries)
  projects/
    <slug-1>.html   # full per-project HTML, same as --project-cost <slug-1>
    <slug-2>.html
    ...
```

`--no-project-drilldown` skips the `projects/` folder entirely and
renders `index.html` with project rows as plain text (no hyperlinks) —
useful for CI or quick-glance runs. Per-turn data is always suppressed
at the instance scope; users drill down by clicking into a project HTML.

### Multi-instance Claude Code setups

Three layered overrides pick the projects directory (highest precedence first):

1. `--projects-dir <path>` CLI flag
2. `CLAUDE_PROJECTS_DIR` environment variable
3. Default `~/.claude/projects`

The resolved projects directory is rendered into the HTML header byline
so output from multiple instances is self-documenting when viewed
side-by-side.

### Cache-dir and export-dir overrides (v1.41.0)

Two parallel override knobs for the parse-cache and export directories.
Same precedence shape as `--projects-dir`:

| Resource | CLI flag | Env var | Default |
|----------|----------|---------|---------|
| Parse cache | `--cache-dir` | `CLAUDE_SESSION_METRICS_CACHE_DIR` | `~/.cache/session-metrics/parse` |
| Exports | `--export-dir` | `CLAUDE_SESSION_METRICS_EXPORT_DIR` | `<cwd>/exports/session-metrics` |

Useful when:
- running in CI / sandboxes where `~/.cache` isn't writable
- juggling multiple Claude Code installs and you want each to keep its own cache
- redirecting reports to a shared / mounted directory without `cd`-ing first

```bash
# Redirect both via env vars
CLAUDE_SESSION_METRICS_CACHE_DIR=/tmp/sm-cache \
CLAUDE_SESSION_METRICS_EXPORT_DIR=/tmp/sm-out \
  uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --output html json

# Or via CLI flags (highest precedence — beats env)
uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py \
  --cache-dir /tmp/sm-cache --export-dir /tmp/sm-out --output html json
```
