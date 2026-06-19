# Changelog — session-metrics

All notable changes to the session-metrics skill.
Versions match the `plugin.json` / `marketplace.json` version field.

## v1.83.0 — 2026-06-20

### Audit remediation: chart-tooltip escaping, null-value hardening, share-safe redaction (minor)

A penta-AI code audit (Codex GPT-5.5, DeepSeek V4 Pro, z.ai GLM 5.2, plus a
code-searcher fan-out) found the core token/cost pipeline correct (suite passed)
and surfaced edge-case hardening plus one chart-tooltip defense-in-depth gap.

- **Highcharts tooltip XSS / defense-in-depth.** The 3D bar-chart tooltip
  formatter concatenated the model id (from `message.model`) into its HTML
  string without escaping, unlike the chartrail/costail rails which use a JS
  `esc()` helper. Added the same `esc()` to the Highcharts tooltip. Live
  exploitability was low (Highcharts' AST sanitiser strips event handlers; no
  `useHTML`), but the inconsistency is now closed. (uPlot/Chart.js tooltips
  render via `textContent` and were already safe.)
- **Null-value hardening.** `"input_tokens": null` or `"model": null` in a
  hand-edited / truncated transcript no longer crashes with `TypeError` —
  `_cost`, `_no_cache_cost`, and `_build_turn_record` coerce present-but-null
  values (`… or 0` / `… or "unknown"`). `.get(k, default)` only covered a
  *missing* key.
- **Empty `cache_creation: {}` fallback.** `_cache_write_split` falls back to
  the flat `cache_creation_input_tokens` (5m tier) when the nested object is
  empty or all-zero, instead of silently zeroing the cache-write cost on a
  partial transcript.
- **`--export-share-safe` redaction gap.** The publication bundle now also
  masks `tool_use_detail[].input_preview` (Bash commands, paths, URLs) and
  workflow `agent_details[].promptPreview`/`resultPreview` via a new
  `render_json(redact_tool_io=…)` path. Plain `--redact-user-prompts`
  (cost-analysis use) keeps those previews visible as before.
- **MultiEdit re-access.** `MultiEdit` is now recognised by
  `_summarise_tool_input` (file-path preview) and `_detect_file_reaccesses`,
  matching `_health.py`.
- **compare-mode JSON.** `render_compare_json` now passes `allow_nan=False`,
  matching the main exporter (a poisoned NaN/Infinity fails loudly rather than
  emitting invalid JSON tokens).
- **Docs.** `references/jsonl-schema.md` corrected — the 5m/1h ephemeral split
  and the fast-mode multiplier are shipped, not pending. `audit-extract.py` now
  documents that its $3 default for non-Anthropic models is dormant by design
  (consumed only by cache-activity findings that no-caching providers never
  trigger).

No change to headline cost numbers for normal sessions. Six regression tests
added; suite 1035 passed / 1 skipped.

## v1.82.0 — 2026-06-19

### Bounded task-breakdown worksheet + summary-only report-back (minor)

Closes an output-truncation gap on the **manual `/task-breakdown`** path flagged
by a Claude Code insights report ("Prompt is too long" / output-limit truncation
when a large session's grouping collapsed — e.g. 1,574 request units into one
task). The auto-companion path was already gated (2–40 units, v1.54.0) and the
insights digest already bounded (v1.78.0), but `--prepare-tasks` still printed
one worksheet line per request unit with **no cap**, so a large export flooded
the stdout the editing model reads back.

- **Worksheet cap (`_render_tasks_worksheet`, `_data.py`).** Above
  `_TASKS_WORKSHEET_UNIT_CAP = 120` request units the worksheet now emits a
  bounded per-*cluster* summary (one line per candidate cluster, itself capped
  at 120 with an explicit "(N more clusters omitted)" note) instead of a
  per-unit dump. On a 1,574-unit export, stdout drops from ~190 KB to ~9 KB
  (125 lines). At/below the cap the rich per-unit worksheet is unchanged. The
  written `*_grouping.json` skeleton still covers **every** unit, so it remains
  the authoritative surface the model edits — no unit is hidden, and the
  "model is an editor, not an author" contract holds.
- **Summary-only report-back.** `task-breakdown/SKILL.md` step 7 and the
  auto-companion reference (`references/tasks-companion.md`) now mandate a short
  reply — counts, total cost, coverage %, verdict tallies, warnings, and the
  file paths — and explicitly forbid pasting the full task list / `*_tasks.md`
  inline (the second overflow vector). Up to 3 notable tasks may be named.

1 new regression test
(`test_prepare_tasks_worksheet_is_bounded_on_large_session`); full suite
**1029 passed / 1 skipped**. No change to the auto-companion or insights paths.

## v1.81.0 — 2026-06-16

### Pricing: MiniMax M3, Kimi K2.7 Code, Qwen 3.7 Plus (minor)

Adds explicit OpenRouter pricing keys for three consult-skill models that
previously fell through to family-fallback rates and emitted the
`[warn] … priced at fallback rates` advisory. Rates verified against the live
OpenRouter model pages (2026-06):

- **MiniMax M3** — `minimax/minimax-m3`, $0.30 in / $1.20 out (regex
  `minimax[-_/.]m3(?!\d)`).
- **Kimi K2.7 Code** — `moonshotai/kimi-k2.7-code`, $0.75 in / $3.50 out
  (regex `kimi[-_/.]k2\.7(?!\d)`).
- **Qwen 3.7 Plus** — `qwen/qwen3.7-plus`, $0.32 in / $1.28 out (regex
  `qwen3\.7(?!\d).*plus\b`).

Cache columns are `0.00`, matching every other non-Anthropic entry (these
OpenRouter models don't emit Anthropic-style `cache_read`/`cache_creation`
usage). The predecessor keys (`kimi-k2.6`, `minimax-m2.7`, `qwen3.6-plus`)
are unchanged. New tests cover explicit-rate resolution, silent (non-flagged)
recognition, and `(?!\d)` over-match guards. Full `test_pricing.py`: 106 passed.

## v1.80.1 — 2026-06-14

### Chart-export XSS hardening + assert-strip robustness (patch)

Two fixes from a follow-up multi-AI audit of the v1.71.0–v1.80.0 range; all
citation-verified, 2 new regression tests (full suite 1015 passed, 1 skipped).

- **Chart data is now `</`-escaped before inlining into executable `<script>`
  blocks.** `_build_chart_html` and `_build_lib_chart_pages` embedded their
  `json.dumps(...)` payload verbatim into a `<script>var DATA=…</script>`
  block (Highcharts / uPlot / Chart.js renderers) **without** the
  `.replace("</", "<\\/")` neutralisation the turn-drawer / timeline payloads
  already apply. A `</script>` token in a crafted/odd model id or malformed
  timestamp could close the tag early and inject markup into a shared HTML
  export. Both builders now escape, and `peak_json` (hour-of-day) gets the same
  treatment for parity (it was already safe via `ZoneInfo` validation, hardened
  defensively).
- **`_build_session_blocks` no longer guards a hot-loop invariant with a bare
  `assert`.** `python -O` strips `assert`, so the `turn is not None` check
  vanished under optimised mode; replaced with an explicit `if turn is None:
  continue`. Behaviour is unchanged for valid transcripts.
- **Investigated but NOT shipped:** a generic prefix-sweep "digit-boundary"
  guard in `_pricing_for` (to stop a bare version prefix underpricing a
  glued-digit successor) was rejected — it regresses the intentional Opus-minor
  prefix design (`claude-opus-4-9` catches `claude-opus-4-99` at the NEW tier).
  The dotted-minor underprice risk stays documented policy debt, handled
  reactively per-model via `(?!\d)` regex (as glm-5.1 / glm-5.2 are).

## v1.80.0 — 2026-06-14

### Audit-driven correctness & robustness fixes (minor)

Three fixes from a multi-AI code-analysis audit of the v1.71.0–v1.79.0 range
(session-health + Phases D–G). All citation-verified; 13 new regression tests.

- **`--refresh-pricing` rejects non-finite / negative rates.** The supplement
  loader converted rate fields with `float()`, which accepts `NaN`, `Infinity`,
  `-Infinity` (and `json.load` parses those tokens by default) and negative
  numbers — any of which silently poisoned every downstream cost figure, and
  because the cache tiers derive from `input`, one bad value fanned out to all
  five pricing slots. The loader now skips a model unless every rate is finite
  and non-negative. JSON exports also pass `allow_nan=False`, so a poisoned
  value fails loud instead of emitting invalid `NaN`/`Infinity` JSON tokens.
- **Session outcome no longer mislabels a recovered session as `errored`.** A
  trailing tool-failure streak (≥3 failed tool calls) was treated as "ended in
  a failure spiral" even when the final turn was a clean text-only completion.
  The streak is now zeroed when the last real turn is text-only and ended on
  `end_turn`/`stop_sequence`; the raw `trailing_failure_streak` signal is still
  reported verbatim.
- **Velocity discloses its excluded cohort.** Single-turn / zero-duration
  request units have no measurable wall-clock and are dropped from the
  throughput cohort (the rates stay internally consistent for the timed cohort).
  The HTML cards and Markdown table now state "N excluded — no measurable
  duration" when timed units < total, so the rates aren't read as whole-session.

No interface or flag changes. Behaviour changes are limited to the three cases
above; all other output is byte-identical to v1.79.0.

## v1.79.0 — 2026-06-14

### GLM-5.2 pricing detection (minor)

Adds an explicit rate entry + regex guard for Z.ai's **GLM-5.2** (`glm-5.2`,
including `glm-5.2[1m]` and date/`-air` suffixed variants), priced at the same
tier as GLM-5.1 (input $1.05 / output $3.50 per 1M tokens).

- **Bug fixed:** without the guard, `glm-5.2…` IDs silently prefix-matched the
  cheaper bare `glm-5` entry ($0.60 / $2.08) — a ~43% input / ~41% output
  undercharge — and, because the prefix sweep is the *silent* resolution tier,
  no unknown-model advisory fired to flag it. This is the same `glm-5`-is-a-
  strict-prefix trap already documented for `glm-5.1`.
- The `(?!\d)` boundary keeps a hypothetical `glm-5.20`+ from gluing on (falls
  through to the nearest `glm-5` prefix, matching the `glm-5.10` behaviour).
- Tests extended with `glm-5.2`, `glm-5.2[1m]`, `glm-5.2-air` (→ $1.05) and the
  `glm-5.20` boundary case (→ $0.60).

## v1.78.0 — 2026-06-13

### Auto-insights companion (minor)

A new prose "Insights" companion page (`*_insights.html` + `*_insights.md`)
that Claude writes over a deterministic digest — CLI-only, no new skill. Same
contract as the Tasks companion: **Python owns every number; the LLM writes
only prose.** Two lenses: `summary` (what got done & why) and `effectiveness`
(waste & how to improve).

- **`--prepare-insights <export.json>`** prints a bounded, truncated digest
  (totals, session health/behaviour, velocity, top cost drivers, per-request
  one-liners) to stdout and writes a renderable `<stem>_insights.json`
  skeleton. The corpus excludes no-prompt and agent-continuation units so the
  prose reflects real interactive work, and the per-request list is hard-capped
  with an explicit "(showing N of M)" overflow note for predictable prompt size.
- **`--insights-lens {summary,effectiveness}`** (default `summary`) and
  **`--insights-focus "<text>"`** (optional free-text steering) shape the digest
  and skeleton.
- **`--render-insights <export.json> <insights.json>`** validates the prose and
  pairs it with FACTS recomputed from the export (the prose is never trusted for
  a figure), then writes the themed HTML + Markdown companions. A zero-edit
  skeleton still renders a correct page (facts strip + a "prose not yet written"
  note).
- The HTML companion reuses the workflow-companion shell and renders a tiny,
  safe Markdown subset (`**bold**`, `` `code` ``, paragraphs) — escaped first,
  so prose cannot inject HTML. Theme-var-only styling.## v1.77.0 — 2026-06-13

### Multi-session & temporal analytics (minor)

Five new sections that render only at multi-session scope (`--project-cost` /
`--all-projects`) and auto-hide for single-session reports. All static
(server-rendered HTML, no JS), theme-var-only, with Markdown mirrors and JSON
keys.

- **Session shape distribution** — three side-by-side histograms (duration,
  turn count, cost) over fixed bucket edges, each with p50/p90. Integer
  buckets use inclusive-upper ranges so a session of exactly 5 turns lands in
  the "1–5" bucket.
- **Cache economics** — weighted hit ratio, no-cache counterfactual cost,
  actual savings, savings fraction, and per-session hit-ratio dispersion
  (≥3 sessions). Reads only already-computed totals; never mutates them.
- **Cost concentration** — top-3 share of total spend + a per-item table
  (session id at project scope, slug at instance scope) with a deterministic
  cost/name tie-break.
- **Sessions per hour** — 24-bar chart of distinct sessions active in each
  local hour (distinct from the existing prompt-per-hour chart).
- **Session activity heatmap** — GitHub-style calendar of distinct sessions
  per day, back-filled from the first active day through today so idle gaps
  are visible. Monotonic single-accent opacity ramp (works across all four
  themes).

New JSON keys (multi-session scope only): `session_shape_histograms`,
`cache_economics`, `project_concentration`, `session_activity_by_hour`,
`activity_heatmap`. A single build-time "today" reference is shared across all
heatmaps in an instance run for determinism.

## v1.76.0 — 2026-06-13

### Interactive HTML overlay (minor)

A keyboard-driven interactive layer on every HTML page — all inline JS/CSS, no
new dependency, static-export contract preserved. The palette, find bar, J/K
navigation and help work by reading section headings from the live DOM, so they
cover every section (named or not); the chip nav covers the named sections.

- **Command palette** (`Cmd`/`Ctrl`+`K`) — fuzzy-jump to any section by heading
  text; arrow keys + Enter to select; also offers a "Find in page…" action.
- **Find bar** (`/`) — in-page text search with `<mark>` highlighting, match
  counter, and prev/next cycling (`Enter` / `Shift+Enter`). Excludes the JSON
  data blobs and the overlay's own chrome.
- **Section navigation** — `J` / `]` next, `K` / `[` previous; smooth-scrolls
  and syncs the URL hash (preserving the active `theme=`).
- **Help overlay** (`?`) — a keyboard-shortcut cheatsheet with a close button.
- **Chip nav band** — a sticky row of section chips (shown when ≥3 named
  sections are present), kept in sync with the URL hash; suppressed on sparse
  variants like the detail page.
- The overlay also ships on the three companion pages (Workflows + both Tasks
  pages). All colours come from the existing theme vars, so it adapts across the
  four themes; `/`, `?` and `J`/`K` are suppressed while a text field is focused.

Accessibility: dialogs carry `role`/`aria-modal`, the palette combobox exposes
`aria-controls` / `aria-expanded` / `aria-activedescendant`, the find counter is
`aria-live`, and the palette/help trap and restore focus.

Also: hardened HTML escaping of the per-turn timestamp cell in the timeline
table (a pre-existing gap surfaced during this release's review) — a no-op on
well-formed timestamps, defensive against malformed JSONL.

## v1.75.0 — 2026-06-13

### Static visualizations (minor)

Five new at-a-glance charts in the HTML report, rendered as pure inline SVG —
no new chart-library dependency, all coloured through the existing theme CSS
vars so they adapt across the four themes (beacon / console / lattice / pulse).
Every section auto-hides when its data is absent, so zero-cache, single-session,
and the byte-stable golden fixtures render unchanged.

- **Cache efficiency** (dashboard/single) — a 4-segment proportional token bar
  (cache-read / cache-write / new-input / output) with a cache-read-ratio and
  savings callout. Negative net savings are surfaced as a "Cache net cost"
  (same discipline as v1.74.0's footer/KPI), never a misleading $0.
- **Velocity** (dashboard/single) — KPI cards surfacing the v1.74.0
  `report["velocity"]` throughput stats: cost/active-min, tokens/active-min, and
  p50/p90 request-cycle time. Renders the precomputed values (no recompute), so
  the page never shows two divergent velocity numbers.
- **Cost over time** (detail/single, session scope) — a cumulative stacked-area
  chart of USD by model across the chronological turn sequence (top-5 + Other),
  with a `$`-amount Y axis + gridlines, turn-index X ticks, per-series point
  markers, and colour-matched right-edge model labels.
- **Cost by session** (project/instance scope) — a squarified treemap, one tile
  per session sized by cost, dimming by rank.
- **Markdown mirrors** for cache efficiency and velocity in `--output md`.

Internals: a shared `_svg_scale` coordinate kernel and a `_squarify` treemap
layout (both deterministic, fixed-precision output for reproducible export
bytes). The session vital-signs lane (originally scoped here) is shipped as a
documented no-op stub pending a concrete per-metric lane the chart-rail does not
already cover.

## v1.74.0 — 2026-06-13

### Accuracy & correctness disciplines (minor)

Six correctness hardenings that protect the report's core value — accurate,
reproducible numbers — without changing the common-case output:

- **Deterministic multi-session fold order.** Instance-scope (`--all-projects`)
  cost sums now visit projects in a stable slug order before folding, and the
  merged `content_blocks` / `null_metric_counts` dicts use sorted keys, so the
  JSON/HTML export bytes are reproducible run-to-run regardless of the OS's
  directory-scan order. (Fixes a latent nondeterminism in the per-session fold.)
- **Null-vs-zero discipline.** Totals now carry `null_metric_counts`, recording
  how many turns had an *unmeasured* metric (currently `latency_seconds`, which
  is genuinely absent on a stream's first turn) versus a measured zero — so a
  consumer can read an aggregate as a lower bound rather than assuming full
  coverage.
- **Negative cache savings are surfaced, never hidden.** When cache writes cost
  more than reads saved, the KPI card relabels to "Cache net cost" (amber), the
  per-turn drawer shows "Cache net cost vs no-cache", and the text footer reads
  "Cache cost vs no-cache baseline" — instead of a misleading $0.0000.
- **CSV formula-injection hardening.** Every CSV export (session, project,
  instance, and the two compare CSVs) routes cells through a writer proxy that
  prefixes genuinely-textual cells beginning with `= + - @`/tab/CR/LF with a
  single quote. Numeric strings (e.g. a negative cost) are left untouched, and
  spreadsheets strip the escape on display.
- **Velocity discipline.** A new `velocity` report key reports cost- and
  token-per-active-minute plus p50/p90/mean turn-cycle seconds, computed over a
  single filtered sample (units with a usable duration) with each unit's
  wall-clock capped at 30 minutes so one outlier can't swamp the cohort.
- **Pricing provenance + `--refresh-pricing`.** Reports now embed the rate-table
  snapshot date and the list of any models priced at family-tier fallback (also
  shown as an HTML "Pricing advisory" when present). The new `--refresh-pricing
  <file.json>` flag supplements rates for *unresolved* models only — it never
  overwrites a known model's rate.

No change to existing cost totals or the common-case export bytes; new report
keys are additive.

## v1.73.2 — 2026-06-13

### Fix: Session Health / Behavior sections now theme-aware (patch)

The two new sections rendered as bare unstyled text — they used
`<section class="card">` with a bare `<h2>`, but themed sections use
`<section class="section">` + `<div class="section-title"><h2>…</h2></div>`
and the boxed "card" look comes from a panel styled with theme CSS
variables. Restructured both to the canonical section markup, wrapped the
body in a new `.health-panel` (border/background via `--border` /
`--surface-deep`, so it matches across all four themes — Beacon, Console,
Lattice, Pulse), added `.health-panel .mini-table` styling for the penalty
table, and switched inline `var(--muted…)` to the real `var(--fg-dim…)`
theme variable. Verified visually in Chrome across all four themes.

## v1.73.1 — 2026-06-13

### Fix: context-pressure mis-reads the 1M long-context tier (patch)

The per-turn `message.model` in the JSONL drops the `[1m]` long-context
suffix, so a session actually running on the 1M tier looked like the 200K
base model to the session-health context-pressure signal. A peak context of
~436K tokens then reported **218% pressure** (impossible) and, on a
*completed* session, wrongly added the 10-point context-pressure penalty to
the health score. Fixed via a physical invariant: a turn's context can't
exceed the real window, so if the observed peak exceeds the base-tier
estimate the session must be on the extended tier — the window is upgraded to
1M and pressure reads correctly (~45%). Found by exporting a live 1M session.

## v1.73.0 — 2026-06-13

### Session Behavior — adoption, autonomy, archetype signals (minor)

A companion to Session Health: cheap behavioral signals derived from
already-parsed turn data, surfaced as a per-session `session_behavior` object.

- **Session archetype** — quick / standard / deep / marathon, bucketed by
  user-prompt count (≤5 / ≤15 / ≤50 / >50).
- **Autonomy ratio** — tool-carrying assistant turns ÷ user prompts (how far
  the agent runs between human checkpoints).
- **Adoption** — plan-mode used (`ExitPlanMode`/`EnterPlanMode`), subagent-spawn
  count, distinct-skill count + names.
- **Tool taxonomy** — raw tool names normalised into ~8 categories
  (read / edit / shell / search / delegate / skill / web / plan).
- **Termination class** — clean / awaiting_user / tool_call_pending (mechanical,
  distinct from the qualitative outcome).
- **Relationship** — continuation (opens on a compaction summary) vs primary.
- **Behavioral turn typing** — per-turn agentic / thinking / text / other from
  the content-block mix.

Renders as a "Session Behavior" chips section in single-session HTML, a
`## Session Behavior` Markdown section, and the `session_behavior` object in
JSON. No change to cost/token math.

## v1.72.0 — 2026-06-13

### Session Health — a 0–100 score, A–F grade, and outcome verdict (minor)

The skill now renders a verdict on **how a session went**, not just what it
cost. A new per-session `session_health` object (new `_health.py` module)
turns the data the JSONL already carries into an auditable quality signal.

- **Outcome classification** — `completed` / `abandoned` / `errored` /
  `unknown` / `in_progress`, each with a confidence. A recency gate (last
  record vs report-generation time) keeps a *live* session from being mislabelled
  "abandoned"; a trailing tool-failure streak or a `stop_reason=="refusal"`
  marks `errored`; a capitulation phrase in the final reply downgrades a
  "completed" to low confidence.
- **Tool-health pass** — `is_error`-led failure detection (with content-heuristic
  enrichment for older transcripts), longest consecutive-failure streak,
  byte-identical repeated-call (retry) detection, edit-churn detection (a file
  re-edited 3+ times in a tight window), and a per-tool failure-rate table.
- **Context pressure** — peak per-turn context ÷ the model's window (1M long-context
  beta auto-detected), plus a mid-task-compaction flag (tool-name overlap across
  a compaction boundary).
- **Health score** — start at 100, subtract capped per-signal penalties
  (failures/retries/churn/streak/compactions/mid-task/context-pressure/outcome),
  floor at 0, map to A≥90 / B≥75 / C≥60 / D≥40 / F. The score is `null` (not 0)
  when scoring would be misleading (automated, in-progress, or outcome-only data),
  with a `basis` list recording which signals had data.
- **Automated-session gate** — benchmark / warm-up / harness sessions aren't graded.
- **Rendering** — a "Session Health" card + a full breakdown section in single-session
  HTML, mirrored in Markdown, and the `session_health` object in the JSON export.
  Single-session scope only (the grade is intrinsically per-session).

Cost/token math is unchanged. Adds `_health.py` (17th leaf module) and the
model→context-window table in `_constants.py`.

## v1.71.0 — 2026-06-13

### Tool-result + tool-input capture for session-health signals (minor)

Parser groundwork for an upcoming session-health layer. The per-turn
record now retains the data needed to reason about *how a session went*,
not just what it cost — surfaced in JSON exports and ready for the
failure / retry / churn passes that build on it.

- **`tool_results` per turn.** Each `tool_result` the turn received is
  captured as `{tool_use_id, is_error, text}`. `is_error` is read straight
  off the JSONL (present and reliable on tool responses; `null` only on
  older transcripts). `text` is the flattened result content, capped at
  600 chars — enough to carry failure signatures (tracebacks, "command
  not found", stack traces) without bloating exports.
- **`input_hash` + `file_path` per tool call.** Every `tool_use_detail`
  entry now carries a stable 16-char hash of its canonicalised input
  (for spotting byte-identical repeated calls) and the target file path
  for Edit/Write/Read/NotebookEdit (for detecting rapid re-editing of one
  file). Hashing avoids retaining large raw inputs in the export.
- **Redaction.** `--redact-user-prompts` now also masks `tool_results.text`
  (it can echo file contents), leaving `is_error` / `tool_use_id` intact.
- **Docs.** `references/jsonl-schema.md` documents the `tool_result`
  block shape and the `is_error` field.

No change to cost/token math; all additions are new per-turn fields.

## v1.70.0 — 2026-06-11

### Compare-suite v2 — fix `tool_heavy_task` hang + agentic-loop bounds (minor)

Root cause of a reproducible benchmark wedge: the `tool_heavy_task`
prompt asked the model to Read three repo-relative paths
(`.claude/skills/session-metrics/SKILL.md` etc.) that can never resolve
inside the empty `sm-compare-run-*` scratch cwd every `--compare-run`
subprocess runs in. Low/medium-effort models gave up and wrote a
degraded summary (silently measuring failed-Read *recovery*, not tool
fan-out); opus-4-8 at `high` escalated to a filesystem-wide
`find / -path …` that wedged the cell until the per-call timeout
(observed: 90 min per wedge in benchmark-effort-prompt sweeps).

- **Compare-suite v1 → v2.** `tool_heavy_task` now reads three frozen
  fixture files (`references/model-compare/fixtures/compare-fixture-*.md`)
  that `--compare-run` stages into the scratch dir before any subprocess
  fires. Sentinels bumped in all 10 prompts; `_SUITE_VERSION = 2`.
  v1 and v2 `tool_heavy_task` numbers are **not comparable** — the
  existing suite-version checker refuses mixed comparisons by design.
- **New flag `--compare-run-max-turns N`** (default 100, `0` = unbounded),
  threaded as `claude -p --max-turns` to every subprocess. Set far
  above legitimate usage (the heaviest suite prompt needs ~5 turns) so
  it never censors the work-volume signal the comparison measures —
  it is pure insurance against infinite retry loops, independent of
  the prompt fix.
- **Bash-tool timeout env caps** for compare-run subprocesses
  (`BASH_DEFAULT_TIMEOUT_MS=300000`, `BASH_MAX_TIMEOUT_MS=600000`,
  user-set values win) — belt-and-braces after the wedged `find /`
  outlived tool-level expectations in headless mode.
- **benchmark-effort-prompt orchestrator** default `--per-call-timeout`
  lowered 5400 s → 1800 s; with `--max-turns` bounding stuck cells the
  90-min ceiling only prolonged genuinely-wedged cells.

Suite: 830 passed, 1 skipped. New tests cover fixture staging,
`--max-turns` threading/opt-out, and the env caps.

## v1.69.1 — 2026-06-11

### Fix crashing `--help` (patch)

`session-metrics --help` crashed with `ValueError: unsupported format
character ','` — the `--invariants` help string contained an unescaped
`%` ("cache hit %, …"), which argparse expands as an old-style format
specifier. Escaped to `%%` (matching the two already-correct
`--invariants-*` strings in the same file). AST-scanned every argparse
`help=` string across the skill payload for other unescaped `%`: none
remain. No behaviour change beyond `--help` now printing; suite 826
passed.

## v1.69.0 — 2026-06-11

### Refusal-aware IFEval scoring + effort-support reference (minor)

Preparation for cross-model benchmarks against `claude-fable-5[1m]`
(whose model-side safety classifiers can decline a prompt with
`stop_reason: "refusal"`, HTTP 200, empty text):

- **Refused runs are excluded from IFEval, not failed.** Previously a
  refusal produced empty assistant text that scored `✗` against the
  predicate — logging an instruction-following failure for a run where
  no instruction was ever attempted, and biasing pass-rate deltas
  against classifier-bearing models. A turn whose `stop_reason` is
  `refusal` now scores `None` (rendered `—`, same as no-predicate
  prompts), drops its pair from the pass-rate/McNemar denominator, and
  surfaces a `refused-runs` advisory in the report header plus a
  `[warn]` on stderr naming the prompt and side.
- **Paired aggregate now requires both sides evaluated.** The IFEval
  denominator previously filtered on side A only; a one-sided `None`
  (now possible via refusal) would have counted side B's exclusion as
  a fail. For all pre-refusal data both sides were always `None`
  together, so historical numbers are unchanged.
- **New `references/pricing.md` § "Effort support by model".** Verified
  table (Anthropic effort docs, 2026-06-11) of supported effort rungs,
  API defaults, and recommended coding efforts: opus-4-7 / opus-4-8 /
  fable-5 all expose the full `low/medium/high/xhigh/max` ladder; every
  current model defaults to `high`; Anthropic recommends `xhigh` for
  opus-4-7/4-8 coding work but `high` for fable-5.

## v1.68.0 — 2026-06-10

### Accuracy + perf batch — shared derived-field helper, synthetic-turn consistency, parse-cache prune fix (minor)

From the 2026-06-10 export-accuracy verification (project export recomputed
independently against 524 raw JSONLs; totals matched to 0.12%):

- **`totals.turns` now equals the per-model table sum at every scope.**
  Non-billable `<synthetic>` placeholder turns (orchestrator/resume markers,
  zero tokens, zero cost) were counted in the headline `turns` but skipped by
  the model breakdown, leaving an unexplained gap (49 turns on the dev-repo
  project export). They are now excluded from `turns` and surfaced in a new
  additive `synthetic_turns` totals field (session, project, and instance
  scope). `thinking_turn_pct` / `tool_call_avg_per_turn` use the billable-turn
  denominator.
- **Shared `_derive_total_fields` helper** — `_totals_from_turns`,
  `_add_totals`, and the instance-scope `_aggregate_totals` previously
  implemented the same eight derived fields (`total`, `total_input`,
  `cache_savings`, `cache_hit_pct`, `partial_hit_rate`, `thinking_turn_pct`,
  `tool_call_*`, `tool_names_top3`) independently — the three-way drift that
  caused the v1.63.0 instance-parity bug. All three now delegate to one
  helper in `_data.py`, so the formulas cannot diverge across scopes.
  Guarded by a fold-vs-single-pass parity test.
- **Parse-cache prune no longer deletes live subagent/workflow blobs.**
  `_prune_cache_global`'s orphan check globbed `*/subagents/*.jsonl`, which
  matches no real layout — subagent transcripts live at
  `<slug>/<session>/subagents/*.jsonl` and dynamic-workflow agents one tier
  deeper (`.../subagents/workflows/<runId>/*.jsonl`). Every subagent blob was
  therefore deleted as "orphaned" on each daily prune and cold-parsed again on
  the next project run. Both real depths are now indexed (legacy depth kept).

## v1.67.0 — 2026-06-10

### Export-audit Phase 3 — export-dir hygiene, index manifest, `--prune-exports` (minor)

The export directory had grown to 6 GB / ~390 flat files in the dev repo with
no way to browse or reclaim it, plus four latent path bugs. All from the
2026-06-10 export audit:

- **`index.html` manifest at the export root** — refreshed after every
  export (session/project/instance and `--render-tasks`). Groups every file
  by run stem, newest first, with per-file links (`dashboard · detail ·
  json · tasks …`), per-run sizes, a latest-run-per-scope strip, and audit
  sidecars listed beside their session run. Relative hrefs only, so the
  directory stays portable. Failure-tolerant: a manifest error warns and
  never breaks the export. A text-only run writes nothing and creates no
  directories.
- **`--prune-exports N`** — keeps the newest N runs per retention group
  (each session id, the `project` series, each compare pair, the dated
  instance dirs) and deletes older runs' files. **Dry run by default**;
  add `--yes` to actually delete (the existing flag, help text extended).
  `audit_*` sidecars and unrecognised files are never touched. On the dev
  repo's real export dir, `--prune-exports 3` reports 5.3 GB reclaimable
  across 147 runs.
- **Same-second collision guards** — a run timestamp that would collide
  with existing files (`_unique_run_ts`) or an existing instance dated dir
  advances one second instead of silently overwriting the earlier run
  (back-to-back A/B exports hit this).
- **`_export_dir` self-nesting guard** — running from inside an
  `exports/session-metrics` directory no longer creates a nested
  `exports/session-metrics/exports/session-metrics` (one such stray empty
  dir existed on disk).
- **Instance dated dirs unified onto the `YYYYMMDDTHHMMSSZ` grammar**
  (was `YYYY-MM-DD-HHMMSS`). The audit companion's `audit-extract.py` and
  the manifest/prune scanners accept both, so pre-existing dirs keep
  working.
- **Tasks nav can no longer dangle** — `--task-companion-nav` now writes a
  themed placeholder page at `<stem>_tasks.html` at export time, so the
  nav button resolves even when the task-breakdown flow is skipped (e.g.
  the 2-40 request-unit gate fails); `--render-tasks` overwrites it.
- **Companion Back links got real hrefs** — the workflows and Tasks
  companion pages' `← Back` anchor now carries the dashboard filename as a
  real `href` (kept the `history.back()` onclick for in-flow navigation),
  so the link works when the page is opened directly in a fresh tab.
- **Docs**: SKILL.md/README filename grammar fixed
  (`<YYYYMMDD_HHMMSS>` → the actual `<YYYYMMDD>T<HHMMSS>Z`), new flag and
  manifest documented.

Tests: +9 (export-dir guard, unique-ts, scanner grouping, prune dry-run/yes
semantics, manifest content, placeholder, companion Back href); one
existing compare test's `*.html` glob tightened to `compare_*.html` (it
was picking up the new manifest). **821 passed, 1 skipped.**

## v1.66.2 — 2026-06-10

### Export-audit Phase 2 — Markdown share-line dedup + render/instance performance (patch)

One user-visible bugfix plus three performance changes from the 2026-06-10
export audit, all guarded by frozen-input A/B comparisons (instance JSON/MD
byte-identical outside `generated_at`/`skill_version`/wall-clock `now_epoch`;
session HTML identical after masking only the intended restructure):

- **Markdown: duplicate "Subagent share of cost" row removed.** Since
  v1.65.0 the MD Summary table emitted the row twice — the original
  emission after *Total cost* plus a second one added in v1.65.0 under the
  belief the row was missing. The row now appears exactly once (original
  position), and `render_md` consumes the precomputed
  `subagent_share_stats` instead of recomputing.
- **Renderers reuse precomputed stats.** `render_html`'s subagent-share /
  attribution-coverage cards and the within-session split (HTML + MD) now
  read the values `_build_report` already stamps on the report
  (`subagent_share_stats`, `subagent_within_session_split`), with the
  recompute kept only as a fallback — the same guard pattern the instance
  renderers already used.
- **Time-of-day epoch array embedded once instead of three times.** The
  hour-of-day, punchcard, and day-part heatmap sections shared a single
  `<script type="application/json" id="tod-epoch-secs">` blob and
  `JSON.parse` it, instead of each inlining its own `var TS=[...]` copy of
  the largest data payload on the page (−10.5% page bytes on the A/B
  fixture; more on prompt-heavy instances).
- **Instance scope: slimmed raw turns + single aggregation walk.**
  `--all-projects` previously held every project's full raw JSONL entries
  (including message content) in memory through the entire rendering
  phase; each turn is now projected down to the `timestamp` +
  `message.{usage,model}` fields `_build_session_blocks` actually reads,
  and the originals are dropped once per-project reports are built.
  `_aggregate_models` and `_aggregate_totals` now share one turn walk
  (tool-name counts collected during the models walk and injected) instead
  of walking every turn twice.

Suite 812 passed / 1 skipped (8 new regression tests: MD single-emission +
stamped-stats preference, shared epoch blob, slim-turn equivalence,
single-walk equivalence). Ruff: identical pre-existing findings, 0
introduced. No cost or token math changed.

## v1.66.1 — 2026-06-10

### Export-audit Phase 1 — accuracy quick wins (bugfix-only patch)

Four fixes from the 2026-06-10 three-agent export audit, each verified by a
quad-AI consult (Codex GPT-5.5 + DeepSeek V4 Pro + GLM 5.1 + code-searcher)
before landing:

- **`by_skill` invocation double-count fixed.** A slash command answered by a
  `Skill` tool_use for the same skill on the same turn counted as 2
  invocations; it now counts as 1. Tokens/cost were never affected — only the
  `invocations` column. The Phase-A regression test that encoded the old
  count (`>= 2`) now asserts `== 1`.
- **5h-block `cache_write` reads the nested ephemeral split.**
  `_build_session_blocks` read only the legacy flat
  `cache_creation_input_tokens`; it now mirrors `_cache_write_split`
  (nested `ephemeral_{5m,1h}_input_tokens` first, flat as fallback). No
  number changes today — current transcripts dual-populate both — but the
  blocks table no longer silently zeroes if the flat field is dropped.
- **Instance `totals.content_blocks` always present.** `_aggregate_totals`
  attached the key only when a count was nonzero; it now stores it
  unconditionally, matching session/project totals schema.
- **HTML escaping parity.** `render_html` now escapes `slug` in
  `<title>`/`<h1>` (parity with the instance renderer), `nav_sibling` in the
  topbar link, `tz_label` in the timeline legend/header, and the
  content-blocks `title=` attribute.

Also adds a drift-guard test asserting every `always_on: False` usage
insight carries a 0-100 percentage value — the headline pick is a `max()`
over those values and is only meaningful on a uniform scale. (The audit's
original "unit-incomparable headline ranking" finding was REFUTED by the
consult: count-valued insights are all `always_on: True` and already
excluded; no behaviour change.)

## v1.66.0 — 2026-06-10

### Recognise Claude Fable 5 — new premium model family ($10/$50)

Fable 5 (shipped 2026-06, Claude Code CLI first) is a new Anthropic model family
on its **own premium tier** — $10 input / $50 output, distinct from Opus,
Sonnet, and Haiku. Before this release a Fable 5 session priced at the Sonnet
`_DEFAULT_PRICING` ($3/$15) fallback and emitted the at-exit unknown-model
advisory on every run (a ~70% cost under-count).

`claude-fable-5` is now a first-class **bare-major** key in `_PRICING`: as a
prefix it catches every `5.x` minor + `[1m]` context tag + date suffix in one
entry. Cache columns follow the standard Anthropic ratios off the $10 base
(read 0.1× = $1, 5m-write 1.25× = $12.50, 1h-write 2× = $20). A dedicated
family fallback holds the Fable 5 tier for un-keyed future majors
(`claude-fable-6`+) rather than letting them default to Sonnet. The
audit-session-metrics input-rate table gains a matching `claude-fable-5` entry
so cache-break impact estimates stay in parity. New `test_pricing.py` coverage:
explicit/silent resolution, minor/date/`[1m]` variants, and the future-major
fallback.

## v1.65.0 — 2026-06-05

### Subagent share card — disclose spawned-but-unattributed subagents (+ Markdown parity)

When `--include-subagents` is on and a report spawned subagents but attributed
**zero** child turns to them, the dashboard previously showed "0% — no subagent
activity", which read as *nothing happened*. It now discloses the real
situation: "**N subagents spawned · no attributed child turns**" (HTML card with
a tooltip noting the child transcripts may belong to a prior resumed or
compacted session), so the missing attribution is visible rather than silently
flattened to zero.

The same disclosure now also appears in **Markdown** exports: the `Subagent
share of cost` row — previously built but never emitted by `render_md` — is
wired in, giving Markdown parity with the HTML card (the no-data case stays
suppressed, so no misleading 0% line appears). Display only — no change to cost
or token math. Suite **800 passed / 1 skipped**.

## v1.64.0 — 2026-06-05

### Fast-mode pricing premium — `/fast` turns are now priced correctly (was under-reported 2×–6×)

The skill has detected `usage.speed == "fast"` since the `/fast` feature
shipped but never applied the fast-mode price premium, so every Opus turn run
in fast mode was under-costed: by **6×** on Opus 4.6 / 4.7 and **2×** on Opus
4.8 (fast mode is Opus-only). This was the single largest cost-accuracy gap in
the tool.

A new `_fast_multiplier_for(model)` mirrors `_pricing_for`'s full resolution
chain (exact → regex → prefix sweep → family fallback → default **1.0**), so it
handles `[1m]`- and date-suffixed model ids and never invents a multiplier for
an unknown model. The multiplier scales the **primary** token cost only — the
advisor sub-cost is a separate model invocation that may not be in fast mode, so
it is billed unscaled. Applied uniformly in both `_cost` and `_no_cache_cost`
(so the cache-savings delta stays correct on fast turns) and to the
`extra_1h_cost` KPI. A new `--no-fast-premium` flag reverts to standard rates
for before/after parity. The run advisory is now model-aware ("2×–6× per
model") instead of the stale hardcoded "~6×".

### Server-side `web_search` per-request billing

`web_search_requests` was parsed nowhere and silently uncosted. Each
server-side web search bills a flat **$0.01/request** on top of the token rate,
now added in `_cost` / `_no_cache_cost` **after** the fast multiplier (a flat
per-request charge must not be fast-scaled). `web_fetch` remains **token-only**
(no per-request charge) — the schema/pricing docs that implied otherwise were
corrected.

### Two new Usage Insights

- **Output-token-limit turns** — cost-share + count of turns that stopped on
  `max_tokens`, gated ≥5 turns AND ≥5% cost. Framed neutrally: incomplete
  responses often need a follow-up; consider raising max output tokens.
- **Extended-thinking engagement** — cost-share of turns that engaged thinking
  (`content_blocks.thinking > 0`), gated ≥10%. Behavioural, not a thinking-token
  measurement (thinking tokens are billed inside `output_tokens`).

### Two compare-mode bug fixes

- `--compare-run-prompt-steering` set without `--compare-run` was silently
  discarded; it now errors at parse time (exit 2) instead of running with no
  effect.
- IFEval predicate runtime errors were swallowed into a false "✗"; the runner
  now collects the failing prompt names and emits one `[warn]` after the compare
  loop, so a broken predicate is visible instead of masquerading as a model
  failure.

### Token efficiency — lazy-load three SKILL.md sections

The Instance-dashboard, post-export-audit, and Tasks-companion sections (~8 KB
of always-loaded `SKILL.md`) moved to `references/{instance-dashboard,
post-export-audit,tasks-companion}.md`, fronted by actionable dispatch stubs
that name the route-critical flags. The common "how much did this cost?" turn no
longer pays for three unused features' prose on every invocation.

Full suite **799 passed / 1 skipped**; new tests cover the fast multiplier
(6× / 4.8-2× / unknown-1×), advisor-exclusion, cost/no-cache parity, web_search
billing (and web_fetch *not* charged), both new insights' fire/hide gates, the
steering guard, and the predicate-error path.

## v1.63.1 — 2026-06-02

### Fix: instance JSON export leaked a `tool_use_names` dict into `totals`

A penta-AI review (`/consult-codex-deepseek-gemini-zai`) of the v1.63.0
instance-parity work surfaced a regression in `_aggregate_totals`
(`_report.py`): the intermediate tool-name `{name: count}` map was stashed on
the returned `totals` under the public key `tool_use_names`, which then leaked
into instance `--output json` exports (`totals.tool_use_names` rendered as a
**dict**). That collides with the per-turn `tool_use_names` field — a **list**
at every other layer — and is a shape mismatch with session/project totals,
which keep the map under the internal `_tool_name_counts` key and `.pop()` it
before export. The stored map was dead weight: `tool_names_top3` is derived
from the local variable, not the stored key. Removed the storage so the key no
longer appears in any export. No user-visible card changed; `tool_names_top3`
and `tool_call_total` are unaffected (verified by re-running a live
`--all-projects --output json` export).

Added `tests/test_instance.py::test_aggregate_totals_does_not_leak_tool_use_names_key`
(guards both the aggregate dict and the rendered instance JSON) and tightened
the existing parity test's now-vacuous assertion into a real leak guard. Full
suite **781 passed / 1 skipped**.

## v1.63.0 — 2026-06-01

### Instance dashboard — full KPI-card parity with session/project scopes

The all-projects (instance) `index.html` now renders the same KPI cards the
session- and project-level dashboards already had: **Cache savings**,
**Cache hit ratio**, **Total input tokens**, **Cache TTL mix**, **Extended
thinking engagement**, **Tool calls**, **Advisor calls**, and **Partial hit
rate**. Previously the instance hero grid surfaced only raw token/cost
totals, so the cache-savings figure (e.g. ~$21.7k across 55 projects) was
invisible at the aggregate scope even though session/project dashboards
featured it.

Root cause: `_aggregate_totals` summed the additive token/cost fields but
never ran the derived-field pass that `_totals_from_turns` (session) and
`_add_totals` (project) run, so `cache_savings` / `cache_hit_pct` /
`total_input` / `partial_hit_rate` / `thinking_turn_pct` / `tool_call_*`
were all absent at instance scope. It now runs that pass.

Also fixes a latent bug surfaced during review: instance-scope tool-name
aggregation read a per-turn field (`tool_use_names`) off the per-project
`totals` dict (where it never exists — the real `_tool_name_counts` map is
stripped before aggregation), so the Tool-calls card's "top:" names would
have rendered `none`. Tool names are now re-walked from the per-project
turns (mirroring `_aggregate_models`), skipping `<synthetic>` marker turns.

The five secondary cards were extracted from the inline session renderer
into shared `_build_*_card_html` helpers reused by both the session and
instance renderers; session/project HTML output is unchanged. No interface
change for existing users.

## v1.62.0 — 2026-05-31

### Tasks page — per-turn drilldown inside each request

The Tasks companion page (`*_tasks.html`) now lets you drill from a request
down to its individual turns. Expand a task, then click any request row to
reveal a compact per-turn sub-table — turn #, time, model, input / output /
cache-read / total tokens, cost, and tools — mirroring the columns of the main
details report's Timeline row. A `⚠` marks risky turns and a `sub` badge marks
subagent turns (which inherit their spawner's request anchor, so the expanded
row count reconciles with the request's `turns` chip).

Turns are resolved from the export's `sessions[].turns[]`, available at session
and project scope. Instance-scope exports carry no per-turn records, so they
degrade gracefully — the per-request table renders with no turn expansion. All
cost / token figures are read straight from the export (no re-summing). The
toggle is click- and keyboard-accessible. No interface or output-format break.

## v1.61.0 — 2026-05-31

### Per-skill `effort` defaults + Haiku short-session caveat

Both skills now declare an `effort` level in frontmatter, overriding the
session effort while the skill is active:

- **`audit-session-metrics` → `effort: low`.** The audit is summarisation
  over a pre-computed digest (every dollar figure comes from
  `audit-extract.py`, not the model), so low effort matches the work. Watch
  point: the residual risk at low is contract adherence (versioned JSON
  schema, write-order, row caps), not analysis quality.
- **`session-metrics` → `effort: medium`.** The core report path is
  near-deterministic script-relay, but two paths need real reasoning — the
  auto-Tasks companion (merge/split/title/verdict) and compare mode — so
  `medium` (not `low`) protects them from under-thinking while still
  trimming the relay path.

Unlike the removed `model:` pins (v1.56.0 / v1.57.0), `effort` does **not**
change the model, so it leaves the context window intact — it cannot trigger
the 200k-window overflow that the model pins did. `effort` trims output /
thinking volume only; it does not reduce the carried-conversation input that
dominates a long session, so the saving is modest and the `/model haiku`
opt-in remains the big cost lever.

Also added a short-session caveat to every `/model haiku` recommendation
(both `SKILL.md` files + README): the manual cheap path still collapses the
window to Haiku's 200k, so it only applies on short/early sessions.

No script behaviour or export-format change. `_SCRIPT_VERSION` untouched.

## v1.60.0 — 2026-05-31

### quick-run wrapper: `--session <uuid>` override

`scripts/session-metrics-quick.sh` now accepts an explicit session id
(`--session <uuid>`, `-s <uuid>`, or `--session=<uuid>`) and targets that
session instead of auto-detecting the newest one for the cwd's project. The id
resolves across **all** projects (the report script falls back to a global
search by uuid), so you can run it from a **fresh** Claude Code session — low
context, cheap — to export an earlier heavy session's metrics without loading
that session's context.

Argument handling was reworked so `"$@"` now passes through verbatim rather than
wholesale-replacing the defaults:

- When you pass `--session`, the wrapper no longer also injects its
  auto-detected session (previously it relied on argparse last-wins, which left
  a confusing doubled `--session` and a misleading echo line).
- The quick `--quiet --output html json` default is appended for a **bare** run
  *or* a `--session` override that named no `--output` — so `--session <uuid>`
  alone still produces HTML+JSON. Every other flag combo (`--list`,
  `--project-cost`, a bare `--output …`) is left exactly as typed, matching the
  pre-override "any args ⇒ verbatim" contract.
- The echo line now shows the user override (tagged `(user override)`).

No change to `session-metrics.py` behaviour or any export format.

## v1.59.0 — 2026-05-31

### Bundled quick-run shell wrapper

Adds `scripts/session-metrics-quick.sh`, a small portable shell helper for
one-shot exports from any shell. It locates `session-metrics.py` (honouring a
`$SM_PY` override, then its own bundled directory, a project-local checkout, a
user-wide copy, and finally the newest **version-pinned** plugin-cache install),
detects the current project slug + newest session from the cwd, echoes the
picked target, and runs a quiet HTML+JSON export. Any arguments passed
**replace** its `--quiet --output html json` default, so it doubles as a thin
launcher for every script flag. `uv` is preferred, with a plain `python3`
fallback (the script is stdlib-only). No change to `session-metrics.py`
behaviour or any export format.

## v1.58.0 — 2026-05-31

### Audit-remediation batch — 7 fixes (Sessions 153–166 review)

Seven fixes from a critical audit of the v1.46.0–v1.57.0 work, triaged via a
quad-AI second opinion (Codex GPT-5.5, DeepSeek V4 Pro, GLM 5.1) and verified
against source. No change to cost/token math or the request_units cost
invariant. Tests 769 → 777.

- **`--render-tasks` no longer crashes on a malformed grouping.json.**
  `_assemble_tasks` skips non-dict `tasks[]` entries with a warning instead of
  raising `AttributeError` on `raw.get(...)`.
- **Workflow-journal parser honours its no-crash contract.**
  `_parse_workflow_journal` widened its `try/except` to cover the `int()`
  coercions, so a non-numeric journal field returns `None` instead of
  propagating `ValueError`/`TypeError` and breaking the whole report.
- **Workflow agents no longer double-surface.** `_build_by_subagent_type`
  skips turns tagged `workflow_run_id`, so dynamic-workflow agent tokens appear
  only in the Dynamic workflows table, not also in the per-subagent-type table.
- **The non-billable `<synthetic>` orchestrator model is excluded from the
  Models breakdown** (`_model_breakdown` + instance `_aggregate_models`), so it
  no longer shows as a zero-cost phantom row. Adds an end-to-end fixture.
- **A workflow journal with no loaded transcripts now emits a `[warn]`** instead
  of silently dropping the run from the table.
- **`--render-tasks` warns when a grouping.json has no `schema_version`**
  (previously only a present-but-different version warned).
- **Blank per-request snippets render an em-dash** instead of the literal text
  `&mdash;` (the HTML-entity fallback was being double-escaped).

## v1.57.0 — 2026-05-30

### Drop the `model: sonnet` pin from `task-breakdown`

Completes the unpinning started in v1.56.0. `task-breakdown` was the last pinned
sibling (`model: sonnet`). The same mechanism applies: a `model:` pin runs the
inline skill turn on that model, carrying the **entire conversation** as input,
so the effective window becomes that model's — and Sonnet's default 200k would
overflow identically on a long session (e.g. running `/task-breakdown` late in
the same session that produced the export). The skill's own input is small (the
compact `request_units` worksheet), so the cliff is driven by conversation
length, not the skill's data.

Removing the pin makes it run in the session's own model/window. Unlike the
audit, this work is **judgement-heavy** (semantic grouping + worth-it / wasted
verdicts), so the cheap path is `/model sonnet` before invoking — capable
enough for the verdicts, cheaper than a frontier model. **Don't** drop to Haiku
here; the semantic calls need the headroom. Added a `## Model` note to the
SKILL.md, updated CLAUDE.md + the marketplace/plugin descriptions, and a third
`test_*_skill_frontmatter_unpinned` regression guard (one per sibling now).

No script or behaviour change beyond the model the skill runs on. `_SKILL_VERSION`
→ `1.57.0`. All three siblings are now unpinned.

## v1.56.0 — 2026-05-30

### Drop the `model: haiku` pin from `session-metrics` + `audit-session-metrics`

Both skills carried `model: haiku` frontmatter. A model pin runs the inline
skill turn on that model, and the turn carries the **entire conversation** as
input — so the effective context window becomes Haiku's 200k, not the session
model's. On a long session against a 1M-window model (e.g. Opus 4.8), invoking
the skill past ~200k of conversation overflowed Haiku's window → `Prompt is too
long` plus an unexpected auto-compaction, even though the session was only
~30% of its real window. Both skills read their data from disk (the JSONL / the
JSON export) and never need the conversation, so the pin bought a cost saving
at the price of making the skills uninvokable on exactly the long sessions
people most want to measure.

Removing the pin makes each skill run in the session's own model/window — no
more 200k cliff. The cost path is preserved but now opt-in: the audit is
summarisation-heavy over a tiny disk-read input, so `/model haiku` before
invoking gives the same ~10× saving without the window trap. Prose in both
`SKILL.md` files, the README, and the marketplace/plugin descriptions updated
to match.

Note: `task-breakdown` is still `model: sonnet`-pinned and shares the same
mechanism — it would overflow on a long session against a 200k-window Sonnet.
Left as-is for now (its input is the compact `request_units` digest and it's
typically run deliberately); flagged here so it's not a surprise.

No script or behaviour change beyond the model the skills run on; every number
still comes from the deterministic Python. `_SKILL_VERSION` → `1.56.0`.

## v1.55.1 — 2026-05-30

### Hardening: `OSError` guards on the Tasks dispatch write paths

Follow-up audit of v1.54.0 + v1.55.0. Both Tasks dispatch entry points guarded
their JSON *reads* with `try/except OSError` → exit code 2 but left their
`write_text` calls bare, so a read-only / full export directory raised an
uncaught traceback instead of a clean error.

- `_run_prepare_tasks` — the `<stem>_grouping.json` skeleton write is now
  wrapped; on `OSError` it prints a clean error and returns exit 2.
- `_run_render_tasks` — the `_tasks.html` + `_tasks.md` companion writes are
  wrapped together with the same guard.
- +4 regression tests for the previously-untested `_run_prepare_tasks` entry
  point (`tests/test_prepare_tasks_dispatch.py`): happy-path skeleton write,
  missing `request_units` (exit 2), malformed JSON (exit 2), and the new
  unwritable-directory guard (chmod `0o500` → exit 2, root-skipped). 793 pass.

No success-path behaviour change.

## v1.55.0 — 2026-05-30

### `--prepare-tasks`: shift the Tasks companion from author to editor

Token/time-efficiency follow-up to v1.54.0. The auto Tasks companion made the model probe `request_units` and then **author** `grouping.json` from scratch (titles + verdicts + rationales + id assignments) — deterministic data-shaping the script can do itself. New `--prepare-tasks <export.json>` mode does that work and hands the model an editor's job instead.

- **Worksheet** — prints one compact line per request unit to stdout (candidate cluster, turns, cost, tokens, `risk/reread/cbreak`, idle gap, snippet, top tools), replacing the per-unit probing with a single read and never loading full `prompt_text`.
- **Renderable skeleton** — writes a candidate `<stem>_grouping.json` with deterministic, conservative clustering (each real user prompt seeds a task; `↳` agent-completion continuations, blank-snippet no-prompt units, and same-slash repeats attach to the preceding cluster), seeded non-blank titles, and suggested verdicts. A **zero-edit skeleton already renders a correct, non-collapsed Tasks page** (graceful degradation against the "model bails to one blob" failure). The model edits titles/merges/rationales/disputed verdicts instead of authoring from scratch.
- **No `likely_waste` pre-fill.** The suggested verdict is only `worth_it`/`mixed`; above the high-waste threshold it is left blank for the model — pre-filling `likely_waste` would anchor it into rubber-stamping a noisy-signal label.
- **Auto-title collapse guard.** Seeded titles are marked `_auto_title`; a task that still carries its auto-generated title while covering >60% of requests now warns (the v1.54.0 blank-title guard couldn't catch a non-blank seeded title). The model drops `_auto_title` when it names a task, so a real grouping never trips it.
- Both SKILL.md procedures (the session-metrics auto-companion and the standalone `/task-breakdown` skill) are rewritten to the prepare→edit→render flow.
- No change to the grouping `schema_version` (the skeleton's underscore `_hint`/`_auto_title` fields are ignored by the resolver for cost/coverage math). No change to any existing export file's contents.

## v1.54.0 — 2026-05-30

### Task grouping: scope-gate the auto-companion + collapse guardrail

Follow-up to v1.52.0 from live testing. A `--project-cost` HTML export (188 sessions, 1,574 request units) auto-triggered the Tasks companion, which asked the model to hand-author a semantic grouping over all 1,574 units. That is impractical at project scale, so the model collapsed everything into a single blank-titled task — and `--render-tasks` accepted it silently.

- **Auto-companion is now scope-gated to single sessions.** SKILL.md only auto-generates the Tasks companion (and only adds `--task-companion-nav`) for single-session exports with **2–40 request units**. It is never generated for `--project-cost` or `--all-projects` (semantic tasks don't span sessions; hand-grouping hundreds of units is meaningless), and is skipped for unusually large single sessions. This also removes the dead `Tasks` nav button that previously appeared on project/instance dashboards pointing at a `*_tasks.html` that was never written. Standalone `/task-breakdown` remains for manual single-session re-grouping.
- **Collapse guardrail in `_assemble_tasks`.** A blank/placeholder-titled task that covers more than 60% of all requests (with ≥ 3 units total) now emits a warning instead of rendering silently — the degenerate "one big blob" grouping. Anchored on the title (a well-titled single task covering a focused session stays valid); the synthetic "Ungrouped requests" task is excluded. The warning surfaces on stderr and in the HTML/MD "Grouping notes" section. Protects the manual `/task-breakdown` path too.
- **task-breakdown SKILL.md large-scale guidance:** group at session granularity at large scale and never emit a single untitled catch-all.
- +4 tests. No change to any export file's contents.

## v1.53.0 — 2026-05-30

### `--quiet` — keep export stdout small so the `[export]` paths aren't buried

**Added — a `--quiet` / `-q` flag** that suppresses the per-turn timeline on stdout, printing only the legend, scope header, grand-total subtotal, and footer. The `[export]` path lines (and `[self-cost]`) still print. Motivation: a `--project-cost` export across a large project rendered the full per-turn timeline to stdout first (e.g. ~18,800 lines / 1.9 MB for 187 sessions), which the harness spills into an overflow file showing only a 2 KB preview — pushing the `[export] … → path` lines, the actual deliverable, past the visible cut. `--quiet` collapses that stdout to ~80–90 lines regardless of session/turn count (O(1) in project size; the whole per-session loop is dropped in project mode, replaced by a one-line note), so the run stays inline. The full per-turn detail still lands in the written HTML/JSON.

**Changed — SKILL.md now adds `--quiet` to every session and project export command.** When exporting, the per-turn detail is redundant on stdout (it's in the files), so the export shortcuts and Quick-usage examples pass `--quiet`. `--all-projects` is excluded — its instance dashboard text is already compact and the flag is a no-op there.

Session and project scopes only. +3 tests (per-turn-row suppression in session and project modes, default-not-quiet). No behaviour change to any export file's contents.

## v1.52.0 — 2026-05-30

### Task grouping UX: automatic Tasks page, nav button, cleaner request labels

Follow-up to v1.51.0 after live testing — removes the friction of a separate `/task-breakdown` step and cleans up agent-heavy sessions.

**Changed — the Tasks companion is now generated automatically during an HTML export.** session-metrics' SKILL.md, when `html` is requested, runs the export with the new `--task-companion-nav` flag and then (when the session has more than one request unit) groups the request units into semantic tasks and runs `--render-tasks` **in the same turn** — no separate slash command. The standalone `/task-breakdown <json>` skill remains for re-grouping a saved export later.

**Added — a `Tasks` nav button** on the dashboard/detail pages, beside Dashboard / Detail / Workflows, pointing at `<stem>_tasks.html`. Rendered only under `--task-companion-nav` (set by the auto flow) so a raw-script run that skips grouping doesn't get a dangling link. `_tasks_companion_href` is stripped from JSON exports like the workflow one.

**Changed — `<task-notification>` user entries collapse to their `<summary>`.** Background-agent completion notifications used to dominate a request unit's prompt snippet with raw XML (the embedded `<result>` payload). `_extract_user_prompt_text` now collapses each to a clean `↳ Agent "…" completed` label and discards the result body — so on agent-heavy sessions the per-request breakdown and the LLM grouping both read cleanly (e.g. a 146-turn $28 implementation unit now labels as `↳ Agent "Code-searcher design review" completed` instead of `<task-notification> <task-id>…`). The anchor still fires (it is a real work boundary); only the label changed.

**Changed — the `task-breakdown` skill is pinned to `model: sonnet`.** Its core job (semantic grouping + verdict calibration) is interpretive with no deterministic pre-compute helper, unlike the Haiku-pinned `audit-session-metrics` — Sonnet fits the judgement and the input is tiny (the compact `request_units` digest), so the call stays cheap. Note: the automatic in-export grouping (above) still runs under session-metrics' own Haiku model; the Sonnet pin governs the standalone `/task-breakdown` path.

+4 tests (task-notification collapse, Tasks nav-button gating, +2 from v1.51.0 retained); full suite 767 passing.

## v1.51.0 — 2026-05-30

### Task grouping — per-request breakdown + Tasks companion + task-breakdown skill

A three-layer answer to "I think in tasks, not turns": tell apart a 40-turn feature (worth it) from a 40-turn debug loop (waste). Grounded in a quad-AI consult (Codex GPT-5.5 + DeepSeek V4 Pro + GLM 5.1 + code-searcher) — empirically, explicit boundary signals fired only 3× in a real 385-turn session, so task **segmentation is semantic**, not regex; the deterministic layer only carves by user prompt.

**Added — deterministic "Per-request breakdown" section (HTML + Markdown dashboards).** Groups every turn by its existing `prompt_anchor_index` into **request units** — one user prompt plus all the work it drove (follow-up tool turns + attributed subagents). Per unit: turn count, combined cost (incl. subagent cost), tokens, tool histogram, waste signals (risky turns, file re-reads, cache breaks — reusing the v1.8.0 classification), idle gap and wall-clock. Honest framing: this is *per-request*, **not** semantic tasks. Cost-sum invariant holds (`sum(units) == session subtotal`). Exposed in JSON as a top-level `request_units` array (redacted under `--redact-user-prompts`); compound `unit_id` (`<session_id>:<anchor>`) keeps project-scope units distinct.

**Added — `--render-tasks <export.json> <grouping.json>` mode + `*_tasks.html` / `*_tasks.md` companion (the 4th export page).** Renders a themed, collapsible per-task page (cloning the workflow-companion shell) from a Claude-authored grouping file. The grouping only assigns `request_unit_ids` to titled tasks + a verdict (worth_it / mixed / likely_waste) + rationale; **every cost/turn/token total is recomputed from the export — the grouping is never trusted for math.** Validates schema version, duplicate/unknown unit ids, and sweeps uncovered units into a synthetic "Ungrouped requests" task. The workflow companion is untouched.

**Added — `task-breakdown` sibling skill.** Reads `request_units` from a JSON export, groups them into semantic tasks (topical continuity primary; idle gaps a weak confirming-only hint), labels each with an evidence-based verdict, writes `grouping.json`, and invokes `--render-tasks`. session-metrics suggests it after a JSON export (alongside the audit suggestion). Only this Claude-authored layer is allowed to call groups "tasks".

11 new tests (cost invariant, subagent rollup, compound-key isolation, JSON redaction, grouping validation, companion render, CLI writer); full suite 765 passing.

## v1.50.1 — 2026-05-30

### Workflow companion runs collapsed by default

**Changed — the per-run `<details class="wf-run">` accordions on the `*_workflows.html` companion now start collapsed** (dropped the `open` attribute) so the page opens as a scannable list of runs; click any run to expand its phase → agent timeline. Display-only; no data, cost, or attribution change. +1 assertion in the companion render test; full suite 754 passing.

## v1.50.0 — 2026-05-30

### Workflow companion: timestamped naming + Markdown sibling

**Changed — the `*_workflows.html` companion now shares the run's timestamped stem.** It was named `project_<slug>_workflows.html` / `session_<sid8>_workflows.html` (timestamp-less), so it sorted away from the `project_<TIMESTAMP>_dashboard.html` / `_detail.html` files in the export directory. It is now `project_<TIMESTAMP>_workflows.html` (and `session_<sid8>_<TIMESTAMP>_…`), sorting directly beside dashboard/detail. `_dispatch` computes **one** run timestamp shared by dashboard, detail, the companion, and every `_write_output` format (json/md/csv/single-page HTML) — which also fixes a pre-existing ~1s drift where the JSON filename's timestamp differed from the dashboard's. The Dashboard/Detail `Workflows` nav link updates to the new filename in lock-step.

**Added — a Markdown companion `*_workflows.md`.** When `md` is among the requested formats and the report has workflows, a standalone `<stem>_workflows.md` deep-dive is written alongside the HTML companion — the Markdown sibling of `_build_workflow_companion_html`, with one section per run and a phase → agent timeline table (exact per-agent token/cost from transcripts; labels/previews from the journal). The main `.md` export keeps its inline `## Dynamic workflows` summary table. +2 tests; full suite 754 passing.

## v1.49.0 — 2026-05-30

### Theme-aware `*_workflows.html` companion

**Changed — the dynamic-workflow companion deep-dive now supports all four themes** (Beacon / Console / Lattice / Pulse), matching the dashboard/detail pages. It previously shipped its own hardcoded dark stylesheet. `_build_workflow_companion_html` now reuses the main report's full page shell — `_theme_css()`, the topbar theme switcher, and the head/body bootstrap JS — so the picked theme applies pre-paint and persists across navigation via `localStorage['sm_theme']` and the `#theme=` hash. New companion-only CSS (`_workflow_companion_css`) is keyed entirely on the `var(--surface)` / `--border` / `--accent` / `--fg-dim` / `--surface-deep` tokens defined identically across all four `body.theme-*` blocks, so the page re-skins automatically on switch with no per-theme overrides.

**Changed — companion restyled** with a cross-run summary KPI strip (runs / agents / cost / tokens), per-run accordions whose summary now uses pill-style chips, uppercase phase headers, and themed `wf-table` agent timelines (generic `th`/`td` colours inherited from the theme stack; result-preview rows omitted when empty). No data or attribution change — cost/token math is identical to v1.48.0. Verified live across all four themes. +1 regression test asserting the embedded theme stack (11 workflow tests); full suite 752 passing.

## v1.48.0 — 2026-05-30

### Dynamic-workflow (Workflow tool / ultracode) token + cost tracking

**Added — workflow agents are now counted, costed, attributed, and surfaced.** Claude Code's `Workflow` tool fans out to 20–100+ background agents whose transcripts land one directory tier deeper than the parser reached — at `<session>/subagents/workflows/<runId>/agent-*.jsonl` — so **0%** of that spend was previously visible (on a real audit run this was Opus-4.8 work worth $32.59, **46% of the session's total**, completely invisible). `_load_session` now walks that tier (gated by a new `--include-workflows`, default on; requires `--include-subagents`), so the existing per-model pricing tallies workflow agents exactly, including the cache-read-heavy component the run journal omits. The sibling `journal.jsonl` event log is excluded; the `<synthetic>` orchestrator placeholder row is zero-priced via `_pricing_for` so it neither overcharges nor trips the unknown-model advisory.

**Added — a dedicated "Dynamic workflows" cost table at every scope**, plus an auto-emitted companion. A new `by_workflow` aggregate (keyed by `runId`, cost from transcripts, metadata from the `wf_<runId>.json` journal) renders as a sortable table on the session/project/instance HTML dashboards, a `## Dynamic workflows` Markdown section, a `# DYNAMIC WORKFLOWS` CSV block, and a `by_workflow` JSON array. When a report contains workflows, a standalone `*_workflows.html` companion is written next to the main export with a per-run `<details>` **phase → agent timeline** (exact per-agent token/cost grafted from transcripts; labels/previews from the journal); both the inline table and a **`Workflows` link in the Dashboard/Detail nav bar** point to it (the companion has a `← back to report` link via `history.back()`). Suppress with `--no-workflow-detail`.

**Fixed — workflow cost now rolls onto the spawning prompt.** Workflow agents carry `parentUuid: null` and no per-agent main-thread tool_use, so Phase-B attribution orphaned them. The main-thread `toolUseResult.runId` + the sibling `tool_result.tool_use_id` now bridge `runId → tool_use_id → spawning-prompt anchor` (captured *pre-dedup* so a resumed session can't lose the link, and the `Workflow` tool_use id is registered in `tool_use_ids` so Pass 1 anchors it). Verified at project scope on two real runs: both attribute with the run's full cost, 0 workflow orphans, no double-count.

**Internals.** New `_build_by_workflow` / `_empty_workflow_row` (`_data.py`), `_parse_workflow_journal` / `_extract_workflow_spawn_links` (`_dispatch.py`), `_build_by_workflow_html` / `_build_workflow_companion_html` (`_html_sections.py`); `workflow_run_id` per-turn field; `workflow_sink` accumulator threaded like `compaction_sink`; `_ZERO_PRICING` / `_SYNTHETIC_MODEL`. `_SCRIPT_VERSION` unchanged (parse-cache blob format is unchanged). 9 new tests (`test_workflows.py`); full suite 750 passing.

## v1.47.0 — 2026-05-30

### Context-compaction timeline markers (Q1c)

**Added — inline compaction dividers + "continued" pill in the HTML detail timeline.** Building on v1.46.0's compaction card, the turn-by-turn HTML report now renders a sky-blue `🗜️ Context compacted (auto|manual) — before turn N · X reclaimed` divider immediately above the first turn that ran on the freshly-compacted context, so the cache-creation spike / cache-read dip on that turn is explained in place. A session that opens on a compaction summary (it continues a prior conversation whose boundary lives in a predecessor JSONL) gets a muted `↩️ Continued from prior conversation` pill on its first turn. Both reuse the existing resume-marker divider styling and leave the real turn row fully clickable.

**Correctness — dividers sourced from the deduped boundary set.** The divider→turn correlation runs in `_build_report` over the already-deduped, subagent-excluded `compaction_events` (not a per-file stamp), so the rendered divider count can never exceed the card's `boundary_count` even though boundaries replay across sibling JSONLs. Each boundary claims the first distinct real turn after it via a timestamp two-pointer walk; a boundary with no following turn (compaction at session end) is still counted on the card but renders no divider. Verified at project scope: 110 boundaries → 110 dividers → 110 stamped turns (0 over-count), 2 continued pills = 2 continuation sessions.

**Internals.** New per-turn fields `is_post_compaction` / `is_continued_from_prior` (defaulted in `_build_turn_record`, stamped by the correlation pass in `_build_report`); rendered in `turn_row` (`_html_sections.py`) alongside the existing clear/resume dividers. No new top-level functions, no `_SCRIPT_VERSION` change.

## v1.46.0 — 2026-05-30

### Context-compaction detection (Q1)

**Added — "Context compactions" report card.** session-metrics now parses `compact_boundary` / `compactMetadata` entries from the transcript (previously ignored entirely) and surfaces them at every scope: a new KPI card on the HTML dashboard (session + project + per-project drilldown) and the instance index; a Summary row plus a dedicated "Context compactions" table in Markdown; and `compaction_events` + `compaction_summary` keys in the JSON export. Each shows the boundary count, the auto/manual trigger split, and total tokens reclaimed (`preTokens − postTokens`). The card auto-hides when a report has no compaction. This explains otherwise-anomalous flow — the cache-creation spike + cache-read drop on the turn right after a compaction is the working context being rebuilt from a summary.

**Correctness — boundaries are deduped and main-session-only.** Two facts were verified empirically against this install. (1) Resume *replays* `compact_boundary` entries across sibling JSONLs (a 206-file project held 136 boundary entries but only 109 distinct uuids; 3 uuids appeared in >1 file), so cross-scope (project/instance) aggregation dedups boundaries on `uuid` with first-occurrence-wins, exactly like turns — extraction now runs *after* the shared `seen_uuids` filter. (2) Subagents get compacted too (their JSONLs carry their own `compact_boundary` entries), so subagent-internal compactions are excluded from this session-flow metric via the `_subagent_agent_id` tag. A real project-scope export reconciles exactly to 109 distinct main-session boundaries (60 auto + 49 manual).

**Internals.** New `_extract_compaction_events` (in `_turn_parser.py`), threaded out of `_load_session` via a `compaction_sink` mutable-accumulator argument (no return-tuple arity change, no second parse — the parse cache is a per-call disk pickle, not in-memory memoized), and aggregated by `_build_compaction_summary` into the report. `_SCRIPT_VERSION` is unchanged — the parse-cache blob format did not change.

**Tests**: +6 (live-shape parse, subagent-boundary skip, continuation-head flag, missing/partial metadata, summary aggregation, end-to-end report). Full suite **738 passed, 1 skipped**. No change to existing report numbers.

## v1.45.1 — 2026-05-29

### Null-safety + prefix-shadow bug fixes (post-audit verified)

**Fixed — a null `message` or `usage` aborted the entire report (P3).** In `_extract_turns`, the assistant branch read `entry.get("message", {})`, whose default fires only on a *missing* key: a present `"message": null` yielded `None` and raised `TypeError` at the `"usage" in msg` test, killing the whole run instead of skipping the line. Separately, a present `"usage": null` passed the `"usage" not in msg` guard (key present) and crashed downstream in `_build_turn_record` (`u.get(...)` on `None`). No dispatch path caught `TypeError`. Both now skip cleanly via `entry.get("message") or {}` plus `isinstance(msg.get("usage"), dict)` — the null-safe idiom the sibling user branch already used.

**Fixed — two-digit Opus-4 minors silently 3×-overcharged (P4).** The plain `claude-opus-4-1` ($15 OLD tier) key was a string prefix of `claude-opus-4-10`..`-19`, so the `_pricing_for` prefix sweep priced a future Opus 4.10+ at OLD $15/$75 — a silent 3× overcharge with no unknown-model warning. `claude-opus-4-1` is now an anchored regex `^claude-opus-4-1(?:-|\[|$)` in `_PRICING_PATTERNS` (mirroring the `claude-opus-4` 4.0 treatment), and the Opus-4 minor family fallback gained a `\d{2,}` alternation so two-digit minors route to the NEW $5/$25 tier *with* a warning. Real `claude-opus-4-1` (+ its date / `[1m]` forms) still price OLD-tier silently.

**Fixed — same prefix-shadow in `audit-extract.py`.** The sibling audit skill's substring matcher (`needle in model`) let the `claude-opus-4-1` needle swallow `claude-opus-4-10`..`-19` → $15. Added a `(?!\d)` boundary to `_input_rate_for_model` (mirrors the main script's lookahead), so two-digit minors resolve NEW $5 while real `claude-opus-4-1` stays $15 — preserving the forward/reverse parity guards.

**Fixed — stale comment + reference doc (P5).** Corrected the `session-metrics.py` comment that wrongly claimed `claude-opus-4-99` "falls through and warns" (it resolves to $5 *silently* via the `claude-opus-4-9` prefix). Dropped the stale `claude-opus-4` / `claude-opus-4-1` rows from `references/pricing.md`'s prefix-match table — both are anchored regexes now, not prefix entries.

**Verified not-a-bug — 1M-context premium.** A quad-AI second-opinion review (+ Anthropic pricing docs) confirmed current Opus 4.6–4.8 and Sonnet 4.6 bill the full 1M window at standard rates, so `pricing.md`'s choice not to model a >200K premium is correct. No change.

**Tests**: +5 — two-digit-minor NEW+warn, `claude-opus-4-1` OLD silent, `claude-opus-4-99` silent, audit-extract two-digit parity, and null-`message`/null-`usage` skip. Full suite **732 passed, 1 skipped**. No behaviour change for any currently-shipping model.

## v1.45.0 — 2026-05-29

### Switch the main skill to `model: haiku` + fix `glm-5.1` suffix mispricing

**Changed — `session-metrics` now runs on Haiku.** The main skill's frontmatter flips `model: sonnet` → `model: haiku`. The run-model only does mechanical dispatch: literal-equality `$ARGUMENTS[0]` routing, ordered first-match-wins export-shortcut scanning, and JSON-filename scope detection for the audit suggestion — all string-matching, no interpretive analysis (the interpretive work lives in the already-Haiku `audit-session-metrics` companion). The compare-mode auto-dispatch gate and the literal-only routing instructions are model-agnostic and already explicit in the frontmatter + dispatch section, so they carry over unchanged. Net effect: the report run is ~10× cheaper with identical output, since every number comes from the deterministic Python script.

**Fixed — stale rationale in the audit-invocation guard.** The "do not invoke `audit-session-metrics` programmatically" note previously justified itself with a "keeps the parent's *Sonnet* model and erases the cost win" argument. With the parent now on Haiku that cost delta no longer exists; the note is rewritten to rest on turn-isolation + the entry-point model-override mechanic, which remain valid.

**Fixed — `glm-5.1` suffixed variants undercharged.** `glm-5` is a strict prefix of `glm-5.1` and precedes it in `_PRICING`, so the prefix sweep in `_pricing_for` returned the cheaper `glm-5` rate ($0.60/$2.08) for any suffixed `glm-5.1` ID (`glm-5.1-air`, `glm-5.1:1m`, `glm-5.1-20260101`) — a silent ~43% input / ~41% output undercharge with no unknown-model warning. Added a `glm-5\.1(?!\d)` regex to `_PRICING_PATTERNS` (mirrors the existing `glm-5-turbo\b` guard) so suffixed variants resolve correctly before the prefix sweep. `references/pricing.md` already documented `glm-5\.1` as the intended matcher — this brings the code in line with the reference. `(?!\d)` keeps a hypothetical `glm-5.10`+ from gluing on.

**Fixed — `_add_totals` docstring overclaim.** The fold helper's docstring claimed byte-equivalence to a single `_totals_from_turns` pass; corrected to note integer fields are exact while derived float fields may differ by at most a rounding ULP (pairwise sum vs. one accumulator).

**Tests**: added 6 `glm-5` / `glm-5.1` cases to the pricing-boundary parametrize (exact keys, date/`:1m`/`-air` suffixes, the `glm-5.10` boundary). Full suite 727 passed, 1 skipped.

## v1.44.0 — 2026-05-29

### Pre-provision the next wave of Opus / Sonnet / Haiku models + harden `[1m]` fallback

**Added — 10 first-class pricing keys ahead of release.** So the next models are recognised the moment they ship (no spurious unknown-model warning, no `[1m]` mispricing), `_PRICING` now carries explicit keys at each family's current rate: Opus `claude-opus-4-9` and bare-major `claude-opus-5` ($5/$25 new tier); Sonnet `claude-sonnet-4-8`, `claude-sonnet-4-9`, bare-major `claude-sonnet-5` ($3/$15); Haiku `claude-haiku-4-6/4-7/4-8/4-9` and bare-major `claude-haiku-5` ($1/$5). `claude-sonnet-4-7` was already explicit. The rates are **assumptions** at family-current pricing — review each when the model actually ships.

**Why bare-major keys for the 5.0 generation.** A single `claude-opus-5` / `claude-sonnet-5` / `claude-haiku-5` key catches every `5.x` minor plus its `[1m]` and date-suffixed forms through the exact-match / prefix-sweep path. They live only in `_PRICING`; the sibling audit-extract table keeps them out (its bare `claude-opus`/`claude-sonnet`/`claude-haiku` needles already resolve them, and a major-only needle there would trip the drift guard).

**Fixed — family-fallback `[1m]` evasion, generalised.** The fallback boundary changed `(?:-|$)` → `(?:-|\[|$)` so the `[` of a `[1m]` tag satisfies it. An un-keyed future variant (e.g. a hypothetical `claude-opus-6[1m]`) now prices at its family tier instead of defaulting to Sonnet $3 — the same evasion fixed for `claude-opus-4-8[1m]` via its explicit key in v1.43.0, here extended to any un-keyed major. The unknown-model warning is preserved; only the rate is corrected. The 2-digit-accident guard is unaffected.

**Parity — `audit-extract.py`.** Added minor-versioned rows (`claude-opus-4-9`, `claude-sonnet-4-8/4-9`, `claude-haiku-4-6/4-7/4-8/4-9`) for lockstep with `_PRICING`. Forward/reverse parity tests already passed via the bare needles; these are traceability, not a behaviour change.

**Tests**: flipped three now-explicit keys to known/silent (`claude-opus-4-9`, `claude-opus-5`, `claude-haiku-4-6`); re-targeted the surviving major-fallback tests at `claude-opus-6` / `claude-haiku-9`; added explicit/silent + `[1m]` coverage for the remaining pre-provisioned keys and two `[1m]`-hardening regression guards.

## v1.43.0 — 2026-05-29

### Recognise Claude Opus 4.8 + its 1M-context variant as a first-class model

**Added — explicit `claude-opus-4-8` pricing key.** Opus 4.8 ships at the same new tier as 4.7 ($5 input / $25 output / $0.50 cache read / $6.25 5m-write / $10 1h-write). It is now a first-class entry in `_PRICING` (above `claude-opus-4-7`), so the exact-match path prices it silently and the prefix sweep covers date-suffixed forms (`claude-opus-4-8-YYYYMMDD`).

**Fixed — 1M-context variant mispricing.** Before this release, `claude-opus-4-8[1m]` (the 1M-context tag Claude Code writes into `message.model`) evaded the family-fallback regex — its `(?:-|$)` boundary doesn't match the trailing `[` — and fell through to `_DEFAULT_PRICING` (Sonnet $3/$15), a ~40% under-count. The explicit key catches it via the prefix sweep at the correct $5/$25 tier. Mirrors how `claude-opus-4-7[1m]` already resolves.

**Fixed — spurious unknown-model warning for 4.8.** `claude-opus-4-8` previously routed through the family fallback: correct rate, but flagged into `_UNKNOWN_MODELS_SEEN`, emitting the at-exit `[warn] Unknown model(s)…` advisory on every run. The explicit key silences it.

**Parity — `audit-extract.py`.** Added an explicit `("claude-opus-4-8", 5.00)` row to the sibling skill's `_INPUT_RATE_PER_M_BY_MODEL` for lockstep with `_PRICING` (it was already correct via the bare `claude-opus` substring needle; this is traceability, not a behaviour change).

**Note — >200K-context premium still not modelled.** Consistent with the existing 4-7[1m] treatment; out of scope.

## v1.42.0 — 2026-05-04

### Partial-hit rate + /clear detection + sparkline event markers

**Added — partial-hit rate surfacing.** New `partial_hit_turns`, `total_cache_turns`, and `partial_hit_rate` fields track turns where `cache_read > 0 AND cache_write > 0` simultaneously (prefix extension). Surfaces in: text footer, HTML KPI card, compare-view row, JSON export, and the multi-window 7d/30d/90d/all-time comparison ribbon.

**Added — `/clear` event detection.** Detects `<command-name>/clear</command-name>` entries in the JSONL and marks the next assistant turn with `is_clear_event: true`. Lets users distinguish cache-hit drops caused by context resets (`/clear`) from those caused by context bloat — different root causes, different fixes.

**Added — sparkline event markers.** The per-session cache-trend sparkline now overlays thin vertical lines at context-reset positions: amber for `/clear` events, purple for session resumes. Correlating these markers with cache-hit-rate drops shows whether degradation is from invalidation or bloat.

**Added — `/clear` timeline dividers.** "Context cleared" divider rows appear in the HTML timeline before the first post-clear turn, styled with an amber pill (paralleling the existing resume-marker dividers).

**Tests**: 81 passed / 16 skipped.

## v1.41.11 — 2026-05-03

### Tier 6 close-out — conftest extraction + vendor-charts upgrade docs

Final slice of the upstream Session 142 audit triage plan. Three of the originally-listed Tier 6 items were verified **already shipped** (Proposal A cache-TTL drilldown lives in v1.2.0, all 16 leaf modules already carry top-of-file docstrings, and `tests/browser/conftest.py` already gates browser tests behind `SESSION_METRICS_RUN_BROWSER_TESTS=1`). The remaining items in this skill payload land here as a single bundled patch.

**Added — `tests/conftest.py`.** Lifted the duplicated `isolate_projects_dir` and `_clear_pricing_cache` autouse fixtures out of every `tests/test_*.py` (8 split files since v1.41.9) into a new shared conftest. Pytest auto-discovers conftest.py and applies its autouse fixtures to every test in the directory tree, replacing 8× ~5-line copies with a single canonical declaration. The `sm` reference inside `_clear_pricing_cache` is fetched lazily via `sys.modules.get("session_metrics")` rather than captured at conftest import time, so the canonical module instance loaded by the test files' existing `sys.modules.get(...) or _load_module(...)` dedup pattern is the one whose `lru_cache` gets cleared (no hidden coupling on conftest-vs-test-file collection ordering).

**Removed.** The `@pytest.fixture(autouse=True)` block (decorator + body + comment header) was deleted from each of the 8 split test files (`test_session_metrics.py`, `test_audit.py`, `test_compare.py`, `test_instance.py`, `test_pricing.py`, `test_render.py`, `test_report.py`, `test_time.py`) and replaced with a one-line `# Autouse fixtures live in tests/conftest.py` pointer.

**Changed — `scripts/vendor/charts/README.md`.** Extended with a new *Upgrade procedure* section covering when to bump (patch / minor / major / licence-change / CVE matrix), step-by-step refresh (fetch → regen SHA-256 → verify locally via `_read_vendor_files` → run tests → bump `_SKILL_VERSION`), the `_charts.py` verifier flow (fail-closed at the call site, manifest-as-source-of-truth, `--allow-unverified-charts` is operator emergency-recovery only), and licence-renewal awareness for Highcharts (non-commercial-free, watch upstream-text on each major bump, MIT alternatives `--chart-lib uplot|chartjs` are the documented fall-back).

**Tests**: 703 passed / 1 skipped (unchanged — pure refactor + docs). Verified across 3 consecutive clean runs after one initial flake attributable to a pre-existing test-ordering variance in `test_parallel_dispatch_matches_sequential_output` (added v1.41.10), NOT introduced by the fixture move.

**Why patch bump for what looks like a refactor + docs change.** Both `tests/` and `scripts/vendor/charts/README.md` ship downstream as part of the skill payload — file bytes change in both mirrors, `_SKILL_VERSION` is embedded in every export. Same boring-bump rule as v1.41.8 / v1.41.9 / v1.41.10.

## v1.41.10 — 2026-05-03

### Test-suite — ThreadPoolExecutor parallel-branch coverage

Three new tests appended to `tests/test_instance.py` pin the previously-untested parallel-orchestration path in `scripts/_dispatch.py:_run_all_projects` (L371-376). The `len(project_inputs) > 1` branch was indirectly exercised by existing instance tests but nothing asserted that `ThreadPoolExecutor` was actually used or that its output matched the serial fallback.

**Added** (3 tests, 700/1 → 703/1):

- `test_parallel_branch_uses_thread_pool_when_multiple_projects` — asserts exactly one `ThreadPoolExecutor` is constructed when >1 project is dispatched, with `max_workers ≤ min(8, cpu_count)`.
- `test_single_project_skips_thread_pool` — symmetric assertion: exactly one project takes the `else` branch and never instantiates the pool.
- `test_parallel_dispatch_matches_sequential_output` — runs `_run_all_projects` twice over 3 synthetic projects (real-pool then fake-serial-pool), spies on `_dispatch_instance`, deep-equals all per-project + instance-level reports except `generated_at`. Pins the load-bearing assumption (documented at L350-358) that `_build_report` is pure over `sessions_raw`.

**Pattern**: a small `_TrackingExec` class (context-manager + `.map()` returning serial list) substitutes via `monkeypatch.setattr(sys.modules["_dispatch"], "ThreadPoolExecutor", _TrackingExec)` so the closure inside `_run_all_projects` (which resolves `ThreadPoolExecutor` from module globals at call-time) picks up the fake.

**Why patch bump for a test-only change.** Same as v1.41.9 — `tests/` is part of the skill payload that rsyncs downstream, so file bytes change in both mirrors. Boring-bump rule applies.

## v1.41.9 — 2026-05-03

### Test-suite restructure — bundle the remaining 6 split slices

Six new sibling test files extracted from `tests/test_session_metrics.py` in one bundled commit (Tiers 4.2-4.10 of the post-audit improvement plan). The monolith drops from 10,647 → 1,149 lines (-9,498); the test surface area is now spread across 8 topic-focused modules.

**New files**:

- `tests/test_audit.py` (~1900 lines) — audit-extract.py helper-script tests + golden-file waste-analysis + `_classify_turn` waterfall + retry-chain detection.
- `tests/test_compare.py` (~4720 lines) — all compare-mode phases (1, 2, 3, 4-5, 6, 7, 10, prompt-steering, 8) — the LARGEST single topical block.
- `tests/test_report.py` (~1250 lines) — Phase A (cache_breaks / by_skill / by_subagent_type), Phase B (subagent attribution), Advisor feature.
- `tests/test_time.py` (~880 lines) — time-of-day, hour-of-day, weekday × hour matrix, 5-hour session blocks.
- `tests/test_render.py` (~610 lines) — chart-library dispatch + vendoring, uPlot / Chart.js renderers, Usage Insights section.
- `tests/test_instance.py` (~510 lines) — `--all-projects` discovery, `_build_instance_report` aggregation, `_run_all_projects` orchestration.

**What stays in `test_session_metrics.py`** (1,149 lines): cost-math, prompt-filter, dedup, fixture totals, cache-TTL drilldown (Proposal A), resume detection (Phase 3), content-block distribution (Proposal B), input validation, `_cwd_to_slug`, parse-jsonl perf-regression guard, T1.3-T1.5 advisory tests, v1.41.0 audit-driven fixes (parse_jsonl, dir overrides).

**Pattern**: each new file uses the cross-file module-aliasing dedup (`sys.modules.get(...) or _load_module(...)`) proven in v1.41.8. Two autouse fixtures (`isolate_projects_dir`, `_clear_pricing_cache`) duplicated into each split file because pytest autouse only fires for tests in the declaring module. `_build_fixture_report` (3-line helper) copied into the four slice files that need it.

**Tests**: 700 passed, 1 skipped — perfect parity with the pre-slice baseline. No behaviour change; pure refactor.

## v1.41.8 — 2026-05-03

### Test-suite restructure — pricing tests split into a sibling module

First slice of a multi-step split of the 10,942-line `tests/test_session_metrics.py` monolith. 21 pricing-domain tests move to a new sibling `tests/test_pricing.py` (~370 lines); the source file shrinks to 10,647 lines.

**Tests moved:**

- 13 `test_pricing_*` tests (Pricing block, lines 84–231 of the original)
- 3 `test_pricing_unknown_model_*` tests
- 1 parametrized `test_pricing_regex_boundaries_v1_41_0` (21 cases)
- 4 audit-extract pricing-table tests (`_input_rate_for_model_table`, `_pricing_parity_forward`, `_pricing_parity_reverse`, `_bare_prefix_needles_match_documented_set`)

**Module-aliasing fix.** Both files end with `_load_module("session_metrics", _SCRIPT)`, which re-execs unconditionally — whichever file pytest collects last wins the `sys.modules["session_metrics"]` slot, and leaf modules under `scripts/_*.py` use `_sm()` to fetch the canonical instance from `sys.modules` at call time. Without dedup, the loser file's `sm` reference points to a stale module and `monkeypatch.setattr(sm, "_UNKNOWN_MODELS_SEEN", set())` writes silently miss. Both files now check `sys.modules.get(...)` first; whichever file pytest loads first creates the canonical instance, the other reuses it.

**Cost / cache-write tests stayed put.** Per literal reading of the plan, only tests whose names contain `pricing` (plus the four audit-extract pricing-table tests) move in this slice; `test_cost_*`, `test_cache_write_split_*`, `test_no_cache_cost_*`, and the audit-extract `cache_break_*` tests stay in `test_session_metrics.py` for a future cost-domain slice.

**Tests:** 705 passed, 16 skipped (unchanged — pure file-split, no count delta). Patch bump because the skill payload's `tests/` directory bytes change and `_SKILL_VERSION` is embedded in every export.

## v1.41.7 — 2026-05-03

### Tier 3 from the Session 142 audit triage plan — `_no_cache_cost` symmetry

`_no_cache_cost` (`_turn_parser.py:535`) previously read the FLAT `cache_creation_input_tokens` field directly while `_cost` (line 467) routed the same data through `_cache_write_split` (which prefers nested `cache_creation.ephemeral_*` fields with a flat fallback). Empirically equal today — 55/55 turns per CLAUDE-activeContext.md:430-432 — but a silent future-drift risk: if Anthropic ever stops populating the flat field while keeping the nested ones, `_no_cache_cost` would silently undercount the cache-creation token portion, biasing the "savings from caching" delta downward on every turn. Routed `_no_cache_cost` through `_cache_write_split` and summed the buckets so both functions read the same source of truth.

Behaviour-preserving on real-world transcripts. The existing `test_no_cache_cost_includes_advisor_iterations` test (added in v1.41.4) and the broader cost suite stay green. Tier 2 (drift-guard test module) was added as part of the same audit triage but lives at the dev-repo top-level `tests/` directory and does not ship downstream — see the dev-repo CHANGELOG for those details.

**Tests**: 705 passed, 16 skipped (unchanged — Tier 3 is behaviour-preserving).

Patch bump for export traceability — `_SKILL_VERSION` is embedded in every export so byte-level changes bump the version even when behaviour is unchanged on real-world transcripts.

## v1.41.6 — 2026-05-03

### Tier 1 doc/lint sweep — README cache-format, active-context leaf count, audit-extract bare-prefix removal

Three small fixes from a triple-AI repo audit (Opus 4.7 + Codex GPT-5.5 + DeepSeek V4 Pro). All three correct stale or risky state without changing user-visible behaviour on real-world Anthropic models.

**README cache-format wording**: said "gzipped JSON dump" but the parse-cache format switched to pickle protocol 5 in `_SCRIPT_VERSION = "1.1.0"` (2026-04-30). Replaced with "pickle protocol 5 dump … keyed on file mtime and `_SCRIPT_VERSION`".

**CLAUDE-activeContext.md leaf count**: said "All 13 Graphify-derived sub-modules extracted" but the working tree now has 15 leaf modules (13 Graphify-derived + `_constants.py` + `_time_of_day.py`). Updated to current count without rewriting the historical Session 131 audit reference.

**`audit-extract.py:_INPUT_RATE_PER_M_BY_MODEL` bare-prefix entry**: removed `("claude-opus-4", 15.00)`. The bare prefix substring-matched any future Opus 4 minor (e.g. hypothetical `claude-opus-4-2`) at the OLD $15/M tier — a 3× over-charge on audit impact estimates if Anthropic ever ships such a model. Mirrors the same removal made in `session-metrics.py:_PRICING` in v1.41.2. Audit-extract's substring matcher now falls through to `claude-opus` at $5/M for any future Opus 4 minor — conservative under-charge rather than the prior 3× over-charge. Real Opus 4.0 IDs (`claude-opus-4`, `claude-opus-4-YYYYMMDD`) are an inherent main-vs-audit asymmetry: the main script's anchored regex prices them at $15; audit-extract now prices them at $5. Audit impact estimates are approximate by design and the under-direction is the safer drift mode.

**Tests**: 700 passed, 1 skipped (unchanged). Pricing parity tests stay green because the removed entry was never an exact key in `_PRICING` (the family-fallback regex covered it) and was never in the documented bare-prefix sentinel set `{"claude-sonnet", "claude-haiku", "claude-opus"}`.

Patch bump for export traceability — `_SKILL_VERSION` is embedded in every export so byte-level changes bump the version even when behaviour is unchanged on real-world transcripts.

## v1.41.5 — 2026-05-03

### P7 (partial) from Session 138 audit — `_detect_retry_chains` perf + audit-driven plan close-out

One perf micro-optimisation in `_data.py:_detect_retry_chains`. Existing 700/1 test suite covers the contract; behaviour-preserving change so no new tests added.

**`_detect_retry_chains` perf** — inner loop tokenized each `b_text` twice via `_tok` (once as the `SequenceMatcher` argument, once when reassigning `a_toks` after a match), so a session with `N` consecutive prompts walked `re.findall(r"\w+", text)` `2N(N-1)/2` times in the worst case. Pre-tokenize `prompted` once into a parallel `pre_toks: list[list[str]]` and read both `a_toks` and `b_toks` by index — collapses the repeat-tokenization to exactly `N` calls. Also hoisted `set(chain)` above the cost-summing generator so the inner `if t.get("index") in chain_set` lookup builds the set once per chain rather than once per turn iteration. Pure micro-opt, no behavioural change.

**P7 splits — deferred.** The remaining P7 items (split `render_html` 1310 lines, `_render_instance_html` 276 lines, `_build_report` 207 lines into smaller helpers) are pure cosmetic refactors with no behavioural change and high churn risk on ~1800 lines. Demoted to a separate future refactor release rather than bundled here.

**P8 — already shipped earlier.** The audit's "Sharing-time hygiene" recommendation (`--redact` flag + `chmod 0600`) was already implemented as `--redact-user-prompts` and the umbrella `--export-share-safe` flag (chmods every written export to `0600` and implies `--redact-user-prompts` + `--no-self-cost`). No code change. Documented gap (HTML/MD/CSV/text non-compare exports still embed verbatim prompt text even with `--redact-user-prompts`) is captured for any future expansion ask.

**Audit close-out.** This release closes the Session 138 `/audit-plugin` remediation plan — P1 → P6 shipped across v1.41.2 → v1.41.4, P7 perf shipped here, P7 splits deferred to a dedicated refactor release, P8 already shipped earlier.

**Tests**: 700 passed, 1 skipped (unchanged from v1.41.4 — perf change is behaviour-preserving).

## v1.41.4 — 2026-05-03

### P3 + P4 + P5 + P6 from Session 138 audit — advisor cost edge cases, atomic-replace cache invalidation, coverage gaps

Four audit items landed in one bump. P3 and P4 are dormant defensive fixes (no observable change on real-world transcripts). P5 closes coverage gaps that would have made any of the above silent. P6 is verified clean and closes without code change.

**P3 — advisor cost edge cases** (`_turn_parser.py:467-560`):

- **`_cost` line 488** — `it.get("model", model)` returns `""` when the iteration has the key but its value is empty (the default arg of `dict.get` only fires on missing keys, not empty values). Empty model string fell through `_pricing_for("")` → `_DEFAULT_PRICING` ($3/$15) instead of the parent turn's tier. Fixed with `it.get("model") or model` — collapses both missing-key and empty-string to the parent model. On Opus 4.7 parent the divergence was 60%+ on advisor cost.
- **`_advisor_info`** — same defect path. Function now takes the parent `model` parameter and uses `_pricing_for(adv_model or model)` instead of conditioning on emptiness and falling to `_DEFAULT_PRICING`. The displayed advisor model name (return tuple position 2) still goes `None` when the iteration carries no model — only the rate fallback changed.
- **`_no_cache_cost`** — previously charged the primary turn's tokens at non-cached rates but skipped the advisor iteration loop entirely. On advisor-using turns the "savings from caching" delta (`cost_usd - no_cache_cost`) was biased downward because the cached side included advisor cost while the no-cache side did not. Mirrored the iterations loop from `_cost` so the comparison is symmetric (advisor has no cache fields, so the cached and no-cache forms are identical for that portion).

**P4 — `_parse_cache_key` includes `st_size`** (`_data.py:113-148`):

The cache key was `path_hash + mtime_ns + _SCRIPT_VERSION`. Atomic-replace tools (`cp -p`, `rsync --inplace`, restore-from-backup) preserve `mtime_ns` while changing content — the cache would silently serve the stale pickled blob. Added `st_size` to the key (already in scope at the `path.stat()` call site, threaded through). All existing on-disk blobs are invalidated by the format change; cold rebuild is automatic on first invocation after upgrade. The prune-on-write logic is unaffected — its prefix glob still catches stranded blobs for the same source path.

**P5 — five new tests** (`tests/test_session_metrics.py`):

1. `test_cached_parse_invalidates_on_size` — same `mtime_ns`, different content size → fresh blob (the P4 invariant).
2. `test_cached_parse_invalidates_on_script_version` — bumping `_SCRIPT_VERSION` mints a new key; old blob pruned.
3. `test_weekly_rollup_boundary_inclusivity` — half-open `[start, end)` math at the `now-7d` and `now-14d` cutoffs; an off-by-one swap on either edge would silently double-count or drop a turn at the seam.
4. `test_advisor_empty_model_falls_back_to_parent_rate` — the P3 invariant: empty `iterations[i].model` charges at the parent turn's rate, not `_DEFAULT_PRICING`.
5. `test_no_cache_cost_includes_advisor_iterations` — the P3 symmetry invariant: `_no_cache_cost` mirrors the advisor loop in `_cost`.

`test_parse_cache_key_includes_path_hash` was updated to pass the new `size` argument.

**P6 — verified clean, no code change.** The audit's NOVEL-2 claim (`compute_instance_baseline` reads a wrong field name at `audit-extract.py:998`) was refuted against a live instance-mode export: the export emits both `project_count` (scalar, primary read) and `projects` (list, fallback), so the existing `data.get("project_count", len(data.get("projects", [])))` is correct.

**Tests**: 5 added, 1 updated for new signature. **700 passed, 1 skipped** (was 695 in v1.41.3).

Patch bump per repo policy: any skill-payload byte change bumps `_SKILL_VERSION` for export traceability. The advisor and cache-key fixes are dormant under normal transcripts (real `iterations[i].model` is always populated, real upgrade paths bump mtime), so users see no observable behaviour change — only the defensive fallback shifted to the more accurate path.

## v1.41.3 — 2026-05-03

### P2 from Session 138 audit — pricing-table parity guard between session-metrics and audit-extract

Test-only patch. `audit-session-metrics/scripts/audit-extract.py` carries a hand-maintained `_INPUT_RATE_PER_M_BY_MODEL` table used to estimate cache_break and idle_gap_cache_decay impact. With no automated check, a future Anthropic price change could land in `session-metrics.py:_PRICING` while the audit-extract table silently keeps the stale rate — silently mis-estimating impact on every audit until someone notices.

**Fix**: three new tests in `tests/test_session_metrics.py`:

1. **Forward parity** (`test_audit_extract_pricing_parity_forward`) — every Anthropic-prefixed key in `_PRICING` must resolve to the same input rate via `audit_extract._input_rate_for_model`.
2. **Reverse parity** (`test_audit_extract_pricing_parity_reverse`) — every entry in `_INPUT_RATE_PER_M_BY_MODEL` (excluding three documented bare-prefix catchalls) must resolve to the same input rate via `session_metrics._pricing_for`.
3. **Bare-prefix sentinel** (`test_audit_extract_bare_prefix_needles_match_documented_set`) — keeps the documented exemption set in sync with the table; adding or removing a bare prefix without updating the exemption would silently weaken the parity guard.

The bare-prefix entries (`claude-sonnet`, `claude-haiku`, `claude-opus`) are family-tier substring fallbacks for hypothetical un-versioned Anthropic IDs. Real transcripts always carry a version, so the divergence from `_DEFAULT_PRICING` is dormant; the sentinel test pins the exemption so future changes get reviewed. Non-Anthropic models (glm-*, openai/*, deepseek/*) are intentionally out of scope: cache_break / idle_gap_cache_decay never fire on them because those models lack prompt caching.

**Tests**: 3 added. **695 passed, 1 skipped** (was 692 in v1.41.2).

No production code changed. No behaviour, interface, or export-format change. Patch bump for export traceability.

## v1.41.2 — 2026-05-03

### P1 from Session 138 audit — wrong-model rate fallback for unknown sub-variants

Latent silent-overcharge bugs in `_pricing_for` for hypothetical future Anthropic releases. Surfaced by all four passes of the Session 138 audit (own + perf-fork + Codex + DeepSeek). Two cases collapsed into one fix:

- **`claude-opus-4-N` for N ≥ 8** prefix-matched the bare `claude-opus-4` entry in `_PRICING` and silently 3×-overcharged at OLD-tier $15/$75 instead of NEW-tier $5/$25 (the rate that has held across 4-5/4-6/4-7).
- **`claude-haiku-4-6` / `claude-haiku-5+`** had no Haiku prefix entry at all and fell through to `_DEFAULT_PRICING` (Sonnet $3/$15) — also a 3× overcharge over the correct Haiku $1/$5.

**The fix** has three parts:

1. **Anchored regex for Opus 4.0** in `_PRICING_PATTERNS`: `^claude-opus-4(?:-\d{8})?$` matches the bare ID and an 8-digit-date-suffixed form. The bare `claude-opus-4` key was removed from `_PRICING` so the prefix sweep no longer silently catches future minors.
2. **New `_PRICING_FAMILY_FALLBACKS` list** in `session-metrics.py`, consulted by `_pricing_for` AFTER the prefix sweep miss but BEFORE the `_DEFAULT_PRICING` fallback. Patterns: future Opus 4 minors → NEW tier; future Opus 5+ → NEW tier; future Haiku 4 minors → Haiku tier; future Haiku 5+ → Haiku tier. Each match adds the model to `_UNKNOWN_MODELS_SEEN` so the at-exit advisory tells the user to refresh `references/pricing.md`.
3. **Advisory wording** updated from "priced at Sonnet rates ($3/$15 per 1M tokens)" to "priced at fallback rates (verify in references/pricing.md)" — the family-fallback path lands on the family's tier, not always Sonnet.

**Sonnet intentionally NOT given a family fallback.** `claude-sonnet-4` is a bare prefix entry and Sonnet 4.x has held one rate tier across all minors, so the silent prefix-sweep behavior is correct for Sonnet. A future `claude-sonnet-5` would need an explicit `_PRICING` row regardless.

**Tests**: `test_pricing_prefix_fallback` deleted (asserted the buggy behaviour). Eight new tests cover the bare ID, date-suffixed Opus 4.0, opus-4-8, opus-4-8 with date, opus-5, haiku-4-6, haiku-9, the silent date-suffixed known model path, and opus-4-1-with-date silent path. **692 passed, 1 skipped.**

## v1.41.1 — 2026-05-02

### Internal: ruff hygiene cleanup (no behaviour change)

Silenced the 22 pre-existing ruff errors across the four v1.41.0-modified files. No behaviour change, no interface change, no export-format change. Patch bump is for **export traceability** — `_SKILL_VERSION` is embedded in every export, so leaving the version unchanged after byte-level skill changes would make exports indistinguishable from the prior set.

**4 documented re-imports pinned with `# noqa: F401` + `# noqa: I001`** at `session-metrics.py:30,33,36`. Tests patch them via `sm.secrets`, `sm.ZoneInfo`, `sm.ZoneInfoNotFoundError`; `ruff check --fix` would delete them and break 7+ tests.

**15 cosmetic auto-fixes**: 8 × `timezone.utc` → `datetime.UTC` (UP017) and 7 × redundant `f` prefix removal (F541).

**3 SIM105 — split treatment**: 2 × `try/except: pass` → `with contextlib.suppress(...)` in `_cli.py` (where comments live above the try); 1 × `# noqa: SIM105` in `_data.py:192` where the on-`pass` comment is locality-dependent.

**Tests**: 684 passed, 1 skipped (unchanged from v1.41.0 baseline).

## v1.41.0 — 2026-05-02

### Audit-driven correctness + ergonomic batch

DeepSeek V4 Pro audit (re-validated by Codex GPT-5.5 + code-searcher) surfaced six actionable findings; six rejections were already correct.

**P0-A — `assert` → explicit error/exit at `session-metrics.py:_load_leaf`.** Under `python -O` the assert was stripped and a missing leaf module crashed cryptically. Now mirrors `_cli.py:_load_compare_module`'s explicit `if/print/sys.exit(1)` pattern.

**P0-B — `_PRICING_PATTERNS` regex hardening (behaviour change).** Three fixes:
- Numeric-suffix families (`gpt-5.5`, `qwen3.6`, `mimo-v2.5`, `kimi-k2.6`, `minimax-m2.7`) carry `(?!\d)` — extra-digit IDs (`gpt-5.55`) fall through to default rates.
- Provider/model separators switched from bare `.` to `[-_/.]` — `deepseekXv4Yflash` no longer satisfies `deepseek.v4.*flash`.
- Suffix tokens (`pro`, `flash`, `plus`) anchored with `\b`.

**Behaviour-impact note**: model names that previously over-matched the looser regex now route to default Sonnet rates. Re-run historical reports for accurate before/after.

**P1-A — `_parse_jsonl` defensive `isinstance(dict)` filter.** A stray non-dict line that parsed as valid JSON would `AttributeError` at `_extract_turns`. Now skipped via the same warn path as malformed JSON.

**P1-B — `--cache-dir` flag + `CLAUDE_SESSION_METRICS_CACHE_DIR` env var.** Parse-cache directory gains operator override; same precedence shape as `--projects-dir` (flag > env > default).

**P1-C — `--export-dir` flag + `CLAUDE_SESSION_METRICS_EXPORT_DIR` env var.** Export directory gains the same override shape; `_instance_export_root` flows through automatically.

**P2-A — `@functools.lru_cache(maxsize=128)` on `_pricing_for`.** Removes the redundant three-tier resolution `_cost`/`_no_cache_cost`/`_advisor_info` each performed per turn. Idempotent set side-effect preserved; tests gain an autouse `_clear_pricing_cache` fixture.

`SKILL.md` and `references/pricing.md` updated for parity with the new regex + flags. **684 passed, 1 skipped.**

---

## v1.40.2 — 2026-05-01

### Post-split audit-2 cleanup (P1 + P1b + P2)

Second-pass audit of the 13-module split caught three follow-ups the first audit missed. LSP `findReferences` + Pyright diagnostics surfaced two; the third was already flagged as a latent maintenance trap.

**P1 — `_PROJECTS_DIR_OVERRIDE` dead-seed elimination.** `_cli.py:49` had a leaf-level seed even though every read/write already routed through `_sm()._PROJECTS_DIR_OVERRIDE`. Same shape as the v1.40.1 Bug 2/3 fix for `_VENDOR_CHARTS_DIR` / `_ALLOW_UNVERIFIED_CHARTS`. Leaf seed deleted; canonical attr now defined directly on the orchestrator beside the other two.

**P1b — drop two unused imports.** `_data.py` collapsed `from datetime import datetime, timedelta, timezone` (timedelta unused). `_cli.py` dropped a redundant function-local `import importlib.util` shadowing the top-level import.

**P2 — collapse the `_CACHE_BREAK_DEFAULT_THRESHOLD = 100_000` triplicate.** Three identical literals in `_data.py`, `_dispatch.py`, `_report.py` (default-arg seeds, intentionally retained in v1.40.0 because Python evaluates `def fn(x=_NAME)` at def-time). New `_constants.py` zero-dep sibling leaf holds the single canonical literal. Orchestrator loads it first via `_load_leaf("_constants")` and keeps the module-level alias for runtime reads + tests.

No behaviour change. 653 tests pass, 1 skipped.

---

## v1.40.1 — 2026-05-01

### Post-split bug fixes and import cleanup

Three bugs found by systematic audit of the 13-module monolith split (Sessions 129–132) and corrected in Session 133.

**Bug 1 — `_dispatch.py` cache-break threshold fallback.** `_CACHE_BREAK_DEFAULT_THRESHOLD` in the HTML-render path was a locally-defined constant that ceased to exist in `_dispatch.py` after the split; the value was the same as `_sm()._CACHE_BREAK_DEFAULT_THRESHOLD` so it silently read the right number, but would have drifted if the default ever changed. Fixed to route through `_sm()`.

**Bug 2/3 — `_charts.py` vendor-dir and allow-unverified constants.** `_VENDOR_CHARTS_DIR` and `_ALLOW_UNVERIFIED_CHARTS` were copied into `_charts.py` as seed variables (unnecessary duplicates of the bindings already owned by `session-metrics.py`). All reads inside `_charts.py` now route through `_sm()`. The four tests that patched the now-removed module-local attributes were updated to patch only `sm.*` (sufficient since all paths go through `_sm()`).

**Import cleanup.** Nine imports moved entirely into leaf modules during the split (`io`, `json`, `os`, `pickle`, `time`, `ThreadPoolExecutor`, `datetime`, `timedelta`, `timezone`) removed from `session-metrics.py`. Three imports retained as module-level attributes for test monkeypatching via `sm.*`: `secrets`, `ZoneInfo`, `ZoneInfoNotFoundError`.

**Audit-skill playbook reinforcement.** `SKILL.md` and all five playbook references in `audit-session-metrics` now carry an explicit guard prohibiting intermediate Python synthesis scripts; the Write tool must be used directly to produce JSON/markdown artefacts.

653 tests pass, 1 skipped.

---

## v1.40.0 — 2026-04-30

### Skill version embedded in all exports

`_SKILL_VERSION = "1.40.0"` added to `session-metrics.py`. Every export now surfaces the skill version that generated it: HTML meta line appends `· skill v1.40.0`; Markdown `Generated:` line appends `|  Skill: v1.40.0`; JSON export gains a top-level `"skill_version"` field; CSV exports prepend a comment row `# Session Metrics skill v1.40.0, <generated_at>, <mode>`. `_SKILL_VERSION` must match `plugin.json` / `marketplace.json` and is bumped whenever those bump. CLAUDE.md sync-procedure updated with the instruction.

---

## v1.39.0 — 2026-04-30

### Cache hygiene — daily lazy global prune

`_prune_cache_global` runs at most once per 24 hours (sentinel file in cache dir) on every normal invocation. It deletes three categories of blobs: (1) **orphaned** — the UUID stem matches no JSONL under `_projects_dir()` (deleted project, renamed slug); (2) **inactive session** — source JSONL mtime > 60 days AND blob mtime > 30 days (session long closed); (3) **stale blob** — blob mtime > 30 days even for a semi-active session. The 30 d / 60 d split protects blobs that are being served on warm hits for an ongoing project. Subagent JSONLs (`*/subagents/*.jsonl`) are included in the live-session index so their blobs are not incorrectly treated as orphaned. No new CLI flags; honours `--no-cache`. 647 → 653 passed, 1 skipped.

---

## v1.38.0 — 2026-04-30

### Cache hygiene — self-pruning parse cache (option a)

`_cached_parse_jsonl` now deletes stranded blobs for the same source file on every cache write. Each JSONL has a unique `{stem}__{path_hash}__` prefix in the cache filename; any blob sharing that prefix but not matching the just-written filename was stranded by a previous `mtime_ns` bump or `_SCRIPT_VERSION` change. The prune glob runs only on cache miss (post-successful write) — zero latency on warm hits. Failures are non-fatal; the parse result is always returned. No `_SCRIPT_VERSION` bump (cache schema unchanged), no new CLI flags.

**Motivation.** v1.37.0 switched to pickle (no compression), which is ~2× larger per blob (~9 MB → ~19 MB per typical session). Live sessions receive a new `mtime_ns` on every appended turn, stranding the prior blob each time. At project scale the orphaned files accumulate silently — 768 MB / 1 584 files measured on the dev machine before this was noticed. The per-file prune targets the structural cause (same-source stranding) without a whole-cache scan.

**Stdlib-only, cross-platform, single-user-local trust model.** No new dependencies or CLI surface.

### Tests

Four new tests; one existing test updated to match the new prune behaviour. 643 → 647 passed, 1 skipped.

- `test_cached_parse_prunes_stale_mtime` — mtime bump leaves exactly 1 blob.
- `test_cached_parse_prunes_stale_version` — version bump leaves exactly 1 (new-version) blob.
- `test_cached_parse_prune_does_not_touch_other_jsonls` — prune for source A leaves source B's blob intact.
- `test_cached_parse_prune_failure_is_non_fatal` — read-only cache dir does not propagate OSError; entries are still returned.
- `test_cached_parse_invalidates_on_mtime` updated: now asserts 1 blob post-bump (was 2 pre-prune).

---

## v1.37.0 — 2026-04-30

### Performance — pickle parse cache (-67% cold / -18% warm / -17% project)

Switched the parse cache at `~/.cache/session-metrics/parse/` from gzip+JSON to `pickle` protocol 5 (stdlib, no compression). Single-file change with broad wins across cold parse, warm cache hits, and `--project-cost` fanout on a 158-session corpus.

**Implementation.** `_cached_parse_jsonl` swaps `gzip.open` + `json.load`/`json.dump` for `open` + `pickle.load`/`pickle.dump(protocol=5)`. Filename suffix `.json.gz` → `.pkl`. Read-side exception catch updated from `(OSError, json.JSONDecodeError)` → `(OSError, pickle.UnpicklingError, EOFError)`. Atomic write via random-suffix tmp + `os.replace` is unchanged (POSIX + Windows safe since Py 3.3). `import gzip` removed (no longer used anywhere); `import pickle` added.

**Cache schema bump.** `_SCRIPT_VERSION` 1.0-rc.5 → 1.1.0 invalidates every existing cache blob exactly once. First run after upgrade rebuilds the cache transparently — slower than a warm hit but identical cold-path cost. No data loss; the JSONL transcripts under `~/.claude/projects/` are the source of truth.

**Disk trade-off.** Pickle (no compression) is ~2× larger on disk than the prior gzip+JSON: ~9 MB → ~19 MB for a typical 28 MB JSONL session. At project scale (158 sessions): ~1.4 GB → ~3 GB cache footprint. Acceptable for a developer-tool cache living in `~/.cache/`. Stale cache management (no GC today; mtime_ns and version bumps strand prior blobs) is a known follow-up.

**Stdlib-only invariant preserved.** No new dependencies; the shipped skill remains stdlib-only per `plugin.json` `strict: true`. Cross-platform: identical behaviour on macOS, Linux, Windows. Trust model is single-user-local; pickle of the script's own writes is safe.

### Tests

Four test sites updated to match the new cache extension (`*.json.gz` → `*.pkl`) and docstring ("gzip+JSON" → "pickle"). 643 passed, 1 skipped — same count as v1.36.0.

---

## v1.36.0 — 2026-04-30

### Sharing-time hygiene — `--export-share-safe` one-flag pre-share gesture (P5)

Closes the audit-driven plan's Priority 5 block. Adds a single CLI flag for the common "I'm about to publish or paste this somewhere" workflow, plus README / SKILL.md guidance documenting the redact + share-safe surfaces.

**P5.1 — Documentation for `--redact-user-prompts` + `--export-share-safe`.**
The README gains a new *Sharing exports safely* subsection under *Privacy* with an at-a-glance table of which surfaces are redacted (JSON + compare HTML) versus chmod-only (HTML / MD / CSV / text). The most-used-commands block gains an `--export-share-safe` example. SKILL.md documents both flags in the *Other useful flags* table.

**P5.2 — `--export-share-safe` flag.**
One-flag bundle that implies `--redact-user-prompts` and `--no-self-cost`, and chmods every written export file to `0o600` (`rw-------`) immediately after the write. Wired through `_write_output`, `_dispatch`, `_dispatch_instance`, plus the compare-mode write sites (`_run_compare`, `_run_compare_run`, `_emit_compare_run_extras`) and the split-HTML / per-project drilldown writers — every export-file write site is covered. Implication is applied in `main()` after `parse_args` so all downstream code paths read a consistent argparse namespace regardless of which combination the user typed. Verified end-to-end against a real 361-turn session: 198 turns redacted, 0 with verbatim prompt text, `self_cost` absent from JSON, both files chmod'd to `-rw-------`. Help text explicitly documents the JSON-only redaction caveat (HTML / MD / CSV / text are chmod'd but contain verbatim prompts) so users pair `--export-share-safe` with `--output json` for full redaction.

### Tests

3 new regression tests (argparse implication: `--export-share-safe → redact + no_self_cost`; chmod 0o600 on a written file with `share_safe=True`; default `share_safe=False` does NOT chmod). 643 total tests pass (1 skipped).

---

## v1.35.0 — 2026-04-29

### Insight + sharing — P2 batch (warmup-trigger length cap + JSON redaction)

Two follow-up fixes from the Session 112 audit (P2.3, P2.4). Schema-additive: existing tooling keeps working; new behaviour is opt-in.

**P2.3 — `session_warmup_overhead` now length-agnostic.**
The trigger was previously gated on `len(turns) <= 15`, which silently silenced mid-length sessions where the first turn still dominated cost. A 17-turn session with 30% first-turn cost never fired. The cap is dropped: any session with `first_turn_cost / total_cost > 20%` now surfaces. To keep the signal honest on long sessions, the suggested severity downgrades to `low` (with a `downgrade_reason`) when `total_turns > 30 AND first_pct < 30` — the warmup cost amortises across many turns. Default severity is unchanged (`medium`); the playbook row in `quick-audit.md` was rewritten to match.

**P2.4 — `--redact-user-prompts` wired through `render_json`.**
The `--redact-user-prompts` flag at `session-metrics.py:10719` was silently ineffective on JSON exports — the redact path only ran in compare HTML, while `render_json` wrote full `prompt_text` and `assistant_text` verbatim. The flag now also masks `prompt_text` / `prompt_snippet` and `assistant_text` / `assistant_snippet` on every turn of single-session and project JSON exports with `[redacted]`. Tool inputs, slash-command names, and structured cost / token fields stay visible so the redacted JSON is still useful for cost analysis. Empty fields stay empty (truthiness preserved). No-op for instance-scope JSON, which carries no per-turn records. Help text updated to document JSON coverage explicitly.

### Tests

8 new regression tests (4 for P2.3 length cap + downgrade matrix, 4 for P2.4 redaction including default-off, structured-field visibility, and empty-field preservation). 624 total tests pass (1 skipped).

---

## v1.34.0 — 2026-04-29

### Insight — P2 batch (cost-share + paste-bomb classification)

Two user-visible insight gaps from the Session 112 audit (P2.1, P2.2). Schema-additive: existing tooling that only reads turn counts keeps working; new fields are extra.

**P2.1 — Cost share alongside turn share in Models table + audit playbook.**
`_model_counts(turns)` (returning `{name: int}`) was renamed to `_model_breakdown(turns)` returning `{name: {turns, cost_usd}}` — same shape that `_aggregate_models` already produced at instance scope, eliminating the cross-scope divergence. Markdown / HTML / text Models tables gain `Turn %` and `Cost %` columns. `audit-extract.compute_baseline` (and project / instance variants) emits `baseline.models` as `{name: {turns, turns_pct, cost_usd, cost_pct}}` so the audit playbook's `model_split_clause` renders by-cost without LLM arithmetic. Pre-v1.34 exports (where `models` was `{name: int}`) still parse — `cost_pct` is `null` so the playbook falls back to turn share. The audit playbook rule was rewritten to lead with cost share and add a turn-share aside when the gap is ≥10pp. Verified on a real session: Opus 78% turns / 96% cost — turn share alone massively understates the dominant model.

**P2.2 — `paste_bomb` waste category.**
`_classify_turn` now has a `paste_bomb` arm: prompts >5 000 chars classify as `paste_bomb`, matching the threshold `audit-extract.py`'s detailed scan already used for its `paste_bombs` finding. Fires above `reasoning` in the priority waterfall (paste behaviour is the actionable user signal, thinking is a downstream effect); subagent dispatch still wins. Added to `_RISK_CATEGORIES` and the waste-distribution bar (bright red, between `oververbose_edit` and `dead_end`). Session 112 turns 15/23 (27 KB skill-injected slash-command bodies) — previously classified as `productive` — now surface in the waste bar and per-turn drawer.

### Tests

8 new regression tests (3 for P2.1, 5 for P2.2). 616 total tests pass (1 skipped).

---

## v1.33.0 — 2026-04-29

### Correctness — P1 audit-pipeline fixes (Sessions 113–116)

Four correctness fixes in the `audit-session-metrics` and `session-metrics` audit pipelines, batched together so users get a single coherent release rather than four point-bumps. No schema change. No flag change. The HTML/JSON exports look the same; the underlying numbers are now right.

**P1.1 — `file_re_reads` detector reads `input_preview`** (Session 113).
`audit-extract.py:710-715` previously looked up `tool_use_detail` entries via `d["input"]["file_path"]`, but the export schema only carries `input_preview` (a string from `_summarise_tool_input`). The dict access silently returned `None` on every `Read`, so `detailed_candidates.file_re_reads` was always `[]` regardless of how many times the same path was re-read. Detector now reads `input_preview` directly. Verified end-to-end against a 328-turn export — surfaced 9 real re-read paths where the old detector returned `[]`. (Codex novel finding from Session 112.)

**P1.2 — Per-model input rate for `cache_break` and `idle_gap_cache_decay` impact** (Session 114).
The audit pipeline used a hardcoded `OPUS_INPUT_RATE_PER_M = 5.00` to convert uncached / cache-write tokens into dollars regardless of which model the turn actually ran on, overstating Sonnet by 67% and Haiku by 400%. Replaced with `_INPUT_RATE_PER_M_BY_MODEL` (substring-priority table covering Opus 4.5/4.6/4.7 / Opus 4.0/4.1 / Sonnet 3.x/4.x / Haiku 4.5 / Haiku 3.5) plus an `_input_rate_for_model` helper. `_detect_idle_gap_cache_decay` now reads the turn's `model`; the cache_break trigger sums per-break impact at each break's own model rate and emits a model-aware `impact_basis` (mixed-model variant when breaks span models). Verified end-to-end on a mixed Opus + Haiku export: cache_break impact $1.28 → $0.86 (33% overstatement removed).

**P1.3 — `_BASH_PATH_RE` requires leading-dot or start-of-arg boundary** (Session 115).
The bash-branch path regex previously allowed *zero* leading dots (`\.{0,2}/`), so a longer string like `cat .claude/skills/foo.py` would yield the substring `/skills/foo.py`. In the re-read detector, that fragment formed its own bucket separate from the legitimate full-path access, silently merging same-suffix files across different project subtrees. Anchored the regex to a start-of-arg boundary via leading `(?<![\w.])` and split the previously combined `\.{0,2}/` alternative into two explicit branches: `\.{1,2}/...` (dot-relative) and `/...` (absolute). Trade-off: `.name/...` style hidden-dir paths in Bash commands no longer contribute to the bash-branch detector at all; net coverage preserved on realistic workloads because the same files are also accessed through Read/Edit/Write (absolute paths, separate detector branch). Verified end-to-end: reaccessed-path count dropped 29 (polluted) → 23 (clean), top-10 free of phantom fragments.

**P1.4 — Marginal-cost attribution in `_detect_file_reaccesses`** (Session 116).
The detector previously summed each path's `cost_usd` as the entire turn cost for every turn that touched the path — a single Bash arg in a 10-tool turn would charge that path 100% of the turn cost, and two re-read paths sharing one turn would each be charged 100%, so `total_reaccess_cost` could exceed the underlying session cost. Session 112's audit attributed $1.11 (54% of session cost) to file_reaccesses on a single Bash arg. Fix: weight each turn's contribution by `path_reads_in_turn / total_tool_calls_in_turn`. Total contribution per turn is now bounded by the turn cost. Verified end-to-end on a 328-turn export: `total_reaccess_cost` $24.70 → $22.80 (46.3% → 42.7%), largest per-path drop $4.81 → $3.51.

### Tests

12 new regression tests covering the four P1 fixes (4 for P1.1+P1.2 in `audit_extract`, 8 for P1.3+P1.4 in `_detect_file_reaccesses`). 612 total tests pass (1 skipped, pre-existing).

---

## v1.32.0 — 2026-04-29

### Feature — project-scope and instance-scope audit support in `audit-session-metrics`

`audit-extract.py` now auto-detects the JSON scope from `data["mode"]` and branches into three code paths:

**Project scope** (`project_*.json`):
- Computes per-session cost ranking (`top_expensive_sessions`, top 5), poor-cache-health sessions (avg cache-hit < 80%, cost > $0.10), sessions with cache breaks, weekly cost and cache delta.
- Suppresses intra-session-only triggers (`idle_gap_cache_decay`, `session_warmup_overhead`) via a `SESSION_ONLY_METRICS` frozenset — these are not meaningful across a multi-session aggregate.
- Baseline gains `sessions_count` and `cost_per_session_avg_usd` in addition to session fields.

**Instance scope** (`instance/*/index.json`):
- Cross-project cost ranking (`top_expensive_projects`, top 5 with cost-share %), poor-cache projects, instance-wide cache-hit average.
- `fired_triggers` and `top_expensive_turns` are always `[]` — no per-turn data exists at instance scope.
- `None`-safe evaluation for `cache_hit_pct` and `cache_savings` (present-but-`null` in instance JSON); fixed by using `or 0` instead of `.get(k, 0)`.

**Schema**: `DIGEST_SCHEMA_VERSION` bumped `1.2 → 1.3` (additive — adds `scope`, `project_analysis`, `instance_analysis` fields).

**New reference playbooks** (three files under `audit-session-metrics/references/`):
- `project-quick-audit.md` — session breakdown table, poor-cache list, cache-break list, weekly trend, fix-first bullets.
- `project-detailed-audit.md` — extends quick with per-session turn drilldown, model distribution, cache-outlier hypothesis.
- `instance-quick-audit.md` — covers both quick and detailed at instance scope (same playbook, no per-turn drilldown available).

**SKILL.md routing**: `audit-session-metrics/SKILL.md` gains a scope routing dispatch matrix replacing the single-row session-only table; `session-metrics/SKILL.md` removes the scope guard that suppressed the post-export audit suggestion for project/instance exports and replaces it with scope-aware suggestions (project → per-session audit, instance → cross-project audit).

### Tests

20 new unit tests in `tests/test_session_metrics.py` (596 total, +20 since v1.31.0):
- `project_filename_parts` / `instance_filename_parts` parser variants.
- `detect_scope` from `data["mode"]` and from filename fallback.
- `compute_project_baseline` and `compute_instance_baseline` (including `None`-safe fields).
- `compute_project_session_analysis` and `compute_instance_project_analysis`.
- `build_digest` for all three scopes — schema version, `scope` field, suppressed triggers, empty instance fired/turns.
- Reference file existence and `v1.3` schema header anchors.

---

## v1.31.0 — 2026-04-29

### Feature — natural-language export dispatch keywords

`SKILL.md` gains an `export` dispatch keyword and a new `## Export shortcuts` section so users can invoke the skill with natural-language phrases documented in the plugin marketplace article.

**New dispatch keywords** (matched on `$ARGUMENTS[0]`):

- `export` — routes to `## Export shortcuts`; scans the full argument string to determine scope and output formats
- `project` — runs `--project-cost`, also picking up `--output` format flags from remaining args
- `project-cost` — alias for `project`

**Export shortcuts routing** (priority-ordered, first match wins):

1. Arg string contains `all-projects` → `--all-projects --output <formats>`
2. Arg string contains `project` → `--project-cost --output <formats>`
3. Otherwise → single session `--session <id> --output <formats>`

Format flags (`html`, `csv`, `md`/`markdown`) are inferred from the argument text; `json` is always appended per the post-export audit convention. Bare invocations without a format word default to `--output json`.

**Example mappings now explicitly documented:**

| Invocation | Command |
|---|---|
| `export session` | `--session … --output json` |
| `export session to html` | `--session … --output html json` |
| `export project` | `--project-cost --output json` |
| `export project to html` | `--project-cost --output html json` |
| `export project sessions to html` | `--project-cost --output html json` |
| `export all-projects` | `--all-projects --output json` |
| `export all-projects to html` | `--all-projects --output html json` |

**Bug fixed:** the prior `export all-projects` path would have matched the `project` substring check and silently routed to `--project-cost`; priority ordering now prevents this.

---

## v1.30.1 — 2026-04-29

### Fix — audit suggestion shown after every export

When the session-metrics skill is invoked with `--output html` (or `csv` or `md`), it now automatically appends `json` to the format list if absent. This ensures the JSON sidecar is always written and the `/audit-session-metrics quick <path>` suggestion is always shown — previously the hint was suppressed on html-only exports, requiring a redundant second `/session-metrics --output json` invocation before the audit could be run.

The Haiku model-pinning on the audit skill is unaffected — the skill still prints the slash-command suggestion rather than invoking the audit programmatically.

---

## v1.30.0 — 2026-04-29

### Feature — session archetype classifier (Tier-2 batch 2: detect-only) + first-turn cost share

The audit-session-metrics skill gains a top-level `session_archetype` classifier and adds `first_turn_cost_usd` / `first_turn_cost_share_pct` to the baseline. Both are forward-looking digest fields that v1.31.0's archetype-conditional severity overrides will consume; v1.30.0 ships the classifier as **detect-only** so it can be calibrated against real audit sidecars before the override matrix lands.

### Schema

`digest_schema_version` and `audit_schema_version` bump to **1.2** (additive — no breaking changes; v1.1 readers continue to work):

- New top-level field `session_archetype` (string enum): `agent_workflow` | `short_test` | `long_debug` | `code_writing` | `exploratory_chat` | `unknown`. The default `unknown` is intentional — biased toward not labelling at low confidence (same lesson as v1.29.0's forbidden `"other"` enum).
- New top-level field `archetype_signals` (debugging dict): `turns`, `subagent_share_pct`, `cache_hit_pct`, `cache_break_count`, `cache_break_pct`, `thinking_turn_pct`, `tool_call_total`, `edit_write_pct_of_tools`, `read_pct_of_tools`, `bash_pct_of_tools`, `tools_per_turn`. Non-negotiable for the v1.31.0 override matrix to read; also a debugging surface when archetype labels feel wrong.
- New baseline fields `first_turn_cost_usd` and `first_turn_cost_share_pct`. The "first turn" skips `<synthetic>` and `is_resume_marker` turns so resumed sessions don't mis-attribute warmup cost to a placeholder.

### Classifier priority chain (first match wins)

1. `agent_workflow` — `subagent_share_pct >= 30`
2. `short_test` — `0 < turns <= 5`
3. `long_debug` — `turns > 30` AND (`cache_break_pct > 2%` OR `cache_hit_pct < 70`)
4. `code_writing` — `turns > 5` AND `Edit + Write >= 25%` of tool calls
5. `exploratory_chat` — `turns > 5` AND `tool_call_total / turns < 1.0`
6. `unknown` — default

The 2% cache-break threshold mirrors the existing `cache_break` trigger's downgrade rule: a single break in 200 turns is below typical concern, so the existing trigger downgrades to low — and the archetype must not pin the same session as `long_debug` while the trigger is calling it routine.

### Calibration corpus (N=2)

The classifier was calibrated against the two unique session JSON exports in `exports/session-metrics/`:

- **session 1bf0a383** (168 turns, $8.44, 75% thinking, Edit/Write 15%, tools/turn 1.18) → `unknown` (no rule fires; honest fallback).
- **session 8461c187** (173 turns, $41.49, 32% thinking, Edit/Write 36%, cache_break_pct 0.58%) → `code_writing` (Edit/Write ≥ 25%; cache_break_pct below 2% so long_debug correctly skipped).

With N=2 the thresholds are working hypotheses, not measured baselines. Treat the override matrix slated for v1.31.0 as gated on at least ~10 audit sidecars existing across multiple session archetypes.

### Why detect-only first

The original Tier-2 plan bundled the archetype classifier and severity-override matrix into one ship. Splitting them means v1.30.0's archetype labels can be observed against real audit runs before the matrix locks in any decisions on guessed thresholds. If a label feels wrong on a real session, fix the threshold; only then ship the override matrix.

### Playbook contract

Both quick-audit.md and detailed-audit.md updated:

- Schema reference bumped to v1.2 with a v1.1 → v1.2 additive migration note.
- New "Session archetype" subsection in quick-audit.md (priority order + thresholds, no narrative in render).
- New "Session archetype + first-turn warmup" subsection in detailed-audit.md (one-sentence narrative in Baseline section when archetype != unknown; first_turn_cost_share narrative gated on `turns > 30 AND share > 5%`).
- Detailed-audit.md explicitly states first_turn_cost_share is **not** a `finding` and never enters `quick_wins` or `structural_fixes` — first-turn setup is unavoidable, so it's framing context, not actionable advice.

### Tests

15 new unit tests in `tests/test_session_metrics.py` (576 total, +15 since v1.29.0):

- `test_audit_extract_digest_schema_version_is_1_2` — schema bump + presence of new fields.
- 6 archetype trigger tests (one per enum value plus `unknown`).
- `test_audit_extract_archetype_long_debug_skips_low_density_breaks` — guards the 0.5% case from v1.29.0's calibration session.
- `test_audit_extract_archetype_priority_subagent_wins_over_short_test` — confirms the priority chain.
- `test_audit_extract_archetype_unknown_on_zero_turns` — short_test must require `turns > 0`.
- `test_audit_extract_archetype_signals_present_and_typed` — guards the v1.31.0 contract.
- 4 first_turn_cost_share tests covering computed share, synthetic-skip, resume-marker-skip, and zero-turn case.

**No `_SCRIPT_VERSION` bump.** This is an audit-skill change; the session-metrics parse cache is untouched.

---

## v1.29.0 — 2026-04-29

### Feature — cache-aware audit pass (Tier-2 batch 1: positive findings + idle-gap cache decay)

The audit-session-metrics skill gains a positive findings array and an idle-gap-cache-decay trigger. Both fix structural problems the v1.28.0 integration test surfaced: Haiku padding the negative findings array with `"other"` filler when no real waste pattern fired, and the audit having no way to celebrate good cache hygiene.

### Schema

`digest_schema_version` and `audit_schema_version` bump to **1.1** (additive — no breaking changes to v1.0 consumers):

- New top-level array `positive_findings` (capped at 3, parallel to `findings`). Findings carry `estimated_savings_usd` rather than `estimated_impact_usd` to signal direction.
- New positive metric enum: `cache_savings_high` (savings > 3× cost OR > $5 absolute) and `cache_health_excellent` (hit ratio > 90% AND zero `cache_breaks`).
- New negative metric enum entry: `idle_gap_cache_decay` — fires when a > 5-minute gap (the 5m ephemeral cache TTL boundary) is followed by a turn where `cache_creation_input_tokens > 50%` of billable input. Aggregates the top 3 events into one finding; severity scales by total rebuild cost (low < $0.30, medium $0.30–$1, high > $1).
- The `"other"` enum is now **forbidden** in v1.1 outputs (was "use sparingly" in v1.0). Both `findings` and `positive_findings` arrays may be empty — that is the correct outcome when no triggers fire, not a defect.

### Why these specific triggers

- **Empirical**: the v1.28.0 integration test (session 8461c187) ran the helper script and found 4 honest negative triggers + 1 obvious positive (cache_savings $11.45 vs $40.83 cost = 28% savings). Haiku padded the audit with 2 `"other"` rows describing the cache savings and a synthetic-turn note. `positive_findings` is the structural fix — Haiku now has a place to put that observation rather than treating it as filler.
- **Cache-relevant**: idle gaps > 5 min cross the cache TTL boundary; cache rebuilds afterwards are a real recoverable cost. The 5m threshold matches the actual cache TTL (independent of the HTML `--idle-gap-minutes` UI default of 10 min, which is a *visual* threshold).
- **Backed by digest data, not vibes**: every threshold uses values already in the digest (`cache_savings`, `cache_hit_pct`, `cache_breaks`, per-turn timestamps, `cache_write_tokens`).

### Playbook contract

Both `quick-audit.md` and `detailed-audit.md` updated:

- Per-array caps are explicit and **independent** — 7 negative + 3 positive in quick mode, 16 negative + 3 positive in detailed mode. The arrays do not compete for slots.
- The "no padding" rule is now stronger: the `other` enum is forbidden in v1.1 outputs.
- New "Positive findings" markdown section renders after the findings table and top-3 turns, before `fix_first` / `quick_wins`. Section is omitted when `positive_findings` is empty.
- New `{savings_suffix}` render rule: appends ` — saved $<savings:.2f>` when `estimated_savings_usd` is non-null.

### Tests

10 new tests in `test_session_metrics.py` (561 total, +10 since v1.28.0):

- Schema version bump asserts.
- `cache_savings_high` fires on ratio threshold (3×) and absolute threshold ($5); does not fire when low.
- `cache_health_excellent` fires above 90% AND requires zero cache breaks (hard suppression).
- `idle_gap_cache_decay` fires after a > 5-min gap with cache rebuild; skips short gaps; skips when no rebuild; severity scales with cost.

The two playbook anchor tests gained v1.29.0 anchors (`positive_findings`, `cache_savings_high`, `cache_health_excellent`, `idle_gap_cache_decay`, `1.1`).

### Files

- `scripts/audit-extract.py` — `evaluate_positive_triggers()`, `_detect_idle_gap_cache_decay()`, idle_gap branch in `evaluate_triggers()`, `CACHE_TTL_5M_SECONDS` constant, `DIGEST_SCHEMA_VERSION = "1.1"`.
- `references/quick-audit.md` and `references/detailed-audit.md` — schema, metric enum tables, finding-cap section, render template.

No `_SCRIPT_VERSION` bump on `session-metrics.py` (this is an audit-skill change; the parse cache is untouched).

---

## v1.26.2 — 2026-04-28

### Bug fix — accumulate user content blocks across the gap (parallel-spawn sibling fix)

Sibling fix to v1.26.1's `agent_links` accumulator. `_extract_turns` was overwriting `last_user_content` on every user JSONL entry, so when N parallel Task tool_results landed in N separate user entries between two assistant turns, only the last entry's content survived into `_preceding_user_content`. Downstream content-block counters under-counted `tool_result` (and `image`) blocks on the next assistant turn by N−1.

Concrete example on the dev project's mini fixture: gap before `msg_C` contains both `u4` (tool_result) and `u5` (sidechain text). Pre-fix the parser kept only `u5`'s text block — `u4`'s tool_result was dropped from the count entirely. Post-fix both survive. Project-wide on the live dev repo, the totals `tool_result` count rises to reflect every parallel-spawn fan-in.

### Fix

`_extract_turns()` now accumulates blocks from every user entry in the inter-assistant gap into `gap_user_blocks`, falls back to `gap_user_str` when only a string-form content (compaction summary) appeared, and resets both on assistant first-occurrence. The per-iteration `last_user_content` is preserved for the inner-loop logic (compaction guard, slash-command detection, agent_link extraction) — only the SNAPSHOT shape changes.

```python
# in user branch (after agent_links extension):
if isinstance(last_user_content, list):
    gap_user_blocks.extend(last_user_content)
elif isinstance(last_user_content, str):
    gap_user_str = last_user_content

# in assistant first-occurrence:
if gap_user_blocks:
    preceding_user[msg_id] = list(gap_user_blocks)
elif gap_user_str is not None:
    preceding_user[msg_id] = gap_user_str
else:
    preceding_user[msg_id] = last_user_content   # back-to-back-assistants fallback
gap_user_blocks = []
gap_user_str = None
```

No `_SCRIPT_VERSION` bump — `_extract_turns` runs after the parse cache, not before.

### Tests

- New: `test_extract_turns_accumulates_parallel_tool_result_blocks` — three parallel Task spawns + three user-entry tool_results between two assistant turns; asserts all three tool_result blocks survive into `_preceding_user_content`.
- Updated: `test_fixture_content_block_counts_per_turn` and `test_fixture_totals_content_blocks_aggregate` — the existing mini fixture's gap before `msg_C` already had two user entries (line 8 tool_result + line 9 sidechain text). Pre-fix the line-8 tool_result was dropped from `msg_C`'s preceding-user content; post-fix it's counted. The tests previously asserted the buggy old count (0) and the buggy total (2); both are now corrected to reflect the accurate behaviour (1 and 3).

517 tests pass (515 existing + 2 new since v1.26.1).

### Severity

Cost/token math was unaffected (those come from assistant `usage` fields, not user content). The fix corrects display-layer signals: `content_blocks.tool_result` and `content_blocks.image` per turn and project-wide, plus any downstream that reads them (turn-character classification, content-block waste analysis).

---

## v1.26.1 — 2026-04-28

### Bug fix — recover subagent attribution lost on parallel Task spawns

`_extract_turns` was overwriting `last_user_agent_links` on every user JSONL entry instead of accumulating, so when the assistant emitted N parallel Task tool_uses in one turn, only the LAST `(tool_use_id, agentId)` pair survived. The other N−1 spawns lost their linkage and every subagent turn from those spawns counted as an orphan.

**Real impact on this dev project (35 session blocks, $1,041 total spend):**

| Signal | Before fix | After fix |
|---|---:|---:|
| Orphan subagent turns | 477 | 8 |
| Attributed subagent turns | 1,221 | 1,697 |
| Spawns recognised | 92 | 93 |
| Subagent share of cost | 3.5% | 4.62% |

The headline 3.5% share was understated by ~30% because the parser was dropping a third of all `(tool_use_id, agentId)` pairs from the JSONL even though the data was present in every parent log.

### Fix

`scripts/session-metrics.py:_extract_turns()` — change overwrite to extend, and reset on assistant first-occurrence so pairs from one inter-assistant gap don't leak into the next:

```python
# was:  last_user_agent_links = agent_links
last_user_agent_links.extend(agent_links)
...
# inside `if msg_id not in preceding_user:` block, after capture:
last_user_agent_links = []
```

Render-time only — no parser-cache schema change, no `_SCRIPT_VERSION` bump, parse cache stays valid.

### Tests

Two regression tests added near the existing Phase-B suite:

- `test_extract_turns_accumulates_parallel_task_agent_links` — synthesises an assistant turn with two parallel Task tool_uses + two separate user `tool_result` entries, asserts both `(tuid, agentId)` pairs survive into the next assistant's `_preceding_user_agent_links`.
- `test_extract_turns_resets_agent_links_after_assistant_first_occurrence` — asserts that pairs do NOT leak from one assistant gap into a later assistant's `_preceding_user_agent_links`.

516 tests pass (514 existing + 2 new).

### Caveat

8 turns remain orphaned in the dev project. These are genuine unrecoverable cases — two subagent JSONL files (`a51a9e01fd9c84bd2`, `af258417369f5ebc6`) lack any `toolUseResult.agentId` in their parent log, most likely because the subagent crashed/was killed before its tool_result could be written back. The headline keeps its `lower bound — N orphan turns excluded` caveat for the residual cases.

---

## v1.26.0 — 2026-04-28

### Observational subagent-cost framing — share, coverage, within-session split, warm-up signals

Builds on v1.7.0 Phase-B parent-prompt attribution to answer the question "what fraction of my session went to subagents, and how should I read that number?". Render-time only — no parser changes, no `_SCRIPT_VERSION` bump, parse cache stays valid.

### What's new

**Headline `Subagent share of cost` card** — top-of-report KPI in HTML (single + instance) and a row in the MD summary table. Reads `sum(attributed_subagent_cost) / totals.cost` and renders as `X% ($Y of $Z) across N spawns`. Branches on `--include-subagents`:
- on, with attributed turns: shows the share, with `lower bound — N orphan turns excluded` when `subagent_attribution_summary.orphan_subagent_turns > 0`.
- on, no subagent activity: `0% — no subagent activity`.
- off: `attribution disabled — re-run with --include-subagents` (avoids the deceptive 0% reading the previous default would have produced).

**Attribution coverage block** — small section under the by-subagent table that surfaces what was previously buried in `subagent_attribution_summary`: orphan turn count, cycles detected, max nesting depth, and spawn → attributed-turn fanout. Frames the headline as observational signal, not a precise measurement.

**Within-session spawning split** — per-session table comparing median *combined* turn cost (parent direct + attributed subagent) on spawning vs. non-spawning turns. Renders only for sessions with ≥3 turns in each bucket. Holds task / model / context constant within a session, but is explicitly labelled descriptive — selection bias remains because users delegate the hardest sub-tasks. *Not* a counterfactual estimate.

**Warm-up columns in `by_subagent_type`**:
- `First-turn %` — median across invocations of `first_turn.cost_usd / total_invocation_cost`. High = short-lived agents pay setup tax without amortising.
- `SP amortised %` — fraction of invocations whose turn ≥2 read from cache (system-prompt cache write paid back at least once).
- Visible only when `--include-subagents` is on AND at least one invocation was observed.

**Per-prompt badge** — appended `(NN% of combined cost)` to the existing `+N subagents` annotation. Labelled "combined", not "of turn", because the visible Cost column shows direct cost only; "% of turn" would mathematically imply the parent was 37% of itself.

### Honesty notes baked into the surfaces

- "Share" is used everywhere instead of "overhead" — overhead implies the cost would otherwise be unpaid, exactly the unanswered counterfactual.
- The headline is documented as a lower bound whenever orphans exist.
- The within-session split's body text states explicitly that descriptive correlation is *not* a counterfactual estimate.
- The synthetic-A/B benchmark and analytical crossover calculator are deferred to follow-ups; this release does not pretend to answer the causal "did delegating cost more" question.

### What changed in code

- `_empty_subagent_row` gains `invocation_count`, `first_turn_share_pct`, `sp_amortisation_pct`.
- `_build_by_subagent_type` groups subagent turns by `subagent_agent_id` per-invocation and rolls per-invocation metrics up to type rows. Aggregation is at report-build time, not per-turn — no parse-cache schema change.
- New helpers: `_compute_subagent_share`, `_compute_within_session_split`, `_compute_instance_subagent_share`, `_median`, `_build_subagent_share_card_html`, `_build_attribution_coverage_html`, `_build_within_session_split_html`, `_build_subagent_share_md`, `_build_within_session_split_md`.
- `_build_report` precomputes `subagent_share_stats` + `subagent_within_session_split` and stashes them on the report dict so JSON/CSV/MD/HTML all see the same values.
- `_build_instance_report` aggregates per-project shares and runs the within-session split over the flattened `all_sessions_out`. Instance report now propagates `include_subagents`.
- `render_html`, `render_md`, `_render_instance_html`, `_render_instance_md` updated.
- CSV `by_subagent_type` block gains `invocation_count`, `first_turn_share_pct`, `sp_amortisation_pct` columns.
- 8 new tests in `tests/test_session_metrics.py`. Existing 506 tests remain green.

### Known limitations

- The headline relies on Phase-B attribution; orphan rate matters. On a real session during manual verification, 45 of ~150 subagent turns were orphans (chains the three-pass linkage couldn't resolve back to a root prompt) — the share was clearly disclosed as a lower bound.
- The within-session split has within-session selection bias and does not replace a synthetic A/B test for the causal question.
- The compression-ratio signal (parent `tool_result` payload size vs. subagent gross spend) was considered but deferred — would require a parser change to capture `tool_result` text length and bump `_SCRIPT_VERSION`.

---

## v1.25.1 — 2026-04-28

### Bug fix — `iterations:null` crash when advisor is not enabled

`<synthetic>` resume-marker turns written by environments where the advisor feature
is not active (e.g. the desktop app) emit `"iterations": null` in the usage dict
rather than omitting the key. `u.get("iterations", [])` returns `None` when the key
exists with a null value, causing `TypeError: 'NoneType' object is not iterable` in
`_cost` and `_advisor_info` whenever a project-scope run included those sessions.

- Replace `u.get("iterations", [])` with `u.get("iterations") or []` in both
  `_cost` and `_advisor_info`. Handles absent, null, and valid-list cases identically.

---

## v1.25.0 — 2026-04-28

### Advisor turn support — cost correction + surface

The Claude Code Advisor (`advisor()` tool) runs a second model against the full conversation
transcript. Its tokens were previously hidden in `usage.iterations[]` and not counted, causing
advisor turns to be silently under-priced by up to 6.6×.

- **Cost correction**: `_cost()` now reads `usage.iterations[type=="advisor_message"]` and
  bills advisor tokens at the advisor model's list rates. The corrected `cost_usd` propagates
  to all session/project/instance aggregates.
- **New per-turn fields**: `advisor_calls`, `advisor_cost_usd`, `advisor_model`,
  `advisor_input_tokens`, `advisor_output_tokens`.
- **Session field**: `advisor_configured_model` from the top-level `advisorModel` JSONL field.
- **Content classification**: `server_tool_use` → letter `v`; `advisor_tool_result` → letter `R`.
  `"advisor"` appears in tool names and the drawer tools list.
- **Dashboard card**: "Advisor calls" (amber badge, auto-hidden when unused).
- **Session table**: amber annotation/badge in `--project-cost` HTML and text output.
- **CLI footer**: `Advisor calls : N call(s)  +$X.XXXX` when advisor was used.
- **Per-turn drawer**: cost section shows Primary / Advisor / Cost breakdown; TOKENS section
  shows Advisor input / Advisor output rows. Both hidden on non-advisor turns.
- **Schema docs** (`references/jsonl-schema.md`): four new fields documented.
- Graceful degradation — sessions without advisor activity produce identical output.

## v1.24.0 — 2026-04-28

### Fix: `file_reread` classification accuracy

- First access in any context segment no longer flagged as a wasteful re-read (only the
  2nd+ read in the same segment counts).
- Subagent-boundary re-reads (model switch or session resume) are now shown as informational
  — no ⚠ badge — because accessing files in a fresh context is expected and unavoidable.
- Drawer explanation splits into two branches: cross-context reads get tips on `offset`/`limit`;
  same-context re-reads get tips on `Grep` / `Read` with offsets.
- `_BASH_PATH_RE` extended-allowlist: hidden directories (`.claude`, `.git`) no longer produce
  false path entries in the classification detail.

## v1.23.0 — 2026-04-28

### Turn Character section in every turn drawer + cross-browser overflow fix

- Clicking any timeline row now shows a "Turn Character" section in the detail drawer with a
  colour-coded classification label and a one-sentence explanation derived from that turn's
  actual token data (file basenames, cache percentages, block counts, etc.).
- Fixed the ⚠ risk badge overflowing outside the timeline cell in Opera and other non-Chromium
  browsers.

## v1.22.0 — 2026-04-28

### 9-category turn waste classification

Classifies every assistant turn into one of: `productive`, `retry_error`, `file_reread`,
`oververbose_edit`, `dead_end`, `cache_payload`, `extended_thinking`, `subagent_dispatch`,
or `normal`.

- Turn Character column in the HTML timeline with colour-coded labels and ⚠ risk badges.
- Stacked-bar chart in the dashboard (waste distribution by session).
- Drill-down cards per waste category with turn count, token share, and examples.
- `turn_character` / `turn_risk` fields in JSON and CSV output.

## v1.21.0 — 2026-04-27

### Four inline markers in the HTML detail timeline

- Idle-gap dividers: slate pill `▮ N min idle` between turns when wall-clock gap ≥ threshold
  (`--idle-gap-minutes`, default 10; set 0 to disable).
- Model-switch dividers: cyan pill `⇄ Model: prev → cur` when the model changes mid-session.
- Truncated-response badge: orange `✂ truncated` on `max_tokens` turns + dashboard KPI card.
- Cache-break inline badge: amber `⚡` on turns that invalidate the prompt cache.

`stop_reason` and `is_cache_break` added as CSV columns.

## v1.20.1 — 2026-04-27

### Fix: spurious skill-tag badge after context compaction

Context-compaction summaries contain verbatim prior-session text including slash-command XML
tags. These were producing a false badge on the first post-compaction turn. Fixed by detecting
the compaction sentinel and skipping slash-command extraction for those entries.

## v1.20.0 — 2026-04-27

### Skill/slash-command badge in HTML timeline model column

When a turn was triggered by a skill invocation or slash command (e.g. `session-metrics`), a
small purple badge appears inline in the timeline. The turn drawer also shows a "Skill" row.

## v1.19.0 — 2026-04-26

### Per-turn latency + session wall-clock

- `latency_seconds` per turn: wall-clock seconds from preceding user entry to the assistant
  response.
- `wall_clock_seconds` per session (first user prompt → last assistant).
- Markdown summary gains `Wall clock` and `Mean turn latency` rows.
- `--compare-run-prompt-steering` wrapper for prompt-steering sweeps via `--compare-run`.

## v1.18.2 — 2026-04-25

### Fix: Console theme turn drawer transparent background

## v1.18.1 — 2026-04-25

### Fix: cache-breaks/skills/subagents sections duplicated in detail.html

The cross-cutting summary sections (cache breaks, skills, subagents) now appear only in the
dashboard page, not in both the dashboard and the detail page.

## v1.18.0 — 2026-04-25

### `--include-subagents` on by default

Subagent JSONL files are now included in session reports automatically. Opt out with
`--no-include-subagents`. Also fixes the subagent hint label in the Insights dashboard card.

## v1.17.1 — 2026-04-25

### Fix: cache-breaks section unstyled in non-default themes

Cache-break section elements now have correct colours across all four themes (Beacon, Console,
Lattice, Pulse).

## v1.17.0 — 2026-04-25

### Subagent → parent-prompt token attribution

Maps every subagent turn's tokens back to the originating user prompt via a three-stage
linkage chain (`tool_use.id → prompt_anchor → agent_id → root`).

- HTML prompts table sorts by `cost_usd + attributed_subagent_cost` by default — the "what
  action cost the most" lens.
- "Subagents +$" column and "+N subagents" row badge auto-appear when attribution is present.
- `--sort-prompts-by {total,self}` and `--no-subagent-attribution` flags.
- Three new CSV columns: `attributed_subagent_tokens`, `attributed_subagent_cost`,
  `attributed_subagent_count`.

## v1.16.0 — 2026-04-25

### Cross-cutting sections: cache breaks, skills & slash commands, subagent summary

Four new summary sections in the HTML dashboard for every session / project export:
cache-break cost analysis, skill/slash-command invocation table, and subagent type breakdown.
`--cache-break-threshold N` (default 500 tokens) controls the minimum re-fill size to report.

## v1.15.2 — 2026-04-25

### 10 additional model pricing entries + regex/prefix matching tier

Extended `_PRICING` with 10 more models. Prefix matching covers entire model families without
requiring exact `model_id` entries. Stderr advisory emitted for truly unknown models.

## v1.15.1 — 2026-04-25

### Non-Claude model pricing: GLM, Gemma 4, Qwen 3.5

Correct per-token rates for GLM-4.7 / GLM-5 / GLM-5.1 (Z.ai), Gemma 4 (Google / Ollama
local variants), and Qwen 3.5:9b. Prevents silent Sonnet-rate mis-attribution on mixed-model
sessions.

## v1.15.0 — 2026-04-24

### 4-theme picker embedded in every HTML export

All four themes (Beacon, Console, Lattice, Pulse) are embedded in every generated HTML file.
Users switch at view-time via a top-nav button strip; choice persists across Dashboard↔Detail
and instance→project drill-down links via URL hash + localStorage. Console is the default.
Also: 25% font size increase, Highcharts bundle gated to single-page variant only.

## v1.14.1 — 2026-04-23

### Fix: instance dashboard chart shows real token breakdowns

Instance daily chart now shows stacked input/output/cache-read/cache-write token breakdown per
day (was showing cost-only bars). Day axis label added.

## v1.14.0 — 2026-04-22

### Instance-level "all projects" dashboard

`--all-projects` generates a single dashboard aggregating every project under your Claude Code
install. Summary cards, daily cost timeline, projects table (sorted by cost, with clickable
drilldown links to per-project dashboards), and reused weekly/punchcard/time-of-day insights.
`--no-project-drilldown` fast path, `--projects-dir PATH` override for custom installs.
Output lands in `exports/session-metrics/instance/YYYY-MM-DD-HHMMSS/`.

## v1.13.1 — 2026-04-22

### Fix: `_resolve_tz` docstring correction

Corrected internal docstring that incorrectly described an `Intl.DateTimeFormat` implementation.

## v1.13.0 — 2026-04-22

### IFEval paired-samples statistics: McNemar test + Wilson CI

`--compare` HTML report gains a statistical significance table: McNemar χ² + p-value and
Wilson 95% CI for each IFEval pass-rate comparison. Small-N banner suppresses stats when
fewer than 6 paired samples are available.

## v1.12.0 — 2026-04-22

### `--strict-tz` flag + Windows tzdata hint

`--strict-tz` exits with a clear error when the system's zoneinfo database cannot resolve the
requested IANA timezone (the default is lenient — falls back to UTC). On Windows, an advisory
hints to install the `tzdata` pip package when `ZoneInfo` fails to load.

## v1.11.3 — 2026-04-21

### Audit Tier 3 fixes: test hygiene + cost note

Added a comment inside `_cost()` pointing to the fast-mode 6× multiplier caveat in
`references/pricing.md`. Test temp-directory randomisation and `atexit` contract pin.

## v1.11.2 — 2026-04-21

### Audit Tier 2 hardening: contract pin

`atexit` advisory handler is now registered at module load time (not lazily), so it fires even
in early-exit paths.

## v1.11.1 — 2026-04-21

### Audit Tier 1 hardening + `--allow-unverified-charts` flag

- Theme-aware drawer backdrop, `<meta name="chart-lib">` in every HTML export, `@media print`
  hide rules for cleaner PDF output.
- Unknown-model `stderr` advisory at process exit (lists models that fell through to Sonnet
  default pricing).
- Fast-mode `stderr` advisory with count of `usage.speed == "fast"` turns.
- `--compare`, `--compare-prep`, `--compare-run`, `--count-tokens-only` are now mutually
  exclusive via argparse group.
- `--allow-unverified-charts` opt-in to skip Highcharts vendor SHA-256 check for offline
  workflows.

## v1.11.0 — 2026-04-21

### Clickable per-turn timeline rows with full detail drawer

Every row in the HTML detail timeline is now clickable. Clicking opens a right-side sliding
drawer showing: turn metadata (model, cost, tokens, stop reason), prompt text, all tool calls
with input previews, and a linked prompts table. Keyboard-accessible (Enter/Escape).

## v1.10.0 — 2026-04-20

### Custom prompt commands in SKILL.md

SKILL.md dispatch extended with custom prompt-command rows so Claude routes natural-language
requests like "compare these two sessions" or "run a headless compare" to the correct flags
without ambiguity. README updated with command examples.

## v1.9.0 — 2026-04-20

### `--compare-run` headless automation

`--compare-run` spawns two `claude -p` sessions headlessly, feeds each one the same prompt
suite, and then calls `--compare` on the resulting JSONLs — a single command for an end-to-end
A/B model benchmark. `[1m]` default effort prefix added to prompt suite entries.

## v1.8.0 — 2026-04-20

### Session-resume detection: `claude -c` and terminal-exit markers

Detects two resume patterns in the JSONL: the `<synthetic>` model marker (auto-continuation
after context limit) and the `/exit` + re-open pattern (manual terminal-exit resume). Both are
surfaced as timeline dividers and counted in the dashboard "Session resumes" card. Terminal
exits are visually distinguished from normal resumes.

## v1.7.1 — 2026-04-19

### Subagent-related fixes

Minor UI fixes to subagent display in the dashboard and timeline.

## v1.7.0 — 2026-04-19

### `--compare` two-session A/B comparison (Phases 1–9 + trigger hardening)

`session-metrics --compare A.jsonl B.jsonl` produces a paired comparison: side-by-side token/
cost/cache metrics, IFEval-style pass-rate evaluation (sentinel-tagged prompt suite, 10 built-in
predicates), paired-turn table, quality-vs-cost verdict, and a shareable single-page HTML
report. Also includes `--compare-prep` to generate a canonical prompt suite, and
`--count-tokens-only` (API-key path) to estimate token counts before running.

Three-layer trigger discipline: argparse mutex, SKILL.md `$ARGUMENTS[0]` dispatch gate, and
description-level LLM guard prevent accidental invocation on unrelated prompts.

## v1.6.0 — 2026-04-19

### `/usage`-style Usage Insights panel on the dashboard

New dashboard section mirroring the data Claude Code's `/usage` command surfaces: total spend,
cache efficiency, model breakdown, top-sessions table, and conditional insight cards
(model-compare nudge, fast-mode advisory, etc.). Threshold-gated so cards only appear when the
data is meaningful.

## v1.5.0 — 2026-04-18

### Resume-marker cost tracking

Session-resume markers now carry a token/cost estimate for the context re-fill cost incurred
by resuming the conversation. Surfaced in the dashboard card and timeline divider subtitle.

## v1.4.1 — 2026-04-18

### Fix: terminal-exit marker visually distinguished from resume marker

The dashboard card correctly reported "2 resumes · 1 terminal exit" but the timeline dividers
were rendering all three as identical "↻ Session resumed" pills. Terminal-exit markers now
render with a distinct visual style (`⊠ Session ended`) so both surfaces tell a consistent
story.

## v1.4.0 — 2026-04-18

### Session-resume detection (initial)

Detects `claude -c` resumes via the `/exit` + `<synthetic>` fingerprint and surfaces resume
events in the dashboard and HTML timeline.

## v1.3.0 — 2026-04-18

### Content-block distribution (Proposal B) + streaming-dedup fix

Per-turn and aggregate counts for `thinking`, `tool_use`, `text`, `tool_result`, and `image`
content blocks. HTML Content column with compact letter encoding and tooltips. Extended-thinking
and Tool-calls dashboard cards. CSV gains five new block-count columns.

Fix: multi-entry streaming messages were losing all but the last content block. `_extract_turns`
now unions blocks across all occurrences of the same `message.id`.

## v1.2.0 — 2026-04-18

### Ephemeral cache TTL drilldown (Proposal A) — pricing accuracy

Splits `cache_creation_input_tokens` into 5-minute and 1-hour buckets and prices each at its
correct Anthropic rate. Previously all cache writes were charged at the 5m rate, causing
up to 60% undercount of the cache-write component for sessions that used 1-hour TTL.

HTML: TTL badge on CacheWr cells. Text/MD: `*` suffix on affected cells. CSV/JSON: three new
per-turn fields. Dashboard: Cache TTL mix card.

## v1.1.0 — 2026-04-18

### uPlot + Chart.js MIT-licensed chart alternatives

`--chart-lib {highcharts,uplot,chartjs,none}`. uPlot (~45 KB, MIT) and Chart.js (~70 KB, MIT)
are fully vendored with SHA-256 manifest verification. Use `--chart-lib uplot` for a fully
MIT-licensed export; `--chart-lib none` for a zero-JS archive.

## v1.0.0 — 2026-04-17

### First stable release

- Per-turn token/cost/cache breakdown across 5-hour session blocks.
- Multi-format export: text, JSON, CSV, Markdown, HTML (2-page dashboard + detail).
- Usage insights: weekly roll-up, session duration + burn rate, hour-of-day punchcard,
  weekday × hour heatmap, 5-hour session-block analysis.
- Vendored Highcharts (`--chart-lib highcharts`) with SHA-256 integrity check.
- Parse cache (`~/.cache/session-metrics/`) for fast re-analysis of unchanged JSONLs.
- Input validation, path containment, timezone support (`--tz`, `--utc-offset`).
- Pricing table covers claude-opus-4-7 / sonnet-4-6 / haiku-4-5 + historical models.
