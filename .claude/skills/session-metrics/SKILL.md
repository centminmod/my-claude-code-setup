---
name: session-metrics
description: >
  Tally Claude Code session token usage and cost estimates from the raw JSONL
  conversation log. Trigger when the user asks about session cost, token usage,
  API spend, cache hit rate, input/output tokens, or wants a breakdown of how
  much a Claude Code session has cost. Also trigger for "how much have we spent",
  "show me token usage", "session summary", "cost so far", or any request to
  analyse or display per-turn metrics from the current or a past session.

  Do NOT auto-dispatch compare mode (--compare / --compare-prep / --compare-run
  / --count-tokens-only) from natural-language phrases. The skill body uses
  $ARGUMENTS[0] as the dispatch key — if the first positional argument is not
  literally "compare", "compare-prep", "compare-run", or "count-tokens", route
  to the default single-session report.
---

# Session Metrics

Runs `scripts/session-metrics.py` against the Claude Code JSONL log to produce
a timeline-ordered cost summary with per-turn and cumulative totals.

## Dispatch — how to route this invocation

**First positional argument received:** `$ARGUMENTS[0]`
**Full argument string:** `$ARGUMENTS`

Read `$ARGUMENTS[0]` above and match it by **literal equality** against the
table below. Claude Code already tokenized the arguments shell-style, so no
parsing is required — just compare strings.

| `$ARGUMENTS[0]`     | Route                                     | Then read |
|---------------------|-------------------------------------------|-----------|
| `all-projects`      | Instance-wide dashboard aggregating every project under `~/.claude/projects` | `## Instance dashboard (all projects)` below |
| `compare`           | Two-session compare on JSONLs that already exist | `## Model comparison` below, then [`references/model-compare.md`](references/model-compare.md) before running |
| `compare-run`       | Fully automated capture: spawns two `claude -p` sessions, feeds the suite, then runs `--compare` | `## Model comparison` below, then [`references/model-compare.md`](references/model-compare.md) "Workflow A — automated" |
| `compare-prep`      | Print manual capture protocol + 10-prompt suite (fallback when headless is unavailable) | `## Model comparison` below |
| `count-tokens`      | API-key-only tokenizer check              | `## Model comparison` below |
| `export`            | Natural-language export shortcut — scan full arg string to determine session vs project scope | `## Export shortcuts` below |
| `project`           | All sessions for the current project — timeline + per-session subtotals + grand total | `## Quick usage` below (`--project-cost`); also scan remaining args for `--output` format flags |
| `project-cost`      | Alias for `project`                       | `## Quick usage` below (`--project-cost`); also scan remaining args for `--output` format flags |
| *(empty, or any other value)* | Default single-session report   | `## Quick usage` below |

This is the single gate that keeps compare mode off the natural-language
path. **Do not infer the route from the user's chat history; only use the
literal value of `$ARGUMENTS[0]` above.**

When the skill auto-triggers from a natural-language question ("how much did
this session cost?", "show me token usage"), there are no positional
arguments — `$ARGUMENTS[0]` is empty — and you always route to the default.
Phrases like "compare 4.6 vs 4.7 cost" arriving as natural language do NOT
produce `$ARGUMENTS[0] = compare` and must not route into compare mode;
answer them by running the default report on the current session and
suggesting `/session-metrics compare-prep` if the user wants a real
benchmark.

## Pre-flight context

- skill-dir: ${CLAUDE_SKILL_DIR}
- session-id: ${CLAUDE_SESSION_ID}

## Export shortcuts

Reached when `$ARGUMENTS[0]` is `export`. Scan the **full argument string** (not just `$ARGUMENTS[0]`) to determine scope and formats. Apply these checks **in order** (first match wins):

1. Full arg string contains `all-projects` → `--all-projects --output <formats>`
2. Full arg string contains `project` (and not already caught above) → `--project-cost --output <formats>`
3. Otherwise → current session `--session ${CLAUDE_SESSION_ID} --output <formats>`

Infer format flags from the argument string: `html` → `html`, `csv` → `csv`, `md` or `markdown` → `md`. Always add `json` alongside any requested format per the post-export audit convention (see `## Optional post-export audit` below).

**Always add `--quiet` to session and project export commands.** When exporting, the per-turn detail lives in the written HTML/JSON, so the full stdout timeline is redundant — and at project scope (or for a long session) it can run to thousands of lines, spilling the run into a harness overflow file that buries the `[export]` path lines you need. `--quiet` collapses stdout to the legend + grand total + footer (plus the `[export]` lines), keeping the run inline. Do **not** add `--quiet` for `--all-projects` — its instance dashboard text is already compact and the flag has no effect there.

**Examples:**

| Full argument string | Command |
|---|---|
| `export session` | `--session ${CLAUDE_SESSION_ID} --quiet --output json` |
| `export session to html` | `--session ${CLAUDE_SESSION_ID} --quiet --output html json` |
| `export session metrics to html` | `--session ${CLAUDE_SESSION_ID} --quiet --output html json` |
| `export to html` | `--session ${CLAUDE_SESSION_ID} --quiet --output html json` |
| `export project` | `--project-cost --quiet --output json` |
| `export project to html` | `--project-cost --quiet --output html json` |
| `export project sessions` | `--project-cost --quiet --output json` |
| `export project sessions to html` | `--project-cost --quiet --output html json` |
| `export entire project's session metrics to html` | `--project-cost --quiet --output html json` |
| `export project metrics to html csv` | `--project-cost --quiet --output html csv json` |
| `export all-projects` | `--all-projects --output json` |
| `export all-projects to html` | `--all-projects --output html json` |

`project` and `project-cost` as the first arg also pick up `--output` flags from remaining args the same way (e.g. `/session-metrics project metrics export to html` → `--project-cost --quiet --output html json`).

## Quick usage

```bash
# Current session (pinned to session ID — no heuristic)
uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --session ${CLAUDE_SESSION_ID}

# Specific session ID
uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --session <uuid>

# Specific project slug (use = when slug starts with "-")
uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --slug=-home-user-projects-myapp
# Or via env var (always safe):
CLAUDE_PROJECT_SLUG="-home-user-projects-myapp" uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py

# List available sessions for this project
uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --list

# All sessions — timeline + per-session subtotals + grand project total
uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --project-cost

# Export to exports/session-metrics/ (one or more formats).
# Add --quiet on exports so a long timeline doesn't bury the [export] paths.
uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --quiet --output json
uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --quiet --output json csv md html
uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --project-cost --quiet --output html
```

> `${CLAUDE_SKILL_DIR}` is expanded by Claude Code to the skill's install directory (plugin cache, project-local copy, or bundled template — whichever applies). When running the script manually from a shell, substitute the actual path.

> **Quick shell wrapper.** For manual runs outside Claude Code, the bundled [`scripts/session-metrics-quick.sh`](scripts/session-metrics-quick.sh) auto-locates `session-metrics.py` (including the version-pinned plugin-cache install), detects the current project + newest session, and runs an HTML+JSON export. Pass `--session <uuid>` (or `-s`) to target a specific session instead — it resolves across all projects, so you can run it from a fresh low-context session to export an earlier heavy one; the HTML+JSON default still applies unless you pass `--output`. Other flags (`--project-cost`, `--list`, an explicit `--output …`) pass through verbatim.

## Export formats

`--output` accepts one or more of: `json` `csv` `md` `html`

Text is always printed to stdout. Exports go to `exports/session-metrics/` in the
project root, named `session_<id8>_<YYYYMMDD_HHMMSS>.<ext>` (single) or
`project_<YYYYMMDD_HHMMSS>.<ext>` (project mode).

| Format | Contents |
|--------|----------|
| `json` | Full structured report with all turns, subtotals, model rates |
| `csv`  | One row per turn: session_id, index, timestamp, model, tokens, cost |
| `md`   | Summary table + per-session Markdown tables |
| `html` | Dark-theme report with summary cards + insights + chart. 2-page split by default (`<stem>_dashboard.html` + `<stem>_detail.html`); pass `--single-page` for one file. |

### HTML-specific flags

| Flag | Purpose |
|------|---------|
| `--single-page`              | Emit one self-contained HTML instead of the dashboard+detail split. |
| `--chart-lib {highcharts,uplot,chartjs,none}` | Choose the chart renderer. Default `highcharts` (richest visualization, vendored, SHA-256-verified, non-commercial license). `uplot` and `chartjs` are MIT-licensed alternatives. `none` emits a detail page with no JS dependency. See [`scripts/vendor/charts/README.md`](scripts/vendor/charts/README.md) for per-library license terms. |
| `--peak-hours H-H`           | Translucent band on the hour-of-day chart (e.g. `5-11`). Community-reported, not an Anthropic SLA. |
| `--peak-tz <IANA>`           | Timezone the peak hours are defined in (default `America/Los_Angeles`). |

### Other useful flags

| Flag | Purpose |
|------|---------|
| `--tz <IANA>`                | IANA timezone for time-of-day bucketing **and timeline/export timestamps**. Defaults to the system local tz (auto-detected via `TZ` env var or the OS setting). |
| `--utc-offset <H>`           | Fixed UTC offset, DST-naive. Use `--tz` for DST-aware. |
| `--no-cache`                 | Skip `~/.cache/session-metrics/parse/` and always re-parse from scratch. |
| `--quiet` / `-q`             | Suppress the per-turn timeline on stdout — print only the legend, scope header, grand-total subtotal, and footer (the `[export]` path lines still print). Keeps stdout small on large session/project exports so the export paths aren't buried under an overflow-sized dump; the full per-turn detail still lands in the written HTML/JSON. Session and project scopes only (no effect on `--all-projects`). |
| `--no-self-cost`             | Suppress the self-cost meta-metric (stderr `[self-cost]` line, HTML KPI card, and JSON `self_cost` key). |
| `--redact-user-prompts`      | Replace freeform `prompt_text` / `prompt_snippet` / `assistant_text` / `assistant_snippet` with `[redacted]` on every turn of single-session and project **JSON** exports, plus compare HTML. Tool inputs, slash-command names, and structured cost / token fields stay visible. HTML / MD / CSV / text are NOT redacted. |
| `--export-share-safe`        | One-flag pre-share gesture (v1.36.0+): implies `--redact-user-prompts` and `--no-self-cost`, and chmods every written export file to `0600` (`rw-------`). For full prompt redaction, pair with `--output json`. |
| `--no-include-subagents`     | Skip spawned subagent JSONL files. Subagents are included by default; use this for faster runs when subagent detail is not needed. |
| `--cache-break-threshold <N>` | Turns whose `input + cache_creation` exceed N are flagged as **cache-break events** (default 100 000). Matches Anthropic's `session-report` convention. |
| `--no-subagent-attribution`  | Disable Phase-B subagent → parent-prompt token attribution. Default behaviour rolls every subagent's tokens up onto the user prompt that spawned the chain (additional `attributed_subagent_*` fields, no double-counting). |
| `--sort-prompts-by {total,self}` | How to rank top prompts in HTML/MD output. `total` (default) = parent + attributed subagent cost, surfaces cheap-prompt-spawning-expensive-subagent turns. `self` = parent only (pre-Phase-B order). CSV/JSON keep `self` ordering for stability regardless of this flag. |

> **Invocation note for the AI.** Don't pass `--tz` or `--utc-offset` unless the user explicitly asks for a specific timezone. The script auto-detects the user's system tz and renders all human-facing timestamps (timeline, session headers, generated-at banner, block anchors) in that tz. JSON/CSV raw `timestamp` fields stay UTC ISO-8601 as a machine-readable audit trail. Don't pass `--include-subagents` — subagents are included by default. Only pass `--no-include-subagents` if the user explicitly asks for a faster/leaner run without subagent detail.

## Output columns

| Column    | Meaning                                      |
|-----------|----------------------------------------------|
| `#`       | Deduplicated turn index                      |
| `Time`    | Timestamp of the turn in the user's local timezone (auto-detected; override with `--tz` / `--utc-offset`). Header shows the active tz label. Raw `timestamp` fields in JSON/CSV exports remain UTC ISO-8601 (`...Z`) for machine-readability. |
| `Input`   | Net new input tokens (uncached portion only — cache reads/writes are shown separately) |
| `Output`  | Output tokens generated (includes thinking + tool_use block tokens) |
| `CacheRd` | Tokens served from prompt cache (cheap)      |
| `CacheWr` | Tokens written to prompt cache (one-time). `1h` / `mix` badge marks turns that used the 1-hour TTL tier; CSV/JSON expose `cache_write_5m_tokens` and `cache_write_1h_tokens` as dedicated columns. |
| `Content` | Per-turn content-block distribution. Letter encoding `T` thinking, `u` tool_use, `x` text, `r` tool_result, `i` image (zero counts omitted). Renders only when at least one turn carries any content block. CSV/JSON expose `thinking_blocks` / `tool_use_blocks` / `text_blocks` / `tool_result_blocks` / `image_blocks` as dedicated per-turn columns. |
| `Total`   | Sum of the four billable token buckets       |
| `Cost $`  | Estimated USD for this turn                  |

Deep-dive on exact column semantics, JSON keys, and detection rules:
[`references/jsonl-schema.md`](references/jsonl-schema.md).

### Per-turn drill-down (HTML only)

In the Detail page and single-page variants, every Timeline row is
clickable (keyboard: Enter / Space) and opens a right-side **drawer**
showing the user's actual prompt, any slash command, the tools that were
called (with one-line input previews), the content-block mix, the
per-turn cost/token breakdown, and the assistant's reply. Prompt and
assistant text are truncated to ~240 characters with a **Show full
prompt** / **Show full response** toggle that reveals the full text (up
to a 2 KB cap on assistant text). Close with the × button, Esc, or a
backdrop click — focus returns to the originating row. Below the
Timeline, a collapsible **Prompts** section lists the top-20
most-expensive prompts; each row opens the same drawer. The Dashboard
variant has no Timeline, so it's unaffected.

Footer shows session totals + **cache savings** vs a hypothetical no-cache
run. Conditional dashboard cards appear when their feature was used in the
session: **Cache TTL mix** (when any 1h-tier cache writes happened),
**Extended thinking engagement** (when any turn carried a `thinking` block),
**Tool calls** (top-3 tool names), **Session resumes** (timeline divider at
each `claude -c` resume point, detected from `/exit` + synthetic-turn
fingerprint — lower-bound count), and the **Usage Insights** panel
(prose-style pattern characterisations inspired by Anthropic's `/usage`
command, auto-hide below threshold, exposed in JSON under `usage_insights`
and in Markdown under `## Usage Insights`).

### Cross-cutting sections (v1.6.0 — inspired by Anthropic's session-report)

Three additional sections auto-hide when empty and render at every scope
(single session / `--project-cost` / `--all-projects`). All three feed the
same `by_skill`, `by_subagent_type`, and `cache_breaks` keys in the JSON
export.

- **Cache breaks** — single turns whose `input + cache_creation` exceeds
  the threshold (configurable via `--cache-break-threshold`, default
  100 000). Each row names **which turn** lost the cache; the HTML version
  is expandable and shows ±2 user-prompt context around the event.
  Complements the overall cache-hit % with actionable "here is where it
  blew up" detail.
- **Skills & slash commands** — one row per named skill or `/slash`
  command, columns: invocations, turns attributed, input / output / cache
  tokens, % cached, cost, % of total. Attribution model: a slash-prefixed
  user prompt sets the "current skill" for that prompt and its follow-up
  turns; a Skill-tool invocation overrides attribution for its own turn.
  Slash-prefixed keys (e.g. `/session-metrics`) are de-slashed so they
  merge with Skill-tool invocations of the same name.
- **Subagent types** — one row per resolved `subagent_type` (from
  `Agent` / `Task` tool_use `input.subagent_type`). Shows spawn count
  always; token/cost columns populate from subagent JSONLs (default behaviour —
  pass `--no-include-subagents` to skip).

**UUID-based dedup** runs at project and instance scope to prevent
resumed-session replays from double-counting. Session scope keeps the
existing `message.id` streaming-split dedup.

### Subagent → parent-prompt attribution (v1.7.0 — Phase B)

Subagent token usage is included by default and rolls up onto the **user prompt** that originally triggered the chain:

- Three new turn-record fields populate on the spawning prompt's row —
  `attributed_subagent_tokens`, `attributed_subagent_cost`,
  `attributed_subagent_count`. They are **purely additive**:
  `cost_usd` / `total_tokens` on every turn (parent and subagent) are
  unchanged, so existing aggregators and the session total are
  untouched. Display layers read both columns separately.
- **Nested chains** (subagent A → subagent B) attribute B's tokens onto
  the **root** user prompt, not onto A. Implemented via an iterative
  resolve over `(tool_use.id, agentId)` linkage extracted from the
  parent's `toolUseResult.agentId` fields, with a cycle guard.
- **HTML prompts table** sorts by `cost_usd + attributed_subagent_cost`
  by default (configurable via `--sort-prompts-by`). A new "Subagents
  +$" column is auto-shown when at least one top-20 row has attributed
  cost. The prompt snippet gains a "+N subagents" badge.
- **CSV per-turn export** always includes the three attribution columns
  (zero on rows without spawn activity) — column count stays stable.
- **JSON report** exposes top-level `subagent_attribution_summary`
  with `attributed_turns`, `orphan_subagent_turns`,
  `nested_levels_seen`, `cycles_detected`. Useful for sanity checks
  when pointing at unfamiliar history.

Disable subagent loading entirely with `--no-include-subagents` (fastest, no subagent token detail).
Disable only the attribution rollup while still loading subagents with `--no-subagent-attribution` (compare against pre-Phase-B reports).

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

## Model comparison

Reached only when `$ARGUMENTS[0]` is `compare`, `compare-run`,
`compare-prep`, or `count-tokens` (see the Dispatch section at the top
of this file).

**Default pair is `claude-opus-4-6[1m]` vs `claude-opus-4-7[1m]`** —
the 1M-context tier, because that matches Claude Code's shipping Opus
routing. Users opt into the 200k-context variants by passing the
unsuffixed IDs explicitly. Mixed-tier pairs are accepted and surface
the existing `context-tier-mismatch` advisory on the report.

| Mode | Use when |
|------|----------|
| `compare-run` *(preferred)* | User wants the report with no manual capture. Orchestrator spawns two `claude -p` sessions via subscription auth, feeds the canonical suite, then runs `--compare`. Zero API key. |
| `compare`                   | Two session JSONLs already exist (either from a prior `compare-run`, or from manual `/model` + paste). Input is a path / UUID / `last-<family>` / `all-<family>` token. |
| `compare-prep`              | Print the manual capture protocol. Only suggest when `claude -p` is unavailable (e.g. CI container without the CLI). |
| `count-tokens`              | API-key tokenizer smoke test. NOT a subscription path; do not suggest to users comparing two subscription sessions. |

**Output formats for compare mode.** Compare mode supports `--output text md json csv html`. The HTML report is always single-page (a compact scored per-prompt table); `--single-page` and `--chart-lib` are ignored when `--compare` is active.

**`compare-run` auto-extras.** When `compare-run` is invoked with
`--output <fmt>`, it emits the compare report *and* five companion
files in `exports/session-metrics/`: a per-session dashboard + detail
(HTML) and raw JSON for each side, plus a Markdown analysis scaffold
(`compare_<a8>_vs_<b8>_<ts>_analysis.md`) with headline ratios,
per-prompt table, cost decomposition, and a bolded decision-framework
verdict. Prose sections carry `{{TODO}}` placeholders so a follow-up
chat can fill them in. Pass `--no-compare-run-extras` to skip the
companions and emit only the compare report. Without `--output`,
nothing writes to disk (text-only stdout path preserved).

**Custom prompts.** Users can add their own prompts to the comparison suite with
`--compare-add-prompt "text"` — no file format knowledge required. The prompt is
saved to `~/.session-metrics/prompts/` and runs automatically on every subsequent
`--compare-run`. Use `--compare-list-prompts` to preview the active suite and call
count before spending on inference. Use `--compare-remove-prompt <name>` to remove.
Full guide: [`references/custom-prompts.md`](references/custom-prompts.md).

**Prompt steering.** `--compare-run-prompt-steering <variant>` wraps every
prompt in the suite with a steering instruction before feeding it to
`claude -p`. The four built-in variants are `concise`,
`think-step-by-step`, `ultrathink`, and `no-tools`. The wrapper is
applied symmetrically to both sides so the A/B stays clean — what shifts
is the model's behaviour under the same instruction, surfaced as token /
cost / thinking / tool-call deltas. Use
`--compare-run-prompt-steering-position {prefix,append,both}` (default
`prefix`) to control where the steering text lands relative to the body.
IFEval pass rates may differ from the unsteered baseline by design —
predicate breakage (e.g. "be concise" violating the 50-word stacked
constraint) is the *measurement*, not a regression. For multi-variant
sweeps with auto-rendered comparison articles + cross-variant summary,
use the `benchmark-effort-prompt` skill instead.

**Before proposing any compare-mode command, read
[`references/model-compare.md`](references/model-compare.md).** That
doc has the full flag table, four workflow recipes, 4-way Opus combo
matrix, IFEval predicates, advisory semantics, and troubleshooting.
The eager content in this file deliberately stays minimal so
single-session reports don't pay for compare-mode context they don't
use.

## Optional post-export audit

When any `--output` format is specified (`html`, `csv`, `md`, or `json`),
always include `json` in the script invocation if it is not already present.
For example, if the user asked for `--output html`, run the script with
`--output html json`. This ensures the JSON export is always written and the
audit suggestion can always be shown.

After all `[export] FMT → path` lines are printed and the optional
`[self-cost]` line lands, append an audit suggestion based on the export scope.
Determine scope from the JSON filename printed by the `[export] JSON` line:

- `session_*.json` → session scope
- `project_*.json` → project scope
- `instance/*/index.json` → instance scope

**Session scope:**
> Want a token-usage audit of this session?
>   `/audit-session-metrics quick   <json-path>`
>   `/audit-session-metrics detailed <json-path>`  (also reads CLAUDE.md + settings)

**Project scope:**
> Want a per-session cost and cache health audit of this project?
>   `/audit-session-metrics quick   <json-path>`   (surfaces top expensive sessions, cache outliers)
>   `/audit-session-metrics detailed <json-path>`  (also drills into top session turn patterns)

**Instance scope:**
> Want a cross-project cost breakdown audit?
>   `/audit-session-metrics quick   <json-path>`   (per-project cost shares and cache health)

Substitute `<json-path>` with the actual path printed by the
`[export] JSON` line. The audit is summarisation-heavy and reads only the
disk export (not the conversation), so for a ~10× cheaper run the user can
`/model haiku` before invoking — the skill no longer pins a model itself.

**Do not invoke `audit-session-metrics` programmatically from this
turn.** It is a separate, user-initiated audit: running it as its own
slash command keeps the turn focused and lets the user decide when to
spend on it (and on which model). The user runs the slash command at
their own discretion.

## Automatic Tasks companion (no extra command)

The per-request breakdown is the deterministic foundation for **task grouping**
("what was I actually trying to do"). To remove the friction of a separate
`/task-breakdown` step, the Tasks companion is generated **automatically as part
of an HTML export**, in this same turn — the user gets it for free.

**Scope gate — the auto-companion is a single-session feature.** Generate it
only for **single-session exports** (the default route / `--session <id>`).
**Never** auto-generate it for `--project-cost` or `--all-projects`: semantic
task grouping does not span sessions, and hand-grouping hundreds of requests
across many sessions is impractical and not meaningful (this is exactly the
case that produces a single blank "blob" task). At project / instance scope,
skip both the companion and the nav button, and simply tell the user that
`/task-breakdown` can be run manually on a *single* session if they want a
task view.

**When `html` is among the requested formats AND this is a single-session
export AND the auto-companion will actually be generated** (see the count gate
below), add `--task-companion-nav` to the script invocation (alongside the
always-on `json`). This renders a `Tasks` nav button on the dashboard/detail
pages pointing at `<stem>_tasks.html`. Do **not** add `--task-companion-nav`
when you are skipping the companion — it would render a button pointing at a
`<stem>_tasks.html` that was never written (a dead link).

**Then, after the `[export]` lines, if this is a single-session export and the
JSON export's `request_units` array has between 2 and 40 entries**, generate
the companion automatically. Skip when there is only one unit (a single-prompt
session needs no grouping) or when there are more than ~40 units (an unusually
large session — tell the user it is too large for a clean auto-grouping and
that `/task-breakdown` remains available manually).

You are an **editor, not an author**: `--prepare-tasks` does the deterministic
work (clustering, seeded titles, suggested verdicts) and writes a *renderable*
skeleton; you only refine the semantic parts. This is far cheaper than
authoring `grouping.json` from scratch.

1. Run `--prepare-tasks` — it prints a compact per-request worksheet to stdout
   and writes a candidate `<stem>_grouping.json` next to the export:

   ```bash
   uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --prepare-tasks \
     <export.json>
   ```

   The worksheet is your single source of grouping signals — **do not re-probe
   the JSON with `jq`/`Read`.** Each row carries the unit's candidate cluster
   (`cl`), turns, cost, tokens, `risk/reread/cbreak`, idle gap, snippet, and
   tools. `[cont]` = an agent-completion continuation, `[blank]` = a no-prompt
   unit; both are pre-attached to the preceding cluster.

2. **Edit** the skeleton `grouping.json` (do not rewrite it from scratch):
   - **Titles** — replace each seeded title with a real task name, and **remove
     that task's `_auto_title` field** (or set it `false`) once you've named it.
     A leftover `_auto_title` on a task covering >60% of requests trips a
     collapse warning at render time — that is the safety net for an unedited
     skeleton, not a target.
   - **Merge / split** — combine clusters that are one semantic task (rewrite
     the affected tasks' `request_unit_ids`); split a cluster only when the
     worksheet clearly shows two distinct goals (e.g. a real prompt that the
     heuristic over-attached). Keep every `unit_id` covered exactly once.
   - **Rationales** — write a one-line `rationale` per task.
   - **Verdicts** — the skeleton pre-fills `worth_it`/`mixed`; a blank `verdict`
     means the waste signals were high enough that *you* must judge it (use the
     `_hint.suggested_verdict` and the worksheet's `risk/reread/cbreak` as
     evidence — **bias toward `mixed`/`worth_it` when unsure**, never re-sum
     numbers). Override a pre-filled verdict only when you actively disagree.

   The `_auto_title` / `_hint` underscore fields are advisory — the renderer
   ignores them for all cost/coverage math.

3. Run the renderer (it recomputes all totals from the export and validates the
   grouping). Make sure the edited JSON still parses first:

   ```bash
   uv run python ${CLAUDE_SKILL_DIR}/scripts/session-metrics.py --render-tasks \
     <export.json> <grouping.json>
   ```

4. Tell the user the task list (verdicts + turns + cost, read back from the
   renderer's stdout / the rendered `*_tasks.md` — do not recompute) and the
   `*_tasks.html` / `*_tasks.md` paths. The dashboard `Tasks` nav button now
   resolves to that page. If the renderer printed a collapse warning, fix the
   grouping and re-render rather than shipping it.

This is automatic for HTML exports. The standalone `/task-breakdown
<json-path>` skill remains for re-grouping a saved JSON export later without
re-running session-metrics. It is session-oriented; pointing it at a
project-scope export with hundreds of units will produce a coarse grouping at
best, so prefer a single-session export as its input. Keep it lightweight:
most sessions are a handful of tasks; don't over- or under-segment. The
deterministic "Per-request breakdown" section in the dashboard is the honest
*per-request* view; the Tasks page is the *semantic* layer you just authored.

## Self-cost meta-metric

session-metrics tracks its own running cost in the current session.
After the `[export]` lines a `[self-cost]` stderr summary prints the
prior turns' tokens / dollars (the *current* run is not yet written
to the JSONL when the script reads it). The HTML dashboard surfaces
the same number as a "Skill self-cost" KPI card. The JSON export
carries it as the top-level `self_cost` key.

Pass `--no-self-cost` to suppress all three surfaces — useful for
clean test snapshots or for users who find the meta-metric noisy.

## Reference files

- [`references/pricing.md`](references/pricing.md) — Per-model token prices used
  for cost calculation. Read when the user asks about pricing or you need to
  add a new model.
- [`references/jsonl-schema.md`](references/jsonl-schema.md) — JSONL entry
  structure + full output-column semantics, cache-TTL split rationale, content-
  block distribution, resume detection. Read when debugging missing data,
  extending the script, or interpreting any non-obvious column/key.
- [`references/model-compare.md`](references/model-compare.md) — `--compare`
  workflow, prompt-suite catalogue, IFEval predicates, interpretation guide.
  Read when `$ARGUMENTS[0]` routes into compare mode.
- [`references/custom-prompts.md`](references/custom-prompts.md) — Step-by-step
  guide for adding, removing, and previewing custom prompts for `--compare-run`.
  Read when the user asks how to add their own prompts or customise the suite.
- [`references/platform-notes.md`](references/platform-notes.md) — Windows
  `tzdata` caveat for IANA `--tz` names, the `--strict-tz` escape hatch,
  and timezone-contract summary. Read when the user reports a timezone
  warning, asks about Windows support, or wants CI-safe tz handling.

## How session detection works

1. Derives the project slug from `cwd`: replaces `/` → `-`, strips leading `-`.
2. Scans `~/.claude/projects/<slug>/` for `*.jsonl` files (excludes `subagents/`).
3. Picks the most recently modified file as the current session.
4. Override with `--session <uuid>` or `--slug <slug>` when needed.

## Deduplication

Each API response is written to the JSONL multiple times (streaming, tool
completion, final). The script deduplicates on `message.id` — keeping only the
**last** occurrence so token counts reflect the final settled value.
